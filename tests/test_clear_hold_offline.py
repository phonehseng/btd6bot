"""In a one-life game Play waits until the track is clear (Match._hold_for_clear).

The game lights the Play button again as soon as a round's last bloon has been
sent. Luminous Cove Impoppable (2026-11-06): the bot pressed it while round
98's MOABs were half way along the route, round 99's 60 MOABs joined them and
the one life was gone 5 s later. Offline: a bare Match with a scripted watch."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import match as M   # noqa: E402


class Watch:
    """A bloon watch that answers the depths it is given, one per look."""

    def __init__(self, depths, ready=True):
        self.depths = list(depths)
        self._ready = ready

    def ready(self):
        return self._ready

    def look(self, frame, now=None, towers=()):
        return self.depths.pop(0) if self.depths else 0.0


class Ex:
    def __init__(self, rules):
        self.rules = rules


class G:
    towers = {}


def bare_match(depths, rules=None, ready=True):
    m = M.Match.__new__(M.Match)
    m.ex, m.g = Ex({"one_life": True} if rules is None else rules), G()
    m.watch = Watch(depths, ready)
    m._clear_hold = {}
    return m


def test_waits_while_bloons_are_on_the_route_then_plays():
    m = bare_match([0.51, 0.55, 0.0, 0.0, 0.0, 0.0])
    now = time.time()
    assert m._hold_for_clear(98, None, now)          # MOABs half way: wait
    assert m._hold_for_clear(98, None, now + 0.4)
    for k in range(M.CLEAR_LOOKS - 1):               # empty looks, not enough yet
        assert m._hold_for_clear(98, None, now + 1 + k)
    assert not m._hold_for_clear(98, None, now + 6)  # clear: Play
    assert not m._hold_for_clear(98, None, now + 7)  # and released for the round


def test_a_bloon_seen_again_restarts_the_count():
    m = bare_match([0.0, 0.0, 0.3] + [0.0] * M.CLEAR_LOOKS)
    now = time.time()
    for k in range(3):
        assert m._hold_for_clear(50, None, now + k)
    for k in range(M.CLEAR_LOOKS - 1):
        assert m._hold_for_clear(50, None, now + 3 + k)
    assert not m._hold_for_clear(50, None, now + 10)


def test_a_panel_over_the_field_does_not_count_as_clear():
    m = bare_match([None] * 10)
    now = time.time()
    for k in range(10):
        assert m._hold_for_clear(60, None, now + k * 0.3)


def test_never_waits_longer_than_the_cap():
    m = bare_match([0.9] * 100)
    now = time.time()
    assert m._hold_for_clear(70, None, now)
    assert not m._hold_for_clear(70, None, now + M.CLEAR_HOLD_MAX_S + 1)


def test_no_wait_with_lives_to_spare_continuous_sends_or_no_watch():
    now = time.time()
    assert not bare_match([0.9], rules={})._hold_for_clear(40, None, now)
    assert not bare_match([0.9], rules={"one_life": True, "continuous": True})._hold_for_clear(40, None, now)
    assert not bare_match([0.9], ready=False)._hold_for_clear(40, None, now)
    m = bare_match([0.9])
    m.watch = None
    assert not m._hold_for_clear(40, None, now)



def test_a_watch_that_never_clears_stops_the_waits_for_the_game():
    """Balance Impoppable (2026-11-06): the watch read bloons on a clear track
    every round and every wait ran to the cap. After CLEAR_CAPPED_ROUNDS
    such rounds Play no longer waits that game."""
    m = bare_match([0.33] * 1000)
    now = time.time()
    for k in range(M.CLEAR_CAPPED_ROUNDS):
        rnd = 70 + k
        assert m._hold_for_clear(rnd, None, now)                          # waits ...
        assert not m._hold_for_clear(rnd, None, now + M.CLEAR_HOLD_MAX_S + 1)   # ... to the cap
        now += 60
    assert not m._hold_for_clear(80, None, now), "the waits are off for the rest of the game"


def test_a_round_that_clears_resets_the_capped_count():
    m = bare_match([0.33, 0.0, 0.0, 0.0, 0.0] + [0.33] * 100)
    now = time.time()
    m._clear_capped = M.CLEAR_CAPPED_ROUNDS - 1
    assert m._hold_for_clear(70, None, now)
    for k in range(M.CLEAR_LOOKS):
        m._hold_for_clear(70, None, now + 1 + k)
    assert m._clear_capped == 0
    assert m._hold_for_clear(71, None, now + 60), "the next round still waits"


def test_a_game_with_rounds_coming_is_not_quit_for_time():
    """Balance Impoppable was quit at round 86 after its 71-minute limit
    while rounds kept coming; only a stalled game, or one far past its
    limit, ends as a timeout."""
    m = M.Match.__new__(M.Match)
    start = time.time() - 72 * 60                      # past a 71-minute limit
    m.stats = {"start": start}
    m._t_round_change = time.time() - 30               # a new round 30 s ago
    assert not m._out_of_time(71)
    m._t_round_change = time.time() - M.ROUND_STALL_S - 1
    assert m._out_of_time(71), "no new round for ROUND_STALL_S: a stalled game ends"
    m.stats = {"start": time.time() - (M.GAME_HARD_LIMIT_FACTOR * 71 + 1) * 60}
    m._t_round_change = time.time()
    assert m._out_of_time(71), "past the hard limit the game ends whatever happens"
    m.stats = {"start": time.time() - 10 * 60}
    assert not m._out_of_time(71)

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
