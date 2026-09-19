"""Machine-checked MBC5 bank-switching safety for the resident image.

On MBC5 the CPU sees ROM bank 0 at ``$0000-$3FFF`` and a switchable bank at
``$4000-$7FFF``.  The hardware rule that follows is narrow: code that writes
the bank register must live in the fixed half, or it pages itself out from
under the program counter, and code in the switchable half must not run while
some other bank is mapped there.

The build used to enforce a proxy for that rule - *every* byte of engine code
below ``$4000`` - which is far stronger than the hardware requires.  It was
cheap while the engine was small and had run out of room by the five-sector
campaign: 160 bytes.  This module enforces the real rule instead, as clauses
over the emitted image:

1. every write to the bank register lies in the fixed half;
2. no instruction that can run while a bank other than 1 is mapped lies in the
   switchable half;
3. the interrupt handlers, and everything they reach, lie in the fixed half
   and never write the bank register - an interrupt can land on any
   instruction, including one in the switchable half, and its vector is fixed;
4. the image contains no instruction the analysis cannot follow (``jp (hl)``
   and ``rst``), so an unfollowed edge can never hide a violation;
5. no control transfer leaves the image into the switchable half;
6. no placement section falls through into the next one, which is what makes a
   section free to be emitted at any address at all.

Code the analysis never reaches is reported but not constrained.  The entry
points are read out of the cartridge's own reset and interrupt vectors and
clause 4 leaves no edge unfollowed, so unreached means unreachable; and clause
1 keeps every bank write in the fixed half whether its routine runs or not.
The engine carries about 900 bytes of it - ``update_world`` and the stepped
line-of-sight walk, both superseded and neither called from anywhere.

Clause 2 is a context-sensitive taint analysis over the control-flow graph.
The mapped bank is tracked as one value - "bank 1" or "the bank this write
selected" - because that is all the rule needs.  A write of the literal 1
clears it; any other write, including one whose value the analysis cannot
read, sets it, which is the conservative direction.  Calls are matched to
their returns per call site, so a routine that switches a bank and restores it
does not contaminate its callers, and one that returns with a foreign bank
still mapped - ``upload_profile_tiles`` does exactly that - contaminates the
right ones.

The analysis is conservative in two places that matter and stays that way on
purpose.  It does not correlate a conditional switch with the conditional
restore that matches it, so ``find_atlas_tile``, which pages the inactive
wall atlas in and out under the same test, is treated as able to return with
that bank mapped; everything it can reach is therefore pinned to the fixed
half.  And it credits nothing to code it cannot reach.  Both cost placement
freedom, never safety.
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from dataclasses import dataclass, field

BANK_REGISTER = 0x2000
FIXED_BANK_END = 0x4000
SWITCHABLE_END = 0x8000

_UNCONDITIONAL_JUMP = frozenset({0xC3, 0x18})
_CONDITIONAL_JUMP = frozenset({0xC2, 0xCA, 0xD2, 0xDA, 0x20, 0x28, 0x30, 0x38})
_UNCONDITIONAL_CALL = frozenset({0xCD})
_CONDITIONAL_CALL = frozenset({0xC4, 0xCC, 0xD4, 0xDC})
_RETURN = frozenset({0xC9, 0xD9})
_CONDITIONAL_RETURN = frozenset({0xC0, 0xC8, 0xD0, 0xD8})
_LD_A_N = 0x3E
_LD_ABS_A = 0xEA
# jp (hl) and the eight rst vectors are the only transfers whose target this
# analysis cannot read out of the image. The engine emits none of them; the
# checker refuses an image that starts to, rather than silently losing an edge.
_UNANALYSABLE = frozenset({0xE9, 0xC7, 0xCF, 0xD7, 0xDF, 0xE7, 0xEF, 0xF7, 0xFF})

_TRANSFERS = (_UNCONDITIONAL_JUMP | _CONDITIONAL_JUMP
              | _UNCONDITIONAL_CALL | _CONDITIONAL_CALL)


@dataclass(frozen=True)
class Instruction:
    address: int
    length: int
    opcode: int
    operands: bytes
    target: int | None
    text: str

    @property
    def end(self) -> int:
        return self.address + self.length


@dataclass
class BankSafetyReport:
    """What the analysis found, in bytes rather than opinions."""

    instructions: dict[int, Instruction]
    bank_writes: tuple[int, ...]
    tainted: frozenset[int]
    interrupt: frozenset[int]
    unreached: frozenset[int]
    external_targets: frozenset[int]
    violations: tuple[str, ...] = ()

    def _bytes(self, addresses) -> int:
        return sum(self.instructions[a].length for a in addresses)

    @property
    def pinned(self) -> frozenset[int]:
        """Instructions that must stay in the fixed half."""
        return frozenset(self.tainted | self.interrupt)

    @property
    def relocatable(self) -> frozenset[int]:
        return frozenset(set(self.instructions) - self.pinned)

    def summary(self) -> dict[str, int]:
        return {
            "instructions": len(self.instructions),
            "instruction_bytes": self._bytes(self.instructions),
            "bank_writes": len(self.bank_writes),
            "bank_window_bytes": self._bytes(self.tainted),
            "interrupt_bytes": self._bytes(self.interrupt),
            "unreached_bytes": self._bytes(self.unreached),
            "pinned_bytes": self._bytes(self.pinned),
            "relocatable_bytes": self._bytes(self.relocatable),
        }


class BankSafetyError(AssertionError):
    pass


def _decode(assembler) -> dict[int, Instruction]:
    """Turn the assembler's own emission record into an instruction map.

    The listing carries one entry per emission with its address and length, and
    ``data_spans`` marks the emissions that are tables, so nothing here has to
    guess an instruction length or risk decoding a lookup table as code.
    """
    resolved = assembler.resolve()
    spans = sorted(assembler.data_spans)
    starts = [start for start, _ in spans]

    def is_data(address: int) -> bool:
        index = bisect.bisect_right(starts, address) - 1
        return index >= 0 and spans[index][0] <= address < spans[index][1]

    instructions: dict[int, Instruction] = {}
    for address, raw, text in assembler.listing:
        if not raw or is_data(address):
            continue
        offset = address - assembler.origin
        encoded = resolved[offset:offset + len(raw)]
        opcode = encoded[0]
        target = None
        if opcode in _TRANSFERS:
            if len(encoded) == 3:
                target = encoded[1] | (encoded[2] << 8)
            else:                                   # jr: signed displacement
                target = (address + 2 + ((encoded[1] ^ 0x80) - 0x80)) & 0xFFFF
        instructions[address] = Instruction(
            address, len(encoded), opcode, bytes(encoded[1:]), target, text)
    return instructions


def _bank_write_value(instruction: Instruction, previous: Instruction | None) -> int | None:
    """The bank a write selects, when the image states it as a literal."""
    if previous is not None and previous.opcode == _LD_A_N:
        return previous.operands[0]
    return None


def _reachable(entry: int, instructions: dict[int, Instruction]) -> set[int]:
    """Everything reachable from ``entry``, calls included, ignoring banks."""
    seen: set[int] = set()
    pending = [entry]
    while pending:
        address = pending.pop()
        if address in seen:
            continue
        instruction = instructions.get(address)
        if instruction is None:
            continue
        seen.add(address)
        opcode = instruction.opcode
        if opcode in _RETURN:
            continue
        if opcode in _UNCONDITIONAL_JUMP:
            pending.append(instruction.target)
            continue
        if opcode in _CONDITIONAL_JUMP or opcode in _UNCONDITIONAL_CALL or opcode in _CONDITIONAL_CALL:
            pending.append(instruction.target)
        pending.append(instruction.end)
    return seen


def analyze(assembler, entry_points: dict[str, int]) -> BankSafetyReport:
    instructions = _decode(assembler)
    ordered = sorted(instructions)
    previous = {ordered[i]: instructions[ordered[i - 1]] for i in range(1, len(ordered))}

    def is_bank_write(instruction: Instruction) -> bool:
        return (instruction.opcode == _LD_ABS_A
                and instruction.operands[0] | (instruction.operands[1] << 8) == BANK_REGISTER)

    bank_writes = tuple(a for a in ordered if is_bank_write(instructions[a]))

    # Context-sensitive walk. A state is the bank believed to be mapped:
    # 0 means bank 1 (the engine's resting bank), anything else is the address
    # of the write that selected a foreign bank, which keeps the report able to
    # name the window an instruction belongs to.
    reached: set[tuple[tuple[int, int], int, int]] = set()
    summaries: dict[tuple[int, int], set[int]] = defaultdict(set)
    callers: dict[tuple[int, int], set[tuple[tuple[int, int], int]]] = defaultdict(set)
    external: set[int] = set()
    pending: list[tuple[tuple[int, int], int, int]] = []

    def push(context: tuple[int, int], address: int, state: int) -> None:
        item = (context, address, state)
        if item not in reached:
            reached.add(item)
            pending.append(item)

    for entry in entry_points.values():
        push((entry, 0), entry, 0)

    while pending:
        context, address, state = pending.pop()
        instruction = instructions.get(address)
        if instruction is None:
            external.add(address)
            continue
        opcode, following = instruction.opcode, instruction.end
        if is_bank_write(instruction):
            selected = _bank_write_value(instruction, previous.get(address))
            push(context, following, 0 if selected == 1 else address)
            continue
        if opcode in _RETURN or opcode in _CONDITIONAL_RETURN:
            if state not in summaries[context]:
                summaries[context].add(state)
                for caller, resume in callers[context]:
                    push(caller, resume, state)
            if opcode in _CONDITIONAL_RETURN:
                push(context, following, state)
            continue
        if opcode in _UNCONDITIONAL_JUMP:
            push(context, instruction.target, state)
            continue
        if opcode in _CONDITIONAL_JUMP:
            push(context, instruction.target, state)
            push(context, following, state)
            continue
        if opcode in _UNCONDITIONAL_CALL or opcode in _CONDITIONAL_CALL:
            target = instruction.target
            if target not in instructions:
                # The OAM DMA stub runs from HRAM and returns with the mapped
                # bank untouched.
                external.add(target)
                push(context, following, state)
                continue
            callee = (target, state)
            if (context, following) not in callers[callee]:
                callers[callee].add((context, following))
                for returned in tuple(summaries[callee]):
                    push(context, following, returned)
            push(callee, target, state)
            if opcode in _CONDITIONAL_CALL:
                push(context, following, state)
            continue
        push(context, following, state)

    tainted = frozenset(address for _, address, state in reached if state)
    covered = {address for _, address, _ in reached}
    unreached = frozenset(set(instructions) - covered)

    interrupt: set[int] = set()
    for name, entry in entry_points.items():
        if name != "reset":
            interrupt |= _reachable(entry, instructions)

    report = BankSafetyReport(
        instructions=instructions,
        bank_writes=bank_writes,
        tainted=tainted,
        interrupt=frozenset(interrupt),
        unreached=unreached,
        external_targets=frozenset(external),
    )
    report.violations = tuple(_violations(assembler, report, entry_points))
    return report


def _describe(instructions: dict[int, Instruction], address: int) -> str:
    instruction = instructions[address]
    return f"{address:04X} {instruction.text}"


def _violations(assembler, report: BankSafetyReport, entry_points: dict[str, int]) -> list[str]:
    instructions = report.instructions
    found: list[str] = []

    for address, instruction in sorted(instructions.items()):
        if instruction.opcode in _UNANALYSABLE:
            found.append(f"clause 4: unfollowable transfer at {_describe(instructions, address)}")

    for address in report.bank_writes:
        if address >= FIXED_BANK_END:
            found.append("clause 1: bank register written from the switchable half at "
                         f"{_describe(instructions, address)}")

    for address in sorted(report.tainted):
        if address >= FIXED_BANK_END:
            found.append("clause 2: runs in the switchable half with a foreign bank mapped at "
                         f"{_describe(instructions, address)}")

    for address in sorted(report.interrupt):
        if address >= FIXED_BANK_END:
            found.append("clause 3: interrupt-reachable code in the switchable half at "
                         f"{_describe(instructions, address)}")
        if address in set(report.bank_writes):
            found.append("clause 3: interrupt-reachable code writes the bank register at "
                         f"{_describe(instructions, address)}")


    for target in sorted(report.external_targets):
        if FIXED_BANK_END <= target < SWITCHABLE_END:
            found.append(f"clause 5: control leaves the image into the switchable half at ${target:04X}")

    ordered = sorted(instructions)
    for name, start in assembler.sections:
        index = bisect.bisect_left(ordered, start) - 1
        if index < 0:
            continue
        before = instructions[ordered[index]]
        if before.opcode in _RETURN or before.opcode in _UNCONDITIONAL_JUMP:
            continue
        found.append(f"clause 6: section {name!r} at ${start:04X} can be fallen into from "
                     f"{_describe(instructions, before.address)}")
    return found


def entry_points(assembler, rom) -> dict[str, int]:
    """Where the console can start executing, read out of the cartridge.

    Taking these from the vector table rather than from a flag means enabling
    another interrupt cannot quietly leave its handler unchecked.
    """
    points: dict[str, int] = {}
    if rom[0x0101] != 0xC3:
        raise BankSafetyError("reset vector does not jump into the engine")
    points["reset"] = rom[0x0102] | (rom[0x0103] << 8)
    for vector in range(0x0040, 0x0068, 8):
        opcode = rom[vector]
        if opcode == 0xFF:
            continue                            # unused vector, left as filler
        if opcode != 0xC3:
            raise BankSafetyError(f"interrupt vector ${vector:02X} is not a jump")
        points[f"interrupt_{vector:02X}"] = rom[vector + 1] | (rom[vector + 2] << 8)
    if assembler.labels["vblank_isr"] not in points.values():
        raise BankSafetyError("the VBlank handler is not installed in its vector")
    return points


def check_bank_safety(assembler, rom) -> BankSafetyReport:
    report = analyze(assembler, entry_points(assembler, rom))
    if report.violations:
        listed = "\n  ".join(report.violations[:20])
        more = "" if len(report.violations) <= 20 else f"\n  ... and {len(report.violations) - 20} more"
        raise BankSafetyError(f"MBC5 bank safety ({len(report.violations)} violations):\n  {listed}{more}")
    return report
