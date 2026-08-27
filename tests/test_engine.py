#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import statistics
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_rom as br  # noqa: E402
import build_rom_v1 as v1  # noqa: E402
from sm83emu import CGB  # noqa: E402

BASELINE_SHA256 = "0b5794c93b43b38a0dd2a76cf4e289f0317dd9b10314632ff366402ecd37fa00"
DOUBLE_SPEED_HZ = 8_388_608


class Lupine3DTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rom, cls.assembler, cls.manifest = br.make_rom()
        cls.symbols = cls.assembler.labels
        cls.grid = br.make_map()

    def boot_to_main(self) -> CGB:
        cgb = CGB(self.rom, self.symbols)
        cgb.run(until_pc=self.symbols["main_loop"], max_steps=2_000_000)
        return cgb

    @staticmethod
    def set_pose(cgb: CGB, x_q8: int, y_q8: int, angle: int) -> None:
        cgb.write16(br.PLAYER_XL, x_q8)
        cgb.write16(br.PLAYER_YL, y_q8)
        cgb.write8(br.ANGLE, angle)

    @staticmethod
    def read_block(cgb: CGB, address: int, count: int) -> bytes:
        return bytes(cgb.read8(address + i) for i in range(count))

    def test_rom_header_checksums_and_manifest(self) -> None:
        rom = self.rom
        self.assertEqual(len(rom), br.ROM_BYTES)
        self.assertEqual(rom[0x0104:0x0134], br.NINTENDO_LOGO)
        self.assertEqual(rom[0x0134:0x013C], b"LUPINE3D")
        self.assertEqual(rom[0x0143], 0xC0)
        self.assertEqual(rom[0x0147], 0x19)
        self.assertEqual(rom[0x0148], 0x07)
        self.assertEqual(rom[0x0149], 0x00)
        self.assertEqual(rom[0x014C], 0x04)
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
        self.assertEqual(self.manifest["maximum_commit_blocks"], 120)
        self.assertEqual(self.manifest["rom_banks"], 256)
        self.assertEqual(self.manifest["cartridge_type"], "MBC5")
        self.assertEqual(self.manifest["projection_lut_bytes"], br.PROJECTION_LUT_BYTES)
        self.assertTrue(self.manifest["projection_lut_exact"])
        self.assertEqual(self.manifest["product_lut_bytes"], br.PRODUCT_LUT_BYTES)
        self.assertTrue(self.manifest["product_lut_exact"])
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

    def test_boot_matches_descriptor_and_microstrip_host_models(self) -> None:
        cgb = self.boot_to_main()
        self.assertTrue(cgb.double_speed)
        self.assertEqual(cgb.io[0x40], 0x93)
        px, py, angle = cgb.read16(br.PLAYER_XL), cgb.read16(br.PLAYER_YL), cgb.read8(br.ANGLE)
        tops = list(self.read_block(cgb, br.RAY_TOPS, br.RAYS))
        styles = list(self.read_block(cgb, br.RAY_STYLES, br.RAYS))
        keys = list(self.read_block(cgb, br.RAY_KEYS, br.RAYS))
        alongs = list(self.read_block(cgb, br.RAY_ALONG, br.RAYS))
        expected = br.reference_adaptive_descriptor_view(px, py, angle)
        self.assertEqual((tops, styles, keys, alongs), expected[:4])
        self.assertEqual(cgb.read8(br.ADAPTIVE_CASTS), expected[4])
        self.assertTrue(all(0 <= top <= 46 for top in tops))
        self.assertTrue(all(0 <= style < br.STYLE_COUNT for style in styles))

        pixels = br.reference_pixel_descriptor_view(px, py, angle)
        pixel_tops = list(self.read_block(cgb, br.PIXEL_TOPS, br.PHYSICAL_COLUMNS))
        pixel_styles = list(self.read_block(cgb, br.PIXEL_STYLES, br.PHYSICAL_COLUMNS))
        pixel_keys = list(self.read_block(cgb, br.PIXEL_KEYS, br.PHYSICAL_COLUMNS))
        pixel_alongs = list(self.read_block(cgb, br.PIXEL_ALONG, br.PHYSICAL_COLUMNS))
        self.assertEqual((pixel_tops, pixel_styles, pixel_keys, pixel_alongs), pixels[:4])
        self.assertEqual(cgb.read8(br.EDGE_RECASTS), pixels[5])
        self.assertEqual(cgb.read8(br.ADAPTIVE_CASTS) + cgb.read8(br.EDGE_RECASTS), pixels[4])
        self.assertEqual(cgb.read8(br.EVENT_COUNT), pixels[6])

        dynamic, view_map, count, overflow = br.reference_compose_view(pixel_tops, pixel_styles)
        self.assertFalse(overflow)
        self.assertEqual(cgb.read8(br.DYN_COUNT), count)
        self.assertEqual(cgb.read8(br.DYN_OVERFLOW), 0)
        self.assertEqual(self.read_block(cgb, br.DYNAMIC_TILES, len(dynamic)), dynamic)
        self.assertEqual(self.read_block(cgb, br.VIEW_MAP, len(view_map)), view_map)
        self.assertEqual(bytes(cgb.vram[0][:len(dynamic)]), dynamic)
        self.assertEqual(bytes(cgb.vram[1][:len(dynamic)]), dynamic)
        self.assertEqual(bytes(cgb.vram[0][0x1800:0x1800 + 384]), view_map)
        self.assertEqual(bytes(cgb.vram[0][0x1C00:0x1C00 + 384]), view_map)
        atlas_start = br.ATLAS_TILE_BASE * 16
        atlas_end = atlas_start + len(br.TILE_ATLAS_TILES)
        self.assertEqual(bytes(cgb.vram[0][atlas_start:atlas_end]), br.TILE_ATLAS_TILES)
        self.assertEqual(bytes(cgb.vram[1][atlas_start:atlas_end]), br.TILE_ATLAS_TILES)
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

    def test_mbc5_projection_lut_layout_and_exact_boundary_samples(self) -> None:
        lut = br.make_projection_top_lut()
        projection = br.make_tables()["projection_half"]
        self.assertEqual(len(lut), br.PROJECTION_LUT_BYTES)
        start = br.PROJECTION_LUT_BASE_BANK * 0x4000
        self.assertEqual(self.rom[start:start + len(lut)], lut)
        for component in (1, 2, 63, 127, 255):
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
                    self.assertEqual(lut[index], expected)

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
            (0x0180, 0x0180, 0, 0),
            (0x0180, 0x0180, 0, 39),
            (0x0680, 0x0180, 72, 39),
            (0x0680, 0x0180, 64, 59),
            (0x0880, 0x0380, 16, 79),
            (0x0880, 0x0380, 0, 79),
            (0x08A0, 0x05C0, 193, 12),
            (0x0D20, 0x0D80, 64, 12),
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
        # v0.3.0's byte-exact reference corpus averaged 1,008,489 cycles for
        # these two hot routines.  Keep a strict regression ceiling while
        # leaving a small allowance for assembler-level maintenance changes.
        hot_path_mean = statistics.fmean(
            cast + render for cast, render in zip(cast_cycles, render_cycles)
        )
        self.assertLess(hot_path_mean, 950_000)

    def test_exhaustive_host_guardrails_for_adaptive_spans_and_capacity(self) -> None:
        max_top_delta = max_dynamic = max_casts = max_edge_casts = 0
        cast_counts: list[int] = []
        dynamic_counts: list[int] = []
        samples = 0
        for y in range(1, 15):
            for x in range(1, 15):
                if self.grid[y * 16 + x] != 0:
                    continue
                for angle in range(0, 256, 16):
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

    def test_full_120_block_commit_fits_one_vblank(self) -> None:
        cgb = self.boot_to_main()
        for i in range(br.DYNAMIC_TILE_CAPACITY * 16):
            cgb.write8(br.DYNAMIC_TILES + i, (i * 37 + 11) & 0xFF)
        for i in range(384):
            cgb.write8(br.VIEW_MAP + i, i & 0x5F)
        cgb.write8(br.DYN_COUNT, br.DYNAMIC_TILE_CAPACITY)
        cgb.call_subroutine("upload_hidden_page", max_steps=500_000)
        self.assertEqual(cgb.page_swaps, 1)
        self.assertEqual(cgb.gdma_vblank_violations, 0)
        commit = cgb.commit_events[-1]
        self.assertEqual(commit["blocks"], 120)
        self.assertEqual(commit["event_count"], 2)
        self.assertTrue(commit["vblank_safe"])
        events = commit["events"]
        self.assertEqual((events[0]["destination"], events[0]["blocks"], events[0]["bank"]), (0x8000, 96, 1))
        self.assertEqual((events[1]["destination"], events[1]["blocks"], events[1]["bank"]), (0x9C00, 24, 0))
        self.assertEqual(bytes(cgb.vram[1][:1536]), self.read_block(cgb, br.DYNAMIC_TILES, 1536))
        self.assertEqual(bytes(cgb.vram[0][0x1C00:0x1C00 + 384]), self.read_block(cgb, br.VIEW_MAP, 384))

    def test_repeated_visual_commits_are_coherent_and_alternate_pages(self) -> None:
        cgb = self.boot_to_main()

        def script(iteration: int, _swaps: int) -> int:
            if 1 <= iteration <= 3:
                return 0x04
            if 4 <= iteration <= 6:
                return 0x01
            return 0

        cgb.button_provider = script
        cgb.run(until_swaps=6, max_steps=5_000_000)
        self.assertEqual(len(cgb.commit_events), 6)
        self.assertEqual(cgb.gdma_vblank_violations, 0)
        for index, commit in enumerate(cgb.commit_events, start=1):
            self.assertTrue(commit["vblank_safe"])
            self.assertEqual(commit["event_count"], 2)
            self.assertLessEqual(commit["blocks"], 120)
            expected_map = 1 if index & 1 else 0
            self.assertEqual(commit["displayed_map"], expected_map)
            expected_destination = 0x9C00 if expected_map else 0x9800
            self.assertEqual(commit["events"][1]["destination"], expected_destination)
        displayed = cgb.read8(br.CURRENT_PAGE)
        map_offset = 0x1C00 if displayed else 0x1800
        dynamic_count = cgb.read8(br.DYN_COUNT)
        self.assertEqual(bytes(cgb.vram[displayed][:dynamic_count * 16]), self.read_block(cgb, br.DYNAMIC_TILES, dynamic_count * 16))
        self.assertEqual(bytes(cgb.vram[0][map_offset:map_offset + 384]), self.read_block(cgb, br.VIEW_MAP, 384))

    def test_controls_move_turn_and_page_flip(self) -> None:
        cgb = self.boot_to_main()

        def script(iteration: int, _swaps: int) -> int:
            if 1 <= iteration <= 4:
                return 0x04  # Up
            if 5 <= iteration <= 7:
                return 0x01  # Right
            return 0

        cgb.button_provider = script
        cgb.run(until_swaps=7, max_steps=6_000_000)
        self.assertEqual(cgb.read16(br.PLAYER_XL), 0x01D0)
        self.assertEqual(cgb.read8(br.ANGLE), 12)
        self.assertEqual(cgb.page_swaps, 7)
        self.assertEqual(cgb.io[0x40] & 0x08, 0x08)

    def test_collision_blocks_world_boundary(self) -> None:
        cgb = self.boot_to_main()
        cgb.write8(br.ANGLE, 128)
        cgb.button_provider = lambda iteration, _swaps: 0x04 if iteration <= 10 else 0
        cgb.run(until_swaps=10, max_steps=8_000_000)
        x = cgb.read16(br.PLAYER_XL)
        self.assertGreaterEqual(x, 0x0100)
        self.assertEqual(x >> 8, 1)

    def test_door_interaction_mutates_map(self) -> None:
        cgb = self.boot_to_main()
        self.set_pose(cgb, 0x0880, 0x0480, 0)
        door_addr = br.MAP + 4 * 16 + 9
        self.assertEqual(cgb.read8(door_addr), 3)
        cgb.button_provider = lambda iteration, _swaps: 0x20 if iteration == 1 else 0
        cgb.run(until_swaps=1, max_steps=1_500_000)
        self.assertEqual(cgb.read8(door_addr), 0)
        self.assertEqual(cgb.read8(0xFF14), 0xC4)

    def test_fire_has_audio_and_visible_muzzle_feedback(self) -> None:
        cgb = self.boot_to_main()
        cgb.button_provider = lambda iteration, _swaps: 0x10 if iteration == 1 else 0
        cgb.run(until_swaps=1, max_steps=1_500_000)
        self.assertEqual(cgb.read8(0xFF14), 0xC7)
        self.assertGreater(cgb.read8(br.FLASH), 0)
        self.assertEqual(cgb.oam[17 * 4], 72)

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
        self.assertLess(update_cycles, 1_200_000)
        self.assertLessEqual(update_frames, 11)
        self.assertGreater(updates_per_second, 7.0)
        self.assertLessEqual(cgb.read8(br.ADAPTIVE_CASTS), 50)
        self.assertLessEqual(cgb.read8(br.EDGE_RECASTS), 16)
        self.assertLessEqual(cgb.read8(br.DYN_COUNT), br.DYNAMIC_TILE_CAPACITY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
