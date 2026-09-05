#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "research"))

import build_rom as br  # noqa: E402
import build_rom_v1 as v1  # noqa: E402
import tail_failure_lab as tail_lab  # noqa: E402
from lupine3d_v4.levels import build_segment_table, compile_level  # noqa: E402
from sm83emu import CGB  # noqa: E402
from playtest import set_test_world_byte

BASELINE_SHA256 = "0b5794c93b43b38a0dd2a76cf4e289f0317dd9b10314632ff366402ecd37fa00"
DOUBLE_SPEED_HZ = 8_388_608


class Lupine3DTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rom, cls.assembler, cls.manifest = br.make_rom()
        cls.symbols = cls.assembler.labels
        cls.grid = br.make_map()
        cls.renderer_level = compile_level(ROOT / "levels" / "renderer_benchmark.json")

    def boot_to_main(self) -> CGB:
        cgb = CGB(self.rom, self.symbols)
        cgb.run(until_pc=self.symbols["main_loop"], max_steps=2_000_000)
        return cgb

    @staticmethod
    def set_pose(cgb: CGB, x_q8: int, y_q8: int, angle: int) -> None:
        for address, value in ((br.PLAYER_XL, x_q8 & 255), (br.PLAYER_XH, x_q8 >> 8), (br.PLAYER_YL, y_q8 & 255), (br.PLAYER_YH, y_q8 >> 8), (br.ANGLE, angle)):
            set_test_world_byte(cgb, address, value)

    @staticmethod
    def read_block(cgb: CGB, address: int, count: int) -> bytes:
        return bytes(cgb.read8(address + i) for i in range(count))

    @staticmethod
    def read_bg_patterns(cgb: CGB, bank: int, first: int, count: int) -> bytes:
        return b"".join(bytes(cgb.vram[bank][br.bg_tile_address(tile) - 0x8000:br.bg_tile_address(tile) - 0x8000 + 16])
                        for tile in range(first, first + count))

    def test_rom_header_checksums_and_manifest(self) -> None:
        rom = self.rom
        self.assertEqual(len(rom), br.ROM_BYTES)
        self.assertEqual(rom[0x0104:0x0134], br.NINTENDO_LOGO)
        self.assertEqual(rom[0x0134:0x013C], b"LUPINE3D")
        self.assertEqual(rom[0x0143], 0xC0)
        self.assertEqual(rom[0x0147], 0x19)
        self.assertEqual(rom[0x0148], 0x07)
        self.assertEqual(rom[0x0149], 0x00)
        self.assertEqual(rom[0x014C], 0x06)
        self.assertEqual(rom[0x0040], 0xC3)
        self.assertEqual(rom[0x0041] | (rom[0x0042] << 8), self.symbols["vblank_isr"])
        self.assertLessEqual(br.HRAM_BYTES_USED, 0x7F)
        self.assertTrue(all(0xFF80 <= address <= 0xFFFE for address in br.HRAM_LAYOUT.values()))
        header = 0
        for value in rom[0x0134:0x014D]:
            header = (header - value - 1) & 0xFF
        self.assertEqual(header, rom[0x014D])
        total = (sum(rom) - rom[0x014E] - rom[0x014F]) & 0xFFFF
        self.assertEqual((rom[0x014E] << 8) | rom[0x014F], total)
        self.assertLessEqual(self.manifest["engine_end"], 0x8000)
        self.assertEqual(self.manifest["rays"], 80)
        self.assertEqual(self.manifest["physical_columns"], 160)
        self.assertEqual(self.manifest["ray_width_pixels"], 2)
        self.assertEqual(self.manifest["projection_fractional_bits"], 5)
        self.assertEqual(self.manifest["framebuffer_bytes"], 0)
        self.assertEqual(self.manifest["maximum_commit_blocks"], 176)
        self.assertEqual(self.manifest["rom_banks"], 256)
        self.assertEqual(self.manifest["cartridge_type"], "MBC5")
        self.assertEqual(self.manifest["projection_lut_bytes"], br.PROJECTION_LUT_BYTES)
        self.assertTrue(self.manifest["projection_lut_exact"])
        self.assertEqual(self.manifest["product_lut_bytes"], br.PRODUCT_LUT_BYTES)
        self.assertTrue(self.manifest["product_lut_exact"])
        self.assertTrue(self.manifest["vblank_input_sampling"])
        self.assertTrue(self.manifest["input_edge_latching"])
        self.assertFalse(self.manifest["render_pose_mutated_by_interrupts"])
        self.assertEqual(self.manifest["ray_depth_buffer_bytes"], br.RAYS)
        self.assertEqual(self.manifest["ray_segment_buffer_bytes"], br.RAYS)
        self.assertEqual(self.manifest["pixel_segment_buffer_bytes"], br.PHYSICAL_COLUMNS)
        self.assertTrue(self.manifest["segment_aware_reconstruction"])
        self.assertEqual(self.manifest["vram_profile"], "entity-heavy")
        self.assertEqual(self.manifest["entity_atlas_patterns"], 121)
        self.assertEqual(self.manifest["renderer_atlas_patterns"], 121)
        self.assertEqual(self.manifest["oam_reserved_ui_entries"], 10)
        self.assertEqual(self.manifest["oam_entity_capacity"], 16)
        self.assertEqual(self.manifest["level_format"], "lupine-level-v2")
        self.assertEqual(self.manifest["active_level_doors"], 4)
        self.assertEqual(self.manifest["maximum_level_doors"], 4)
        self.assertEqual(self.manifest["safe_spawn_radius_cells"], 5)
        self.assertTrue(self.manifest["exit_beacon"])
        self.assertTrue(self.manifest["animated_door"])
        self.assertFalse(self.manifest["world_height_surface_rails"])
        self.assertTrue(self.manifest["material_geometry_decoupled"])
        self.assertEqual(self.manifest["maximum_level_sightline"], 6)
        self.assertEqual(self.manifest["live_hud_fields"], ["health", "remaining_hostiles", "exit_status"])
        self.assertEqual(self.manifest["sha256"], hashlib.sha256(rom).hexdigest())

    def test_build_is_deterministic_and_v1_oracle_is_frozen(self) -> None:
        rom2, _, _ = br.make_rom()
        self.assertEqual(self.rom, rom2)
        old_rom, _, _ = v1.make_rom()
        self.assertEqual(hashlib.sha256(old_rom).hexdigest(), BASELINE_SHA256)

    def test_camera_plane_tables_are_symmetric(self) -> None:
        tables = br.make_tables()
        offsets = [
            int.from_bytes(tables["ray_offsets"][i:i + 2], "little", signed=True)
            for i in range(0, br.RAYS * 2, 2)
        ]
        corrections = list(tables["ray_corrections"])
        for left, right in zip(offsets, reversed(offsets)):
            self.assertEqual(left, -right)
        self.assertEqual(corrections, list(reversed(corrections)))
        physical_offsets = [
            int.from_bytes(tables["physical_offsets"][i:i + 2], "little", signed=True)
            for i in range(0, br.PHYSICAL_COLUMNS * 2, 2)
        ]
        physical_corrections = list(tables["physical_corrections"])
        self.assertEqual(physical_offsets, [-x for x in reversed(physical_offsets)])
        self.assertEqual(physical_corrections, list(reversed(physical_corrections)))
        self.assertEqual(len(tables["projection_half"]), 512)


    def test_wall_material_patterns_are_low_noise_and_side_lit(self) -> None:
        self.assertEqual(len(br.WALL_PATTERNS), br.STYLE_COUNT)
        self.assertEqual(len(br.WALL_MATERIAL_NAMES), br.STYLE_COUNT)
        for style, pattern in enumerate(br.WALL_PATTERNS):
            self.assertEqual(len(pattern), 8)
            base = br.WALL_BASE_COLORS[style]
            for row in pattern:
                self.assertEqual(len(row), 4)
                self.assertTrue(all(color in (2, 3) for color in row))
                # Flat base rows are permitted; a full-width contrasting row
                # would recreate the v0.2.0 horizontal banding regression.
                self.assertFalse(len(set(row)) == 1 and row[0] != base)

        # The primary plaster material is deliberately texture-free. Exact
        # DDA side selection, rather than screen-space stripes, carries depth.
        self.assertTrue(all(color == 2 for row in br.WALL_PATTERNS[0] for color in row))
        self.assertTrue(all(color == 3 for row in br.WALL_PATTERNS[1] for color in row))

        plaster_light = sum(color == 2 for row in br.WALL_PATTERNS[0] for color in row)
        plaster_shadow = sum(color == 2 for row in br.WALL_PATTERNS[1] for color in row)
        panel_light = sum(color == 2 for row in br.WALL_PATTERNS[2] for color in row)
        panel_shadow = sum(color == 2 for row in br.WALL_PATTERNS[3] for color in row)
        self.assertGreater(plaster_light, plaster_shadow)
        self.assertGreater(panel_light, panel_shadow)
        self.assertEqual(self.manifest["full_width_contrast_bands"], 0)
        self.assertTrue(self.manifest["world_anchored_face_events"])
        self.assertEqual(len(br.make_seam_tile_lookup()), 256)
        self.assertEqual(br.make_seam_tile_lookup()[0], br.WALL_TILE_BASE)
        self.assertTrue(all(len(set(row)) == 1 for pattern in br.WALL_PATTERNS for row in pattern))

    def test_industrial_hud_and_spatial_clarity_grammar(self) -> None:
        self.assertEqual(len(br.make_ui_tiles()), 16 * 16)
        self.assertEqual(len(br.make_weapon_tiles()), 16 * 16)
        self.assertEqual(br.ATLAS_TILE_BASE, 119)
        self.assertEqual(br.STATIC_VIEW_TILES, 23)
        self.assertEqual(br.surface_detail_mask([0] * 8), 0)
        self.assertEqual(br.surface_detail_mask([2] * 8), 0)
        self.assertEqual(br.surface_detail_mask([3] * 8), 0)
        self.assertEqual(br.SURFACE_RAIL_VARIANTS, 0)
        self.assertNotEqual(br.CREASE_STYLE, br.DOOR_SPINE_STYLE)
        self.assertNotEqual(br.CREASE_STYLE, br.TECH_RIB_STYLE)

        # An uninterrupted machinery wall has no special contrast line at the
        # old eye-height row. Every interior tile row remains phase-free.
        _, horizon_tile = br.reference_tile_signature_and_bytes(
            [16] * 8, [2] * 8, br.SURFACE_RAIL_Y0,
        )
        rows = [horizon_tile[index:index + 2] for index in range(0, 16, 2)]
        self.assertEqual(len(set(rows)), 1)

        tops = [16] * br.PHYSICAL_COLUMNS
        alongs = [0] * br.PHYSICAL_COLUMNS
        same_segment = [1] * br.PHYSICAL_COLUMNS
        material_keys = [0x20] * 80 + [0x40] * 80
        material_styles = [0] * 80 + [2] * 80
        decorated, events = br.decorate_surface_events(
            tops, material_styles, material_keys, alongs, same_segment,
        )
        self.assertEqual(decorated, material_styles)
        self.assertEqual(events, 1)

        physical_segments = [1] * 80 + [2] * 80
        decorated, _ = br.decorate_surface_events(
            tops, [0] * br.PHYSICAL_COLUMNS, [0x20] * br.PHYSICAL_COLUMNS,
            alongs, physical_segments,
        )
        self.assertNotEqual(decorated[79], br.CREASE_STYLE)
        self.assertEqual(decorated[80], br.CREASE_STYLE)

        door_keys = [0x20] * br.PHYSICAL_COLUMNS
        door_segments = [1] * br.PHYSICAL_COLUMNS
        for index in range(70, 90):
            door_keys[index] = 0x60
            door_segments[index] = 3
        decorated, _ = br.decorate_surface_events(
            tops, [0] * br.PHYSICAL_COLUMNS, door_keys, alongs, door_segments,
        )
        self.assertEqual(decorated[70], br.CREASE_STYLE)
        self.assertEqual(decorated[79], br.DOOR_SPINE_STYLE)
        self.assertEqual(decorated[80], br.DOOR_SPINE_STYLE)
        self.assertEqual(decorated[89], br.CREASE_STYLE)

        tilemap = br.make_tilemap()
        self.assertTrue(all(32 <= tilemap[y * 32 + x] < 128
                            for y in range(12,18) for x in range(20)))

        # Exercise the actual ROM routine and both page maps. LCD-off makes
        # this a deterministic VRAM-content check rather than a mode-timing test.
        cgb = self.boot_to_main()
        cgb.write8(0xFF40, 0)
        cgb.write8(br.PLAYER_HEALTH, 7)
        cgb.write8(br.EXIT_ACTIVE, 1)
        cgb.call_subroutine("prepare_hud_tiles")
        cgb.call_subroutine("update_hud_tiles")
        for map_offset in (0x1800, 0x1C00):
            base = map_offset + br.HUD_ROW * 32
            self.assertEqual(cgb.vram[0][base + br.HUD_HEALTH_TENS_X], br.HUD_DIGIT_BASE)
            self.assertEqual(cgb.vram[0][base + br.HUD_HEALTH_ONES_X], br.HUD_DIGIT_BASE + 14)
            self.assertEqual(cgb.vram[0][base + br.HUD_STATUS_TENS_X], br.HUD_DIGIT_BASE)
            self.assertEqual(cgb.vram[0][base + br.HUD_STATUS_ONES_X], br.HUD_DIGIT_BASE + 2)

    def test_boot_matches_descriptor_and_microstrip_host_models(self) -> None:
        cgb = self.boot_to_main()
        self.assertTrue(cgb.double_speed)
        self.assertEqual(cgb.io[0x40], br.BG_LCDC)
        px, py, angle = cgb.read16(br.PLAYER_XL), cgb.read16(br.PLAYER_YL), cgb.read8(br.ANGLE)
        tops = list(self.read_block(cgb, br.RAY_TOPS, br.RAYS))
        styles = list(self.read_block(cgb, br.RAY_STYLES, br.RAYS))
        keys = list(self.read_block(cgb, br.RAY_KEYS, br.RAYS))
        alongs = list(self.read_block(cgb, br.RAY_ALONG, br.RAYS))
        expected = br.reference_adaptive_descriptor_view(px, py, angle)
        self.assertEqual((tops, styles, keys, alongs), expected[:4])
        self.assertEqual(cgb.read8(br.ADAPTIVE_CASTS), expected[4])
        self.assertEqual(list(self.read_block(cgb, br.RAY_DEPTH, br.RAYS)), expected[5])
        self.assertEqual(list(self.read_block(cgb, br.RAY_SEGMENT, br.RAYS)), expected[6])
        self.assertTrue(all(0 <= top <= 46 for top in tops))
        self.assertTrue(all(0 <= style < br.STYLE_COUNT for style in styles))

        pixels = br.reference_pixel_descriptor_view(px, py, angle)
        pixel_tops = list(self.read_block(cgb, br.PIXEL_TOPS, br.PHYSICAL_COLUMNS))
        pixel_styles = list(self.read_block(cgb, br.PIXEL_STYLES, br.PHYSICAL_COLUMNS))
        pixel_keys = list(self.read_block(cgb, br.PIXEL_KEYS, br.PHYSICAL_COLUMNS))
        pixel_alongs = list(self.read_block(cgb, br.PIXEL_ALONG, br.PHYSICAL_COLUMNS))
        self.assertEqual((pixel_tops, pixel_styles, pixel_keys, pixel_alongs), pixels[:4])
        self.assertEqual(
            list(self.read_block(cgb, br.PIXEL_SEGMENT, br.PHYSICAL_COLUMNS)),
            pixels[9],
        )
        self.assertEqual(cgb.read8(br.EDGE_RECASTS), pixels[5])
        self.assertEqual(cgb.read8(br.ADAPTIVE_CASTS) + cgb.read8(br.EDGE_RECASTS), pixels[4])
        self.assertEqual(cgb.read8(br.EVENT_COUNT), pixels[6])

        dynamic, view_map, count, overflow = br.reference_compose_view(pixel_tops, pixel_styles)
        self.assertFalse(overflow)
        self.assertEqual(cgb.read8(br.DYN_COUNT), count)
        self.assertEqual(cgb.read8(br.DYN_OVERFLOW), 0)
        self.assertEqual(self.read_block(cgb, br.DYNAMIC_TILES, len(dynamic)), dynamic)
        self.assertEqual(self.read_block(cgb, br.VIEW_MAP, len(view_map)), view_map)
        self.assertEqual(self.read_bg_patterns(cgb, 0, 0, count), dynamic)
        self.assertEqual(self.read_bg_patterns(cgb, 1, 0, count), dynamic)
        self.assertEqual(bytes(cgb.vram[0][0x1800:0x1800 + 384]), view_map)
        self.assertEqual(bytes(cgb.vram[0][0x1C00:0x1C00 + 384]), view_map)
        self.assertEqual(self.read_bg_patterns(cgb, 0, br.ATLAS_TILE_BASE, br.TILE_ATLAS_COUNT), br.TILE_ATLAS_TILES)
        self.assertEqual(self.read_bg_patterns(cgb, 1, br.ATLAS_TILE_BASE, br.TILE_ATLAS_COUNT), br.TILE_ATLAS_TILES)
        mask_count = cgb.read8(br.MASK_TILE_COUNT)
        self.assertEqual(bytes(cgb.vram[cgb.read8(br.OBJ_PAGE)][:mask_count*16]), self.read_block(cgb, br.MASK_TILES, mask_count*16))
        visible_ids = [view_map[y * 32 + x] for y in range(12) for x in range(20)]
        atlas_limit = br.ATLAS_TILE_BASE + br.TILE_ATLAS_COUNT
        self.assertTrue(all(tile < count or br.CEILING_TILE <= tile < atlas_limit for tile in visible_ids))

    def test_exact_tile_atlas_entries_reproduce_their_vram_tiles(self) -> None:
        signature_map = br.tile_atlas_signature_map()
        self.assertEqual(len(signature_map), br.TILE_ATLAS_SIGNATURE_COUNT)
        for signature, tile_id in signature_map.items():
            y0, dark_mask, *tops = signature
            styles = [1 if dark_mask & (0x80 >> pixel) else 0 for pixel in range(8)]
            rebuilt_signature, rebuilt_tile = br.reference_tile_signature_and_bytes(tops, styles, y0)
            self.assertEqual(rebuilt_signature, signature)
            offset = (tile_id - br.ATLAS_TILE_BASE) * 16
            self.assertEqual(br.TILE_ATLAS_TILES[offset:offset + 16], rebuilt_tile)

    def test_level_compiler_owns_map_spawns_profiles_and_surface_segments(self) -> None:
        level = br.ACTIVE_LEVEL
        self.assertEqual((level.width, level.height), (16, 16))
        self.assertEqual(level.grid, self.grid)
        self.assertEqual(level.format, "lupine-level-v2")
        self.assertEqual(len(level.header_bytes()), 18)
        self.assertEqual(len(level.door_bytes()), br.MAX_DOORS * br.DOOR_RECORD_BYTES)
        self.assertEqual(len(level.doors), 4)
        self.assertEqual(level.safe_radius_cells, 5)
        self.assertEqual(sum(bool(door.flags & br.DOOR_FLAG_EXIT) for door in level.doors), 1)
        self.assertTrue(level.doors[-1].flags & br.DOOR_FLAG_LOCK_SENTINEL)
        self.assertEqual(level.vram_profile, br.VRAM_PROFILE_ENTITY)
        self.assertEqual(level.entities[0].kind, "sentinel")
        self.assertEqual(level.pickups[0].source, "sentinel_drop")
        self.assertEqual(len(level.segment_table), 16 * 16 * 4)
        segment_start = br.SEGMENT_TABLE_ROM_BANK * 0x4000
        self.assertEqual(
            self.rom[segment_start:segment_start + len(level.segment_table)],
            level.segment_table,
        )
        # Every non-zero certificate names a solid cell face. Static paint
        # changes do not split a physically continuous plane.
        for y in range(level.height):
            for x in range(level.width):
                base = (y * level.width + x) * 4
                ids = level.segment_table[base:base + 4]
                if any(ids):
                    self.assertNotEqual(level.grid[y * level.width + x], 0)
                if y + 1 < level.height and level.grid[y * 16 + x] == level.grid[(y + 1) * 16 + x] != 0:
                    for side in (0, 1):
                        first, second = ids[side], level.segment_table[base + 16 * 4 + side]
                        if first and second:
                            self.assertEqual(first, second)
        synthetic = bytes((1, 2, 0, 0, 0, 0, 0, 0))
        synthetic_segments = build_segment_table(synthetic, 4, 2)
        self.assertEqual(synthetic_segments[3], synthetic_segments[4 + 3])
        self.assertNotEqual(synthetic_segments[3], 0)

        report = level.readability
        self.assertIsNotNone(report)
        self.assertEqual(report.unreachable_cells, 0)
        self.assertEqual(report.maximum_sightline, 6)
        self.assertEqual(report.maximum_open_rectangle, (4, 3))
        self.assertGreaterEqual(report.minimum_door_separation, 8)
        self.assertGreaterEqual(report.critical_path_turns, 3)
        # Two paint seams on latent jamb faces become visible as doors open.
        self.assertEqual(report.material_seams, 2)
        self.assertEqual(report.material_singleton_runs, 2)

    def test_level_v2_rejects_unsafe_spawns_bad_door_frames_and_missing_exit_lock(self) -> None:
        source = json.loads((ROOT / "levels" / "living_world.json").read_text(encoding="utf-8"))
        mutations = []
        unsafe = json.loads(json.dumps(source))
        unsafe["player_spawn"]["x_q8"] = unsafe["entities"][0]["x_q8"]
        unsafe["player_spawn"]["y_q8"] = unsafe["entities"][0]["y_q8"]
        mutations.append((unsafe, "safe_radius_cells"))
        bad_frame = json.loads(json.dumps(source))
        bad_frame["doors"][0]["orientation"] = "vertical"
        mutations.append((bad_frame, "orientation"))
        no_exit_lock = json.loads(json.dumps(source))
        no_exit_lock["doors"][-1]["kind"] = "standard"
        no_exit_lock["doors"][-1]["unlock"] = "none"
        mutations.append((no_exit_lock, "exit door"))
        with tempfile.TemporaryDirectory() as directory:
            for index, (mutated, message) in enumerate(mutations):
                path = Path(directory) / f"invalid_{index}.json"
                path.write_text(json.dumps(mutated), encoding="utf-8")
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    compile_level(path)

    def test_level_v2_readability_gates_reject_voids_bypasses_and_long_sightlines(self) -> None:
        source = json.loads((ROOT / "levels" / "living_world.json").read_text(encoding="utf-8"))
        cases = []

        sealed_void = json.loads(json.dumps(source))
        row = list(sealed_void["rows"][1]); row[8] = "0"
        sealed_void["rows"][1] = "".join(row)
        cases.append((sealed_void, "unreachable"))

        bypass = json.loads(json.dumps(source))
        for x, y in ((1, 6), (1, 7), (2, 7)):
            row = list(bypass["rows"][y]); row[x] = "0"; bypass["rows"][y] = "".join(row)
        cases.append((bypass, "door"))

        long_view = json.loads(json.dumps(source))
        row = list(long_view["rows"][7]); row[9] = "0"
        long_view["rows"][7] = "".join(row)
        cases.append((long_view, "readability"))

        with tempfile.TemporaryDirectory() as directory:
            for index, (mutated, message) in enumerate(cases):
                path = Path(directory) / f"unreadable_{index}.json"
                path.write_text(json.dumps(mutated), encoding="utf-8")
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    compile_level(path)

    def test_scene_vram_profiles_exchange_atlas_capacity_for_entity_tiles(self) -> None:
        self.assertEqual(len(br.RENDERER_ATLAS_TILES) // 16, 121)
        self.assertEqual(len(br.ENTITY_ATLAS_TILES) // 16, 121)
        self.assertEqual(br.ENTITY_TILE_BASE, 0)
        self.assertLessEqual(br.EXIT_BEACON_TILE + br.EXIT_BEACON_FRAMES, br.ENTITY_TILE_LIMIT)

        cgb = self.boot_to_main()
        cgb.write8(br.VRAM_PROFILE, br.VRAM_PROFILE_RENDERER)
        cgb.call_subroutine("init_vram", max_steps=500_000)
        for bank in range(2):
            self.assertEqual(self.read_bg_patterns(cgb, bank, br.ATLAS_TILE_BASE, 121), br.RENDERER_ATLAS_TILES)

    def test_mbc5_projection_lut_layout_and_exact_boundary_samples(self) -> None:
        lut = br.make_projection_top_lut()
        projection = br.make_tables()["projection_half"]
        self.assertEqual(len(lut), br.PROJECTION_LUT_BYTES)
        start = br.PROJECTION_LUT_BASE_BANK * 0x4000
        self.assertEqual(self.rom[start:start + len(lut)], lut)
        for component in (1, 2, 63, 127):
            for correction in (110, 118, 127):
                for distance in (0, 1, 31, 255, 256, 511):
                    perpendicular = min(511, (distance * correction + component // 2) // component)
                    expected = 48 - projection[perpendicular]
                    index = (
                        (component * br.PROJECTION_LUT_CORRECTION_COUNT
                         + correction - br.PROJECTION_LUT_CORRECTION_MIN)
                        * br.PROJECTION_LUT_DISTANCES
                        + distance
                    )
                    self.assertEqual(lut[index * 2], expected)
                    self.assertEqual(lut[index * 2 + 1], min(255, perpendicular))

        products = br.make_product_lut()
        product_start = br.PRODUCT_LUT_BASE_BANK * 0x4000
        self.assertEqual(self.rom[product_start:product_start + len(products)], products)
        for multiplier in (0, 1, 63, 127):
            for multiplicand in (0, 1, 127, 255):
                index = (multiplier * 256 + multiplicand) * 2
                actual = products[index] | (products[index + 1] << 8)
                self.assertEqual(actual, multiplier * multiplicand)

    def test_rom_signed_error_dda_matches_host_probes(self) -> None:
        cgb = self.boot_to_main()
        probes = [
            (0x0180, 0x0280, 0, 0),
            (0x0180, 0x0280, 0, 39),
            (0x0180, 0x0280, 32, 59),
            (0x0880, 0x0680, 0, 0),
            (0x0880, 0x0680, 0, 39),
            (0x0480, 0x0C80, 192, 39),
        ]
        observed_styles = set()
        for x_q8, y_q8, angle, ray_index in probes:
            with self.subTest(pose=(x_q8, y_q8, angle), ray=ray_index):
                self.set_pose(cgb, x_q8, y_q8, angle)
                cgb.write8(br.CAST_INDEX, ray_index)
                cgb.call_subroutine("cast_indexed")
                expected = br.reference_cast_hit(x_q8, y_q8, angle, ray_index)
                actual = (
                    cgb.read8(br.DDA_MAP_X), cgb.read8(br.DDA_MAP_Y),
                    cgb.read8(br.DDA_AXIS), cgb.read16(br.DDA_DIST_L),
                    cgb.read8(br.DDA_MATERIAL), cgb.read8(br.DDA_CROSSINGS),
                    cgb.read8(br.TOP_RESULT), cgb.read8(br.STYLE_RESULT),
                    cgb.read8(br.FACE_RESULT), cgb.read8(br.ALONG_RESULT),
                )
                wanted = (
                    expected.map_x, expected.map_y, expected.axis,
                    expected.axis_distance_q8, expected.material, expected.crossings,
                    expected.top, expected.style, expected.face_key, expected.along,
                )
                self.assertEqual(actual, wanted)
                observed_styles.add(actual[7])
        self.assertEqual(observed_styles, {0, 1, 2, 3, 4})

    def test_physical_edge_cast_offsets_cross_the_256_byte_table_page(self) -> None:
        cgb = self.boot_to_main()
        probes = [
            (0x0680, 0x0120, 64, 127),
            (0x0680, 0x0120, 64, 128),
            (0x0880, 0x0580, 144, 159),
        ]
        for x_q8, y_q8, angle, pixel_index in probes:
            with self.subTest(pose=(x_q8, y_q8, angle), pixel=pixel_index):
                self.set_pose(cgb, x_q8, y_q8, angle)
                cgb.write8(br.PIXEL_INDEX, pixel_index)
                cgb.call_subroutine("cast_physical_indexed")
                expected = br.reference_cast_physical_hit(x_q8, y_q8, angle, pixel_index)
                self.assertEqual(cgb.read8(br.TOP_RESULT), expected.top)
                self.assertEqual(cgb.read8(br.STYLE_RESULT), expected.style)
                self.assertEqual(cgb.read8(br.FACE_RESULT), expected.face_key)
                self.assertEqual(cgb.read8(br.ALONG_RESULT), expected.along)

    def test_rom_adaptive_and_compositor_match_host_pose_corpus(self) -> None:
        cgb = self.boot_to_main()
        cast_cycles: list[int] = []
        render_cycles: list[int] = []
        poses = [
            (0x0180, 0x0180, 0),
            (0x0680, 0x0120, 64),
            (0x0880, 0x0580, 144),
            (0x0D80, 0x0D80, 224),
            (0x08E0, 0x0180, 16),
            (0x0520, 0x0B80, 192),
        ]
        for x_q8, y_q8, angle in poses:
            with self.subTest(pose=(x_q8, y_q8, angle)):
                self.set_pose(cgb, x_q8, y_q8, angle)
                before = cgb.cycles
                cgb.call_subroutine("cast_all")
                cast_cycles.append(cgb.cycles - before)
                tops = list(self.read_block(cgb, br.RAY_TOPS, br.RAYS))
                styles = list(self.read_block(cgb, br.RAY_STYLES, br.RAYS))
                keys = list(self.read_block(cgb, br.RAY_KEYS, br.RAYS))
                alongs = list(self.read_block(cgb, br.RAY_ALONG, br.RAYS))
                expected = br.reference_adaptive_descriptor_view(x_q8, y_q8, angle)
                self.assertEqual((tops, styles, keys, alongs), expected[:4])
                self.assertEqual(cgb.read8(br.ADAPTIVE_CASTS), expected[4])
                pixels = br.reference_pixel_descriptor_view(x_q8, y_q8, angle)
                pixel_tops = list(self.read_block(cgb, br.PIXEL_TOPS, br.PHYSICAL_COLUMNS))
                pixel_styles = list(self.read_block(cgb, br.PIXEL_STYLES, br.PHYSICAL_COLUMNS))
                pixel_keys = list(self.read_block(cgb, br.PIXEL_KEYS, br.PHYSICAL_COLUMNS))
                pixel_alongs = list(self.read_block(cgb, br.PIXEL_ALONG, br.PHYSICAL_COLUMNS))
                self.assertEqual((pixel_tops, pixel_styles, pixel_keys, pixel_alongs), pixels[:4])
                self.assertEqual(
                    list(self.read_block(cgb, br.PIXEL_SEGMENT, br.PHYSICAL_COLUMNS)),
                    pixels[9],
                )
                self.assertEqual(cgb.read8(br.EDGE_RECASTS), pixels[5])
                self.assertEqual(cgb.read8(br.EVENT_COUNT), pixels[6])
                before = cgb.cycles
                cgb.call_subroutine("render_view")
                render_cycles.append(cgb.cycles - before)
                dynamic, view_map, count, overflow = br.reference_compose_view(pixel_tops, pixel_styles)
                self.assertFalse(overflow)
                self.assertEqual(cgb.read8(br.DYN_COUNT), count)
                self.assertEqual(cgb.read8(br.DYN_OVERFLOW), 0)
                self.assertEqual(self.read_block(cgb, br.DYNAMIC_TILES, len(dynamic)), dynamic)
                self.assertEqual(self.read_block(cgb, br.VIEW_MAP, 384), view_map)
        # The entity-heavy profile deliberately trades roughly 2.3% wall
        # throughput for 41 OBJ tile IDs. Depth and segment certificates are
        # also produced in this path, so preserve a feature-aware ceiling.
        hot_path_mean = statistics.fmean(
            cast + render for cast, render in zip(cast_cycles, render_cycles)
        )
        self.assertLess(hot_path_mean, 980_000)

    def test_exhaustive_host_guardrails_for_adaptive_spans_and_capacity(self) -> None:
        max_top_delta = max_dynamic = max_casts = max_edge_casts = 0
        cast_counts: list[int] = []
        dynamic_counts: list[int] = []
        samples = 0
        for y in range(1, 15):
            for x in range(1, 15):
                if self.grid[y * 16 + x] != 0:
                    continue
                for angle in range(0, 256, 8):
                    px, py = (x << 8) | 0x80, (y << 8) | 0x80
                    full = br.reference_full_descriptor_view(px, py, angle)
                    adaptive = br.reference_adaptive_descriptor_view(px, py, angle)
                    self.assertEqual(adaptive[1], full[1])
                    self.assertEqual(adaptive[2], full[2])
                    delta = max(abs(a - b) for a, b in zip(adaptive[0], full[0]))
                    max_top_delta = max(max_top_delta, delta)
                    pixels = br.reference_pixel_descriptor_view(px, py, angle)
                    _, _, dynamic_count, overflow = br.reference_compose_view(pixels[0], pixels[1])
                    self.assertFalse(overflow)
                    max_dynamic = max(max_dynamic, dynamic_count)
                    max_casts = max(max_casts, pixels[4])
                    max_edge_casts = max(max_edge_casts, pixels[5])
                    dynamic_counts.append(dynamic_count)
                    cast_counts.append(pixels[4])
                    samples += 1
        self.assertGreater(samples, 2_000)
        self.assertLessEqual(max_top_delta, 2)
        self.assertLessEqual(max_dynamic, br.DYNAMIC_TILE_CAPACITY)
        self.assertLessEqual(max_casts, 70)
        self.assertLessEqual(max_edge_casts, 16)
        self.assertLess(statistics.fmean(cast_counts), 47.0)
        self.assertLess(statistics.fmean(dynamic_counts), 35.0)

    def test_tail_failure_certificate_preserves_worst_case_evidence(self) -> None:
        records, summary = tail_lab.inspect_pose(
            2688, 2944, 12, grid=self.renderer_level.grid,
        )
        historical = json.loads((ROOT / "research/results/tail_failures_v4.json").read_text())
        self.assertEqual(historical["tail"]["maximum_top_error_px"], 41.0)
        self.assertFalse(records)
        self.assertLess(summary["max_top_error_px"], 1.0)
        self.assertEqual(summary["wrong_segments"], 0)

    def test_full_120_block_commit_stages_before_atomic_publication(self) -> None:
        cgb = self.boot_to_main()
        cgb.write8(br.MASK_TILE_COUNT, 0)  # exercise the wall-only packet
        for i in range(br.DYNAMIC_TILE_CAPACITY * 16):
            cgb.write8(br.DYNAMIC_TILES + i, (i * 37 + 11) & 0xFF)
        for i in range(384):
            cgb.write8(br.VIEW_MAP + i, i & 0x5F)
        cgb.write8(br.DYN_COUNT, br.DYNAMIC_TILE_CAPACITY)
        cgb.call_subroutine("upload_hidden_page", max_steps=500_000)
        self.assertEqual(cgb.page_swaps, 1)
        self.assertEqual(cgb.gdma_vblank_violations, 0)
        commit = cgb.commit_events[-1]
        self.assertEqual(commit["blocks"], 144)
        self.assertEqual(commit["event_count"], 3)
        self.assertTrue(commit["vblank_safe"])
        self.assertTrue(commit["staged"])
        events = commit["events"]
        self.assertEqual((events[0]["destination"], events[0]["blocks"], events[0]["bank"]), (br.DYNAMIC_TILE_VRAM, 96, 1))
        self.assertEqual((events[1]["destination"], events[1]["blocks"], events[1]["bank"]), (0x9C00, 24, 1))
        self.assertEqual((events[2]["destination"], events[2]["blocks"], events[2]["bank"]), (0x9C00, 24, 0))
        self.assertEqual(self.read_bg_patterns(cgb, 1, 0, 96), self.read_block(cgb, br.DYNAMIC_TILES, 1536))
        self.assertEqual(bytes(cgb.vram[0][0x1C00:0x1C00 + 384]), self.read_block(cgb, br.VIEW_MAP, 384))

    def test_oam_dma_is_atomic_and_defers_when_gdma_consumes_the_vblank(self) -> None:
        cgb = self.boot_to_main()
        marker = bytes((88, 96, br.PICKUP_TILE, 0x09))
        for offset, value in enumerate(marker):
            cgb.write8(br.OAM_SHADOW + br.ENTITY_OAM_FIRST * 4 + offset, value)
        before = bytes(cgb.oam)
        cgb.write8(br.OAM_DIRTY, 1)
        cgb.write8(br.DYN_COUNT, br.DYNAMIC_TILE_CAPACITY)
        cgb.call_subroutine("publish_oam_if_budget")
        self.assertEqual(bytes(cgb.oam), before)
        self.assertEqual(cgb.read8(br.OAM_DIRTY), 1)
        self.assertEqual(cgb.read8(br.OAM_DEFERRED), 1)

        cgb.write8(br.DYN_COUNT, 0)
        cgb.call_subroutine("publish_oam_if_budget")
        self.assertEqual(cgb.read8(br.OAM_DIRTY), 0)
        self.assertEqual(
            bytes(cgb.oam[br.ENTITY_OAM_FIRST * 4:br.ENTITY_OAM_FIRST * 4 + 4]),
            marker,
        )

    def test_repeated_visual_commits_are_coherent_and_alternate_pages(self) -> None:
        cgb = self.boot_to_main()

        def script(iteration: int, _swaps: int) -> int:
            if 1 <= iteration <= 3:
                return 0x04
            if 4 <= iteration <= 6:
                return 0x01
            return 0

        cgb.button_provider = script
        cgb.run(until_presentations=6, max_steps=5_000_000)
        self.assertEqual(len(cgb.commit_events), 6)
        self.assertEqual(cgb.gdma_vblank_violations, 0)
        for index, commit in enumerate(cgb.commit_events, start=1):
            self.assertTrue(commit["vblank_safe"])
            self.assertIn(commit["event_count"], (3, 4))
            self.assertLessEqual(commit["blocks"], 176)
            expected_map = 1 if index & 1 else 0
            self.assertEqual(commit["displayed_map"], expected_map)
            expected_destination = 0x9C00 if expected_map else 0x9800
            self.assertEqual(commit["events"][-1]["destination"], expected_destination)
        displayed = cgb.read8(br.CURRENT_PAGE)
        map_offset = 0x1C00 if displayed else 0x1800
        dynamic_count = cgb.read8(br.DYN_COUNT)
        self.assertEqual(self.read_bg_patterns(cgb, displayed, 0, dynamic_count), self.read_block(cgb, br.DYNAMIC_TILES, dynamic_count * 16))
        self.assertEqual(bytes(cgb.vram[0][map_offset:map_offset + 384]), self.read_block(cgb, br.VIEW_MAP, 384))

    def test_controls_move_turn_and_page_flip(self) -> None:
        cgb = self.boot_to_main()
        start_x = cgb.read16(br.PLAYER_XL)
        start_y = cgb.read16(br.PLAYER_YL)

        def script(iteration: int, _swaps: int) -> int:
            if 1 <= iteration <= 4:
                return 0x04  # Up
            if 5 <= iteration <= 7:
                return 0x01  # Right
            return 0

        cgb.button_provider = script
        cgb.run(until_presentations=7, max_steps=6_000_000)
        self.assertEqual(cgb.read16(br.PLAYER_XL), start_x)
        self.assertLess(cgb.read16(br.PLAYER_YL), start_y)
        self.assertEqual((start_y - cgb.read16(br.PLAYER_YL)) % 4, 0)
        self.assertGreater(cgb.read8(br.ANGLE), 192)
        self.assertEqual(cgb.page_swaps, 7)
        self.assertEqual(cgb.io[0x40] & 0x08, 0x08)

    def test_vblank_sampler_latches_a_press_during_a_long_render(self) -> None:
        cgb = self.boot_to_main()
        self.assertEqual(cgb.ie & 1, 1)
        self.assertTrue(cgb.ime)
        start_frame = cgb.frame_count
        start_samples = cgb.read8(br.INPUT_SAMPLE_COUNT)
        pulse_frame = start_frame + 2
        cgb.button_provider = lambda _iteration, _swaps: 0x10 if cgb.frame_count == pulse_frame else 0

        # The pulse occurs after input consumption and disappears before the
        # visual update finishes. It must survive in the edge latch.
        cgb.run(until_presentations=1, max_steps=3_000_000)
        self.assertEqual(cgb.read8(br.FLASH), 0)
        self.assertGreater(cgb.read16(br.SIM_STEPS), 0)
        self.assertGreater(cgb.wramx[2][br.FLASH - 0xD000], 0)
        self.assertGreaterEqual((cgb.read8(br.INPUT_SAMPLE_COUNT) - start_samples) & 0xFF, 2)
        self.assertTrue(any(event["bit"] == 0 for event in cgb.interrupt_events))

        # The next stable simulation step consumes the preserved edge even
        # though the button is no longer held.
        cgb.run(until_presentations=2, max_steps=3_000_000)
        self.assertGreater(cgb.read8(br.FLASH), 0)
        self.assertEqual(cgb.read8(0xFF14), 0xC7)

    def test_collision_blocks_world_boundary(self) -> None:
        cgb = self.boot_to_main()
        self.set_pose(cgb, 0x0180, 0x0D80, 128)
        cgb.button_provider = lambda iteration, _swaps: 0x04 if iteration <= 10 else 0
        cgb.run(until_presentations=10, max_steps=8_000_000)
        x = cgb.read16(br.PLAYER_XL)
        self.assertGreaterEqual(x, 0x0100 + br.PLAYER_RADIUS_Q8)
        self.assertEqual(x >> 8, 1)

    def test_animated_door_opens_a_subcell_aperture_on_fixed_ticks(self) -> None:
        cgb = self.boot_to_main()
        self.set_pose(cgb, 0x0480, 0x0C40, 192)
        door_addr = br.MAP + 11 * 16 + 4
        door_record = br.DOOR_TABLE
        self.assertEqual(cgb.read8(door_addr), 3)
        cgb.call_subroutine("cast_all")
        closed_top = cgb.read8(br.RAY_TOPS + 40)
        cgb.write8(door_record + br.DOOR_STATE_OFFSET, 1)
        cgb.write8(door_record + br.DOOR_FRACTION_OFFSET, 192)
        cgb.call_subroutine("cast_all")
        self.assertGreater(cgb.read8(br.RAY_TOPS + 40), closed_top)
        cgb.write8(door_record + br.DOOR_STATE_OFFSET, 0)
        cgb.write8(door_record + br.DOOR_FRACTION_OFFSET, 0)
        cgb.call_subroutine("open_door")
        cgb.call_subroutine("update_animated_doors")
        self.assertEqual(cgb.read8(door_addr), 3)
        self.assertEqual(cgb.read8(door_record + br.DOOR_STATE_OFFSET), 1)
        self.assertEqual(cgb.read8(door_record + br.DOOR_FRACTION_OFFSET), 8)
        self.assertEqual(cgb.read8(0xFF14), 0xC4)
        for _ in range(31): cgb.call_subroutine("update_animated_doors")
        self.assertEqual(cgb.read8(door_addr), 0)
        self.assertEqual(cgb.read8(door_record + br.DOOR_STATE_OFFSET), 2)
        for index in range(1, br.MAX_DOORS):
            record = br.DOOR_TABLE + index * br.DOOR_RECORD_BYTES
            self.assertEqual(cgb.read8(record + br.DOOR_STATE_OFFSET), 0)

        # Empty-world mode remains the exact visual oracle and intentionally
        # retains the original instant interaction semantics.
        legacy = self.boot_to_main()
        legacy.write8(br.WORLD_MODE, br.WORLD_MODE_EMPTY)
        self.set_pose(legacy, 0x0480, 0x0C40, 192)
        legacy.call_subroutine("open_door")
        self.assertEqual(legacy.read8(door_addr), 0)

        # The exit door is a separate record and rejects interaction with a
        # distinct lock sound until the Sentinel-death condition is active.
        exit_cgb = self.boot_to_main()
        exit_record = br.DOOR_TABLE + 3 * br.DOOR_RECORD_BYTES
        self.set_pose(exit_cgb, 0x0980, 0x0A80, 64)
        exit_cgb.call_subroutine("open_door")
        self.assertEqual(exit_cgb.read8(exit_record + br.DOOR_STATE_OFFSET), 0)
        self.assertEqual(exit_cgb.read8(0xFF14), 0xC2)
        exit_cgb.write8(br.EXIT_ACTIVE, 1)
        exit_cgb.call_subroutine("open_door")
        self.assertEqual(exit_cgb.read8(exit_record + br.DOOR_STATE_OFFSET), 1)
        self.assertEqual(exit_cgb.read8(0xFF14), 0xC4)

        # Every authored threshold is reachable through the same coordinate
        # lookup, but mutates only its own record.
        interactions = (
            (0, (0x0480, 0x0C40, 192), False),  # start airlock, from south
            (1, (0x0380, 0x0740, 192), False),  # courtyard access, from south
            (2, (0x06C0, 0x0780, 0), False),    # zig-zag entry, from west
            (3, (0x0980, 0x0A80, 64), True),    # exit lock, from north
        )
        for target_index, pose, unlock_exit in interactions:
            with self.subTest(door=br.ACTIVE_LEVEL.doors[target_index].name):
                probe = self.boot_to_main()
                self.set_pose(probe, *pose)
                if unlock_exit:
                    probe.write8(br.EXIT_ACTIVE, 1)
                probe.call_subroutine("open_door")
                for index in range(br.MAX_DOORS):
                    record = br.DOOR_TABLE + index * br.DOOR_RECORD_BYTES
                    expected = 1 if index == target_index else 0
                    self.assertEqual(
                        probe.read8(record + br.DOOR_STATE_OFFSET), expected,
                    )

    def test_sentinel_projection_combat_drop_pickup_and_exit_vertical_slice(self) -> None:
        cgb = self.boot_to_main()
        self.set_pose(cgb, 0x0880, 0x0880, 0)
        cgb.call_subroutine("cast_all")
        cgb.call_subroutine("render_entities")
        self.assertEqual(cgb.read8(br.SENTINEL_VISIBLE), 1)
        self.assertEqual(cgb.read8(br.SENTINEL_SCREEN_X), 80)
        used = cgb.read8(br.SENTINEL_OAM_USED)
        actors = sum((cgb.read8(br.OAM_SHADOW + (br.ENTITY_OAM_FIRST+i)*4+3) & 7) == 1
                     for i in range(used))
        self.assertIn(actors, (2, 4, 8))
        self.assertLessEqual(used - actors, 4)
        self.assertLessEqual(br.ENTITY_OAM_FIRST + used, 40)

        # The hitscan consumes the same projection/occlusion certificate that
        # the player sees; three shots complete the authored combat loop.
        for expected_health in (2, 1, 0):
            cgb.call_subroutine("player_fire_hitscan")
            self.assertEqual(cgb.read8(br.SENTINEL_HEALTH), expected_health)
            if expected_health:
                cgb.write8(br.SENTINEL_VISIBLE, 1)
        self.assertEqual(cgb.read8(br.SENTINEL_STATE), br.SENTINEL_DEAD)
        self.assertEqual(cgb.read8(br.PICKUP_ACTIVE), 1)
        self.assertEqual(cgb.read8(br.EXIT_ACTIVE), 1)

        # The active exit has a world-space billboard, not an unexplained
        # invisible completion cell.
        self.set_pose(cgb, 0x0A80, 0x0C80, 64)
        cgb.call_subroutine("cast_all")
        cgb.call_subroutine("render_entities")
        entity_tiles = [
            cgb.read8(br.OAM_SHADOW + index * 4 + 2)
            for index in range(br.ENTITY_OAM_FIRST, 40)
        ]
        self.assertGreater(cgb.read8(br.MASK_TILE_COUNT), 0)
        self.assertTrue(all(tile % 2 == 0 for tile in entity_tiles))

        cgb.write16(br.PLAYER_XL, cgb.read16(br.SENTINEL_XL))
        cgb.write16(br.PLAYER_YL, cgb.read16(br.SENTINEL_YL))
        cgb.call_subroutine("collect_pickup_and_exit")
        self.assertEqual(cgb.read8(br.PICKUP_ACTIVE), 0)
        self.assertEqual(cgb.read8(br.PICKUP_COLLECTED), 1)
        cgb.write8(br.PLAYER_XH, cgb.read8(br.EXIT_CELL_X))
        cgb.write8(br.PLAYER_YH, cgb.read8(br.EXIT_CELL_Y))
        cgb.call_subroutine("collect_pickup_and_exit")
        self.assertEqual(cgb.read8(br.LEVEL_COMPLETE), 1)

    def test_sentinel_exact_los_chase_and_attack_run_on_simulation_ticks(self) -> None:
        cgb = self.boot_to_main()
        cgb.write8(br.SENTINEL_STATE, br.SENTINEL_PATROL)
        self.set_pose(cgb, 0x0880, 0x0880, 0)
        before_x = cgb.read16(br.SENTINEL_XL)
        cgb.write8(br.INPUT_SAMPLE_COUNT, br.AI_TICK_INTERVAL)
        cgb.call_subroutine("update_world")
        self.assertEqual(cgb.read8(br.LOS_RESULT), 1)
        self.assertEqual(cgb.read8(br.SENTINEL_STATE), br.SENTINEL_CHASE)
        self.assertLess(cgb.read16(br.SENTINEL_XL), before_x)

        self.set_pose(cgb, 0x0980, 0x0880, 0)
        health = cgb.read8(br.PLAYER_HEALTH)
        cgb.write8(br.INPUT_SAMPLE_COUNT, br.AI_TICK_INTERVAL * 2)
        cgb.write8(br.SENTINEL_COOLDOWN, 0)
        cgb.call_subroutine("update_world")
        self.assertEqual(cgb.read8(br.SENTINEL_STATE), br.SENTINEL_ATTACK)
        self.assertLess(cgb.read8(br.PLAYER_HEALTH), health)

        cgb.write16(br.SENTINEL_XL, 0x0104)
        cgb.write16(br.SENTINEL_YL, 0x0180)
        cgb.write8(br.LOS_DX, 3)
        cgb.write8(br.LOS_DY, 0)
        cgb.write8(br.LOS_SX, 0xFF)
        cgb.call_subroutine("sentinel_chase_step")
        self.assertEqual(cgb.read16(br.SENTINEL_XL), 0x0104)

    def test_entity_wall_depth_clipping_and_scanline_budget(self) -> None:
        cgb = self.boot_to_main()
        self.set_pose(cgb, 0x0980, 0x0880, 0)
        cgb.call_subroutine("cast_all")
        cgb.call_subroutine("render_entities")
        self.assertLess(cgb.read8(br.SENTINEL_DEPTH), cgb.read8(br.RAY_DEPTH + 40))
        cgb.write8(br.DYN_COUNT, 0)
        cgb.call_subroutine("publish_oam_if_budget")
        visible_scanlines = [0] * 144
        visible_total = 0
        for index in range(40):
            y = cgb.read8(0xFE00 + index * 4) - 16
            x = cgb.read8(0xFE00 + index * 4 + 1) - 8
            if x <= -8 or x >= 160 or y <= -8 or y >= 144:
                continue
            visible_total += 1
            for scanline in range(max(0, y), min(144, y + 8)):
                visible_scanlines[scanline] += 1
        self.assertLessEqual(visible_total, 40)
        self.assertLessEqual(max(visible_scanlines), 10)

        # Put the actor past the solid east boundary. Projection remains in
        # front of the camera but the wall-depth samples reject every strip.
        cgb.write16(br.SENTINEL_XL, 0x1080)
        cgb.call_subroutine("project_sentinel")
        self.assertEqual(cgb.read8(br.SENTINEL_VISIBLE), 0)

    def test_fire_has_audio_and_visible_muzzle_feedback(self) -> None:
        cgb = self.boot_to_main()
        cgb.button_provider = lambda iteration, _swaps: 0x10 if iteration == 1 else 0
        cgb.run(until_presentations=2, max_steps=3_000_000)
        self.assertEqual(cgb.read8(0xFF14), 0xC7)
        self.assertGreater(cgb.read8(br.FLASH), 0)
        self.assertEqual(cgb.oam[9 * 4], 72)

    def test_optional_vblank_micro_reprojection_is_clamped_and_hud_safe(self) -> None:
        probe = r'''
import json, sys
from pathlib import Path
root = Path.cwd()
sys.path.insert(0, str(root / "tools"))
import build_rom as br
from sm83emu import CGB
rom, assembler, manifest = br.make_rom()
cgb = CGB(rom, assembler.labels)
cgb.run(until_pc=assembler.labels["main_loop"], max_steps=2_000_000)
cgb.button_provider = lambda _iteration, _swaps: 0x01
cgb.run(until_presentations=2, max_steps=5_000_000)
signed = [event["value"] - 256 if event["value"] & 0x80 else event["value"] for event in cgb.scx_events]
guards = all(
    cgb.read8(br.VIEW_MAP + row * 32 + 31) == cgb.read8(br.VIEW_MAP + row * 32)
    and cgb.read8(br.VIEW_MAP + row * 32 + 20) == cgb.read8(br.VIEW_MAP + row * 32 + 19)
    for row in range(12)
)
print(json.dumps({
    "compiled": manifest["micro_reprojection_compiled"],
    "minimum": min(signed), "maximum": max(signed),
    "nonzero": any(signed), "final_scx": cgb.io[0x43],
    "stat_interrupts": sum(event["bit"] == 1 for event in cgb.interrupt_events),
    "hud_resets": sum(event["ly"] >= 96 and event["value"] == 0 for event in cgb.scx_events),
    "guards": guards,
}))
'''
        environment = dict(os.environ)
        environment["LUPINE3D_REPROJECTION"] = "1"
        completed = subprocess.run(
            [sys.executable, "-c", probe], cwd=ROOT, env=environment,
            check=True, capture_output=True, text=True, timeout=120,
        )
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertTrue(result["compiled"])
        self.assertTrue(result["nonzero"])
        self.assertGreater(result["stat_interrupts"], 0)
        self.assertGreater(result["hud_resets"], 0)
        self.assertGreaterEqual(result["minimum"], -br.REPROJECT_LIMIT)
        self.assertLessEqual(result["maximum"], br.REPROJECT_LIMIT)
        self.assertEqual(result["final_scx"], 0)
        self.assertTrue(result["guards"])

    def test_deterministic_cycle_budget_and_update_floor(self) -> None:
        cgb = self.boot_to_main()
        cgb.button_provider = lambda _iteration, _swaps: 0
        start_cycles = cgb.cycles
        start_frames = cgb.frame_count
        cgb.step()  # enter the main-loop body once
        cgb.run(until_pc=self.symbols["main_loop"], max_steps=2_000_000)
        update_cycles = cgb.cycles - start_cycles
        update_frames = cgb.frame_count - start_frames
        updates_per_second = DOUBLE_SPEED_HZ / update_cycles
        self.assertEqual(cgb.page_swaps, 1)
        # This now includes certified traversal, finite door intersections,
        # fixed-tick simulation and an attribute/OAM packet. Keep an explicit
        # ceiling, rather than pretending this changed workload is free.
        self.assertLess(update_cycles, 1_400_000)
        self.assertLessEqual(update_frames, 10)
        self.assertGreater(updates_per_second, 6.0)
        self.assertLessEqual(cgb.read8(br.ADAPTIVE_CASTS), 50)
        self.assertLessEqual(cgb.read8(br.EDGE_RECASTS), 16)
        self.assertLessEqual(cgb.read8(br.DYN_COUNT), br.DYNAMIC_TILE_CAPACITY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
