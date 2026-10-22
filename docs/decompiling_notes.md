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
- Decoding it means replaying those routines. A separate effort is building
  that decoder (see `docs/game_model.md` once it lands).

## Smaller finds

- The **Halloween season** shows up in the files too: seasonal bloon skins
  (`ZomgSepia`…), and in game the bats and pumpkins that confused motion-based
  tracking.
- The map-select screen shows each category's unlock progress as "7 / 12"
  (Advanced) or "Beat 13 more maps…" (Expert). The bot reads those instead of
  guessing.
