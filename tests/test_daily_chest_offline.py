"""Offline checks for the Daily Reward chest (btd6bot/dailychest.py).

Fixtures (tests/fixtures/daily_chest_*.png) are crops of real frames, the
region FIXTURE_CROP of the game window:
  daily_chest_ready_lvl150.png   main menu, level-150 account, Halloween coffin
                                 with its glow (rec_20261107_165100.mkv, 0:18)
  daily_chest_ready_lvl10.png    main menu, level-10 account, another day
                                 (docs/screens/after_home.jpg)
  daily_chest_settings_over.png  the same menu under the Settings popup (0:17)
  daily_chest_in_game.png        a game in progress (rec_20261107_163500.mkv, 0:30)
No frame of an already-opened chest or of the reward screen exists yet; the
"no glow" case is made by painting the glow over with the sand next to it.
The flow tests drive DailyChest with scripted fake screens.

Run: python tests/test_daily_chest_offline.py
"""
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import dailychest as D  # noqa: E402
from btd6bot.vision import Word  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
FIXTURE_CROP = (0.15, 0.45, 0.50, 0.78)   # where the fixture crops sit in the window


def _frame(name):
    """Rebuild a whole window frame (black outside the crop) from a fixture."""
    crop = cv2.imread(str(FIX / name))
    assert crop is not None, name
    ch, cw = crop.shape[:2]
    w = round(cw / (FIXTURE_CROP[2] - FIXTURE_CROP[0]))
    h = round(ch / (FIXTURE_CROP[3] - FIXTURE_CROP[1]))
    frame = np.zeros((h, w, 3), np.uint8)
    x0, y0 = int(FIXTURE_CROP[0] * w), int(FIXTURE_CROP[1] * h)
    frame[y0:y0 + ch, x0:x0 + cw] = crop
    return frame


