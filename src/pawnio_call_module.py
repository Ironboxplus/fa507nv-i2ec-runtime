#!/usr/bin/env python3
import argparse
import ctypes
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser()
    p.add_argument("--module", type=Path, required=True)
    p.add_argument("--library", type=Path, default=root / "pawnio-runtime" / "PawnIOLib.dll")
    p.add_argument("--function", required=True)
    p.add_argument("--input", type=lambda x: int(x, 0), action="append", default=[])
    p.add_argument("--out-count", type=int, default=8)
    a = p.parse_args()
    lib = ctypes.WinDLL(str(a.library), use_last_error=True)
    H=ctypes.c_void_p; U=ctypes.c_uint64; S=ctypes.c_size_t
    lib.pawnio_open_win32.argtypes=[ctypes.POINTER(H)]; lib.pawnio_open_win32.restype=ctypes.c_bool
    lib.pawnio_load_win32.argtypes=[H,ctypes.c_void_p,S]; lib.pawnio_load_win32.restype=ctypes.c_bool
    lib.pawnio_execute_win32.argtypes=[H,ctypes.c_char_p,ctypes.POINTER(U),S,ctypes.POINTER(U),S,ctypes.POINTER(S)]; lib.pawnio_execute_win32.restype=ctypes.c_bool
    lib.pawnio_close_win32.argtypes=[H]; lib.pawnio_close_win32.restype=ctypes.c_bool
    blob=a.module.read_bytes(); buf=(ctypes.c_ubyte*len(blob)).from_buffer_copy(blob); h=H()
    if not lib.pawnio_open_win32(ctypes.byref(h)): raise OSError(ctypes.get_last_error(),'open')
    try:
        if not lib.pawnio_load_win32(h,buf,len(blob)): raise OSError(ctypes.get_last_error(),'load')
        ins=(U*len(a.input))(*a.input) if a.input else None; outs=(U*a.out_count)(); ret=S()
        ok=lib.pawnio_execute_win32(h,a.function.encode(),ins,len(a.input),outs,a.out_count,ctypes.byref(ret))
        if not ok: raise OSError(ctypes.get_last_error(),a.function)
        print(json.dumps({'function':a.function,'output':[int(outs[i]) for i in range(ret.value)]},sort_keys=True))
    finally:
        lib.pawnio_close_win32(h)

if __name__=='__main__': main()
