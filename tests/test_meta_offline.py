"""Offline tests for btd6bot.meta: pure helpers plus a simulated upgrade-tree
flow with fake screen/input/menus. Run: python tests/test_meta_offline.py
(also collectable by pytest). Never touches the game, mouse or keyboard."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from btd6bot import meta as M  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402
from btd6bot.menus import Menus  # noqa: E402
from btd6bot.planner import MKPick, UpgradeStep  # noqa: E402
from btd6bot.vision import Word  # noqa: E402


def _hsv_patch(h, s, v, size=(40, 40)):
    hsv = np.zeros((size[0], size[1], 3), np.uint8)
    hsv[...] = (h, s, v)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def W(text, x, y, conf=0.95):
    return Word(text, x, y, 0.05, 0.03, conf)


# ----------------------------------------------------------------- icons

def test_classify_icon_synthetic():
    blue = _hsv_patch(99, 244, 253)      # unlocked disc (measured on upgrade_tree.jpg)
    green = _hsv_patch(54, 220, 203)     # unlockable now
    grey = _hsv_patch(60, 40, 105)       # locked
    stone = _hsv_patch(22, 63, 127)      # locked tier-5 stone face
    bg_dark = _hsv_patch(105, 255, 82)   # hex background
    bg_bright = _hsv_patch(105, 255, 186)
    assert M.classify_icon(blue) and M.icon_state(blue) == "unlocked"
    assert not M.classify_icon(green) and M.icon_state(green) == "available"
    for p in (grey, stone, bg_dark, bg_bright):
        assert M.icon_state(p) == "locked", M.icon_fractions(p)
    # half the disc covered by white/grey tack art is still unlocked
    art = blue.copy()
    art[:, :20] = (230, 230, 230)
    assert M.classify_icon(art)
    # a mostly-covered disc (15% blue) is not
    art[:, :34] = (230, 230, 230)
    assert not M.classify_icon(art)
    assert not M.classify_icon(np.zeros((0, 0, 3), np.uint8))


def test_classify_icon_real_screenshot():
    img = cv2.imread(str(ROOT / "docs" / "screens" / "upgrade_tree.jpg"))
    assert img is not None
    states = M.tree_states(img)
    U, A, L = "unlocked", "available", "locked"
    assert states == [[U, A, L, L, L], [A, L, L, L, L], [A, L, L, L, L]], states
    assert M.tiers_from_states(states) == [1, 0, 0]


def test_tiers_from_states():
    U, A, L = "unlocked", "available", "locked"
    assert M.tiers_from_states([[U, U, A, L, L], [L] * 5, [U, U, U, U, U]]) == [2, 0, 5]
    # a gap stops the count (tiers must be contiguous)
    assert M.tiers_from_states([[U, L, U, L, L], [A] * 5, [L] * 5]) == [1, 0, 0]
    assert M.tiers_from_states([[True, True, False, False, False]] * 3) == [2, 2, 2]


# ----------------------------------------------------------------- parsing

def test_parsers():
    assert M.parse_xp("XP: 1,234") == 1234
    assert M.parse_xp("XP:704") == 704
    assert M.parse_xp("XP: 7O4") == 704
    assert M.parse_xp("704 XP") == 704
    assert M.parse_xp("") is None and M.parse_xp("TACK") is None
    assert M.parse_unlock_cost("UNLOCK FOR: 550 XP") == 550
    assert M.parse_unlock_cost("550 XP") == 550
    assert M.parse_unlock_cost("Unlock for: 1,200XP") == 1200
    assert M.parse_unlock_cost("Ingame cost 190") is None
    assert M.parse_mm("$175") == 175
    assert M.parse_mm("$12,345") == 12345
    assert M.parse_mm("S175") == 175
    assert M.parse_mm("$4.99") is None
    assert M.parse_level("10") == 10 and M.parse_level("") is None and M.parse_level("0") is None
    assert M.parse_mk_points([W("Points:", 0.8, 0.05), W("3", 0.85, 0.05)]) == 3
    assert M.parse_mk_points([W("3 Points", 0.8, 0.05)]) == 3
    assert M.parse_mk_points([W("Knowledge", 0.5, 0.05)]) is None


def test_money_safety():
    for t in ("$4.99", "US$1.99", "4,99 €", "€2,99", "USD 9.99", "£0.79"):
        assert M.is_real_money(t), t
    for t in ("$175", "$1,830", "1,830/4,250", "250", "$12,345"):
        assert not M.is_real_money(t), t
    for t in ("+", "UNLOCK ALL", "Unlock All", "Respec", "Buy", "Store", "$4.99",
              "INSTAS + POWERS", "Powers", "Continue for"):
        assert not M.safe_text(t), t
    for t in ("UNLOCK FOR:", "Select", "MONKEYS", "KNOWLEDGE", "Cancel", "Primary"):
        assert M.safe_text(t), t


def test_mm_values_and_costs():
    cfg = M.MetaConfig()
    assert M.mm_values([W("250", 0.8, 0.8), W("Points 3", 0.8, 0.1), W("+10%", 0.8, 0.5)]) == [250]
    assert M.mm_values([W("$4.99", 0.5, 0.5)]) is None
    assert M.pick_mm_cost([], 250) == 250            # price not drawn: assume tier price
    assert M.pick_mm_cost([200, 250], 250) == 250    # "+$200" description + price
    assert M.pick_mm_cost([200], 1000) == 200        # -> fails the expected check below
    assert M.pick_mm_cost([200], 0) == 0             # free node, number is description
    assert M.pick_mm_cost(None, 250) is None
    assert M.mk_mm_allowed(0, 0, cfg)
    assert M.mk_mm_allowed(250, 300, cfg, expected=250)
    assert not M.mk_mm_allowed(250, 200, cfg, expected=250)       # cannot afford
    assert not M.mk_mm_allowed(200, 5000, cfg, expected=1000)     # unexpected price
    assert not M.mk_mm_allowed(2000, 99999, cfg)                  # respec price
    assert not M.mk_mm_allowed(None, 99999, cfg)
    assert not M.mk_mm_allowed(250, None, cfg, expected=250)
    assert not M.mk_mm_allowed(500, 600, M.MetaConfig(mm_reserve=200), expected=500)


# ----------------------------------------------------------------- names

def test_names():
    assert M.tower_id("beast") == "beast_handler"
    assert M.tower_id("tack") == "tack"
    assert M.tower_id("Banana Farm") == "farm"
    assert M.tower_from_title("TACK SHOOTER") == "tack"
    assert M.tower_from_title("B0MB SHOOTER") == "bomb"
    assert M.tower_from_title("XP: 704") is None
    assert M.match_hero("OBYN") == "obyn"
    assert M.match_hero("Obyn Greenfoot") == "obyn"
    assert M.match_hero("STRIKER JONES") == "striker_jones"
    assert M.match_hero("Captain Churchill") == "churchill"
    assert M.match_hero("Select") is None and M.match_hero("ok") is None
    assert M.fuzzy_match("MO'MONKEY MONEY", "Mo' Monkey Money")
    assert M.fuzzy_match("Self Taught Heroe", "Self Taught Heroes")
    assert not M.fuzzy_match("More Cash", "Bonus Monkey!")


def test_arrow_steps_and_steps():
    order = ["a", "b", "c", "d", "e"]
    assert M.arrow_steps("a", "b", order) == (1, 1)
    assert M.arrow_steps("a", "e", order) == (-1, 1)
    assert M.arrow_steps("b", "b", order) == (1, 0)
    assert M.arrow_steps(None, "b", order) == (1, 5)
    s = M.normalise_steps([UpgradeStep("tack", 0, 1, 120, True, "x"), ("tack", 2, 3), ("x", 4, 1)])
    assert s == [("tack", 1, 1), ("tack", 2, 3)]


# ----------------------------------------------------------------- MK order

def test_mk_candidates_order():
    acc = AccountState(player_level=31, mk_points=2)
    c = M.mk_candidates(acc)
    assert [x.name for x in c[:3]] == ["Magic Tricks", "Speedy Brewing", "Mo' Monkey Money"]
    assert all(x.mm_cost == 0 for x in c[:3])
    assert all(x.tree != "powers" for x in c)
    for n in ("Magic Tricks", "Speedy Brewing", "Mo' Monkey Money"):
        acc.unlock_mk(n)
    c = M.mk_candidates(acc)
    names = [x.name for x in c]
    assert names[0] == "Extra Dart Pops", names[:5]
    # "4 and 4" (primary T3) needs 5 primary points first
    i = names.index("4 and 4")
    assert sum(1 for x in c[:i] if x.tree == "primary") >= 5, names[:i]
    by = {x.name: x for x in c}
    assert by["Master Double Cross"].mm_cost == 250
    assert by["Come On Everybody!"].mm_cost == 500
    assert by["More Cash"].mm_cost == 1000
    assert names.index("Bonus Monkey!") < names.index("More Cash")
    # no duplicates, nothing already owned
    assert len(names) == len(set(names))
    assert "Magic Tricks" not in names
    # explicit picks
    c = M.mk_candidates(AccountState(), [MKPick("Monkey Education", "support", "xp")])
    assert [x.name for x in c][-1] == "Monkey Education"
    assert sum(1 for x in c[:-1] if x.tree == "support") >= 3


# ----------------------------------------------------------------- fakes

class FakeInput:
    def __init__(self, on_click=None):
        self.clicks = []
        self.scrolls = []
        self.on_click = on_click

    def click(self, fx, fy, hold=0.07):
        self.clicks.append((round(fx, 3), round(fy, 3)))
        if self.on_click:
            self.on_click(fx, fy)

    def scroll(self, clicks, fx=0.5, fy=0.5):
        self.scrolls.append(clicks)

    def press(self, key, hold=0.05):
        raise AssertionError("meta must not press keys")


class FakeMenus(Menus):
    """Real identify()/has()/find() over scripted OCR words."""

    def __init__(self, words_fn):
        super().__init__(screen=None, inp=None)
        self.words_fn = words_fn

    def read(self, scale=0.5):
        self.words = list(self.words_fn())
        return self.words

    def in_game(self):
        return False


MAIN_WORDS = [W("PLAY", 0.5, 0.974), W("MONKEYS", 0.132, 0.974), W("HEROES", 0.251, 0.974),
              W("KNOWLEDGE", 0.868, 0.974), W("$175", 0.926, 0.056)]


def _new_meta(words_fn, on_click=None, account=None, screen=None, cls=M.Meta):
    inp = FakeInput(on_click)
    meta = cls(screen, inp, FakeMenus(words_fn), account or AccountState())
    meta.sleep = lambda s: None
    return meta, inp


def test_to_main_menu_bounded():
    unknown = [W("something", 0.5, 0.5)]
    meta, inp = _new_meta(lambda: unknown)
    assert meta.to_main_menu() is False
    assert len(inp.clicks) == meta.cfg.back_tries
    assert set(inp.clicks) == {M.BACK_ARROW}
    # never acts on a game/end screen
    defeat = [W("DEFEAT", 0.5, 0.2), W("Continue", 0.7, 0.75)]
    meta, inp = _new_meta(lambda: defeat)
    assert meta.to_main_menu() is False and inp.clicks == []
    # already there: no clicks
    meta, inp = _new_meta(lambda: MAIN_WORDS)
    assert meta.to_main_menu() is True and inp.clicks == []
    # a confirm modal is cancelled, never confirmed
    state = {"modal": True}
    modal = [W("Are you sure?", 0.5, 0.4), W("Yes", 0.6, 0.6), W("Cancel", 0.4, 0.6)]

    def click(x, y):
        state["modal"] = False
        assert (round(x, 2), round(y, 2)) == (0.4, 0.6), (x, y)

    meta, inp = _new_meta(lambda: modal if state["modal"] else MAIN_WORDS, click)
    assert meta.to_main_menu() is True and len(inp.clicks) == 1


def test_hero_purchase_disabled_by_default():
    meta, inp = _new_meta(lambda: [])
    assert meta.cfg.allow_hero_purchase is False
    assert meta._buy_hero("adora", W("5,000", 0.6, 0.8)) is False
    assert inp.clicks == []


# -------------------------------------------- simulated upgrade-tree flow

COL = {"unlocked": (99, 244, 253), "available": (54, 220, 203), "locked": (60, 40, 105)}
TOWERS_SIM = ["dart", "boomerang", "bomb", "tack"]


class TreeSim:
    """Main menu -> Monkeys grid -> per-tower upgrade tree, driven by clicks."""

    def __init__(self, xp, tiers):
        self.screen = "main"
        self.tower = None
        self.xp = dict(xp)
        self.tiers = {t: list(v) for t, v in tiers.items()}
        self.selected = None
        self.cost = 300

    # -- what the game shows
    def words(self):
        if self.screen == "main":
            return MAIN_WORDS
        if self.screen == "grid":
            return [W("PRIMARY", 0.3, 0.12), W("MILITARY", 0.6, 0.12),
                    W("Dart Monkey", 0.1, 0.35), W("Tack Shooter", 0.4, 0.35)]
        ws = [W("UNLOCK ALL", 0.9, 0.955), W("Applies to this Monkey only.", 0.9, 0.985),
              W("Ingame cost", 0.12, 0.75)]
        if self.selected and self.state(*self.selected) == "available":
            ws += [W("UNLOCK FOR:", 0.143, 0.672), W(f"{self.cost} XP", 0.143, 0.70)]
        return ws

    def state(self, path, tier):
        have = self.tiers.setdefault(self.tower, [0, 0, 0])[path - 1]
        return "unlocked" if tier <= have else "available" if tier == have + 1 else "locked"

    def frame(self, region=None):
        img = np.zeros((600, 960, 3), np.uint8)
        if self.screen == "tree":
            img[...] = _hsv_patch(105, 255, 82, (600, 960))
            for p in (1, 2, 3):
                for t in range(1, 6):
                    x, y = M.TREE_ICON_X[t - 1], M.TREE_ICON_Y[p - 1]
                    color = _hsv_patch(*COL[self.state(p, t)], (1, 1))[0, 0].tolist()
                    cv2.circle(img, (int(x * 960), int(y * 600)), 44, color, -1)
        return img

    # -- what a click does
    def click(self, x, y):
        # safety: never UNLOCK ALL (bottom-right) or the XP "+" (0.70, 0.035)
        assert not (x > 0.8 and y > 0.9), ("UNLOCK ALL clicked", x, y)
        assert not (abs(x - 0.70) < 0.02 and y < 0.07), ("XP + clicked", x, y)
        if self.screen == "main":
            if abs(x - 0.132) < 0.03 and 0.85 < y < 0.98:
                self.screen = "grid"
            return
        if self.screen == "grid":
            if (x, y) == M.BACK_ARROW:
                self.screen = "main"
            elif y < 0.4:
                self.screen = "tree"
                self.tower = "dart" if x < 0.25 else "tack"
                self.selected = None
            return
        if (x, y) == M.BACK_ARROW:
            self.screen = "grid"
        elif (x, y) in (M.TREE_NEXT, M.TREE_PREV):
            i = TOWERS_SIM.index(self.tower)
            self.tower = TOWERS_SIM[(i + (1 if x > 0.5 else -1)) % len(TOWERS_SIM)]
            self.selected = None
        elif abs(x - 0.143) < 0.05 and 0.64 < y < 0.72 and self.selected:
            p, t = self.selected
            if self.state(p, t) == "available" and self.xp[self.tower] >= self.cost:
                self.xp[self.tower] -= self.cost
                self.tiers[self.tower][p - 1] = t
        else:
            for p in (1, 2, 3):
                for t in range(1, 6):
                    if (round(x, 3), round(y, 3)) == (M.TREE_ICON_X[t - 1], M.TREE_ICON_Y[p - 1]):
                        self.selected = (p, t)


class SimMeta(M.Meta):
    """OCR of the header/cost lines comes from the simulator instead of RapidOCR."""
    sim: TreeSim = None

    def _tree_title(self, f=None):
        return self.sim.tower if self.sim.screen == "tree" else None

    def _tree_xp(self, f=None):
        return self.sim.xp.get(self.sim.tower) if self.sim.screen == "tree" else None

    def _unlock_cost(self, f=None):
        sel = self.sim.selected
        if self.sim.screen == "tree" and sel and self.sim.state(*sel) == "available":
            return self.sim.cost
        return None


class SimScreen:
    def __init__(self, sim):
        self.sim = sim

    def grab(self, region=None):
        return self.sim.frame(region)


def test_spend_tower_xp_simulated():
    sim = TreeSim(xp={"tack": 700, "bomb": 100, "dart": 0}, tiers={"tack": [1, 0, 0]})
    acc = AccountState()
    acc.unlocked_towers |= {"tack", "bomb"}
    SimMeta.sim = sim
    meta, inp = _new_meta(sim.words, sim.click, acc, SimScreen(sim), cls=SimMeta)
    steps = [("tack", 1, 1), ("tack", 1, 2), ("tack", 2, 1), ("tack", 2, 2), ("tack", 3, 1),
             ("bomb", 1, 1)]
    done = meta.spend_tower_xp(steps)
    # 700 XP at 300 each: two unlocks, then out of XP
    assert done == [("tack", 1, 2, 300), ("tack", 2, 1, 300)], done
    assert sim.tiers["tack"] == [2, 1, 0]
    assert acc.unlocked_upgrades["tack"] == [2, 1, 0]
    assert acc.tower_xp["tack"] == 100.0
    assert acc.observed_upgrade_costs["tack"] == {"0-2": 300, "1-1": 300}
    assert acc.unlocked_upgrades.get("bomb", [0, 0, 0]) == [0, 0, 0]   # 100 < 300
    assert sim.screen == "main"                                       # back home
    assert len(inp.clicks) < 60


def test_read_upgrade_state_simulated():
    sim = TreeSim(xp={"tack": 50}, tiers={"tack": [2, 0, 3]})
    acc = AccountState()
    SimMeta.sim = sim
    meta, inp = _new_meta(sim.words, sim.click, acc, SimScreen(sim), cls=SimMeta)
    assert meta.read_upgrade_state("tack") == [2, 0, 3]
    assert acc.unlocked_upgrades["tack"] == [2, 0, 3]
    assert acc.tower_xp["tack"] == 50.0
    assert sim.screen == "main"


if __name__ == "__main__":
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print("all tests passed")
