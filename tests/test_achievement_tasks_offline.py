"""Offline checks for the small achievement routines: btd6bot/achtasks.py
(wanted cards, daily caps, click allow-list), powers.py (Powers / Instas in
a game), powershop.py (buying a Power with Monkey Money), heroskin.py
(Lookin fab) and quests.py (First Steps look).

Fixtures are crops of the bot's own recordings (1280x800):
  powers_side_normal.jpg  right panel of a normal game, Powers button lit
                          (rec_20261107_151000.mkv 0:30, Downstream Half Cash)
  powers_side_chimps.jpg  the same in CHIMPS, the button crossed out
                          (rec_20261107_173100.mkv 0:10)
  skins_quincy.jpg        HEROES screen, Quincy: two skins priced 2,500 MM
                          (rec_20261107_150700.mkv 0:36)
  skins_obyn.jpg          HEROES screen, Obyn: three skins with a "New" ribbon
                          hiding their price (0:39)
  achtasks_ocr_words.json OCR of two real screens (see OCR below)
  powers_panel_live.jpg / insta_panel_live.jpg  the right side of the first
                          live captures of the powers panel (2026-11-08 00:26)
No recording shows the power shop: that flow is driven with scripted OCR words.

Run: python tests/test_achievement_tasks_offline.py
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import achtasks as A  # noqa: E402
from btd6bot import heroskin as H  # noqa: E402
from btd6bot import powers as P  # noqa: E402
from btd6bot import powershop as S  # noqa: E402
from btd6bot import quests as Q  # noqa: E402
from btd6bot.vision import Word  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
SIZE = (800, 1280)
SIDE_CROP = (0.84, 0.0, 1.0, 1.0)
SKIN_CROP = (0.80, 0.0, 1.0, 0.70)
NOW = 1_794_100_000.0
# calibration screenshots of the flows go to a scratch folder, not logs/
A.CAPTURE_DIR = Path(tempfile.mkdtemp(prefix="ach_captures_"))


def _frame(name, crop):
    """A whole 1280x800 frame, black outside the fixture crop."""
    img = cv2.imread(str(FIX / name))
    assert img is not None, name
    f = np.zeros((*SIZE, 3), np.uint8)
    x0, y0 = int(crop[0] * SIZE[1]), int(crop[1] * SIZE[0])
    f[y0:y0 + img.shape[0], x0:x0 + img.shape[1]] = img[:SIZE[0] - y0, :SIZE[1] - x0]
    return f


def _w(text, x=0.9, y=0.5, conf=0.9):
    return Word(text, x, y, 0.05, 0.03, conf)


def _budget(tmp, clock=lambda: NOW):
    return A.Budget("ACC", path=Path(tmp) / "tasks.json", clock=clock)


class Inp:
    """Records clicks; has no press(): any key press would raise."""

    def __init__(self):
        self.clicks = []

    def click(self, fx, fy, *a, **kw):
        self.clicks.append((round(fx, 3), round(fy, 3)))

    def scroll(self, *a, **kw):
        pass

    def move(self, *a, **kw):
        pass


# -- achtasks ------------------------------------------------------------------------
def test_wanted_cards_from_the_scan():
    st = {"Power User": "progress", "Empowered": "progress", "You've Got the Power": "complete",
          "Lookin fab": "unknown", "First Steps": "collect"}
    assert A.wanted(A.POWER_CARDS, st) == ["Power User", "Empowered"]
    assert A.wanted((A.SKIN_CARD,), st) == ["Lookin fab"]
    assert A.wanted((A.FIRST_STEPS_CARD,), st) == []      # finished, reward waiting
    assert A.wanted(A.INSTA_CARDS, st) == []              # not read: not wanted


def test_real_scan_matches_the_catalog():
    """The planner's matcher finds the cards in the committed account scan."""
    from btd6bot import planner
    root = Path(__file__).resolve().parents[1]
    cat = planner._load_json_cached(str(root / "data" / "achievements.json"))
    scans = sorted((root / "data" / "accounts").glob("*.achievements.json"))
    assert scans
    st = A.card_statuses(cat, planner._load_json_cached(str(scans[0])))
    assert st, "no card matched"


def test_budget_caps_and_days():
    with tempfile.TemporaryDirectory() as tmp:
        t = [NOW]
        b = _budget(tmp, clock=lambda: t[0])
        assert b.allow("mm", A.MM_PER_DAY) and not b.allow("mm", A.MM_PER_DAY + 1)
        b.add("mm", 2900)
        assert b.left("mm") == 100 and not b.allow("mm", 101)
        t[0] += 86400                                     # next UTC day
        assert b.left("mm") == A.MM_PER_DAY
        b.set_flag("skin_equipped", {"hero": "obyn"})
        assert _budget(tmp).flag("skin_equipped") == {"hero": "obyn"}
        for _ in range(A.FAILURES_PER_DAY):
            b.add("powers_failures")
        assert b.resting("powers")


def test_counting_input_stops_at_the_click_cap():
    with tempfile.TemporaryDirectory() as tmp:
        b = _budget(tmp)
        b.add("clicks", A.CLICKS_PER_DAY - 1)
        inp = A.CountingInput(Inp(), b)
        inp.click(0.5, 0.5)
        try:
            inp.click(0.5, 0.5)
            raise AssertionError("cap not enforced")
        except A.CapReached:
            pass
        assert not hasattr(inp, "press")


def test_allow_list_never_takes_real_money():
    assert A.allowed_word(_w("ROAD SPIKES"), ("roadspikes",))
    assert not A.allowed_word(_w("ROAD SPIKES $0.99"), ("roadspikes099",))
    assert not A.allowed_word(_w("STARTER BUNDLE"), ("starterbundle",))
    assert not A.allowed_word(_w("Glue Trap"), ("roadspikes",))
    assert A.find_allowed([_w("YES", 0.4), _w("NO", 0.6)], ("no", "cancel")).text == "NO"


# -- powers: the button and the panel ---------------------------------------------------
# powers_panel_live.jpg / insta_panel_live.jpg: the right 16% (x >= 0.84) of
# logs/achievement_captures/powers_panel_20261108_002637.png and
# insta_panel_20261108_002642.png (first live run, Tricky Tracks Easy,
# 2026-11-08 00:26, 1920x1200).
BIG = (1200, 1920)
PANEL_CROP_X = 0.84


