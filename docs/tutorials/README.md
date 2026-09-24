# Tutorials

Lessons, in order, each built on the last. Every command and output in them
is real; follow them literally from the repository root.

| Tutorial | You will | Time |
|---|---|---|
| [Your first game](first-game.md) | make a game from the starter: retitle it, recolour it, add an enemy kind, approve its goldens and play it through | 30 minutes |
| [Your first level](first-level.md) | draw a level from a blank grid, fix what the compiler refuses, edit it in Tiled, watch it being finished | 30 minutes |
| [Your first engine change](first-engine-change.md) | change the SM83 the engine emits, see a test catch it, see which ROMs move, prove nothing else did | 30 minutes |

The first two need only Python, Make and an emulator to play the result.
The third is for contributors to the engine itself.

## The contracts in one paragraph

For when you want to know what the engine promises before you start:
simulation runs on a fixed tick in WRAM bank 2 while each frame renders
from an immutable snapshot in bank 1. A frame is cast with forty-one
prepared rays and reconstructed to 160 columns, its walls textured and
composed into a ring of dynamic tiles, and published to the hidden VRAM page
by HBlank DMA during composition plus one VBlank tail. Everything the
console draws is predicted byte for byte by a Python model, and every
invariant (geometry, publication safety, the MBC5 bank rule, the memory
reserves, agreement between cores) is a hard gate; pictures are golden
snapshots with an explicit acceptance path. [Architecture](../explanation/architecture.md)
states these contracts precisely and [verification](../explanation/verification.md)
says how each is checked.