def _without_glow(frame):
    """The chest as it would look with no glow: glow pixels in GLOW_REGION
    painted with the pink sand of the control patch."""
    f = frame.copy()
    h, w = f.shape[:2]
    cx0, cy0, cx1, cy1 = D.CONTROL_REGION
    sand = np.median(f[int(cy0 * h):int(cy1 * h), int(cx0 * w):int(cx1 * w)].reshape(-1, 3), axis=0)
    x0, y0, x1, y1 = D.GLOW_REGION
    patch = f[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    glow = (hsv[..., 0] >= D.GLOW_HUE[0]) & (hsv[..., 0] <= D.GLOW_HUE[1]) & (hsv[..., 1] >= D.GLOW_MIN_SAT)
    patch[glow] = sand
    return f


# -- detection -----------------------------------------------------------------
def test_glow_found_on_both_accounts():
    for name in ("daily_chest_ready_lvl150.png", "daily_chest_ready_lvl10.png"):
        glowing, share, control = D.chest_glows(_frame(name))
        assert glowing, (name, share, control)


def test_no_glow_under_a_popup_or_in_a_game():
    for name in ("daily_chest_settings_over.png", "daily_chest_in_game.png"):
        glowing, share, control = D.chest_glows(_frame(name))
        assert not glowing, (name, share, control)


def test_no_glow_when_painted_over():
    glowing, share, _ = D.chest_glows(_without_glow(_frame("daily_chest_ready_lvl150.png")))
    assert not glowing, share


def test_yellow_everywhere_is_not_the_glow():
    """An all-yellow backdrop lights the control patch too."""
    f = np.full((800, 1280, 3), 0, np.uint8)
    f[:] = cv2.cvtColor(np.uint8([[[22, 150, 245]]]), cv2.COLOR_HSV2BGR)[0, 0]
    assert not D.chest_glows(f)[0]


# -- reading screens -----------------------------------------------------------
def _w(text, x=0.5, y=0.5, conf=0.9):
    return Word(text, x, y, 0.1, 0.04, conf)


def test_countdown_parsed_from_glued_ocr():
    words = [_w("Returnin5h12mtoclaim"), _w("your next reward!", y=0.55)]
    assert D.countdown_seconds(words) == 5 * 3600 + 12 * 60
    assert D.countdown_seconds([_w("Return in 0h 7m to claim your next reward!")]) == 420
    assert D.countdown_seconds([_w("PLAY")]) is None


def test_classify_screens():
    assert D.classify([_w("DAILY REWARD"), _w("Day 3")]) == "rewards"
    assert D.classify([_w("DAY1"), _w("DAY2"), _w("DAY3")]) == "rewards"
    assert D.classify([_w("Would you like to be notified when your Daily Reward chest is ready")]) \
        == "notify_prompt"
    assert D.classify([_w("STORE"), _w("$4.99")]) == "shop"
    assert D.classify([_w("UNLOCK ALL")]) == "shop"
    assert D.classify([_w("Returnin3h1mtoclaimyournextreward")]) == "countdown"
    assert D.classify([_w("+100"), _w("OK")]) == "popup"
    assert D.classify([_w("INSTA MONKEY!")], "insta_reward") == "insta_reward"
    assert D.classify([_w("???")]) == "unknown"


def test_main_menu_numbers_are_not_a_shop():
    """The main menu's XP bar ("1,830/4,250") and Monkey Money must not read
    as prices, and its countdown bubble needs no back-arrow click."""
    words = [_w("PLAY"), _w("1,830/4,250"), _w("$213,233"), _w("Returnin5h12m")]
    assert D.classify(words, "main_menu") == "main_menu"


# -- pacing ---------------------------------------------------------------------
NOW = 1_794_100_000.0


def test_due_rules():
    assert D.is_due({}, NOW, False)[0]                                   # never tried
    assert not D.is_due({"next_at": NOW + 3600}, NOW, False)[0]         # not yet
    assert D.is_due({"next_at": NOW + 3600}, NOW, True)[0]              # glow beats a guess
    assert not D.is_due({"next_at": NOW + 3600, "next_from_game": True}, NOW, True)[0]
    three = {"tries": [NOW - 20000, NOW - 15000, NOW - 9000]}
    assert not D.is_due(three, NOW, True)[0]                            # daily cap
    assert not D.is_due({"tries": [NOW - 600]}, NOW, True)[0]           # an hour between tries
    assert D.is_due({"tries": [NOW - 90000] * 3}, NOW, False)[0]        # old tries expire


def test_record_result():
    rec = D.record_result({}, NOW, "not_ready", wait=3600)
    assert rec["next_at"] == NOW + 3600 + D.COUNTDOWN_MARGIN and rec["next_from_game"]
    rec = D.record_result({}, NOW, "opened")
    assert rec["next_at"] == D.next_utc_midnight(NOW) and rec["last_opened"] == NOW
    rec = D.record_result(rec, NOW + 10, "no_response")
    assert rec["next_at"] == NOW + 10 + D.FAILED_RETRY and len(rec["tries"]) == 2
    assert D.next_utc_midnight(NOW) % 86400 == 0 and 0 < D.next_utc_midnight(NOW) - NOW <= 86400


# -- the flow, on scripted screens ---------------------------------------------
MAIN = ("main_menu", [_w("PLAY"), _w("MONKEYS"), _w("HEROES")])
REWARDS = ("unknown", [_w("DAILY REWARD", y=0.06), _w("Day 4"), _w("Today"),
                       _w("Returnin23h58mtoclaimyournextreward", y=0.9)])


class FakeMenus:
    """identify() returns the next scripted (screen name, words); the last
    one repeats. A click on the back arrow from a non-menu screen jumps to
    the main menu when back_works."""

    def __init__(self, script, back_works=True):
        self.script = list(script)
        self.words = []
        self.back_works = back_works
        self.collection_calls = 0

    def identify(self, read=True):
        name, self.words = self.script[0] if len(self.script) == 1 else self.script.pop(0)
        return name

    def dismiss_popup(self):
        return False

    def handle_collection_event(self):
        self.collection_calls += 1
        return True


class FakeInput:
    def __init__(self, menus=None):
        self.clicks = []
        self.menus = menus

    def click(self, fx, fy, hold=0.07):
        self.clicks.append((round(fx, 3), round(fy, 3)))
        m = self.menus
        if m and m.back_works and (fx, fy) == D.BACK_ARROW:
            m.script = [MAIN]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _chest(script, back_works=True):
    menus = FakeMenus(script, back_works)
    inp = FakeInput(menus)
    clock = Clock()
    return D.DailyChest(None, inp, menus, sleep=clock.sleep, clock=clock), inp, menus


def test_flow_opens_and_leaves_by_the_back_arrow():
    chest, inp, _ = _chest([MAIN, REWARDS])
    assert chest.claim() == "opened"
    assert inp.clicks[0] == D.CHEST and D.BACK_ARROW in inp.clicks
    assert chest.wait == 23 * 3600 + 58 * 60


def test_flow_presses_claim_when_offered():
    claim = ("unknown", [_w("DAILY REWARD"), _w("Day 1"), _w("CLAIM", 0.5, 0.8)])
    chest, inp, _ = _chest([MAIN, claim, REWARDS])
    assert chest.claim() == "opened"
    assert (0.5, 0.8) in inp.clicks


def test_flow_insta_monkey_panel_then_rewards():
    insta = ("insta_reward", [_w("INSTA MONKEY!"), _w("New Dart Monkey 0-2-2")])
    chest, inp, _ = _chest([MAIN, insta, REWARDS])
    assert chest.claim() == "opened"
    assert (0.5, 0.5) in inp.clicks


def test_flow_declines_notifications_never_yes():
    ask = ("unknown", [_w("Would you like to be notified when your Daily Reward chest is ready"),
                       _w("YES", 0.4, 0.7), _w("NO", 0.6, 0.7)])
    chest, inp, _ = _chest([MAIN, REWARDS, ask, MAIN])
    chest.inp.menus = None          # the back arrow must not short-cut this script
    assert chest.claim() == "opened"
    assert (0.6, 0.7) in inp.clicks and (0.4, 0.7) not in inp.clicks


def test_flow_not_ready_countdown_over_the_menu():
    bubble = ("main_menu", MAIN[1] + [_w("Returnin4h30mtoclaimyournextreward")])
    chest, inp, _ = _chest([MAIN, bubble])
    assert chest.claim() == "not_ready"
    assert chest.wait == 4 * 3600 + 30 * 60
    assert inp.clicks == [D.CHEST]            # no back arrow: there it is the profile button


def test_flow_no_response():
    chest, inp, _ = _chest([MAIN])
    assert chest.claim() == "no_response" and inp.clicks == [D.CHEST]


def test_flow_not_on_main_menu_clicks_nothing():
    chest, inp, _ = _chest([("victory", [_w("VICTORY")])])
    assert chest.claim() == "not_on_main_menu" and inp.clicks == []


def test_flow_bails_out_of_a_shop_without_clicking_it():
    shop = ("unknown", [_w("STORE"), _w("BUY", 0.5, 0.8), _w("$9.99", 0.5, 0.85)])
    chest, inp, _ = _chest([MAIN, shop])
    assert chest.claim().startswith("bailed")
    assert (0.5, 0.8) not in inp.clicks and D.BACK_ARROW in inp.clicks


def test_flow_bails_after_unknown_screens():
    chest, inp, _ = _chest([MAIN, ("unknown", [_w("???")])])
    assert chest.claim() == "bailed: an unknown screen"
    assert D.BACK_ARROW in inp.clicks


def test_flow_never_presses_escape():
    """The fakes have no key method at all: any key press would raise."""
    chest, inp, _ = _chest([MAIN, REWARDS])
    assert not hasattr(inp, "press")
    chest.claim()


def test_run_if_due_saves_per_account_and_respects_the_cap():
    class Screen:
        def grab(self):
            return _frame("daily_chest_ready_lvl150.png")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "daily_chest.json"
        for i in range(5):
            chest, inp, _ = _chest([MAIN])     # never reacts: "no_response"
            D.run_if_due(Screen(), inp, None, "ACC1", state_path=path,
                         now=NOW + i * 2 * 3600, chest=chest)
        rec = D.load_state(path)["ACC1"]
        # glowing chest, no game countdown: retried every 2 h, capped at 3/24 h
        assert len(rec["tries"]) == D.MAX_TRIES_PER_DAY, rec
        chest, inp, _ = _chest([MAIN, REWARDS])
        assert D.run_if_due(Screen(), inp, None, "ACC2", state_path=path, now=NOW, chest=chest) == "opened"
        state = D.load_state(path)
        assert state["ACC2"]["next_from_game"] and "ACC1" in state


def test_runner_hook():
    """Bot._daily_chest_if_due: back to the main menu only after a try, keyed
    by the signed-in User ID, and a failure never ends the bot."""
    from unittest import mock
    from btd6bot import runner as R

    def run(result=None, error=None):
        seen, homes = [], []

        def fake(screen, inp, menus, key):
            seen.append(key)
            if error:
                raise error
            return result
        bot = R.Bot.__new__(R.Bot)
        bot.s = bot.inp = bot.menus = None
        bot.uid = "UID1"
        bot.to_main_menu = lambda: homes.append(1)
        with mock.patch.object(D, "run_if_due", fake):
            bot._daily_chest_if_due()
        return seen, homes

    assert run(None) == (["UID1"], [])
    assert run("opened") == (["UID1"], [1])
    assert run(error=ValueError("boom")) == (["UID1"], [1])



def test_the_monkey_money_counter_is_not_a_real_money_price():
    """2026-11-07 19:48: '$213,880' read as '$213.88' in the top-right
    corner made the chest flow bail out as if on a store page."""
    corner = [Word("$213.88", 0.93, 0.04, 0.1, 0.04, 0.9)]
    assert not D.shop_like(corner)
    offer = [Word("$12.99", 0.50, 0.70, 0.1, 0.04, 0.9)]
    assert D.shop_like(offer), "a price with cents elsewhere still counts"
    assert D.shop_like(corner + [Word("BUNDLE", 0.5, 0.3, 0.1, 0.04, 0.9)])

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