def _big(name):
    img = cv2.imread(str(FIX / name))
    assert img is not None, name
    f = np.zeros((*BIG, 3), np.uint8)
    x0 = int(PANEL_CROP_X * BIG[1])
    f[:, x0:x0 + img.shape[1]] = img[:BIG[0], :BIG[1] - x0]
    return f


# the words OCR read on those two screens (logs/bot.log, 2026-11-08 00:26)
LIVE_POWERS_WORDS = [_w("POWERS", 0.924, 0.077), _w("+", 0.93, 0.15), _w("22", 0.977, 0.683),
                     _w("InsTAMonKeYs", 0.925, 0.78)]
LIVE_INSTA_WORDS = [_w("POWERS", 0.924, 0.077)] + [_w(t, 0.95, 0.3 + 0.03 * i) for i, t in
                                                    enumerate(["9", "12", "14", "20", "12", "11", "19", "6",
                                                               "16", "9"])]


def test_powers_button_lit_in_a_normal_game_only():
    assert P.button_lit(_frame("powers_side_normal.jpg", SIDE_CROP))
    assert not P.button_lit(_frame("powers_side_chimps.jpg", SIDE_CROP))
    assert not P.button_lit(np.zeros((*SIZE, 3), np.uint8))


def test_panel_open_is_told_by_the_button_not_by_blue():
    """The powers panel is as blue as the tower list; the button tells them
    apart (bolt = closed, monkey face = open)."""
    assert P.panel_closed(_frame("powers_side_normal.jpg", SIDE_CROP))
    for name in ("powers_panel_live.jpg", "insta_panel_live.jpg"):
        assert P.tower_list_shown(_big(name)) and not P.panel_closed(_big(name)), name


def test_badges_on_the_live_powers_tab():
    f = _big("powers_panel_live.jpg")
    badges = P.find_badges(f)
    assert len(badges) == 1 and abs(badges[0][0] - 0.977) < 0.005 and abs(badges[0][1] - 0.683) < 0.005
    assert P.is_gold_tile(f, P.icon_of(badges[0]))         # the "INSTA MONKEYS" tile
    assert P.power_badges(f) == []                          # no Power hexagon carries a count
    assert P.on_powers_tab(f, LIVE_POWERS_WORDS) and P.on_powers_tab(f)


def test_badges_on_the_live_insta_tab():
    f = _big("insta_panel_live.jpg")
    badges = P.insta_badges(f)
    assert len(badges) == 10, badges                        # 9, 12, 14, 20, 12, 11, 19, 6, 16, 9
    xs = sorted({round(b[0], 2) for _, b in badges})
    assert xs == [0.91, 0.98], xs
    icon, badge = badges[0]
    assert abs(icon[0] - 0.892) < 0.006 and abs(icon[1] - 0.30) < 0.006
    assert not P.on_powers_tab(f, LIVE_INSTA_WORDS)


def test_classify_panel():
    assert P.classify_panel(LIVE_POWERS_WORDS) == "powers"
    assert P.classify_panel([_w("9")], _big("insta_panel_live.jpg")) == "powers"
    assert P.classify_panel([_w("0-2-2"), _w("x1")]) == "tiers"
    assert P.classify_panel([_w("Buy for"), _w("35"), _w("Monkey Money"), _w("Are you sure")]) == "shop"
    assert P.classify_panel([_w("$4.99")]) == "shop"
    assert P.classify_panel([_w("UPGRADES")]) == "unknown"
    assert P.read_count([_w("22")]) == 22 and P.read_count([]) is None


def test_pick_tier():
    tiers = [(_w("2-0-0"), (2, 0, 0)), (_w("0-2-2"), (0, 2, 2)), (_w("5-0-2"), (5, 0, 2))]
    assert P.pick_tier(tiers, want_t5=False)[1] == (2, 0, 0)
    assert P.pick_tier(tiers, want_t5=True)[1] == (5, 0, 2)
    assert P.pick_tier(tiers[:2], want_t5=True)[1] == (2, 0, 0)
    assert P.pick_tier([], False) is None


def _plan(mode="easy", p=0.9):
    return SimpleNamespace(mode_key=mode, p_win=p)


def test_plan_extras_gating():
    st = {"Power User": "progress", "Insta Century": "progress", "Instant Gratification": "progress"}
    with tempfile.TemporaryDirectory() as tmp:
        b = _budget(tmp)
        ex = P.plan_extras(_plan(), {}, "ACC", st, budget=b)
        assert ex and ex.want_powers and ex.want_instas and ex.want_t5
        assert P.plan_extras(_plan("chimps"), {}, "ACC", st, budget=b) is None
        assert P.plan_extras(_plan("hard"), {}, "ACC", st, budget=b) is None
        assert P.plan_extras(_plan("apopalypse"), {}, "ACC", st, budget=b) is None
        assert P.plan_extras(_plan(p=0.8), {}, "ACC", st, budget=b) is None
        assert P.plan_extras(_plan(), {"achievement": "Unsung Monkeys"}, "ACC", st, budget=b) is None
        assert P.plan_extras(_plan(), {}, "ACC", {"Power User": "complete"}, budget=b) is None
        po = P.plan_extras(_plan("primary_only"), {}, "ACC", st, budget=b)
        assert po.want_powers and not po.want_instas and not po.want_t5


# -- powers: the in-game flow on the live frames --------------------------------------
class FakeModel:
    def track_mask(self):
        m = np.zeros((40, 64), bool)
        m[20, 5:60] = True
        return m

    def known(self):
        return True

    def progress_full(self):
        return np.tile(np.linspace(0, 1, 64, dtype=np.float32), (40, 1))

    def track_weight(self):
        return self.track_mask().astype(np.float32)

    def cell_to_frac(self, cx, cy):
        return cx / 64 * 0.85, cy / 40

    def score_spots(self, r, avoid=()):
        c = np.zeros((40, 64), np.float32)
        c[10, 10] = c[30, 40] = c[12, 50] = 1.0
        return c

    def best_spots(self, cover, n=3):
        ys, xs = np.nonzero(cover > 0)
        return [(int(x), int(y), 1.0) for x, y in zip(xs, ys)][:n]


