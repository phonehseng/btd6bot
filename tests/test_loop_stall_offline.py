"""A play-loop pass that was held up looks for an end screen first, and a
stuck loop is reported (no game needed).

Spring Spring CHIMPS (2026-11-08): round 95 was lost at 22:30:28 and the
defeat card stood still from then on, yet the bot logged nothing from
22:30:14 until "off game screen: defeat" at 22:32:25 - a still screen makes
Match._frozen look for a popup within ~2 s, so the loop was not running.
The PC was busy with tools/check.py's 16 test processes, started 22:30:22,
and the screen recorder fell 45 s behind too.

Now (match.py): every pass marks its phases (Match._mark, LoopBeat); a pass
longer than LOOP_STALL_S names its slowest phase and looks at the screen
before buying anything (Match._after_stall); bot.py's snapshot thread saves
the stacks of a loop stuck in one phase (LoopBeat.stall_report)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import match as M  # noqa: E402
from btd6bot.match import LoopBeat, Match  # noqa: E402


class FakeMenus:
    def __init__(self, screen, words=()):
        self.screen = screen
        self.words = [type("W", (), {"text": w})() for w in words]
        self.identified = 0

    def identify(self):
        self.identified += 1
        return self.screen

    def dismiss_popup(self):
        return False


class FakeLives:
    def __init__(self, n):
        self.n = n

    def median(self):
        return self.n


def bare_match(screen, words=(), lives=1):
    m = Match.__new__(Match)          # only what _after_stall touches
    m.menus = FakeMenus(screen, words)
    m._lives = FakeLives(lives)
    m.g = type("G", (), {"hud": type("H", (), {"lives": staticmethod(lambda f: 0)})()})()
    return m


def test_defeat_found_after_a_held_up_pass():
    # the defeat card of 2026-11-08: "Bloons Leaked" is on it
    m = bare_match("defeat", ["DEFEAT", "Round 95", "Bloons Leaked", "Home", "Restart"])
    assert m._after_stall(131.0, ("surplus", 125.0), f=None) == "defeat"
    assert m.menus.identified == 1


def test_game_still_on_carries_on():
    m = bare_match("in_game")
    assert m._after_stall(20.0, ("plan tick", 18.0), f=None) is None


def test_slowest_phase_is_named():
    m = bare_match("in_game")
    m._mark("HUD read", now=100.0)
    m._mark("plan tick", now=100.3)
    m._mark("surplus", now=101.0)      # the plan tick took 0.7 s
    m._mark("Play button", now=231.0)  # surplus: 130 s
    m._mark("abilities", now=231.1)
    assert m._take_slowest() == ("surplus", 130.0)
    assert m._take_slowest() == ("", 0.0)     # each pass starts afresh
    LoopBeat.stop()


def test_stuck_loop_reported_once():
    LoopBeat.stop()
    assert LoopBeat.stall_report(now=1000.0) is None          # no game: nothing to report
    LoopBeat.mark("surplus", now=1000.0)
    assert LoopBeat.stall_report(now=1000.0 + M.LOOP_STALL_S - 1) is None
    report = LoopBeat.stall_report(now=1030.0)
    assert report == "stuck 30 s in surplus", report
    assert LoopBeat.stall_report(now=1060.0) is None          # once per stall
    LoopBeat.mark("abilities", now=1061.0)                     # the loop moved on ...
    assert LoopBeat.stall_report(now=1062.0) is None
    assert LoopBeat.stall_report(now=1100.0) == "stuck 39 s in abilities"   # ... and stuck again
    LoopBeat.stop()


if __name__ == "__main__":
    test_defeat_found_after_a_held_up_pass()
    test_game_still_on_carries_on()
    test_slowest_phase_is_named()
    test_stuck_loop_reported_once()
    print("ok")
