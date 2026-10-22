"""Out-of-game account management: tower XP, Monkey Knowledge, hero, MM/level.

Everything here runs from the main menu (or the map/difficulty screen for the
hero) and goes back there when done. Buttons are found by their OCR text;
fixed positions are only fallbacks. Every flow is bounded (max attempts) and
gives up by walking back to the main menu with the back arrow.

Safety rules (on top of menus.FORBIDDEN):
  * never press Esc, never click "+" buttons, UNLOCK ALL, respec/reset, or
    anything showing a real-money price
  * Monkey Money is only spent on Monkey Knowledge nodes the planner order
    asks for (tier 4+ gates cost MM), and on heroes only when
    MetaConfig.allow_hero_purchase is True (default False)
  * purchase confirm dialogs are never closed with a generic "yes": they are
    confirmed explicitly after the price check, or cancelled

The caller owns persistence: Meta updates the AccountState in memory and the
caller should ``account.save()`` afterwards. ``account.selected_hero`` is set
as a dynamic attribute (AccountState has no such field and does not persist
it); runner.account_selected_hero() already reads it with getattr.

Every position or wording that still needs a live check is marked
``# VERIFY LIVE:``.
"""
from __future__ import annotations

import difflib
import logging
import re
import time
from dataclasses import dataclass

import cv2
import numpy as np

from . import planner
from . import towers as T
from .hud import parse_int, rec_text
from .menus import forbidden
from .vision import crop, norm

log = logging.getLogger("meta")

# ---------------------------------------------------------------------------
# Screen layout (fractions of the client area, 1920x1200 / 16:10)
# ---------------------------------------------------------------------------

BACK_ARROW = (0.044, 0.055)
# main menu bottom row: OCR labels sit at y~0.974, the round buttons above them
MAIN_BUTTONS = {                     # label x, fallback click position
    "monkeys": (0.132, 0.88),
    "heroes": (0.251, 0.88),
    "knowledge": (0.868, 0.88),
}
MAIN_LABEL_REGION = (0.0, 0.90, 1.0, 1.0)
MAIN_LABEL_DY = -0.08                # label -> button centre  # VERIFY LIVE
MM_REGION = (0.895, 0.025, 0.952, 0.09)      # "$175"; the "+" starts at x~0.952  # VERIFY LIVE at 1920x1200
MM_REGION_WIDE = (0.84, 0.0, 0.952, 0.11)    # VERIFY LIVE: big balances grow leftwards?
LEVEL_REGION = (0.095, 0.03, 0.125, 0.08)    # number inside the level star

# upgrade tree (same screen in game and from the Monkeys menu; see game.py)
try:
    from .game import Game as _G
except Exception:  # game.py is edited live; never let that break this module
    _G = None
TREE_ICON_X = getattr(_G, "TREE_ICON_X", (0.306, 0.424, 0.541, 0.659, 0.777))
# game.py's row y is the label line; the icon disc centre sits ~0.03 higher
TREE_ICON_Y = tuple(round(y - 0.03, 3) for y in getattr(_G, "TREE_ICON_Y", (0.33, 0.53, 0.73)))
TREE_UNLOCK = getattr(_G, "TREE_UNLOCK", (0.143, 0.683))
TREE_XP_REGION = (0.52, 0.01, 0.70, 0.065)     # "XP: 704" (the "+" at x~0.70 is never clicked)
TREE_TITLE_REGION = (0.28, 0.005, 0.54, 0.07)  # "TACK SHOOTER"  # VERIFY LIVE: long names fit
TREE_COST_REGION = (0.04, 0.685, 0.25, 0.72)   # "550 XP" line of the UNLOCK FOR button
TREE_LEFT_PANEL = (0.0, 0.2, 0.27, 0.8)        # selected upgrade name + UNLOCK FOR button
TREE_PREV = (0.2, 0.06)    # VERIFY LIVE: yellow arrows beside the header
TREE_NEXT = (0.8, 0.06)
ICON_HALF = (0.03, 0.045)                      # patch half-size inside an icon disc

# Monkeys menu: tower grid. VERIFY LIVE: whether portraits carry name labels,
# and the grid position used when no name can be read.
MONKEYS_GRID_FALLBACK = (0.2, 0.3)
# Order the top arrows of the upgrade tree cycle through.
# VERIFY LIVE: menu order, whether locked towers are skipped, wrap-around.
TOWER_ORDER = list(T.TOWERS)

# Monkey Knowledge screen. VERIFY LIVE: all of these.
MK_TABS = ("primary", "military", "magic", "support", "heroes")  # "powers" is in FORBIDDEN
MK_TAB_FALLBACK = {                  # VERIFY LIVE: tab buttons (guess: left column)
    "primary": (0.07, 0.20), "military": (0.07, 0.31), "magic": (0.07, 0.42),
    "support": (0.07, 0.53), "heroes": (0.07, 0.64),
}
MK_TREE_REGION = (0.15, 0.12, 0.72, 0.95)      # VERIFY LIVE: scrollable node area
MK_PANEL_REGION = (0.70, 0.10, 1.0, 0.98)      # VERIFY LIVE: info panel of the selected node
MK_POINTS_REGION = (0.30, 0.0, 1.0, 0.12)      # VERIFY LIVE: "Points: N" / "N Points" header
MK_BUY_WORDS = ("unlock", "learn", "acquire")   # VERIFY LIVE: purchase button text
MK_OWNED_WORDS = ("unlocked", "owned", "learned", "acquired", "active")  # VERIFY LIVE
# Calibrated node positions (tree, name) -> (x, y) after scrolling to top;
# filled in live when node names are not drawn on the tree.
MK_NODE_POS: dict[tuple[str, str], tuple[float, float]] = {}

# Hero picker. VERIFY LIVE: portrait grid on the left, details on the right.
HERO_GRID_REGION = (0.0, 0.10, 0.35, 0.98)
HERO_DETAIL_REGION = (0.35, 0.05, 1.0, 0.98)
CHANGE_HERO = (0.06, 0.93)           # map select / difficulty screen, label at y~0.976
HERO_SELECT_FALLBACK = (0.59, 0.57)  # btd6farmer CONFIRM_HERO (16:9) - search region only

