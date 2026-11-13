"""Water Park CHIMPS: round 7 gets a third tower it can pay for.

Why
---
Water Park CHIMPS lost round 7 on 2026-11-13 07:50 (loss case
20261113_075317, journal 20261113_075008_WaterPark_chimps), seven seconds
after Play, with 33 of the round's 55 layers popped when the first blue got
out. The build's third step was a desperado "during round 7" - but a
desperado costs $325 and round 7 starts with $258 ($650, less the boomerang
and the dart, plus round 6's $163). With plan_first the steps are bought in
order, so nothing was bought while the plan waited: round 7 was played on
boomerang + dart alone, the board that had lost it at 04:14 and 06:23, and
without even the boomerang's 0-0-1 those games had.

The fix puts the plan's second dart ($215) before the desperado, on the spot
that was Rosalia's (0.58, 0.453); she takes the dart's old spot. Of the 26
free dart spots only this one lifts round 7 on the pool lane (1.10 -> 1.51)
without dropping round 8 on the slide lane (1.43; the dart at 0.729, 0.283
rates round 7 at 1.56 and round 8 at 0.99).

What is tested
--------------
  * every tower the plan buys before round 8 is affordable when its round
    starts, on the cash the lost game had (the model's round 7 cash is the
    game's $258);
  * round 7 starts with three damage towers, and the plan does not stand
    still through it;
  * round 7 rates clearly above the boards that lost it (1.28 with the
    boomerang's 0-0-1, 1.10 without), and round 8, on round 6's lane, no
    lower than round 6, which held.

Run: python tests/test_waterpark_chimps_round7_offline.py (no game).
"""
import logging
import sys
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
import pin_spots  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import towers as T  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)

BUILD = ROOT / "strategies" / "maps" / "waterpark_chimps.yaml"
# The lost game's cash when round 7 started (game.log: "round 7  cash 258").
LIVE_ROUND7_CASH = 258
# The best rating of a board that lost round 7 here (06:23: boomerang 0-0-1 +
# dart); the new board must clear it by MARGIN_OVER_LOST.
LOST_ROUND7_MARGIN = 1.28
MARGIN_OVER_LOST = 0.15


@lru_cache(maxsize=None)
def build():
    return yaml.safe_load(BUILD.read_text(encoding="utf-8"))


def damage_places(d):
    """The plan's indices that place a damage tower (no hero, no buffer)."""
    return [i for i, st in enumerate(d["plan"]) if st.get("do") == "place" and st.get("kind") != "hero"
            and st.get("kind") not in S.Executor.BUFFERS and st.get("role", "dps") == "dps"]


def round7_cash(d):
    """The cash round 7 starts with before it buys anything: the mode's
    starting cash, less the steps buy_rounds puts in round 6, plus round 6's
    income."""
    econ = O.economy(d["modes"][0])
    bought = pin_spots.buy_rounds(d["plan"], d["modes"][0], d.get("hero"))
    spent = sum(T.tower_cost(d["plan"][i]["kind"], econ.family) for i, r in bought.items()
                if r == econ.start_round and d["plan"][i].get("do") == "place")
    return econ.start_cash - spent + econ.income(econ.start_round)


@lru_cache(maxsize=None)
def own_lane_margins():
    """{round: margin on the lane the round takes} for rounds 6-8."""
    d = build()
    rounds = range(6, 9)
    lanes = O.lane_margins(d, rounds)
    sched = O.round_lanes(d["map"], rounds)
    return {r: lanes[sched[r][0]][r] for r in rounds}


def test_the_models_round_7_cash_is_the_games():
    assert abs(round7_cash(build()) - LIVE_ROUND7_CASH) <= 5, round7_cash(build())


def test_round_7_starts_with_a_third_damage_tower_it_can_pay_for():
    d = build()
    bought = pin_spots.buy_rounds(d["plan"], d["modes"][0], d.get("hero"))
    by_round_7 = [i for i in damage_places(d) if bought.get(i, 999) <= 7]
    assert len(by_round_7) >= 3, [d["plan"][i] for i in by_round_7]
    third = d["plan"][by_round_7[2]]
    econ = O.economy(d["modes"][0])
    assert T.tower_cost(third["kind"], econ.family) <= round7_cash(d), third


def test_the_plan_buys_something_when_round_7_starts():
    """The lost build's mistake: its first step after the opening ($325)
    could not be bought with round 7's $258, so the plan stood still
    through the round (its steps' rounds began 6, 6, 8)."""
    d = build()
    bought = pin_spots.buy_rounds(d["plan"], d["modes"][0], d.get("hero"))
    rounds = [bought[i] for i in sorted(bought)]
    assert 7 in rounds, rounds[:6]


def test_round_7_rates_above_the_boards_that_lost_it():
    m = own_lane_margins()
    assert m[7] >= LOST_ROUND7_MARGIN + MARGIN_OVER_LOST, m


def test_round_8_rates_no_lower_than_round_6_which_held():
    m = own_lane_margins()
    assert m[8] >= m[6], m


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
                print("FAIL", fname, repr(e)[:1500])
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
