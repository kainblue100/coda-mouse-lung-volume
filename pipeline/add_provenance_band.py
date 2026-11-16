"""Burn a provenance band onto each rendered still.

The renders contain nothing but classifier output on the 150 real sections, but
that is not obvious from looking at them, and several things that ARE
presentation choices (apparent vessel calibre, colour, despeckling) can be
mistaken for measurements. This adds the provenance line so the figure cannot be
read as claiming more than the data supports.
"""
import os

from PIL import Image, ImageDraw, ImageFont

SRC = r"D:\coda_matlab\lungs_150\three_d"
OUT = r"D:\coda_matlab\coda-mouse-lung-3d\assets\new"
os.makedirs(OUT, exist_ok=True)

VIEWS = ["hero", "front", "oblique", "top"]

BG = (12, 10, 13)
FG = (242, 238, 244)
DIM = (138, 128, 145)
VESSEL = (255, 47, 94)
AIRWAY = (242, 160, 60)


def font(size, bold=False, mono=False):
    fd = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    names = []
    if mono:
        names = ["segoeui.ttf", "consola.ttf", "arial.ttf"]
    elif bold:
        names = ["segoeuib.ttf", "arialbd.ttf"]
    else:
        names = ["segoeui.ttf", "arial.ttf"]
    for n in names:
        p = os.path.join(fd, n)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def band(width):
    """Build the provenance band and return it as an image."""
    pad = int(width * 0.035)
    f_h = font(max(15, width // 58), bold=True)
    f_b = font(max(13, width // 74))
    f_m = font(max(12, width // 86), mono=True)

    lines = [
        ("From the slice data", FG, f_h),
        ("All 7 classes are classifier output on the 150 real serial sections, at their true 10 um spacing.", DIM, f_b),
        ("Nothing here is an atlas, a template, an interpolation, or drawn by hand.", DIM, f_b),
        ("Magenta = vasculature.  Amber = bronchioles.  Blue haze = alveoli.  The outline is the section tissue.", DIM, f_b),
        ("", DIM, f_b),
        ("Presentation only, not a measurement", FG, f_h),
        ("Apparent vessel and airway calibre is widened by the renderer's emission. In the data these", DIM, f_b),
        ("structures are 1 to 2 voxels thick, so their rendered width is not a measured diameter.", DIM, f_b),
        ("Colour, glow and opacity are display choices. Despeckling removed 590k isolated voxels.", DIM, f_b),
        ("Display grid is 12 um in plane; the section spacing itself is untouched at 10 um.", DIM, f_b),
        ("", DIM, f_b),
        ("Not in this image", FG, f_h),
        ("No reference anatomy and no other specimen. Those exist elsewhere in the project and are", DIM, f_b),
        ("excluded from every render here: BodyParts3D is a human atlas, MOUSE_lung.glb is procedural,", DIM, f_b),
        ("and lapdMouse m07 is a different animal.", DIM, f_b),
    ]

    h = pad
    for txt, _, ft in lines:
        h += (ft.size + 10) if txt else int(ft.size * 0.7)
    h += pad * 2                      # extra bottom room for descenders

    im = Image.new("RGB", (width, h), BG)
    d = ImageDraw.Draw(im)
    d.line([(0, 0), (width, 0)], fill=(58, 50, 64), width=2)

    y = pad
    for txt, col, ft in lines:
        if txt:
            d.text((pad, y), txt, font=ft, fill=col)
            y += ft.size + 10
        else:
            y += int(ft.size * 0.7)
    return im


for v in VIEWS:
    p = os.path.join(SRC, f"V150iso_{v}.png")
    if not os.path.isfile(p):
        print("missing", p, flush=True)
        continue
    img = Image.open(p).convert("RGB")
    b = band(img.width)
    out = Image.new("RGB", (img.width, img.height + b.height), BG)
    out.paste(img, (0, 0))
    out.paste(b, (0, img.height))
    dst = os.path.join(OUT, f"{v}.png")
    out.save(dst, optimize=True)
    print(f"{v}: {img.size} -> {out.size}  {os.path.getsize(dst)/1e6:.2f} MB", flush=True)

print("DONE")
