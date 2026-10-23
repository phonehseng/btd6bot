# Intermediate maps, group B: map builds and what was learned

Maps: Lost Crevasse, Luminous Cove, Moon Landing, Polyphemus, Quarry, Quiet
Street, Rake, Spice Islands, Spring Spring, Streambed, Sulfur Springs, Water
Park. Written October 2026 for the medals the main account still lacked.

## How the builds were made and checked

1. **Map analysis from the game's own data.** Routes, scenarios and
   untouchable stretches from `btd6bot/dps_model.py` `Track`; areas, heights,
   sight blockers and removables from `data/map_geometry/<id>.json`
   (`btd6bot/mapgeom.py`) and `data/map_mechanics.json`; legal cells from
   `placement.valid_spots`; reach from `Track.zones` with line of sight.
2. **Community research.** bloonswiki / bloons.fandom (Strategy sections,
   read through search summaries: both wikis refused direct fetching this
   time), btd6index, YouTube guide descriptions and comments, a BloonsPlayer
   CHIMPS script. Almost every written build is a CHIMPS build; for the
   modes asked here (Easy ... Hard) the guides are videos without text, so
   the community input is the choice of towers and the kind of spot, not a
   round-by-round order. Each file names its sources.
3. **Order and spots.** `tools/optimize_builds.py`'s greedy optimizer, run
   from a scratch script (nothing written to `strategies/optimized/`),
   restricted to the towers the sources use, at a safety margin of 3.0
   (2.5-2.6 where noted), with three extra rules:
   * spots the live bot has seen the game refuse (`data/maps/<map>.npz`,
     the refused layer) are left out;
   * a damage tower's spot must reach at least 45% of the track the best
     legal spot reaches **on the executor's screen grid**
     (`Executor.MIN_REACH_SHARE`); below 25% the executor sells it
     (`sell_useless`), whatever the damage model says;
   * no spot under the top HUD (fy < 0.13, or fx > 0.68 and fy < 0.17):
     the optimizer puts map-wide towers on the worst cells, which were often
     the top edge (fy 0.078), where the bot has never placed a tower.
   Buccaneer Grape Shot crosspaths (0-x-x) were excluded: see the model
   gaps below.
4. **Validation of every file**, in the account's scenario (Fast Track +
   Double Cash, `optimize_builds.economy(mode, boosts)`):
   * `strategy.load_all()`: bot_ready True, `validate()` empty;
   * the plan replayed the way the executor buys (in order, each step as
     soon as the cash allows, like `optimize_builds.replay_plan`), and
     `dps_model.round_margin` on every round from the start round to the
     last: worst margin at least 2.0 (the numbers are in each file's header
     and below). Plan only, fill not counted - except in Deflation and where
     a file says "plan + fill" (see below);
   * `tools/simulate_threats.py simulate(strat, mode, map_name, scenario=...)`
     with the account's start round, cash and income: no gaps; and on the
     base economy as the tests run it: no gaps;
   * `strategy.coverage()` on a fully unlocked account: nothing missing;
   * every `at` legal in plan order (as `tests/test_map_hints_offline.py`
     checks), clear of the HUD and of refused cells;
   * `tests/test_map_hints_offline.py` and
     `tests/test_achievement_strats_offline.py` (results at the end).
5. **Easy family (Easy, Primary Only, Deflation)**: the test's threat
   simulation runs the base economy (no boosts; Deflation on $20,000) and
   requires the whole `plan` to be bought. So in those files `plan` is the
   core that the base economy affords, and what the account's Double Cash
   adds (Deflation: the second $20,000 of the $40,000) is `fill`. Where a
   file's margins count the fill, its header says "plan + fill".

Apopalypse was not built for any map: its rounds are random and come without
a break, so the damage model (one standard round at a time) cannot validate
a build for it.

## Model and executor gaps found (no code was changed)

1. **Heights and line of sight.** `MapModel.sight` and `MapSetup.sight` treat
   every sight blocker as blocking at any height. On Water Park the water
   slide itself is a blocker ("BlockingTrack", height 50) and its lane runs
   on top of it (heights 13-54), so the model says no aimed tower can ever
   hit the slide. Whether the game agrees is not known: the two Water Park
   losses (solo_tack, 2026-10-22 16:00 and 16:29) leaked on both odd and
   even rounds, and their logs do not say which lane leaked. Towers on the
   raised pink circles (LandLoop, height 60) and the big middle land
   (LandHut, 55) stand above the blocker and may well see the slide. A
   height-aware sight test (blocker height vs tower and bloon height),
   checked once in play, would open Water Park Primary Only and make the
   other Water Park builds cheaper.
