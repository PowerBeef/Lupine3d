# Your first engine change

This tutorial changes the engine itself: the easy skill will take a quarter
of an enemy's contact damage instead of half. On the way you will read the
SM83 the engine emits, see a test catch the change, see which ROMs it moves,
and run the checks that prove nothing else did. Every output below is real.

Read [engine development](../engine/README.md) first for where things are
and the rules a change keeps. Try this in a scratch branch or a copy of the
tree; it is an exercise, not a change the project wants.

## 1. Find the code

The skill scales contact damage when an enemy's touch lands. The engine is
Python that emits SM83 machine code, so the routine is a Python function
calling the assembler, in the module that owns the living world:

```sh
grep -n '"scale_contact_damage"' tools/lupine3d_v4/living_world.py
```

```python
a.label("scale_contact_damage")  # B = authored damage -> skill-scaled damage
a.ld_a_abs(DIFFICULTY); a.or_r("a"); a.jr("damage_not_easy", "nz")
a.ld_r_r("a", "b"); a.cb("srl", "a"); a.ld_r_r("b", "a"); a.ret()
a.label("damage_not_easy"); a.cp_n(2); a.ret("c")
a.ld_r_r("a", "b"); a.cb("srl", "a"); a.add_a_r("b"); a.ld_r_r("b", "a"); a.ret()
```

Read it as SM83: load the skill; if it is not 0 (easy), go on. On easy, copy
the damage from B to A, shift it right once (halve it), put it back and
return. On normal (1) return unchanged; on hard add half again. Each call is
one instruction ([the assembler](../engine/assembler.md)).

## 2. Change it

Shift twice on easy:

```python
a.ld_r_r("a", "b"); a.cb("srl", "a"); a.cb("srl", "a"); a.ld_r_r("b", "a"); a.ret()
```

This routine touches no bank register and no model of the picture, so
there is nothing else to keep in step: the host model predicts frames, and
contact damage is not in a frame ([add a routine](../engine/add-a-routine.md)
covers the cases where there is).

## 3. Let the tests find it

The engine's tests pin what they know. Run the one for skills; historical
tests run under explicit legacy settings, because the engine reads its flags
once at import:

```sh
LUPINE3D_DISPLAY=legacy LUPINE3D_ART=legacy LUPINE3D_ART_ANIMATION=0 LUPINE3D_POPULATION=evidence \
  .venv/bin/python -m unittest tests.test_enemies.SkillTests
```

```text
FAIL: test_skill_scales_contact_damage_and_nothing_else (tests.test_enemies.SkillTests.test_skill_scales_contact_damage_and_nothing_else)
    self.assertEqual(self._damage(cgb, 0, base), base // 2, base)
AssertionError: 1 != 2 : 4
```

The test runs the ROM's own `scale_contact_damage` in the harness
(`call_subroutine`) for three damages at each skill. It is right to fail:
the behaviour changed. Say what the new behaviour is, in the test:

```python
self.assertEqual(self._damage(cgb, 0, base), base // 4, base)
```

```text
Ran 2 tests in 11.962s

OK
```

## 4. See which ROMs moved

```sh
python tools/rom_identity.py compare --base HEAD --only default,legacy
```

```text
  CHANGED   default: ROM 9707e90eea9c -> 2e07c0c36300
  CHANGED   legacy: ROM de3841cc467e -> 61254fb0e2d2
FAILED: a ROM changed
```

`rom_identity` builds each configuration at the base and in your tree, each
in a fresh process, and compares the bytes. For a refactor, every ROM must
be identical; for a behaviour change like this one, the ROMs that move are
exactly the ones that should.

## 5. Prove nothing else changed

```sh
make playtest playtest-world
```

Both tours pass their frame checks and every golden still matches (nine and
fourteen scenes): they play at the default skill, so no picture moved. Had
one moved, the run would name the scene and you would look at its diff
before accepting it with a note ([verification](../explanation/verification.md)).

Before pushing a real change, run everything CI runs, in parallel, each lane
in its own copy of the tree:

```sh
python tools/lupine.py ci
```

That is the regression suite, the docs check, the playtests, the historical
profile, the starter game (built, played through, the limits game, a
scaffold), the controller route over the whole showcase in chunks, and the
slow lane: the A/B variants, wall reuse, motion, and both pinned emulator
cores ([development](../engine/development.md) says how to build them).

## Where next

- [Add a routine](../engine/add-a-routine.md), [add a check](../engine/add-a-check.md).
- [Architecture](../explanation/architecture.md): how a frame is made.
- [AGENTS.md](../../AGENTS.md): every contract the engine keeps, in one
  place.
