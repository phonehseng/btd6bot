"""A written plan's re-check knows the towers a freezing map has in ice.

Glacial Trail Primary Only (2026-11-11 22:55, opt_glacialtrail_primary_only,
loss case 20261111_230017_GlacialTrail_primary_only): the plan bought both
tack shooters with the Fast Track cash of round 10. Glacial Trail freezes a
tower in the rounds 9 and 10 after its placement round and every ten rounds
after that (dps_model.frozen_in), so both stood in ice in rounds 19-20 and
29-30: the game lost 80 lives in round 19, 82 in round 20 and the last 38 in
round 29. The file promised "worst margin 2.20, unsafe rounds: none" -
optimize_builds.replay_plan rated every round with all towers at the map's
average uptime - and the runner played it on that promise
(strategy._optimized_prior).

Checked here:
  * replay_plan rates the plan as that game bought it (both tacks in round
    10) at the "nothing pops" floor in rounds 19, 20, 29 and 30, and the
    same two tacks bought two rounds apart well above it in those rounds;
  * a tower counts as frozen whichever of the two rounds round a purchase
    the game counts from (the worse margin is kept);
  * a map without a freeze is rated as before;
  * restate_plan rewrites only the two numbers the runner reads, and the
    file as committed is no longer offered for play.
Run: python tests/test_optimizer_freeze_offline.py"""
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O                 # noqa: E402
from btd6bot import dps_model as D          # noqa: E402
from btd6bot import strategy as S           # noqa: E402

MAP = "Glacial Trail"
PLAN_FILE = ROOT / "strategies" / "optimized" / "glacialtrail_primary_only.yaml"
LOST_ROUNDS = (19, 20, 29, 30)              # both tacks in ice (placed in round 10)
FLOOR = 0.1                                 # at or under this nothing pops (the model's floor is 0.06)
# The two patches of ground beside the track, where the game took a tack
# in the lost game (its game.log): Floor4 and Floor2.
FLOOR4, FLOOR2 = [0.719, 0.641], [0.142, 0.513]
SCENARIO = {"start_round": 10, "start_cash": 3832, "income_multiplier": 2}


def _two_tacks(start_cash):
    """A Primary Only plan of two tack shooters on the two patches. With the
    Fast Track cash of round 10 all four steps are bought in that round."""
    return {"map": MAP, "modes": ["primary_only"], "hero": "quincy",
            "optimizer": {"scenario": dict(SCENARIO, start_cash=start_cash)},
            "plan": [{"do": "place", "id": "t1", "kind": "tack", "at": FLOOR4},
                     {"do": "upgrade", "id": "t1", "to": "2-3-0"},
                     {"do": "place", "id": "t2", "kind": "tack", "at": FLOOR2},
                     {"do": "upgrade", "id": "t2", "to": "3-2-0"}]}


def test_towers_bought_together_are_frozen_together():
    margins = O.replay_plan(_two_tacks(SCENARIO["start_cash"]))
    for rnd in LOST_ROUNDS:
        assert margins[rnd] <= FLOOR, (rnd, margins[rnd])
    # between the freezes the same board holds
    assert min(margins[r] for r in (12, 14, 22, 26)) > 1.0, margins


def test_towers_bought_rounds_apart_cover_for_each_other():
    """The same two finished tacks, the Floor4 one bought four rounds after
    the other: it is awake in rounds 19 and 20 and holds them, and sits in
    ice itself in rounds 23 and 24."""
    mode = "primary_only"
    setup = O.MapSetup(MAP, mode)
    ev = O.Evaluator(setup, mode)
    towers, _cash = O._replayed_towers(_two_tacks(SCENARIO["start_cash"]), setup)

    def margin(rnd, placed):
        return O._awake_margin(ev, setup, MAP, mode, rnd, towers, placed)

    together, apart = {"t1": 10, "t2": 10}, {"t1": 14, "t2": 10}
    for rnd in (19, 20):
        assert margin(rnd, together) <= FLOOR < 1.0 < margin(rnd, apart), (rnd, margin(rnd, apart))
    assert margin(23, apart) < margin(23, together)     # t1's own turn in the ice
    assert setup.track.uptime == D.tower_uptime(MAP)    # the map's average is put back


def test_either_round_of_a_purchase_counts():
    """A tower bought before round p starts may be counted from p - 1: the
    round before its first frozen round is rated without it too."""
    margins = O.replay_plan(_two_tacks(SCENARIO["start_cash"]))
    first_frozen = SCENARIO["start_round"] + D.FREEZE_FIRST_OFFSET
    assert margins[first_frozen - 1] <= FLOOR, margins[first_frozen - 1]
    assert margins[first_frozen - 2] > FLOOR


def test_a_map_without_a_freeze_is_rated_as_before():
    plan = yaml.safe_load((ROOT / "strategies" / "optimized" / "quad_deflation.yaml").read_text(encoding="utf-8"))
    assert D.tower_uptime(plan["map"]) == 1.0
    rounds = [31, 40, 50]
    setup = O.MapSetup(plan["map"], "deflation")
    ev = O.Evaluator(setup, "deflation")
    towers, _cash = O._replayed_towers(plan, setup)
    margins = O.replay_plan(plan, rounds)
    for rnd in rounds:
        whole = round(D.round_margin(ev.stations(towers), "deflation", rnd, setup.track), 2)
        assert margins[rnd] == whole, (rnd, margins[rnd], whole)


def test_restate_rewrites_the_numbers_the_runner_reads():
    """On a copy of the plan with the numbers it was lost with."""
    tmp = Path(tempfile.mkdtemp()) / PLAN_FILE.name
    lines = PLAN_FILE.read_text(encoding="utf-8").splitlines()
    lines = ["  worst_margin: 2.20" if ln.startswith("  worst_margin:")
             else "  unsafe_rounds: []" if ln.startswith("  unsafe_rounds:") else ln for ln in lines]
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        was = yaml.safe_load(tmp.read_text(encoding="utf-8"))
        assert S._optimized_prior(dict(was), {}) == []          # played on its promise
        before, worst = O.restate_plan(tmp)
        now = yaml.safe_load(tmp.read_text(encoding="utf-8"))
        assert before == 2.2 and worst <= FLOOR
        assert now["optimizer"]["worst_margin"] == worst
        assert set(LOST_ROUNDS) <= set(now["optimizer"]["unsafe_rounds"])
        assert now["plan"] == was["plan"] and now["fill"] == was["fill"]
        assert S._optimized_prior(dict(now), {}), "a plan with frozen rounds must not be played"
        O.restate_plan(tmp)                                      # a second run leaves one note
        assert sum(ln.startswith("# Restated ") for ln in tmp.read_text(encoding="utf-8").splitlines()) == 1
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


def test_the_lost_plan_is_not_offered_for_play():
    plan = yaml.safe_load(PLAN_FILE.read_text(encoding="utf-8"))
    margins = O.replay_plan(plan)
    if min(margins.values()) < S.OPTIMIZED_MIN_MARGIN:
        assert S._optimized_prior(dict(plan), {}), "the file promises more than its replay holds"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
