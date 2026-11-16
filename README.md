# CODA mouse lung: 150 serial sections to a 3D volume

The original CODA histology pipeline (Kiemen et al., *Nature Methods* 2022) run end to end on
all 150 serial sections of the mouse lung dataset, plus the rendering work needed to make the
result readable.

**Live page:** https://kainblue100.github.io/coda-mouse-lung-volume/

> This repo is separate from `coda-mouse-lung-3d`, which is an earlier version of
> this project built from Blender mesh renders. This one carries the corrected
> volume renders, the rendering fix, and the provenance table.

## What this is

Every voxel in the volume is the classifier's output on a real section. Nothing is synthetic,
nothing is an atlas, and no anatomy was drawn by hand.

| | |
|---|---|
| sections | 150, spaced 10 µm |
| classification | 1 µm/px, 1000 px tiles |
| volume grid | 2983 × 2497 × 150 = 1,117,282,650 voxels |
| voxel | 4 × 4 × 10 µm |
| physical size | 11.93 × 9.99 × 1.50 mm |
| volume | 0.1788 cm³ |
| share of a mouse lung | 13.8 % (reference lung = 1.3 cm³) |

## Pipeline

| stage | CODA section | what happens | result |
|---|---|---|---|
| 1 | Section 3 | tissue masks, then global + elastic registration between consecutive sections | 150 masks, 150 warps, 150 deform fields |
| 2 | Section 4 | DeepLabv3+ / ResNet-50, 8 epochs, weighted pixel loss | `net.mat`, 143 MB, validation loss 0.02596 |
| 3 | Section 4.5 | classify all 150 slices | 87 min, ≈ 30 s per slice |
| 4 | Section 5 | scale the warps by 10 and apply them to the classified images | 150 / 150 warped |
| 5 | Section 6 | downsample in plane by 4, crop to tissue, stack | `volume.mat`, 59 MB |

Parameters are the tutorial's own: `ds=[1 2 10]`, `umpix=1`, `sxy=1000`, `ntrain=15`,
`scale=10`, `sk=4`, `nwhite=6`.

## Class composition

Converted with the true voxel volume, 0.004 × 0.004 × 0.010 mm³.

| class | voxels | mm³ | share |
|---|---:|---:|---:|
| alveoli | 115,941,596 | 18.551 | 10.4 % |
| vasculature | 1,424,078 | 0.228 | 0.13 % |
| bronchioles | 2,088,352 | 0.334 | 0.19 % |
| stroma | 9,317,596 | 1.491 | 0.83 % |
| nonexpanded | 8,122,270 | 1.300 | 0.73 % |
| cancer | 141,801 | 0.023 | 0.013 % |
| background | 980,246,957 | 156.840 | 87.7 % |
| **total** | **1,117,282,650** | **178.766** | **100 %** |

## Provenance

Everything in the renders is classifier output on the real sections. That is not obvious from
looking at the images, and two things that are not measurements can easily be read as if they
were.

| Element in the render | Where it comes from | Status |
|---|---|---|
| Vasculature (magenta) | Class 3, classifier output on the 150 sections | data |
| Bronchioles (amber) | Class 1, same source | data |
| Alveoli, stroma, nonexpanded, cancer, background | Classes 2, 7, 5, 4, 6 | data |
| Outer silhouette | The tissue mask of each individual section | data |
| 1.5 mm thickness | 150 sections at their real 10 µm spacing | data |
| Apparent calibre of vessels and airways | Widened by the renderer's emission. The labelled structures are 1 to 2 voxels thick in the data, so the rendered width is not a diameter | presentation |
| Colour, glow strength, opacity | Display parameters chosen by hand | presentation |
| 590,000 removed voxels | Despeckle filter on isolated components below 250 voxels | processing |
| 12 µm in-plane grid | Display resampling, smoother than the raw 4 µm grid | processing |
| Anatomy that is not the specimen | None appears in any render here | excluded |

### Deliberately kept out

Three assets in this project are not the specimen and would be misleading inside a
reconstruction. None of them is used in any render above.

- `LUNG_anatomical.glb` is a human lung from the BodyParts3D atlas. Wrong species.
- `MOUSE_lung.glb` is a set of procedural lobes built from sphere primitives. The shape is
  invented rather than imaged.