2. **Raised land over low track (screen overlap).** Placement grids are
   built in screen space; a raised area whose screen image overlaps a low
   lane counts as track. Sulfur Springs' central island (height 51, inside
   the big loop: "the best real estate" per the wiki) is all blocked in the
   model, as are parts of other cliffs.
3. **The executor's reach grid ignores heights.** `Executor._reach` counts
   track cells near the tower on the screen grid. A cliff tower on Sulfur
   Springs (height 51, track at 0.5) reaches 100-240 units of lane in world
   space but almost nothing on the screen grid, so `sell_useless` would sell
   it. The builds here keep every finite-range damage tower at >= 45%.
4. **Quarry's MOAB track is not in the stock `Track`.** `PathMoab` starts
   inactive (`MapEventMoabTrack` opens it after round 39) and is skipped, so
   the stock model sends MOABs down the standard lane, including the top
   stretch they never use. The Quarry builds were checked with PathMoab
   added as a MOAB-only route (scratch helper `add_moab_route`).
5. **Buccaneer Grape Shot was overrated (fixed in `dps_model` since).**
   Before `_trigger_rates`, every buccaneer crosspath with a middle-path
   tier got its grape weapon at a readiness-check rate (100 shots a second
   in the profile): one 0-3-2 boat "held" Medium to round 60 in the model,
   and the optimizer picked exactly that. These builds never use the
   buccaneer middle path (it was excluded from the start), and every build
   with a buccaneer was re-checked after the fix: the margins did not
   change (see the table at the end).
6. **The refused layer is very wide on two maps.** On Spice Islands and
   Luminous Cove the live refused layer covers almost every land cell that
   fits a Heli Pilot, Monkey Ace, Super Monkey or Village (e.g. both sniper
   spots of `luminouscove_hard.yaml` are refused now). Many of these
   refusals came in long runs (ten in a row on Water Park, 16:04) that look
   like a held-tower problem rather than real map limits. A way to forget
   refusals made during such runs would give the builds their land back.
7. **Top HUD.** The optimizer's map-wide towers go to the "worst" cells,
   which are often at fy 0.078, under the lives/cash/round display. The bot
   has never placed a tower above fy 0.11. `MapSetup.spots` could skip the
   HUD band.
8. **Tests and new maps.** `test_map_strategies_load_valid_and_ready` first
   required every file in `strategies/maps/` to be listed in its map's
   `strategies` in `data/map_strategy_hints.json`, which has no entry for
   eleven of these maps; the test was relaxed during the day (listed builds
   must be under their own map). `data/map_strategy_hints.json` still has no
   hints for these maps, so the executor's hint-spot fallback knows nothing
   about them.
9. **Threat table vs map-wide builds.** `strategy.coverage` answers the
   R60 BFB, R63 rush and R80 ZOMG only with fixed tower tiers (sniper 4-x-x,
   tack 4-x-x, a Super Monkey, ...). Military builds whose snipers took the
   middle or bottom path have none of them, although the damage model rates
   those rounds safe. The files add the cheapest qualifying step (a sniper's
   top path, or a role-placed Super Monkey for the Hard rush) and say so.
