"""Measure where Sanctuary's moving platforms really stand, from a recorded game.

Usage:
    python tools/measure_platforms.py LOG OUTDIR [--map Sanctuary]

LOG is a bot log covering one game on the map (the "match: round N  cash"
lines give each round's start); the recordings in ~/.btd6bot_cache/recordings
(rec_YYYYmmdd_HHMMSS.mkv, one per minute) give the frames. For every round
one frame 1.5 s before the next round starts is cut (ffmpeg, below normal
priority) into OUTDIR, and then:

  1. read:  which layout the screen shows, of the rounds r-1, r, r+1
            (mapgeom.platform_round_on_screen) - checks mapgeom.platform_state;
  2. shift: for each platform and state, the shift from the scene's pose
            that puts the most platform stone (mapgeom.stone_mask) inside the
            platform's outline, averaged over every frame in that state and
            searched within 30 world units of the pose mapgeom computes
            (_platform_state_poses) - checks those poses (PLATFORM_ARM_TURN).

Rounds shorter than 5 s are left out of step 2: their frame may show the
platforms still moving.
"""
import argparse
import glob
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import mapgeom                    # noqa: E402
from btd6bot.layout import LAYOUTS             # noqa: E402
from btd6bot.maplearn import MapModel          # noqa: E402

CACHE = Path.home() / ".btd6bot_cache"
BELOW_NORMAL = 0x00004000          # Windows process priority class
SEARCH_UNITS = 30.0


def round_starts(log_path):
    """[(time, round)] of a game: its start and every round change."""
    out = []
    for line in open(log_path, encoding="utf-8", errors="replace"):
        m = re.match(r"(\S+ \S+),\d+ I match: (?:round (\d+)  cash|game starts at round (\d+))", line)
        if m:
            out.append((datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), int(m.group(2) or m.group(3))))
    return out


def cut_frames(starts, outdir):
    """One frame per round, 1.5 s before the next round's line; returns
    {round: seconds the round lasted}."""
    ffmpeg = glob.glob(str(CACHE / "tools/ffmpeg/*/bin/ffmpeg.exe"))
    if not ffmpeg:
        sys.exit("ffmpeg not found under ~/.btd6bot_cache/tools/ffmpeg")
    outdir.mkdir(parents=True, exist_ok=True)
    lengths = {}
    for (t, r), (t2, _) in zip(starts, starts[1:]):
        lengths[r] = (t2 - t).total_seconds()
        at = t2 - timedelta(seconds=1.5)
        rec = at.replace(second=0)
        video = CACHE / "recordings" / f"rec_{rec:%Y%m%d_%H%M%S}.mkv"
        if video.exists():
            subprocess.run([ffmpeg[0], "-loglevel", "error", "-y", "-ss", str((at - rec).total_seconds()),
                            "-i", str(video), "-frames:v", "1", "-vf", "scale=960:-1",
                            str(outdir / f"r{r:02d}.png")], creationflags=BELOW_NORMAL)
    return lengths


def measure_shifts(model, frames):
    """Print, per platform and state, the measured shift from the scene and
    the one mapgeom computes."""
    grids = mapgeom.grids_for(model)
    proj = grids["proj"]
    h, w = next(iter(frames.values())).shape
    for plat in grids["platforms"]:
        area = next((a for a, _ in plat["areas"] if a["type"] == "land"), None)
        if area is None:
            continue
        mover = plat["mover"]
        pts = proj.to_frac(np.asarray(area["polygons"][0]))[:, :2] * [w, h]
        x0, y0 = pts.min(axis=0).astype(int)
        x1, y1 = pts.max(axis=0).astype(int) + 1
        kernel = np.zeros((y1 - y0, x1 - x0), np.float32)
        cv2.fillPoly(kernel, [(pts - [x0, y0]).astype(np.int32)], 1.0)
        kernel /= kernel.sum()
        for state, pose in sorted(mover["state_poses"].items()):
            rounds = [r for r in frames if mapgeom.platform_state(mover, r) == state]
            if not rounds:
                continue
            score = sum(cv2.matchTemplate(frames[r], kernel, cv2.TM_CCORR) for r in rounds) / len(rounds)
            gx = int(round(pose[0] * proj.ux * w)) + x0
            gy = int(round(-pose[1] * proj.uy * h)) + y0
            rx, ry = int(SEARCH_UNITS * proj.ux * w), int(SEARCH_UNITS * proj.uy * h)
            window = np.full(score.shape, -1.0, np.float32)
            ya, yb = max(0, gy - ry), min(score.shape[0], gy + ry + 1)
            xa, xb = max(0, gx - rx), min(score.shape[1], gx + rx + 1)
            window[ya:yb, xa:xb] = score[ya:yb, xa:xb]
            iy, ix = np.unravel_index(np.argmax(window), window.shape)
            dx, dz = (ix - x0) / w / proj.ux, -(iy - y0) / h / proj.uy
            print(f"{plat['name']:22s} state {state}: {len(rounds):2d} frames, measured ({dx:6.1f}, {dz:6.1f}), "
                  f"mapgeom ({pose[0]:6.1f}, {pose[1]:6.1f}), stone {window.max():.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("outdir")
    ap.add_argument("--map", default="Sanctuary")
    args = ap.parse_args()
    model = MapModel(args.map, LAYOUTS["16:10"]["playfield"])
    if not mapgeom.has_platforms(model):
        sys.exit(f"{args.map} has no moving platforms")
    lengths = cut_frames(round_starts(args.log), Path(args.outdir))
    frames, wrong, unclear = {}, [], []
    for p in sorted(Path(args.outdir).glob("r*.png")):
        r = int(p.stem[1:])
        img = cv2.imread(str(p))
        seen = mapgeom.platform_round_on_screen(model, img, [r - 1, r, r + 1])
        if seen is None:
            unclear.append(r)
        elif seen != r:
            wrong.append((r, seen))
        if lengths.get(r, 0) >= 5:
            stone = mapgeom.stone_mask(img).astype(np.float32)
            stone[:, int(stone.shape[1] * mapgeom.PANEL_X):] = 0
            frames[r] = stone
    print(f"layout read: {len(frames)} rounds kept; unclear {unclear}; read as another round {wrong}")
    if frames:
        measure_shifts(model, frames)


if __name__ == "__main__":
    main()
