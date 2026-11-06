"""Reading a map's medals from its map-select card.

Under every map thumbnail sit four medal slots: Easy, Medium, Hard and
Impoppable. An empty slot is a flat tan medal outline; an earned medal is
coloured (bronze/silver/gold/black rim around a blue star). Reading them lets
the bot adopt any save file instead of trusting its own notes.
"""
import time

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
#
# Which small medal is which was checked on 2026-11-06 against each
# difficulty's mode screen (Lotus Island) and the whole 17-page carousel
# (88 maps, see tests/test_medal_grid_offline.py). The game colours them
#   Easy:   Primary Only green, Deflation purple
#   Medium: Military Only green, Reverse purple, Apopalypse blue
#   Hard:   Magic Monkeys Only green, ABR purple (top right), Double HP blue
#           (bottom left), Half Cash white-gold (bottom right)
# The 2026-10-21 table had Apopalypse/Reverse, ABR/Double HP and Half Cash
# mixed up: the 03:31 scan "adopted" Lotus Island Apopalypse from its purple
# Reverse medal, and the account kept Apopalypse and Half Cash on maps the
# game shows without them, so the planner never played them.
# ---------------------------------------------------------------------------
GRID_X0, GRID_DX = 488, 471     # name-label centre of column 0, column step (px @1920)
GRID_Y0, GRID_DY = 152, 348     # name-label centre of row 0, row step (px @1200)

# mode -> (x, y, half-size, colour test, threshold), px relative to card (0, 0)
MODE_POINTS = {
    "easy":          (335, 414, 7, "blue", 0.2),
    "primary_only":  (307, 443, 6, "green", 0.15),
    "deflation":     (376, 440, 6, "purple", 0.12),
    "medium":        (433, 405, 7, "blue", 0.2),
    "military_only": (408, 435, 6, "green", 0.12),
    "reverse":       (435, 450, 6, "purple", 0.15),
    "apopalypse":    (475, 430, 6, "blue", 0.25),
    "hard":          (537, 406, 7, "yellow", 0.4),
    "magic_only":    (497, 415, 6, "green", 0.15),
    "abr":           (583, 407, 6, "purple", 0.15),
    "double_hp":     (511, 448, 6, "blue", 0.1),
    "half_cash":     (574, 457, 6, "pale", 0.07),
    "impoppable":    (632, 409, 10, "blue", 0.3),
    "chimps":        (666, 448, 6, "blue", 0.3),
}
# Sample points re-centred on 2026-11-06 (each moved at most 5 px) to the spot
# that best separates earned from missing over the 88 captured cards: every
# missing medal there measures at most 0.01, every earned one at least twice
# its threshold (ABR and Impoppable are the closest). A medal reads "earned"
# above its threshold and "missing" below half of it; in between the reading
# is unsure and the medal audit leaves the account alone.
UNSURE_BELOW = 0.5
# The white-gold Half Cash medal ("pale" test) shows a little blue and almost
# none of the tan/orange card behind it; an empty slot there is mostly card.
PALE_MAX_TAN = 0.12


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


def _medal_state(fractions, test, thr):
    """True (earned), False (clearly missing) or None (unsure) for one sample."""
    value = fractions["blue" if test == "pale" else test]
    if value > thr and (test != "pale" or fractions["tan"] < PALE_MAX_TAN):
        return True
    return False if value < thr * UNSURE_BELOW else None


def read_grid_detail(frame, col, row):
    """{mode: True / False / None} for the card at grid position (col 0-2,
    row 0-1). None marks a medal whose colour sits between "earned" and
    "missing" (a page still sliding in, a popup edge over the card)."""
    hh, ww = frame.shape[:2]
    sx, sy = ww / 1920.0, hh / 1200.0
    out = {}
    for mode, (x, y, r, test, thr) in MODE_POINTS.items():
        cx, cy = int((x + GRID_DX * col) * sx), int((y + GRID_DY * row) * sy)
        rr = max(2, int(r * sx))
        patch = frame[max(0, cy - rr):cy + rr, max(0, cx - rr):cx + rr]
        out[mode] = _medal_state(_fractions(patch), test, thr) if patch.size else None
    return out


def read_grid_card(frame, col, row):
    """{mode: earned} for the card at grid position (col 0-2, row 0-1)."""
    return {mode: bool(state) for mode, state in read_grid_detail(frame, col, row).items()}


# ---------------------------------------------------------------------------
# Card frame: a map with all 14 medals gets a black border - its card frame
# is dark navy (HSV ~108/121/53). Every other card's frame is orange
# (~18/234/219) or, with few medals, tan (~18/112/200). On all 88 captured
# cards of 2026-11-06 the navy frame and the 14 medals went together. The
# frame is sampled on its two side strips beside the thumbnail, below the
# hero badge and above the medals, relative to the card's name label so the
# search page's cards can be read the same way. A "REWARD" banner can cover
# the right strip; then the left one decides alone.
# ---------------------------------------------------------------------------
FRAME_STRIPS = ((-194, -188), (190, 196))   # x ranges from the name-label centre (px @1920)
FRAME_DY = (108, 208)                         # y range below the name-label centre (px @1200)
FRAME_SHARE = 0.8                             # share of a strip that must show one frame colour


