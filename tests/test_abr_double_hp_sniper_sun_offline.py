"""ABR with double_hp_sniper_sun: the Fast Track start holds round 23.

The account's Fast Track starts every ABR game at round 22 with ~$9,000.
ABR round 23 brings leads (and rounds 24-30 camo leads); the build bought
its sniper only after Shinobi Tactics, so the lead answer was the
Alchemist's Acidic Mixture Dip, which reaches only the ninjas beside it.
Bloody Puddles ABR was lost at round 23 on 2026-11-08 (loss case
20261108_181807_BloodyPuddles_abr: a lead leaked for 46 lives), and the
executor-faithful replay rated round 23 at 0.06 on Bloody Puddles, Mesa,
Spillway, Tricky Tracks and Water Park. The sniper now comes at 2-2-0
(Full Metal Jacket, Night Vision Goggles, Shrapnel Shot) before n1 3-0-2.

Checked here with the replay (simulate_threats.simulate on the learned map,
Fast Track start, Double Cash income), each round's starting board rated by
the live forecast:
  * round 23 holds (margin >= 1) on Bloody Puddles and Mesa, and on
    Spillway is rated 0.9 or more (0.96 since 2026-11-09, when Shrapnel Shot
    stopped counting hits on the bloon its bullet struck - see
    tests/test_thrown_off_pieces_offline.py; the build then won Spillway ABR
    live, 2026-11-09 06:27);
  * the rounds lost live hold too: Mesa 30, Spillway 40;
  * Logs ABR (won live) keeps every round from 22 to 80 at 1 or more;
  * the fill ends in Cripple MOAB on s1 (Sunset Gulch ABR, lost round 76
    with $33,000 idle and "plan and fill exhausted");
  * primary_core no longer plays ABR (Bazaar ABR, lost round 40).
Run: python tests/test_abr_double_hp_sniper_sun_offline.py"""
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O                 # noqa: E402
import simulate_threats as SIM              # noqa: E402
from btd6bot import dps_model as D          # noqa: E402
from btd6bot import strategy as S           # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

MODE, BUILD = "abr", "double_hp_sniper_sun"
BOOSTS = {"double_cash": True, "fast_track": True}     # the main account's (account.boosts)


def _margins(map_name, rounds=None):
    """{round: margin} of the build's replay on `map_name` (all rounds, or `rounds`)."""
    econ = O.economy(MODE, BOOSTS)
    scenario = {"start_round": econ.start_round, "start_cash": econ.start_cash,
                "income_multiplier": econ.cash_mult}
    boards = {}
    SIM.simulate(S.load_all()[BUILD], MODE, map_name, real_map=True, learned=True,
                 scenario=scenario, boards=boards)
    m = SIM.map_model(map_name, learned=True)
    fc = RoundForecast(map_name, MODE, m.sight,
                       (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    assert fc._ready()
    out = {}
    for rnd, board in sorted(boards.items()):
        if rounds and rnd not in rounds:
            continue
        towers = [SimpleNamespace(tid=t, kind=k, tiers=ti, x=fx, y=fy) for t, (k, ti, fx, fy) in board.items()]
        st = fc.stations(towers)
        out[rnd] = D.round_margin(st, MODE, rnd, fc.track) if st else 0.0
    return out


def test_bloody_puddles_round_23():
    ms = _margins("Bloody Puddles", {23})
    assert ms[23] >= 1.0, ms


def test_mesa_rounds_23_and_30():
    ms = _margins("Mesa", {23, 30})
    assert ms[23] >= 1.0 and ms[30] >= 1.0, ms


def test_spillway_rounds_23_and_40():
    ms = _margins("Spillway", {23, 40})
    assert ms[23] >= 0.9 and ms[40] >= 1.0, ms


def test_logs_still_holds_every_round():
    ms = _margins("Logs")
    worst = min(ms, key=ms.get)
    assert ms[worst] >= 1.0, f"round {worst} rated {ms[worst]:.2f}"


def test_fill_ends_in_cripple_moab_and_lead_answer_is_the_sniper():
    strat = S.load_all()[BUILD]
    assert strat["fill"][-1] == {"do": "upgrade", "id": "s1", "to": "5-2-0"}
    assert strat["answers"]["lead"][0] == {"do": "upgrade", "id": "s1", "to": "1-0-0"}
    ids = [st.get("id") + ":" + st.get("to", "place") for st in strat["plan"]]
    assert ids.index("s1:2-2-0") < ids.index("n1:3-0-2"), ids


def test_primary_core_does_not_play_abr():
    assert "abr" not in S.load_all()["primary_core"]["modes"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
