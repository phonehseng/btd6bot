"""#Ouch Apopalypse: the pond build replaces the general builds that lost there.

Case 20261112_114515_Ouch_apopalypse (2026-11-12 11:37): apopalypse_ninja_
sniper's fourth loss on #Ouch (rounds 47, 49, 51 and now 54). All 150 lives
held to round 52; the MOABs of rounds 53-54 then walked past three ninjas,
three snipers and two darts standing at single corners of the map's four
separate lanes (stills end_030-031). apopalypse_apache_spikes already
excluded #Ouch after its round-48 loss.

The fix is strategies/maps/ouch_apopalypse.yaml: seven buccaneers and a sub
in the central pond, the one place that reaches all four lanes. Its
tools/apopalypse_check.py numbers (minutes per run) are in its header; here:
  * the general builds stay off #Ouch Apopalypse and the map build fits it;
  * every planned spot is legal in plan order on the map's geometry;
  * every pond boat reaches all four lanes or three (the header's claim);
  * on one fixed MOAB window (the rater's constructed worst round 54,
    rounds 54-55 laid end to end) the build's round-54 board out-rates the
    board the lost game had standing: 2.09 against 0.80 (2026-11-12),
    held here at 1.8 and twice the lost board.
Run: python tests/test_ouch_apopalypse_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import planner as PL           # noqa: E402
from btd6bot import strategy as S           # noqa: E402

MAP = "#Ouch"
MODE = "apopalypse"
BUILD = "ouch_apopalypse"
LOSING = ("apopalypse_ninja_sniper", "apopalypse_apache_spikes")

# The lost game's board when its last round was read (journal round 47, the
# spots of its place events) - it stood unchanged to the defeat at round 54
# but for n2 2-0-4 and a fresh sniper.
LOST_BOARD = {
    "opener": ("dart", (0, 3, 2), 0.5905, 0.2913),
    "n1": ("ninja", (4, 0, 2), 0.35, 0.7257),
    "n2": ("ninja", (2, 0, 4), 0.35, 0.2913),
    "a1": ("alchemist", (3, 2, 0), 0.4729, 0.7683),
    "s1": ("sniper", (3, 2, 0), 0.521, 0.4191),
    "ninja1": ("ninja", (0, 0, 0), 0.6279, 0.2913),
    "v1": ("village", (2, 0, 2), 0.3981, 0.7428),
    "ninja2": ("ninja", (1, 0, 0), 0.5905, 0.3935),
    "s2": ("sniper", (0, 2, 4), 0.4515, 0.7257),
    "dart1": ("dart", (0, 2, 4), 0.5905, 0.6065),
    "sniper1": ("sniper", (2, 2, 0), 0.5905, 0.4531),
    "n3": ("ninja", (4, 0, 2), 0.521, 0.2913),
}
# The build's round-54 board in the apopalypse_check replay (2026-11-12).
BUILD_ROUND = 54


def _specs():
    return {sid: PL.StrategySpec.from_any(dict(s, id=sid, **(s.get("planner") or {})))
            for sid, s in S.load_all().items() if not s.get("achievement")}


def _build_board(upto_step):
    """{tid: (kind, tiers, fx, fy)} after the build's plan steps [0, upto_step)."""
    board = {}
    for st in S.load_all()[BUILD]["plan"][:upto_step]:
        if st["do"] == "place" and st["kind"] != "hero":
            board[st["id"]] = (st["kind"], (0, 0, 0), *st["at"])
        elif st["do"] == "upgrade" and st["id"] in board:
            k, _, x, y = board[st["id"]]
            board[st["id"]] = (k, tuple(int(c) for c in st["to"].split("-")), x, y)
    return board


def test_losing_builds_exclude_ouch_and_the_map_build_fits():
    from btd6bot.account import AccountState
    specs = _specs()
    category = AccountState().map_category(MAP)
    for sid in LOSING:
        assert MAP in specs[sid].excluded_maps, sid
    general = [sid for sid, s in specs.items()
               if s.maps is None and PL._strategy_fits(s, MAP, category, MODE)]
    assert not general, f"general builds still offered on {MAP} {MODE}: {general}"
    assert PL._strategy_fits(specs[BUILD], MAP, category, MODE)


def test_spots_legal_in_plan_order_and_boats_reach_the_lanes():
    import simulate_threats as SIM
    from btd6bot import placement as P
    from btd6bot import dps_model as D
    import optimize_builds as O
    m = SIM.map_model(MAP, learned=False)
    setup = O.MapSetup(MAP, MODE)
    track = setup.track
    placed = []
    for st in S.load_all()[BUILD]["plan"]:
        if st["do"] != "place":
            continue
        hero = S.load_all()[BUILD]["hero"] if st["kind"] == "hero" else None
        v = P.valid_spots(m, st["kind"], hero=hero, towers=placed)
        cx, cy = m.frac_to_cell(*st["at"])
        assert v is not None and v[cy, cx], f"{st['id']} at {st['at']} is not legal"
        placed.append((cx, cy, st["kind"], hero))
        if st["kind"] == "buccaneer":
            x, z, _ = track.frac_to_world(*st["at"])
            zones = track.zones(x, z, D.profile("buccaneer", (0, 0, 2)).range)
            lanes = sum(1 for zz in zones if zz)
            assert lanes >= 3, f"{st['id']} reaches {lanes} lanes"


def test_build_out_rates_the_lost_board_on_a_moab_window():
    import apopalypse_check as AC
    rater = AC.Rater(MAP)
    plan = S.load_all()[BUILD]["plan"]
    upto = next(i for i, st in enumerate(plan) if st.get("id") == "sb1")   # before the sub: rounds 47-53
    own, lost = _build_board(upto), dict(LOST_BOARD)
    margins = {}
    for name, board in (("build", own), ("lost", lost)):
        st = rater.stations(board)
        window = [rater.worst_rounds(board, st, r)["alone"] for r in (BUILD_ROUND, BUILD_ROUND + 1)]
        margins[name] = rater.margin(st, window)
    assert margins["build"] >= 1.8, margins
    assert margins["build"] >= 2 * margins["lost"], margins


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.ERROR)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
