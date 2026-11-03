"""Global-range towers only fit a map that has room for them (no game needed).

High Finance Medium (2026-11-03): mapfit called a heli's coverage 1.0
("global range reaches everything") although no cell of the map is big
enough for its pad until the buildings are bought. The planner rated
solo_heli 0.84, every heli step was given up ("0 legal cells") and the game
was lost at round 38 with one sniper. Cornfield (solo_ace, the next game)
has room for a single ace. Run: python tests/test_global_room_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import mapfit as F  # noqa: E402


def coverage(map_name, kind):
    model, _ = F._model_for(map_name)
    assert model is not None, f"{map_name}: no geometry"
    return F.kind_coverage(model, kind)["early"]


def test_no_room_no_fit():
    assert coverage("High Finance", "heli") == 0.0
    assert coverage("High Finance", "ace") == 0.0
    assert coverage("High Finance", "sniper") == 1.0     # a small tower still fits
    print("ok High Finance: no room for a heli or an ace, snipers fit")


def test_room_for_one_is_a_partial_fit():
    assert 0.0 < coverage("Cornfield", "ace") < 1.0
    print("ok Cornfield: room for a single ace is a partial fit")


def test_open_map_full_fit():
    assert coverage("Cargo", "heli") == 1.0
    print("ok Cargo: room for several helis is a full fit")


if __name__ == "__main__":
    test_no_room_no_fit()
    test_room_for_one_is_a_partial_fit()
    test_open_map_full_fit()
    print("ALL OK")
