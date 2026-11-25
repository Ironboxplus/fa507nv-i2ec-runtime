# FA507NV IT5570 runtime I2EC backend

This repository contains the narrow runtime transport needed to validate and,
only after explicit checks, write the FA507NV IT5570 EC `GPD0` register.

The earlier SIO/SMFI experiment was not the live GPIO backend: it could read a
stable `0x1604` value but a bit write read back unchanged. The EC firmware and
IT5570 documentation identify a separate dedicated I2EC window at `0x681–0x683`
that addresses the full 16-bit EC memory space. `src/IT5570I2EC.p` exposes that
window to PawnIO; `src/i2ec_runtime_adapter.py` keeps the default path read-only
and requires `SPCTRL1[1:0] == 3` plus readback verification before a write.

The CI workflow compiles the PawnIO module and runs the Python state-machine
tests in parallel. CI never touches hardware and never contains a firmware
flasher. A hardware probe must be run locally, elevated, with the exact module
artifact from a pinned Actions run.

On Windows, the first live read uses the already signed `LpcIO.bin` module and
`src/i2ec_lpcio_bridge.py`. The bridge temporarily anchors the PIO whitelist
with inactive LDN `0x14`, restores its `0x30/0x60/0x61` bytes in `finally`, and
does not expose a write operation.

## Scope

- Read `0x200D` (I2EC permission) and `0x1604` (GPD0 data byte).
- Verify a controlled `old | 1` write and restore the original byte.
- Keep the higher-level runtime controller fail-closed until a live readback is
  recorded on this machine.

No firmware image is modified or flashed by this project.
