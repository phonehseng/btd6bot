"""Small template library (assets/*.png captured at 1920x1200)."""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

ASSETS = Path(__file__).resolve().parents[1] / "assets"
REF_HEIGHT = 1200


@lru_cache(maxsize=None)
def load(name, height=REF_HEIGHT):
    img = cv2.imread(str(ASSETS / f"{name}.png"))
    if img is None:
        raise FileNotFoundError(ASSETS / f"{name}.png")
    if height != REF_HEIGHT:
        s = height / REF_HEIGHT
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return img


def match(frame, name, region=None):
    """Best normalised correlation of template `name` inside region (fractions)."""
    tpl = load(name, frame.shape[0])
    img = frame
    if region:
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = region
        img = frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    if img.shape[0] < tpl.shape[0] or img.shape[1] < tpl.shape[1]:
        return 0.0, None
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    return float(score), loc


def brightness_ratio(frame, name, region):
    """How bright the best match of template `name` in region is, as a share
    of the template's own brightness (1.0 = as captured).

    TM_CCOEFF_NORMED ignores brightness, so a button under a dark overlay
    still matches its shape almost perfectly; this tells the two apart."""
    _, loc = match(frame, name, region)
    if loc is None:
        return 0.0
    tpl = load(name, frame.shape[0])
    h, w = frame.shape[:2]
    x0, y0 = int(region[0] * w) + loc[0], int(region[1] * h) + loc[1]
    patch = frame[y0:y0 + tpl.shape[0], x0:x0 + tpl.shape[1]]
    return float(patch.mean()) / max(float(tpl.mean()), 1.0)


def classify(frame, names, region):
    scores = {n: match(frame, n, region)[0] for n in names}
    best = max(scores, key=scores.get)
    return best, scores


def mean_color(frame, region):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = region
    return np.asarray(frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]).reshape(-1, 3).mean(0)
