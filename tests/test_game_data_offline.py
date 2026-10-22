"""The bot's round table (data/rounds.json) must match the game's own round sets
(data/game_data/round_sets.json, extracted by btd6bot/gamedata.py).

A failure here usually means a game update changed rounds: re-run
`python -m btd6bot.gamedata` and update data/rounds.json from it.
Skipped when the game data has not been extracted on this machine."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from btd6bot.gamedata import parse_bloon_id  # noqa: E402

GAME = ROOT / "data" / "game_data" / "round_sets.json"
MINE = ROOT / "data" / "rounds.json"


def _key(g):
    return (g["bloon"], g["count"], bool(g["camo"]), bool(g["regrow"]), bool(g["fortified"]))


def test_bloon_ids_parse():
    assert parse_bloon_id("CeramicRegrowFortifiedCamo") == ("ceramic", True, True, True)
    assert parse_bloon_id("DdtCamo") == ("ddt", False, False, True)
    assert parse_bloon_id("Red") == ("red", False, False, False)


def test_rounds_match_the_game():
    if not GAME.exists():
        return
    game, mine = json.loads(GAME.read_text()), json.loads(MINE.read_text())
    for mode in ("standard", "abr"):
        bad = [r for r, rd in game[mode].items()
               if Counter(map(_key, rd["groups"])) != Counter(map(_key, mine[mode].get(r, {}).get("groups", [])))]
        assert not bad, f"{mode} rounds differ from the game: {bad[:10]}"


if __name__ == "__main__":
    test_bloon_ids_parse()
    test_rounds_match_the_game()
    print("ok")
