"""Isotropic re-render: kills the stepped "stack of slices" look.

The volume is anisotropic - 4 x 4 um in plane but 10 um between sections - so
sampling it directly terraces along z. This resamples z to 4 um (150 -> 375
planes) and smooths each class mask before compositing, which is what removes
the layering.

Smoothing has to happen on the per-class masks, not on the label volume: the
labels are categorical, so interpolating them directly would invent class ids
that mean nothing. Instead each class contributes to five continuous fields
(R, G, B, emission, absorption) and those are what get interpolated.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

NPY = r"D:\coda_matlab\lungs_150\lung_data\vol.npy"
OUT = r"D:\coda_matlab\lungs_150\three_d"
os.makedirs(OUT, exist_ok=True)

RGB = np.array([
    [0.00, 0.00, 0.00],
    [1.00, 0.62, 0.16],   # 1 bronchioles  amber
    [0.28, 0.48, 0.95],   # 2 alveoli      faint blue haze
    [1.00, 0.14, 0.32],   # 3 vasculature  magenta/red
    [1.00, 0.97, 0.35],   # 4 cancer       yellow
    [0.14, 0.58, 0.62],   # 5 nonexpanded  teal
    [0.00, 0.00, 0.00],   # 6 background
    [0.76, 0.28, 0.82],   # 7 stroma       violet
], dtype=np.float32)

EM = np.array([0.0, 2.10, 0.0040, 2.55, 3.00, 0.020, 0.0, 0.020], dtype=np.float32)
AB = np.array([0.0, 0.135, 0.0030, 0.200, 0.210, 0.006, 0.0, 0.006], dtype=np.float32)

DZ_UP = 1.0          # keep the 150 planes; z voxel is 10 um
MAX_XY = 1000        # xy step 3 -> ~12 um in plane against 10 um in z, so the
                     # voxels are near-isotropic (1.2x). Going finer (step 2)
                     # is correct in theory but 279M voxels x 7 classes of
                     # despeckle and blur simply does not fit this box: the
                     # process spent 10 minutes wall clock for 80 s of CPU,
                     # i.e. thrashing. The aspect fix below is what actually
                     # removes the stacked-plate look, not the voxel size.


def load_xy_downsampled(max_xy=MAX_XY):
    v = np.load(NPY, mmap_mode="r")
    print("volume", v.shape, v.dtype, flush=True)
    sx = max(1, int(np.ceil(v.shape[0] / max_xy)))
    sy = max(1, int(np.ceil(v.shape[1] / max_xy)))
    a = np.asarray(v)
    if sx > 1 or sy > 1:
        a = a[::sx, ::sy, :]
    a = np.ascontiguousarray(a.transpose(2, 0, 1))     # (Z, Y, X)
    print(f"  xy step ({sx},{sy}) -> {a.shape}", flush=True)
    return a, sx, sy


def despeckle(a, min_vox=250):
    out = a.copy()
    for lab in range(1, 8):
        m = (a == lab)
        if not m.any():
            continue
        cc, k = ndimage.label(m, structure=np.ones((3, 3, 3), dtype=np.uint8))
        if k <= 1:
            continue
        sizes = np.bincount(cc.ravel())
        bad = np.flatnonzero(sizes < min_vox)
        bad = bad[bad != 0]
        if bad.size == 0:
            continue
        small = np.isin(cc, bad) & m
        out[small] = 6
        print(f"  despeckle {lab}: {k} comps, -{int(small.sum()):,} vox", flush=True)
    return out


def build_fields(a, dz_up=DZ_UP, blur=(0.90, 0.75, 0.75)):
    """(5, Z', Y, X) float16: R, G, B, emission, absorption, isotropic in z.

    float16 because the box only has 11.9 GB of RAM; a float32 version of these
    five fields is 6.2 GB and pushes the machine into swap.

    The z blur is deliberately larger than the in-plane blur. The sections are
    10 um apart but the reconstruction claims 4 um, so the z axis carries less
    independent information; without extra smoothing the duplicated planes show
    up as a comb of fine striations along every branch.
    """
    z, y, x = a.shape
    nz = int(round(z * dz_up))
    F = np.zeros((5, nz, y, x), dtype=np.float16)
    print(f"fields {nz} x {y} x {x}  {F.nbytes/1e9:.2f} GB (float16)", flush=True)
    zf = (nz - 1) / max(z - 1, 1)

    for lab in range(1, 8):
        m = (a == lab)
        n = int(m.sum())
        if n == 0 or (EM[lab] == 0 and AB[lab] == 0):
            continue
        # nearest-neighbour z duplication then blur: the blur is what actually
        # removes the terracing, and it is much cheaper than an order-1 zoom
        zw = np.arange(nz) / zf
        zi = np.clip(np.round(zw).astype(np.int32), 0, z - 1)
        mz = np.ascontiguousarray(m[zi]).astype(np.float32)
        del m
        mz = ndimage.gaussian_filter(mz, sigma=blur, mode="nearest")
        F[0] += (mz * (RGB[lab, 0] * EM[lab])).astype(np.float16)
        F[1] += (mz * (RGB[lab, 1] * EM[lab])).astype(np.float16)
        F[2] += (mz * (RGB[lab, 2] * EM[lab])).astype(np.float16)
        F[3] += (mz * EM[lab]).astype(np.float16)
        F[4] += (mz * AB[lab]).astype(np.float16)
        print(f"  class {lab}: {n:,} vox -> z{nz}, peak {float(mz.max()):.3f}", flush=True)
        del mz
    return F


def rot_y(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float32)


def rot_x(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float32)


def raymarch(F, size=900, angle=0.6, elev=0.25, zoom=1.0, nsteps=700,
             phys=(11.932, 9.988, 1.500)):
    """Parallel projection, with the physical aspect ratio preserved.

    The volume is 11.93 x 9.99 x 1.50 mm, so normalising each axis to [-0.5,0.5]
    on its own stretches z by ~8x and turns the 150 sections into a visible stack
    of plates. Each axis is therefore scaled by its share of the largest physical
    dimension before the voxel lookup.
    """
    _, z, h, w = F.shape
    extent = np.array(phys, dtype=np.float32)
    A = extent / extent.max()                        # (Ax, Ay, Az), max = 1

    t0, t1 = -1.45, 1.45
    step = (t1 - t0) / nsteps

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    px = (xx / (size - 1) * 2 - 1) * 0.5 / zoom
    py = -(yy / (size - 1) * 2 - 1) * 0.5 / zoom
    P = np.stack([px, py, np.zeros_like(px)], -1)

    R = rot_x(elev) @ rot_y(angle)
    origin = P @ R.T
    viewdir = (R @ np.array([0.0, 0.0, 1.0], dtype=np.float32)).astype(np.float32)

    acc = np.zeros((size, size, 3), dtype=np.float32)
    trans = np.ones((size, size), dtype=np.float32)

    for i in range(nsteps):
        pos = origin + viewdir * (t0 + i * step)
        # undo the aspect scaling when converting back to voxel indices
        gx = ((pos[..., 0] / A[0] + 0.5) * w).astype(np.int32)
        gy = ((pos[..., 1] / A[1] + 0.5) * h).astype(np.int32)
        gz = ((pos[..., 2] / A[2] + 0.5) * z).astype(np.int32)
        ok = (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h) & (gz >= 0) & (gz < z)
        if not ok.any():
            continue
        np.clip(gx, 0, w - 1, out=gx)
        np.clip(gy, 0, h - 1, out=gy)
        np.clip(gz, 0, z - 1, out=gz)
        g = (gz, gy, gx)
        rgb = np.stack([F[0][g], F[1][g], F[2][g]], -1)
        ab = F[4][g]
        rgb = np.where(ok[..., None], rgb, 0.0)
        ab = np.where(ok, ab, 0.0)
        acc += trans[..., None] * rgb
        trans *= (1.0 - np.clip(ab, 0.0, 1.0))

    out = np.clip(acc, 0, None)
    out = out / (1.0 + out)
    out = np.clip(out ** (1 / 2.2), 0, 1)
    return (out * 255).astype(np.uint8)


def label(img, text, sub=None):
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    W = im.width
    fd = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    try:
        f = ImageFont.truetype(os.path.join(fd, "segoeuib.ttf"), max(17, W // 36))
        f2 = ImageFont.truetype(os.path.join(fd, "segoeui.ttf"), max(13, W // 52))
    except Exception:
        f = f2 = ImageFont.load_default()
    x0, y0 = int(W * 0.035), int(W * 0.032)
    d.text((x0, y0), text, font=f, fill=(240, 244, 250))
    if sub:
        d.text((x0, y0 + int(W * 0.05)), sub, font=f2, fill=(150, 162, 178))
    return im


def fields_cached(a):
    """Cache the composited fields; building them costs ~10 minutes."""
    import hashlib
    key = hashlib.md5(f"{a.shape}{a.dtype}{MAX_XY}{DZ_UP}{blur_sig()}".encode()).hexdigest()[:12]
    p = os.path.join(os.path.dirname(NPY), f"fields_{key}.npy")
    if os.path.exists(p):
        print("loading cached fields", p, flush=True)
        return np.load(p, mmap_mode="r")
    F = build_fields(a)
    np.save(p, F)
    print("cached fields ->", p, flush=True)
    return F


def blur_sig():
    import inspect
    return "1.0"   # bump when build_fields' blur changes


def main():
    a, sx, sy = load_xy_downsampled()
    print("despeckling", flush=True)
    a = despeckle(a)
    F = fields_cached(a)
    del a
    vol_mm = (2983 * 0.004, 2497 * 0.004, 150 * 0.010)
    SUB = (f"150 serial sections  |  {vol_mm[0]:.2f} x {vol_mm[1]:.2f} x {vol_mm[2]:.2f} mm"
           f"  |  12 um in plane x 10 um between sections  |  0.179 cm3")

    # a true 90-degree side view of a 1.5 mm slab is an empty sliver, so the
    # third view is a raised oblique that still shows the full footprint
    views = [("hero", 0.65, 0.30, 1.00), ("front", 0.00, 0.10, 1.05),
             ("oblique", 1.05, 0.42, 1.45), ("top", 0.90, 1.05, 1.00)]
    for name, ang, el, zm in views:
        print("render", name, flush=True)
        img = raymarch(F, size=1000, angle=ang, elev=el, zoom=zm, nsteps=700)
        label(img, "CODA mouse lung", SUB).save(os.path.join(OUT, f"V150iso_{name}.png"))
        print("  saved", name, flush=True)

    print("turntable", flush=True)
    frames = []
    N = 40
    for i in range(N):
        ang = 2 * np.pi * i / N
        f = raymarch(F, size=640, angle=ang, elev=0.26, zoom=1.0, nsteps=420)
        frames.append(label(f, "CODA mouse lung", None))
        sys.stdout.write("."); sys.stdout.flush()
    print(flush=True)
    import imageio.v2 as iio
    iio.mimsave(os.path.join(OUT, "V150iso_turntable.mp4"), frames, fps=20, quality=8)
    frames[0].save(os.path.join(OUT, "V150iso_turntable.gif"), save_all=True,
                   append_images=frames[1:], duration=60, loop=0)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