10. **Map actions the bot cannot do.** Buying removables (Rake's rock,
    Streambed's skull, Quiet Street's cars and ice, Spice Islands' palm,
    Polyphemus' trees), reopening Polyphemus' eye (paid switch), Luminous
    Cove's cave doors. None of the builds needs them.
11. **The executor adds a $200 dart opener** in front of an Easy-family plan
    whose first tower is not a "cheap opener" (`Executor.CHEAP_OPENERS`:
    no desperado), even with Fast Track starting at round 10; in the threat
    simulation that dart and its surplus upgrades kept a plan from finishing.
    The Easy files here start with a cheap tower.

## Builds written

All in `strategies/maps/`. Worst margin = lowest `dps_model.round_margin`
over every round of the mode, replayed as the executor buys with the
account's Fast Track + Double Cash. "plan" = plan only; "p+f" = plan +
fill (Easy-family files, see above). All 27 files: `load_all()` bot_ready
True, `validate()` empty, no threat-simulation gaps (account and base
economy), `coverage()` complete, every `at` legal in order.

| file | modes | towers (core) | hero | worst margin |
|---|---|---|---|---|
| waterpark_easy | easy | sub, sniper, ace | Brickell | 2.74 R39 (plan) |
| waterpark_military | medium, military_only, reverse, hard | sniper, sub, buccaneer, ace, heli | Brickell | 2.62 / 2.62 / 3.47 / 3.47 (plan) |
| waterpark_deflation | deflation | ace, sniper, buccaneer, sub, tack | Brickell | 4.60 R51 (p+f) |
| lostcrevasse_military | medium, military_only, reverse | buccaneer, sub, sniper, ace, heli | Sauda | 4.81 / 4.81 / 4.27 (plan) |
| luminouscove_military | military_only, reverse | buccaneer, sub, sniper | Brickell | 3.87 / 3.87 (plan) |
| luminouscove_deflation | deflation | buccaneer, sub, druid, sniper, ninja | Brickell | 3.15 R56 (p+f) |
| moonlanding_military | medium, military_only, reverse | sniper, ace | Obyn | 3.22 / 3.22 / 3.55 (plan) |
| moonlanding_deflation | deflation | sniper, ace, druid | Obyn | 3.12 R54 (p+f) |
| polyphemus_easy | easy, primary_only | dart, desperado, tack, boomerang, bomb | Sauda | 2.65 / 2.65 R40 (plan) |
| polyphemus_military | medium, military_only, reverse, hard | buccaneer, sniper, ace | Brickell | 2.86 / 2.86 / 2.89 / 3.63 (plan) |
| polyphemus_deflation | deflation | bomb, sniper, sub, ace, boomerang | Sauda | 2.38 R58 (p+f) |
| quarry_military | medium, military_only, reverse | buccaneer, sub, ace, sniper | Etienne | 3.26 / 3.26 / 3.75 (plan) |
| quarry_deflation | deflation | bomb, ace, sniper, alchemist, sub, buccaneer | Etienne | 2.30 R58 (p+f) |
| quietstreet_easy | easy | dart, alchemist, sniper | Psi | 2.48 R34 (p+f) |
| quietstreet_military | medium, military_only, reverse | sniper, ace | Psi | 2.68 / 2.68 / 2.35 (plan) |
| quietstreet_deflation | deflation | bomb, sniper, village, alchemist | Psi | 2.28 R54 (p+f) |
| rake_military | medium, military_only, reverse, hard | buccaneer, sniper, heli, ace | Psi | 3.87 / 3.87 / 3.75 / 2.59 (plan) |
| rake_deflation | deflation | bomb, buccaneer, sniper, ace, druid, heli, spike | Psi | 3.83 R56 (p+f) |
| spiceislands_military | military_only, reverse | buccaneer, sub, sniper | Brickell | 4.13 / 4.46 (plan) |
| spiceislands_deflation | deflation | bomb, buccaneer, sub, sniper | Brickell | 7.18 R59 (p+f) |
| springspring_military | medium, military_only, reverse | buccaneer, sub, sniper, ace, heli | Etienne | 3.87 / 3.87 / 3.87 (plan) |
| springspring_deflation | deflation | bomb, buccaneer, sniper, sub, ace, heli, boomerang | Etienne | 2.18 R54 (p+f) |
| streambed_military | medium, military_only, reverse | buccaneer, sub, ace, sniper, heli | Sauda | 3.15 / 3.15 / 3.19 (plan) |
| streambed_deflation | deflation | bomb, buccaneer, sniper, sub, tack, druid, ace | Sauda | 2.99 R54 (p+f) |
| sulfursprings_easy | easy | sniper, desperado, alchemist, super | Quincy | 2.25 R37 (p+f) |
| sulfursprings_military | medium, military_only, reverse, hard | sniper, ace | Brickell | 4.91 / 4.91 / 4.86 / 3.40 (plan) |
| sulfursprings_deflation | deflation | bomb, sniper, ace, druid, alchemist | Quincy | 2.80 R58 (p+f) |

The buccaneer re-check after the `dps_model` fix (`_trigger_rates`): every
file with a buccaneer replayed to exactly the margins above (none uses the
middle path).

Every Medium/Hard file ends its plan with $20k-$110k unspent on the
account's economy; `fill` spends it on tier 5s (one per path and tower
type, as the game allows) where the account has them unlocked.