def _with_power_badge(frame):
    """The live Powers tab with the "22" badge copied onto the first blue
    hexagon (row 3, left): an owned Power as the game would mark it."""
    f = frame.copy()
    h, w = f.shape[:2]
    src = (0.977, 0.683)
    dst = (0.9109, 0.552)                   # badge spot of the hexagon at (0.892, 0.58)
    hw, hh = int(0.016 * w), int(0.025 * h)
    sx, sy, dx, dy = int(src[0] * w), int(src[1] * h), int(dst[0] * w), int(dst[1] * h)
    f[dy - hh:dy + hh, dx - hw:dx + hw] = frame[sy - hh:sy + hh, sx - hw:sx + hw]
    return f


class FakeGame:
    """The live frames: the closed tower list until POWERS_BUTTON is clicked,
    then `panel` (a function of the clicks so far), the tower list again
    after the next POWERS_BUTTON click. `holding`: answers for is_holding()."""

    def __init__(self, panel, holding=(False,)):
        self.inp = Inp()
        self.closed_frame = _frame("powers_side_normal.jpg", SIDE_CROP)
        self.panel = panel
        self.holding = list(holding)
        self.cancelled = self.closed = 0

    def _open(self):
        return self.inp.clicks.count(P.POWERS_BUTTON) % 2 == 1

    def fresh(self):
        return self.panel(self.inp.clicks) if self._open() else self.closed_frame

    def is_holding(self, f=None):
        return self.holding.pop(0) if len(self.holding) > 1 else self.holding[0]

    def cancel_hold(self):
        self.cancelled += 1

    def close_panels(self):
        self.closed += 1


class FakeMenus:
    """Side-panel reads pop `pages`; badge reads (small regions) get `count`."""

    def __init__(self, pages, count=()):
        self.pages = list(pages)
        self.count = list(count)
        self.v = self

    def read(self, region=None, img=None):
        if region == P.SIDEBAR:
            return self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
        return [_w(str(self.count.pop(0)))] if self.count else []


def _extras(tmp, **kw):
    b = _budget(tmp)
    kw.setdefault("want_powers", True)
    kw.setdefault("want_instas", False)
    return P.InGameExtras(b, sleep=lambda s: None, capture_dir=Path(tmp) / "cap", **kw), b


def _in_grid(pt):
    return P.GRID[0] <= pt[0] <= P.GRID[2] and P.GRID[1] <= pt[1] <= P.GRID[3]


def test_live_panel_without_owned_powers_clicks_nothing_in_it():
    with tempfile.TemporaryDirectory() as tmp:
        ex, b = _extras(tmp)
        live = _big("powers_panel_live.jpg")
        g = FakeGame(lambda clicks: live)
        res = ex.run(g, FakeMenus([LIVE_POWERS_WORDS]), FakeModel(), [])
        assert res["result"] == "done" and res["powers"] == [], res
        assert g.inp.clicks == [P.POWERS_BUTTON, P.POWERS_BUTTON], g.inp.clicks   # open, close
        assert b.flag("powers_seen")["owned"] == 0 and b.used("power_uses") == 0
        assert list((Path(tmp) / "cap").glob("powers_panel_*.png"))


def test_badged_instant_power_is_used_and_verified():
    with tempfile.TemporaryDirectory() as tmp:
        ex, b = _extras(tmp)
        live = _big("powers_panel_live.jpg")
        owned = _with_power_badge(live)
        icon = P.power_badges(owned)[0][0]
        # badged until its hexagon is clicked, then the badge is gone (count 1 -> 0)
        g = FakeGame(lambda clicks: live if (round(icon[0], 3), round(icon[1], 3)) in clicks else owned)
        res = ex.run(g, FakeMenus([LIVE_POWERS_WORDS], count=[1]), FakeModel(), [])
        assert res["result"] == "done" and len(res["powers"]) == 1, res
        assert b.used("power_uses") == 1
        assert [c for c in g.inp.clicks if _in_grid(c)] == [(round(icon[0], 3), round(icon[1], 3))]


def test_badged_power_on_the_cursor_goes_on_the_track():
    with tempfile.TemporaryDirectory() as tmp:
        ex, b = _extras(tmp)
        owned = _with_power_badge(_big("powers_panel_live.jpg"))
        g = FakeGame(lambda clicks: owned, holding=[True, False])
        res = ex.run(g, FakeMenus([LIVE_POWERS_WORDS]), FakeModel(), [])
        assert b.used("power_uses") >= 1, res
        track_y = 20 / 40
        assert any(abs(y - track_y) < 1e-3 for _, y in g.inp.clicks), g.inp.clicks


def test_power_that_changes_nothing_stops_the_routine():
    with tempfile.TemporaryDirectory() as tmp:
        ex, b = _extras(tmp)
        owned = _with_power_badge(_big("powers_panel_live.jpg"))
        g = FakeGame(lambda clicks: owned)
        res = ex.run(g, FakeMenus([LIVE_POWERS_WORDS], count=[3, 3]), FakeModel(), [])
        assert res["result"].startswith("bailed: Power slot 1 clicked but nothing changed"), res
        assert b.used("power_uses") == 0 and g.inp.clicks[-1] == P.POWERS_BUTTON


def test_purchase_question_is_declined_never_confirmed():
    with tempfile.TemporaryDirectory() as tmp:
        ex, b = _extras(tmp)
        owned = _with_power_badge(_big("powers_panel_live.jpg"))
        g = FakeGame(lambda clicks: owned)
        question = [_w("Buy this Power for", 0.5, 0.4), _w("35", 0.5, 0.45), _w("Monkey Money", 0.5, 0.47),
                    _w("YES", 0.6, 0.6), _w("NO", 0.4, 0.6)]
        res = ex.run(g, FakeMenus([LIVE_POWERS_WORDS, question]), FakeModel(), [])
        assert res["result"].startswith("bailed"), res
        assert (0.4, 0.6) in g.inp.clicks and (0.6, 0.6) not in g.inp.clicks
        assert b.used("power_uses") == 0 and b.used("powers_failures") == 1


def test_unreadable_panel_bails_and_closes():
    with tempfile.TemporaryDirectory() as tmp:
        ex, b = _extras(tmp)
        g = FakeGame(lambda clicks: np.zeros((*BIG, 3), np.uint8))
        res = ex.run(g, FakeMenus([[_w("???")]]), FakeModel(), [])
        assert res["result"].startswith("bailed"), res
        assert b.used("powers_failures") == 1
        assert g.inp.clicks.count(P.POWERS_BUTTON) == 2              # opened, then closed
        assert list((Path(tmp) / "cap").glob("powers_panel_*.png")), "no calibration capture"


