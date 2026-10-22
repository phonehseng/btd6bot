"""Reading a map's medals from its map-select card.

Under every map thumbnail sit four medal slots: Easy, Medium, Hard and
Impoppable. An empty slot is a flat tan medal outline; an earned medal is
coloured (bronze/silver/gold/black rim around a blue star). Reading them lets
the bot adopt any save file instead of trusting its own notes.
"""
import cv2
import numpy as np

SLOTS = ["easy", "medium", "hard", "impoppable"]
# slot centres relative to the centre of the map-name label on the card
# (measured on docs/screens/search.jpg, 1920x1200)
SLOT_DX = (-0.0763, -0.0266, 0.0256, 0.0752)
SLOT_DY = 0.206
PATCH = 0.008  # half-size of the sampled patch, fraction of width


def slot_earned(patch):
    """True if a BGR patch shows an earned medal rather than an empty slot."""
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    # Earned medals show a blue star backdrop: 0.29 of the patch on a real
    # bronze medal vs <= 0.01 on every empty slot sampled. Hue/value spread is
    # NOT used: red thumbnails wrap the hue circle and slot edges add texture.
    blue = np.mean((h > 85) & (h < 130) & (s > 90) & (v > 110))
    # VERIFY LIVE: the Impoppable medal may lack blue; a mostly-black patch counts too
    dark = np.mean(v < 70)
    return bool(blue > 0.06 or dark > 0.4)


def read_card(frame, name_x, name_y):
    """{difficulty: earned} for the card whose name label is centred at (name_x, name_y)."""
    hh, ww = frame.shape[:2]
    out = {}
    r = int(PATCH * ww)
    for diff, dx in zip(SLOTS, SLOT_DX):
        cx, cy = int((name_x + dx) * ww), int((name_y + SLOT_DY) * hh)
        patch = frame[max(0, cy - r):cy + r, max(0, cx - r):cx + r]
        out[diff] = slot_earned(patch) if patch.size else False
    return out


# ---------------------------------------------------------------------------
# Map-select pages (PLAY, no search): 6 cards per page on a fixed 3x2 grid.
# Each card shows a medal cluster per difficulty: a big Easy/Medium/Hard medal
# with small medals for its sub-modes around it, then an Impoppable skull and a
# small CHIMPS skull. Unearned slots are plain tan outlines and unearned small
# medals are not drawn at all. Calibrated live 2026-10-21 (1920x1200, v57.3) on
# a fully-medalled card and six partial ones; every sample point is chosen where
# only that medal draws (not the big medal's ribbons, not the map thumbnail).
# ---------------------------------------------------------------------------
GRID_X0, GRID_DX = 488, 471     # name-label centre of column 0, column step (px @1920)
GRID_Y0, GRID_DY = 152, 348     # name-label centre of row 0, row step (px @1200)

# mode -> (x, y, half-size, colour test, threshold), px relative to card (0, 0)
MODE_POINTS = {
    "easy":          (339, 412, 7, "blue", 0.2),
    "primary_only":  (305, 445, 6, "green", 0.15),
    "deflation":     (380, 445, 6, "purple", 0.12),
    "medium":        (437, 410, 7, "blue", 0.2),
    "military_only": (405, 440, 6, "green", 0.12),
    "apopalypse":    (440, 455, 6, "purple", 0.15),
    "reverse":       (478, 430, 6, "blue", 0.25),
    "hard":          (537, 402, 7, "yellow", 0.4),
    "magic_only":    (493, 415, 6, "green", 0.15),
    "double_hp":     (582, 412, 6, "purple", 0.15),
    "half_cash":     (507, 452, 6, "blue", 0.1),
    "abr":           (570, 452, 6, "abr", 0.0),
    "impoppable":    (633, 405, 10, "blue", 0.3),
    "chimps":        (668, 452, 6, "blue", 0.3),
}


def _fractions(patch):
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.int32)
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    return {
        "blue": float(np.mean((h >= 85) & (h <= 125) & (s > 80) & (v > 120))),
        "green": float(np.mean((h > 40) & (h < 85) & (s > 110))),
        "purple": float(np.mean((h > 125) & (h < 165) & (s > 90))),
        "yellow": float(np.mean((h >= 20) & (h <= 35) & (s > 170) & (v > 220))),
        "tan": float(np.mean((h >= 8) & (h <= 30) & (s > 60) & (s < 190) & (v > 140))),
    }


def read_grid_card(frame, col, row):
    """{mode: earned} for the card at grid position (col 0-2, row 0-1)."""
    hh, ww = frame.shape[:2]
    sx, sy = ww / 1920.0, hh / 1200.0
    out = {}
    for mode, (x, y, r, test, thr) in MODE_POINTS.items():
        cx, cy = int((x + GRID_DX * col) * sx), int((y + GRID_DY * row) * sy)
        rr = max(2, int(r * sx))
        patch = frame[max(0, cy - rr):cy + rr, max(0, cx - rr):cx + rr]
        if patch.size == 0:
            out[mode] = False
            continue
        f = _fractions(patch)
        if test == "abr":  # white-and-gold medal: some blue, almost no tan card
            out[mode] = f["blue"] > 0.07 and f["tan"] < 0.12
        else:
            out[mode] = f[test] > thr
    return out


def grid_cell(x, y):
    """(col, row) of the card whose name label is at fractional (x, y), or None."""
    col = min(range(3), key=lambda c: abs(x * 1920 - (GRID_X0 + GRID_DX * c)))
    row = min(range(2), key=lambda r: abs(y * 1200 - (GRID_Y0 + GRID_DY * r)))
    if abs(x * 1920 - (GRID_X0 + GRID_DX * col)) > 150 or abs(y * 1200 - (GRID_Y0 + GRID_DY * row)) > 60:
        return None
    return col, row
