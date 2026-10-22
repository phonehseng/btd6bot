# Decompiling notes

What we learned by reading the game's own files: Unity asset bundles via
UnityPy, and `GameAssembly.dll` + `global-metadata.dat` via Cpp2IL. Everything
was done on **copies** in `~/.btd6bot_cache`, read-only and only for
understanding. The game folder was never modified, no mods were used and no
game code was run. Newest finds are at the bottom.

## How the game is built

- **Unity 6000.3.23f1**, IL2CPP build. The C# code is compiled to native code
  in `GameAssembly.dll` (~91 MB). Class, field and method names survive in
  `global-metadata.dat` (~21 MB), which is what makes the code readable at all.
- Content ships as **Addressables bundles** in
  `BloonsTD6_Data/StreamingAssets/aa/StandaloneWindows64/Full/`, about 125 of them.
  - **Every map is its own bundle** (`map_<id>_scenes_all_<hash>.bundle`). A new
    map in an update is simply a new file, which is why the bot can pick up maps
    it has never heard of.
  - Monkey Meadow's bundle is called `map_tutorial`, and Town Center's id is
    `towncentre` (British spelling).
- Cpp2IL turns the binary back into **19,298 C# declaration files** (classes,
  fields with memory offsets, method signatures) and an instruction-level dump
  of method bodies. The decompiler is 15 MB; its download was verified by SHA-256.

## Maps

- A map scene holds readable components: `Map`, `Path`, `PolyLineNodes` /
  `BezierLineNodes` / `CurvedLineNodes`, `Area`, `BaseArea`.