def test_chimps_button_is_never_clicked():
    with tempfile.TemporaryDirectory() as tmp:
        ex, _ = _extras(tmp)
        g = FakeGame(lambda clicks: None)
        g.closed_frame = _frame("powers_side_chimps.jpg", SIDE_CROP)
        res = ex.run(g, FakeMenus([LIVE_POWERS_WORDS]), FakeModel(), [])
        assert res["result"] == "button not lit" and g.inp.clicks == []


def _insta_game(holding=(False,)):
    powers, instas = _big("powers_panel_live.jpg"), _big("insta_panel_live.jpg")
    label = (0.925, 0.78)
    return FakeGame(lambda clicks: instas if label in clicks else powers, holding=holding)


def test_insta_tower_list_without_tiers_places_nothing():
    """The step after a tower icon is not seen yet: no tier label, no placement."""
    with tempfile.TemporaryDirectory() as tmp:
        ex, b = _extras(tmp, want_powers=False, want_instas=True)
        g = _insta_game()
        counts = [9, 12, 14, 20, 12, 11, 19, 6, 16, 9]
        m = FakeMenus([LIVE_POWERS_WORDS, LIVE_INSTA_WORDS, [_w("SOMETHING", 0.9, 0.4)]], count=counts)
        res = ex.run(g, m, FakeModel(), [])
        assert res["result"] == "done" and res["instas"] == [], res
        bomb = P.insta_badges(_big("insta_panel_live.jpg"))[3][0]      # the 20
        assert g.inp.clicks == [P.POWERS_BUTTON, (0.925, 0.78), (round(bomb[0], 3), round(bomb[1], 3)),
                                P.POWERS_BUTTON], g.inp.clicks
        assert b.used("insta_uses") == 0
        assert list((Path(tmp) / "cap").glob("insta_tower_*.png"))


def test_insta_with_tier_labels_is_placed_lowest_first():
    with tempfile.TemporaryDirectory() as tmp:
        ex, b = _extras(tmp, want_powers=False, want_instas=True)
        g = _insta_game(holding=[True, False])
        tiers = [_w("3-0-0", 0.90, 0.3), _w("0-2-2", 0.96, 0.3)]
        m = FakeMenus([LIVE_POWERS_WORDS, LIVE_INSTA_WORDS, tiers], count=[9, 12])
        res = ex.run(g, m, FakeModel(), [])
        assert res["instas"] == ["3-0-0"], res
        assert b.used("insta_uses") == 1
        assert (0.9, 0.3) in g.inp.clicks and (0.96, 0.3) not in g.inp.clicks


def test_insta_t5_while_instant_gratification_is_wanted():
    with tempfile.TemporaryDirectory() as tmp:
        ex, b = _extras(tmp, want_powers=False, want_instas=True, want_t5=True)
        g = _insta_game(holding=[True, False])
        tiers = [_w("0-2-2", 0.90, 0.3), _w("5-0-2", 0.96, 0.3)]
        res = ex.run(g, FakeMenus([LIVE_POWERS_WORDS, LIVE_INSTA_WORDS, tiers]), FakeModel(), [])
        assert res["instas"] == ["5-0-2"], res


def test_track_points_lie_late_on_the_track():
    pts = P.track_points(FakeModel())
    assert len(pts) == P.TARGET_TRIES
    assert all(abs(y - 20 / 40) < 1e-6 for _, y in pts)
    assert all(x / 0.85 * 64 >= 0.55 * 64 - 1 for x, _ in pts)


# -- power shop -------------------------------------------------------------------------
def test_shop_due_only_with_no_owned_power():
    st = {"Power User": "progress"}
    with tempfile.TemporaryDirectory() as tmp:
        b = _budget(tmp)
        assert not S.is_due(b, st, NOW)[0]                       # panel never read
        b.set_flag("powers_seen", {"at": NOW - 60, "owned": ["roadspikes"]})
        assert not S.is_due(b, st, NOW)[0]
        b.set_flag("powers_seen", {"at": NOW - 60, "owned": []})
        assert S.is_due(b, st, NOW)[0]
        assert not S.is_due(b, {"Power User": "complete"}, NOW)[0]
        b.add("mm", A.MM_PER_DAY)
        assert not S.is_due(b, st, NOW)[0]


def test_read_price():
    name = _w("Road Spikes", 0.5, 0.4)
    words = [name, _w("35", 0.52, 0.5), _w("213,233", 0.95, 0.05), _w("x0", 0.55, 0.42)]
    w, v = S.read_price(words, name, limit=3000)
    assert v == 35
    assert S.read_price(words, name, limit=20) == (None, None)
    assert S.read_price([name, _w("0.99", 0.5, 0.5)], name, 3000) == (None, None)


class ShopMenus:
    """Scripted screens for the shop: identify() pops the next screen."""

    def __init__(self, screens):
        self.screens = list(screens)
        self.words = []

    def identify(self):
        name, self.words = self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]
        return name


def _shop(tmp, screens, mm=(1000, 965)):
    b = _budget(tmp)
    mms = list(mm)
    shop = S.PowerShop(SimpleNamespace(grab=lambda: np.zeros((8, 8, 3), np.uint8)), Inp(),
                       ShopMenus(screens), b, read_mm=lambda: mms.pop(0), sleep=lambda s: None)
    return shop, b


MAIN = ("main_menu", [_w("PLAY")])


def test_shop_buys_one_and_counts_the_real_spend():
    page = [_w("POWERS", 0.3, 0.1), _w("Road Spikes", 0.5, 0.4), _w("35", 0.5, 0.5)]
    confirm = [_w("Buy Road Spikes?", 0.5, 0.4), _w("35", 0.5, 0.5), _w("YES", 0.6, 0.65), _w("NO", 0.4, 0.65)]
    with tempfile.TemporaryDirectory() as tmp:
        shop, b = _shop(tmp, [MAIN, ("unknown", page), ("unknown", page), ("unknown", confirm),
                              ("unknown", [_w("PURCHASED")]), MAIN])
        res = shop.buy_one()
        assert res == "bought roadspikes 35", res
        assert b.used("mm") == 35 and b.used("purchases") == 1
        assert b.flag("powers_seen") is None
        assert (0.4, 0.65) not in shop.inp._inp.clicks


