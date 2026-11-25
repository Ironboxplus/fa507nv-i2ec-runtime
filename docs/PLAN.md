# Runtime I2EC backend plan

> User approval, 2026-11-26: “将这个笔记本固件修复的bug走githubactions，先新建仓库，然后根据devworkflow的指导来异步并发使用actions”。

## Proven root cause

The SIO/SMFI host window is not a verified live GPIO write path: the target
bit write was rejected by readback. The firmware's dedicated I2EC configuration
provides the full EC-memory address latch at `0x681–0x683`, with permission
controlled by `0x200D[1:0]`.

## Design

1. Compile one small PawnIO module exposing only I2EC read and guarded write.
2. Keep the Python adapter read-only by default.
3. Require the EC to report read-write permission before a write.
4. Read back every write and restore the original byte after a timed test.
5. Keep all higher-level runtime safety predicates in the existing controller;
   CI does not assert a hardware gate.

## CI and verification

`python-tests`, `static-audit`, and `pawn-module` run as independent jobs on
the same commit. The concurrency group includes the commit SHA, so a new
commit does not cancel the run whose failure is being inspected. The final
gate is a green run of all three jobs; a green job from a different commit is
not sufficient.

The hardware step happens only after the module artifact is pinned to a green
Actions commit. It is not part of CI and it never flashes firmware.
