"""The game model decoded from the game's own files (data/game_model, made by
tools/decode_sim_model.py) and the bot code that uses it.

Three groups of checks:
  * the decoder's own logic on tiny hand-made inputs (no game files needed);
  * the decoded tables against facts every BTD6 player knows (a Dart Monkey
    costs $200, a Ceramic is worth 104 RBE, ...);
  * the bot's hand-written tables (towers.py costs, data/placement.json)
    against the decoded ones - these fail when a game update changed a
    price or footprint: re-run `python tools/decode_sim_model.py` and copy
    the new values (`--sync-placement` does it for placement.json).
"""
import importlib.util
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import gamemodel as G  # noqa: E402
from btd6bot import placement as PL  # noqa: E402
from btd6bot import towers as T  # noqa: E402

_spec = importlib.util.spec_from_file_location("decode_sim_model", ROOT / "tools" / "decode_sim_model.py")
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)

DATA = ROOT / "data" / "game_model"


# ---------------------------------------------------------------------------
# The decoder's logic, on hand-made inputs
# ---------------------------------------------------------------------------

READER = {456: "ReadBoolean", 552: "ReadInt32", 616: "ReadSingle", 664: "ReadString"}
LAYOUT = {"reader": 16, "table": 24, "index": 32}
CTX = (LAYOUT, READER, {(o - D.VTABLE_START) // D.VTABLE_ENTRY: n for o, n in READER.items()}, 60)


class NoDeclarations:
    """Stands in for Cpp2IL's class files: no field names known."""
    def find(self, short, full=None):
        return None


def test_set_routine_is_read_as_fields():
    # A routine in the loader's shape: parent first, then per object a float
    # stored at 0x58 and a "ReadBoolean() ? null : ReadString()" at 0x60.
    body = [
        (1, "Move", "rdi, rcx"),
        (2, "Call", "GameModelLoader.Set_v_Model_Fields, rcx, rdx, r8"),
        (3, "Move", "rbx, [rdi+24]"),        # the object table
        (4, "Move", "rbx, [r14+rbx]"),       # this object
        (5, "Move", "rcx, [rdi+16]"),        # the BinaryReader
        (6, "Move", "rdx, [rcx]"),
        (7, "Move", "rax, [rdx+616]"),       # ReadSingle
        (8, "Call", "rax"),
        (9, "Move", "[rbx+88], xmm0"),
        (10, "Move", "rcx, [rdi+16]"),
        (11, "Move", "rdx, [rcx]"),
        (12, "Move", "rax, [rdx+456]"),      # ReadBoolean
        (13, "Call", "rax"),
        (14, "Compare", "rax, 0"),
        (15, "JumpIfEqual", "{18}"),
        (16, "Move", "rax, 0"),
        (17, "Goto", "{22}"),
        (18, "Move", "rcx, [rdi+16]"),
        (19, "Move", "rdx, [rcx]"),
        (20, "Move", "rax, [rdx+664]"),      # ReadString
        (21, "Call", "rax"),
        (22, "Move", "[rbx+96], rax"),
        (23, "JumpIfLess", "{3}"),           # next object
    ]
    parent, levels, full = D.analyse_set_routine("Set_v_Thing_Fields", body, CTX, NoDeclarations())
    assert parent == "Model"
    assert levels == [[("@0x58", None, ["f32"]), ("@0x60", None, ["str?"])]]


def test_object_references_are_recognised():
    body = [
        (1, "Move", "rdi, rcx"),
        (2, "Move", "rbx, [rdi+24]"),
        (3, "Move", "rbx, [r15+rbx]"),
        (4, "Move", "rcx, [rdi+16]"),
        (5, "Move", "rsi, [rdi+24]"),
        (6, "Move", "rdx, [rcx]"),
        (7, "Move", "rax, [rdx+552]"),       # ReadInt32 ...
        (8, "Call", "rax"),
        (9, "Move", "rsi, [rsi+32+rax*8]"),  # ... used as table[index]: a reference
        (10, "Move", "[rbx+56], rsi"),
        (11, "JumpIfLess", "{2}"),
    ]
    _, levels, _ = D.analyse_set_routine("Set_v_Thing_Fields", body, CTX, NoDeclarations())
    assert levels == [[("@0x38", None, ["ref"])]]


class TinyProgram:
    """A loader program with one type, as LoaderProgram would derive it."""
    steps = [("table_size",), ("Create_Records",), ("set", "Thing"), ("root",)]
    typed_readers = {}

    def levels(self, type_name):
        return [[("cost", "float", ["f32"]), ("name", "string", ["str?"]), ("next", "Thing", ["ref"])]]


def test_decode_replays_sections():
    i32 = lambda v: struct.pack("<i", v)                        # noqa: E731
    f32 = lambda v: struct.pack("<f", v)                        # noqa: E731
    data = (i32(3)                                              # table: [null, a, b]
            + i32(2)                                            # Create_Records: 2 objects
            + i32(1) + i32(2)                                   # Set_v_Thing(start 1, count 2)
            + f32(1.5) + b"\x00" + b"\x01a" + i32(2)            # a: 1.5, "a", -> b
            + f32(2.0) + b"\x01" + i32(0)                       # b: 2.0, null, -> null
            + i32(1))                                           # the root is a
    root, table = D.decode(data, TinyProgram())
    assert root.type == "Thing" and root["cost"] == 1.5 and root["name"] == "a"
    assert root["next"] is table[2] and table[2]["name"] is None and table[2]["next"] is None


def test_floats_are_written_short():
    assert D.short_float(struct.unpack("<f", struct.pack("<f", 18.3))[0]) == 18.3
    assert D.short_float(200.0) == 200.0


def test_round_to_5_is_bankers_rounding():
    # Math.RoundToNearestInt(value, 5): halves go to the even multiple
    assert G.round_to_5(212.5) == 210      # 42.5 -> 42
    assert G.round_to_5(217.5) == 220      # 43.5 -> 44
    assert G.round_to_5(213.0) == 215 and G.round_to_5(212.4) == 210


# ---------------------------------------------------------------------------
# The decoded tables, against well-known facts
# ---------------------------------------------------------------------------

def test_known_towers():
    dart = G.tower("dart")
    assert dart["cost"] == 200 and dart["radius"] == 6 and dart["range"] == 32
    assert dart["placement"] == ["land"] and dart["category"] == "primary"
    assert not dart["camo"] and not dart["pops"]["lead"] and dart["pops"]["black"]
    assert dart["damage_types"] == ["sharp"]
    assert G.tower("ninja")["cost"] == 400 and G.tower("ninja")["camo"]
    assert G.tower("bomb")["pops"]["lead"] and not G.tower("bomb")["pops"]["black"]
    assert G.tower("sub")["placement"] == ["water"]
    assert G.tower("farm")["footprint"] == {"shape": "rectangle", "width": 30, "height": 30}
    assert G.tower("super")["cost"] == 2500
    assert len([t for t in json.loads((DATA / "towers.json").read_text(encoding="utf-8")).values()
                if t["available"]]) >= 26


def test_known_upgrades():
    sharp = G.upgrade("dart", 1, 1)
    assert sharp["name"] == "Sharp Shots" and sharp["cost"] == 140
    assert G.upgrade("dart", 3, 2)["name"] == "Enhanced Eyesight" and "camo" in G.upgrade("dart", 3, 2)["gains"]
    assert G.upgrade("sniper", 1, 1)["pops"]["lead"]                 # Full Metal Jacket
    assert G.upgrade("ice", 1, 2)["name"] == "Cold Snap"             # internal id "Metal Freeze"
    assert G.upgrade("spike", 1, 4)["cost"] == 9500
    for tower_id, entry in json.loads((DATA / "upgrades.json").read_text(encoding="utf-8")).items():
        if G.tower(tower_id)["available"]:
            assert [len(p) for p in entry["paths"]] == [5, 5, 5], tower_id


def test_known_heroes():
    assert G.hero("quincy")["cost"] == 540 and G.hero("quincy")["monkey_money"] == 0
    assert G.hero("churchill")["cost"] == 2000 and G.hero("churchill")["monkey_money"] == 2500
    assert G.hero("admiral_brickell")["placement"] == ["water"]
    assert G.hero("dan_dmonke")["name"] == "Dan D'Monke"
    assert len(json.loads((DATA / "heroes.json").read_text(encoding="utf-8"))) == len(T.HEROES)


def test_known_bloons():
    assert G.bloon("Red")["speed"] == 25 and G.bloon("Red")["rbe"] == 1
    ceramic = G.bloon("ceramic")
    assert ceramic["health"] == 10 and ceramic["children"] == {"Rainbow": 2} and ceramic["rbe"] == 104
    assert G.bloon("Moab")["rbe"] == 616 and G.bloon("Bfb")["rbe"] == 3164
    assert G.bloon("Zomg")["rbe"] == 16656 and G.bloon("Bad")["rbe"] == 55760
    ddt = G.bloon("ddt", camo=True)
    assert ddt["camo"] and set(ddt["immune"]) == {"lead", "black"} and ddt["moab_class"]
    assert G.immune("Lead") == ["lead"] and G.immune("Zebra") == ["black", "white"]
    assert G.bloon("ceramic", regrow=True, fortified=True, camo=True)["health"] == 20
    assert G.bloon("Bfb")["speed_vs_red"] == 0.25


def test_capabilities():
    camo = G.answers("camo")
    assert ("ninja", 0, 0) in camo and ("dart", 3, 2) in camo and ("sniper", 2, 1) in camo
    lead = G.answers("lead")
    assert ("bomb", 0, 0) in lead and ("sniper", 1, 1) in lead and ("boomerang", 3, 2) in lead
    assert G.answers("gives_camo") == [("village", 2, 2)]                # Radar Scanner
    decamo = G.answers("decamo")                                         # Shimmer, Counter-Espionage
    assert ("wizard", 3, 3) in decamo and ("ninja", 2, 2) in decamo and ("mortar", 3, 3) in decamo
    assert G.can("spike", (0, 0, 0), "hits_camo") and not G.can("spike", (0, 0, 0), "camo")
    assert G.can("dart", (0, 2, 3), "camo") and not G.can("dart", (2, 0, 0), "camo")
    assert G.can("dart", (2, 3, 0), "camo") is False
    assert G.can("dart", (5, 5, 0), "camo") is None                      # not a real crosspath


# ---------------------------------------------------------------------------
# Prices: the game's formula, and the bot's tables against the game
# ---------------------------------------------------------------------------

def test_difficulty_multipliers_come_from_the_game():
    assert G.cost_multipliers("easy") == [0.85]
    assert G.cost_multipliers("medium") == []
    assert G.cost_multipliers("hard") == [1.08]
    assert G.cost_multipliers("impoppable") == [1.08, 1.12]   # Impoppable is played on Hard
    assert G.cost_multipliers("chimps") == [1.08]             # CHIMPS: Hard prices


def test_game_prices():
    assert [G.tower_price("dart", d) for d in ("easy", "medium", "hard", "impoppable")] == [170, 200, 215, 240]
    assert G.upgrade_price("spike", 1, 4, "hard") == 10260
    assert G.upgrade_price("dart", 1, 1, "impoppable") == 165   # 140 + 11 + 16 = 167 -> 165
    assert G.upgrade_price("dart", 1, 3, "easy") == 275         # 320 - 47 = 273 -> 275
    assert G.tower_price("wizard", "easy") == 210               # 212.5 -> 210 (even)
    assert G.hero_price("quincy", "hard") == 585
    assert G.price(1000, "medium", discount=0.15) == 850


def test_bot_cost_tables_match_the_game():
    """towers.py's hand-entered Medium costs must equal the game's."""
    bad = []
    for tower_id, t in T.TOWERS.items():
        game = G.tower(tower_id)
        if game is None:
            bad.append(f"{tower_id}: not in the game model")
            continue
        if t["cost"] != game["cost"]:
            bad.append(f"{tower_id}: {t['cost']} vs game {game['cost']}")
        for path in range(1, 4):
            for tier in range(1, 6):
                mine, theirs = T.upgrade(tower_id, path, tier), G.upgrade(tower_id, path, tier)
                if mine["cost"] != theirs["cost"]:
                    bad.append(f"{tower_id} {path}-{tier} {mine['name']}: {mine['cost']} vs game {theirs['cost']}")
    for hero_id, h in T.HEROES.items():
        game = G.hero(hero_id)
        if game is None or h["cost"] != game["cost"]:
            bad.append(f"hero {hero_id}: {h['cost']} vs game {game and game['cost']}")
    assert not bad, "towers.py costs differ from the game:\n" + "\n".join(bad)


def test_bot_prices_are_the_game_prices():
    for d in ("easy", "medium", "hard", "impoppable"):
        for tower_id in T.TOWERS:
            assert T.tower_cost(tower_id, d) == G.tower_price(tower_id, d)
            for path in range(1, 4):
                for tier in range(1, 6):
                    assert T.upgrade_cost(tower_id, path, tier, d) == G.upgrade_price(tower_id, path, tier, d)
        for hero_id in T.HEROES:
            assert T.hero_cost(hero_id, d) == G.hero_price(hero_id, d)


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------

def test_placement_uses_the_game_footprints():
    assert PL.footprint_radius("dart") == 6
    assert PL.footprint_radius("farm") == 15
    assert PL.footprint_radius("hero", "quincy") == 7
    assert PL.size_level("dart") == 1 and PL.size_level("boomerang") == 2
    assert PL.size_level("buccaneer") == 3 and PL.size_level("super") == 4
    assert PL.surfaces("ice") == {"land", "water"}
    assert PL.surfaces("sub") == {"water"}
    assert PL.surfaces("hero", "admiral_brickell") == {"water"}


def test_placement_json_in_step_with_the_game():
    doc = json.loads((ROOT / "data" / "placement.json").read_text(encoding="utf-8"))
    bad = []
    for key, entry in doc["towers"].items():
        game = G.tower(key) or G.hero(key)
        if game is None:
            continue
        for field, value in D.placement_fields(game).items():
            if field == "display_range" and entry.get("range_type") != "radius":
                continue
            if entry.get(field) != value:
                bad.append(f"{key}.{field}: {entry.get(field)!r} vs game {value!r}")
    assert not bad, ("data/placement.json differs from the game model "
                     "(python tools/decode_sim_model.py --sync-placement):\n" + "\n".join(bad))


# ---------------------------------------------------------------------------
# The derived loader format itself
# ---------------------------------------------------------------------------

def test_loader_schema():
    schema = json.loads((DATA / "loader_schema.json").read_text(encoding="utf-8"))
    types = schema["types"]
    assert len(types) > 1000
    model = [f[0] for lv in types["Model"]["levels"] for f in lv]
    assert model == ["runtimeTypeIndex", "isTower", "childDependants", "_name"]
    tower = [f[:3] for f in types["TowerModel"]["levels"][0][:3]]
    assert tower == [["cost", "float", ["f32"]], ["range", "float", ["f32"]], ["ignoreBlockers", "bool", ["bool"]]]
    assert types["TowerModel"]["parent"] == "EntityModel" and types["EntityModel"]["parent"] == "Model"
    assert schema["steps"][0] == ["table_size"] and schema["steps"][-1] == ["root"]
    # no store went to an unknown field
    assert not [f for t in types.values() for lv in t["levels"] for f in lv if f[0].startswith("@")]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