CONFIRM_WORDS = ("confirm", "yes", "ok")
CANCEL_WORDS = ("cancel", "no", "close")   # modal dismissals; never a yes/ok

# never click these on meta screens (in addition to menus.FORBIDDEN)
META_FORBIDDEN = ("respec", "reset", "unlockall", "allmonkeys", "skin", "doublecash",
                  "instamonkey", "trophy", "getmore", "addmore")


# ---------------------------------------------------------------------------
# Monkey Knowledge data (docs/research_ui.md; tiers per bloonswiki nav)
# ---------------------------------------------------------------------------

MK_TREES: dict[str, dict[int, list[str]]] = {
    "primary": {
        1: ["Fast Tack Attacks", "Increased Lifespan", "Extra Dart Pops"],
        2: ["Poppy Blades", "Hard Tacks", "Fast Glue", "Fraggy Frags", "Cheap 'Rangs", "Crossbow Reach"],
        3: ["Big Inferno", "Icy Chill", "More Splatty Glue", "Budget Clusters", "Recurring 'Rangs",
            "Extra Bounce", "4 and 4", "Force vs Force"],
        4: ["So... Cold...", "Aviation Grade Glue", "Mega Mauler", "Hard Press", "Master Double Cross"],
        5: ["Big Cryo Blast", "Hypothermia", "Cheaper Solution", "Violent Impact",
            "Bionic Augmentation", "Long Turbo", "Come On Everybody!"],
        6: ["Bonus Glue Gunner", "More Cash", "Bonus Monkey!"],
    },
    "military": {
        1: ["Naval Upgrades", "Airforce Upgrades", "Elite Military Training", "Emergency Unlock"],
        2: ["Big Bunch", "Accelerated Aerodarts", "Ceramic Shock"],
        3: ["Breaking Ballistic", "Faster Takedowns", "Targeted Pineapples", "Rapid Razors",
            "Extra Burny Stuff", "Cheaper Maiming", "Gorgon Storm"],
        4: ["Quad Burst", "Trade Agreements", "Gun Coolant", "Paint Stripper", "Cross the Streams"],
        5: ["Flanking Maneuvers", "Wingmonkey", "Aeronautic Subsidy", "Charged Chinooks",
            "Budget Battery", "Master Defender"],
        6: ["Sub Admiral", "Military Conscription", "Advanced Logistics", "Door Gunner"],
        7: ["Big Bloon Sabotage"],
    },
    "magic": {
        1: ["Super Range", "Lingering Magic", "Magic Tricks"],
        2: ["Cheaper Doubles", "Heavy Knockback", "Hot Magic", "Speedy Brewing", "Mo' Monkey Money"],
        3: ["Diversion Tactics", "Strike Down the False", "Warm Oak", "Flame Jet", "Strong Tonic"],
        4: ["X-ray Ultra", "Cold Front", "Arcane Impale", "Acid Stability"],
        5: ["Deadly Tranquility", "There Can Be Only One", "Vine Rupture"],
        6: ["Tiny Tornadoes", "Mana Shield"],
    },
    "support": {
        1: ["Flat Pack Buildings", "One More Spike"],
        2: ["Insider Trades", "More Valuable Bananas", "First Last Line of Defense"],
        3: ["Bigger Banks", "Farm Subsidy", "Vigilant Sentries", "Monkey Education"],
        4: ["Backroom Deals", "Inland Revenue Streams", "Thicker Foams", "Very Shreddy", "To ARMS!"],
        5: ["Better Sell Deals", "Healthy Bananas", "Big Traps", "Hi-Value Mines",
            "Veteran Monkey Training", "Global Ability Cooldowns"],
        6: ["Bank Deposits", "Paragon of Power"],
    },
    "heroes": {
        1: ["Heroic Reach", "More 'Splody", "Ability Discipline"],
        2: ["Heroic Velocity", "Scholarships"],
        3: ["Quick Hands", "Self Taught Heroes", "Ability Mastery"],
        4: ["Hero Favors"],
        5: ["Empowered Heroes", "Big Bloon Blueprints"],
        6: ["Monkeys Together Strong", "Weak Point"],
    },
}
# points already invested in the tree before a node of that tier can be bought
# (VERIFY LIVE: magic T3/T4 unknown -> treated as no gate; the screen decides)
MK_GATES: dict[str, dict[int, int]] = {
    "primary": {3: 5, 4: 8, 5: 10, 6: 10},
    "military": {3: 4, 4: 8, 5: 8, 6: 14, 7: 14},
    "magic": {5: 8, 6: 8},
    "support": {3: 3, 4: 3, 5: 8, 6: 14},
    "heroes": {3: 3, 4: 3, 5: 8, 6: 8},
}
MK_TIER_MM = {4: 250, 5: 500, 6: 1000, 7: 1000}   # first purchase only
# known prerequisite chains (parents first; VERIFY LIVE where the wiki is unsure)
MK_CHAINS: dict[str, list[str]] = {
    "Mo' Monkey Money": ["Magic Tricks", "Speedy Brewing"],
    "Speedy Brewing": ["Magic Tricks"],
    "Monkey Education": ["Flat Pack Buildings", "More Valuable Bananas"],  # VERIFY LIVE: parent
    "Farm Subsidy": ["Flat Pack Buildings", "More Valuable Bananas"],
    "Self Taught Heroes": ["More 'Splody", "Scholarships"],
    "Quick Hands": ["Heroic Reach", "Heroic Velocity"],
    "Hero Favors": ["Heroic Reach", "Heroic Velocity", "Quick Hands", "More 'Splody",
                    "Scholarships", "Self Taught Heroes"],
    "Bonus Monkey!": ["Extra Dart Pops", "Crossbow Reach", "4 and 4", "Master Double Cross",
                      "Come On Everybody!"],
    "More Cash": ["Extra Dart Pops", "Crossbow Reach", "4 and 4", "Master Double Cross",
                  "Come On Everybody!", "Bonus Monkey!"],
    "Ceramic Shock": ["Elite Military Training"],
    "Big Bloon Sabotage": ["Naval Upgrades", "Breaking Ballistic", "Quad Burst", "Big Bunch",
                           "Faster Takedowns", "Trade Agreements", "Flanking Maneuvers",
                           "Sub Admiral", "Elite Military Training", "Ceramic Shock",
                           "Cheaper Maiming", "Master Defender"],
}
_MK_INDEX = {norm(n): (tree, tier, n) for tree, tiers in MK_TREES.items()
             for tier, names in tiers.items() for n in names}


