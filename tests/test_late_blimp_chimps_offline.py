"""Late blimp damage in the Firing Range and Haunted CHIMPS guide builds.

Two one-life games of 2026-11-13 were lost in the blimp rounds after
getting further than any game on those maps before:

  * Firing Range (loss case 20261113_013939_FiringRange_chimps) lost round
    95 to its camo DDTs. From round 85 to 94 the bot held $5,600-28,400 for
    the guide's Super Brittle ice ($30,240), then spent the rest on the
    Tack Zone's tiers. Neither adds blimp damage there: from every legal
    cell they reach 30-55 units of one lane (the fence), the blimp check
    counts them for nothing and the damage model moved round 95 0.44 ->
    0.44 with them. The build now buys Sub Commander (the water sub that
    reaches both lanes) with that cash.
  * Haunted (loss case 20261113_020851_Haunted_chimps, and the round-96
    loss at 00:40) lost round 91 with the BFBs of the route that leaves by
    the right-hand exit alive at that exit. The two routes cross: each
    climbs one branch of the stairs to the door and comes down the other
    to the far exit. The hardened build of 0aae14f had moved every tower
    but the crossbow and the boat away from the right-hand exit; the two
    games that held round 91 still had the wizard and the glue there. The
    damage model rates the board the same either way (it credits the
    map-wide Flagship planes and sniper with the whole route), so the
    build carries the fix: the MOAB Eliminator stands by the right-hand
    branch.

Checked here:
  * Firing Range's plan has Sub Commander after Cripple MOAB and no tower
    the blimp check counts for nothing (ice, tack); the threat simulation
    (simulate_threats on the live learned map, CHIMPS cash) reads the
    blimp check at least BLIMP_FLOORS in the late rounds that were lowest
    (before: 95 0.43, 99 0.33, 100 0.59);
  * on Haunted, the blimp damage beside each exit - over the towers of the
    finished plan's board that are not map-wide, threats.blimp_dps times
    the units of the route's last EXIT_STRETCH units within the tower's
    range - is at least MIN_EXIT_DAMAGE on the weaker exit. The board that
    lost had 62,600 beside the left-hand exit and 9,650 beside the right;
    with the Eliminator by the right-hand branch 20,200 and 92,000.

Run: python tests/test_late_blimp_chimps_offline.py (no game)."""
import logging
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import pin_spots  # noqa: E402
import simulate_threats as SIM  # noqa: E402
import test_chimps_intermediate_guides_offline as TG  # noqa: E402
from btd6bot import dps_model as D  # noqa: E402
from btd6bot import maplearn as ML  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import threats as TH  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)

# Firing Range: blimp check ratio floors (before the change: 95 0.43, 99 0.33, 100 0.59)
BLIMP_FLOORS = {95: 0.6, 99: 0.45, 100: 0.75}
EXIT_STRETCH = 300.0       # world units before a route's visible end
MIN_EXIT_DAMAGE = 15000.0  # blimp_dps x route units beside the weaker exit (the lost board: 9,650)


def _load(sid):
    return yaml.safe_load((ROOT / "strategies" / "maps" / f"{sid}.yaml").read_text(encoding="utf-8"))


def _final_board(plan):
    """{tid: (kind, tiers, (fx, fy))} once every step of the plan is bought."""
    board = {}
    for st in plan["plan"]:
        if st["do"] == "place" and st["kind"] != "hero":
            board[st["id"]] = (st["kind"], (0, 0, 0), tuple(st["at"]))
        elif st["do"] == "upgrade" and st["id"] in board:
            kind, _, at = board[st["id"]]
            board[st["id"]] = (kind, S.parse_cross(st["to"]), at)
    return board


def _attack_range(kind, tiers):
    """The tower's own range at that crosspath, from the game's export."""
    code = "".join(str(t) for t in tiers)
    return float(D.attacks()["towers"][kind]["crosspaths"][code]["range"])


def test_firing_range_buys_sub_commander_not_super_brittle():
    d = _load("firingrange_chimps")
    steps = [(st["do"], st.get("id"), st.get("kind"), st.get("to")) for st in d["plan"]]
    assert not any(kind in ("ice", "tack") for _, _, kind, _ in steps), steps
    cripple = steps.index(("upgrade", "s1", None, "5-2-0"))
    commander = steps.index(("upgrade", "sb1", None, "2-0-5"))
    assert cripple < commander, (cripple, commander)


def test_firing_range_blimp_check_in_the_late_rounds():
    ML.DATA = pin_spots.live_maps_dir()
    d = _load("firingrange_chimps")
    r = SIM.simulate(dict(d, bot_ready=True), "chimps", d["map"], real_map=True, learned=True,
                     account=TG._capped_account())
    ramp = dict(r["ramp"])
    for rnd, floor in BLIMP_FLOORS.items():
        assert ramp[rnd] >= floor, (rnd, ramp[rnd], floor)


def exit_damage(d):
    """[(blimp damage beside the exit, {tid: (units in range, blimp_dps)})]
    per route of the map: over the towers of the finished plan that are not
    map-wide (the damage model credits those with the whole route already),
    threats.blimp_dps times the units of the route's last EXIT_STRETCH
    visible units inside the tower's own range."""
    track = D.Track(d["map"])
    board = _final_board(d)
    out = []
    for path in track.paths:
        hit = np.nonzero(path["hittable"])[0]
        end = path["dist"][hit[-1]]
        tail = path["xyz"][path["hittable"] & (path["dist"] >= end - EXIT_STRETCH)][:, :2]
        towers = {}
        for tid, (kind, tiers, at) in board.items():
            if TH.tower_facts(kind).get("map_wide"):
                continue
            x, z, _ = track.frac_to_world(*at)
            near = np.hypot(tail[:, 0] - x, tail[:, 1] - z) <= _attack_range(kind, tiers)
            if near.any():
                towers[tid] = (float(near.sum()) * D.TRACK_STEP, TH.blimp_dps(kind, tiers))
        out.append((sum(units * dps for units, dps in towers.values()), towers))
    return out


def test_haunted_every_exit_has_blimp_damage_beside_it():
    per_exit = exit_damage(_load("haunted_chimps"))
    assert min(total for total, _ in per_exit) >= MIN_EXIT_DAMAGE, per_exit


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
