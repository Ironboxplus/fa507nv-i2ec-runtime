"""Fail-closed Windows adapter for the IT5570 dedicated I2EC window."""
from __future__ import annotations

import argparse
import ctypes
import json
import time
from pathlib import Path


class I2ECAdapter:
    def __init__(self, library: Path, module: Path):
        self.lib = ctypes.WinDLL(str(library), use_last_error=True)
        H = ctypes.c_void_p; U = ctypes.c_uint64; S = ctypes.c_size_t
        self.lib.pawnio_open_win32.argtypes = [ctypes.POINTER(H)]
        self.lib.pawnio_open_win32.restype = ctypes.c_bool
        self.lib.pawnio_load_win32.argtypes = [H, ctypes.c_void_p, S]
        self.lib.pawnio_load_win32.restype = ctypes.c_bool
        self.lib.pawnio_execute_win32.argtypes = [H, ctypes.c_char_p,
            ctypes.POINTER(U), S, ctypes.POINTER(U), S, ctypes.POINTER(S)]
        self.lib.pawnio_execute_win32.restype = ctypes.c_bool
        self.lib.pawnio_close_win32.argtypes = [H]
        self.lib.pawnio_close_win32.restype = ctypes.c_bool
        self.handle = H()
        if not self.lib.pawnio_open_win32(ctypes.byref(self.handle)):
            raise OSError(ctypes.get_last_error(), "pawnio_open_win32")
        blob = module.read_bytes()
        buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        if not self.lib.pawnio_load_win32(self.handle, buf, len(blob)):
            self.lib.pawnio_close_win32(self.handle)
            raise OSError(ctypes.get_last_error(), "pawnio_load_win32")

    def call(self, name: str, values=(), out_count=0):
        U = ctypes.c_uint64; S = ctypes.c_size_t
        ins = (U * len(values))(*values) if values else None
        outs = (U * out_count)() if out_count else None
        returned = S()
        if not self.lib.pawnio_execute_win32(self.handle, name.encode(), ins,
                                              len(values), outs, out_count,
                                              ctypes.byref(returned)):
            raise OSError(ctypes.get_last_error(), name)
        return [int(outs[i]) for i in range(returned.value)] if outs is not None else []

    def read(self, address: int) -> int:
        return self.call("ioctl_it5570_i2ec_read", [address], 1)[0] & 0xFF

    def write_verified(self, address: int, value: int) -> dict:
        before = self.read(address)
        self.call("ioctl_it5570_i2ec_write", [address, value & 0xFF])
        after = self.read(address)
        if after != (value & 0xFF):
            raise RuntimeError(f"I2EC readback mismatch: before={before:#x} target={value:#x} after={after:#x}")
        return {"address": hex(address), "before": before, "target": value & 0xFF, "after": after}

    def close(self):
        if getattr(self, "handle", None):
            self.lib.pawnio_close_win32(self.handle)
            self.handle = None

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--library", type=Path, required=True)
    p.add_argument("--module", type=Path, required=True)
    p.add_argument("--address", type=lambda x: int(x, 0), action="append", default=[0x200D, 0x1604])
    p.add_argument("--write-gpd0", action="store_true")
    p.add_argument("--hold-seconds", type=float, default=0.0)
    a = p.parse_args()
    with I2ECAdapter(a.library, a.module) as ec:
        samples = [{"address": hex(x), "value": ec.read(x)} for x in a.address]
        result = {"samples": samples, "write": None, "verified_write": False}
        if a.write_gpd0:
            ctrl = ec.read(0x200D)
            if (ctrl & 3) != 3:
                raise RuntimeError(f"I2EC is not read-write: SPCTRL1={ctrl:#x}")
            old = ec.read(0x1604)
            result["write"] = ec.write_verified(0x1604, old | 1)
            result["verified_write"] = True
            if a.hold_seconds:
                time.sleep(a.hold_seconds)
            result["restore"] = ec.write_verified(0x1604, old)
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
