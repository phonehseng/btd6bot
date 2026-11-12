"""A Monkey Sub with Advanced Intel (2-x-x) shoots the camo bloons that
another tower's camo detection covers - the damage model must see that.

Luminous Cove Impoppable (2026-11-05 09:00, chimps_sub_druid_water at a
Fast Track start): two 2-0-3 subs stood next to a 0-2-3 dart with Enhanced
Eyesight, and the model rated every camo round (33, 36, 37, 42) at the
margin floor because the subs' darts counted as camo-blind. In the game's
own code the sub's camo filter (FilterInvisibleSubIntel) lets every bloon
through and only reports the sub's own blindness; the shared-range target
supplier then hands the sub the camo bloons a camo-detecting tower sees.
The real rounds 33-36 held on one life while reinforce, seeing "0.06 ->
0.06", bought bare darts instead of the plan's sub tiers.

Offline, against data/game_model/attacks.json (tools/export_attacks.py
writes the "camo_shared" flag) and Monkey Meadow's geometry.
Run: python tests/test_sub_intel_camo_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def test_export_marks_advanced_intel_only():
    """The flag sits on the sub from Advanced Intel up, on nothing else."""
    for tiers in ((2, 0, 0), (2, 0, 3)):
        # the darts are shared-camo
        sources = D.profile("sub", tiers).sources
        assert any(s.camo_shared and not s.camo for s in sources), tiers
        assert not any(s.camo_shared and s.camo for s in sources), tiers
    for tiers in ((3, 0, 2), (5, 2, 0)):
        # The export still flags the darts from 3-x-x on, but a submerged sub
        # throws no darts (dps_model._surfaced_or_submerged, 2026-11-12;
        # docs/model_audit_military.md M12): only the submerged attack, which
        # sees camo on its own, is a source.
        darts = next(a for a in D.crosspath("sub", tiers)["attacks"] if a["name"] == "Attack")
        assert darts.get("camo_shared"), tiers
        assert not any(s.camo_shared for s in D.profile("sub", tiers).sources), tiers
    for tiers in ((0, 0, 0), (1, 0, 0), (0, 2, 0), (0, 0, 4)):
        assert not any(s.camo_shared for s in D.profile("sub", tiers).sources), tiers
    for kind in ("dart", "ninja", "sniper", "druid", "alchemist"):
        assert not any(s.camo_shared for s in D.profile(kind, (0, 0, 0)).sources), kind


def test_detects_camo_is_the_towers_own_sight():
    assert D.detects_camo("ninja", (0, 0, 0))
    assert D.detects_camo("dart", (0, 0, 2))
    assert not D.detects_camo("dart", (0, 0, 0))
    assert not D.detects_camo("sub", (2, 0, 3))      # shared sight is not its own
    assert not D.detects_camo("spike", (0, 0, 0))    # spikes pop camo without seeing it


def test_intel_sub_sees_camo_next_to_a_detecting_tower():
    """On a real map: the sub's station has camo sources only when a
    camo-detecting tower stands on the board (skipped without geometry)."""
    from btd6bot.forecast import RoundForecast
    fc = RoundForecast("Monkey Meadow", "hard")
    if not fc._ready():
        print("skip: no map geometry")
        return
    sub = SimpleNamespace(tid="sb1", kind="sub", tiers=(2, 0, 3), x=0.47, y=0.52)
    blind_dart = SimpleNamespace(tid="d0", kind="dart", tiers=(0, 0, 0), x=0.30, y=0.42)
    eyes_dart = SimpleNamespace(tid="d1", kind="dart", tiers=(0, 0, 2), x=0.30, y=0.42)

    def sub_sees(board):
        st = [s for s in fc.stations(board) if s.tid == "sb1"]
        assert st, "the sub must reach the track from its water spot"
        return all(s.camo for s in st[0].sources)

    assert not sub_sees([sub])
    assert not sub_sees([sub, blind_dart])
    assert sub_sees([sub, eyes_dart])
    # a camo round then costs fewer lives with the sub's darts counted
    alone = D.simulate_round(fc.stations([eyes_dart]), "hard", 33, fc.track).lives_lost
    helped = D.simulate_round(fc.stations([eyes_dart, sub]), "hard", 33, fc.track).lives_lost
    assert helped < alone, (alone, helped)


def test_intel_camo_holds_only_on_lanes_a_detector_reaches():
    """Muddy Puddles Impoppable (2026-11-06 08:46): one camo dart in the
    top-left corner reached two of the four lanes, yet the model gave both
    Advanced Intel subs camo on all four and rated round 33 (camo yellows
    and reds) at 16.0; the camo bloons of the other lanes ended the game.
    The shared sight now holds only on the paths a detector reaches, so the
    model sees round 33 as lost and the bot buys camo detection."""
    track = D.Track("Muddy Puddles")
    if not track.paths:
        print("skip: no map geometry")
        return

    def placed(tid, kind, tiers, fx, fy):
        x, z = track.frac_to_world(fx, fy)[:2]
        return D.Placed(tid, kind, tiers, x, z)
    board = [placed("sb1", "sub", (2, 0, 4), 0.644, 0.402), placed("dr", "dart", (0, 0, 3), 0.168, 0.164),
             placed("sb2", "sub", (2, 0, 3), 0.377, 0.641), placed("a1", "alchemist", (3, 2, 0), 0.633, 0.342)]
    stations = D.stations_for(board, track)
    dart = next(s for s in stations if s.tid == "dr")
    sub = next(s for s in stations if s.tid == "sb1")
    reached = frozenset(i for i in range(len(track.paths)) if dart.covers(i))
    assert sub.camo_paths == reached and len(reached) < len(track.paths), (sub.camo_paths, reached)
    assert D.round_margin(stations, "impoppable", 33, track) < 1.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
