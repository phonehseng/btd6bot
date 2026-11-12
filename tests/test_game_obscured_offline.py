"""The bot pauses while another program's window lies over the game.

Luminous Cove CHIMPS (2026-11-12 16:04, loss case 20261112_160448): BTD6
was the foreground window, so the bot played on, while the Claude app's
window covered the right third of the map; round 8 was lost. Screen.obscured_by
samples points of the game area with WindowFromPoint; python windows (the
bot's own HUD overlays) do not count."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import screen as S  # noqa: E402

GAME, HUD, OTHER = 100, 200, 300          # pids


def _screen(owner_at):
    """A Screen whose WindowFromPoint returns a window owned by
    owner_at(fx, fy) - a pid - at each sampled point."""
    sc = S.Screen.__new__(S.Screen)
    sc.left, sc.top, sc.width, sc.height = 0, 0, 1000, 1000
    sc._pid = lambda: GAME
    pts = {}

    def wfp(pt):
        fx, fy = pt[0] / 1000, pt[1] / 1000
        pid = owner_at(fx, fy)
        h = len(pts) + 1
        pts[h] = pid
        return h
    S.win32gui = SimpleNamespace(WindowFromPoint=wfp, GetAncestor=lambda h, f: h,
                                 GetWindowText=lambda h: "Claude")
    S.win32process = SimpleNamespace(GetWindowThreadProcessId=lambda h: (0, pts[h]))
    S._is_python = lambda pid: pid == HUD
    return sc


def test_an_app_window_over_the_right_third_pauses():
    sc = _screen(lambda fx, fy: OTHER if fx > 0.65 else GAME)
    assert sc.obscured_by() == "Claude"


def test_the_bots_own_hud_does_not_pause():
    assert _screen(lambda fx, fy: HUD if fy < 0.6 else GAME).obscured_by() is None


def test_a_single_point_is_not_enough():
    assert _screen(lambda fx, fy: OTHER if (fx, fy) == (0.85, 0.85) else GAME).obscured_by() is None


if __name__ == "__main__":
    import importlib
    for name in ("test_an_app_window_over_the_right_third_pauses", "test_the_bots_own_hud_does_not_pause",
                 "test_a_single_point_is_not_enough"):
        importlib.reload(S)
        globals()[name]()
    print("all tests passed")
