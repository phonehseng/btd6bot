"""Map categories (no game needed): the game's own map data is the truth, and
the map-select sweep can no longer file maps under the wrong tab.

Before: both account files said Monkey Meadow, In The Loop, Skull Tweak,
Three Mines 'Round, Spa Pits and Tinkerton (the first Beginner page) were
"expert" - the Expert tab's read showed the Beginner page, the last matching
tab won, and overrides were only ever added.
Run: python tests/test_map_categories_offline.py"""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import account as A  # noqa: E402
from btd6bot import gamedata as G  # noqa: E402
from btd6bot import runner as R  # noqa: E402

FIRST_BEGINNER_PAGE = ["Monkey Meadow", "In The Loop", "Skull Tweak", "Three Mines 'Round", "Spa Pits", "Tinkerton"]


def item(map_id, difficulty, sprite=None, browser=0):
    """One entry of the game's MapSet, as the bundle stores it."""
    ref = f"MapImages[MapSelect{sprite}Button]" if sprite else "dea8e4f4b0c528d42b899d187f1e3da0"
    return {"id": map_id, "difficulty": difficulty, "mapSprite": {"guidRef": ref},
            "isBrowserOnly": browser, "isDebug": 0}


def test_mapset_entries():
    e = G.map_entry(item("Tutorial", 0, "MonkeyMeadow"))
    assert e == {"id": "Tutorial", "sprite": "MonkeyMeadow", "category": "beginner",
                 "browser_only": False, "debug": False}
    assert G.map_entry(item("ThreeMinesAround", 0, "ThreeMinesAroundMap"))["sprite"] == "ThreeMinesAround"
    assert G.map_entry(item("#ouch", 3))["category"] == "expert"
    assert G.map_entry(item("Blons", 3, browser=1))["browser_only"]


def test_game_ids_find_their_display_names():
    entries = [G.map_entry(i) for i in (
        item("BaseEditorMap", 1, browser=1), item("Tutorial", 0, "MonkeyMeadow"),
        item("TownCentre", 0, "TownCentre"), item("ThreeMinesAround", 0, "ThreeMinesAroundMap"),
        item("MuddyPuddles", 3, "MuddyPuddles"), item("BloodyPuddles", 3, "BloodyPuddles"),
        item("ShipCapture", 2, "ShipCapture"), item("ProtectTheYacht", 1, browser=1),
        item("SomeFutureMap", 1, "SomeFutureMap"))]
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "maps.json"
        f.write_text(json.dumps(entries), encoding="utf-8")
        with mock.patch.object(A, "GAME_MAPS_FILE", f):
            got = A._game_map_categories()
    assert got == {"Monkey Meadow": "beginner", "Town Center": "beginner", "Three Mines 'Round": "beginner",
                   "Muddy Puddles": "expert", "Bloody Puddles": "expert", "Ship Capture": "advanced"}, got


def test_extracted_game_data_covers_every_map():
    """With data/game_data/maps.json extracted, every map has the game's category."""
    if not A.GAME_MAPS_FILE.exists():
        print("  (no extracted game data here - skipped)")
        return
    missing = [m for m in A.MAPS if m not in A.GAME_MAP_CATEGORIES]
    assert not missing, missing
    assert all(A.GAME_MAP_CATEGORIES[m] == "beginner" for m in FIRST_BEGINNER_PAGE)


def test_account_files_hold_no_override_the_game_data_contradicts():
    if not A.GAME_MAPS_FILE.exists():
        return
    for f in (ROOT / "data" / "accounts").glob("*.json"):
        if f.name.count(".") != 1:
            continue  # backups, achievements, benches
        raw = json.loads(f.read_text(encoding="utf-8"))
        bad = {m: c for m, c in raw.get("map_category_overrides", {}).items()
               if A.GAME_MAP_CATEGORIES.get(m, c) != c}
        assert not bad, (f.name, bad)