## Not written, and why

| map | mode | reason |
|---|---|---|
| all twelve | Apopalypse | random rounds without breaks: the damage model cannot validate it |
| Water Park | Primary Only | no primary tower can reach the slide in the model (sight blocker under the whole lane, model gap 1): every slide round is unpoppable |
| Luminous Cove | Primary Only | best optimizer result 0.76 (account cash; 0.43-0.56 on the other runs): the only land is the bottom strip, most of it in the live refused layer, and the lanes loop round water |
| Spice Islands | Primary Only | 2.00 at best, and only on spots the executor would sell (screen-grid reach under 25%); 0.72 with executor-safe spots: the islands are tiny and mostly refused |
| Quiet Street | Primary Only | 0.64-1.38: walls block sight near both entrances, darts leak the lead rounds and bombs miss camo |
| Sulfur Springs | Primary Only | 0.71 with executor-safe spots (1.22 without): the cliffs are 50 units above the lane (model gaps 2 and 3) |

Luminous Cove Medium/Hard is served by the existing `luminouscove_hard.yaml`
(not mine, not edited). Replayed the same way it rates medium 1.30 (R56)
and hard 0.19 (R78), and both of its sniper spots are now in the live
refused layer - worth a second look by its owner.

## Per map

### Lost Crevasse
- Data: two routes at once (Path1 565, Path2 509 hittable units; boss path
  unused); they share the long middle diagonal in opposite directions. The
  lake bottom right reaches both after the split; ice crystals block sight
  on the upper right.
- Sources: bloonswiki Lost_Crevasse; OneEyedDeacon CHIMPS v53.2 (sniper next
  to a crystal); CHIMPS comments (two aces and a buccaneer).
- Build: buccaneers and a sub in the lake, two snipers, two Bomber Aces over
  the diagonal, a Heli Pilot; Sauda on the junction below the diagonal.

### Luminous Cove
- Data: lanes alternate by round; both loop round the heart pond, which
  reaches ~45% of each lane from the water. Land only at the bottom, mostly
  refused live. The cave doors are a click event (not used).
- Sources: bloonswiki Luminous_Cove (water strategies, centre water best);
  BlueCliff Hard (Sub 2-0-4); metaldevil Brickell CHIMPS (Destroyer ->
  Carrier).
