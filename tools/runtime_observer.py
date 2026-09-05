"""Instruction-boundary observations; never patch code or write emulated RAM.

Exclusive totals partition every elapsed T-cycle. Casting scopes are a second,
nested view and must not be added to those totals. OAM DMA's 640-T-cycle bus
ownership overlaps the executing HRAM wait loop; it is subtracted from that
loop's category. GDMA's CPU stall is already included by CGB._tick.
"""
from collections import Counter
import math
import statistics

import build_rom as br

CPU_HZ = 8_388_608
LCD_DOTS = 70_224
LCD_CPU_CYCLES = LCD_DOTS * 2
EXCLUSIVE = ("engine", "simulation_service", "interrupts", "publication_waits", "dma")


def distribution(values):
    """Nearest-rank percentiles; all values remain in CPU T-cycles."""
    values = sorted(values)
    if not values:
        return dict(count=0, mean=None, p50=None, p95=None, p99=None, worst=None)
    return dict(count=len(values), mean=statistics.fmean(values),
                **{f"p{p}": values[max(0, math.ceil(p / 100 * len(values)) - 1)] for p in (50, 95, 99)},
                worst=values[-1])


class RuntimeObserver:
    def __init__(self, c):
        self.c = c
        self.start = c.cycles
        self.totals = Counter({name: 0 for name in EXCLUSIVE})
        self.nested = Counter()
        self.counts = Counter()
        self.scopes = []
        self.casting = []
        self.events = []
        self.samples = {}
        self.external_ram_writes = 0
        self.oam_dma_end = 0
        self.pending_visible = []
        self.world_actor_candidates = set()
        self.last_published_actors = []
        self.executing = False
        self._step, self._write = c.step, c.write8
        self.entries = {c.symbols[name]: category for name, category in
                        (("render_yield", "simulation_service"), ("render_yield_ray", "simulation_service"),
                         ("render_yield_column", "simulation_service"), ("wait_vblank", "publication_waits"))
                        if name in c.symbols}
        self.cast_entries = {c.symbols[name]: name for name in
                             ("cast_all", "build_pixel_descriptors", "decorate_pixel_styles", "cast_one_v2")
                             if name in c.symbols}
        counter_labels = (
            ("cast_one_v2", "logical_rays"), ("dda_post_step", "crossings"),
            ("dda_read_cell", "scalar_cell_reads"), ("cast_physical_and_store", "physical_recasts"),
            ("q14_resume", "q14_continuations"), ("compose_dynamic_tile", "dynamic_compositions"),
            ("physical_missing_query", "additional_physical_queries"),
            ("dynamic_cache_hit", "dynamic_cache_hits"), ("dynamic_cache_miss", "dynamic_cache_misses"),
            ("packet_setup", "packet_setups"), ("packet_bounds", "packet_bounds"),
            ("packet_project_ray", "logical_rays"), ("packet_scalar_ray", "logical_rays"),
            ("packet_split", "packet_splits"), ("packet_fallback", "packet_fallbacks"),
            ("packet_read_cell", "packet_cell_reads"))
        self.counters = {}
        for name,counter in counter_labels:
            if name in c.symbols:
                self.counters.setdefault(c.symbols[name],[]).append(counter)
        self.packet_continues = {c.symbols[name] for name in ("packet_continue_x","packet_continue_y") if name in c.symbols}
        self.samples_pc = c.symbols.get("queue_vblank_input")
        self.simulation_pc = c.symbols.get("simulation_tick")
        self.admission_pc = c.symbols.get("submit_masked_oam")
        self.actor_pc = c.symbols.get("render_sentinel_actor")
        self.foreground = "foreground_vblank" in c.symbols
        c.step, c.write8 = self.step, self.write

    def _event(self, kind, **fields):
        event = dict(kind=kind, cycles=self.c.cycles, lcd_frame=self.c.frame_count,
                     ly=self.c.ly, **fields)
        self.events.append(event)
        return event

    def write(self, address, value):
        c = self.c
        if not self.executing and (0xC000 <= address < 0xFE00 or 0xFF80 <= address < 0xFFFF):
            self.external_ram_writes += 1
        if address in (0x2000, 0x3000, 0xFF70):
            self.counts["wram_bank_writes" if address == 0xFF70 else "rom_bank_writes"] += 1
        if address == 0xFF46:
            self.oam_dma_end = c.cycles + 640
            self.counts["oam_transfers"] += 1
            self._event("oam_dma", source=value << 8)
        if address == br.FLASH and value and (c.io[0x70] & 7) == 2:
            tick = c.read16(br.SIM_TICK)
            sample = self.samples.get(tick)
            self._event("accepted_fire", tick=tick, sampled_cycles=sample)
        self._write(address, value)
        if self.foreground and address == br.FG_SERIAL:
            self.counts["foreground_publications"] += 1
            self._event("foreground_publication", sequence=c.read16(br.FG_CONSUMED_SEQUENCE),generation=c.read16(br.FG_PUBLISHED_GENERATION))
        if address == 0xFF46 and c.oam[9 * 4] and c.oam[9 * 4 + 1]:
            # A scanline estimate, not a claim about the exact first pixel's
            # variable mode-3 dot. Independent PPU qualification remains separate.
            top=c.oam[36]-16;tile=c.oam[38]&254;attributes=c.oam[39];bank=(attributes>>3)&1
            opaque=[]
            for row in range(16):
                source_row=15-row if attributes&64 else row
                address=(tile+source_row//8)*16+(source_row%8)*2
                if 0<=top+row<144 and (c.vram[bank][address] or c.vram[bank][address+1]):opaque.append(top+row)
            if opaque:
                y=opaque[0]
                delta = (y * 456 - (c.ly * 456 + c.ppu_dots)) % LCD_DOTS
                self.pending_visible.append((c.cycles + delta * (2 if c.double_speed else 1),
                    c.read16(br.FG_CONSUMED_SEQUENCE) if self.foreground else None,
                    c.read16(br.FG_FRAME_GENERATION if value == 0xC8 else br.FG_PUBLISHED_GENERATION) if self.foreground else None))

    def _admission(self):
        c = self.c
        if not c.read8(br.MASK_BITS): reason = "occluded"
        elif c.read8(br.SENTINEL_OAM_USED) >= br.ENTITY_OAM_COUNT: reason = "object_capacity"
        elif not 0 < c.b < 160: reason = "y_clipped"
        elif any(c.read8(br.WORLD_SCANLINES + y) >= (10 if "preflight_actor" in c.symbols else 4) for y in range(max(0, c.b - 16), min(144, c.b))):
            reason = "scanline_capacity"
        else: reason = "admitted"
        prefix = "prospective_oam_" if "preflight_actor" in c.symbols and c.read8(br.ADMISSION_MODE) else "oam_"
        self.counts[prefix + reason] += 1

    def step(self):
        c = self.c
        for stack in (self.scopes, self.casting):
            while stack and (c.pc, c.sp) == stack[-1][:2]: stack.pop()
        pending_irq = bool(c.ime and c.ie & c.io[0x0F] & 0x1F)
        if pending_irq:
            self.scopes.append((c.pc, c.sp, "interrupts"))
        elif not c.halted:
            if c.pc in self.entries:
                self.scopes.append((c.read16(c.sp), (c.sp + 2) & 65535, self.entries[c.pc]))
            if c.pc in self.cast_entries:
                self.casting.append((c.read16(c.sp), (c.sp + 2) & 65535, self.cast_entries[c.pc]))
            for counter in self.counters.get(c.pc,()): self.counts[counter] += 1
            if c.pc in self.packet_continues:
                self.counts["crossings"] += c.read8(br.PACKET_WORKSPACE+1)
            if c.pc == c.symbols.get("packet_project_ray"):
                self.counts["crossings"] += 1
            if c.pc == self.samples_pc:
                tick = (c.read16(br.SIM_CLOCK) + 1) & 65535
                self.samples[tick] = c.cycles
                self._event("input_sample", tick=tick, held=c.read8(br.INPUT_LAST_RAW))
            if c.pc == self.simulation_pc:
                tick = c.read16(br.SIM_TICK)
                self._event("simulation_acceptance", tick=tick, sampled_cycles=self.samples.get(tick))
            if self.foreground and c.pc == c.symbols.get("foreground_producer_commit"):
                slot=c.read8(br.FG_HEAD);data=bytes(c.wramx[4][0x200+slot*10:0x20A+slot*10])
                accepted=next((e['cycles'] for e in reversed(self.events) if e['kind']=='accepted_fire'),c.cycles)
                self._event("foreground_queued",sequence=int.from_bytes(data[:2],"little"),
                    sampled_tick=int.from_bytes(data[2:4],"little"),accepted_tick=int.from_bytes(data[4:6],"little"),
                    generation=int.from_bytes(data[6:8],"little"),sampled_cycles=self.samples.get(int.from_bytes(data[2:4],"little")),
                    accepted_cycles=accepted)
            if c.pc == self.admission_pc: self._admission()
            if c.pc == self.actor_pc:
                self.world_actor_candidates.add(c.read8(br.ENTITY_SLOT))
        category = self.scopes[-1][2] if self.scopes else "engine"
        before, gdmas, presentations = c.cycles, len(c.gdma_events), c.presentations
        self.executing = True
        try:
            result = self._step()
        finally:
            self.executing = False
        elapsed = c.cycles - before
        dma = sum(e["blocks"] * (64 if c.double_speed else 32) for e in c.gdma_events[gdmas:])
        dma += max(0, min(c.cycles, self.oam_dma_end) - before)
        assert 0 <= dma <= elapsed, (dma, elapsed)
        self.totals["dma"] += dma
        self.totals[category] += elapsed - dma
        if category == "engine":
            for _, _, name in self.casting: self.nested[name] += elapsed - dma
        if c.presentations != presentations:
            tick = c.read16(br.FRAME_TICK)
            self.last_published_actors = sorted(self.world_actor_candidates)
            self.world_actor_candidates.clear()
            self._event("world_publication", snapshot_tick=tick,
                        actor_candidates=self.last_published_actors,
                        snapshot_age_ticks=(c.read16(br.SIM_CLOCK) - tick) & 65535,
                        input_age_ticks=(c.read16(br.SIM_CLOCK) - c.read16(br.SIM_TICK)) & 65535,
                        reused=bool(c.read8(br.FRAME_REUSED)))
        while self.pending_visible and c.cycles >= self.pending_visible[0][0]:
            estimate,sequence,generation = self.pending_visible.pop(0)
            self._event("muzzle_scanline_estimate", scanline_cycles=estimate,sequence=sequence,generation=generation)
        return result

    def report(self):
        elapsed = self.c.cycles - self.start
        assert sum(self.totals.values()) == elapsed
        flashes=[e for e in self.events if e["kind"]=="muzzle_scanline_estimate"]
        latencies=[]
        for event in self.events:
            if event["kind"] != ("foreground_queued" if self.foreground else "accepted_fire"): continue
            sample=event.get("sampled_cycles")
            visible=next((f for f in flashes if f["scanline_cycles"]>=event["cycles"] and (not self.foreground or
                         (f["generation"]==event["generation"] and ((f["sequence"]-event["sequence"])&65535)<32768))),None)
            if sample is not None and visible:
                latencies.append(dict(sample_to_visible=visible["scanline_cycles"]-sample,
                                      accepted_to_visible=visible["scanline_cycles"]-event.get("accepted_cycles",event["cycles"]),
                                      sequence=event.get("sequence")))
        return dict(timing_unit="cpu_t_cycles", cpu_hz=CPU_HZ, lcd_dots_per_interval=LCD_DOTS,
                    cpu_cycles_per_lcd_interval=LCD_CPU_CYCLES, elapsed_cycles=elapsed,
                    exclusive_cycles=dict(self.totals), nested_casting_cycles=dict(self.nested),
                    counters=dict(self.counts), game_ram_writes_after_trial_start=self.external_ram_writes,
                    event_precision="instruction boundaries; first opaque muzzle row at scanline start, excluding variable mode-3 pixel timing",
                    timing_reconciled=True, events=self.events,
                    feedback_latency={"sample_to_visible":distribution([v["sample_to_visible"] for v in latencies]),
                                      "accepted_to_visible":distribution([v["accepted_to_visible"] for v in latencies]),
                                      "samples":latencies,"target_t_cycles":2*LCD_CPU_CYCLES})

    def detach(self):
        self.c.step, self.c.write8 = self._step, self._write
