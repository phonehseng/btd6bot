"""A tower with map-wide and local sources keeps its local sources local.

dps_model.station_for used to give every source of a tower the whole map as
soon as one of them was map-wide. Lost Crevasse CHIMPS (2026-11-08 01:13-01:37,
loss case 20261108_014123) had an Inferno Ring on the lake shore at
(0.799, 0.785): its meteor reaches the whole map, its ring of fire (range 34.5)
reaches no track there - the bot read 0 pops at 4-0-2 - but the model let the
ring burn the whole track and rated round 93 at 2.95. Round 93's fortified
MOAB leaked at the west exit. The Aircraft Carrier / Carrier Flagship (planes
map-wide, the boat's own cannons local) was read the same way.

Now such a tower is two stations: the map-wide sources over the whole map,
the local ones only within the tower's reach (Station.parts, played by
dps_model._play with the rest). Checked here:
  * the lake-shore Inferno Ring: map-wide meteor, no local station; on a
    cell where the ring reaches both lanes, a local station over a part of
    the track only;
  * the Carrier Flagship: planes over the whole map, cannons near the boat;
  * a tower with only map-wide or only local sources is unchanged (sniper,
    dart);
  * the live round-93 board rates round 93 under 2 (it was 2.95), and less
    than it did with the ring counted map-wide.

Run: python tests/test_mixed_range_offline.py (also collectable by pytest).
Never touches the game."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

MAP = "Lost Crevasse"
LAKE_SHORE = (0.799, 0.785)      # the 01:00 build's t1: the ring reaches no track
BOTH_LANES = (0.457, 0.402)      # the best ring cell: 60+ units of each lane
BOAT = (0.665, 0.709)            # the Lost Crevasse build's b1

# The live board when round 93 started (journal 20261108_011559, positions of
# the placements as logged).
LIVE_R93 = [
    ("b1", "buccaneer", (5, 2, 0), 0.665, 0.709), ("starter", "dart", (0, 0, 0), 0.2, 0.428),
    ("d1", "desperado", (0, 0, 0), 0.206, 0.641), ("k1", "skywarden", (0, 0, 0), 0.227, 0.334),
    ("s1", "sniper", (4, 2, 0), 0.35, 0.181), ("x1", "dart", (2, 0, 4), 0.537, 0.453),
    ("v1", "village", (4, 2, 0), 0.729, 0.624), ("r1", "boomerang", (3, 0, 2), 0.419, 0.291),
    ("t1", "tack", (5, 0, 2), 0.799, 0.785), ("p1", "spike", (3, 2, 0), 0.457, 0.394),
]


def _track():
    return D.Track(MAP)


def _placed(tr, tid, kind, tiers, at):
    x, z, _ = tr.frac_to_world(*at)
    return D.Placed(tid, kind, tiers, x, z)


def _length(st):
    return sum(z.length for z in st.zones if z)


def test_inferno_ring_on_the_lake_shore_has_no_local_station():
    tr = _track()
    t = _placed(tr, "t1", "tack", (5, 0, 2), LAKE_SHORE)
    st = D.station_for(t, [t], tr)
    assert st is not None
    assert all(s.placement == "global" for s in st.sources), "the meteor alone is map-wide"
    assert abs(_length(st) - sum(tr.total_length())) < 1.0
    assert st.parts == [], "the ring of fire reaches no track from the lake shore"
    # its Ring of Fire (4-0-2, local only) reaches nothing there either
    assert D.station_for(_placed(tr, "t0", "tack", (4, 0, 2), LAKE_SHORE), [], tr) is None


def test_inferno_ring_on_the_track_keeps_its_ring_local():
    tr = _track()
    t = _placed(tr, "t1", "tack", (5, 0, 2), BOTH_LANES)
    st = D.station_for(t, [t], tr)
    assert len(st.parts) == 1
    ring = st.parts[0]
    assert all(s.placement != "global" for s in ring.sources)
    assert 0 < _length(ring) < 0.5 * sum(tr.total_length())
    assert sum(1 for z in ring.zones if z) == 2, "both lanes pass the cell"


def test_flagship_planes_are_map_wide_and_its_cannons_local():
    tr = _track()
    b = _placed(tr, "b1", "buccaneer", (5, 2, 0), BOAT)
    st = D.station_for(b, [b], tr)
    assert st.parts, "the boat's own cannons are a local station"
    cannons = st.parts[0]
    assert abs(_length(st) - sum(tr.total_length())) < 1.0
    assert 0 < _length(cannons) < 0.5 * _length(st)
    assert {s.placement for s in st.sources} == {"global"}
    assert "global" not in {s.placement for s in cannons.sources}


def test_single_reach_towers_are_unchanged():
    tr = _track()
    s = _placed(tr, "s", "sniper", (0, 2, 0), (0.350, 0.181))
    d = _placed(tr, "d", "dart", (0, 0, 2), (0.537, 0.453))
    assert D.station_for(s, [s], tr).parts == []
    assert D.station_for(d, [d], tr).parts == []


def test_live_round_93_board_is_no_longer_rated_safe_by_the_ring():
    fc = RoundForecast(MAP, "chimps")
    assert fc._ready()
    board = [SimpleNamespace(tid=t, kind=k, tiers=tiers, x=x, y=y) for t, k, tiers, x, y in LIVE_R93]
    st = fc.stations(board)
    now = D.round_margin(st, "chimps", 93, fc.track)
    # the old reading: every source of each mixed tower over the whole map
    merged = []
    for s in st:
        if s.parts:
            whole = D.Station(tid=s.tid, kind=s.kind, tiers=s.tiers, zones=s.zones,
                              sources=s.sources + [x for p in s.parts for x in p.sources],
                              order=s.order, strong=s.strong, camo_paths=s.camo_paths)
            merged.append(whole)
        else:
            merged.append(s)
    old = D.round_margin(merged, "chimps", 93, fc.track)
    assert now < 2.0, f"round 93 rated {now:.2f}: live it was lost"
    assert now < old, (now, old)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
