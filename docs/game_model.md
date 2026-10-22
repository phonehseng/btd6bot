# The game model: exact tower, upgrade, hero and bloon data

The bot used to carry hand-typed tables (costs from a community site,
footprints and ranges "from memory"). The game itself ships all of these
numbers in one file. This page explains that file, how
`tools/decode_sim_model.py` reads it, and what lands in `data/game_model/`.

Ground rules, as for all the decompiling work (see `decompiling_notes.md`):
only **copies** of game files in `~/.btd6bot_cache` are read; the game folder
is never modified; no game code or DLL is run; no mods. The decompiled code is
read as text, to learn the file format.

## Using it from the bot

`btd6bot/gamemodel.py` loads the JSON files lazily and answers small questions.
Every function returns `None` (or an empty answer) when the data is missing,
so callers keep a fallback.

| call | answer |
|---|---|
| `tower("dart")` | the tower's entry (bot ids, as in `towers.TOWERS`) |
| `upgrade("dart", 3, 2)` | path 1-3, tier 1-5: name, cost, XP, what it can do, what it `gains` |
| `hero("quincy")` | cost, footprint, range, placement, Monkey Money price, unlock level, abilities |
| `bloon("ceramic", camo=True)` or `bloon("CeramicCamo")` | speed, health, children, RBE, immunities |
| `footprint_radius(kind, hero)`, `surfaces(kind, hero)`, `size_class(r)` | placement facts |
| `price(base, difficulty, kind)`, `tower_price`, `upgrade_price`, `hero_price` | the game's own price formula |
| `can("dart", (0, 2, 3), "camo")` | a capability of one upgrade combination |
| `answers("lead")` | `[(tower, path, min tier)]`, same shape as `strategy.ANSWERS` |
| `refresh()` | re-decode after a game update (for start-up, next to `gamedata.refresh()`) |

Capability words: `camo` (the game's camo detection: an attack may target
camo bloons and fires something that hits them), `hits_camo` (something
damaging can hit camo, aimed or not - Spike Factory spikes), `lead`, `black`,
`white`, `purple`, `frozen` (some damage can pop that property), `decamo`
(strips camo for good: Shimmer, Signal Flare, Counter-Espionage, Submerge and
Support, Cleansing Foam), `gives_camo` (Radar Scanner), `gives_damage_type`
(MIB), `moab_bonus`. Abilities are left
out of these: they are not always on.

`placement.py` now takes footprint radii and surfaces from here first, and
`towers.py`'s price functions use the decoded costs and the game's formula.

## The files in data/game_model

| file | from | contents |
|---|---|---|
| `towers.json` | sim_model + English texts | per bot tower id: `game_id`, `name`, `category`, `cost` (Medium), `radius`, `footprint` (circle radius or rectangle), `placement` (area types), `range`, `global_range`, `camo`, `hits_camo`, `pops`, `damage_types`, `damage_bonus`, `abilities`, `max_tiers`, `available`, and `crosspaths`: capability words for every upgrade combination the game has a model for |
| `upgrades.json` | sim_model + English texts | per tower, `paths[3][5]`: `id` (internal), `name` (shown in game), `cost`, `xp` (tower XP to unlock), `model`, `range`, the same capability fields, `gains` |
| `heroes.json` | sim_model + English texts | per bot hero id: cost, footprint, range, placement, `monkey_money`, `unlock_player_level`, `max_level`, `first_level_with` (level each capability starts), `abilities` with level and cooldown |
| `bloons.json` | sim_model | per game bloon id (`CeramicRegrowFortifiedCamo`): `speed` (world units/s), `speed_vs_red`, `health`, `layer`, `children` (id: count), `rbe`, `leak_damage`, `immune`, camo/regrow/fortified/moab flags |
| `difficulties.json` | game_data bundle | each difficulty / mode "Mod": cost multipliers, first and last round |
| `loader_schema.json` | Cpp2IL output | the derived file format (below), for checking and debugging |
| `source.json` | | which bundles were read, sizes, counts; the refresh stamp |

Unknown towers get a snake_case id from their own name (`sheriff`: present
in the model but not purchasable, `available: false`).

## The file format of sim_model

`sim_model` is a 17 MB TextAsset in `game_model_assets_all_<hash>.bundle`. It
has no header or field names: it is the exact sequence of `BinaryReader` calls
made by a generated C# class, `GameModelLoader` (1,077 methods). Its `Load`
routine reads, in order:

1. **Table size** (Int32). Every object, list and dictionary gets a slot in one
   table `m`; slot 0 is null. References everywhere are Int32 indexes into it.
2. **Containers**, in a fixed order:
   - `CreateArraySet<T>`: a count, then a length per array (filled later);
   - `Read_a_<T>_Array`: arrays of plain values read on the spot (Int32,
     Single, String, Vector3 = 3 floats, Keyframe = 6 floats, ...);
   - `CreateListSet<T>`, `Read_l_Single_List`, `CreateDictionarySet<K,V>`,
     `Read_String_v_<V>_Dictionary` the same way for lists and dictionaries.
