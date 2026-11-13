"""Firing Range CHIMPS round 95, the fourth loss (2026-11-13 05:08-05:33).

Loss case 20261113_053533_FiringRange_chimps. The game ran the Sub Commander
build of b4f2e95 and bought its plan to the letter: Cripple MOAB at round
83, Sub Commander at round 91. The journal's cause of death was idle cash:
round 95 started with $9,502. Why it sat:

  * the live forecast rated round 95 at 0.44 from round 86 to the end, with
    and without Sub Commander. The live bot rated with status effects off
    (dps_model.LIVE_STATUS_RATING), and this board's late game stands on
    the sniper's Maim MOAB and Cripple MOAB stuns, which then count for
    nothing. The build had been chosen on replays with them on, which rate
    the same board 0.84. Read live, nothing the bank could buy moved round
    95 ("nothing $9502 buys helps round 95 (0.44; 8 purchases tried)");
    rated with the stuns, the look buys the sniper's Maim MOAB path
    (round 95 0.84 -> 0.91). CHIMPS games now rate with status effects on
    (dps_model.live_status_rating, set by runner.Bot.play).
  * the build itself did not hold round 95 in either model: its replay
    rated 95 at 0.86, 99 0.81, 100 0.94. It now buys a Sentry Champion
    before Cripple MOAB and Sub Commander (found by the caretaker's search
    of 02:25 in worktree ct-1113-0208): 95 1.14, 99 1.10, 100 1.27.

Checked here, on the lost game's board at round 94 (the game geometry, as
tests/test_ramp_yields_to_lost_round_offline.py does) and on the build's
replay (optimize_builds.replay_plan, live learned map, live sight).
Run: python tests/test_firingrange_chimps_round95_offline.py (no game)."""
import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import optimize_builds as O                   # noqa: E402
import pin_spots                              # noqa: E402
import simulate_threats as SIM                # noqa: E402
from btd6bot import dps_model as D            # noqa: E402
from btd6bot import mapgeom as G              # noqa: E402
from btd6bot import maplearn as ML            # noqa: E402
from btd6bot import reinforce as R            # noqa: E402
from btd6bot import strategy as S             # noqa: E402
from btd6bot import threats as TH             # noqa: E402
from btd6bot.layout import LAYOUTS            # noqa: E402

MAP, MODE, BUILD = "Firing Range", "chimps", "firingrange_chimps"
RND, CASH, LOST_ROUND = 94, 9_502, 95
HERO_PLACED = 26
# the board standing when the $9,502 sat (game.log purchase lines to 05:32:45)
BOARD_94 = [
    ("sb1", "sub", "2-0-5", 0.687, 0.436), ("s1", "sniper", "5-2-0", 0.409, 0.930),
    ("hero", "hero", "0-0-0", 0.740, 0.675), ("b1", "buccaneer", "5-2-0", 0.729, 0.453),
    ("v1", "village", "4-2-0", 0.655, 0.572), ("r1", "boomerang", "3-0-2", 0.676, 0.726),
    ("sniper1", "sniper", "1-2-0", 0.275, 0.547), ("sniper2", "sniper", "0-2-2", 0.286, 0.598),
    ("sniper3", "sniper", "1-2-0", 0.318, 0.572),
]
# the ending the lost game played, after Maim MOAB (b4f2e95)
SUB_COMMANDER_ENDING = [
    {"do": "upgrade", "id": "v1", "to": "4-2-0"},
    {"do": "upgrade", "id": "s1", "to": "5-2-0"},
    {"do": "upgrade", "id": "sb1", "to": "2-0-5"},
]
DANGER_ROUNDS = (95, 99, 100)   # the rounds that ending rated under 1.0


class _Status:
    """Rate with status effects on or off inside the block."""

    def __init__(self, on):
        self.on = on

    def __enter__(self):
        self.saved = D.STATUS_RATING
        D.STATUS_RATING = self.on

    def __exit__(self, *exc):
        D.STATUS_RATING = self.saved


def _ready():
    return D.available() and TH.available()


