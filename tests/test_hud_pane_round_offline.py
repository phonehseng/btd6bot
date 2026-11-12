"""The HUD's green ground follows the pane the bot sees open on screen.

Covered Garden's open pane changes as a round ends, and the bot reads the
new round number only later: on every round of the 2026-11-11 22:12 game the
log says "the screen shows pane N open - judging panes as in round R+1 (the
bot's round is R)". The bot's placement judges panes by the screen
(Executor._pane_now), but the HUD drew the ground of the stale round, so the
owner saw the green area stay on the pane that had just shut while the bot
was buying (2026-11-12). The match now writes "pane_round" to hud.json and
the field layer draws that round's ground."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import glass_field as F  # noqa: E402

MAP = "Covered Garden"


def _source():
    return F.FieldSource(ROOT / "data" / "maps")


def test_the_pane_round_decides_the_ground():
    src = _source()
    stale = src.view(MAP, "impoppable", 12, 100)
    seen = src.view(MAP, "impoppable", 12, 100, pane_round=13)
    fresh = src.view(MAP, "impoppable", 13, 100)
    assert stale is not None and seen is not None
    assert (seen.land == fresh.land).all(), "drawn as the round whose pane is open"
    assert (seen.land != stale.land).any(), "not as the stale round"


def test_the_layer_key_changes_with_the_pane_round():
    layer = F.FieldLayer(ROOT / "data" / "maps")
    rect = (0, 0, 1920, 1080)
    snap = SimpleNamespace(game={"map": MAP, "mode": "impoppable", "end_round": 100}, round=12, pane_round=None)
    k1 = layer.key(snap, rect)
    snap2 = SimpleNamespace(game=snap.game, round=12, pane_round=13)
    assert layer.key(snap2, rect) != k1


def test_maps_without_panes_ignore_it():
    src = _source()
    assert src.phase_key("Monkey Meadow", 5, 6) == src.phase_key("Monkey Meadow", 5)


if __name__ == "__main__":
    test_the_pane_round_decides_the_ground()
    test_the_layer_key_changes_with_the_pane_round()
    test_maps_without_panes_ignore_it()
    print("all tests passed")
