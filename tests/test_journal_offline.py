"""The game journal (btd6bot/journal.py) and the CHIMPS guards next to its
hooks: the line format, the no-op NULL journal, a failing write switching it
off, every cause_of_death category, Game.sell refusing in no-sell modes, Executor.why
putting the reason on each sale, the tower XP count without Monkey Knowledge in CHIMPS, and the report tool.
Offline: synthetic events, files in a temporary folder."""
import io
import json
import logging
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import journal as J          # noqa: E402
from btd6bot import match as M            # noqa: E402
from btd6bot.forecast import CRISIS_MARGIN  # noqa: E402
from btd6bot.game import Game, Placed     # noqa: E402
from btd6bot.strategy import MODE_RULES, Executor  # noqa: E402
from btd6bot.towerxp import TowerXpCounter  # noqa: E402
import journal_report as JR               # noqa: E402

logging.disable(logging.CRITICAL)         # the failing-write test logs an exception on purpose


class TempJournalDir:
    """Point journal.JOURNAL_DIR at a temporary folder for one test."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = J.JOURNAL_DIR
        J.JOURNAL_DIR = Path(self._tmp.name) / "journal"
        return J.JOURNAL_DIR

    def __exit__(self, *exc):
        J.close()
        J.JOURNAL_DIR = self._old
        self._tmp.cleanup()


def chimps_game():
    return J.start_game("Alpine Run", "chimps", "chimps_ninja_sun", "sauda", MODE_RULES["chimps"],
                        account=SimpleNamespace(player_level=127, boosts={"double_cash": True}),
                        executor=SimpleNamespace(no_sell=True))


# -- the file -------------------------------------------------------------------------

def test_every_line_has_t_ev_rnd_and_is_on_disk_at_once():
    with TempJournalDir() as folder:
        jr = chimps_game()
        assert J.current() is jr and jr.path.parent == folder
        assert jr.path.name.endswith("_AlpineRun_chimps.jsonl")
        jr.event("place", tid="n1", kind="ninja", x=0.5, y=0.5, cost=340, why={"source": "plan"})
        # flushed: readable while the journal is still open
        lines = [json.loads(x) for x in jr.path.read_text(encoding="utf-8").splitlines()]
        assert [x["ev"] for x in lines] == ["game_start", "place"]
        for x in lines:
            assert {"t", "ev", "rnd"} <= set(x)
        start = lines[0]
        assert start["no_sell"] and start["one_life"] and start["no_mk"] and start["start_round"] == 6
        assert start["round_set"] == "standard" and start["account_level"] == 127
        assert lines[1]["rnd"] == 6               # filed under the start round until a snapshot
        jr.round(rnd=7, cash=500, lives=1)
        jr.event("upgrade", tid="n1", cost=350)
        assert J.read(jr.path)[-1]["rnd"] == 7
        assert len(jr.events) == 4                # kept in memory as well


def test_null_does_nothing():
    J.close()
    assert J.current() is J.NULL
    assert J.NULL.event("place", tid="x") is None
    assert J.NULL.round(rnd=3) is None and J.NULL.leak(lost=1) is None and J.NULL.end(outcome="defeat") is None
    J.NULL.close()
    assert J.NULL.events == [] and not J.NULL.active


def test_a_failing_write_switches_the_journal_off_without_raising():
    with tempfile.TemporaryDirectory() as tmp:
        jr = J.Journal(Path(tmp))                 # a folder: opening it for append fails
        assert jr.event("place", tid="a") is None
        assert jr.off and not jr.active
        assert jr.event("place", tid="b") is None   # stays off, no second exception
        assert jr.events == []


def test_unwritable_values_are_written_as_text():
    with TempJournalDir():
        jr = chimps_game()
        jr.event("hold", why={"set": {"camo"}}, obj=object())
        last = J.read(jr.path)[-1]
        assert last["why"]["set"] == ["camo"] and isinstance(last["obj"], str)


def test_find_for_and_prune():
    with TempJournalDir() as folder:
        jr = chimps_game()
        jr.round(rnd=10, cash=1)
        t0 = jr.events[0]["t"]
        assert J.find_for(t0 - 100, t0 + 100) == jr.path
        assert J.find_for(t0 + 1000, t0 + 2000) is None
        J.close()
        assert J.prune(days=14) == 0
        assert J.prune(days=14, now=time.time() + 15 * 86400) == 1
        assert list(folder.glob("*.jsonl")) == []


# -- cause of death ---------------------------------------------------------------------

def ev(ev_, rnd, **fields):
    return dict(t=0, ev=ev_, rnd=rnd, **fields)


def base_events(cash_at_death=100, margin=0.8, early_margin=0.9, early_cash=100):
    return [ev("game_start", 6, mode="chimps"),
            ev("place", 38, tid="n1", kind="ninja", cost=340, why={"source": "plan"}),
            ev("upgrade", 39, tid="n1", kind="ninja", cross_after="1-0-0", cost=300, why={"source": "reinforce"}),
            ev("round", 41, cash=early_cash, margin=early_margin, waiting="plan step 8"),
            ev("round", 43, cash=cash_at_death, margin=margin, waiting="plan step 9"),
            ev("leak", 43, lost=1, lives_after=0, inferred=True, uncovered=[],
               groups=[{"bloon": "ceramic", "share": 0.7}, {"bloon": "moab", "share": 0.3}])]


def test_property_gap_comes_first():
    events = base_events()
    events[-1]["uncovered"] = ["camo"]
    c = J.cause_of_death(events, 43, {"auto_start": True, "steps_given_up": 2})
    assert c["category"] == "property_gap" and "camo" in c["evidence"]
    assert c["detail"]["top_groups"][0]["bloon"] == "ceramic"
    assert [p["tid"] for p in c["detail"]["last_purchases"]] == ["n1", "n1"]
    assert c["detail"]["last_purchases"][-1]["why"]["source"] == "reinforce"
    assert c["detail"]["waiting"] == "plan step 9"


def test_auto_start():
    assert J.cause_of_death(base_events(), 43, {"auto_start": True})["category"] == "auto_start"


def test_placement_from_given_up_steps_or_refused_spots():
    assert J.cause_of_death(base_events(), 43, {"steps_given_up": 1})["category"] == "placement"
    events = base_events() + [ev("place_failed", 40, kind="ace", reason="spot")]
    assert J.cause_of_death(events, 43, {})["category"] == "placement"
    old = base_events() + [ev("place_failed", 20, kind="ace", reason="spot")]
    assert J.cause_of_death(old, 43, {})["category"] != "placement"   # long before the death


def test_model_warned_unfunded():
    events = base_events(early_margin=CRISIS_MARGIN - 0.1, early_cash=2000)
    c = J.cause_of_death(events, 43, {})
    assert c["category"] == "model_warned_unfunded" and "41" in c["evidence"]
    # a warning with no cash to act on is not this cause
    poor = base_events(early_margin=CRISIS_MARGIN - 0.1, early_cash=50)
    assert J.cause_of_death(poor, 43, {})["category"] != "model_warned_unfunded"


def test_idle_cash():
    assert J.cause_of_death(base_events(cash_at_death=900), 43, {})["category"] == "idle_cash"


def test_model_overrated():
    assert J.cause_of_death(base_events(margin=1.3), 43, {})["category"] == "model_overrated"


def test_unknown():
    assert J.cause_of_death(base_events(), 43, {})["category"] == "unknown"
    assert J.cause_of_death([], None, None)["category"] == "unknown"


class StubExecutor:
    mode = "chimps"
    rules = MODE_RULES["chimps"]
    round_set = "standard"
    waiting = "plan step 8 n1 -> 3-0-2 wait"
    dead_steps = ()

    def _covers(self, sig):
        return ("camo" not in sig, "")

    def blimp_ratio(self, load):
        return 0.4


def bare_match():
    """A Match with only what the journal hooks touch."""
    m = M.Match.__new__(M.Match)
    m.ex = StubExecutor()
    m.g = SimpleNamespace(towers={"n1": Placed("n1", "ninja", 0.5, 0.5, [2, 0, 1], 900)})
    m._lives = M.LivesTracker(1)
    m._lives.update(1)
    m._margins, m._round_lost, m._leak_rounds = {43: 0.52}, 0, set()
    m._crisis_round = None
    m.depths = []
    m.stats = {"steps_given_up": 0}
    return m


def test_one_life_defeat_without_a_leak_gets_an_inferred_one():
    with TempJournalDir():
        jr = chimps_game()
        m = bare_match()
        m._journal_round(43, 491, 1)
        cause = m._journal_end("defeat", 43)
        leaks = [e for e in jr.events if e["ev"] == "leak"]
        assert len(leaks) == 1 and leaks[0]["inferred"] and leaks[0]["lost"] == 1 and leaks[0]["rnd"] == 43
        assert leaks[0]["groups"] and abs(sum(g["share"] for g in leaks[0]["groups"]) - 1) < 0.01
        end = jr.events[-1]
        assert end["ev"] == "game_end" and end["cause"]["category"] == cause["category"]
        # round 43 brings nothing the stub cannot pop, no purchase was journaled
        # (so cash proves nothing) and the model rated it 0.52: the cause stays open
        assert cause["category"] == "unknown"


def test_a_journaled_leak_is_not_doubled_and_names_uncovered_properties():
    with TempJournalDir():
        jr = chimps_game()
        m = bare_match()
        m._journal_leak(24, 1, 0)             # round 24 brings camo greens
        m._journal_end("defeat", 24)
        leaks = [e for e in jr.events if e["ev"] == "leak"]
        assert len(leaks) == 1 and not leaks[0]["inferred"]
        assert "camo" in " ".join(leaks[0]["uncovered"])
        assert jr.events[-1]["cause"]["category"] == "property_gap"


def test_a_defeat_counts_the_lives_still_trusted_as_lost():
    """Mesa ABR 2026-11-09: 100 lives gone in one round, the drop never
    confirmed before the Defeat card - the report said 0 lives lost."""
    m = bare_match()
    m._lives = M.LivesTracker(100)
    m._lives.update(100)
    m.stats = {"lives_lost": 0}
    m._count_last_lives("defeat")
    assert m.stats["lives_lost"] == 100
    m.stats = {"lives_lost": 3}
    m._count_last_lives("victory")
    assert m.stats["lives_lost"] == 3


def test_a_defeat_loses_at_least_the_starting_lives():
    """Flooded Valley 2026-11-09: ABR lost 100 lives in five seconds with the
    tracker holding one low read (10) - reported 10 lost; Apopalypse leaked
    150 -> 53 during the opening build before the first read, then counted
    20 more - reported 53. A defeat ends at 0: the whole start went."""
    m = bare_match()
    m.ex.rules = {"lives": 100}              # an instance attribute: the class's CHIMPS rules stay
    m._lives = M.LivesTracker(100)
    m._lives.update(10)                       # the one low read
    m.stats = {"lives_lost": 0}
    m._count_last_lives("defeat")
    assert m.stats["lives_lost"] == 100
    m.ex.rules = {"lives": 150, "continuous": True}
    m._lives = M.LivesTracker(150)
    for read in (53, 51, 51, 51, 49, 49, 49, 37, 37, 37, 33, 33, 33):
        m.stats["lives_lost"] = 0 if read == 53 else m.stats["lives_lost"]
        m.stats["lives_lost"] += m._lives.update(read)
    assert m.stats["lives_lost"] == 20
    m._count_last_lives("defeat")
    assert m.stats["lives_lost"] == 150
    # the journal's inferred leak carries the same uncounted lives
    with TempJournalDir():
        chimps_game()
        m._margins, m._round_lost, m._leak_rounds = {}, 0, set()
        m._journal_end("defeat", 15)
        leak = [e for e in J.current().events if e["ev"] == "leak"][-1]
        assert leak["inferred"] and leak["lost"] == 130, leak


def test_a_win_has_no_cause():
    with TempJournalDir():
        jr = chimps_game()
        assert bare_match()._journal_end("victory", 100) is None
        assert jr.events[-1]["cause"] is None and not [e for e in jr.events if e["ev"] == "leak"]


def test_a_loss_folder_gets_the_games_journal_and_its_cause():
    from btd6bot import losses as L
    with TempJournalDir(), tempfile.TemporaryDirectory() as cases:
        old_dir, L.LOSS_DIR = L.LOSS_DIR, Path(cases)
        try:
            jr = chimps_game()
            bare_match()._journal_end("defeat", 43)
            t0, t1 = jr.events[0]["t"] - 5, jr.events[-1]["t"] + 5
            J.close()
            folder = L.file_loss(None, {"start": t0, "end": t1, "map": "Alpine Run", "mode": "chimps",
                                        "outcome": "defeat", "round": 43, "lines": [(t0, "I game: placed")]})
            assert J.read(folder / "journal.jsonl")[-1]["ev"] == "game_end"
            report = (folder / "report.md").read_text(encoding="utf-8")
            assert "journal.jsonl" in report and "cause of death: unknown" in report
            assert "no recording" in report          # the journal is not a recording
        finally:
            L.LOSS_DIR = old_dir


# -- the CHIMPS guards ----------------------------------------------------------------

class StubInput:
    def __init__(self):
        self.clicks = []

    def click(self, *xy):
        self.clicks.append(xy)


def stub_game(no_sell):
    g = Game.__new__(Game)
    g.inp = StubInput()
    g.selected = []
    g.select = lambda p: g.selected.append(p.tid) or True
    g.panel = lambda p: {"sell": (0.1, 0.9)}
    g.no_sell, g.why = no_sell, {"source": "sell_useless", "reason": "out of reach"}
    g.towers = {"d1": Placed("d1", "dart", 0.3, 0.3, [0, 0, 0], 200)}
    return g


def test_game_sell_refuses_without_a_click_in_no_sell_modes():
    with TempJournalDir():
        jr = chimps_game()
        g = stub_game(no_sell=True)
        assert g.sell(g.towers["d1"]) is False
        assert g.inp.clicks == [] and g.selected == [] and "d1" in g.towers
        assert not [e for e in jr.events if e["ev"] == "sell"]


def test_game_sell_journals_the_sale_and_its_reason():
    import btd6bot.game as G
    sleep, G.time.sleep = G.time.sleep, lambda s: None
    try:
        with TempJournalDir():
            jr = chimps_game()
            g = stub_game(no_sell=False)
            assert g.sell(g.towers["d1"]) is True
            assert g.inp.clicks == [(0.1, 0.9)] and "d1" not in g.towers
            sale = jr.events[-1]
            assert sale["ev"] == "sell" and sale["why"]["source"] == "sell_useless" and sale["spent"] == 200
    finally:
        G.time.sleep = sleep


def test_executor_why_nests_and_reaches_the_journal():
    """Executor.why is what fills g.why in the live game: the innermost
    block's reason is journaled, the outer one comes back after it, and
    sell_useless sales carry their own reason."""
    import btd6bot.game as G
    sleep, G.time.sleep = G.time.sleep, lambda s: None
    try:
        with TempJournalDir():
            jr = chimps_game()
            ex = Executor.__new__(Executor)
            ex.g = stub_game(no_sell=False)
            ex.g.why = None
            ex.m = SimpleNamespace(frac_to_cell=lambda fx, fy: (fx * 100, fy * 100))
            ex.failed_spots = set()
            with ex.why("plan", "plan step 3", role="dps"):
                with ex.why("answer", "threat camo due"):
                    assert ex.g.why == {"source": "answer", "reason": "threat camo due"}
                assert ex.g.why == {"source": "plan", "reason": "plan step 3", "role": "dps"}
            assert ex.g.why is None
            assert ex._sell_and_avoid(ex.g.towers["d1"], 12, "no pops in 4 rounds") is True
            sale = jr.events[-1]
            assert sale["ev"] == "sell"
            # the sale also carries the tower and what it had cost
            assert sale["why"]["source"] == "sell_useless"
            assert sale["why"]["reason"] == "no pops in 4 rounds"
            assert sale["why"]["tower"] == "d1"
            assert ex.g.why is None
    finally:
        G.time.sleep = sleep


def test_tower_xp_has_no_monkey_knowledge_in_chimps():
    account = SimpleNamespace(mk_unlocked=["Monkey Education"])
    assert M.xp_knowledge(account, MODE_RULES["chimps"]) == ()
    assert M.xp_knowledge(account, MODE_RULES["hard"]) == ["Monkey Education"]
    assert M.xp_knowledge(None, MODE_RULES["hard"]) == ()
    plain = TowerXpCounter("Alpine Run", ()).mult
    assert TowerXpCounter("Alpine Run", M.xp_knowledge(account, MODE_RULES["chimps"])).mult == plain
    assert TowerXpCounter("Alpine Run", M.xp_knowledge(account, MODE_RULES["hard"])).mult > plain


# -- the report tool ---------------------------------------------------------------------

def write_game(folder, name, outcome, strategy, upgrade_round, cause=None, start_t=None):
    start_t = start_t or time.time() - 3600
    events = [ev("game_start", 6, map="Alpine Run", mode="chimps", strategy=strategy),
              ev("place", 6, tid="n1", kind="ninja", cost=340, why={"source": "plan"}),
              ev("upgrade", upgrade_round, tid="n1", kind="ninja", cross_after="1-0-0", cost=300,
                 why={"source": "reinforce"}),
              ev("round", 30, cash=200, margin=0.3), ev("round", 31, cash=200, margin=1.7),
              ev("leak", 30, lost=1, uncovered=["camo"], groups=[{"bloon": "green", "camo": True, "share": 1.0}]),
              ev("game_end", 43, outcome=outcome, round=43, cause=cause)]
    for e in events:
        e["t"] = start_t
    (folder / name).write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def test_journal_report_runs_on_a_synthetic_folder():
    with tempfile.TemporaryDirectory() as tmp:
        live, losses = Path(tmp) / "journal", Path(tmp) / "losses"
        live.mkdir()
        (losses / "case").mkdir(parents=True)
        write_game(live, "a.jsonl", "defeat", "chimps_ninja_sun", 40,
                   {"category": "property_gap"}, start_t=time.time() - 100)
        write_game(live, "b.jsonl", "victory", "chimps_ninja_sun", 20, start_t=time.time() - 200)
        # the loss folder's copy of game a is the same game: counted once
        write_game(losses / "case", "journal.jsonl", "defeat", "chimps_ninja_sun", 40,
                   {"category": "property_gap"}, start_t=time.time() - 100)
        buf = io.StringIO()
        with redirect_stdout(buf):
            s = JR.main(["--mode", "chimps"], journal_dir=live, loss_dir=losses)
        text = buf.getvalue()
        assert s["games"] == 2 and s["wins"] == 1 and s["losses"] == 1
        assert s["causes"] == [{"category": "property_gap", "strategy": "chimps_ninja_sun", "games": 1}]
        assert {"property": "camo", "leaks": 2} in s["uncovered"]
        assert s["lives_by_bloon"][0]["bloon"] == "camo green"
        src = {r["source"]: r for r in s["by_source"]}
        assert src["plan"]["places"] == 2 and src["reinforce"]["spent"] == 600
        calib = {r["margin"]: r for r in s["calibration"]}
        assert calib["<0.5"]["leak_rate"] == 1.0 and calib[">1.5"]["leak_rate"] == 0.0
        row = next(r for r in s["crosspaths"] if r["cross"] == "1-0-0")
        assert row["median_win"] == 20 and row["median_loss"] == 40
        assert "Causes of death" in text and "property_gap" in text
        with redirect_stdout(io.StringIO()):
            assert JR.main(["--losses-only", "--json"], journal_dir=live, loss_dir=losses)["games"] == 1
            assert JR.main(["--since", "1m"], journal_dir=live, loss_dir=losses)["games"] == 0
            assert JR.main(["--map", "nowhere"], journal_dir=live, loss_dir=losses)["games"] == 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