def _executor():
    """The round-94 executor of the lost game: its plan used up, $9,502."""
    m = G.apply(ML.MapModel(MAP, LAYOUTS["16:10"]["playfield"]), G.load(MAP))
    g = SIM.CashGame(MODE, "psi", m)
    g.cash, g.round = CASH, RND
    ex = S.Executor(g, m, S.load_all()[BUILD], MODE, SIM.full_account())
    for tid, kind, cross, x, y in BOARD_94:
        g.towers[tid] = SIM.Placed(tid, kind, x, y, tiers=[int(c) for c in cross.split("-")])
    g.towers["hero"].placed_round = HERO_PLACED
    ex.purchased = len(g.towers)
    ex.idx = len(ex.plan)
    ex._init_threats()
    ex.cash_seen = CASH
    return ex


def _look(status):
    """reinforce.best on the round-94 board, without the time budget."""
    with _Status(status):
        ex = _executor()
        saved = R.LOOK_BUDGET_S
        R.LOOK_BUDGET_S = 1e9
        try:
            fc = ex._forecast()
            before = fc.margin(list(ex.g.towers.values()), LOST_ROUND)
            return before, R.best(ex, fc, CASH, RND, 100, lives=1)
        finally:
            R.LOOK_BUDGET_S = saved


def test_chimps_rates_with_status_effects_live():
    assert D.live_status_rating("chimps") is True
    for mode in ("impoppable", "hard", "apopalypse", "half_cash"):
        assert D.live_status_rating(mode) == D.LIVE_STATUS_RATING, mode


def test_without_status_effects_the_bank_found_nothing():
    """As live: round 95 at 0.44 and no purchase."""
    if not _ready():
        return
    before, (status, found) = _look(False)
    assert before < 0.5, before
    assert found is None, found[0].what


def test_with_status_effects_the_bank_buys_for_round_95():
    if not _ready():
        return
    before, (status, found) = _look(True)
    assert 0.75 < before < 1.0, before
    assert status == "buy", status
    option, worst, was, after = found
    assert worst == LOST_ROUND and option.cost <= CASH, (worst, option.what)
    assert after > was + 0.03, (option.what, was, after)


def _build():
    return yaml.safe_load((ROOT / "strategies" / "maps" / f"{BUILD}.yaml").read_text(encoding="utf-8"))


def test_the_champion_comes_before_cripple_moab_and_sub_commander():
    d = _build()
    order = [(st["id"], st.get("to") or st.get("kind")) for st in d["plan"]]
    champion = order.index(("e1", "5-2-0"))
    assert order.index(("e1", "engineer")) < champion < order.index(("s1", "5-2-0")) \
        < order.index(("sb1", "2-0-5")) < order.index(("v1", "4-2-0")), order
    assert d["planner"]["towers"]["engineer"] == [5, 2, 0]


def test_the_late_rounds_rate_over_1_and_over_the_sub_commander_ending():
    """Replayed as the executor buys, with status effects on (as the live
    CHIMPS forecast now rates): rounds 95, 99 and 100 over 1.0 and over the
    ending the lost game played."""
    ML.DATA = pin_spots.live_maps_dir()
    O.USE_LEARNED = True
    d = _build()
    old = copy.deepcopy(d)
    maim = next(i for i, st in enumerate(d["plan"]) if st.get("id") == "s1" and st.get("to") == "4-2-0")
    old["plan"] = copy.deepcopy(d["plan"][:maim + 1]) + copy.deepcopy(SUB_COMMANDER_ENDING)
    with _Status(True):
        new_m = O.replay_plan(d, rounds=DANGER_ROUNDS, live_sight=True)
        old_m = O.replay_plan(old, rounds=DANGER_ROUNDS, live_sight=True)
    for rnd in DANGER_ROUNDS:
        assert new_m[rnd] > 1.0, (rnd, new_m[rnd])
        assert new_m[rnd] > old_m[rnd] + 0.2, (rnd, new_m[rnd], old_m[rnd])


if __name__ == "__main__":
    import inspect
    fails = 0
    for fname, fn in list(globals().items()):
        if fname.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", fname)
            except Exception as e:  # noqa: BLE001 - report every failure, then fail the run
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", fname, repr(e)[:600])
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
