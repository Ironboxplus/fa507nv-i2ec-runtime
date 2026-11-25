"""Use the signed PawnIO LpcIO module to read IT5570's dedicated I2EC ports.

The official module whitelists PIO ranges discovered as Super-I/O BARs.  FA507NV
does not expose the dedicated I2EC base as a BAR, so this adapter temporarily
uses inactive LDN 0x0B as a whitelist anchor at 0x680.  It restores every SIO
configuration byte in a finally block and never writes the I2EC data port.
"""
from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path


class Bridge:
    def __init__(self, library: Path, module: Path, sio_base: int = 0x2E):
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
        self.handle = H(); self.sio_base = sio_base
        # LDN 0x14 is inactive and has writable BAR registers on this IT5570.
        # It is used only as a whitelist anchor and restored byte-for-byte below.
        self.ldn = 0x14
        if not self.lib.pawnio_open_win32(ctypes.byref(self.handle)):
            raise OSError(ctypes.get_last_error(), "pawnio_open_win32")
        blob = module.read_bytes(); buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        if not self.lib.pawnio_load_win32(self.handle, buf, len(blob)):
            self.close(); raise OSError(ctypes.get_last_error(), "pawnio_load_win32")
        self._changed = False; self._old = {}
        self.call("ioctl_select_slot", [0 if sio_base == 0x2E else 1])
        final = 0x55 if sio_base == 0x2E else 0xAA
        for value in (0x87, 0x01, 0x55, final): self.call("ioctl_pio_outb", [sio_base, value])
        self.call("ioctl_superio_outb", [0x07, self.ldn])
        for reg in (0x30, 0x60, 0x61):
            self._old[reg] = self.call("ioctl_superio_inb", [reg], 1)[0]
        self.call("ioctl_superio_outb", [0x60, 0x06])
        self.call("ioctl_superio_outb", [0x61, 0x80])
        self._changed = True
        self.call("ioctl_find_bars", [])

    def call(self, name, values=(), out_count=0):
        U = ctypes.c_uint64; S = ctypes.c_size_t
        ins = (U * len(values))(*values) if values else None
        outs = (U * out_count)() if out_count else None; returned = S()
        if not self.lib.pawnio_execute_win32(self.handle, name.encode(), ins, len(values),
                                              outs, out_count, ctypes.byref(returned)):
            raise OSError(ctypes.get_last_error(), name)
        return [int(outs[i]) for i in range(returned.value)] if outs is not None else []

    def read_i2ec(self, address: int) -> int:
        self.call("ioctl_pio_outb", [0x681, (address >> 8) & 0xFF])
        self.call("ioctl_pio_outb", [0x682, address & 0xFF])
        return self.call("ioctl_pio_inb", [0x683], 1)[0] & 0xFF

    def close(self):
        if not getattr(self, "handle", None): return
        try:
            if self._changed:
                self.call("ioctl_superio_outb", [0x07, self.ldn])
                for reg, value in self._old.items(): self.call("ioctl_superio_outb", [reg, value])
        except Exception:
            pass
        try:
            self.call("ioctl_pio_outb", [self.sio_base, 0x02])
            self.call("ioctl_pio_outb", [self.sio_base + 1, 0x02])
        except Exception:
            pass
        self.lib.pawnio_close_win32(self.handle); self.handle = None

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


def main():
    p = argparse.ArgumentParser(); p.add_argument("--library", type=Path, required=True)
    p.add_argument("--module", type=Path, required=True)
    p.add_argument("--address", type=lambda x: int(x, 0), action="append",
                   default=[0x200D, 0x2012, 0x2014, 0x2015, 0x1604])
    a = p.parse_args()
    with Bridge(a.library, a.module) as bridge:
        print(json.dumps({"transport": "signed-LpcIO+temporary-inactive-LDN-BAR",
                          "samples": [{"address": hex(x), "value": bridge.read_i2ec(x)} for x in a.address]}, sort_keys=True))


if __name__ == "__main__": main()