- **Three ways to draw a bloon path** (the surprise that broke curvy maps):
  - `PolyLineNodes`: straight lines. A child object that has children of its own
    is a Bézier curve (Monkey Meadow's corners).
  - `BezierLineNodes`: the nodes form a chain *anchor, handle, handle, anchor…*,
    sampled with `Math.MakeBezierPoints(start, end, startTangent, endTangent,
    division = 30)`. Tree Stump is one of these: its handles sit well off the
    track while its anchors sit on it.
  - `CurvedLineNodes`: a natural cubic spline through every node, the classic
    open-source `CubicSpline.FitParametric`, resampled `samplesPer100Units`
    times per 100 units.
  - Count across all maps: 140 straight, 94 spline, 35 Bézier.
- **Areas** are polygons with a type, from the `AreaType` enum: track, water,
  land, unplaceable, ice, removable, Mermonkey-only water, shallow water.
  - The **first polygon is the outline; every further one is a hole**
    (`Area.ToModel`). On Logs the grass blocks are holes in the track outline.
    Reading them as more track had blocked the best tower ground.
  - Each map's `BaseArea` gives the ground everywhere else: land on most maps,
    water on 8 island maps, and "unplaceable" on 9 maps where only drawn land
    counts (Infernal's round platforms).
- **Heights.** Points are 3-D. 26 maps have raised or sunken paths (Downstream
  up to 188 units, X Factor 150, Luminous Cove 54). The camera is tilted, so
  height pushes things up the screen. That factor was measured twice (≈0.5–0.55).
- **Scale:** 5.3 screen pixels per world unit at 1920 px wide; the play field is
  centred on the world origin.

## Placement rules (from `Map.CanPlace`)

- The tower's centre must be on the map and on ground it may use: land, water,
  or both (`TowerModel.areaTypes`).
- Its **footprint** (`EntityModel.radius`, or a rectangle) may not intersect
  track, obstacles, water (for land towers), blocker zones, or other towers.
- **Tower size classes** come from `TowerModel.GetTowerSize`, which compares the
  footprint radius with three constants read from the DLL's data section:
  - radius ≤ 6 → small
  - radius = 7 → medium
  - radius = 8 → large
  - anything else → XL
- Some areas only accept sizes up to a limit, written as cumulative lists like
  `small,medium`.
- There is **no extra "distance from the path" rule**. Everything follows from
  the areas plus footprints.

## Game data (`game_data` bundle, readable)

- **47 round sets**: Default (standard), Alternate (ABR), plus quest, Frontier
  and Rogue sets.
  - Bloon modifiers are spelled into the id, e.g. `CeramicRegrowFortifiedCamo`.
  - The bot's round table matched the game in every round except one detail:
    **DDTs are always listed as camo (`DdtCamo`)**, and our table said they
    weren't. Fixed.
- **162 achievements**, each with its goal, the statistic it counts (for
  example `bfbsPopped`), its Monkey Money reward, and an `isCoop` flag.
  15 are co-op. Rewards total 27,770 MM.
- Other contents seen there: Frontier and Rogue data, skins, emotes, trophy
  store items, and the map editor's props.

## The simulation model (`sim_model`)

- All towers, upgrades, bloons and rules live in one **17 MB binary**
  (`game_model` bundle, TextAsset `sim_model`).
- It is read by a **generated** loader, `GameModelLoader`:
  - a ~104 KB `Load` routine;
  - **1,048** per-type routines `Set_v_<Type>_Fields`. Each one first calls its
    parent type's routine, then reads fields in a fixed order with BinaryReader
    calls: float, bool, int, string, and object references as indexes into a
    big object table.
- Decoding it means replaying those routines. That decoder now exists:
  `tools/decode_sim_model.py`, explained in [`docs/game_model.md`](game_model.md).

## The simulation model, decoded

- The file is **354,277 table slots**: 224,031 objects of 999 types, 130,171
  arrays and lists, 74 dictionaries. It decodes in about a second, using every
  byte, once the format is known.
- The format is **derived from the loader's code**, not typed in: a small
  symbolic walk over each `Set_v_<Type>_Fields` routine's ISIL finds which
  `BinaryReader` method is called and where the value is stored (a field
  offset from the class declarations, or a `GetField("name")` for private
  fields). See `data/game_model/loader_schema.json` for the result.
- **BinaryReader vtable slots, verified**: byte offset `0x138 + 16 x slot`,
  slots in token order of `BinaryReader.cs` after `System.Object`'s 4: 456
  ReadBoolean, 536 ReadUInt16 (one enum is a `ushort`), 552 ReadInt32, 616
  ReadSingle, 664 ReadString. In `Load` the same reads go through IL2CPP's
  virtual-invoke helper with the slot number (15 = ReadInt32).
- Strings are `ReadBoolean() ? null : ReadString()`; asset references
  (prefabs, sprites) are a plain `ReadString()` into a struct; objects are
  Int32 indexes into the table. Four classes under an abstract parent get an
  extra loop for the parent's fields.
- **Every upgrade combination is its own TowerModel** (`DartMonkey-205`),
  every hero level too (`Quincy 7`). That is where per-upgrade facts (camo,
  lead popping, range) come from.
- **Upgrade ids are not the shown names**: "Metal Freeze" is Cold Snap,
  "Soulbind" Prince of Darkness, "Bionc Boomerang" (sic) Bionic Boomerang. The
  English names are in `localization_assets_all_<hash>.bundle`, a TextAsset
  per language (XML: `<UpgradeNames><T id="Metal Freeze">Cold Snap</T>`).
- **Every Medium cost in the bot's tables was right** (26 towers, 390
  upgrades, 18 heroes). Footprints and ranges were not: e.g. Monkey Village and
  Super Monkey are radius 11, Banana Farm a 30 x 30 square, Ice Monkey, Pat
  Fusty and Silas may stand on water.
- **Difficulty prices**: the multipliers are `GlobalCostModModel` entries in the
  game_data bundle's difficulty and mode `Mod` assets (Easy 0.85, Hard 1.08,
  Impoppable +0.12 on top of Hard; CHIMPS adds nothing: Hard prices). Upgrade
  changes are cut to whole dollars, and the final price is rounded to $5 with
  **banker's rounding** (`Math.RoundToNearestInt`, IL2CPP `bankers_roundf`,
  confirmed from the DLL's code bytes and its 1.0 / 0.5 constants). 23 Easy /
  Hard / Impoppable prices differed by $5 from the bot's old half-up formula.
- A tower called **Sheriff** is in the shop list with 0 copies allowed and no
  upgrades: present in the files, not purchasable.

## Smaller finds

- The **Halloween season** shows up in the files too: seasonal bloon skins
  (`ZomgSepia`…), and in game the bats and pumpkins that confused motion-based
  tracking.
- The map-select screen shows each category's unlock progress as "7 / 12"
  (Advanced) or "Beat 13 more maps…" (Expert). The bot reads those instead of
  guessing.
