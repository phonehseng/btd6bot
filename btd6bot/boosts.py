"""Double Cash and Fast Track: read them on map select, and know what they do.

Both are permanent Monkey Money purchases with an on/off toggle at the
bottom-left of the map-select screen, under CHANGE HERO (calibrated live,
v57.3, 1920x1200):

    [coins x2]    [check box]   Double Cash: every pop pays twice
    [fast clock]  [check box]   Fast Track: start later with more cash

A box shows a green check mark while the boost is on. An account that does
not own a boost shows no toggle, so it reads as off.

Neither works in CHIMPS (the game switches them off there, like powers -
MODE_RULES marks CHIMPS "no_powers"), and Double Cash changes nothing in a
mode without pop income (Deflation: MODE_RULES "income": False).
"""
import cv2
import numpy as np

# centre of each toggle's check box (fractions of the window)
TOGGLES = {"double_cash": (0.156, 0.889), "fast_track": (0.156, 0.942)}
BOX_HALF = (0.008, 0.012)                   # half width / half height of the check mark
CHECK_GREEN = ((40, 120, 140), (85, 255, 255))   # the check mark's green, OpenCV HSV
MIN_GREEN = 0.12                            # share of the box that must be green


def read(frame):
    """{"double_cash": bool, "fast_track": bool} from a map-select frame."""
    h, w = frame.shape[:2]
    out = {}
    for name, (fx, fy) in TOGGLES.items():
        x0, x1 = int((fx - BOX_HALF[0]) * w), int((fx + BOX_HALF[0]) * w)
        y0, y1 = int((fy - BOX_HALF[1]) * h), int((fy + BOX_HALF[1]) * h)
        box = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
        green = cv2.inRange(box, *CHECK_GREEN)
        out[name] = bool(np.count_nonzero(green) >= MIN_GREEN * green.size)
    return out


def double_cash_applies(boosts, mode):
    """Does Double Cash pay out in `mode` for an account with these boosts?"""
    from .strategy import MODE_RULES     # imported here: strategy imports a lot
    rules = MODE_RULES.get(mode, {})
    return bool(boosts.get("double_cash")) and rules.get("income", True) and not rules.get("no_powers")


# The first round of a Fast Track game, by the mode's reward tier
# (account.ModeInfo.reward_tier), as the bot's own games report it ("match:
# game starts at round N (Fast Track?)" in logs/bot.log, 2026-11-05): Easy 10,
# Medium 15, the Hard family 22, Impoppable 29. The skipped rounds' cash comes
# with it. Deflation keeps its round 31 (no income, nothing to skip) and CHIMPS
# allows no boost at all.
FAST_TRACK_START = {"easy": 10, "medium": 15, "hard": 22, "impoppable": 29}

# Modes the bot plays with Fast Track switched off (runner sets the toggle
# per game; the account still owns the boost). Impoppable (owner, 2026-11-10):
# from the round-29 start a game has eleven rounds of income to buy a whole
# MOAB answer, and 10 of Impoppable's 45 losses on record came on round 40
# (Sunset Gulch, Workshop, Ship Capture twice and Midnight Mansion that day
# alone). From round 6 the build grows into it.
FAST_TRACK_OFF_MODES = frozenset({"impoppable"})


def fast_track_wanted(mode, strategy=None):
    """Should the Fast Track toggle be on for a game in `mode` played with
    `strategy` (a strategy dict, optional)?

    Off in FAST_TRACK_OFF_MODES, and off for a build whose file says
    `fast_track: false`: a plan written for the mode's own first round (a
    tower or two that grow with the income) cannot be bought all at once
    in the one round a Fast Track start gives. abr_ninja_alch was such a
    build and went 2-8 with Fast Track on (2026-11-11: Bloody Puddles ABR
    lost on round 23 after one minute, Last Resort on round 28), while the
    builds tuned for the round-22 start (double_hp_sniper_sun) keep it."""
    if mode in FAST_TRACK_OFF_MODES:
        return False
    from .strategy import MODE_RULES     # imported here: strategy imports a lot
    if MODE_RULES.get(mode, {}).get("no_powers"):
        # CHIMPS forbids every boost. The toggle was switched ON for it at
        # 2026-11-12 17:45 (Ancient Portal CHIMPS, lost 9 s after its first
        # tower): only Impoppable was in FAST_TRACK_OFF_MODES, and nothing
        # asked whether the mode allows powers at all.
        return False
    return not (isinstance(strategy, dict) and strategy.get("fast_track") is False)


def fast_track_start(mode):
    """The round a game in `mode` begins at with Fast Track on, or None when
    Fast Track changes nothing there (the game forbids powers, the mode buys
    everything up front, the tier has no rounds to skip, or the bot plays the
    mode with the toggle off: FAST_TRACK_OFF_MODES)."""
    from .account import MODES
    from .strategy import MODE_RULES
    rules = MODE_RULES.get(mode, {})
    info = MODES.get(mode)
    if info is None or rules.get("no_powers") or rules.get("buy_all_upfront"):
        return None
    if not fast_track_wanted(mode):
        return None            # played with the toggle off (FAST_TRACK_OFF_MODES)
    start = FAST_TRACK_START.get(info.reward_tier)
    return start if start is not None and start > info.start_round else None