3. **Records**: 999 x `Create_Records<T>`: a count, then that many empty objects.
4. **Fields**: 999 x `Set_v_<Type>_Fields(start, count)`, start and count read
   from the file. Each routine first calls its parent type's routine for the
   same objects (TowerModel -> EntityModel -> Model), then loops over the
   objects reading its own fields. So the file holds, for one type, all the
   objects' `Model` fields, then all their `EntityModel` fields, then all their
   `TowerModel` fields.
5. **Links**: `LinkArray`, `LinkList`, `LinkDictionary` fill the containers
   with references (a dictionary entry is a string key plus a reference).
6. **Root**: one Int32, the slot of the `GameModel`.

A field is one of these read patterns ("atoms"):

| atom | written by the loader as | used for |
|---|---|---|
| `f32`, `i32`, `bool`, `u16` | `br.ReadSingle()` etc. | numbers, enums (`TowerSet`, `AreaType`, `BloonProperties` flags) |
| `str?` | `br.ReadBoolean() ? null : br.ReadString()` | strings |
| `str` | `br.ReadString()` passed to a struct constructor | asset references (prefab, sprite, sound GUIDs) |
| `ref` | `m[br.ReadInt32()]` | objects, arrays, lists |
| several | e.g. 3 x `ReadSingle` into one `Vector3` | small structs |

Private fields are set through reflection (`Type.GetField("name")` then
`FieldInfo.SetValue`), public ones by a direct store at the field's memory
offset. Four classes sit under an abstract parent without its own routine;
their routine has an extra loop for the parent's fields first ("levels").

Strings are .NET `BinaryReader` strings: a 7-bit-encoded byte length, then UTF-8.

## How the decoder works

`tools/decode_sim_model.py`, in five numbered sections:

1. **Reading Cpp2IL's output.** `GameModelLoader.txt` (the ISIL dump: numbered
   statements like `Move rax, [rdx+552]`, `Call rax`) and the class
   declaration files (`public float cost; //Field offset: 0x58`).
2. **Deriving the format.** A small symbolic walk goes through each routine's
   statements in order and tracks what registers hold: the loader (`this`),
   its reader (`this+0x10`), its table (`this+0x18`), the object being
   filled, the result of each read. That yields events - a read, a store at an
   offset or through a `FieldInfo`, a comparison with 0, a backward jump (end
   of a loop), the call to the parent routine. Reads are grouped up to the next
   store; the store's offset (or the `GetField` string) names the field.
   - Which `BinaryReader` method a vtable call is comes from
     `BinaryReader.cs`: virtual methods are numbered in metadata-token order
     after `System.Object`'s 4, and IL2CPP puts slot *n* at byte
     `0x138 + 16n` (so 456 = ReadBoolean, 536 = ReadUInt16, 552 = ReadInt32,
     616 = ReadSingle, 664 = ReadString; all verified).
   - The generic helpers (`CreateArraySet`, `LinkArray`, ...) are shared code,
     so the ISIL can't say which type they are called for - and doesn't need
     to: their read pattern is the same for every type. Each one's pattern is
     still checked against what the decoder assumes, so a changed helper
     stops the decoder instead of producing garbage.
   - `Load` calls the generic helpers by address; the declarations give their
     RVAs, and the cached DLL copy's PE header gives the load address.
3. **Replaying.** A short Python loop reads the file with these rules. Built-in
   proofs: every one of the 17,076,980 bytes is consumed, and every one of the
   224,031 objects is filled by exactly one `Set` section. The current file
   decodes in about a second (about 6 s with the export).
4. **Exporting.** Towers and heroes come from `GameModel.towers` (one
   `TowerModel` per tower *and* upgrade combination: `DartMonkey`,
   `DartMonkey-100`, ..., and one per hero level); the shop lists
   (`towerSet`, `heroSet`) give order and limits; upgrades follow the
   `UpgradePathModel` links from model to model. Capabilities are read off the
   objects under each `TowerModel` (ability subtrees and cosmetic objects
   skipped):
   - camo: an `AttackModel` whose `AttackFilterModel` has no active
     `FilterInvisible...` filter, firing a `ProjectileModel` without one that
     carries damage (a carrier with `FilterAllModel`, like a bomb in flight,
     hits nothing itself);
   - popping: every damage source (`DamageModel`, damage-over-time) has
     `immuneBloonProperties`, the bloon properties it can't damage
     (`BloonProperties`: Lead 1, Black 2, White 4, Purple 8, Frozen 16);
   - `damage_types` are community names for those sets (sharp = Lead+Frozen,
     explosion = Black, cold = Lead+White, ...), for reading only;
   - `damage_bonus` from `DamageModifierForTagModel` (tag `Moabs`, `Ceramic`...).
   English names come from the localization bundle's "English" table
   (`UpgradeNames`, `TowerNames`, `HeroNames`): internal ids differ, e.g.
   "Metal Freeze" is Cold Snap, "Soulbind" is Prince of Darkness.
