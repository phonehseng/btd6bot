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
