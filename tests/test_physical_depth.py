"""Physical-query provenance, exact reuse and same-snapshot promotion."""
from dataclasses import replace
import unittest

from test_render_experiments import variant
import build_rom as br
from playtest import read_block, set_test_world_byte, validate_frame
from quality_witnesses import scene_corpus,setup,expected_mask
from sm83emu import CGB


class PhysicalDepthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.physical = variant(COMPACT_STRIPS=1,FOLDED=1,PHYSICAL_DEPTH=1)
        cls.forced = variant(COMPACT_STRIPS=1,FOLDED=1,PHYSICAL_DEPTH=1,WALL_REUSE=0)
        cls.scenes = {s.name:s for s in scene_corpus()}

    def boot(self,variant,scene):
        c=CGB(variant[0],variant[1]); queries=set()
        def clear(cpu): queries.clear()
        def query(cpu):
            self.assertEqual(cpu.io[0x70]&7,1)
            queries.add(cpu.read8(br.PIXEL_INDEX))
        c.breakpoints[variant[1]["clear_physical_depth"]]=clear
        c.breakpoints[variant[1]["cast_physical_indexed_prepared"]]=query
        c.run(until_pc=variant[1]["main_loop"]); setup(c,scene)
        c.run(until_presentations=c.presentations+1)
        return c,queries

    def validity(self,c):
        bits=read_block(c,br.PIXEL_DEPTH_VALID,20)
        return {x for x in range(160) if bits[x>>3] & (1<<(x&7))}

    def actor(self,c,xy):
        data=xy[0].to_bytes(2,"little")+xy[1].to_bytes(2,"little")
        for i,value in enumerate(data):
            set_test_world_byte(c,br.ENTITY_SLOTS+i,value); set_test_world_byte(c,br.SENTINEL_XL+i,value)

    def test_complete_witness_and_actual_query_provenance(self):
        scene=self.scenes["height_class_occlusion"]
        c,queries=self.boot(self.physical,scene)
        self.assertEqual(self.validity(c),queries)
        self.assertTrue(set(range(72,88)) <= queries)
        self.assertEqual({c.read8(br.PIXEL_DEPTH+x) for x in range(72,88)},{128})
        c.ime=False; c.a=80; c.write8(br.SENTINEL_DEPTH,120); c.call_subroutine("entity_column_visible")
        self.assertEqual(c.a,expected_mask(scene,scene.actors[0],80))
        self.assertEqual(c.a,255)
        self.assertEqual(c.read8(br.PHYSICAL_DEPTH_MISSING),0)
        validate_frame(c)

    def test_reuse_keeps_validity_and_queries_only_new_coverage(self):
        c,queries=self.boot(self.physical,self.scenes["height_class_occlusion"])
        first=set(queries)
        c.run(until_presentations=c.presentations+1)
        self.assertEqual(c.read8(br.FRAME_REUSED),1)
        self.assertEqual(c.read8(br.PHYSICAL_QUERY_COUNT),0)
        self.assertEqual(queries,first)
        self.actor(c,(1984,1280))
        c.run(until_presentations=c.presentations+1)
        self.assertEqual(self.validity(c),queries)
        self.assertGreater(len(queries-first),0)
        self.assertEqual(c.read8(br.PHYSICAL_QUERY_COUNT),len(queries-first))
        # A flat plane does not imply identical reconstructed descriptors:
        # off-axis queries refine quantized tops/along coordinates as well.
        self.assertEqual(c.read8(br.REFINEMENT_DIRTY),1)
        self.assertEqual(c.read8(br.FRAME_REUSED),0)
        self.assertEqual(c.read8(br.GEOMETRY_BACKBONE_RAN),0)
        self.assertEqual(c.read8(br.PHYSICAL_DEPTH_MISSING),0)
        validate_frame(c)

    def test_refinement_promotion_matches_forced_full_with_identical_coverage(self):
        scene=replace(self.scenes["actor_covered_discontinuity"],actors=((1984,960),))
        fast,queries=self.boot(self.physical,scene)
        full,_=self.boot(self.forced,scene)
        initial=self.validity(fast)
        # Find a real reconstructed descriptor that differs from its physical
        # query, then move the actor over it while the wall key stays constant.
        fast.ime=False
        target=None
        for x in range(8,152):
            if x in initial: continue
            fast.write8(br.PIXEL_INDEX,x); fast.call_subroutine("cast_physical_indexed")
            if any(fast.read8(base+x)!=fast.read8(result) for base,result in
                   ((br.PIXEL_TOPS,br.TOP_RESULT),(br.PIXEL_KEYS,br.FACE_RESULT),(br.PIXEL_ALONG,br.ALONG_RESULT),
                    (br.PIXEL_SEGMENT,br.SEGMENT_RESULT),(br.PIXEL_SURFACE,br.SURFACE_RESULT))):
                target=x;break
        self.assertIsNotNone(target,"fixture must contain a physical refinement")
        queries.intersection_update(initial)  # diagnostic probes above do not publish validity
        fast.ime=True
        xy=(1984,scene.pose[1]+round((target-80)*960/br.CAMERA_FOCAL_PIXELS))
        for c in (fast,full):
            self.actor(c,xy)
            def union(cpu):
                for x in initial:
                    address=br.PHYSICAL_COVERAGE+(x>>3)
                    cpu.write8(address,cpu.read8(address)|(1<<(x&7)))
            c.breakpoints[c.symbols["refine_physical_depth"]]=union
            c.run(until_presentations=c.presentations+1)
            validate_frame(c)
        self.assertEqual(fast.read8(br.GEOMETRY_BACKBONE_RAN),0)
        self.assertEqual(fast.read8(br.REFINEMENT_DIRTY),1)
        self.assertEqual(fast.read8(br.FRAME_REUSED),0)
        self.assertEqual(fast.render_screen().tobytes(),full.render_screen().tobytes())
        self.assertEqual(self.validity(fast),self.validity(full))
        for address,count in ((br.PIXEL_TOPS,640),(br.PIXEL_SEGMENT,160),(br.PIXEL_SURFACE,160),
                              (br.VIEW_MAP,384),(br.DYNAMIC_TILES,fast.read8(br.DYN_COUNT)*16),
                              (br.MASK_TILES,fast.read8(br.MASK_TILE_COUNT)*16)):
            self.assertEqual(read_block(fast,address,count),read_block(full,address,count),hex(address))

    def test_one_through_four_actors_and_repeatable_decoration(self):
        scene=self.scenes["four_actor_coverage"]
        for count in range(1,5):
            c,queries=self.boot(self.physical,replace(scene,actors=scene.actors[:count]))
            self.assertEqual(self.validity(c),queries)
            self.assertLessEqual(len(queries),160)
            self.assertEqual(c.read8(br.PHYSICAL_DEPTH_MISSING),0)
            before=read_block(c,br.PIXEL_STYLES,160)
            c.ime=False
            c.call_subroutine("restore_base_styles"); c.call_subroutine("decorate_pixel_styles")
            self.assertEqual(read_block(c,br.PIXEL_STYLES,160),before)
            self.assertEqual(c.rom_bank,1)

    def test_coverage_selects_each_actors_current_lod(self):
        scene=replace(self.scenes["height_class_occlusion"],actors=((1344,1152),))
        c=CGB(self.physical[0],self.physical[1]);c.run(until_pc=c.symbols["main_loop"]);setup(c,scene)
        c.write8(br.SENTINEL_LOD,2);c.write8(br.LOD_HISTORY,2)
        c.run(until_presentations=c.presentations+1)
        self.assertTrue(set(range(72,88))<=self.validity(c))
        self.assertEqual(c.read8(br.PHYSICAL_DEPTH_MISSING),0)

    def test_all_screen_refinement_is_bounded_and_preserves_guard_bytes(self):
        c=CGB(self.physical[0],self.physical[1]);c.run(until_pc=c.symbols["main_loop"])
        setup(c,self.scenes["four_actor_coverage"])
        queried=set()
        def cover_all(cpu):
            for offset in range(20):cpu.write8(br.PHYSICAL_COVERAGE+offset,255)
        def observe_query(cpu):
            column=cpu.read8(br.PIXEL_INDEX)
            self.assertLess(column,160)
            queried.add(column)
        c.breakpoints[c.symbols["refine_physical_depth"]]=cover_all
        c.breakpoints[c.symbols["cast_physical_indexed_prepared"]]=observe_query
        for address in range(0xDF56,0xDF60):c.write8(address,0xA5)
        c.run(until_presentations=c.presentations+1)
        self.assertEqual(self.validity(c),set(range(160)))
        self.assertEqual(queried,set(range(160)))
        self.assertEqual(read_block(c,0xDF56,10),bytes([0xA5])*10)
        self.assertLessEqual(c.read8(br.PHYSICAL_QUERY_COUNT),160)
        self.assertEqual(c.read8(br.PHYSICAL_DEPTH_MISSING),0)
        self.assertEqual(c.io[0x70]&7,1)
        self.assertEqual(c.rom_bank,1)
        validate_frame(c)


if __name__ == "__main__": unittest.main()
