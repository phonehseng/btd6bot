"""Time spent between games (no game needed): achievement claims, waiting
without tripping the supervisor's watchdog, error streaks and benches, and
when the map-select medal sweep runs.

Before (log of 2026-10-21/22):
  * the achievements "!" badge started a full scan - 204 s and 192 s, 28 min apart;
  * a 30-minute time.sleep() outlived the watchdog's 10-minute limit;
  * one setup bug benched 13 maps for 6 h each, and Tree Stump, left at round
    59 with 149 lives, was benched 12 h and recorded as a loss;
  * every restart swept the map medals again (~40 s, 13 of 14 found nothing).
Run: python tests/test_between_games_offline.py"""
import json
import logging
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import achievements as A  # noqa: E402
from btd6bot import runner as R  # noqa: E402
from btd6bot.vision import Word  # noqa: E402

logging.getLogger("achievements").setLevel(logging.ERROR)
logging.getLogger("runner").setLevel(logging.CRITICAL)


# -- a fake achievements list -------------------------------------------------
# Two columns, two card rows per page, laid out the way parse_cards reads them:
# a one-word title, a sentence below it, and the status (COLLECT / NN% /
# COMPLETE) lower down in the same column.
COLUMNS, ROWS = (0.25, 0.75), (0.30, 0.59)