def test_shop_bails_on_real_money():
    page = [_w("Road Spikes", 0.5, 0.4), _w("$1.99", 0.5, 0.5), _w("SPECIAL OFFER", 0.5, 0.2)]
    with tempfile.TemporaryDirectory() as tmp:
        shop, b = _shop(tmp, [MAIN, ("unknown", page), MAIN])
        res = shop.buy_one()
        assert res.startswith("bailed"), res
        assert b.used("mm") == 0 and b.used("powershop_failures") == 1
        assert (0.5, 0.4) not in shop.inp._inp.clicks and (0.5, 0.5) not in shop.inp._inp.clicks


def test_shop_overspend_stops_buying_for_the_day():
    page = [_w("Road Spikes", 0.5, 0.4), _w("35", 0.5, 0.5)]
    with tempfile.TemporaryDirectory() as tmp:
        shop, b = _shop(tmp, [MAIN, ("unknown", page), ("unknown", page), ("unknown", []), MAIN],
                        mm=(1000, 500))
        shop.buy_one()
        assert b.resting("powershop") and b.used("mm") == 500


# -- hero skin --------------------------------------------------------------------------
def test_skin_icons_found_on_both_hero_screens():
    q = _frame("skins_quincy.jpg", SKIN_CROP)
    o = _frame("skins_obyn.jpg", SKIN_CROP)
    assert [H.has_icon(q, c) for c in H.slot_centres()] == [True, True, False, False]
    assert [H.has_icon(o, c) for c in H.slot_centres()] == [True, True, True, False]
    assert not any(H.in_banner(c) for c in H.slot_centres())


def test_priced_skin_words():
    assert H.priced([_w("2,500")])
    assert not H.priced([_w("New")])
    assert not H.priced([])



# Words OCR read from real screens (bot's Vision on the full frame):
#   quests_all         logs/achievement_captures/quests_20261107_180710.png
#                      (first live run: the Quests menu, ALL tab)
#   skin_page_unowned  rec_20261107_180600.mkv 0:52 - the page an Obyn skin
#                      icon opens: "MOUNTAIN GUARDIAN SKIN ... UNLOCK FOR: 2,500"
#   skin_page_obyn_ocean  logs/achievement_captures/skin_obyn_skin2_20261107_190033.png
#   skin_page_bundle      .../skin_obyn_skin3_20261107_190041.png: Obyn's third
#                      icon is a real-money bundle ("SKELETOR PRESTIGE PACK $12.99")
OCR = json.loads((FIX / "achtasks_ocr_words.json").read_text(encoding="utf-8"))


def _ocr(key):
    return [Word(t, x, y, 0.1, 0.03, c) for t, x, y, c in OCR[key]]


def test_skin_page_unowned_from_the_live_run():
    """The first live run read the hero screen's button region on this page
    and saw nothing; the page itself says UNLOCK FOR: 2,500."""
    assert H.skin_page(_ocr("skin_page_unowned")) == ("unowned", None)


def test_skin_page_button_words():
    def page(*button):
        return [_w("SOME SKIN", 0.5, 0.05), _w("$213.833", 0.9, 0.05)] + [_w(t, 0.5, 0.87) for t in button]
    assert H.skin_page(page("SELECT"))[0] == "select"
    assert H.skin_page(page("SELECTED"))[0] == "selected"
    assert H.skin_page(page("EQUIP"))[0] == "select"
    assert H.skin_page(page("USE"))[0] == "select"
    assert H.skin_page(page("UNLOCK FOR:", "2,500"))[0] == "unowned"
    assert H.skin_page(page())[0] == "unknown"
    # the word must be in the button region, not anywhere on the page
    assert H.skin_page([_w("SELECT", 0.5, 0.4)])[0] == "unknown"
    assert H.skin_page(page("SELECT") + [_w("SKIN BUNDLE $9.99", 0.5, 0.5)])[0] == "shop"


class FakePicker:
    def __init__(self, hero="obyn"):
        self.hero = hero
        self.meta = SimpleNamespace(_open_hero_picker=lambda: (True, "main_menu"),
                                    to_main_menu=lambda: True)

    def shown_hero(self):
        return self.hero

    def _find_and_equip(self, hero):
        self.hero = hero
        return True


def _equipper(tmp, frame, reads, hero="obyn"):
    """reads: OCR answers in order (price under an icon, then whole pages)."""
    b = _budget(tmp)
    reads = list(reads)
    menus = SimpleNamespace(v=SimpleNamespace(read=lambda region: reads.pop(0) if reads else []))
    eq = H.SkinEquipper(SimpleNamespace(grab=lambda: frame), Inp(), menus,
                        SimpleNamespace(unlocked_heroes={"obyn", "quincy"}, selected_hero="obyn"),
                        b, sleep=lambda s: None, picker=FakePicker(hero), capture_dir=Path(tmp) / "cap")
    return eq, b


def test_priced_skins_are_never_clicked():
    with tempfile.TemporaryDirectory() as tmp:
        q = _frame("skins_quincy.jpg", SKIN_CROP)
        eq, _ = _equipper(tmp, q, [[_w("2,500")], [_w("2,500")]], hero="quincy")
        assert eq.try_hero("quincy") == "none_owned"
        assert eq.inp._inp.clicks == []


def test_unowned_skin_pages_are_left_by_the_back_arrow():
    """The live run's case: three "New" skins, each opening an UNLOCK FOR page."""
    with tempfile.TemporaryDirectory() as tmp:
        o = _frame("skins_obyn.jpg", SKIN_CROP)
        page = _ocr("skin_page_unowned")
        eq, b = _equipper(tmp, o, [[_w("New")], page, [_w("New")], page, [_w("New")], page])
        assert eq.try_hero("obyn") == "none_owned"
        clicks = eq.inp._inp.clicks
        slots = [(H.SKIN_X, round(y, 3)) for _, y in H.slot_centres(3)]
        assert clicks == [slots[0], H.BACK_ARROW, slots[1], H.BACK_ARROW, slots[2], H.BACK_ARROW], clicks
        assert (0.5, 0.851) not in clicks and (0.504, 0.891) not in clicks   # never UNLOCK FOR
        assert len(list((Path(tmp) / "cap").glob("skin_obyn_skin*.png"))) == 3