5. **Refreshing.** `refresh()` re-extracts when the game_model bundle's name
   (it carries a content hash) or `EXTRACT_VERSION` changed. All files are
   computed before any is written, so a failure keeps the previous data.

## Prices on each difficulty

Read from the game's code and data, not guessed:

- Each difficulty and mode is a `Mod` asset in the game_data bundle. Easy has
  `GlobalCostModModel(0.85)`, Hard `1.08`, the Impoppable mode `1.12`; Medium
  and CHIMPS (`Clicks`) have none. Impoppable and CHIMPS are modes of Hard
  (`ModeType.GetModesForDifficulty`), so their games carry Hard's mod too:
  Impoppable = 1 + 0.08 + 0.12 = 1.2, **CHIMPS = Hard prices (1.08)**.
- `GlobalCostModModel.Mutate` adds `(m - 1) x Medium cost` per mod, in 32-bit
  floats. For towers and heroes the cost is a float; for upgrades it is a
  whole number and the change is cut toward zero (`cvttss2si`).
- At purchase, `TowerManager.GetTowerCost` / `GetTowerUpgradeCost` apply
  discounts and call `Math.RoundToNearestInt(price, 5)` =
  `round(price / 5) * 5`, where `round` is **banker's rounding** (IL2CPP's
  `bankers_roundf`: an exact .5 goes to the even number).

So Easy Wizard Monkey is 212.5 -> **$210** (not 215), Impoppable Sharp Shots is
140 + 11 + 16 = 167 -> **$165** (not 170). `gamemodel.price` implements this;
`towers.price` now calls it.

## How it was checked

- Structure: all bytes used, every object filled once, and all 4,485 fields'
  read patterns match their declared C# types (floats read with `ReadSingle`,
  bools with `ReadBoolean`, enums with `ReadInt32`/`ReadUInt16`, ...); no
  store goes to an offset the class declarations do not name.
- Known values: Dart Monkey $200, radius 6, range 32; Ninja $400 with camo
  detection; Super Monkey $2,500; Sharp Shots $140; Spiked Mines $9,500;
  Quincy $540; Captain Churchill $2,000 and 2,500 Monkey Money; RBE of a
  Ceramic 104, MOAB 616, BFB 3,164, ZOMG 16,656, DDT 816, BAD 55,760; a BFB
  moves at 0.25x a red's speed; DDTs are immune to lead and black.
- All of the bot's 26 tower, 390 upgrade and 18 hero Medium costs agree.
- Camo detection, as worked out from the filters, agrees with the game's own
  upgrade descriptions: Increased Accuracy (Mortar 0-0-1) "enough to hit Camo
  Bloons", Advanced Targeting (Dartling 0-1-0), Eagle Eye, Echosense
  Precision, Night Vision Goggles, Cold Snap ("Metal Freeze": "Can freeze and
  pop Lead and Camo Bloons"); Submerge and Support only reveals camo, its
  attack comes with Bloontonium Reactor (4-x-x).

## After a game update

1. Start the bot or run `python tools/decode_sim_model.py`. If the new file
   still decodes with the old loader description, the JSON is refreshed and
   nothing else is needed.
2. If it reports that the format does not match (bytes left over, objects
   unfilled, a helper pattern changed), the loader changed: copy the new
   `GameAssembly.dll` and `global-metadata.dat` into
   `~/.btd6bot_cache/il2cpp/in/`, re-run Cpp2IL (as described in
   `decompiling_notes.md`) and run the tool again.
3. `python tools/check.py`: `test_game_model_offline.py` fails when the
   bot's own tables (`towers.py` costs, `data/placement.json`) no longer match.
   `python tools/decode_sim_model.py --sync-placement` updates placement.json;
   `towers.py` costs are edited by hand (the price functions already use the
   decoded costs meanwhile).

## Not decoded (yet)

- Attack stats in a bot-friendly form: damage, pierce, attack rate, projectile
  speed per upgrade are in the model (`WeaponModel.rate`,
  `ProjectileModel.pierce`, `DamageModel.damage`) but not exported.
- Line of sight: `TowerModel.ignoreBlockers` / `AttackModel.attackThroughWalls`
  exist; `data/placement.json`'s hand-written notes are still used.
- Paragons, powers, Monkey Knowledge, Geraldo's items, boss bloons' special
  behaviours, freeplay groups: decoded but not exported.
- Ranges that change with upgrades are only in `upgrades.json` (`range` of
  each tier's model), not used by the bot yet.
