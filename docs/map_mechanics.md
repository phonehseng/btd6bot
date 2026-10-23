# Map mechanics

Some maps change while a game is played: obstacles can be bought away,
roof panes open and close, ice melts, gears turn, platforms drift, a giant's
eye switches towers off, bloons vanish into gates and tunnels. The bot reads
all of this from the game's own map scenes, the same way it reads tracks and
placement areas, and plans its placement so that nothing it builds is lost
or stranded later.

Everything here comes from **copies** of the game files in
`~/.btd6bot_cache` (map scene bundles read with UnityPy, `GameAssembly.dll`
and its metadata decompiled with Cpp2IL). Nothing in the game folder is
changed, no mods are used and no game code is run.

## Where it lives

| What | File |
|---|---|
| Extraction from the map scenes | `btd6bot/gamefiles.py` (`GEOMETRY_VERSION` 7) |
| Per-map data (areas, paths, mechanics) | `data/map_geometry/<map id>.json`, key `"mechanics"` |
| Readable summary of every map | `data/map_mechanics.json` (rebuilt with the geometry) |
| What changes, when, and what it means for placement | `btd6bot/mapgeom.py` (`dynamics`, `placement_grids`, `removables`) |
| Tower placement | `btd6bot/placement.py` (`valid_spots`) |
| Reach per tower and map | `btd6bot/mapfit.py`, `data/map_fit.json` |
| Pictures to check a map by eye | `python tools/render_map_mechanics.py "Covered Garden"` |
| The table below | `python tools/map_mechanics.py --write` |
| Tests | `tests/test_map_mechanics_offline.py` |

## How a map describes its mechanics

The scene components that matter (class names from the decompiled
`Assets.Scripts.Unity.Map` namespace):

- **`Removeable`** (and `RoundRemoveable`, `CustomMushroomGrottoRemoveable`):
  an obstacle with a price (`removealCost`, sic), whether it can be bought
  yet (`isActive`), and what happens to its ground when sold. The Areas on
  the obstacle's own object are what it occupies. The game's
  `Map.DestroyRemoveable` then either deletes those areas (`destroyArea`,
  uncovering what lies beneath) or changes their type to
  `defaultTerrianType` (usually land).
- **`RoundRemoveable`** (Three Mines 'Round's ore): you pay, it is mined for
  `durationRounds` rounds and then pays `cashReward` (e.g. $435 returns
  $870, $3,000 returns $4,600).
- **`RegenRemovable`** with a `LinearRoundBasedCost`: a paid switch that
  comes back (Polyphemus' eye, Castle Revenge's engine, Ancient Portal's
  portals).
- **`MapEvent`**: "when these triggers fire, do these actions", with
  `MapActions` lists it can call. Triggers include round start/end
  (`StartRoundTrigger`, `AfterRoundTrigger` with a round and an "every N"),
  time, a removable being bought, a click on a map object, a tower being
  placed, lives running low. Actions include `CreateArea(s)`,
  `DestroyArea(s)`, `CycleAreas`, `SetAreaActive`, `RotateArea`,
  `MovingPlatform`, `SuspendTowersOnArea`, `PathActive`, `ToggleSplitter`,
  `SellRemoveable`, `RemovableActive`, `MapEventActive`.
- **`PathPointInfo`** on path nodes: `bloonsInvulnerable` (bloons cannot be
  hit there: gates, tunnels, the hole they drop into) and
  `disablePathTargeting` (ground-targeting towers cannot aim there).
- **Splitters** (which path the next bloon takes: alternating by round,
  MOABs only, ...) and **gizmos** (paid map abilities: Tricky Tracks' train,
  Workshop's power core and reverse motor, Dark Dungeons' statue).

What the game does when areas change (read from the decompiled simulation,
`Simulation.Track.Map`):

- `CreateArea` (used by `CreateAreaAction` and `CycleAreasAction`) does
  **not** remove towers already standing there. New towers just cannot be
  placed while the area is there.