def test_owned_skin_is_selected_on_its_page():
    with tempfile.TemporaryDirectory() as tmp:
        o = _frame("skins_obyn.jpg", SKIN_CROP)
        page = [_w("MOUNTAIN GUARDIAN SKIN", 0.5, 0.05), _w("SELECT", 0.5, 0.87)]
        done = [_w("MOUNTAIN GUARDIAN SKIN", 0.5, 0.05), _w("SELECTED", 0.5, 0.87)]
        eq, _ = _equipper(tmp, o, [[_w("New")], page, done])
        assert eq.try_hero("obyn") == "equipped"
        assert eq.inp._inp.clicks == [(H.SKIN_X, round(H.SKIN_Y0, 3)), (0.5, 0.87), H.BACK_ARROW]


def test_unknown_skin_page_stops_with_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        o = _frame("skins_obyn.jpg", SKIN_CROP)
        eq, _ = _equipper(tmp, o, [[_w("New")], [_w("SOMETHING ELSE", 0.5, 0.5)]])
        assert eq.try_hero("obyn").startswith("bailed: unknown")
        assert eq.inp._inp.clicks[-1] == H.BACK_ARROW


def test_heroes_without_owned_skins_are_not_opened_again():
    with tempfile.TemporaryDirectory() as tmp:
        b = _budget(tmp)
        acct = SimpleNamespace(unlocked_heroes={"obyn", "quincy"}, selected_hero="obyn")
        tried = []

        class Eq(H.SkinEquipper):
            def try_hero(self, hero):
                tried.append(hero)
                return "none_owned"
        eq = Eq(None, Inp(), None, acct, b, sleep=lambda s: None, picker=FakePicker())
        st = {"Lookin fab": "unknown"}
        H.BUY_ONE_SKIN = False
        try:
            res = H.run_if_due(None, None, None, acct, "ACC", st, budget=b, equipper=eq)
            assert res.startswith("no owned skin") and tried == ["obyn", "quincy"]
            assert set(b.flag("skins_checked")) == {"obyn", "quincy"}
            # another day: nothing left to check, nothing opened
            b2 = A.Budget("ACC", path=b.path, clock=lambda: NOW + 86400)
            assert H.run_if_due(None, None, None, acct, "ACC", st, budget=b2, equipper=eq) is None
            assert tried == ["obyn", "quincy"]
        finally:
            H.BUY_ONE_SKIN = True


def test_skin_run_once_and_only_while_wanted():
    with tempfile.TemporaryDirectory() as tmp:
        b = _budget(tmp)
        calls = []
        eq = SimpleNamespace(run=lambda: calls.append(1) or "equipped obyn")
        st = {"Lookin fab": "unknown"}
        assert H.run_if_due(None, None, None, None, "ACC", st, budget=b, equipper=eq) == "equipped obyn"
        assert H.run_if_due(None, None, None, None, "ACC", st, budget=b, equipper=eq) is None
        assert calls == [1]
        assert H.run_if_due(None, None, None, None, "ACC", {"Lookin fab": "complete"},
                            budget=_budget(tmp + "x"), equipper=eq) is None


# -- hero skin: buying one (owner's permission 2026-11-07) ------------------------------
def test_mm_amounts_as_ocr_reads_them():
    assert H.parse_mm("2,500") == 2500 and H.parse_mm("@2.500") == 2500
    assert H.parse_mm("$213.833") == 213833 and H.parse_mm("150") == 150
    assert H.parse_mm("$2.99") is None and H.parse_mm("4,99") is None and H.parse_mm("LVL3") is None


def test_live_skin_page_price_and_total():
    page = _ocr("skin_page_unowned")
    unlock, price = H.button_price(page)
    assert unlock.text == "UNLOCKFOR:" and price == 2500
    assert H.mm_total(page) == 213833
    assert H.button_price([_w("UNLOCK FOR:", 0.5, 0.85), _w("$24.99", 0.5, 0.89)]) == (None, None)
    assert H.button_price([_w("SELECT", 0.5, 0.87)]) == (None, None)


def _page(total, *button):
    return ([_w("MOUNTAIN GUARDIAN SKIN", 0.5, 0.055), _w(total, 0.907, 0.056)]
            + [_w(t, 0.5, 0.85 + 0.04 * i) for i, t in enumerate(button)])


def _buyer(tmp, reads, used_mm=0):
    q = _frame("skins_quincy.jpg", SKIN_CROP)
    eq, b = _equipper(tmp, q, reads, hero="quincy")
    if used_mm:
        b.add("mm", used_mm)
    return eq, b


def test_buy_one_skin_then_select_it():
    with tempfile.TemporaryDirectory() as tmp:
        question = _page("$213.833", "@2.500") + [_w("Unlock this skin?", 0.5, 0.4),
                                                  _w("YES", 0.6, 0.62), _w("NO", 0.4, 0.62)]
        reads = [_ocr("skin_page_unowned"), question,
                 _page("$211.333", "SELECT"), _page("$211.333", "SELECT"), _page("$211.333", "SELECTED")]
        eq, b = _buyer(tmp, reads)
        assert eq.buy_for("quincy") == "equipped"
        clicks = eq.inp._inp.clicks
        assert clicks == [(H.SKIN_X, round(H.SKIN_Y0, 3)), (0.5, 0.851), (0.6, 0.62), (0.5, 0.85),
                          H.BACK_ARROW], clicks
        assert (0.4, 0.62) not in clicks
        flag = b.flag("skin_bought")
        assert flag["state"] == "bought" and flag["price"] == 2500 and flag["mm_after"] == 211333
        assert b.used("mm") == 2500 and b.used("purchases") == 1


def test_buy_settles_on_the_real_monkey_money_drop():
    with tempfile.TemporaryDirectory() as tmp:
        reads = [_ocr("skin_page_unowned"), _page("$213.833", "UNLOCK FOR:", "@2.500")]
        eq, b = _buyer(tmp, reads)
        assert eq.buy_for("quincy") == "bailed: not_bought"
        assert b.flag("skin_bought")["state"] == "not_bought" and b.used("mm") == 0
        assert (0.5, 0.85) not in eq.inp._inp.clicks[2:]          # no SELECT click
    with tempfile.TemporaryDirectory() as tmp:
        reads = [_ocr("skin_page_unowned"), _page("$203.833", "SELECT")]
        eq, b = _buyer(tmp, reads)
        assert eq.buy_for("quincy") == "bailed: unexpected"
        assert b.flag("skin_bought")["state"] == "unexpected" and b.used("mm") == 10000


