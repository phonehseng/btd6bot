"""Draw a map's placement grid and its mechanics to a PNG, to check them by eye.

Usage:
    python tools/render_map_mechanics.py "Covered Garden" [more maps...] [--out logs]
    python tools/render_map_mechanics.py --all

Colours (one cell = one MapModel grid cell):
    green        land a tower can use for the whole game
    blue         water a tower can use for the whole game
    orange       usable at the start, but not for the whole game (rising
                 water, eroding ice, cycling windows...)
    yellow       ground that moves and carries towers (gears, platforms)
    magenta      ground a moving platform sweeps over, or where towers get
                 switched off
    dark grey    obstacles, track, other unusable ground
    red          bloon lanes towers can hit; purple: lanes where bloons
                 cannot be hit (gates, tunnels)
    black dots   line-of-sight blockers (counting every blocker that is
                 ever there)
    white boxes  removable obstacles, with their price
Reads only data/map_geometry, or --geometry DIR (no game files).
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import mapgeom as G  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402

SCALE = 6   # output pixels per grid cell


def render(map_name, out_dir):
    geom = G.load(map_name)
    if geom is None:
        print(f"{map_name}: no geometry")
        return None
    proj = G.Projection(LAYOUTS["16:10"]["playfield"])
    lanes = np.zeros(G.GRID[::-1], bool)
    heat, _, _ = G.paint_paths(geom, proj, lanes)
    grids = G.placement_grids(geom, proj, lanes | (heat > 0))
    h, w = heat.shape
    img = np.full((h, w, 3), 60, np.uint8)                          # dark grey
    img[grids["static_land"] | grids["static_water"]] = (0, 140, 255)   # orange (BGR)
    img[grids["land"]] = (60, 170, 60)
    img[grids["water"]] = (200, 120, 40)
    img[grids["moving"]] = (0, 220, 220)
    img[grids["unsafe"]] = (200, 0, 200)
    img[lanes] = (150, 60, 150)
    img[heat > 0] = (40, 40, 220)
    img = cv2.resize(img, (w * SCALE, h * SCALE), interpolation=cv2.INTER_NEAREST)
    ys, xs = np.nonzero(grids["sight"])
    for y, x in zip(ys, xs):
        cv2.circle(img, (int(x * SCALE + SCALE // 2), int(y * SCALE + SCALE // 2)), 1, (0, 0, 0), -1)
    for r in G.removables(map_name):
        for poly in r["polygons"]:
            pts = np.round(proj.to_cells(poly) * SCALE).astype(np.int32)
            cv2.polylines(img, [pts], True, (255, 255, 255), 1)
        c = proj.to_cells([r["position"]])[0] * SCALE
        cv2.putText(img, f"${r['cost']}", (int(c[0]) - 14, int(c[1])), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, map_name, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    out = Path(out_dir) / f"mechanics_{G.map_id_for(map_name)}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("maps", nargs="*")
    ap.add_argument("--all", action="store_true", help="every map in data/map_geometry")
    ap.add_argument("--out", default=str(ROOT / "logs"))
    ap.add_argument("--geometry", help="read geometry from this folder instead of data/map_geometry")
    args = ap.parse_args()
    if args.geometry:
        G.GEOMETRY_DIR = Path(args.geometry)
    names = [f.stem for f in sorted(G.GEOMETRY_DIR.glob("*.json"))] if args.all else args.maps
    for name in names:
        path = render(name, args.out)
        if path:
            print(path)