- Builds: military (two buccaneers and a sub in the heart pond, snipers on
  the bottom land, a third sniper 4-1-0 for the threat table's BFB entry);
  deflation (the same core plus a druid and a ninja).

### Moon Landing
- Data: one 1,242-unit lane through three walled craters; no water; the
  crater walls block sight.
- Sources: bloonswiki Moon_Landing; BeatbloonsBob CHIMPS (snipers, heli);
  OneEyedDeacon Flying Fortress CHIMPS.
- Builds: snipers (one on the Elite Defender path) and Bomber/Ground Zero
  aces; deflation adds a Druid of the Jungle (map-wide vines in the export).

### Polyphemus
- Data: two lanes share the C-shaped road in opposite directions; the eye
  closes every 10 rounds from 6 and switches its towers off (the model's
  grid leaves it out). Nine removable tree groups ($500-$1,000), unused.
- Sources: bloonswiki Polyphemus; btd6index; ZoozieBloons CHIMPS.
- Builds: Easy/Primary Only with darts, desperados, a tack, a boomerang and a
  bomb on the land inside the C (all at >= 81% executor reach); military
  with buccaneers in the sea at both ends, snipers and aces; deflation with
  bombs, snipers, a sub, aces and a boomerang.

### Quarry
- Data: one 1,336-unit lane; MOABs take PathMoab from round 40 (model gap
  4, checked with the extra route); a river along the bottom takes boats.
- Sources: bloonswiki Quarry; bloons.fandom Quarry; BloonsPlayer CHIMPS
  script.
- Builds: military (two buccaneers and two subs in the bottom river, two
  aces, snipers); deflation (bombs, ace, sniper, alchemist, sub, buccaneer).

### Quiet Street
- Data: non-MOABs enter top and bottom and leave by the other side; MOABs
  use the thick road from bottom to top (MoabOnlySplitter); no water without
  the $500 ice; cars and walls block sight.
- Sources: bloonswiki Quiet_Street; bloons.fandom Quiet_Street; Sauda /
  Carrier Flagship / BEZ CHIMPS video.
- Builds: Easy (darts by the entrances, snipers, an alchemist); military
  (snipers and aces, Tsar Bomba in fill); deflation (bombs, snipers, and a
  Radar Scanner village that gives the bombs camo - the camo pinks of R53
  were the weak point without it).

### Rake
- Data: two lanes at once crossing in the middle, over 40% of each off
  screen; a $1,000 rock (unused); the centre pool reaches both lanes.
- Sources: bloonswiki Rake; bloons.fandom Rake; Sky Shredder guide.
- Builds: military (two buccaneers in the pool, snipers, two helis, aces);
  deflation (bombs, buccaneer, sniper, ace, druid, heli, spike factory).

### Spice Islands
- Data: one 1,044-unit lane; the most water; five tiny islands, mostly in
  the live refused layer; palm trees block sight ($1,000, unused).
- Sources: bloonswiki Spice_Islands; bloons.fandom Spice_Islands/Strategies;
  SnartFarts CHIMPS.
- Builds: military (two buccaneers and a sub beside the lane, snipers);
  deflation (bombs on the middle island, buccaneers, a sub, an Elite Sniper
  in fill; the threat table's BFB entry, a MOAB Assassin, is the last fill
  step because the account's $40,000 runs out before it - the model rates
  R60 safe without it).

### Spring Spring
- Data: two lanes at once, same entrance and exit, round the big island;
  only ~55% of each lane is on screen.
- Sources: bloonswiki Spring_Spring; bloons.fandom Spring_Spring/Strategies;
  Psi Sub Commander black border.
- Builds: military (buccaneers and a sub at the exit water, snipers, aces, a
  heli); deflation (adds bombs and a boomerang).

### Streambed
- Data: one 1,202-unit lane round a pond; a $1,000 dino skull blocks sight
  (unused).
- Sources: bloonswiki Streambed; bloons.fandom Streambed/Strategies; pirate
  black border.
- Builds: military (buccaneers and a sub in the pond, aces, snipers, a
  heli); deflation (bombs, buccaneer, sniper, sub, tack, druid, ace).

### Sulfur Springs
- Data: one 1,071-unit lane in the pit; all land on cliffs 50 units higher
  (model gaps 2 and 3); the central island is blocked in the model.
- Sources: bloonswiki Sulfur_Springs; bloons.fandom Sulfur_Springs; Hard
  Standard guide.
- Builds: Easy (snipers, desperados, an alchemist, a Super Monkey in fill);
  military (snipers on every path, Bomber Aces placed by hand on HUD-free
  cliff spots - the optimizer's spot ranking misses that an ace's circle is
  wider than its dart range); deflation (bombs, snipers, aces, a druid).

### Water Park
- Data: lanes alternate every round; the slide is a sight blocker (model gap
  1); water only reaches the lazy river.
- Sources: bloonswiki Water_Park; OneEyedDeacon and Tadomika CHIMPS; Mr.
  Moe's per-mode runs; ixbert Hard.
- Builds: Easy, military and deflation, all with map-wide snipers and aces
  for the slide and boats for the river. The top-left pink circle inside the
  slide loop is in the live refused layer, so no build relies on it.

## Test results (2026-10-22)

- My 27 files through the four map-strategy tests of
  `tests/test_map_hints_offline.py`, restricted to them: all pass.
- `python tests/test_map_hints_offline.py` on the whole folder: 7 of 8 pass;
  `test_map_strategies_load_valid_and_ready` fails on
  `offthecoast_deflation` ("marked bot_ready: false in YAML"), another
  group's file.
- `python tests/test_achievement_strats_offline.py`: 15 of 16 pass;
  `test_all_achievement_yamls_load` fails on the same `offthecoast_*`
  files (bot_ready false), not on these.
