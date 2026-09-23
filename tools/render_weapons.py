#!/usr/bin/env python3
"""Render the first-person weapon cels from 3D models, straight at the
console's resolution.

    python tools/render_weapons.py                 # preview sheets under build/weapon-art/
    python tools/render_weapons.py --write         # write the native PNGs and their manifest records
    python tools/render_weapons.py --check         # the committed sheets equal a fresh render

Offline authoring, never called by a ROM build: the build compiles the
committed indexed PNGs under `assets/sable_v2/native/` through
`sprite_assets`, exactly as it does the enemy and HUD art.

The technique is the one 3D-to-pixel-art pipelines use, fitted to the
weapon's OBJ budget (`docs/ART_PIPELINE.md`, "Weapons are rendered from
models"):

- Each weapon is a handful of signed-distance primitives in gun space
  (+z along the barrel, +y up, +x to the gun's right): tubes, rounded
  boxes, ellipsoids for the gloved hands. Parts carry a material and a
  name, and the parts of the action (pump, bolt, capacitor rings, shutter)
  move with the animation, so the cels are posed from one model.
- The camera is the view's own eye with a viewmodel field of view: a long
  focal length and a distant gun, as first-person games draw their held
  weapon, so the gun keeps its shape instead of ballooning near the eye.
  Every pose is solved from where the receiver's rear and the muzzle land
  on screen; the muzzle sits under the flash object.
- Each pixel is decided at the target resolution from 4x4 samples: the
  majority part, its averaged normal and nearest depth. Shading is three
  bands per material from one key light, with a specular glint on metal.
- Ink is drawn on the silhouette's own edge and on the farther side of
  every boundary between differently named parts, which is what makes a
  pump read as a pump at forty pixels.
- The weapon is fitted to OBJ palette 0 (ink, steel, highlight) for every
  object. A sprite takes one palette, so a second colour could only show in
  whole 8x16 blocks that do not follow a diagonal, sliding part; the fit
  still records a palette per object (`object_palettes`) so a later weapon
  whose second material fills whole objects can use one.

The window is 40x32 pixels at world x 68..107, y 88..119 on the slim
display: five 8x16 objects across and two down, four cels (idle, the kick,
the action back, the action returning). Recovery is the idle cel.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "assets" / "sable_v2" / "native"
MANIFEST = ROOT / "assets" / "sable_v2" / "assets.json"

WEAPONS = ("shotgun", "slug_rifle", "arc_lance", "pulse_carbine")
FRAMES = ["idle", "recoil", "action_back", "action_forward"]
TICKS = [0, 4, 6, 6]
WIDTH, HEIGHT = 40, 32
WINDOW = (68, 88, WIDTH, HEIGHT)        # world pixels on the 160x120 slim view
OBJECT_W, OBJECT_H = 8, 16

CX, CY = 80.0, 60.0                      # the view's centre
VM_FOCAL = 900.0                         # the viewmodel's focal length in pixels
SS = 4                                   # samples per pixel per axis

# The two weapon palettes as the console shows them (RGB555 expanded the
# way the harness does, c*255//31). Index 0 is transparent.
def _rgb(r, g, b):
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)


STEEL_555 = [(4, 4, 5), (13, 16, 17), (29, 28, 24)]
# One palette for the whole weapon. A sprite takes one palette, so a second
# colour (wood on a pump) could only show in whole 8x16 blocks: the gun is
# diagonal and the action slides, so the colour would sit in rectangles
# that do not follow the part. Every object therefore uses OBJ palette 0;
# `fit` still chooses per object among PALETTES, so a future weapon whose
# second material fills whole objects can add one.
PALETTES = ([_rgb(*c) for c in STEEL_555],)
PALETTE_OBJ = (0,)                       # the OBJ palette each fitted palette is
# The PNG's own palette (for previews and the sprite compiler's check).
SHEET_PALETTE = [[0, 0, 0], [30, 35, 40], [111, 132, 137], [238, 229, 197]]

# ------------------------------------------------------------------ geometry


def _length(v):
    return np.sqrt(np.sum(v * v, axis=-1))


def _capsule(p, a, b, r):
    pa, ba = p - a, b - a
    h = np.clip(np.sum(pa * ba, -1) / np.dot(ba, ba), 0, 1)
    return _length(pa - ba * h[:, None]) - r


def _cylinder(p, a, b, r):
    ba, pa = b - a, p - a
    baba = np.dot(ba, ba)
    paba = np.sum(pa * ba, -1)
    x = _length(pa * baba - ba * paba[:, None]) - r * baba
    y = np.abs(paba - baba * 0.5) - baba * 0.5
    x2, y2 = x * x, y * y * baba
    d = np.where(np.maximum(x, y) < 0, -np.minimum(x2, y2),
                 np.where(x > 0, x2, 0) + np.where(y > 0, y2, 0))
    return np.sign(d) * np.sqrt(np.abs(d)) / baba


def _roundbox(p, half, r):
    q = np.abs(p) - (half - r)
    return _length(np.maximum(q, 0)) + np.minimum(np.max(q, -1), 0) - r


def _ellipsoid(p, radii):
    k0 = _length(p / radii)
    k1 = _length(p / (radii * radii))
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def rotation(yaw, pitch, roll):
    """Positive yaw turns +z towards +x; positive pitch turns +z towards -y."""
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]])
    return ry @ rx @ rz


@dataclass(frozen=True)
class Part:
    kind: str          # cyl, cap, box, ell
    material: str      # steel, polymer, wood, glove, sleeve, ink, glow
    args: tuple
    name: str          # parts sharing a name read as one piece
    action: bool = False   # moves with the action (pump, bolt, rings, shutter)


@dataclass
class Pose:
    origin: np.ndarray
    yaw: float
    pitch: float
    roll: float
    action: float = 0.0    # metres the action has travelled back


def _distance(parts, pose, p_cam):
    p = (p_cam - pose.origin) @ rotation(pose.yaw, pose.pitch, pose.roll)
    best = np.full(len(p), 1e9)
    which = np.full(len(p), -1)
    moved = p - np.array([0, 0, -pose.action])
    for index, part in enumerate(parts):
        q = moved if part.action else p
        if part.kind == "cyl":
            d = _cylinder(q, np.array(part.args[0]), np.array(part.args[1]), part.args[2])
        elif part.kind == "cap":
            d = _capsule(q, np.array(part.args[0]), np.array(part.args[1]), part.args[2])
        elif part.kind == "box":
            qq = q - np.array(part.args[0])
            if len(part.args) > 3:
                qq = qq @ rotation(*part.args[3])
            d = _roundbox(qq, np.array(part.args[1]), part.args[2])
        elif part.kind == "ell":
            qq = q - np.array(part.args[0])
            if len(part.args) > 2:
                qq = qq @ rotation(*part.args[2])
            d = _ellipsoid(qq, np.array(part.args[1]))
        else:
            raise ValueError(part.kind)
        closer = d < best
        best = np.where(closer, d, best)
        which = np.where(closer, index, which)
    return best, which


def aim(length, rear=(106.0, 136.0), depth=3.2, muzzle=(79.0, 90.0), roll=-0.45):
    """The pose that puts the gun's origin at `rear` (world pixels, `depth`
    metres away) and the point `length` metres along its axis at `muzzle`."""
    ray = lambda sx, sy: np.array([(sx - CX) / VM_FOCAL, -(sy - CY) / VM_FOCAL, 1.0])
    o = ray(*rear) * depth
    r = ray(*muzzle)
    a, b, c = r @ r, -2 * (r @ o), o @ o - length * length
    s = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
    d = s * r - o
    d /= np.linalg.norm(d)
    return Pose(o, yaw=math.atan2(d[0], d[2]), pitch=-math.asin(d[1]), roll=roll)


# ------------------------------------------------------------------ render


def render(parts, pose):
    """Per pixel: coverage, majority part, its mean normal and nearest depth."""
    x0, y0, w, h = WINDOW
    xs = (np.arange(w * SS) + 0.5) / SS + x0
    ys = (np.arange(h * SS) + 0.5) / SS + y0
    gx, gy = np.meshgrid(xs, ys)
    dirs = np.stack(((gx - CX) / VM_FOCAL, -(gy - CY) / VM_FOCAL, np.ones_like(gx)), -1).reshape(-1, 3)
    dirs /= _length(dirs)[:, None]
    t = np.full(len(dirs), 0.5)
    done = np.zeros(len(dirs), bool)
    hit = np.zeros(len(dirs), bool)
    for _ in range(200):
        active = np.nonzero(~done)[0]
        if not len(active):
            break
        d, _ = _distance(parts, pose, dirs[active] * t[active, None])
        t[active] += d * 0.9
        close = d < 2e-4
        hit[active[close]] = True
        done[active[close | (t[active] > 60.0)]] = True
    points = dirs * t[:, None]
    _, which = _distance(parts, pose, points)
    normal = np.zeros_like(points)
    for axis in range(3):
        off = np.zeros(3); off[axis] = 2e-4
        normal[:, axis] = _distance(parts, pose, points + off)[0] - _distance(parts, pose, points - off)[0]
    normal /= np.maximum(_length(normal), 1e-9)[:, None]
    which = np.where(hit, which, -1)
    which = which.reshape(h, SS, w, SS).transpose(0, 2, 1, 3).reshape(h, w, SS * SS)
    normal = normal.reshape(h, SS, w, SS, 3).transpose(0, 2, 1, 3, 4).reshape(h, w, SS * SS, 3)
    t = t.reshape(h, SS, w, SS).transpose(0, 2, 1, 3).reshape(h, w, SS * SS)
    part = np.full((h, w), -1)
    mean_normal = np.zeros((h, w, 3))
    depth = np.full((h, w), 1e9)
    for y in range(h):
        for x in range(w):
            samples = which[y, x]
            hits = samples[samples >= 0]
            if len(hits) * 2 < SS * SS:
                continue                                 # under half covered: clear
            values, counts = np.unique(hits, return_counts=True)
            major = values[np.argmax(counts)]
            chosen = samples == major
            part[y, x] = major
            mean_normal[y, x] = normal[y, x][chosen].mean(0)
            depth[y, x] = t[y, x][chosen].min()
    mean_normal /= np.maximum(_length(mean_normal), 1e-9)[..., None]
    return part, mean_normal, depth


LIGHT = np.array([0.3, 0.85, -0.3]); LIGHT = LIGHT / np.linalg.norm(LIGHT)
HALF = (LIGHT + np.array([0, 0, -1.0])); HALF = HALF / np.linalg.norm(HALF)
BANDS = {"steel": (0.12, 0.84), "polymer": (0.35, 0.8), "wood": (0.1, 0.55),
         "glove": (0.05, 0.62), "sleeve": (0.45, 0.8)}
DESIRED = {
    "ink": {"shadow": _rgb(2, 3, 4)},
    "steel": {"shadow": _rgb(5, 6, 8), "mid": _rgb(12, 15, 17), "light": _rgb(26, 28, 27)},
    "polymer": {"shadow": _rgb(3, 3, 4), "mid": _rgb(8, 9, 11), "light": _rgb(14, 16, 18)},
    # Wood reads as the mid tone without the crest highlight, cut by ink
    # grooves, so it parts from the lit steel beside it in one palette.
    "wood": {"shadow": _rgb(4, 4, 5), "mid": _rgb(13, 16, 17), "light": _rgb(13, 16, 17)},
    # Gloves are lit like the gun: mid tone with bright knuckles, so the
    # hand reads as a hand and not as the gun's shadow.
    "glove": {"shadow": _rgb(4, 4, 5), "mid": _rgb(13, 16, 17), "light": _rgb(26, 28, 27)},
    "sleeve": {"shadow": _rgb(4, 4, 5), "mid": _rgb(4, 4, 5), "light": _rgb(13, 16, 17)},
    "glow": {"shadow": _rgb(26, 28, 27), "mid": _rgb(26, 28, 27), "light": _rgb(29, 28, 24)},
}
PART_GAP = 0.004     # metres a neighbour must be nearer for a part-boundary ink line


def shade(parts, part, normal, depth):
    """Desired RGB and opacity per pixel: banded material colour, then ink."""
    h, w = part.shape
    rgb = np.zeros((h, w, 3))
    opaque = part >= 0
    for y in range(h):
        for x in range(w):
            if not opaque[y, x]:
                continue
            material = parts[part[y, x]].material
            if material == "ink":
                rgb[y, x] = DESIRED["ink"]["shadow"]
                continue
            diffuse = float(normal[y, x] @ LIGHT)
            lo, hi = BANDS.get(material, (0.15, 0.6))
            if material == "glow" or (material == "steel" and float(normal[y, x] @ HALF) > 0.95) or diffuse > hi:
                band = "light"
            elif diffuse > lo:
                band = "mid"
            else:
                band = "shadow"
            rgb[y, x] = DESIRED[material][band]
    ink = np.zeros((h, w), bool)
    for y in range(h):
        for x in range(w):
            if not opaque[y, x]:
                continue
            for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                yy, xx = y + dy, x + dx
                if not (0 <= yy < h and 0 <= xx < w) or not opaque[yy, xx]:
                    ink[y, x] = True
                    break
                if (parts[part[yy, xx]].name != parts[part[y, x]].name
                        and depth[y, x] - depth[yy, xx] > PART_GAP):
                    ink[y, x] = True
                    break
    # A lone pixel whose four neighbours agree on another colour is noise.
    clean = rgb.copy()
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if not opaque[y, x] or ink[y, x]:
                continue
            around = [tuple(rgb[y + dy, x + dx]) for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0))
                      if opaque[y + dy, x + dx] and not ink[y + dy, x + dx]]
            if len(around) == 4 and len(set(around)) == 1 and around[0] != tuple(rgb[y, x]):
                clean[y, x] = around[0]
    clean[ink] = DESIRED["ink"]["shadow"]
    return clean, opaque


def fit(cels):
    """One palette per 8x16 object over every cel; returns index images and choices."""
    h, w = cels[0][1].shape
    choice = []
    for oy in range(0, h, OBJECT_H):
        for ox in range(0, w, OBJECT_W):
            errors = []
            for palette in PALETTES:
                colours = np.array(palette, float)
                error = 0.0
                for rgb, opaque in cels:
                    block = rgb[oy:oy + OBJECT_H, ox:ox + OBJECT_W]
                    mask = opaque[oy:oy + OBJECT_H, ox:ox + OBJECT_W]
                    d = ((block[..., None, :] - colours[None, None]) ** 2).sum(-1)
                    error += float((d.min(-1) * mask).sum())
                errors.append(error)
            choice.append(int(np.argmin(errors)))
    indices = []
    for rgb, opaque in cels:
        out = np.zeros((h, w), np.uint8)
        k = 0
        for oy in range(0, h, OBJECT_H):
            for ox in range(0, w, OBJECT_W):
                colours = np.array(PALETTES[choice[k]], float)
                block = rgb[oy:oy + OBJECT_H, ox:ox + OBJECT_W]
                idx = ((block[..., None, :] - colours[None, None]) ** 2).sum(-1).argmin(-1) + 1
                out[oy:oy + OBJECT_H, ox:ox + OBJECT_W] = np.where(opaque[oy:oy + OBJECT_H, ox:ox + OBJECT_W], idx, 0)
                k += 1
        indices.append(out)
    return indices, [PALETTE_OBJ[c] for c in choice]


# ------------------------------------------------------------------ models


def _hands(add, grip, fingers_x, sleeve_to, right=True, fingers_dy=-0.004):
    """A gloved left hand under the fore-end at `grip` (moving with the
    action when `grip` is on it), three fingers over its near side (-x: the
    gun is right of the eye and points at the centre, so the camera sees
    its left flank), and
    the right hand on the grip, mostly out of frame."""
    gx, gy, gz, moving = grip
    add("ell", "glove", ((gx + 0.004, gy - 0.034, gz), (0.030, 0.020, 0.050)), "lhand", moving)
    for k, dz in enumerate((-0.028, -0.002, 0.024)):
        add("ell", "glove", ((fingers_x, gy + fingers_dy, gz + dz), (0.011, 0.024, 0.012)), f"lfinger{k}", moving)
    add("cap", "sleeve", ((gx + 0.004, gy - 0.054, gz - 0.03), sleeve_to, 0.036), "lsleeve", moving)
    if right:
        add("ell", "glove", ((0.006, -0.065, 0.02), (0.040, 0.040, 0.056)), "rhand")
        add("cap", "sleeve", ((0.02, -0.11, -0.01), (0.14, -0.30, -0.22), 0.046), "rsleeve")


def shotgun():
    """Pump shotgun: barrel over a magazine tube, a grooved wooden pump the
    left hand racks, receiver with its ejection port on the near side."""
    P = []
    add = lambda kind, material, args, name, action=False: P.append(Part(kind, material, args, name, action))
    add("box", "steel", ((0, 0.0, 0.09), (0.017, 0.030, 0.10), 0.005), "receiver")
    add("box", "ink", ((-0.0175, 0.010, 0.11), (0.0015, 0.010, 0.04), 0.001), "receiver")
    add("box", "polymer", ((0, -0.06, 0.03), (0.015, 0.045, 0.03), 0.006, (0, -0.35, 0)), "grip")
    add("box", "polymer", ((0, -0.03, -0.16), (0.021, 0.036, 0.13), 0.008), "stock")
    add("cyl", "steel", ((0, 0.020, 0.15), (0, 0.020, 0.64), 0.0150), "barrel")
    add("cyl", "steel", ((0, 0.020, 0.62), (0, 0.020, 0.645), 0.0170), "barrel")
    add("cyl", "ink", ((0, 0.020, 0.644), (0, 0.020, 0.647), 0.010), "barrel")
    add("cyl", "steel", ((0, -0.014, 0.15), (0, -0.014, 0.57), 0.0135), "tube")
    add("box", "steel", ((0, 0.003, 0.55), (0.008, 0.020, 0.010), 0.002), "band")
    add("cyl", "wood", ((0, -0.016, 0.30), (0, -0.016, 0.52), 0.028), "pump", True)
    for k in range(6):
        z = 0.315 + k * 0.034
        add("cyl", "ink", ((0, -0.016, z), (0, -0.016, z + 0.007), 0.0292), "pump", True)
    # Fingers on the near side but low, wrapping the pump's underside, so
    # the hand shows and the grooves above it still do.
    _hands(add, (0.0, -0.016, 0.40, True), -0.026, (-0.10, -0.28, 0.02), fingers_dy=-0.024)
    return P, 0.645, 0.09


def slug_rifle():
    """Heavy rifle: a long barrel ending in a big ported muzzle brake with a
    front sight, a grooved wooden handguard, and a bolt handle on the near
    side of the receiver that the action pulls back."""
    P = []
    add = lambda kind, material, args, name, action=False: P.append(Part(kind, material, args, name, action))
    add("box", "steel", ((0, 0.0, 0.10), (0.017, 0.026, 0.12), 0.004), "receiver")
    add("box", "polymer", ((0, -0.06, 0.0), (0.015, 0.045, 0.03), 0.006, (0, -0.35, 0)), "grip")
    add("box", "polymer", ((0, -0.03, -0.16), (0.021, 0.036, 0.13), 0.008), "stock")
    add("cyl", "steel", ((0, 0.010, 0.22), (0, 0.010, 0.70), 0.0130), "barrel")
    add("box", "steel", ((0, 0.010, 0.685), (0.020, 0.019, 0.036), 0.004), "brake")
    for k in range(2):
        add("box", "ink", ((-0.0205, 0.010, 0.672 + k * 0.026), (0.0015, 0.010, 0.006), 0.001), "brake")
    add("cyl", "ink", ((0, 0.010, 0.7205), (0, 0.010, 0.7225), 0.009), "brake")
    add("box", "steel", ((0, 0.036, 0.675), (0.004, 0.008, 0.006), 0.002), "sight")
    add("box", "wood", ((0, -0.006, 0.40), (0.016, 0.019, 0.11), 0.007), "handguard")
    for k in range(4):
        add("box", "ink", ((0, -0.006, 0.32 + k * 0.05), (0.0165, 0.0195, 0.004), 0.004), "handguard")
    add("cap", "steel", ((-0.017, 0.012, 0.13), (-0.046, -0.008, 0.12), 0.006), "bolt", True)
    add("ell", "steel", ((-0.048, -0.010, 0.12), (0.011, 0.011, 0.011)), "bolt", True)
    _hands(add, (0.0, -0.006, 0.44, False), -0.022, (-0.10, -0.28, 0.02))
    return P, 0.72, 0.07


def arc_lance():
    """Energy lance: a dark emitter body banded by two brass capacitor rings
    that slide back as it recharges, a lit coil along its top, and a fork of
    two prongs with live tips at the muzzle."""
    P = []
    add = lambda kind, material, args, name, action=False: P.append(Part(kind, material, args, name, action))
    add("box", "steel", ((0, 0.0, 0.10), (0.017, 0.027, 0.12), 0.008), "receiver")
    add("box", "polymer", ((0, -0.06, 0.02), (0.015, 0.045, 0.03), 0.006, (0, -0.35, 0)), "grip")
    add("box", "polymer", ((0, -0.03, -0.16), (0.022, 0.036, 0.13), 0.008), "stock")
    add("cyl", "steel", ((0, 0.008, 0.18), (0, 0.008, 0.55), 0.017), "emitter")
    for k, z in enumerate((0.24, 0.38)):
        add("cyl", "wood", ((0, 0.008, z), (0, 0.008, z + 0.07), 0.026), f"ring{k}", True)
        for g in (0.022, 0.046):
            add("cyl", "ink", ((0, 0.008, z + g), (0, 0.008, z + g + 0.005), 0.0265), f"ring{k}", True)
    for side in (-1, 1):
        add("cyl", "steel", ((side * 0.012, 0.008, 0.55), (side * 0.018, 0.008, 0.68), 0.009), f"prong{side}")
        add("ell", "glow", ((side * 0.018, 0.008, 0.684), (0.010, 0.010, 0.010)), f"tip{side}")
    _hands(add, (0.0, -0.012, 0.33, False), 0.024, (-0.10, -0.28, 0.02))
    return P, 0.68, 0.08


def pulse_carbine():
    """Compact carbine: a dark boxy shroud with a row of lit vents, a steel
    muzzle and barrel, a carry handle whose charging shutter slides back,
    and a deep wooden magazine."""
    P = []
    add = lambda kind, material, args, name, action=False: P.append(Part(kind, material, args, name, action))
    add("box", "polymer", ((0, 0.0, 0.22), (0.023, 0.029, 0.22), 0.007), "shroud")
    for k in range(4):
        add("box", "glow", ((-0.0232, 0.006, 0.25 + k * 0.045), (0.0012, 0.012, 0.009), 0.002), f"vent{k}")
    add("box", "steel", ((0, -0.002, 0.46), (0.018, 0.022, 0.028), 0.006), "muzzle")
    add("cyl", "steel", ((0, 0.000, 0.46), (0, 0.000, 0.55), 0.0115), "barrel")
    add("cyl", "ink", ((0, 0.000, 0.549), (0, 0.000, 0.552), 0.007), "barrel")
    add("box", "steel", ((0, 0.044, 0.16), (0.010, 0.013, 0.12), 0.004), "handle")
    add("box", "steel", ((-0.012, 0.042, 0.21), (0.005, 0.009, 0.022), 0.002), "shutter", True)
    add("box", "wood", ((0, -0.064, 0.17), (0.016, 0.050, 0.030), 0.006, (0, 0.18, 0)), "magazine")
    add("box", "polymer", ((0, -0.06, -0.02), (0.015, 0.045, 0.03), 0.006, (0, -0.35, 0)), "grip")
    _hands(add, (0.0, -0.028, 0.38, False), -0.026, (-0.10, -0.28, 0.02))
    return P, 0.55, 0.06


MODELS = {"shotgun": shotgun, "slug_rifle": slug_rifle, "arc_lance": arc_lance, "pulse_carbine": pulse_carbine}


def poses(length, travel):
    """Idle, the kick (the gun jolts down and its muzzle lifts, so the muzzle
    stays under the flash), the action fully back, and returning."""
    base = aim(length)
    out = []
    for kick, action in ((0.0, 0.0), (1.0, 0.0), (0.3, 1.0), (0.15, 0.5)):
        pose = copy.deepcopy(base)
        pose.origin = pose.origin + np.array([0.0, -0.022 * kick, 0.0])
        pose.pitch -= 0.03 * kick
        pose.action = travel * action
        out.append(pose)
    return out


def render_sheet(name):
    """The weapon's four cels as palette-index images and its object palettes."""
    parts, length, travel = MODELS[name]()
    cels = [shade(parts, *render(parts, pose)) for pose in poses(length, travel)]
    return fit(cels)


