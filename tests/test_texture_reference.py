"""The textured-wall reference: along-face coordinates, symmetric textures,
and the row-window composition equal to the pixel-level one.

The textured profile exists on the slim viewport only, so these tests run
under it: `tools/run_tests.py` runs the historical suite under the legacy
geometry, where they are skipped, and `tests/test_textured_walls.py` runs
this module again in a fresh slim process.
"""
from fractions import Fraction
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_rom as br  # noqa: E402
from lupine3d_v4 import texture_reference as tx  # noqa: E402
from lupine3d_v4.reference import reference_cast_hit  # noqa: E402

SLIM = unittest.skipUnless(br.SLIM_DISPLAY, "the textured reference is defined on the slim viewport")


def checker(name="checker"):
    rows = tuple(tuple(1 + ((u // 4 + v // 2) % 3) for u in range(16)) for v in range(8))
    return tx.Texture(name, rows)


@SLIM
class AlongFaceTests(unittest.TestCase):
    def test_along_face_is_the_hit_point_on_the_face(self):
        # Facing +x from the middle of a cell, the centre ray hits the wall
        # ahead at the player's own y fraction.
        br.select_reference_level(0)
        grid = bytes(1 if x in (0, 15) or y in (0, 15) else 0 for y in range(16) for x in range(16))
        # The ray's own direction, advanced by its axis distance, lands on the
        # face where the along coordinate says (to the raw components' rounding).
        for px, py, yaw, ray in ((2048, 2048, 0, 40), (2048, 2112, 0, 12), (2148, 2048, 64, 40), (2048, 2248, 128, 70)):
            hit = reference_cast_hit(px, py, yaw, ray, grid, {})
            if hit.axis == 0:
                expected = py + (1 if hit.dy > 0 else -1) * hit.axis_distance_q8 * abs(hit.dy) / abs(hit.dx)
                mirrored = hit.dx < 0
            else:
                expected = px + (1 if hit.dx > 0 else -1) * hit.axis_distance_q8 * abs(hit.dx) / abs(hit.dy)
                mirrored = hit.dy > 0
            # The east and north faces are read right to left so texture
            # columns never decrease across the view (reference.py).
            expected_q8 = (-int(expected) if mirrored else int(expected)) % 256
            error = min(abs(hit.along_q8 - expected_q8), 256 - abs(hit.along_q8 - expected_q8))
            # The reference advances the Q14 ordering direction; the raw 7-bit
            # components used here differ from it by a few units over five cells.
            self.assertLessEqual(error, 12, (px, py, yaw, ray, hit.along_q8, expected))
        self.assertEqual(reference_cast_hit(2048, 2048, 0, 40, grid, {}).axis, 0)
        self.assertEqual(reference_cast_hit(2148, 2048, 64, 40, grid, {}).axis, 1)

    def test_texture_columns_never_decrease_along_a_face(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
        import textured_walls_lab as lab
        br.select_reference_level(0)
        for pose in ((1152, 3456, 192), (1408, 3200, 0), (1152, 3100, 255)):
            columns, _ = lab.textured_columns(pose, None, None)
            for first in range(0, 160, 8):
                for start, end in tx.tile_runs(columns, first):
                    u = [c.u for c in columns[start:end]]
                    steps = [(b - a) % tx.TEXELS for a, b in zip(u, u[1:])]
                    self.assertTrue(all(step < 8 for step in steps), (pose, start, u))


class TextureTests(unittest.TestCase):
    def test_textures_are_sixteen_by_eight_with_wall_colours(self):
        with self.assertRaises(ValueError):
            tx.Texture("bad", tuple(tuple(0 for _ in range(16)) for _ in range(8)))
        with self.assertRaises(ValueError):
            tx.Texture("short", tuple(tuple(2 for _ in range(16)) for _ in range(7)))
        self.assertEqual(checker().texel(17, 0), checker().texel(1, 0))

    def test_v_lut_covers_every_height_class(self):
        lut = tx.make_v_lut()
        self.assertEqual(len(lut), (br.HORIZON + 1) * 64)
        for half in range(2, br.HORIZON + 1):
            rows = [lut[half * 64 + offset] for offset in range(half)]
            self.assertEqual(rows[0], 0)
            if half >= tx.TEXEL_ROWS:
                self.assertEqual(rows[-1], tx.TEXEL_ROWS - 1)
            self.assertEqual(rows, sorted(rows))


@SLIM
class CompositionTests(unittest.TestCase):
    def test_row_windows_equal_pixel_level_composition(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
        import textured_walls_lab as lab
        textures = [checker("a"), checker("b"), checker("c")]
        windows = tx.make_row_windows(textures)
        br.select_reference_level(0)
        for pose in ((1152, 3456, 192), (1152, 3136, 192), (1408, 3200, 0), (1152, 3100, 191)):
            columns, _ = lab.textured_columns(pose, None, None)
            affine = tx.affine_columns(columns)
            pixels, view_map, count, overflow, stats = tx.compose_pixels(textures, affine)
            self.assertFalse(overflow)
            by_kernel, kernel_map, kernel_count, kernel_overflow = tx.compose_kernel(textures, columns, windows)
            self.assertEqual(by_kernel, pixels, pose)
            self.assertEqual(kernel_map, view_map, pose)
            self.assertEqual((kernel_count, kernel_overflow), (count, False))
            self.assertEqual(count, len(pixels) // 16)
            self.assertLessEqual(count, tx.DYNAMIC_TILE_CAPACITY)   # the textured profile's 238, whatever this build's
            # Every wall tile is mirrored into the lower half of the map.
            for row in range(br.FOLDED_ROWS):
                self.assertEqual(view_map[row * 32:row * 32 + 20], view_map[(br.VIEW_ROWS - 1 - row) * 32:(br.VIEW_ROWS - 1 - row) * 32 + 20])

    def test_window_table_size_is_twenty_kib_per_texture(self):
        self.assertEqual(tx.window_table_bytes(1), 4 * len(tx.DELTA_CLASSES) * 16 * tx.PHASE_STEPS * 8 * 2)


if __name__ == "__main__":
    unittest.main()
