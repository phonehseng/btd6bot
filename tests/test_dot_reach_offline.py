"""Damage over time is credited only on the bloons an attack reaches.

Ancient Portal CHIMPS (2026-11-12 17:58-18:11, ancientportal_chimps;
journal logs/journal/20261112_175800_AncientPortal_chimps.jsonl) was lost on
round 63, its rush of 162 ceramics. The live model rated the round 5.19;
without the glue gunner g1 (Bloon Liquefier 4-2-0) it rated 0.45. The model
credited every glued bloon with the glue's whole 110 damage over 11 s, on a
ceramic shell of 10 HP: one glue popped eleven shells. The glob and the
Splat it throws off were also counted as two glues on the same crowd.

dps_model._dot_hp_rate now caps each glued (burnt, poisoned) bloon at the
health of its layer, and _dot_key counts one attack's pieces that carry the
same damage over time as one status (the game refreshes it, never stacks
it). The board below is the log's, rebuilt with tools/rate_board.py
board_from_log between the game's NEXT line and its game over.

All offline: no game, no game files. Run: python tests/test_dot_reach_offline.py
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402

ROUND = 63
# (tid, kind, tiers, x, y) in screen fractions, as the log placed them
ANCIENT_PORTAL_R63 = [
    ("sb1", "sub", (2, 0, 4), 0.623, 0.658), ("starter", "dart", (0, 0, 0), 0.58, 0.249),
    ("hero", "hero", (0, 0, 0), 0.516, 0.658), ("n1", "ninja", (0, 0, 0), 0.719, 0.538),
    ("ans_lead_bomb", "bomb", (0, 0, 0), 0.703, 0.436), ("a1", "alchemist", (3, 0, 1), 0.58, 0.828),
    ("w1", "wizard", (4, 2, 0), 0.601, 0.198), ("v1", "village", (3, 2, 0), 0.612, 0.436),
    ("g1", "glue", (4, 2, 0), 0.612, 0.283), ("r1", "boomerang", (3, 0, 2), 0.655, 0.479),
]


def _live_margin(board, drop=None):
    """The round's margin as the live bot rates it (status effects off,
    dps_model.LIVE_STATUS_RATING)."""
    from btd6bot.forecast import RoundForecast
    saved = D.STATUS_RATING
    try:
        D.STATUS_RATING = D.LIVE_STATUS_RATING
        fc = RoundForecast("Ancient Portal", "chimps")
        if not fc._ready():
            return None
        towers = [SimpleNamespace(tid=t, kind=k, tiers=c, x=x, y=y) for t, k, c, x, y in board if t != drop]
        return D.round_margin(fc.stations(towers), "chimps", ROUND, fc.track)
    finally:
        D.STATUS_RATING = saved


def _glue_beside(track, tiers, at=0.5):
    pts = track.paths[0]["xyz"]
    p = pts[int(len(pts) * at)]
    return D.stations_for([D.Placed("g", "glue", tiers, float(p[0]) + 15.0, float(p[1]))], track)


def test_ancient_portal_round_63_is_rated_short():
    """The lost round rates well under 1.0, and the glue no longer carries
    it: 5.19 before (0.45 without g1), about 0.5 now."""
    if not D.available():
        return
    with_glue = _live_margin(ANCIENT_PORTAL_R63)
    if with_glue is None:
        return
    without = _live_margin(ANCIENT_PORTAL_R63, drop="g1")
    assert with_glue < 0.7, with_glue
    assert with_glue - without < 0.2, (with_glue, without)


def test_one_liquefier_does_not_hold_a_ceramic_rush():
    """One 4-2-0 glue alone beside Monkey Meadow's track, CHIMPS round 63
    (three bursts of 40-42 ceramics and 75 leads). Before the fix it rated
    2.2 with status effects off and 3.5 with them on; the game's glue
    reaches a few of each burst. Bloon Solver 5-2-0 rated 3.9 / 9.7."""
    if not D.available():
        return
    track = D.Track("Monkey Meadow")
    saved = D.STATUS_RATING
    try:
        for status in (False, True):
            D.STATUS_RATING = status
            for tiers in ((4, 2, 0), (5, 2, 0)):
                m = D.round_margin(_glue_beside(track, tiers), "chimps", ROUND, track)
                assert m < 0.6, (tiers, status, m)
    finally:
        D.STATUS_RATING = saved


def test_liquefier_reaches_shots_times_pierce_bloons():
    """Against a packed ceramic burst the 4-2-0 glue's damage over time on
    ceramic shells is no more than the bloons its best piece glues a second
    times a shell's 10 HP (it is about 200). Before, glob and splat were
    summed at 110 damage each and capped only by the bloons in the zone:
    3,300 HP a second here, 1,422 at the Ancient Portal glue's spot."""
    if not D.available():
        return
    track = D.Track("Monkey Meadow")
    (st,) = _glue_beside(track, (4, 2, 0))
    zone = next(z for z in st.zones if z is not None)
    ceramic = D.layer("Ceramic")
    rho = 1.0                                  # a burst: a bloon every unit of track
    glued = max(D._hit_rate(s, ceramic, rho, zone) for s in st.sources if s.dot_total)
    hp, *_ = D._Rates(st).get("Ceramic", 1.0, rho, next(i for i, z in enumerate(st.zones) if z is not None))
    assert hp <= glued * ceramic.hp * st.strength * D.TOWER_EFFICIENCY + 1e-6, (hp, glued)
    assert hp < 400.0, hp