class FakeList:
    """The game's achievement list: cards in list order, a scroll position
    and the clicks that claim rewards. `moves`: a claimed card drops to the
    bottom of the list (else it keeps its place showing COMPLETE)."""

    def __init__(self, cards, moves=False):
        self.cards = [dict(c) for c in cards]
        self.moves = moves
        self.top = 0              # index of the first visible card
        self.collect_at = {}      # (x, y) of a visible COLLECT button -> card
        self.reads = self.scrolls = 0

    def words(self):
        out = [Word("Achievements", 0.5, 0.05, 0.1, 0.03, 0.9)]
        self.collect_at = {}
        for i, card in enumerate(self.cards[self.top:self.top + 4]):
            x, y = COLUMNS[i % 2], ROWS[i // 2]
            out.append(Word(card["name"], x, y, 0.1, 0.03, 0.9))
            out.append(Word(card["desc"], x, y + 0.04, 0.3, 0.02, 0.9))
            status = {"collect": "COLLECT", "complete": "COMPLETE"}.get(card["status"], f"{card['progress']}%")
            out.append(Word(status, x + 0.1, y + 0.15, 0.08, 0.03, 0.9))
            if card["status"] == "collect":
                self.collect_at[(round(x + 0.1, 3), round(y + 0.15, 3))] = card
        return out

    def click(self, x, y):
        card = self.collect_at.get((round(x, 3), round(y, 3)))
        if card is not None:
            card["status"] = "complete"
            if self.moves:
                self.cards.remove(card)
                self.cards.append(card)


class FakeMenus:
    def __init__(self, fake_list):
        self.list = fake_list
        self.words = []

    def identify(self, read=True):
        return "main_menu"

    def read(self, scale=0.5):
        self.list.reads += 1
        self.words = self.list.words()
        return self.words

    def has(self, *keys, words=None):
        from btd6bot.vision import norm
        return any(norm(k) in norm(w.text) for w in (words or self.words) for k in keys)

    def find(self, *keys, words=None, region=None):
        return None

    def wait_for(self, targets, timeout=6.0, cheap_in_game=True):
        return "main_menu"


class FakeInput:
    def __init__(self, fake_list):
        self.list = fake_list

    def click(self, x, y):
        self.list.click(x, y)

    def drag(self, *a, **k):
        pass

    def scroll(self, ticks, x, y):
        self.list.scrolls += 1
        self.list.top += 4


def card(name, status, progress=None):
    return {"name": name, "desc": f"Do the {name} thing many times", "status": status, "progress": progress}


def run_claim(cards, moves=False):
    fake = FakeList(cards, moves)
    ach = A.Achievements(None, FakeInput(fake), FakeMenus(fake))
    with tempfile.TemporaryDirectory() as d, \
            mock.patch.object(A, "STATE", Path(d) / "state.json"), \
            mock.patch.object(A, "_catalog_names", lambda: {}), \
            mock.patch.object(A.time, "sleep", lambda s: None):
        A.Achievements.save({c["name"]: {"desc": c["desc"], "status": c["status"], "progress": c["progress"]}
                             for c in cards}, scanned_at="2026-10-22 02:30:04")
        claimed = ach.claim()
        saved = json.loads(A.STATE.read_text(encoding="utf-8"))
    return claimed, fake, saved


def test_collect_word_is_a_button_not_a_description():
    """'Our Powers Combined' says "Collect at least 12 different Powers":
    every scan used to count it as a reward and click its text."""
    assert A._is_collect("COLLECT") and A._is_collect("Collegt")
    assert not A._is_collect("Collect at least 12 different Powers")
    words = [Word("OurPowersCombined", 0.25, 0.30, 0.1, 0.03, 0.9),
             Word("Collect at least 12 different Powers", 0.25, 0.34, 0.3, 0.02, 0.9),
             Word("4%", 0.35, 0.45, 0.05, 0.03, 0.9)]
    (only,) = A.parse_cards(words)
    assert only["status"] == "progress" and only["progress"] == 4


def test_claim_reads_one_page_when_the_finished_cards_are_on_top():
    cards = [card("Alpha", "collect"), card("Bravo", "collect"), card("Charlie", "progress", 80),
             card("Delta", "progress", 77)] + [card(f"Card{i}", "progress", 0) for i in range(80)]
    claimed, fake, saved = run_claim(cards)
    assert claimed == ["Alpha", "Bravo"]
    assert fake.scrolls == 0, "nothing below the first page can be finished"
    assert fake.reads <= 6, f"{fake.reads} page reads for one page"
    # the planner's saved progress learns about the claims at once
    assert saved["cards"]["Alpha"]["status"] == "complete"
    assert saved["cards"]["Charlie"]["status"] == "progress"
    assert saved["scanned_at"] == "2026-10-22 02:30:04", "a claim pass is not a full scan"


def test_claim_scrolls_on_while_whole_pages_are_finished():
    finished = [card(f"Done{i}", "collect") for i in range(5)]
    rest = [card("Echo", "progress", 40)] + [card(f"Card{i}", "progress", 0) for i in range(40)]
    for moves in (False, True):  # claimed cards keep their place / drop to the bottom
        claimed, fake, _ = run_claim(finished + rest, moves=moves)
        assert sorted(claimed) == [f"Done{i}" for i in range(5)], (moves, claimed)
        assert fake.scrolls <= 1, (moves, fake.scrolls)


def test_claim_with_nothing_to_claim_stops_at_once():
    claimed, fake, _ = run_claim([card(f"Card{i}", "progress", 50 - i) for i in range(40)])
    assert claimed == [] and fake.scrolls == 0


# -- the runner ------------------------------------------------------------------
def bare_bot():
    """A Bot without a game window: only the attributes these tests use."""
    bot = R.Bot.__new__(R.Bot)
    bot.benched_calls = []
    bot.bench = lambda m, mode, hours, why="": bot.benched_calls.append((m, mode, hours))
    bot.idled = []
    bot._idle = lambda seconds, why, code_stamp=None: bot.idled.append(seconds)
    return bot


class Plan:
    def __init__(self, map_name, mode="easy"):
        self.map, self.mode_key = map_name, mode


def fail(where, message):
    """An exception raised inside a bot function called `where`."""
    namespace = {}
    exec(compile(f"def {where}():\n    raise RuntimeError({message!r})\n",
                 str(Path(R.__file__).parent / "match.py"), "exec"), namespace)
    try:
        namespace[where]()
    except RuntimeError as e:
        return e


def test_error_signature_ignores_the_message():
    a = fail("play", "no defence could be placed on Quarry")
    b = fail("play", "no defence could be placed on Balance")
    c = fail("setup", "no defence could be placed on Quarry")
    assert R._error_signature(a) == R._error_signature(b) != R._error_signature(c)


def test_a_map_is_benched_only_after_failing_twice():
    with tempfile.TemporaryDirectory() as d, mock.patch.object(R, "ERROR_FILE", Path(d) / "errors.json"):
        bot = bare_bot()
        bot._errors = R._load_errors()
        bot._game_error(fail("one", "x"), Plan("Logs"))
        assert bot.benched_calls == [], "one failure is not enough to bench"
        bot._game_error(fail("two", "y"), Plan("Logs"))
        assert bot.benched_calls == [("Logs", "easy", 6)]
        # a different map failing once is not benched
        bot._game_error(fail("three", "z"), Plan("Quarry"))
        assert len(bot.benched_calls) == 1


def test_the_same_error_in_a_row_waits_instead_of_benching_and_survives_restarts():
    """The 02:04-02:15 burst: one bug, 13 maps benched for 6 h each."""
    with tempfile.TemporaryDirectory() as d, mock.patch.object(R, "ERROR_FILE", Path(d) / "errors.json"):
        maps = ["Bloonarius Prime", "Lost Crevasse", "Luminous Cove", "Ancient Portal", "Sulfur Springs"]
        bot = bare_bot()
        bot._errors = R._load_errors()
        for i, name in enumerate(maps):
            if i == 2:  # the supervisor restarts the bot in the middle of it
                bot = bare_bot()
                bot._errors = R._load_errors()
            bot._game_error(fail("play", f"no defence on {name}"), Plan(name))
        assert bot.benched_calls == [], bot.benched_calls
        assert bot.idled == [600, 600, 600], "waits from the third error on"
        bot._game_done(Plan("Logs"))
        assert R._load_errors()["streak"] == 0


def test_games_left_with_lives_or_signed_out_are_not_the_maps_fault():
    assert R.outside_cause("abandoned", "main_menu")      # Tree Stump: round 59, 149 lives
    assert R.outside_cause("defeat", "title")             # someone signed in elsewhere
    assert R.outside_cause("defeat", "account")
    assert R.outside_cause("defeat", "defeat") is None    # a real loss
    assert R.outside_cause("defeat", "main_menu") is None


def test_long_waits_keep_the_status_fresh_and_end_on_pause():
    with tempfile.TemporaryDirectory() as d:
        pause = Path(d) / "PAUSE"
        states = []
        with mock.patch.object(R, "PAUSE_FILE", pause), mock.patch.object(R, "IDLE_POLL", 0.01), \
                mock.patch.object(R, "IDLE_STATUS_EVERY", 0.05), \
                mock.patch.object(R, "set_state", lambda text, game=None: states.append(text)):
            bot = R.Bot.__new__(R.Bot)
            t = time.time()
            bot._idle(0.3, "idle: nothing to play")
            assert 0.25 < time.time() - t < 2 and len(states) >= 4, states
            pause.write_text("")
            t = time.time()
            bot._idle(60, "idle: nothing to play")
            assert time.time() - t < 1, "a PAUSE file ends the wait"


def test_medal_sweep_is_daily_per_account():
    with tempfile.TemporaryDirectory() as d, mock.patch.object(R, "ROOT_DIR", Path(d)):
        (Path(d) / "data" / "accounts").mkdir(parents=True)
        assert R._medal_sweep_due("AAAA")
        R._write_stamp(R._medal_sweep_file("AAAA"), time.time())
        assert not R._medal_sweep_due("AAAA")
        assert R._medal_sweep_due("BBBB"), "each account has its own stamp"
        assert R._medal_sweep_due("AAAA", now=time.time() + R.MEDAL_SWEEP_EVERY + 1)


def account_check(uid_on_screen, last_run_uid, swept_ago, bot=None):
    """Bot._check_account with the game and files faked. Returns (bot, sweeps)."""
    sweeps = []
    with tempfile.TemporaryDirectory() as d, mock.patch.object(R, "ROOT_DIR", Path(d)), \
            mock.patch.object(R, "read_user_id", lambda *a: uid_on_screen), \
            mock.patch.object(R, "load_for", lambda uid: (mock.Mock(), False)), \
            mock.patch.object(R, "is_stale", lambda uid: False), \
            mock.patch.object(R, "current_path", lambda: Path(d) / f"{last_run_uid}.json"):
        (Path(d) / "data" / "accounts").mkdir(parents=True)
        if swept_ago is not None:
            R._write_stamp(R._medal_sweep_file(uid_on_screen), time.time() - swept_ago)
        if bot is None:
            bot = R.Bot.__new__(R.Bot)
            bot.s = bot.inp = bot.menus = None
            bot.uid, bot._games_since_id, bot._medals_due = None, 0, False
        bot.scan_all_medals = lambda: sweeps.append(1) or 88
        bot.to_main_menu = lambda: True
        bot._check_account(force=True)
    return bot, sweeps


def test_restarts_do_not_repeat_the_medal_sweep():
    _, sweeps = account_check("AAAA", "AAAA", swept_ago=600)
    assert sweeps == [], "same account, swept 10 minutes ago: a code reload must not sweep again"
    _, sweeps = account_check("AAAA", "AAAA", swept_ago=R.MEDAL_SWEEP_EVERY + 60)
    assert sweeps == [1], "a day old: sweep"
    _, sweeps = account_check("BBBB", "AAAA", swept_ago=600)
    assert sweeps == [1], "someone signed in to another account: sweep"
    bot, _ = account_check("AAAA", "AAAA", swept_ago=600)
    _, sweeps = account_check("BBBB", "AAAA", swept_ago=600, bot=bot)
    assert sweeps == [1], "an account switch while running: sweep"


class FakeAch:
    calls = []

    def __init__(self, *a):
        pass

    def claim(self):
        FakeAch.calls.append("claim")

    def scan(self, collect=True):
        FakeAch.calls.append("scan")


def achievements_run(badge_reads, ach_at, muted_at=0.0):
    """Run Bot._achievements_if_due with the badge reading as given (one value
    per has_badge call). Returns the calls made to the achievements screen."""
    FakeAch.calls = []
    reads = iter(badge_reads)
    with tempfile.TemporaryDirectory() as d, \
            mock.patch.object(R, "ACH_STAMP", Path(d) / "ach.txt"), \
            mock.patch.object(R, "ACH_MUTE", Path(d) / "mute.txt"), \
            mock.patch.object(R, "Achievements", FakeAch), \
            mock.patch.object(R.time, "sleep", lambda s: None), \
            mock.patch.object(R, "set_state", lambda *a, **k: None):
        R._write_stamp(R.ACH_MUTE, muted_at)
        bot = R.Bot.__new__(R.Bot)
        bot.s = bot.inp = None
        bot.menus = mock.Mock()
        bot.menus.has_badge = lambda *a: next(reads)
        bot.to_main_menu = lambda: True
        bot._ach_at = ach_at
        bot._achievements_if_due()
        return FakeAch.calls, R._read_stamp(R.ACH_MUTE), bot._ach_at


def test_badge_claims_without_a_full_scan():
    recent = time.time() - 600
    calls, _, at = achievements_run([True, False], recent)
    assert calls == ["claim"] and at == recent
    calls, _, _ = achievements_run([False], recent)
    assert calls == []


def test_full_scan_daily_and_a_stuck_badge_cannot_loop():
    calls, _, at = achievements_run([False], time.time() - R.ACH_EVERY - 1)
    assert calls == ["scan"] and at > time.time() - 5
    # badge still lit after claiming -> one full scan; still lit -> muted
    recent = time.time() - 600
    calls, muted, at = achievements_run([True, True, True], recent)
    assert calls == ["claim", "scan"] and muted == at
    # muted: the badge no longer starts anything until the next full scan
    calls, _, _ = achievements_run([True], at, muted_at=at)
    assert calls == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