def sheet_png(indices) -> bytes:
    image = Image.new("P", (WIDTH * len(indices), HEIGHT), 0)
    image.putpalette([c for rgb in SHEET_PALETTE for c in rgb] + [0] * (768 - 12))
    for n, cel in enumerate(indices):
        for y in range(HEIGHT):
            for x in range(WIDTH):
                image.putpixel((n * WIDTH + x, y), int(cel[y, x]))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", transparency=0, optimize=False)
    return buffer.getvalue()


def preview(name, indices, object_palettes, scale=6):
    """The sheet as the console colours it: each object in its palette."""
    colours = dict(zip(PALETTE_OBJ, PALETTES))
    image = Image.new("RGB", (WIDTH * len(indices), HEIGHT), (40, 44, 48))
    for n, cel in enumerate(indices):
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if cel[y, x]:
                    obj = (y // OBJECT_H) * (WIDTH // OBJECT_W) + x // OBJECT_W
                    image.putpixel((n * WIDTH + x, y), colours[object_palettes[obj]][cel[y, x] - 1])
    return image.resize((image.width * scale, image.height * scale), Image.NEAREST)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the native sheets and manifest records")
    parser.add_argument("--check", action="store_true", help="fail unless the committed sheets equal a fresh render")
    parser.add_argument("--weapon", choices=WEAPONS, action="append")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    out = ROOT / "build" / "weapon-art"
    out.mkdir(parents=True, exist_ok=True)
    failed = []
    for name in args.weapon or WEAPONS:
        indices, object_palettes = render_sheet(name)
        data = sheet_png(indices)
        preview(name, indices, object_palettes).save(out / f"{name}.png")
        record = manifest["assets"][name]
        if args.check:
            path = ROOT / "assets" / "sable_v2" / record["file"]
            if path.read_bytes() != data or record.get("object_palettes") != object_palettes:
                failed.append(name)
        if args.write:
            (NATIVE / f"{name}.png").write_bytes(data)
            record.update(file=f"native/{name}.png", size=[WIDTH, HEIGHT], frames=FRAMES, ticks=TICKS,
                          anchor=[WIDTH // 2, HEIGHT], palette=SHEET_PALETTE,
                          object_palettes=object_palettes, sha256=hashlib.sha256(data).hexdigest())
        print(f"{name}: object palettes {object_palettes}")
    if args.write:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    if failed:
        raise SystemExit(f"committed sheets differ from a fresh render: {', '.join(failed)}")
    print(f"previews in {out}")


if __name__ == "__main__":
    main()