def test_buy_refused_over_the_cap_or_for_real_money():
    with tempfile.TemporaryDirectory() as tmp:
        eq, b = _buyer(tmp, [_ocr("skin_page_unowned")], used_mm=A.MM_PER_DAY - 2000)
        assert eq.buy_for("quincy").startswith("bailed: 2500 MM is over the cap")
        assert (0.5, 0.851) not in eq.inp._inp.clicks and b.flag("skin_bought") is None
    with tempfile.TemporaryDirectory() as tmp:
        # a real-money price: that slot is skipped as a bundle; the next page
        # (nothing readable here) stops the pass - nothing bought either way
        eq, b = _buyer(tmp, [_page("$213.833", "UNLOCK FOR:", "$24.99")])
        assert eq.buy_for("quincy").startswith("bailed: unknown")
        assert eq.inp._inp.clicks[:2] == [(H.SKIN_X, round(H.SKIN_Y0, 3)), H.BACK_ARROW]
        assert (0.5, 0.85) not in eq.inp._inp.clicks
        assert b.flag("skin_bought") is None and b.flag("skin_bundle_slots") == {"quincy": [1]}
    with tempfile.TemporaryDirectory() as tmp:
        bundle = _ocr("skin_page_unowned") + [_w("SKIN BUNDLE", 0.5, 0.5)]
        eq, b = _buyer(tmp, [bundle])
        assert eq.buy_for("quincy").startswith("bailed")
        assert (0.5, 0.851) not in eq.inp._inp.clicks and b.flag("skin_bought") is None


def test_buy_only_once_ever_and_only_when_nothing_is_owned():
    with tempfile.TemporaryDirectory() as tmp:
        b = _budget(tmp)
        acct = SimpleNamespace(unlocked_heroes={"obyn", "quincy"}, selected_hero="obyn")
        bought = []

        class Eq(H.SkinEquipper):
            def try_hero(self, hero):
                return "none_owned"

            def _buy(self):
                bought.append(1)
                self.budget.set_flag("skin_bought", {"state": "not_bought"})
                return "buy quincy: bailed: not_bought"
        eq = Eq(None, Inp(), None, acct, b, sleep=lambda s: None, picker=FakePicker())
        st = {"Lookin fab": "unknown"}
        res = H.run_if_due(None, None, None, acct, "ACC", st, budget=b, equipper=eq)
        assert res.endswith("bailed: not_bought") and bought == [1], res
        later = A.Budget("ACC", path=b.path, clock=lambda: NOW + 86400)
        assert H.run_if_due(None, None, None, acct, "ACC", st, budget=later, equipper=eq) is None
        assert bought == [1]


def test_quincy_is_the_hero_skins_are_bought_for():
    acct = SimpleNamespace(unlocked_heroes={"obyn", "quincy"}, selected_hero=None)
    assert H.heroes_to_try(acct)[0] == "quincy"


# -- hero skin: a real-money bundle in the skin column (live run 2026-11-07 19:00) -------
def test_live_bundle_page_is_a_shop():
    """Obyn's third icon opened "SKELETOR PRESTIGE PACK ... $12.99"."""
    assert H.skin_page(_ocr("skin_page_bundle"))[0] == "shop"
    assert H.skin_page(_ocr("skin_page_obyn_ocean"))[0] == "unowned"
    assert H.button_price(_ocr("skin_page_obyn_ocean"))[1] == 2500


def _obyn_live_reads():
    # price under icon 1 ("2.500"), icon 2 ("New"), its page, icon 3 (nothing), its page
    return [[_w("2.500")], [_w("New")], _ocr("skin_page_obyn_ocean"), [], _ocr("skin_page_bundle")]


def test_bundle_slot_is_skipped_and_the_hero_still_counts_as_checked():
    with tempfile.TemporaryDirectory() as tmp:
        o = _frame("skins_obyn.jpg", SKIN_CROP)
        eq, b = _equipper(tmp, o, _obyn_live_reads())
        assert eq.try_hero("obyn") == "none_owned"
        slots = [(H.SKIN_X, round(y, 3)) for _, y in H.slot_centres(3)]
        clicks = eq.inp._inp.clicks
        assert clicks == [slots[1], H.BACK_ARROW, slots[2], H.BACK_ARROW], clicks
        assert not any(abs(x - 0.732) < 0.01 and abs(y - 0.794) < 0.01 for x, y in clicks)  # never $12.99
        assert b.flag("skin_bundle_slots") == {"obyn": [3]}
        # the next pass never clicks the bundle slot again
        eq2, _ = _equipper(tmp, o, [[_w("2.500")], [_w("New")], _ocr("skin_page_obyn_ocean")])
        eq2.budget = b
        assert eq2.try_hero("obyn") == "none_owned"
        assert slots[2] not in eq2.inp._inp.clicks


def test_buy_pass_skips_the_bundle_slot_too():
    with tempfile.TemporaryDirectory() as tmp:
        o = _frame("skins_obyn.jpg", SKIN_CROP)
        # in this script slot 1 opens the bundle (skipped, remembered), slot 2
        # the Ocean Guardian page, bought: the total drops by exactly 2,500
        paid = _ocr("skin_page_obyn_ocean")
        paid = [w if w.text != "$213.849" else Word("$211.349", w.x, w.y, w.w, w.h, w.conf) for w in paid]
        paid = [w for w in paid if w.y < 0.8] + [_w("SELECTED", 0.5, 0.87)]
        reads = [_ocr("skin_page_bundle"), _ocr("skin_page_obyn_ocean"), paid, paid]
        eq, b = _equipper(tmp, o, reads)
        res = eq.buy_for("obyn")
        assert res == "equipped", res
        assert b.flag("skin_bundle_slots") == {"obyn": [1]}
        slots = [(H.SKIN_X, round(y, 3)) for _, y in H.slot_centres(2)]
        assert eq.inp._inp.clicks[:4] == [slots[0], H.BACK_ARROW, slots[1], (0.499, 0.852)], eq.inp._inp.clicks
        assert b.flag("skin_bought")["state"] == "bought" and b.used("mm") == 2500


