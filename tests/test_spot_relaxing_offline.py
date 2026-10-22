"""Offline checks for Executor._spots_widening: a place step that finds no
spot is relaxed in stages (near radius, near, segment, role) before it can
be given up. Run: python tests/test_spot_relaxing_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot.strategy import Executor  # noqa: E402


def _executor(finds):
    """An Executor whose spot finder only succeeds when finds(step) is True."""
    ex = Executor.__new__(Executor)
    ex.SPOTS_PER_HOLD = 4
    ex.seen = []
    ex.pick_spots = lambda kind, step, n=1: (ex.seen.append(dict(step)) or
                                              ([(10, 10, 1.0)] if finds(step) else []))
    ex._any_legal_spot = lambda kind: []
    return ex


def test_segment_is_dropped_when_nothing_covers_it():
    ex = _executor(lambda st: "segment" not in st)
    step = {"do": "place", "kind": "ninja", "role": "dps", "segment": [0.0, 0.5]}
    assert ex._spots_widening("ninja", step) == [(10, 10, 1.0)]
    assert "segment" in ex.seen[0] and "segment" not in ex.seen[-1]


def test_near_widens_before_it_is_dropped():
    ex = _executor(lambda st: st.get("near_radius", 0) > 10)
    step = {"do": "place", "kind": "village", "role": "support", "near": ["s1"], "near_radius": 8}
    assert ex._spots_widening("village", step)
    assert ex.seen[-1]["near_radius"] == 8 * Executor.NEAR_WIDENING[0]


def test_support_step_falls_back_to_a_damage_spot():
    ex = _executor(lambda st: st.get("role") == "dps" and "near" not in st)
    step = {"do": "place", "kind": "sniper", "role": "support", "near": ["v1"], "near_radius": 10}
    assert ex._spots_widening("sniper", step)
    assert ex.seen[-1]["role"] == "dps"


def test_gives_up_only_after_every_stage():
    ex = _executor(lambda st: False)
    step = {"do": "place", "kind": "ninja", "role": "support", "near": ["a1"], "segment": [0, 0.5]}
    assert ex._spots_widening("ninja", step) == []
    assert len(ex.seen) >= 5      # original + 2 radii + no near + no segment + as dps


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