def _strip_kind(patch):
    """"black", "gold" or None (neither colour fills it) for one frame strip."""
    if patch.size == 0:
        return None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.int32)
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    navy = np.mean((h >= 95) & (h <= 120) & (s > 70) & (v < 100))
    warm = np.mean((h >= 10) & (h <= 28) & (s > 80) & (v > 150))  # orange or tan
    if navy >= FRAME_SHARE:
        return "black"
    if warm >= FRAME_SHARE:
        return "gold"
    return None


def card_frame(frame, name_x, name_y):
    """"black" (a black border: all 14 medals), "gold" (any other card) or
    None (no card frame seen, or the strips disagree) for the card whose name
    label is centred at fractional (name_x, name_y)."""
    hh, ww = frame.shape[:2]
    sx, sy = ww / 1920.0, hh / 1200.0
    cx, cy = name_x * ww, name_y * hh
    y0, y1 = max(0, int(cy + FRAME_DY[0] * sy)), int(cy + FRAME_DY[1] * sy)
    kinds = {_strip_kind(frame[y0:y1, max(0, int(cx + a * sx)):int(cx + b * sx)])
             for a, b in FRAME_STRIPS} - {None}
    return kinds.pop() if len(kinds) == 1 else None


def grid_card_frame(frame, col, row):
    """card_frame for the map-select card at grid position (col, row)."""
    return card_frame(frame, (GRID_X0 + GRID_DX * col) / 1920.0, (GRID_Y0 + GRID_DY * row) / 1200.0)


def card_is_confident(medals, frame_kind):
    """May this card reading change the account? Every medal must read
    clearly, the frame must be seen, and the two must agree: a black border
    with a medal missing (or all 14 under an orange frame) means the page was
    caught mid-slide or something covers the card."""
    if frame_kind is None or any(state is None for state in medals.values()):
        return False
    return (frame_kind == "black") == all(medals.values())


def grid_cell(x, y):
    """(col, row) of the card whose name label is at fractional (x, y), or None."""
    col = min(range(3), key=lambda c: abs(x * 1920 - (GRID_X0 + GRID_DX * c)))
    row = min(range(2), key=lambda r: abs(y * 1200 - (GRID_Y0 + GRID_DY * r)))
    if abs(x * 1920 - (GRID_X0 + GRID_DX * col)) > 150 or abs(y * 1200 - (GRID_Y0 + GRID_DY * row)) > 60:
        return None
    return col, row


# ---------------------------------------------------------------------------
# Medal audit: the cards are the source of truth when they read clearly.
#
# Until 2026-11-06 a scan only ever ADDED medals: removing them had made a
# loop on 2026-10-22 (the bot won Park Path Easy and Logs Easy, the next scan
# "removed" them, the planner played them again). But the misread table kept
# Apopalypse and Half Cash on maps the game shows without them, and nothing
# ever took them back, so those maps never got their black border. The owner
# asked on 2026-11-06 for the cards to correct the account both ways; the
# 2026-10-22 loop is kept out by three rules instead:
#   * a card that does not read confidently (card_is_confident) changes nothing;
#   * a medal is only removed when a second read moments later agrees;
#   * a medal the bot itself won in the last RECENT_WIN_GUARD is never removed.
# ---------------------------------------------------------------------------
RECENT_WIN_GUARD = 15 * 60   # seconds a medal the bot just won is safe from removal
HISTORY_TIME = "%Y-%m-%dT%H:%M:%S"   # AccountState.history "t" stamps (local time)


def recent_wins(history, now, window=RECENT_WIN_GUARD):
    """{(map, mode)} the bot won within `window` seconds before `now`, from
    AccountState.history."""
    out = set()
    for game in history:
        if not game.get("won"):
            continue
        try:
            t = time.mktime(time.strptime(game["t"], HISTORY_TIME))
        except (KeyError, TypeError, ValueError):
            continue
        if now - t <= window:
            out.add((game.get("map"), game.get("mode")))
    return out


def wants_second_look(record, medals, frame_kind):
    """Should the scan read this card again before the account is changed?
    Yes when the reading would take a medal away, or when the account says
    all 14 are earned while the frame is not black."""
    if frame_kind != "black" and all(record.get(m) for m in MODE_POINTS):
        return True
    return any(record.get(m) and medals.get(m) is False for m in MODE_POINTS)


def audit_card(record, reads, protected=()):
    """What one map's card changes in the account's medals for that map.

    record: {mode: earned} from the account. reads: [(medals, frame_kind)],
    the first read of the card and, when wants_second_look said so, a second
    one. protected: modes the bot itself won moments ago (recent_wins).
    Returns {"add": [...], "remove": [...], "guarded": [...], "kept": [...],
    "unsure": bool}: "guarded" are medals not removed because the bot just
    won them, "kept" ones not removed because no second read confirmed it."""
    out = {"add": [], "remove": [], "guarded": [], "kept": [], "unsure": False}
    if not reads or not all(card_is_confident(m, f) for m, f in reads) \
            or any(m != reads[0][0] for m, _ in reads[1:]):
        out["unsure"] = True    # unclear or the two reads differ: change nothing
        return out
    medals = reads[0][0]
    for mode in MODE_POINTS:
        if medals[mode] and not record.get(mode):
            out["add"].append(mode)
        elif record.get(mode) and not medals[mode]:
            if mode in protected:
                out["guarded"].append(mode)
            elif len(reads) < 2:
                out["kept"].append(mode)
            else:
                out["remove"].append(mode)
    return out