def test_every_dot_is_capped_at_the_layer_health():
    """Every damage-over-time source of every crosspath, on every bloon
    layer: no more than its hits times the layer's health (or its own
    whole amount when that is smaller)."""
    if not D.available():
        return
    track = D.Track("Monkey Meadow")
    zone = D.stations_for([D.Placed("d", "dart", (0, 0, 0), *_beside_xy(track))], track)[0].zones[0]
    attacks = json.loads((ROOT / "data" / "game_model" / "attacks.json").read_text(encoding="utf-8"))
    checked = 0
    for kind, tower in attacks["towers"].items():
        for code in tower["crosspaths"]:
            prof = D.profile(kind, tuple(int(c) for c in code))
            for src in (prof.sources if prof else ()):
                if not src.dot_total:
                    continue
                for bid in ("Red", "Ceramic", "Lead", "Moab", "Zomg"):
                    lay = D.layer(bid)
                    hits = D._hit_rate(src, lay, 0.5, zone)
                    got = D._dot_hp_rate(src, hits, lay, 0.5, zone)
                    assert got <= hits * min(src.dot_total, lay.hp) + 1e-9, (kind, code, src.name, bid)
                    checked += 1
    assert checked > 100


def test_one_attacks_pieces_share_one_glue():
    """The glob and its Splat carry the same damage over time: a bloon
    struck by both holds one glue, so they share one key; different burns
    of one attack (a mortar's ordinary and MOAB burns) do not, nor do a
    Buccaneer's front and rear darts, which fly at different bloons."""
    glue = D.profile("glue", (4, 2, 0)).sources
    keys = {D._dot_key(s) for s in glue if s.dot_total}
    assert len(keys) == 1, keys
    mortar = [s for s in D.profile("mortar", (0, 0, 5)).sources if s.dot_total]
    assert len({D._dot_key(s) for s in mortar}) == len(mortar) > 1
    darts = [s for s in D.profile("buccaneer", (0, 2, 5)).sources if s.dot_total]
    assert len({D._dot_key(s) for s in darts}) == len(darts) == 2


def _beside_xy(track, at=0.5):
    pts = track.paths[0]["xyz"]
    p = pts[int(len(pts) * at)]
    return float(p[0]) + 15.0, float(p[1])


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
