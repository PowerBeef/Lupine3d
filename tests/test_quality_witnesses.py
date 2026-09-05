"""Explicit legacy characterizations alongside independent geometric truth."""
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import build_rom as br
from quality_witnesses import scene_corpus, plane_hit, expected_mask, actor_transform, capture
from sm83emu import CGB


class QualityWitnesses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom,cls.asm,_ = br.make_rom()
        cls.scenes = {scene.name:scene for scene in scene_corpus()}

    def test_synthetic_height_class_mask_characterization(self):
        c = CGB(self.rom,self.asm.labels)
        for i in range(80): c.write8(br.RAY_DEPTH+i,128)
        for i in (39,41): c.write8(br.RAY_DEPTH+i,113)
        c.write8(br.SENTINEL_DEPTH,120); c.a = 80
        c.call_subroutine("entity_column_visible")
        self.assertEqual(c.a,0b11001100)

    def test_complete_flat_wall_witness_has_independent_visibility(self):
        scene = self.scenes["height_class_occlusion"]
        for column in range(160):
            hit = plane_hit(scene,column)
            self.assertEqual(hit["depth_q8"],1024)
            self.assertEqual(hit["axis"],0)
            self.assertEqual(hit["plane_q8"],2048)
        self.assertEqual(actor_transform(scene,scene.actors[0]),(Fraction(960),Fraction(0)))
        self.assertEqual(expected_mask(scene,scene.actors[0],80),0xFF)
        c,image,row = capture(self.rom,self.asm.labels,scene)
        self.assertEqual(image.size,(160,144))
        self.assertEqual(row["legacy_mask"],0xCC)  # known defect, removed only with the depth fix
        self.assertEqual(row["geometric_mask"],0xFF)
        self.assertTrue(row["intentional_legacy_difference"])
        self.assertGreater(c.read8(br.SENTINEL_OAM_USED),0)
        self.assertGreater(c.read8(br.MASK_TILE_COUNT),0)
        # These are actual physical casts in the generated machine code,
        # independent of the intermediate pair-height reconstruction.
        for column in range(76,84):
            c.write8(br.PIXEL_INDEX,column); c.call_subroutine("cast_physical_indexed")
            self.assertEqual(c.read8(br.DEPTH_RESULT),128)
            self.assertEqual(c.rom_bank,1)

    def test_thin_occluder_and_actor_covered_corner(self):
        thin = self.scenes["thin_occluder"]
        self.assertEqual(expected_mask(thin,thin.actors[0],80),0)
        corner = self.scenes["actor_covered_discontinuity"]
        mask = expected_mask(corner,corner.actors[0],103)
        self.assertNotIn(mask,(0,255))
        self.assertEqual(plane_hit(corner,100)["plane_q8"],2048)
        self.assertLess(plane_hit(corner,108)["depth_q8"],960)

    def test_finite_panels_and_camera_wrap_are_analytic(self):
        closed,open_half = (self.scenes[f"finite_door_{fraction}"] for fraction in (0,192))
        self.assertEqual(plane_hit(closed,80)["material"],3)
        self.assertEqual(plane_hit(open_half,80)["material"],1)
        scene = self.scenes["height_class_occlusion"]
        for column in (0,79,80,159):
            self.assertEqual(plane_hit(scene,column),plane_hit(replace(scene,pose=(1024,1152,256)),column))
        self.assertEqual(len([s for s in self.scenes if s.startswith("fractional_actor_")]),16)


if __name__ == "__main__": unittest.main()