# ---------------------------------------------------------------------------
# Pure helpers (tested offline in tests/test_meta_offline.py)
# ---------------------------------------------------------------------------

# VERIFY LIVE: blue = unlocked, green = unlockable now (inferred from upgrade_tree.jpg:
# Faster Shooting is blue and the selected green Even Faster Shooting offers
# "UNLOCK FOR 550 XP"; Super Range Tacks stays grey until Long Range Tacks is unlocked).
# Icon colours measured on docs/screens/upgrade_tree.jpg (OpenCV HSV, H 0-180):
#   unlocked   sky-blue disc   H~99  S~244 V~253  -> 64% of the patch passes BLUE
#   available  bright green    H~53  S~190-250 V~200 -> 52-68% pass GREEN, 0-1% BLUE
#   locked     dark grey-green / stone tier-5 face: S 20-70, V 105-127 -> <=5% pass either
# The hex background is the same hue family as "unlocked" (H~105, S 255) but
# darker: only 1.3% of background pixels reach V>=215, so the V floor keeps it
# out. 0.25 sits far from both the unlocked (0.64) and locked (<=0.05) values,
# leaving room for the white tack/dart art covering part of a disc.
BLUE_H = (88, 112)
GREEN_H = (35, 85)
SAT_MIN = 110
BLUE_V_MIN = 215
GREEN_V_MIN = 150
ICON_FRAC = 0.25


