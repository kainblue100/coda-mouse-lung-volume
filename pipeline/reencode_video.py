"""Re-encode the turntables for maximum playback compatibility.

The first mp4s were written by imageio and did not open in the local player.
Windows 10 N ships without the H.264 decoder, so we produce a baseline-profile
yuv420p mp4 (faststart) plus a VP9 webm, both of which open in Chrome/Edge
without a system codec, and keep the GIF as the last resort.
"""
import os
import subprocess

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SRC = r"D:\coda_matlab\lungs_150\three_d"
OUT = r"D:\coda_matlab\lungs_150\video_out"
os.makedirs(OUT, exist_ok=True)

JOBS = [
    ("V150iso_turntable.mp4", "new-turntable"),
    ("V150_turntable.mp4", "old-turntable"),
]


def probe(path):
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", path],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in p.stderr.splitlines():
        s = line.strip()
        if s.startswith("Stream") or s.startswith("Duration"):
            print("   ", s)
    return p.stderr


def run(args):
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print("    ffmpeg failed:", p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "?")
    return p.returncode == 0


for src_name, stem in JOBS:
    src = os.path.join(SRC, src_name)
    if not os.path.isfile(src):
        print("missing", src, flush=True)
        continue

    print(f"\n{src_name}", flush=True)
    probe(src)

    mp4 = os.path.join(OUT, stem + "-h264.mp4")
    ok = run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
              "-i", src,
              "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
              "-pix_fmt", "yuv420p", "-crf", "20",
              "-movflags", "+faststart",
              "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
              mp4])
    if ok:
        print(f"    h264  {os.path.getsize(mp4)/1e6:.2f} MB  {os.path.basename(mp4)}")

    webm = os.path.join(OUT, stem + ".webm")
    ok = run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
              "-i", src,
              "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0",
              "-pix_fmt", "yuv420p",
              "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
              webm])
    if ok:
        print(f"    vp9   {os.path.getsize(webm)/1e6:.2f} MB  {os.path.basename(webm)}")

print("\nsource gifs copied for reference")
import shutil
for g in ("V150iso_turntable.gif", "V150_turntable.gif"):
    s = os.path.join(SRC, g)
    if os.path.isfile(s):
        shutil.copy2(s, os.path.join(OUT, g))
        print(f"    {g}  {os.path.getsize(os.path.join(OUT, g))/1e6:.2f} MB")

print("\nDONE")