- `DestroyArea` re-checks every tower that stood on the area with
  `CanPlace` and **destroys** those whose spot is no longer valid (land
  towers on melted ice, on flooded ground).
- `MoveArea` / `RotateArea` **carry** the towers on the area along.
- `SuspendTowersOnArea` switches the towers on an area off until the
  player pays to switch them back on.
- `CycleAreasAction` with `invert`: each step one area of the list is
  removed (open) and all the others are created (closed); the step is
  `round / roundsPerRotate`.

## How the bot treats each kind

Changes are sorted into **automatic** ones (they will happen: rounds passing,
time, map load, bloons spawning, the bot's own towers) and **player** ones
(buying, clicking: they happen only if the bot does it, and it does neither
today). Unknown trigger types count as automatic.

Placement is then checked in four states of the map - as it starts, with
everything that may appear, without everything that may vanish, and both -
and a cell is used only if it is fine in all of them. Line-of-sight blockers
that are there at any time count as always there.

| Kind | Maps | Bot's treatment |
|---|---|---|
| Removable obstacle | 37 maps, 120 obstacles ($250-$5,000; two $0 easter-egg popups) | Stays an obstacle. `mapgeom.removables(map)` lists name, price, position (world and screen), outline, whether it can be bought yet; `mapgeom.removal_effect(model, name)` says which cells it frees and which it ruins; `placement.valid_spots(..., removed=[names])` places as if bought. Not bought by the strategy (see "Wiring" below). |
| Ore to mine | Three Mines 'Round (6) | Recorded with price, rounds and payout; not used. |
| Areas that open and close in turn | Covered Garden (roof panes, every round), Midnight Mansion (magic fires, every 2 rounds, line-of-sight blockers) | Covered Garden's panes are timed (`mapgeom.pane_open`): the open pane's ground takes towers in its round (bottom-left on round 1, then clockwise), and a tower under a pane is upgraded or sold only in its pane's rounds. Fires block sight for the whole game. |
| Areas that vanish by themselves | Erosion (ice melts after rounds 18, 36, 54, 72, 90), Cargo/Quarry (trucks/rocks cleared at the first MOAB), One Two Tree (blockers cleared as plots open), Skull Tweak/Spa Pits (easter-egg click areas), Polyphemus/Ancient Portal (click areas) | Ground that may go is never used (towers on it would be destroyed). Obstacles that may go still block until they are gone. With `last_round` a short game ignores later melts; with `now_round` ground that has certainly opened counts. |
| Areas that appear by themselves | One Two Tree (land plots at rounds 2-77), Polyphemus/Castle Revenge/Ancient Portal (click areas) | Counted as there for obstacles, as not there for ground (plots are used once `now_round` passes their round). |
| Rotating ground | Geared (two gears, 45 and 108 degrees after every round) | Carries its towers. Global-range towers may stand on it; other towers only on "steady" spots that keep covering at least 60 % of their track in every position (`mapgeom.steady_spots`). On Geared there are none: finite-range plans fit it at 0. |
| Moving platforms | Sanctuary (6 platforms and 2 moving obstacles, moving at the start of every round) | As rotating ground; the water and land a platform sweeps over are never used, and a moving obstacle blocks everything it passes. |
| Towers switched off | Polyphemus (the eye closes after round 6 and every 10 rounds; towers on its pool stop until the player pays) | The pool is never used. |
| Bloons out of reach | 12 maps (Castle Revenge 38 %, Dark Castle 63 %, Midnight Mansion 55 %, Quad 59 %, X Factor 36 % of the track...) | Those stretches get no track heat, so coverage is not counted there; their lanes still block placement. |
| No ground targeting | Mushroom Grotto (dark caves), Skull Tweak | Recorded (matters only for spike-style path targeting). |
| Paths that open | Cargo, Quarry, Sunset Gulch, Workshop (MOAB routes after round 39/40), Bloonarius Prime (prime-round whirl path), Ancient Portal | Painted when the map opens them by itself; paths only the player can open (Workshop's power-core loops, Spa Pits' and Skull Tweak's easter-egg routes) are not, so no tower is placed to cover a route bloons never take. |
| Alternating paths | 14 maps | Every path is painted, so all get covered. |
| Paid switches, map abilities, clickable objects | Polyphemus, Castle Revenge, Ancient Portal; Tricky Tracks, Workshop, Dark Dungeons; 14 maps | Not used. |
| Seasonal obstacle | Tricky Tracks (Halloween pumpkin patch) | Counted as there. |

### Line of sight: which towers suit which maps

Towers that need line of sight lose track behind blockers; on maps where
blockers come and go (Midnight Mansion's fires), the bot counts them as always
there. Global-range towers (sniper, mortar, heli, ace, dartling, and farms)
ignore both line of sight and moving ground, so they are the better choice on
**Geared**, **Sanctuary**, **Midnight Mansion**, **Covered Garden** and, in
long games, **Erosion**. `data/map_fit.json` has an `"advice"` list per map
saying so, and its reach numbers already reflect it (Geared: 0 for every
finite-range tower, 1 for global ones).

## Two finds about placement itself

Reading the mechanics turned up two older mistakes, now fixed:

1. **Stacked areas.** The game sorts areas by height, highest first
   (`Simulation.Track.Map.CreateMap`), and `Map.CanPlace` takes the first
   area containing the tower's centre: its type decides. The footprint is then
   checked only against areas from that height up to 5 units above it
   (constant 5.0 in the DLL's data); areas whose height plus render offset
   reach 250 never take towers. Raised platforms are built exactly like that:
   placeable land 1 unit above an unplaceable cliff (Quarry, Castle Revenge,
   Mesa, Sulfur Springs, Tinkerton, Dark Dungeons, Water Park...). The bot
   used to let the cliff win everywhere, so Quarry had no placeable cell at
   all and Sulfur Springs three.
2. **Blocker circles.** The circles the game collides projectiles with are
   stored in the simulation's flat plane, where a point at height h sits at
   y = -(z + h/sqrt(3)). Read that way all 9,430 circles of all maps lie
   inside their own blocker polygons (read as local coordinates, as before,
   under half did, and stray circles blocked large parts of maps). The circles now
   only count for line of sight, not as obstacles to stand on. The same
   factor, 1/sqrt(3) = 0.577, is the camera tilt the bot measured live as
   `HEIGHT_FACTOR` = 0.55.

### Maps whose usable ground changed most

Cells where a land or water tower's centre may stand (of 17,280), before this
work, and now for the whole game (what the bot uses by default):

| Map | Before | Now |
|---|---:|---:|
| Sulfur Springs | 3 | 9,017 |
| Quarry | 0 | 7,923 |
| Castle Revenge | 789 | 5,139 |
| Dark Dungeons | 1,498 | 6,471 |
| Water Park | 3,531 | 8,343 |
| Tinkerton | 3,934 | 8,933 |
| Cornfield | 847 | 1,834 |
| Midnight Mansion | 1,292 | 2,598 |
| Mesa | 2,730 | 5,225 |
| One Two Tree | 1,874 | 3,221 |
| Erosion | 12,001 | 1,414 (12,272 at the start; a 40-round game keeps much more) |
| Covered Garden | 5,332 | 2,198 (7,098 with every pane open) |

Geared and Sanctuary keep their cells, but finite-range towers may use only
steady spots there (none on Geared, a few on Sanctuary).

## Wiring removables into the strategy

Buying is deliberately not wired into `strategy.py`. What is ready for it:

1. `mapgeom.removables(map_name, playfield)` - each obstacle's `name`,
   `cost`, `available` / `unlocked_by`, `position` and `frac` (screen
   fractions of its middle, where to click), `polygons`, `after`, and for ore
   `rounds` / `cash_reward`.
2. `mapgeom.removal_effect(model, name)` - `freed_land`, `freed_water` (cells
   gained) and `lost_land`, `lost_water` (cells ruined: Flooded Valley's dam
   floods land), plus `cells_freed`.
3. `placement.valid_spots(model, kind, ..., removed=[names])` - placement as
   if those obstacles were bought.

A buyer would: pick the obstacle whose freed cells add the most reach for
the next tower per dollar (`removal_effect` x `visible_cover`), check
`lost_land`/`lost_water` hold none of its towers, click `frac`, confirm the
price on the in-game panel, then place with `removed=[...]` for the rest of
the game. Live prices may differ from the scene's by difficulty, mode or
perks (`RemovableCostMultiplierModModel` exists) - read the panel.
`valid_spots(now_round=..., last_round=...)` and
`mapfit.strategy_fit(..., last_round=...)` likewise wait for the strategy
and planner to pass the round and the game's length.

## Needs checking in the game

- Sanctuary's platform offsets: the curves are applied as shifts relative
  to each platform's starting state, in the scene's x/z (sign of z and the
  turning centre not confirmed).
- Covered Garden's pane timing is taken from the guides (bottom-left open
  on round 1, clockwise every round), which matches the scene's cycle order
  (LowerLeft, UpperLeft, UpperRight, LowerRight) with roundsPerRotate 0 read
  as 1. A pane that shuts mid-click is not learned as a refused spot.
- Whether `OnMapLoadedWithActiveRegenRemovableTrigger` fires in a fresh
  game (treated as "may happen", which paints both Ancient Portal paths).
- Removal prices on Easy/Hard/Impoppable compared with the scene's.
- That raised platforms (Quarry, Castle Revenge) now take towers where the
  grid says, and that no spot on them is refused.

## Per-map table

<!-- table:start -->
| Map | Removable obstacles | Changes by itself | Only if the player acts | Bloons out of reach | Bot's note |
|---|---|---|---|---|---|
| #Ouch | 1 ($1,000) |  |  |  |  |
| Adora's Temple |  | paths alternate |  |  |  |
| Ancient Portal |  | areas appear, areas vanish, path opens | clickable objects, paid switch |  |  |
| Another Brick | 2 ($1,000) |  |  |  |  |
| Bazaar | 4 ($500) | paths alternate |  |  |  |
| Bloody Puddles | 3 ($500-1,000), 2 unlocked later | paths alternate | areas appear, areas vanish |  |  |
| Bloonarius Prime |  | path opens |  |  |  |
| Cargo | 2 ($500), 2 unlocked later | areas vanish, path opens |  |  | line of sight changes during the game: blockers count as always there; global-range towers (sniper, mortar, heli, ace, dartling) do not care |
| Castle Revenge |  | areas appear | areas vanish, paid switch | 38% of the track | 38% of the track cannot be hit (gates, tunnels): cover the open stretches |
| Chutes | 2 ($350) | paths alternate |  |  |  |
| Cornfield | 13 ($350-1,500) |  |  |  |  |
| Covered Garden |  | areas open/close in turn |  |  | some ground is closed off part of the time (towers already there stay, but none can be placed while it is closed): only ground that is always open is used |
| Cracked | 1 ($1,000) |  |  |  |  |
| Dark Castle | 4 ($1,000) |  |  | 63% of the track | 63% of the track cannot be hit (gates, tunnels): cover the open stretches |
| Dark Dungeons |  |  | clickable objects, paid map ability | 10% of the track |  |
| Dark Path | 8 ($250-1,000), 6 unlocked later |  | areas appear, areas vanish |  |  |
| Downstream | 2 ($350) |  |  |  |  |
| Enchanted Glade |  | paths alternate |  | 2% of the track |  |
| Encrypted | 4 ($250) |  | areas appear, areas vanish |  |  |
| Erosion |  | areas vanish, paths alternate |  |  | ground disappears during the game: only ground that lasts is used |
| Firing Range | 1 ($1,000) |  |  |  |  |
| Flooded Valley | 1 ($5,000), 1 unlocked later |  | areas appear, areas vanish, clickable objects |  |  |
| Geared |  | rotating ground (carries towers) |  |  | towers on moving ground are carried around: use it for global-range towers |
| Glacial Trail |  |  |  | 16% of the track | 16% of the track cannot be hit (gates, tunnels): cover the open stretches |
| Haunted | 2 ($500) |  |  |  |  |
| High Finance | 15 ($350-1,500) | paths alternate |  |  |  |
| Infernal |  | paths alternate |  |  |  |
| KartsNDarts | 2 ($500) |  |  | 24% of the track | 24% of the track cannot be hit (gates, tunnels): cover the open stretches |
| Last Resort | 1 ($1,000) | paths alternate | areas appear, areas vanish |  |  |
| Lotus Island |  |  | clickable objects |  |  |
| Luminous Cove |  | paths alternate | areas vanish, clickable objects |  |  |
| Mesa | 3 ($500) |  |  |  |  |
| Midnight Mansion | 2 ($250) | areas open/close in turn |  | 55% of the track | line of sight changes during the game: blockers count as always there; global-range towers (sniper, mortar, heli, ace, dartling) do not care; 55% of the track cannot be hit (gates, tunnels): cover the open stretches |
| Muddy Puddles |  | paths alternate |  |  |  |
| Mushroom Grotto | 5 ($250-400) |  | areas appear, areas vanish |  |  |
| One Two Tree |  | areas appear, areas vanish |  |  | line of sight changes during the game: blockers count as always there; global-range towers (sniper, mortar, heli, ace, dartling) do not care |
| Pat's Pond | 4 ($500) |  |  |  |  |
| Peninsula | 3 ($500) |  |  |  |  |
| Polyphemus | 9 ($500-1,000), 1 unlocked later | areas appear, areas vanish, towers switched off | areas vanish, paid switch |  | towers on part of the map get switched off: that part is not used |
| Quad | 4 ($1,500) |  |  | 59% of the track | 59% of the track cannot be hit (gates, tunnels): cover the open stretches |
| Quarry |  | areas vanish, path opens | clickable objects |  |  |
| Quiet Street | 7 ($250-500) |  | areas appear, areas vanish |  |  |
| Rake | 1 ($1,000) |  |  |  |  |
| Ravine |  | paths alternate | clickable objects |  |  |
| Sanctuary |  | moving platforms (carry towers) |  |  | towers on moving ground are carried around: use it for global-range towers |
| Scrapyard |  |  | clickable objects |  |  |
| Ship Capture | 1 ($1,000) |  | areas appear, areas vanish | 16% of the track | 16% of the track cannot be hit (gates, tunnels): cover the open stretches |
| Skates | 1 ($500) |  | areas appear, areas vanish, clickable objects |  |  |
| Skull Tweak | 1 ($0), 1 unlocked later | areas vanish | areas appear, areas vanish, clickable objects, path opens | 4% of the track |  |
| Spa Pits | 1 ($0), 1 unlocked later | areas vanish | areas appear, areas vanish, clickable objects, path opens | 2% of the track |  |
| Spice Islands | 1 ($1,000) |  |  |  |  |
| Spillway | 4 ($2,000) |  |  |  |  |
| Streambed | 1 ($1,000) |  |  |  |  |
| Sulfur Springs |  |  | clickable objects |  |  |
| Sunken Columns | 2 ($1,000) |  |  |  |  |
| Sunset Gulch |  | path opens |  |  |  |
| The Cabin | 1 ($500) |  | clickable objects |  |  |
| Three Mines 'Round | 6 ore to mine |  |  |  |  |
| Tinkerton |  |  | clickable objects |  |  |
| Tricky Tracks |  | seasonal obstacle | paid map ability |  |  |
| Water Park |  | paths alternate |  |  |  |
| Workshop |  | path opens | paid map ability |  |  |
| X Factor | 1 ($2,000) | paths alternate | areas vanish | 36% of the track | 36% of the track cannot be hit (gates, tunnels): cover the open stretches |
<!-- table:end -->