- `lapd_m07/` is the lapdMouse archive of a different mouse, a C57BL/6 male of 24.1 g, with its
  own airway tree. It can be compared against this reconstruction but not merged into it.

If any of those appear in a figure beside this volume, they need a label saying which one is
the measurement and which is a reference.

## The rendering bug

Both renders in the comparison are the same volume. The difference is how the renderer mapped
it into space.

The data is 11.93 × 9.99 × 1.50 mm, but the renderer mapped each axis onto `[-0.5, 0.5]`
independently. That stretches z by about eight times, turning a 1.5 mm slab into a block. The
150 sections became visible edges, which is what read as a stack of plates.

Five defects, in order of impact:

1. **Aspect ratio destroyed by normalisation.** Each axis must carry its share of the largest
   physical dimension before converting back to voxel indices. This was the dominant artefact.
2. **The camera was inside the volume.** Normalising a per-pixel vector to get the ray
   direction makes every ray diverge from the origin, which sits inside the data. The first
   render was a starburst.
3. **In-plane sampling coarser than z.** Downsampling xy four times to 16 µm while resampling z
   to 4 µm is anisotropy in the opposite direction to the data's own.
4. **Parenchyma emission too high.** A ray crosses about 700 steps, so a small per-step value
   accumulates into a white haze. Emission is now near zero on the parenchyma classes and
   absorption carries the structure.
5. **Single-voxel specks.** Isolated one-voxel islands of every class become hundreds of
   coloured dots in the black. Connected-component filtering below 250 voxels removed about
   590,000 of them.

Scored by an image critic: smoothness **4/10 → 8/10**, structure clarity **8/10**.

### What remains

A faint corduroy texture on the finer branches, scored 6/10 on the oblique view. That is the
10 µm between-section spacing showing through. The sections are the true sampling limit in z,
and no amount of interpolation invents detail that was never imaged.

## The honest limit

150 sections at 10 µm is 1.5 mm of tissue. A mouse lung is roughly 10 to 20 mm long and about
1.3 cm³, so this is close to 14 % of the organ by volume. The result therefore reads as a
tissue block containing a bronchovascular tree, not as an anatomically recognisable lung. A
whole-lung silhouette would need several hundred more sections.

## Reproducing

```bash
# server: bzhang@10.13.8.200, /home/bzhang/Kludt/coda3d_run
export CUDA_VISIBLE_DEVICES=1
export LD_LIBRARY_PATH=/home/bzhang/Kludt/cuda-compat-13-4:$LD_LIBRARY_PATH

matlab -batch s_sec4_gpu          # train + test
matlab -batch s_sec45_classify    # classify all 150
matlab -batch s_sec56             # registration + volume
```

GPU access needs no root and no reboot. The CUDA forward-compatibility userspace libraries on
`LD_LIBRARY_PATH` are enough for MATLAB R2026b to see the RTX 4090, which cut training from
19.2 s to 1.14 s per iteration. `train_deeplab_r2026b.m` is the R2026b port of CODA's
`train_deeplab.m`, since `deeplabv3plusLayers`, `replaceLayer` and `countEachLabel` no longer
exist.

## Repository layout

```
index.html                     the page
assets/new/                    corrected renders, with the provenance band
assets/old/                    earlier renders, kept for comparison
assets/video/                  turntables, mp4 with gif fallback
pipeline/render_volume.py      the volume ray marcher (aspect-corrected)
pipeline/read_volume_mat.py    reads volume.mat directly, MATLAB v5 container
pipeline/add_provenance_band.py  burns the provenance band onto a render
pipeline/reencode_video.py     re-encodes the turntables for compatibility
```

The MATLAB stages (`s_sec3.m`, `s_sec4_gpu.m`, `s_sec45_classify.m`, `s_sec56.m`) live with the
server run rather than here; the commands are in the section above.

## Credits

CODA pipeline: Kiemen, Braxton, Grahn, Han, Babu, Reichel, Jiang, Bakker, Liu, van der Heijden,
Eastwood, Wang, Chen, Maley, Lai, Weimer, Hong, Wood, Hruban, Wu. *Nature Methods* 2022.