def test_live_19h_run_now_reaches_the_purchase():
    """Quincy priced, Obyn: priced, unowned MM skin, bundle -> both checked,
    so the same run goes on to buy (Quincy first)."""
    with tempfile.TemporaryDirectory() as tmp:
        b = _budget(tmp)
        acct = SimpleNamespace(unlocked_heroes={"obyn", "quincy"}, selected_hero="quincy")
        q = _frame("skins_quincy.jpg", SKIN_CROP)
        o = _frame("skins_obyn.jpg", SKIN_CROP)
        reads = [[_w("2.500")], [_w("@2.500")]] + _obyn_live_reads()
        frames = [q, q, o, o, o, o, o, o]
        bought = []

        class Eq(H.SkinEquipper):
            def _buy(self):
                bought.append(heroes_first(self.account))
                return "buy quincy: (scripted)"
        picker = FakePicker("quincy")
        menus = SimpleNamespace(v=SimpleNamespace(read=lambda region: reads.pop(0) if reads else []))
        screen = SimpleNamespace(grab=lambda: frames.pop(0) if len(frames) > 1 else frames[0])
        eq = Eq(screen, Inp(), menus, acct, b, sleep=lambda s: None, picker=picker,
                capture_dir=Path(tmp) / "cap")
        res = H.run_if_due(None, None, None, acct, "ACC", {"Lookin fab": "unknown"}, budget=b, equipper=eq)
        assert "quincy: none_owned" in res and "obyn: none_owned" in res, res
        assert bought == ["quincy"], res
        assert set(b.flag("skins_checked")) == {"quincy", "obyn"}


def heroes_first(account):
    return H.heroes_to_try(account)[0]


# -- quests -----------------------------------------------------------------------------
def test_quests_describe():
    assert Q.describe([_w("QUESTS"), _w("First Time"), _w("Tutorial!")]) == ("quests", True)
    assert Q.describe(_ocr("quests_all")) == ("quests", False)
    assert Q.describe([_w("$4.99")])[0] == "shop"
    assert Q.describe([_w("???")])[0] == "unknown"


def test_quest_cards_from_the_live_capture():
    found = Q.cards(_ocr("quests_all"))
    assert [c["title"] for c in found] == ["BYTHePOWeROFBATTLeCAT!", "He-MANHASTHePOWeR!", "OHNO!SKeLeTOR!",
                                           "ROGueLeGenDSPReVIeW"], found
    assert [c["progress"] for c in found] == ["0/1", "0/3", "0/3", "0/1"]
    assert all(c["go"] for c in found)
    assert found[1]["desc"].startswith("HeLP He-MAn")
    assert Q.tutorial_card(found) is None


def test_tutorials_tab_found_in_the_live_capture():
    tab = A.find_allowed(_ocr("quests_all"), Q.TUTORIALS_TAB, region=Q.TAB_ROW)
    assert tab is not None and abs(tab.x - 0.642) < 0.01


def _tutorials_page():
    words = [w for w in _ocr("quests_all") if w.y < 0.22]
    return words + [_w("New", 0.146, 0.239), _w("FIRST TIME TUTORIAL!", 0.33, 0.242),
                    _w("Learn the basics of Bloons TD 6", 0.35, 0.283), _w("GO!", 0.805, 0.30),
                    _w("x100", 0.262, 0.36), _w("0/1", 0.806, 0.361)]


def test_quests_look_opens_tutorials_and_never_go():
    with tempfile.TemporaryDirectory() as tmp:
        b = _budget(tmp)
        screens = [MAIN, ("unknown", _ocr("quests_all")), ("unknown", _tutorials_page()),
                   ("unknown", []), MAIN]
        menus = ShopMenus(screens)
        inp = Inp()
        res = Q.run_if_due(SimpleNamespace(grab=lambda: np.zeros((8, 8, 3), np.uint8)), inp, menus,
                           "ACC", {"First Steps": "progress"}, budget=b)
        assert res == "quests, tutorial listed", res
        assert inp.clicks[:2] == [Q.QUEST_GIVER, (0.642, 0.169)], inp.clicks
        assert set(inp.clicks[2:]) <= {Q.BACK_ARROW}
        assert not any(abs(x - 0.805) < 0.01 for x, _ in inp.clicks)       # GO! never clicked
        seen = b.flag(Q.SEEN_FLAG)
        assert seen["tutorial_listed"] and seen["card"]["progress"] == "0/1"
        assert Q.run_if_due(None, inp, menus, "ACC", {"First Steps": "progress"}, budget=b) is None


def test_old_quests_flag_does_not_stop_the_tutorials_look():
    with tempfile.TemporaryDirectory() as tmp:
        b = _budget(tmp)
        b.set_flag("quests_seen", {"at": NOW, "tutorial_listed": False})
        b.add("quests_look")
        menus = ShopMenus([MAIN, ("unknown", _ocr("quests_all")), ("unknown", _ocr("quests_all")), MAIN])
        res = Q.run_if_due(SimpleNamespace(grab=lambda: np.zeros((8, 8, 3), np.uint8)), Inp(), menus,
                           "ACC", {"First Steps": "progress"}, budget=b)
        assert res == "quests, tutorial not read"


# -- runner hook ------------------------------------------------------------------------
def test_runner_hook_returns_home_only_after_a_task_acted():
    from unittest import mock
    from btd6bot import runner as R

    bot = R.Bot.__new__(R.Bot)
    bot.s = bot.inp = bot.menus = bot.account = None
    bot.uid = "UID1"
    bot.read_mm = lambda: None
    homes = []
    bot.to_main_menu = lambda: homes.append(1)
    with mock.patch.object(A, "card_statuses", lambda: {}), \
            mock.patch.object(H, "run_if_due", lambda *a, **k: None), \
            mock.patch.object(Q, "run_if_due", lambda *a, **k: "quests, tutorial listed"), \
            mock.patch.object(S, "run_if_needed", lambda *a, **k: (_ for _ in ()).throw(ValueError("x"))):
        bot._achievement_tasks_if_due()
    assert homes == [1, 1]          # quests acted, the shop failed: both end on the main menu


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