def icon_fractions(bgr_patch):
    """(blue_frac, green_frac) of saturated bright pixels in an icon patch."""
    if bgr_patch is None or bgr_patch.size == 0:
        return 0.0, 0.0
    hsv = cv2.cvtColor(bgr_patch, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    sat = s >= SAT_MIN
    blue = sat & (h >= BLUE_H[0]) & (h <= BLUE_H[1]) & (v >= BLUE_V_MIN)
    green = sat & (h >= GREEN_H[0]) & (h <= GREEN_H[1]) & (v >= GREEN_V_MIN)
    n = float(h.size)
    return float(np.count_nonzero(blue)) / n, float(np.count_nonzero(green)) / n


def icon_state(bgr_patch):
    """'unlocked' | 'available' (bright green: unlockable now) | 'locked'.

    Calibrated live on the Tack Shooter tree: unlocked icons are vivid (blue
    discs for tiers 1-3, full-colour art for tiers 4-5 such as Inferno Ring),
    locked ones are dull grey-green / khaki stone, and the next affordable tier
    is a bright green disc.
      unlocked  saturated >= 0.40, green ~0
      available saturated ~0.33-0.60, green ~= saturated
      locked    saturated <= 0.03
    """
    if bgr_patch is None or bgr_patch.size == 0:
        return "locked"
    hsv = cv2.cvtColor(bgr_patch, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    sat = float(np.mean((s > 150) & (v > 200)))  # vivid AND bright (not the hex background)
    green = float(np.mean((h > 35) & (h < 85) & (s > 150) & (v > 150)))
    if sat < 0.15:
        return "locked"
    if green >= 0.6 * sat:
        return "available"
    return "unlocked"


def classify_icon(bgr_patch):
    """True if the upgrade-tree icon is already unlocked (blue disc)."""
    return icon_state(bgr_patch) == "unlocked"


def icon_region(path, tier):
    """Patch region (fractions) inside the icon of path 1..3, tier 1..5."""
    x, y = TREE_ICON_X[tier - 1], TREE_ICON_Y[path - 1]
    return (x - ICON_HALF[0], y - ICON_HALF[1], x + ICON_HALF[0], y + ICON_HALF[1])


def tree_states(frame):
    """3x5 icon states of the upgrade tree in a full client frame."""
    return [[icon_state(crop(frame, icon_region(p, t))) for t in range(1, 6)] for p in range(1, 4)]


def tiers_from_states(states):
    """Unlocked tier per path = length of the leading run of 'unlocked' icons."""
    out = []
    for row in states:
        n = 0
        for st in row:
            if st not in ("unlocked", True):
                break
            n += 1
        out.append(n)
    return out


def parse_xp(text):
    """'XP: 1,234' / 'XP:704' / '704 XP' -> int, or None."""
    if not text:
        return None
    t = text.replace(" ", "")
    m = re.search(r"[Xx][Pp][:;.]?([0-9OoIl,.]+)", t) or re.search(r"([0-9OoIl,.]+)[Xx][Pp]", t)
    return parse_int(m.group(1)) if m else None


def parse_unlock_cost(text):
    """'UNLOCK FOR: 550 XP' / '550 XP' -> 550. None without an 'XP' marker."""
    if not text or "xp" not in text.lower():
        return None
    t = text.lower()
    t = t.split("for", 1)[1] if "for" in t else t
    m = re.search(r"([0-9oil,.]+)\s*xp", t)
    return parse_int(m.group(1)) if m else None


def parse_mm(text):
    """Monkey Money label ('$175', '$12,345', 'S175') -> int, or None."""
    if not text or is_real_money(text):
        return None
    v = parse_int(text.replace("+", ""))
    return v if v is not None and v < 100_000_000 else None


def parse_level(text):
    v = parse_int(text or "")
    return v if v is not None and 1 <= v <= 999 else None


_REAL_MONEY = re.compile(
    r"([$€£¥]\s*\d+[.,]\d{2}\b)|(\b\d+[.,]\d{2}\s*[$€£¥])|\b(usd|eur|gbp|aud|cad|nzd)\b"
    r"|\bus\$", re.I)


def is_real_money(text):
    """Price in a real currency ('$4.99', '4,99 €', 'USD'). Monkey Money ('$175') is not."""
    return bool(text) and bool(_REAL_MONEY.search(text))


def safe_text(text):
    """May a word with this text ever be clicked by the meta flows?"""
    if not text or text.strip() in ("+", "＋"):
        return False
    n = norm(text)
    if forbidden(text) or any(f in n for f in META_FORBIDDEN) or is_real_money(text):
        return False
    return True


def fuzzy_match(text, target, ratio=0.8):
    """OCR-tolerant comparison of two names (case/punctuation-insensitive)."""
    a, b = norm(text), norm(target)
    if not a or not b:
        return False
    if a == b or (len(b) >= 5 and b in a) or (len(a) >= 6 and a in b):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= ratio


def tower_id(name):
    """Account/planner tower id -> towers.TOWERS key ('beast' -> 'beast_handler')."""
    if name in T.TOWERS:
        return name
    alias = {"beast": "beast_handler"}.get(name)
    if alias:
        return alias
    return T.find_tower(name) or T.find_tower(planner.canon_tower(name).replace("_", " "))


def tower_from_title(text):
    """Header text of the upgrade tree -> towers.TOWERS key, or None."""
    if not text:
        return None
    tid = T.find_tower(text)
    if tid:
        return tid
    for k, t in T.TOWERS.items():
        if fuzzy_match(text, t["name"], 0.82):
            return k
    return None


def arrow_steps(cur, target, order=None):
    """(+1|-1, n): shortest way through the tree arrows from cur to target."""
    order = order or TOWER_ORDER
    if cur not in order or target not in order:
        return 1, len(order)
    i, j, n = order.index(cur), order.index(target), len(order)
    fwd = (j - i) % n
    back = (i - j) % n
    return (1, fwd) if fwd <= back else (-1, back)


def normalise_steps(priorities):
    """UpgradeStep (path 0..2) or (tower, path 1..3, tier) -> [(tower, path1, tier)]."""
    out = []
    for p in priorities or []:
        if hasattr(p, "tower"):
            out.append((p.tower, int(p.path) + 1, int(p.tier)))
        else:
            tower, path, tier = p[0], int(p[1]), int(p[2])
            out.append((tower, path, tier))
    return [s for s in out if 1 <= s[1] <= 3 and 1 <= s[2] <= 5]


def match_hero(text):
    """OCR'd hero name ('OBYN', 'Striker', 'Captain Churchill') -> hero id, or None."""
    n = norm(text)
    if len(n) < 3:
        return None
    for hid, h in T.HEROES.items():
        full = norm(h["name"])
        if n == full or n == norm(hid):
            return hid
    for hid, h in T.HEROES.items():
        parts = [norm(p) for p in re.split(r"[\s_]+", h["name"]) if len(norm(p)) >= 4]
        if any(n == p or (len(n) >= 5 and (n in p or p in n)) for p in parts):
            return hid
    for hid, h in T.HEROES.items():
        if fuzzy_match(text, h["name"], 0.85):
            return hid
    return None


def mk_info(name):
    """(tree, tier, canonical name) of an MK node, or (None, None, name)."""
    hit = _MK_INDEX.get(norm(name))
    return hit if hit else (None, None, name)


def mk_invested(account, tree):
    return sum(1 for n in account.mk_unlocked if mk_info(n)[0] == tree)


@dataclass
class MKCandidate:
    name: str
    tree: str
    tier: int | None
    mm_cost: int          # expected first-purchase MM cost (0 for tiers 1-3)
    reason: str


def mk_candidates(account, picks=None):
    """Ordered MK nodes to try: for each planner target (planner.choose_mk order)
    its known parents, gate fillers when the tree has too few points, then the
    target itself. The runtime buys the first one the screen allows."""
    if picks is None:
        picks = planner.choose_mk(account)[0]
    have = {norm(n) for n in account.mk_unlocked}
    out: list[MKCandidate] = []
    planned: set[str] = set()

    def add(name, tree, why):
        key = norm(name)
        if key in have or key in planned:
            return
        planned.add(key)
        _, tier, canon = mk_info(name)
        out.append(MKCandidate(canon, tree, tier, MK_TIER_MM.get(tier or 0, 0), why))

    def invested(tree):
        return mk_invested(account, tree) + sum(1 for c in out if c.tree == tree)

    def fill_gate(tree, tier, why):
        gate = MK_GATES.get(tree, {}).get(tier or 0, 0)
        fillers = list(planner.MK_TREE_ENTRY.get(tree, []))
        for t in (1, 2):
            fillers += MK_TREES.get(tree, {}).get(t, [])
        for f in fillers:
            if invested(tree) >= gate:
                break
            add(f, tree, f"gate filler ({tree} T{tier} needs {gate}) for {why}")

    for pick in picks:
        tree = pick.tree
        if tree not in MK_TREES:      # powers tab is never opened
            continue
        for name in MK_CHAINS.get(pick.name, []) + [pick.name]:
            if norm(name) in have or norm(name) in planned:
                continue
            ntree, tier, canon = mk_info(name)
            ntree = ntree or tree
            fill_gate(ntree, tier, pick.name)
            add(canon, ntree, f"{'target' if name == pick.name else 'parent'} of {pick.name}: {pick.reason}")
    return out


def parse_mk_points(words):
    """Available MK points from header words ('Points: 3', '3 Points', 'Available 3')."""
    txt = " ".join(w.text for w in sorted(words, key=lambda w: (round(w.y, 2), w.x)))
    for pat in (r"points?\s*[:：]?\s*(\d+)", r"(\d+)\s*(?:knowledge\s*)?points?",
                r"available\s*[:：]?\s*(\d+)"):
        m = re.search(pat, txt, re.I)
        if m:
            return int(m.group(1))
    return None


def mm_values(words):
    """Stand-alone numbers >= 100 in a panel/dialog (possible MM prices).

    None when a real-money price is visible anywhere (never buy then)."""
    vals = []
    for w in words:
        if is_real_money(w.text):
            return None
        if re.fullmatch(r"[$sS]?\s*[0-9][0-9,]*", w.text.strip()):
            v = parse_int(w.text)
            if v is not None and v >= 100:
                vals.append(v)
    return vals


def pick_mm_cost(values, expected):
    """MM price to check against: the expected tier price when it is on screen,
    else the expected price if no number shows, else the largest number seen
    (which then fails the expected-price check). None = refuse."""
    if values is None:
        return None
    expected = expected or 0
    if expected and expected in values:
        return expected
    if not values:
        return expected
    if not expected:
        # tier 1-3 nodes are free; numbers in the text are descriptions ("+$200")
        # VERIFY LIVE: free nodes show no price
        return 0
    return max(values)


def mk_mm_allowed(cost, account_mm, cfg, expected=None):
    """May an MK node costing ``cost`` MM be bought (planner-ordered node)?"""
    if cost is None:
        return False
    if cost == 0:
        return True
    if cost > cfg.max_mk_mm_per_node:
        return False
    if expected is not None and expected > 0 and cost != expected:
        return False   # unexpected price (respec? different node?) -> refuse
    if account_mm is None:
        return False
    return account_mm - cost >= cfg.mm_reserve


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class MetaConfig:
    allow_hero_purchase: bool = False   # spend MM on heroes (never real money)
    max_hero_mm: int = 7000
    max_mk_mm_per_node: int = 1000      # T6/T7 MK price; anything above is refused
    mm_reserve: int = 0                 # never let MM drop below this through MK
    max_unlocks: int = 20               # tower-XP unlock steps per call
    max_mk_buys: int = 12               # MK purchases per call
    back_tries: int = 8                 # back-arrow clicks to reach the main menu
    nav_tries: int = 3                  # retries for opening a screen


# ---------------------------------------------------------------------------
# Meta: screen flows
# ---------------------------------------------------------------------------

class Meta:
    def __init__(self, screen, inp, menus, account, config=None):
        self.s = screen
        self.inp = inp
        self.m = menus
        self.acc = account
        self.cfg = config or MetaConfig()
        self.sleep = time.sleep           # tests swap this for a no-op

    # -- low level -------------------------------------------------------------
    def _frame(self):
        return self.s.grab()

    def _read(self, scale=0.5):
        return self.m.read(scale=scale)

    def _words_in(self, region, words=None):
        words = self.m.words if words is None else words
        x0, y0, x1, y1 = region
        return [w for w in words if x0 <= w.x <= x1 and y0 <= w.y <= y1]

    def _find(self, *keys, region=None, exact=False):
        """First safe word matching any key (exact: whole normalised text)."""
        words = self._words_in(region) if region else self.m.words
        for k in [norm(k) for k in keys]:
            for w in words:
                n = norm(w.text)
                hit = (n == k) if exact else (n == k or (len(k) > 3 and k in n))
                if hit and safe_text(w.text):
                    return w
        return None

    def _click(self, x, y, wait=0.8, what=""):
        log.info("click %s at %.3f,%.3f", what, x, y)
        self.inp.click(x, y)
        self.sleep(wait)

    def _click_word(self, w, dy=0.0, wait=0.8):
        if w is None or not safe_text(w.text):
            return False
        self._click(w.x, w.y + dy, wait, repr(w.text))
        return True

    def _state(self):
        return self.m.identify()

    # -- navigation -------------------------------------------------------------
    def to_main_menu(self):
        """Back arrow until the main menu shows. Never used in a game/end screen."""
        for _ in range(self.cfg.back_tries):
            st = self._state()
            if st == "main_menu":
                return True
            if st in ("in_game", "defeat", "victory", "pause", "level_up", "tower_choice",
                      "restart_confirm", "overwrite"):
                log.warning("to_main_menu: on %s - not a meta screen, leaving it to the runner", st)
                return False
            # a modal (purchase confirm etc.) is closed by cancelling, never by a yes/ok
            w = self._find(*CANCEL_WORDS, exact=True)
            if w and w.conf > 0.6:
                self._click_word(w)
                continue
            self._click(*BACK_ARROW, wait=1.2, what="back arrow")
        ok = self._state() == "main_menu"
        if not ok:
            log.warning("could not get back to the main menu")
        return ok

    def _open_main_button(self, name, check):
        """Main menu -> MONKEYS/HEROES/KNOWLEDGE; check() verifies the new screen."""
        for attempt in range(self.cfg.nav_tries):
            if self._state() != "main_menu" and not self.to_main_menu():
                return False
            w = self._find(name, region=MAIN_LABEL_REGION)
            if w is not None:
                self._click_word(w, dy=MAIN_LABEL_DY, wait=1.5)
            else:
                self._click(*MAIN_BUTTONS[name], wait=1.5, what=name + " (fallback)")
            for _ in range(3):
                self._read()
                if check():
                    return True
                self.sleep(0.8)
            log.info("%s did not open (attempt %d)", name, attempt + 1)
        return False

    # -- main menu readings --------------------------------------------------
    def read_mm_and_level(self):
        """(monkey_money, level) from the main menu; syncs the account. None if unreadable."""
        if self._state() != "main_menu":
            return None, None
        mm, lvl = None, None
        reads = []
        for _ in range(2):   # two agreeing reads (guards against OCR blips)
            f = self._frame()
            m1 = parse_mm(rec_text(crop(f, MM_REGION))[0])
            l1 = parse_level(rec_text(crop(f, LEVEL_REGION))[0])
            reads.append((m1, l1))
            self.sleep(0.3)
        if reads[0][0] is not None and reads[0][0] == reads[1][0]:
            mm = reads[0][0]
        if reads[0][1] is not None and reads[0][1] == reads[1][1]:
            lvl = reads[0][1]
        if mm is None:   # wider OCR: "$" word left of the "+"
            ws = self.m.v.read(MM_REGION_WIDE, img=self._frame())
            vals = [parse_mm(w.text) for w in ws if w.text.strip().startswith(("$", "S", "s"))]
            vals = [v for v in vals if v is not None]
            mm = vals[0] if len(vals) == 1 else None
        cur = self.acc.player_level
        if lvl is not None and cur <= lvl <= cur + 4:
            for e in self.acc.sync_level(lvl):   # may add MM rewards: MM is set after
                log.info(e)
        elif lvl is not None and lvl != cur:
            # a big jump is either an OCR misread or a different save file;
            # runner.read_level() owns adopting a save file's level
            log.warning("main menu level %d vs account %d - not synced here", lvl, cur)
        if mm is not None:
            self.acc.monkey_money = mm
        log.info("main menu: MM %s, level %s", mm, lvl)
        return mm, lvl

    # -- upgrade tree -------------------------------------------------------------
    def _on_tree(self):
        return self.m.has("unlockall", "ingamecost", "appliestothismonkey", "unlockfor")

    def _on_monkeys_menu(self):
        # VERIFY LIVE: the Monkeys grid shows category headers / tower names
        if self._on_tree() or (self.m.has("play") and self.m.has("knowledge")):
            return False
        names = sum(1 for w in self.m.words if tower_from_title(w.text))
        return names >= 2 or (self.m.has("primary") and self.m.has("military"))

    def _tree_title(self, f=None):
        f = self._frame() if f is None else f
        return tower_from_title(rec_text(crop(f, TREE_TITLE_REGION))[0])

    def _tree_xp(self, f=None):
        f = self._frame() if f is None else f
        return parse_xp(rec_text(crop(f, TREE_XP_REGION))[0])

    def _unlock_cost(self, f=None):
        """XP price of the selected upgrade ('550 XP'), None when not offered."""
        f = self._frame() if f is None else f
        return parse_unlock_cost(rec_text(crop(f, TREE_COST_REGION))[0])

    def open_monkeys(self):
        return self._open_main_button("monkeys", lambda: self._on_monkeys_menu() or self._on_tree())

    def goto_tower_tree(self, tower):
        """Monkeys grid or any upgrade tree -> the tree of ``tower`` (verified by title)."""
        target = tower_id(tower)
        if target is None:
            log.warning("unknown tower %r", tower)
            return False
        self._read()
        if not self._on_tree():
            if not self._on_monkeys_menu():
                log.warning("goto_tower_tree: neither the Monkeys grid nor a tree is showing")
                return False
            # Monkeys grid: click the tower's name, else any tower, else a fallback slot
            want = T.TOWERS[target]["name"]
            w = next((w for w in self.m.words if fuzzy_match(w.text, want) and safe_text(w.text)), None)
            if w is None:
                w = next((w for w in self.m.words if tower_from_title(w.text) and safe_text(w.text)), None)
            # VERIFY LIVE: the portrait sits above its name label
            if w is not None:
                self._click_word(w, dy=-0.05, wait=1.5)
            else:
                self._click(*MONKEYS_GRID_FALLBACK, wait=1.5, what="grid fallback")
            self._read()
            if not self._on_tree():
                log.warning("upgrade tree did not open for %s", tower)
                return False
        cur = self._tree_title()
        if cur == target:
            return True
        step, n = arrow_steps(cur, target)
        for _ in range(min(n, len(TOWER_ORDER)) + 2):
            self._click(*(TREE_NEXT if step > 0 else TREE_PREV), wait=0.9, what="tree arrow")
            cur = self._tree_title()
            if cur == target:
                return True
        log.warning("could not reach the %s tree (last title %s)", tower, cur)
        return False

    def _unlock_icon(self, tower, path, tier):
        """On the tower's tree: unlock (path 1..3, tier). True / False / 'have' (already)."""
        f = self._frame()
        state = icon_state(crop(f, icon_region(path, tier)))
        if state == "unlocked":
            self.acc.unlock_upgrade(tower, path - 1, tier)
            return "have"
        if state == "locked":
            log.info("%s path %d tier %d not unlockable yet (prerequisite)", tower, path, tier)
            return False
        x, y = TREE_ICON_X[tier - 1], TREE_ICON_Y[path - 1]
        self._click(x, y, wait=0.9, what=f"{tower} p{path}t{tier} icon")
        have = need = None
        for _ in range(3):
            f = self._frame()
            have = self._tree_xp(f)
            need = self._unlock_cost(f)
            if have is not None and need is not None:
                break
            self.sleep(0.6)
        log.info("tree %s p%d t%d: needs %s XP, have %s", tower, path, tier, need, have)
        if have is not None:
            self.acc.tower_xp[tower] = float(have)
        if have is None or need is None or have < need:
            return False
        # the UNLOCK FOR button must read as such (never UNLOCK ALL, bottom-right)
        self._read(scale=0.6)
        btn = self._find("unlockfor", "unlock", region=TREE_LEFT_PANEL)
        if btn is None:
            log.info("no UNLOCK FOR button in the left panel")
            return False
        self._click_word(btn, wait=1.0)
        f = self._frame()
        after = self._tree_xp(f)
        ok = classify_icon(crop(f, icon_region(path, tier))) or (after is not None and after <= have - need)
        if not ok:
            log.warning("unlock of %s p%d t%d not confirmed (xp %s -> %s)", tower, path, tier, have, after)
            return False
        self.acc.tower_xp[tower] = float(have)
        self.acc.unlock_upgrade(tower, path - 1, tier, cost=need)
        log.info("unlocked %s path %d tier %d for %d XP", tower, path, tier, need)
        return True

    def spend_tower_xp(self, priorities=None):
        """Unlock upgrades with tower XP in planner order. Returns [(tower, path1, tier, cost)]."""
        if priorities is None:
            priorities = planner.choose_upgrade_unlocks(self.acc)[0]
        steps = normalise_steps(priorities)[: self.cfg.max_unlocks]
        done = []
        if not steps:
            return done
        try:
            if not self.open_monkeys():
                return done
            blocked = set()      # (tower, path) whose lower tier failed
            bad_towers = set()
            cur = None
            for tower, path, tier in steps:
                if tower in bad_towers or (tower, path) in blocked:
                    continue
                if tower != cur:
                    if not self.goto_tower_tree(tower):
                        bad_towers.add(tower)
                        cur = None
                        # start over from a known screen before the next tower
                        if not (self.to_main_menu() and self.open_monkeys()):
                            break
                        continue
                    cur = tower
                res = self._unlock_icon(tower, path, tier)
                if res is True:
                    cost = self.acc.observed_upgrade_costs.get(tower, {}).get(f"{path - 1}-{tier}")
                    done.append((tower, path, tier, cost))
                elif res is False:
                    blocked.add((tower, path))
        finally:
            self.to_main_menu()
        return done

    def read_upgrade_state(self, tower, leave=True):
        """Classify the 15 icons of ``tower`` and sync account.unlocked_upgrades.

        Starts from the main menu, Monkeys grid or any upgrade tree. Returns
        [p1, p2, p3] or None."""
        try:
            self._read()
            if not self._on_tree() and not self._on_monkeys_menu() and not self.open_monkeys():
                return None
            if not self.goto_tower_tree(tower):
                return None
            self.sleep(0.4)
            f = self._frame()
            states = tree_states(f)
            tiers = tiers_from_states(states)
            xp = self._tree_xp(f)
            log.info("%s tree: %s -> %s (xp %s)", tower, states, tiers, xp)
            self.acc.unlocked_upgrades[tower] = tiers
            if xp is not None:
                self.acc.tower_xp[tower] = float(xp)
            return tiers
        finally:
            if leave:
                self.to_main_menu()

    def sync_upgrade_states(self, towers=None):
        """read_upgrade_state for several towers in one Monkeys-menu visit."""
        towers = sorted(towers or self.acc.unlocked_towers)
        out = {}
        try:
            for t in towers:
                r = self.read_upgrade_state(t, leave=False)
                if r is not None:
                    out[t] = r
        finally:
            self.to_main_menu()
        return out

    # -- Monkey Knowledge ---------------------------------------------------------
    def _on_mk(self):
        # VERIFY LIVE: header wording of the MK screen
        tabs = sum(1 for t in MK_TABS if self.m.has(t))
        return self.m.has("knowledge") and tabs >= 2 and not self.m.has("play")

    def open_knowledge(self):
        return self._open_main_button("knowledge", self._on_mk)

    def _read_mk_points(self):
        self._read(scale=0.6)
        return parse_mk_points(self._words_in(MK_POINTS_REGION))

    def _open_mk_tab(self, tree):
        if tree not in MK_TABS:
            return False
        # tab labels, preferably outside the info panel (its text may say "Primary")
        cands = [w for w in self.m.words if norm(w.text) == tree and safe_text(w.text)]
        cands.sort(key=lambda w: w.x >= MK_PANEL_REGION[0])
        w = cands[0] if cands else None
        if w is not None:
            self._click_word(w, wait=1.0)
        else:
            self._click(*MK_TAB_FALLBACK[tree], wait=1.0, what=f"{tree} tab (fallback)")
        self._read(scale=0.6)
        return self._on_mk()

    def _find_mk_node(self, cand, scrolls=4):
        """Locate a node by its name on the tree (scrolling), else a calibrated spot."""
        cx = (MK_TREE_REGION[0] + MK_TREE_REGION[2]) / 2
        cy = (MK_TREE_REGION[1] + MK_TREE_REGION[3]) / 2
        for i in range(scrolls + 1):
            self._read(scale=0.6)
            for w in self._words_in(MK_TREE_REGION):
                if fuzzy_match(w.text, cand.name) and safe_text(w.text):
                    return (w.x, w.y)
            if i < scrolls:
                self.inp.scroll(-3, cx, cy)   # VERIFY LIVE: wheel scrolls the tree
                self.sleep(0.5)
        self.inp.scroll(3 * scrolls, cx, cy)  # back to the top for calibrated positions
        self.sleep(0.5)
        return MK_NODE_POS.get((cand.tree, cand.name))

    def _buy_mk_node(self, cand):
        """Select and buy one node. Returns 'ok' | 'owned' | 'locked' | 'mm' | 'fail'."""
        if not self._open_mk_tab(cand.tree):
            return "fail"
        pos = self._find_mk_node(cand)
        if pos is None:
            log.info("MK node %r not found on the %s tab", cand.name, cand.tree)
            return "fail"
        self._click(*pos, wait=1.0, what=f"MK node {cand.name}")
        self._read(scale=0.6)
        panel = self._words_in(MK_PANEL_REGION)
        if not any(fuzzy_match(w.text, cand.name) for w in panel):
            log.info("MK panel does not show %r: %s", cand.name, [w.text for w in panel][:8])
            return "fail"
        if any(norm(w.text) in MK_OWNED_WORDS for w in panel):
            return "owned"
        btn = next((w for w in panel for k in MK_BUY_WORDS
                    if norm(w.text).startswith(k) and safe_text(w.text)), None)
        if btn is None:
            return "locked"
        values = mm_values(panel)
        if cand.tier is None:   # unknown node: any visible price counts
            cost = None if values is None else max(values, default=0)
            expected = None
        else:
            expected = cand.mm_cost
            cost = pick_mm_cost(values, expected)
        if not mk_mm_allowed(cost, self.acc.monkey_money, self.cfg, expected):
            log.info("MK %s: MM cost %s not allowed (have %s)", cand.name, cost, self.acc.monkey_money)
            return "mm"
        before = self._read_mk_points()
        self._click_word(btn, wait=1.0)
        # an MM node may ask for confirmation: confirm only the price we checked
        self._read(scale=0.6)
        conf = self._find(*CONFIRM_WORDS, exact=True)
        if conf is not None:
            dvals = mm_values(self.m.words)
            ok = dvals is not None and (not dvals or cost in dvals) and \
                mk_mm_allowed(cost, self.acc.monkey_money, self.cfg, expected)
            if ok:
                self._click_word(conf, wait=1.0)
            else:
                log.warning("MK confirm shows %s (checked price %s MM) - cancelling", dvals, cost)
                self._click_word(self._find(*CANCEL_WORDS, exact=True))
                return "mm"
        after = self._read_mk_points()
        panel = self._words_in(MK_PANEL_REGION)
        owned = any(norm(w.text) in MK_OWNED_WORDS for w in panel)
        if (before is not None and after is not None and after < before) or owned:
            self.acc.unlock_mk(cand.name, cost or 0)
            if after is not None:
                self.acc.mk_points = after
            log.info("bought MK %s (%s MM)", cand.name, cost or 0)
            return "ok"
        log.warning("MK purchase of %s not confirmed (points %s -> %s)", cand.name, before, after)
        return "fail"

    def buy_monkey_knowledge(self):
        """Spend MK points in planner order. Returns the names bought."""
        bought = []
        if self.acc.player_level < 30 and self.acc.mk_points <= 0:
            return bought
        if self.to_main_menu():
            self.read_mm_and_level()   # fresh MM balance before any MM-gated node
        try:
            if not self.open_knowledge():
                return bought
            pts = self._read_mk_points()
            if pts is not None:
                self.acc.mk_points = pts
            skip = set()
            for _ in range(self.cfg.max_mk_buys):
                if self.acc.mk_points <= 0:
                    break
                cands = [c for c in mk_candidates(self.acc) if c.name not in skip]
                if not cands:
                    break
                progressed = False
                for cand in cands[:6]:   # bounded look-ahead past blocked nodes
                    res = self._buy_mk_node(cand)
                    log.info("MK %s (%s): %s", cand.name, cand.reason, res)
                    if res == "ok":
                        bought.append(cand.name)
                        progressed = True
                        break
                    if res == "owned":   # save file already had it
                        if cand.name not in self.acc.mk_unlocked:
                            self.acc.mk_unlocked.append(cand.name)
                        progressed = True
                        break
                    skip.add(cand.name)
                if not progressed:
                    break
        finally:
            self.to_main_menu()
        return bought

    def survey_mk(self, scrolls=3):
        """Calibration aid: log every OCR word per MK tab and scroll (clicks tabs only)."""
        out = {}
        try:
            if not self.open_knowledge():
                return out
            for tree in MK_TABS:
                if not self._open_mk_tab(tree):
                    continue
                seen = []
                for i in range(scrolls + 1):
                    self._read(scale=0.6)
                    seen += [(w.text, round(w.x, 3), round(w.y, 3)) for w in self.m.words]
                    if i < scrolls:
                        self.inp.scroll(-3, 0.43, 0.5)
                        self.sleep(0.5)
                self.inp.scroll(3 * scrolls, 0.43, 0.5)
                out[tree] = seen
                log.info("MK %s: %s", tree, seen)
        finally:
            self.to_main_menu()
        return out

    # -- heroes ---------------------------------------------------------------------
    def _on_heroes(self):
        if self.m.has("play") and self.m.has("knowledge"):
            return False
        names = sum(1 for w in self.m.words if match_hero(w.text))
        return self.m.has("select", "selected") or names >= 2

    def _open_hero_picker(self):
        st = self._state()
        if st == "main_menu":
            return self._open_main_button("heroes", self._on_heroes), st
        if st in ("map_select", "difficulty", "mode_select"):
            w = self._find("change", "changehero", region=(0.0, 0.8, 0.25, 1.0))
            # VERIFY LIVE: label at (0.06, 0.976), portrait button above it
            if w is not None:
                self._click_word(w, dy=-0.04, wait=1.5)
            else:
                self._click(*CHANGE_HERO, wait=1.5, what="CHANGE HERO (fallback)")
            self._read()
            return self._on_heroes(), st
        if st == "hero_select" or (st == "unknown" and self._on_heroes()):
            return True, st
        return False, st

    def _hero_button(self):
        """(kind, word) of the hero action button: 'select' | 'selected' | 'buy' | None."""
        detail = self._words_in(HERO_DETAIL_REGION)
        for w in detail:
            n = norm(w.text)
            if n in ("selected", "equipped"):
                return "selected", w
        for w in detail:
            if norm(w.text) == "select" and safe_text(w.text):
                return "select", w
        for w in detail:   # an MM price button: digits only (e.g. "2,500")
            t = w.text.strip()   # VERIFY LIVE: unowned heroes show an MM price button
            if re.fullmatch(r"[0-9][0-9,]{2,}", t) and not is_real_money(t) and (parse_int(t) or 0) >= 1000:
                return "buy", w
        return None, None

    def select_hero(self, hero_id):
        """Equip ``hero_id`` via HEROES / CHANGE HERO. Returns True when equipped."""
        if hero_id not in T.HEROES:
            log.warning("unknown hero %r", hero_id)
            return False
        name = T.HEROES[hero_id]["name"]
        ok, origin = self._open_hero_picker()
        if not ok:
            log.warning("hero picker did not open (from %s)", origin)
            if origin == "main_menu":
                self.to_main_menu()
            return False
        equipped = False
        try:
            for attempt in range(4):
                self._read()
                # VERIFY LIVE: names under the portraits; else scroll the grid
                w = next((w for w in self._words_in(HERO_GRID_REGION)
                          if match_hero(w.text) == hero_id and safe_text(w.text)), None)
                if w is None:
                    self.inp.scroll(-3, 0.15, 0.55)
                    self.sleep(0.6)
                    continue
                self._click_word(w, dy=-0.04, wait=1.0)   # portrait above the label
                self._read()
                detail = self._words_in(HERO_DETAIL_REGION)
                if not any(match_hero(d.text) == hero_id for d in detail):
                    log.info("hero detail does not show %s", name)
                    continue
                kind, btn = self._hero_button()
                if kind == "selected":
                    equipped = True
                    break
                if kind == "buy":
                    if not self._buy_hero(hero_id, btn):
                        break
                    self._read()
                    kind, btn = self._hero_button()
                if kind == "select":
                    self._click_word(btn, wait=1.0)
                    self._read()
                    k2, _ = self._hero_button()
                    equipped = k2 == "selected" or (k2 is None and not self._find("select", exact=True))
                    break
                log.info("no SELECT button for %s (%s)", name, kind)
                break
        finally:
            self._click(*BACK_ARROW, wait=1.2, what="back arrow")
            if origin == "main_menu":
                self.to_main_menu()
            else:
                back = self._state()
                if back != origin:
                    log.warning("after the hero picker: %s (came from %s)", back, origin)
        if equipped:
            self.acc.selected_hero = hero_id   # dynamic attribute, not persisted
            log.info("hero %s equipped", hero_id)
        return equipped

    def _buy_hero(self, hero_id, btn):
        """Monkey Money hero purchase; only with cfg.allow_hero_purchase."""
        price = parse_int(btn.text)
        if not self.cfg.allow_hero_purchase:
            log.info("hero %s costs %s MM - purchase disabled", hero_id, price)
            return False
        if price is None or price > self.cfg.max_hero_mm or price > (self.acc.monkey_money or 0):
            log.info("hero %s: price %s not affordable/allowed (MM %s)", hero_id, price, self.acc.monkey_money)
            return False
        self._click_word(btn, wait=1.0)
        self._read()
        conf = self._find(*CONFIRM_WORDS, exact=True)
        dialog = mm_values(self.m.words)
        if conf is None or dialog is None or price not in dialog:
            log.warning("hero confirm dialog unexpected (%s MM) - cancelling", dialog)
            self._click_word(self._find(*CANCEL_WORDS, exact=True))
            return False
        self._click_word(conf, wait=1.5)
        self.acc.unlocked_heroes.add(hero_id)
        self.acc.monkey_money = (self.acc.monkey_money or 0) - price
        log.info("bought hero %s for %d MM", hero_id, price)
        return True
