"""Extract the vol array from the MATLAB v5 .mat.

The file is a chain of miCOMPRESSED elements; the last one is the 1.1e9-element
label volume. Inflate it, walk the miMATRIX sub-elements, and save a plain
uint8 .npy so everything downstream can memory-map instead of re-parsing.
"""
import os
import struct
import zlib

import numpy as np

SRC = r"D:\coda_matlab\lungs_150\lung_data\volume.mat"
OUT = r"D:\coda_matlab\lungs_150\lung_data\vol.npy"

MI_DT = {1: "i1", 2: "u1", 3: "</i2", 4: "</u2", 5: "</i4", 6: "</u4",
         7: "</f4", 9: "</f8", 12: "</i8", 13: "</u8"}
MI_NAME = {1: "int8", 2: "uint8", 3: "int16", 4: "uint16", 5: "int32",
           6: "uint32", 7: "single", 9: "double", 12: "int64", 13: "uint64",
           14: "matrix", 15: "compressed", 16: "utf8"}


def tag(buf, off):
    t = struct.unpack_from("<I", buf, off)[0]
    small = (t >> 16) & 0xFFFF
    typ = t & 0xFFFF
    if small:
        return typ, small, off + 8, True
    n = struct.unpack_from("<I", buf, off + 4)[0]
    return typ, n, off + 8, False


def pad8(n):
    return (8 - (n % 8)) % 8


def advance(base_off, n, small):
    """Offset of the next sub-element.

    A small-data-element occupies 8 bytes total (the tag with the inline size
    plus up to 4 bytes of data); only a regular element pays the 8-byte padding.
    """
    if small:
        return base_off + 8
    return base_off + 8 + n + pad8(n)


def parse_matrix(raw, off):
    """off = index of the first sub-element inside a miMATRIX."""
    # array flags: tag + 8 bytes
    t, n, d, small = tag(raw, off)
    cls = raw[d]
    off = advance(off, n, small)
    # dimensions
    t, n, d, small = tag(raw, off)
    dims = np.frombuffer(raw, dtype="<i4", count=n // 4, offset=d)
    off = advance(off, n, small)
    # name
    t, n, d, small = tag(raw, off)
    if small:
        name = bytes(raw[d - 4:d]).rstrip(b"\x00")
    else:
        name = bytes(raw[d:d + n]).rstrip(b"\x00")
    off = advance(off, n, small)
    # real part
    t, n, d, small = tag(raw, off)
    if t not in MI_DT:
        raise SystemExit(f"unexpected data type {t} ({MI_NAME.get(t, t)})")
    dt = np.dtype(MI_DT[t])
    count = n // dt.itemsize
    arr = np.frombuffer(raw, dtype=dt, count=count, offset=d)
    arr = arr.reshape(tuple(int(x) for x in dims), order="F")
    return cls, tuple(int(x) for x in dims), name, arr, t


def main():
    size = os.path.getsize(SRC)
    print(f"{SRC}  {size/1e6:.1f} MB")
    with open(SRC, "rb") as f:
        f.read(128)
        body = f.read()

    off, idx = 0, 0
    payload = None
    while off + 8 <= len(body):
        t, n, d, small = tag(body, off)
        if t == 15 and n > 10_000_000:
            print(f"element [{idx}] off={off} compressed={n:,} -> inflating", flush=True)
            payload = zlib.decompress(body[d:d + n])
            print(f"  inflated {len(payload):,} bytes", flush=True)
            break
        off += 8 + n
        idx += 1

    if payload is None:
        raise SystemExit("big element not found")

    # payload starts with a miMATRIX element
    t, n, d, small = tag(payload, 0)
    print(f"element type {MI_NAME.get(t, t)} size={n:,}")
    inner = d if not small else d - 8
    cls, dims, name, arr, dt = parse_matrix(payload, inner)
    print(f"class={cls} ({MI_NAME.get(cls, cls)}) dims={dims} name={name!r} dtype={MI_NAME.get(dt)}")
    print(f"nbytes={arr.nbytes:,}")

    vals, counts = np.unique(arr, return_counts=True)
    print("labels:", list(zip(vals.tolist(), counts.tolist())))

    np.save(OUT, arr)
    print(f"wrote {OUT}  {os.path.getsize(OUT)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
