"""A panic placement grows a standing tower of its kind before buying
another bare one (Executor._panic_grow). Dark Dungeons Military Only
(2026-11-05, lost round 50): every leak placed another 0-0-0 sniper at
$330 - nine of them by the end, 2 damage every 1.6 s each against a ceramic
rush - while the build's own snipers stood at 1-2-0 and $8-12k was idle.
Now the leak's cash takes the newest sniper below the build's crosspath
(planner.towers, here sniper 2-2-0) one tier further; a new one is placed
only once every standing sniper has reached it.
Offline: the fake game and map model of test_achievement_strats_offline.
Run: python tests/test_panic_grow_offline.py"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from btd6bot import strategy as S                                    # noqa: E402
from test_achievement_strats_offline import FakeGame, FakeModel, full_account  # noqa: E402

logging.getLogger("strategy").setLevel(logging.CRITICAL)

BUILD = {
    "id": "t_panic_grow", "hero": "quincy", "modes": ["military_only"],
    "planner": {"towers": {"sniper": [2, 2, 0]}},
    "plan": [{"do": "place", "id": "s1", "kind": "sniper", "role": "dps"},
             {"do": "upgrade", "id": "s1", "to": "1-2-0"}],
    "fill": [],
    "panic": [{"do": "place", "kind": "sniper", "role": "exit"}],
}


def executor():
    g = FakeGame()
    ex = S.Executor(g, FakeModel(), dict(BUILD), "military_only", full_account())
    for _ in range(6):              # the plan: s1 placed and grown to 1-2-0
        ex.tick(10 ** 6, 20)
    assert g.towers["s1"].tiers == [1, 2, 0], g.towers["s1"].tiers
    return g, ex


def test_leak_grows_the_standing_sniper_instead_of_placing_one():
    g, ex = executor()
    ex.tick(10 ** 6, 21, lives_dropped=True)       # the leak: two panic steps
    assert g.towers["s1"].tiers == [2, 2, 0], g.towers["s1"].tiers
    assert g.placed.count("sniper") == 1, g.placed  # no bare sniper bought


def test_a_sniper_at_the_target_lets_a_new_one_be_placed():
    g, ex = executor()
    g.towers["s1"].tiers = [2, 2, 0]                # already where the build wants it
    ex.tick(10 ** 6, 21, lives_dropped=True)
    assert g.placed.count("sniper") == 2, g.placed  # the panic step placed as before
    ex.tick(10 ** 6, 21, lives_dropped=True)        # the next leak grows the new one
    new = [p for p in g.towers.values() if p.kind == "sniper" and p.tid != "s1"][0]
    assert sum(new.tiers) == 1 and g.placed.count("sniper") == 2, (new.tiers, g.placed)


def test_target_comes_from_the_build():
    g, ex = executor()
    assert ex._panic_target("sniper") == (2, 2, 0)
    assert ex._panic_target("tack") == S.Executor.PANIC_TARGET
    ex.strat = dict(BUILD, planner={}, fill=[{"do": "upgrade", "kind": "tack", "to": "2-0-3"}])
    assert ex._panic_target("tack") == (2, 0, 3)


def test_a_tower_grown_another_way_is_left_alone():
    g, ex = executor()
    g.towers["s1"].tiers = [0, 0, 3]                # off the build's crosspath
    ex.tick(10 ** 6, 21, lives_dropped=True)
    assert g.towers["s1"].tiers == [0, 0, 3] and g.placed.count("sniper") == 2, g.placed


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