GAME = {m: "beginner" for m in FIRST_BEGINNER_PAGE}


def test_game_data_beats_overrides():
    raw = {"map_category_overrides": {m: "expert" for m in FIRST_BEGINNER_PAGE} | {"Brand New Map": "advanced"}}
    with mock.patch.dict(A.GAME_MAP_CATEGORIES, GAME, clear=True):
        acc = A.AccountState.from_dict(raw)
        assert acc.map_category_overrides == {"Brand New Map": "advanced"}, "stale overrides dropped on load"
        acc.map_category_overrides["Monkey Meadow"] = "expert"   # even if one sneaks back in
        assert acc.map_category("Monkey Meadow") == "beginner"


def test_a_map_seen_in_its_own_category_loses_its_override():
    with mock.patch.dict(A.GAME_MAP_CATEGORIES, GAME, clear=True):
        acc = A.AccountState()
        acc.map_category_overrides["Monkey Meadow"] = "expert"
        assert acc.note_map_category("Monkey Meadow", "beginner")
        assert not acc.note_map_category("Tinkerton", "expert"), "the page disagrees with the game data"
        assert acc.map_category_overrides == {}
    with mock.patch.dict(A.GAME_MAP_CATEGORIES, {}, clear=True):   # no game data on this machine
        acc = A.AccountState()
        acc.note_map_category("Ship Capture", "intermediate")
        assert acc.map_category("Ship Capture") == "intermediate"
        acc.note_map_category("Ship Capture", A.MAPS["Ship Capture"])
        assert "Ship Capture" not in acc.map_category_overrides


def test_tabs_that_read_the_same_page_are_not_used():
    beginner = {"monkeymeadow", "intheloop", "skulltweak", "threeminesround", "spapits", "tinkerton"}
    reads = {"beginner": beginner, "intermediate": {"lostcrevasse", "luminouscove", "ancientportal"},
             "advanced": {"shipcapture", "ascent", "mushroomgrotto"}, "expert": set(beginner)}
    first = R.tab_first_pages(reads)
    assert first["beginner"] == first["expert"] == set()
    assert first["intermediate"] == reads["intermediate"] and first["advanced"] == reads["advanced"]


def test_page_category():
    known = {"Monkey Meadow": "beginner", "In The Loop": "beginner", "Lost Crevasse": "intermediate"}
    first = {"beginner": set(), "intermediate": {"lostcrevasse", "luminouscove"},
             "advanced": {"shipcapture", "ascent"}, "expert": set()}
    # 1. known maps decide - the old code let a duplicate Expert tab win here
    assert R.page_category({"monkeymeadow", "intheloop"}, ["Monkey Meadow", "In The Loop"],
                           first | {"expert": {"monkeymeadow", "intheloop"}}, None, known) == "beginner"
    # 2. no two known maps agree: an unambiguous tab match
    assert R.page_category({"shipcapture", "ascent", "newmap"}, [], first, "intermediate", known) == "advanced"
    # 3. nothing to go on: the page continues the current category
    assert R.page_category({"newmap", "othermap"}, [], first, "advanced", known) == "advanced"
    assert R.page_category({"newmap"}, [], first, None, known) is None
    # known maps that disagree are no evidence
    assert R.page_category(set(), ["Monkey Meadow", "Lost Crevasse"], first, "expert", known) == "expert"


def test_first_win_on_a_map_moves_the_category_unlock_bars():
    acc = A.AccountState()
    acc.category_progress = {"beginner": [1, 1], "advanced": [7, 12], "expert": [7, 20]}
    acc.record_result("Quiet Street", "easy", "s", True)
    assert acc.category_progress == {"beginner": [1, 1], "advanced": [8, 12], "expert": [8, 20]}
    acc.record_result("Quiet Street", "primary_only", "s", True)   # same map again
    acc.record_result("Logs", "easy", "s", False)                  # a loss
    assert acc.category_progress["advanced"] == [8, 12]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
