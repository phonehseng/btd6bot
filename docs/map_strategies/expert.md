# Expert maps: map-specific builds

Builds in `strategies/maps/` for the Expert maps whose medals the main account
still lacks, written October 2026 (game v57/v58). Per map: what the map data
shows, the sources, the builds written with their worst modelled margin, and
what was skipped and why. The general research for these maps (Hard and
CHIMPS guides, removable obstacles, BTD6 Index records) is in
`docs/map_strategies.md`, section "Expert maps".

## How the builds were made and checked

1. **Map data.** Routes, scenarios and hittable stretches from `btd6bot/dps_model.py`
   `Track` (built on `data/map_geometry`), mechanics from `data/map_mechanics.json`,
   legal spots from `placement.valid_spots` on a `MapModel` filled by `mapgeom.apply`,
   sight from `MapModel.sight`. Where the model's routes are wrong (see the gaps
   below) the checks used corrected routes, worked out from the map's own paths and
   splitters.
2. **Towers.** The tower kinds come from the guides (sources per map below and in
   each file's header), filtered by the mode (`MODE_TOWER_FILTER`) and the bot's
   rules (no mortar or dartling; desperado, mermonkey and skywarden allowed since
   their hotkeys were verified; no snipers on the maps whose walls block sight).
   One finding drove many builds: **Druid of the Jungle (druid 0-3-0)** - the game
   data gives its vines map-wide reach and they destroy a whole non-MOAB bloon per
   grab; the CHIMPS guides for Workshop, Ravine and Dark Castle use it early. On the
   maps whose lanes take turns (Muddy and Bloody Puddles) or split (Glacial Trail's
   freezes, Workshop's fast belt) it covers every lane from one spot. The vines do
   not see camo (a radar village or a camo tower is added) and do not grab MOABs.
3. **Spots and order.** Two ways, both checked the same way afterwards:
   - the greedy planner of `tools/optimize_builds.py` run with only those kinds and
     the account's boosts, plus scratch changes: candidate spots for every route
     (not only the 8 that cover most track in total), leaks summed over a map's
     alternative scenarios (else a tower that covers one of two alternating lanes
     never looks useful), village always a candidate, 5 rounds of lookahead, and on
     Glacial Trail the freezes; then repairs that add the purchase raising the
     weakest round most per dollar (per scenario on alternating maps);
   - by hand from the guides (the #Ouch pond build, the druid builds), with the
     same tools to find spots and to fix single rounds.
4. **Easy family.** The test `test_map_strategies_pass_the_threat_simulation`
   wants the whole plan bought on the base economy (no Double Cash, $650 at
   round 1; $20,000 in Deflation). Plans were cut at about $12,000 (Deflation:
   $18,000) and the rest moved to `fill`, which the executor buys after the plan.
   Large single upgrades sit in `fill`: in the simulation the executor's surplus
   spending (idle cash over $800) never lets cash pile up for them. A plan opens
   with a cheap tower (no executor opener dart is added).
5. **Checks per file** (all must pass before a file is kept):
   - `strategy.load_all()` loads it with `bot_ready` True; `validate()` is empty;
   - every round's `dps_model.round_margin` (sight function passed) is at least 2.0
     when the plan and then `fill` are bought in order as cash allows on the
     account's economy (`optimize_builds.economy(mode, boosts)`: Easy round 10 with
     $3,832, Medium round 15 with $6,057, Deflation round 31 with $40,000);
   - `tools/simulate_threats.py simulate()` reports no gaps, on the base economy
     and on the account's (`scenario=`);
   - every `at` is legal in plan order (as `tests/test_map_hints_offline.py`) and
     off the HUD;
   - `strategy.usable()` and `strategy.coverage()` pass on a fully unlocked account;
     threats the final build did not cover got an `answers` entry;
   - `tests/test_map_hints_offline.py` and `tests/test_achievement_strats_offline.py`
     were run (results at the end of this page).
6. **Corrections used only in the checks** (scratch code, nothing in the repo was
   changed): corrected routes for Dark Castle, Sanctuary, Workshop and Ravine;
   Workshop bloons 1.5x faster (conveyor); Glacial Trail towers frozen on rounds
   r+8, r+9, r+10, r+18, ... after the round r they were bought for (ice monkeys
   excepted; villages counted as frozen too, although the game keeps their buffs);
   Sub 2-x-x (Advanced Intel) reaching only track inside its own range or another
   non-global tower's range, not the whole map.
7. **Glacial Trail timing.** Steps carry `round:` (an existing step key: the
   executor waits for that round) so that towers are bought in groups three rounds
   apart and no round has two groups frozen.

## Model and bot gaps found

- **Reverse-mode splitters followed as forward routes** (`dps_model.map_routes`).
  Dark Castle, Sanctuary and Workshop name splitters after a path for both
  directions; the route walk follows the Reverse ones too, so routes run
  entrance -> exit -> back to another entrance (Dark Castle: `Path1+PathMerge2+
  PathMerge1+Path2`, 1,343 units) or stop after two short pieces (Workshop:
  100 and 141 units instead of a 440-unit belt). Ravine's forks are merged into
  one route (`Path2-split2+Path2+Path2-split1`) with three identical scenarios,
  and Path1's lanes are missing. The repo's own `strategies/optimized` builds
  for these maps were rated on those routes. Suggested fix: follow a splitter
  named after X only to paths that start within JOIN_DISTANCE of X's end, and
  treat AlternateRoundMultiPathSplitter groups as scenarios of several routes.
- **Advanced Intel exported as map-wide.** `attacks.json` marks Sub 2-x-x
  `global`; in the game it reaches only bloons inside some other tower's range.
  The model therefore overrates subs on maps with few other towers.
- **Optimizer spots on multi-lane maps.** `MapSetup.spots` keeps the 8 spots
  with the most track in total and `free_spot` returns only the first free one,
  so on Dark Dungeons, Bloody Puddles, Muddy Puddles and Infernal whole lanes got
  no tower (the optimized builds there rate 0.06: some lane leaks everything).
- **Workshop:** the conveyor's +50% bloon speed is not modelled; the MOAB ramp
  is a hidden path.
- **Glacial Trail:** the 2-rounds-in-10 freeze is not modelled by `dps_model`
  or the optimizer. The executor should also not click a frozen tower (the
  upgrade fails) and should spread placements over rounds.
- **Psi** has range None in `towers.HEROES` (reach 0 for spot picking, although
  Psi is map-wide); the Muddy Puddles builds place Psi by hand.
- **Simulation surplus.** In `simulate_threats` the executor's `surplus()`
  upgrades the opener dart (it has no planned cap) and places extra copies of
  the main tower whenever idle cash passes $800, so an expensive plan step can
  wait forever on the base economy. Plans here open with a cheap tower (no
  opener) and keep large upgrades in `fill`.
- **Exact spots under the HUD.** The executor's role-based picking keeps off the
  top ~8% of the play field and the UI overlays (`maplearn.score_spots`), but an
  `at` spot is clicked as given, and `placement.valid_spots` allows spots under the
  lives/cash HUD, the round counter and the ability buttons; the optimizer puts
  map-wide towers there on purpose (lowest-scoring spots). The builds here keep
  every `at` out of those areas.
- **Buccaneer model fix (during this work).** `dps_model` counted the Grape Shot
  and Cannon secondaries at 20 shots a second until `_trigger_rates` was added.
  Every buccaneer build was re-checked after the fix: `ouch_easy` was reworked
  (hero bought later; worst margin 2.40) and `ouch_deflation` was rebuilt from
  scratch (the old 3-buccaneer plan fell to 1.65).
- **Sniper sight fix (during this work).** Snipers are now held to line of sight
  in `dps_model` (`MAP_WIDE_NEEDS_SIGHT`). Every published build was re-checked
  with the sight function passed (as `replay_plan` does): all stayed above 2.0
  (`trickytracks_deflation` fell from 2.18 to 2.07). On maps whose walls block
  sight (Dark Castle, Dark Dungeons, Glacial Trail, Ravine, Workshop) the builds
  use no snipers at all, as the guides advise; Bloody Puddles' snipers stand on the
  top edge, clear of the jeep.
- **Bot capabilities missing** (described, not built):
  - buying removable obstacles: Dark Castle trees ($1,000 each: longer usable
    lanes), Quad trusses ($1,500 each: bloons immune and sight blocked under
    them), Bloody Puddles jeep + chinook ($1,000 + $500: sight and space);
  - map gizmos: Workshop Reverse Motor (cancels the +50% belt speed for 30 s,
    first use free) and Track Extensions, Tricky Tracks train, Ravine sword,
    Dark Dungeons torch traps;
  - Apopalypse: its rounds are random and continuous; `data/game_data/round_sets.json`
    has only the standard and ABR sets, so no Apopalypse build can be checked.

## Summary

| Map | File | Modes | Worst margin (round) | Hero |
|---|---|---|---|---|
| #Ouch | `strategies/maps/ouch_deflation.yaml` | deflation | deflation 2.16 (R54) | quincy |
| #Ouch | `strategies/maps/ouch_easy.yaml` | easy | easy 2.40 (R14) | admiral_brickell |
| #Ouch | `strategies/maps/ouch_medium.yaml` | medium, military_only | medium 2.00 (R54); military_only 2.00 (R54) | quincy |
| #Ouch | `strategies/maps/ouch_primary_only.yaml` | primary_only | primary_only 2.11 (R40) | quincy |
| #Ouch | `strategies/maps/ouch_reverse.yaml` | reverse | reverse 2.13 (R54) | quincy |
| Bloody Puddles | `strategies/maps/bloodypuddles_easy.yaml` | easy | easy 2.99 (R40) | quincy |
| Bloody Puddles | `strategies/maps/bloodypuddles_medium.yaml` | medium, reverse | medium 2.83 (R59); reverse 2.18 (R59) | quincy |
| Bloody Puddles | `strategies/maps/bloodypuddles_military_only.yaml` | military_only | military_only 2.09 (R43) | quincy |
| Dark Castle | `strategies/maps/darkcastle_deflation.yaml` | deflation | deflation 2.40 (R51) | obyn |
| Dark Castle | `strategies/maps/darkcastle_easy.yaml` | easy | easy 2.20 (R37) | obyn |
| Dark Castle | `strategies/maps/darkcastle_medium.yaml` | medium | medium 2.02 (R59) | obyn |
| Dark Castle | `strategies/maps/darkcastle_military_only.yaml` | military_only | military_only 2.16 (R34) | obyn |
| Dark Castle | `strategies/maps/darkcastle_reverse.yaml` | reverse | reverse 2.02 (R59) | obyn |
| Dark Dungeons | `strategies/maps/darkdungeons_easy.yaml` | easy | easy 2.38 (R40) | sauda |
| Dark Dungeons | `strategies/maps/darkdungeons_medium.yaml` | medium, reverse | medium 2.02 (R54); reverse 2.02 (R54) | sauda |
| Flooded Valley | `strategies/maps/floodedvalley_deflation.yaml` | deflation | deflation 3.79 (R54) | admiral_brickell |
| Flooded Valley | `strategies/maps/floodedvalley_easy.yaml` | easy | easy 2.33 (R39) | admiral_brickell |
| Flooded Valley | `strategies/maps/floodedvalley_medium.yaml` | medium, military_only, reverse | medium 2.33 (R15); military_only 2.33 (R15); reverse 2.25 (R55) | admiral_brickell |
| Glacial Trail | `strategies/maps/glacialtrail_easy.yaml` | easy | easy 2.62 (R40) | dan_dmonke |
| Infernal | `strategies/maps/infernal_deflation.yaml` | deflation | deflation 4.32 (R54) | quincy |
| Infernal | `strategies/maps/infernal_easy.yaml` | easy | easy 2.23 (R10) | quincy |
| Infernal | `strategies/maps/infernal_medium.yaml` | medium, military_only, reverse | medium 2.80 (R15); military_only 2.80 (R15); reverse 3.44 (R60) | quincy |
| Muddy Puddles | `strategies/maps/muddypuddles_deflation.yaml` | deflation | deflation 2.74 (R59) | psi |
| Muddy Puddles | `strategies/maps/muddypuddles_easy.yaml` | easy | easy 4.65 (R37) | psi |
| Muddy Puddles | `strategies/maps/muddypuddles_medium.yaml` | medium, reverse | medium 4.18 (R15); reverse 3.29 (R56) | psi |
| Muddy Puddles | `strategies/maps/muddypuddles_military_only.yaml` | military_only | military_only 2.25 (R58) | psi |
| Quad | `strategies/maps/quad_deflation.yaml` | deflation | deflation 2.00 (R54) | quincy |
| Quad | `strategies/maps/quad_easy.yaml` | easy | easy 2.23 (R34) | quincy |
| Quad | `strategies/maps/quad_medium.yaml` | medium | medium 2.18 (R58) | quincy |
| Quad | `strategies/maps/quad_military_only.yaml` | military_only | military_only 2.00 (R15) | quincy |
| Quad | `strategies/maps/quad_primary_only.yaml` | primary_only | primary_only 2.25 (R34) | quincy |
| Quad | `strategies/maps/quad_reverse.yaml` | reverse | reverse 2.38 (R40) | quincy |
| Ravine | `strategies/maps/ravine_deflation.yaml` | deflation | deflation 2.16 (R58) | etienne |
| Ravine | `strategies/maps/ravine_medium.yaml` | medium, reverse | medium 2.51 (R58); reverse 2.54 (R58) | etienne |
| Sanctuary | `strategies/maps/sanctuary_medium.yaml` | medium, reverse | medium 2.40 (R59); reverse 2.40 (R49) | quincy |
| Sanctuary | `strategies/maps/sanctuary_military_only.yaml` | military_only | military_only 2.48 (R49) | obyn |
| Tricky Tracks | `strategies/maps/trickytracks_deflation.yaml` | deflation | deflation 2.07 (R54) | etienne |
| Tricky Tracks | `strategies/maps/trickytracks_easy.yaml` | easy | easy 2.11 (R40) | etienne |
| Tricky Tracks | `strategies/maps/trickytracks_medium.yaml` | medium, reverse | medium 2.28 (R59); reverse 2.11 (R54) | etienne |
| Tricky Tracks | `strategies/maps/trickytracks_military_only.yaml` | military_only | military_only 2.13 (R54) | etienne |
| Tricky Tracks | `strategies/maps/trickytracks_primary_only.yaml` | primary_only | primary_only 2.09 (R39) | etienne |
| Workshop | `strategies/maps/workshop_easy.yaml` | easy | easy 2.59 (R40) | sauda |
| Workshop | `strategies/maps/workshop_reverse.yaml` | reverse | reverse 2.18 (R58) | sauda |

Margin 2.0 means every round still pops with every tower at half its modelled
strength. All margins are on the account's economy (Double Cash + Fast Track).

## #Ouch

**Mechanics (map data).** Four very short lanes are all active every round (two vertical, two horizontal; map data: 4 routes of 209-310 hittable units, one scenario). The only water is the central pond, and it touches all four lanes: a buccaneer there covers ~350 units of track (a third of every lane), a land tower in a corner covers two lanes. No sight blockers. The pond can be drained for $1,000 (never bought here: the bot does not click map objects).

Model: 4 routes (Path1-Path4) in one scenario, hittable 209/310/209/309 units; land 80%, water 4%
(the pond), no sight blockers; one removable (the pond's water, $1,000).

**Sources.**

- BlueCliff, #Ouch Hard No MK (ft. Quincy): subs in the pond, sniper, then Pirate Lord (https://www.youtube.com/watch?v=Kxojxz7wJlE)
- CurlyFrys, #OUCH Hard Standard Easy Tutorial: Sauda + subs + Pirate Lord (https://www.youtube.com/watch?v=UYXG9xnWkX0)
- bloonswiki #Ouch / fandom Ouch: the pond holds 9 buccaneers or 13 subs and reaches all four lanes (https://www.bloonswiki.com/Ouch, https://bloons.fandom.com/wiki/Ouch)

**Builds written.**

- `ouch_deflation.yaml` (deflation; hero quincy): 7 buccaneers (0-3-2, 0-3-1, 2-0-1); 5 snipers (1-2-0); 3 bombs (0-2-4, 0-1-2, 0-0-2); 1 boomerang (0-0-0).
  Worst margin: deflation 2.16 at R54. Plan bought by the base-economy simulation: deflation 24/24.
- `ouch_easy.yaml` (easy; hero admiral_brickell): 2 subs (2-0-4); 1 buccaneer (3-2-0); 2 snipers (2-2-0, 1-2-0).
  Worst margin: easy 2.40 at R14. Plan bought by the base-economy simulation: easy 17/17.
- `ouch_medium.yaml` (medium, military_only; hero quincy): 7 buccaneers (2-3-0, 2-0-2, 1-3-0, 2-2-0); 8 snipers (2-2-0, 1-2-0); 3 helis (3-0-2); 4 aces (1-3-0, 0-3-0).
  Worst margin: medium 2.00 at R54, military_only 2.00 at R54. Plan bought by the base-economy simulation: medium 61/65, military_only 55/64.
- `ouch_primary_only.yaml` (primary_only; hero quincy): 17 darts (0-2-3, 0-1-1, 0-0-1, 0-1-0); 6 desperados (0-1-0, 0-0-0); 6 boomerangs (0-2-3, 0-2-2, 0-0-1); 3 bombs (0-2-3, 0-2-2, 0-1-2); 1 tack (0-0-0).
  Worst margin: primary_only 2.11 at R40. Plan bought by the base-economy simulation: primary_only 57/57.
- `ouch_reverse.yaml` (reverse; hero quincy): 7 buccaneers (2-3-0, 2-2-0, 2-0-2, 1-3-0); 14 snipers (2-2-0, 1-2-0); 1 druid (0-3-0); 3 helis (3-0-2); 4 aces (1-3-0, 0-3-0).
  Worst margin: reverse 2.13 at R54. Plan bought by the base-economy simulation: reverse 68/79.

**Not written.**

- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Bloody Puddles

**Mechanics (map data).** Five short vertical lanes; every round two of them spawn (the pair changes each round: AlternateRoundMultiPathSplitter in the map data). The model plays each lane alone with the whole round, which is harder than the real pairs. Small ponds between the lanes; the crashed jeep blocks sight and space until bought ($1,000 + $500, never bought here).

Model: 6 routes, each its own scenario (the AlternateRoundMultiPathSplitter pairs are
played one lane at a time with the whole round: harder than the real pairs, so the
checks are on the safe side); 4% of the sight lines blocked (the jeep). Removables: jeep
($1,000), helicopter and jeep wreck ($500 each).

**Sources.**

- BlueCliff, Bloody Puddles Hard No MK (ft. Quincy): Advanced-Intel subs in the ponds, snipers (https://www.youtube.com/watch?v=7LdEUBMskzk)
- bloonswiki Bloody_Puddles: Airburst subs early, desperados at R6, snipers see every lane (https://www.bloonswiki.com/Bloody_Puddles)
- fandom Bloody_Puddles/Strategies: spawn pairs repeat every 4 rounds (https://bloons.fandom.com/wiki/Bloody_Puddles/Strategies)

**Builds written.**

- `bloodypuddles_easy.yaml` (easy; hero quincy): 3 druids (1-3-0); 2 snipers (3-2-0, 2-2-0).
  Worst margin: easy 2.99 at R40. Plan bought by the base-economy simulation: easy 17/17.
- `bloodypuddles_medium.yaml` (medium, reverse; hero quincy): 7 druids (2-3-0, 0-3-1, 1-3-0); 7 snipers (2-5-0, 0-3-2, 2-2-0, 0-2-2).
  Worst margin: medium 2.83 at R59, reverse 2.18 at R59. Plan bought by the base-economy simulation: medium 31/39, reverse 31/39.
- `bloodypuddles_military_only.yaml` (military_only; hero quincy): 14 snipers (2-2-0, 0-2-2, 1-2-0, 0-1-0); 10 buccaneers (2-0-2, 2-0-1); 13 aces (2-3-0, 1-3-0, 2-1-0, 0-1-0); 5 helis (3-0-2, 1-0-2); 1 sub (2-1-0).
  Worst margin: military_only 2.09 at R43. Plan bought by the base-economy simulation: military_only 72/107.

**Not written.**

- primary_only: not written: best reached 0.06 (rounds 10-38). The model plays each of the five lanes alone with the whole round, and primary towers reach one or two lanes; the Druid of the Jungle that carries the other Bloody Puddles builds is a magic tower.
- deflation: not written: best reached 0.77 at round 59 (druids under a radar village, Maim MOAB snipers, and the optimizer's own mix). Every MOAB-class round is checked on one lane at a time, and the $40,000 does not buy enough for rounds 54-60 that way.
- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Dark Castle

**Mechanics (map data).** Four entrances on the left run under tree packs (bloons immune there) and merge into one stretch through the castle door to the exit. The model's own routes for this map follow the Reverse-mode splitters; these builds were checked on the corrected forward routes (Path1/Path4 -> PathMerge2, Path2/Path3 -> PathMerge1 -> PathMerge2). Castle walls block a third of the map's sight lines. The trees can be bought ($1,000 each; not done here).

Model (corrected routes): 4 routes of ~205 hittable units (the tree packs and the castle
door are invulnerable stretches); a third of the sight lines blocked; four tree packs
removable ($1,000 each).

**Sources.**

- BlueCliff, Dark Castle Hard No MK (ft. Obyn): ninja 4-0-2 + sub + alchemist at the merge (https://www.youtube.com/watch?v=QB0bitxGZn0)
- Yoboi3li, Dark Castle CHIMPS (no abilities, no micro): druids, Obyn (https://www.youtube.com/watch?v=YUR_SIL0trE)
- bloonswiki Dark_Castle_(BTD6): the lanes converge near the end, spike factories by the castle are useful (https://www.bloonswiki.com/Dark_Castle_(BTD6))

**Builds written.**

- `darkcastle_deflation.yaml` (deflation; hero obyn): 6 bombs (0-3-2, 0-2-2); 1 sub (4-0-2); 1 druid (0-3-1); 4 ninjas (0-0-0); 2 darts (0-2-4); 2 spikes (4-0-1, 2-0-1).
  Worst margin: deflation 2.40 at R51. Plan bought by the base-economy simulation: deflation 22/22.
- `darkcastle_easy.yaml` (easy; hero obyn): 20 darts (0-2-3, 0-1-1, 0-0-1, 0-1-0); 2 druids (0-3-0, 1-1-0); 1 ninja (0-0-0); 2 boomerangs (0-3-2, 0-2-2); 4 subs (2-2-0, 2-0-1, 0-0-0).
  Worst margin: easy 2.20 at R37. Plan bought by the base-economy simulation: easy 50/50.
- `darkcastle_medium.yaml` (medium; hero obyn): 3 druids (2-3-0, 0-4-1, 1-3-0); 12 ninjas (3-2-0, 0-2-3, 2-0-3, 1-0-3); 5 darts (0-2-4, 1-0-4, 0-3-2, 0-0-3); 2 subs (0-3-2, 2-0-3); 1 bomb (0-2-2); 2 spikes (4-2-0, 4-0-1); 1 village (4-0-0).
  Worst margin: medium 2.02 at R59. Plan bought by the base-economy simulation: medium 61/79.
- `darkcastle_military_only.yaml` (military_only; hero obyn): 6 buccaneers (4-0-2, 2-3-0, 3-0-2, 3-0-1); 1 heli (3-0-2); 3 aces (2-3-0, 1-3-0).
  Worst margin: military_only 2.16 at R34. Plan bought by the base-economy simulation: military_only 32/33.
- `darkcastle_reverse.yaml` (reverse; hero obyn): 3 druids (2-3-0, 0-4-1, 1-3-0); 12 ninjas (3-2-0, 0-2-3, 2-0-3, 1-0-3); 5 darts (0-2-4, 1-0-4, 0-3-2, 0-0-3); 2 subs (2-0-3, 0-3-2); 2 bombs (0-2-2, 0-3-0); 4 spikes (4-2-0, 4-0-1, 2-0-2); 1 village (4-0-0).
  Worst margin: reverse 2.02 at R59. Plan bought by the base-economy simulation: reverse 61/85.

**Not written.**

- primary_only: not written: best reached 1.09 at round 34 after repairs (darts, boomerangs, bombs and tacks at the merge); the 160-yellow round 34 and the white/black/lead rounds 35-40 stay short - the Druid of the Jungle that fixed Easy is not a primary tower.
- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Dark Dungeons

**Mechanics (map data).** Six walled rooms; three bloon lanes run at once (left, middle, right) and MOAB-class take their own two lanes (MoabOnlySplitter). Walls block more than a third of all sight lines, so each lane needs towers in its own room; the middle lane sits lower. A small sludge pool is the only water.

Model: 5 routes in one scenario (3 bloon lanes, 2 MOAB lanes), 10% of the track hidden
(stairs); 37% of the sight lines blocked; torches and a $30,000 statue (map abilities).

**Sources.**

- ApexZ, Dark Dungeons CHIMPS Full Auto Start: darts per room, spikes, tacks (https://www.youtube.com/watch?v=wqGrbHhDv3U)
- OneEyedDeacon, CLASSIC and EASY Dark Dungeons w/ Sauda (https://www.youtube.com/watch?v=zVL8Gs1MyLw)
- bloonswiki Dark_Dungeons (https://www.bloonswiki.com/Dark_Dungeons)

**Builds written.**

- `darkdungeons_easy.yaml` (easy; hero sauda): 5 tacks (2-3-0, 3-0-2, 2-0-2, 1-2-0); 11 darts (0-2-3, 0-1-2, 1-0-2, 1-0-1); 6 boomerangs (0-2-3, 0-3-2, 0-2-2, 0-2-1); 2 spikes (0-0-0); 2 bombs (0-2-2, 0-0-0); 1 druid (0-3-1).
  Worst margin: easy 2.38 at R40. Plan bought by the base-economy simulation: easy 49/49.
- `darkdungeons_medium.yaml` (medium, reverse; hero sauda): 2 tacks (3-0-2); 5 darts (0-2-4, 4-0-2, 1-0-4, 0-3-2); 2 druids (2-3-0, 0-3-1); 10 ninjas (4-0-2, 1-0-4, 3-2-0, 2-0-3); 5 boomerangs (0-2-2, 0-1-2, 0-2-1, 0-0-2); 3 bombs (0-2-2, 0-0-2); 1 spike (2-0-4); 3 ices (2-0-1, 2-0-0, 0-0-0).
  Worst margin: medium 2.02 at R54, reverse 2.02 at R54. Plan bought by the base-economy simulation: medium 82/102, reverse 82/102.

**Not written.**

- primary_only: not written: best reached 0.34 at round 37 after repairs (camo darts were added for rounds 24/28; the camo and white rounds 33-37 stay short in three walled rooms at once).
- deflation: not written: best reached 0.06 at round 59 (camo leads; a bomb build without radar). Not redone with a radar village for lack of time.
- military_only: not written: best reached 1.65 at round 43 (aces, helis and a sludge-pool sub; snipers left out because walls block their sight).
- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Flooded Valley

**Mechanics (map data).** Two lanes run on top of the dam in opposite directions at the same time. The dam blocks sight from the big left land, so land towers there see nothing; the water on the right side touches the track at the dam's bends. Water towers (subs, buccaneers, mermonkeys) carry every guide.

Model: 2 routes in one scenario, 231 hittable units each; 14% of the sight lines
blocked (the dam); water 39% of the map; the $5,000 dam plate floods the left land.

**Sources.**

- G-Horizon, Flooded Valley CHIMPS Easy Guide: two mermonkeys, buccaneer (https://www.youtube.com/watch?v=68Jbc9m1zts)
- Tiggy Gaming, Flooded Valley: buccaneer start, sub, Brickell, Carrier Flagship (https://www.youtube.com/watch?v=5x1IfnoZy2c)
- bloonswiki Flooded_Valley (https://www.bloonswiki.com/Flooded_Valley)

**Builds written.**

- `floodedvalley_deflation.yaml` (deflation; hero admiral_brickell): 2 mermonkeys (3-0-1); 2 buccaneers (0-5-2, 2-3-0).
  Worst margin: deflation 3.79 at R54. Plan bought by the base-economy simulation: deflation 8/8.
- `floodedvalley_easy.yaml` (easy; hero admiral_brickell): 3 buccaneers (2-3-0, 2-0-2, 0-0-0); 1 sub (0-1-2); 1 mermonkey (0-0-1).
  Worst margin: easy 2.33 at R39. Plan bought by the base-economy simulation: easy 13/13.
- `floodedvalley_medium.yaml` (medium, military_only, reverse; hero admiral_brickell): 13 buccaneers (0-4-2, 0-3-2, 3-0-2, 3-0-1); 1 sub (0-1-3).
  Worst margin: medium 2.33 at R15, military_only 2.33 at R15, reverse 2.25 at R55. Plan bought by the base-economy simulation: medium 42/42, military_only 41/41, reverse 42/42.

**Not written.**

- primary_only: not written: the dam blocks every land spot's sight; the only primary tower that reaches the track is an Ice Monkey at four water-edge spots (14 units of each lane), far from a 2.0 margin.
- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Glacial Trail

**Mechanics (map data).** One long lane, 16% of it hidden under ice. Every tower except Ice Monkeys (and the heroes Silas and Dan) is frozen for 2 rounds in every 10, counted from the round it was placed. The checks here count a tower bought before round r as frozen on r+8, r+9, r+10, r+18, ... (either placement round). Ice walls block 60% of the sight lines.

Model: one route, 442 of 648 units hittable (16% under the ice); 62% of the sight lines
blocked; very few legal spots near the track (the bottom-right loop and two spots on
the left), a large far land in the top right that sees nothing.

**Sources.**

- G-Horizon, Glacial Trail CHIMPS Easy Guide: ice monkeys + Perma-Spike (https://www.youtube.com/watch?v=Hv8M3AOfwS0)
- bloonswiki Glacial_Trail: the freeze rule and which towers are immune (https://www.bloonswiki.com/Glacial_Trail)

**Builds written.**

- `glacialtrail_easy.yaml` (easy; hero dan_dmonke): 3 druids (1-3-0); 2 ninjas (4-0-1); 1 dart (2-0-4).
  Worst margin: easy 2.62 at R40. Plan bought by the base-economy simulation: easy 15/15.

**Not written.**

- primary_only: not written: primary towers freeze like the others, only ice monkeys do not, and those reach the track from three spots (16-42 units); the few near-track spots cannot hold the freeze rounds.
- deflation: not written: best reached 1.18 at round 53 (druids under one radar village, ninjas, Sharp Shooter darts in three freeze groups). The far land fits only one village beside three druids, so a frozen village leaves the vines blind to the camo pinks of round 53.
- medium: not written: best reached 0.31 (round 56) and, after moving the druids for a second radar village, 0.06 (rounds 28-30: the lead rounds fall in two groups' freezes). More work needed.
- military_only: not written: helis and aces freeze like the rest; no build was found.
- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).
- reverse: not written: same build as Medium, same result.

## Infernal

**Mechanics (map data).** Two long lanes alternate by round (odd rounds top, even rounds bottom: AlternateRoundSplitter). Very little ground: islands and two middle pillars inside the waves reach both lanes; two small ponds.

Model: 2 routes, each its own scenario (odd/even rounds), ~370 hittable units; land
only 10% of the map, water 3%; no sight blockers.

**Sources.**

- TNR Omega, How to Beat Infernal on Hard with No MK: Quincy, ninja on the middle pillars, Advanced-Intel subs, ace (https://www.youtube.com/watch?v=MrI-1g5eITI)
- BlueCliff, Infernal Hard No MK (ft. Quincy) (https://www.youtube.com/watch?v=5vrEQFKBWmI)
- fandom Infernal: the lane rule and the islands (https://bloons.fandom.com/wiki/Infernal)

**Builds written.**

- `infernal_deflation.yaml` (deflation; hero quincy): 8 snipers (0-2-3, 1-3-0); 2 aces (2-3-0); 1 buccaneer (4-0-1).
  Worst margin: deflation 4.32 at R54. Plan bought by the base-economy simulation: deflation 24/24.
- `infernal_easy.yaml` (easy; hero quincy): 8 snipers (3-2-0, 0-2-2, 1-2-0); 5 darts (0-2-1, 1-0-1, 0-0-1); 2 subs (2-0-2, 1-0-1).
  Worst margin: easy 2.23 at R10. Plan bought by the base-economy simulation: easy 36/36.
- `infernal_medium.yaml` (medium, military_only, reverse; hero quincy): 2 buccaneers (4-0-1, 0-3-1); 7 snipers (0-2-4, 0-2-3, 1-2-0); 2 aces (2-3-0).
  Worst margin: medium 2.80 at R15, military_only 2.80 at R15, reverse 3.44 at R60. Plan bought by the base-economy simulation: medium 36/38, military_only 34/37, reverse 36/38.

**Not written.**

- primary_only: not written: best reached 1.26 at round 15 (then 1.10 at round 33 after repairs). The islands are full (18 towers) before both alternating lanes are covered.
- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Muddy Puddles

**Mechanics (map data).** Four lanes take turns, one lane per round (AlternateRoundSplitter: 1, 2, 3, 4, 3, 2). Long-range and map-wide towers cover the lane schedule best; the ponds between the lanes take water towers. No sight blockers.

Model: 4 routes, each its own scenario: every round is checked on every lane (the real
schedule gives each lane only some rounds, so the checks are on the safe side); no
sight blockers.

**Sources.**

- G-Horizon, Muddy Puddles CHIMPS Easy Guide: buccaneer, snipers, Advanced-Intel subs, Psi (https://www.youtube.com/watch?v=gJLFvkHiOBk)
- BlueCliff, Muddy Puddles Hard No MK (https://www.youtube.com/watch?v=2oT7VyTQKKk)
- bloonswiki Muddy_Puddles: long range does well because only one lane is active at a time (https://www.bloonswiki.com/Muddy_Puddles)

**Builds written.**

- `muddypuddles_deflation.yaml` (deflation; hero psi): 11 buccaneers (4-0-1, 0-3-2, 0-3-1, 2-0-1); 8 snipers (0-2-3, 1-3-0, 0-2-2, 1-2-0); 1 ninja (3-0-0); 2 darts (0-0-0).
  Worst margin: deflation 2.74 at R59. Plan bought by the base-economy simulation: deflation 16/16.
- `muddypuddles_easy.yaml` (easy; hero psi): 4 druids (1-3-0); 2 snipers (3-2-0, 2-2-0).
  Worst margin: easy 4.65 at R37. Plan bought by the base-economy simulation: easy 17/17.
- `muddypuddles_medium.yaml` (medium, reverse; hero psi): 5 druids (2-3-0, 1-3-0, 0-3-1, 0-3-0); 8 snipers (2-5-0, 2-2-0, 0-2-2, 1-2-0); 2 buccaneers (0-3-1, 0-0-0).
  Worst margin: medium 4.18 at R15, reverse 3.29 at R56. Plan bought by the base-economy simulation: medium 42/43, reverse 42/43.
- `muddypuddles_military_only.yaml` (military_only; hero psi): 2 snipers (1-2-0); 11 buccaneers (0-3-2, 0-3-1, 2-0-2, 2-0-1); 1 heli (3-0-2); 10 aces (2-3-0, 1-3-0, 1-1-0, 0-1-0).
  Worst margin: military_only 2.25 at R58. Plan bought by the base-economy simulation: military_only 58/71.

**Not written.**

- primary_only: not written: best reached 0.06 (round 24 camo, rounds 33-37). Each of the four lanes must hold every round in the model, and primary towers reach one or two lanes.
- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Quad

**Mechanics (map data).** Four entrances are active every round and each route loops through two quadrants; bloons are immune under the four trusses, which also block sight ($1,500 each to remove; not done here). A central pond.

Model: 4 routes in one scenario, ~270-280 hittable units (immune under the trusses);
12% of the sight lines blocked; four trusses removable ($1,500 each).

**Sources.**

- BlueCliff, Quad Hard No MK (ft. Quincy): a dart in each corner, sub, sniper, cluster bombs (https://www.youtube.com/watch?v=DAJAobKFCLE)
- fandom Quad/Strategies: the two kill zones (https://bloons.fandom.com/wiki/Quad/Strategies)
- bloonswiki Quad: spike factories and bombs at the kill zones (https://www.bloonswiki.com/Quad)

**Builds written.**

- `quad_deflation.yaml` (deflation; hero quincy): 1 village (2-2-0); 5 darts (2-0-4, 0-2-3, 1-0-3, 0-0-3); 16 bombs (0-2-3, 0-2-2); 8 snipers (1-3-0, 1-2-0); 3 spikes (1-0-0, 0-0-0); 1 ninja (0-0-0).
  Worst margin: deflation 2.00 at R54. Plan bought by the base-economy simulation: deflation 21/21.
- `quad_easy.yaml` (easy; hero quincy): 20 darts (0-2-4, 0-2-3, 1-0-3, 0-1-3); 6 boomerangs (0-3-2, 0-2-2, 0-2-1, 0-0-1); 1 bomb (0-2-2).
  Worst margin: easy 2.23 at R34. Plan bought by the base-economy simulation: easy 54/54.
- `quad_medium.yaml` (medium; hero quincy): 4 druids (2-3-0, 0-3-1); 7 ninjas (3-0-2, 3-0-1, 2-2-0, 0-0-0); 11 darts (0-2-3, 3-0-2, 1-0-2, 0-0-2); 3 boomerangs (0-2-3, 0-2-1, 0-0-2); 3 bombs (0-2-3, 0-2-2); 7 snipers (0-2-2, 2-2-0, 1-2-0).
  Worst margin: medium 2.18 at R58. Plan bought by the base-economy simulation: medium 92/99.
- `quad_military_only.yaml` (military_only; hero quincy): 8 buccaneers (0-3-2, 2-0-2); 4 helis (3-0-2, 0-2-2); 7 aces (2-3-0, 1-3-0, 2-1-0, 0-1-0); 5 snipers (0-2-3, 0-2-1, 1-2-0).
  Worst margin: military_only 2.00 at R15. Plan bought by the base-economy simulation: military_only 59/72.
- `quad_primary_only.yaml` (primary_only; hero quincy): 20 darts (0-2-3, 0-0-1, 0-0-0); 14 desperados (3-1-0, 0-3-0, 0-1-0, 0-0-0); 2 boomerangs (0-3-2, 0-2-3); 3 tacks (3-2-0, 2-3-0); 1 glue (2-0-0).
  Worst margin: primary_only 2.25 at R34. Plan bought by the base-economy simulation: primary_only 49/49.
- `quad_reverse.yaml` (reverse; hero quincy): 4 druids (2-3-0, 0-3-1); 9 ninjas (3-0-2, 3-0-1, 2-2-0, 0-0-0); 14 darts (0-2-3, 3-0-2, 1-0-2, 0-0-2); 3 boomerangs (0-2-3, 0-2-1, 0-0-2); 5 bombs (3-0-2, 0-2-3, 0-2-2, 0-0-0); 8 snipers (2-2-0, 0-2-2, 1-2-0); 3 spikes (1-0-0, 0-0-0).
  Worst margin: reverse 2.38 at R40. Plan bought by the base-economy simulation: reverse 95/113.

**Not written.**

- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Ravine

**Mechanics (map data).** Two entrances alternate by round and each one forks in two, so a round runs on two of four lanes. The model's own routes merge the Ravine forks into one route; these builds were checked on the corrected routes (Path1 -> split1 or split2 in even rounds, Path2 -> split1 or split2 in odd rounds). Bridges and trees block sight; the river is too low for water towers.

Model (corrected routes): 2 scenarios of 2 routes each (220/237 and 379/354 hittable
units); 19% of the sight lines blocked; the river is too low for water towers.

**Sources.**

- OneEyedDeacon, Ravine Chimps is SIMPLE with Etienne + Sky Shredder (https://www.youtube.com/watch?v=OpHwKwqMcOY)
- bloonswiki Ravine: the bottom-left area touches the lanes; aces ignore the sight blockers (https://www.bloonswiki.com/Ravine)

**Builds written.**

- `ravine_deflation.yaml` (deflation; hero etienne): 3 bombs (0-2-2, 0-1-2); 4 aces (2-3-0, 1-3-0); 5 druids (0-3-1, 0-3-0); 1 dart (0-2-4).
  Worst margin: deflation 2.16 at R58. Plan bought by the base-economy simulation: deflation 21/21.
- `ravine_medium.yaml` (medium, reverse; hero etienne): 6 druids (2-3-0, 0-4-1, 0-3-1); 2 ninjas (1-0-1, 0-0-0); 5 aces (2-3-0, 1-3-0).
  Worst margin: medium 2.51 at R58, reverse 2.54 at R58. Plan bought by the base-economy simulation: medium 35/36, reverse 35/36.

**Not written.**

- easy: not written: best reached 1.56 after fixing rounds 15, 28 and 30; the camo round 33 stays short on the alternating forks and no free spot is left for a radar village by the druids.
- primary_only: not written: best reached 0.06 (round 24 camo and round 34) on the four forks.
- military_only: not written: best reached 1.68 at round 38 (aces and helis; snipers left out: the bridges and trees block sight).
- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Sanctuary

**Mechanics (map data).** Two entrances meet in the middle and leave through four exits, all at once. The model's own routes follow the Reverse-mode splitters; these builds were checked on the corrected routes (left entrance -> exits 3/4, right entrance -> exits 1/2). Towers stand on round platforms that move every round: only map-wide towers or spots that barely move are used.

Model (corrected routes): 4 routes in one scenario (264/342 hittable units); 14% of the
map is moving platforms (only map-wide towers or steady spots there); no sight blockers.

**Sources.**

- OneEyedDeacon, Sanctuary Chimps is EASY with Permaspike: Obyn, desperados, snipers, Archmage (https://www.youtube.com/watch?v=auCq92xN0nk)
- bloonswiki Sanctuary (https://www.bloonswiki.com/Sanctuary)

**Builds written.**

- `sanctuary_medium.yaml` (medium, reverse; hero quincy): 3 druids (0-3-1); 8 snipers (0-2-4, 0-2-2, 2-2-0, 1-2-0); 1 wizard (0-1-0).
  Worst margin: medium 2.40 at R59, reverse 2.40 at R49. Plan bought by the base-economy simulation: medium 34/34, reverse 34/34.
- `sanctuary_military_only.yaml` (military_only; hero obyn): 8 snipers (1-5-0, 0-2-4, 2-3-0, 3-2-0); 2 aces (2-3-0).
  Worst margin: military_only 2.48 at R49. Plan bought by the base-economy simulation: military_only 31/41.

**Not written.**

- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Tricky Tracks

**Mechanics (map data).** Six short lanes run at once on three diagonal tracks. The strips between the tracks reach two lanes (one track) or more; no water. The train ($2,500, rising) is never used by the bot.

Model: 6 routes in one scenario (235-340 hittable units); 12% of the sight lines blocked;
no water; the train is a paid map ability.

**Sources.**

- ApexZ, Tricky Tracks CHIMPS Full Auto Start: darts, mermonkeys, Etienne, boomerangs (https://www.youtube.com/watch?v=fWry_CuR6GI)
- OneEyedDeacon, Tricky Tracks Chimps Guide (https://www.youtube.com/watch?v=ZaqClazQHSM)
- bloonswiki Tricky_Tracks (https://www.bloonswiki.com/Tricky_Tracks)

**Builds written.**

- `trickytracks_deflation.yaml` (deflation; hero etienne): 8 snipers (0-2-2, 1-2-0); 4 mermonkeys (3-0-1); 5 wizards (0-3-2, 0-0-0); 2 boomerangs (0-3-2, 0-3-1).
  Worst margin: deflation 2.07 at R54. Plan bought by the base-economy simulation: deflation 27/27.
- `trickytracks_easy.yaml` (easy; hero etienne): 24 darts (0-1-1, 0-1-0, 0-0-1, 0-0-0); 9 wizards (2-1-0, 0-2-1, 0-1-0, 0-0-0); 6 desperados (0-1-0, 0-0-0); 2 mermonkeys (0-1-1, 1-0-0); 2 boomerangs (0-2-3, 0-0-1); 1 druid (1-3-0); 2 snipers (0-2-2, 1-2-0); 2 tacks (3-2-0, 2-3-0).
  Worst margin: easy 2.11 at R40. Plan bought by the base-economy simulation: easy 62/62.
- `trickytracks_medium.yaml` (medium, reverse; hero etienne): 3 druids (0-3-1, 1-3-0); 5 ninjas (1-0-1, 1-0-0, 0-0-1); 10 darts (0-2-4, 0-2-3, 1-0-2); 8 desperados (0-1-0); 4 wizards (0-2-2, 0-1-2, 0-1-0); 4 boomerangs (0-2-3, 0-3-2); 5 snipers (2-2-0, 1-2-0); 1 mermonkey (0-0-1).
  Worst margin: medium 2.28 at R59, reverse 2.11 at R54. Plan bought by the base-economy simulation: medium 87/107, reverse 87/107.
- `trickytracks_military_only.yaml` (military_only; hero etienne): 8 snipers (0-2-4, 0-2-3, 1-2-0); 12 aces (2-3-0, 1-3-0); 1 heli (3-0-2).
  Worst margin: military_only 2.13 at R54. Plan bought by the base-economy simulation: military_only 34/53.
- `trickytracks_primary_only.yaml` (primary_only; hero etienne): 24 darts (0-2-3, 0-2-1, 0-1-1, 0-0-1); 9 desperados (0-1-0); 3 boomerangs (0-3-2, 0-2-2); 4 bombs (0-2-3, 0-2-2); 1 tack (0-2-1).
  Worst margin: primary_only 2.09 at R39. Plan bought by the base-economy simulation: primary_only 60/60.

**Not written.**

- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Workshop

**Mechanics (map data).** One conveyor lane; bloons ride it 50% faster (the checks speed every bloon up by 1.5) and MOAB-class drop from a chute onto its last third. The model's own routes for this map are broken (only two short stretches); these builds were checked on the corrected belt route. Tables block sight. The Reverse Motor and Track Extension gizmos are never used by the bot.

Model (corrected routes): the belt (310 hittable units) and the MOAB stretch from the
chute (106 units: the chute itself is a hidden path); a third of the sight lines
blocked (tables); checked with bloons 1.5x faster. MOAB rounds are the hard part: a
MOAB crosses its visible stretch in about 3 seconds.

**Sources.**

- BlueCliff, Workshop Hard No MK (ft. Quincy): ninja + spike factories at the exit (https://www.youtube.com/watch?v=sukBmxvnnk4)
- OneEyedDeacon, Easiest Workshop Chimps w/ NO ABILITIES: Sauda, spikes (https://www.youtube.com/watch?v=e2jZofvcaNQ)
- bloonswiki Workshop_(BTD6): fast bloons, spikes at the single exit (https://www.bloonswiki.com/Workshop_(BTD6))

**Builds written.**

- `workshop_easy.yaml` (easy; hero sauda): 3 druids (1-3-0, 0-3-0); 1 spike (2-0-4); 1 ninja (2-0-1); 1 heli (3-0-2); 1 dart (2-0-4); 1 bomb (0-3-2).
  Worst margin: easy 2.59 at R40. Plan bought by the base-economy simulation: easy 15/15.
- `workshop_reverse.yaml` (reverse; hero sauda): 5 druids (2-4-0, 2-3-0, 0-3-1, 0-3-0); 5 ninjas (4-2-0, 3-2-0, 3-0-1, 0-0-0); 1 ace (2-5-0); 1 spike (0-1-1); 1 dart (0-2-5); 1 glue (4-2-0).
  Worst margin: reverse 2.18 at R58. Plan bought by the base-economy simulation: reverse 20/42.

**Not written.**

- primary_only: not written: best reached 0.97 at round 40. A MOAB crosses its visible stretch (106 units at 1.5x speed) in about 3 seconds and primary towers can stand only in the exit cluster, which is full.
- deflation: not written: best reached 0.7 at round 58 (MOAB-class rounds, same reason).
- medium: not written: best reached 1.98 at round 58; Reverse alone passes (workshop_reverse).
- military_only: not written: best reached 0.06 at round 40 (aces and helis only).
- apopalypse: not written: random continuous rounds; no round data to check a build against (see gaps).

## Tests run

Run on 2026-10-23 after the last file was written, at idle priority, with every
build in `strategies/maps/` in place (these and the other groups'):

- `python tests/test_map_hints_offline.py`: all 8 tests pass.
- `python tests/test_achievement_strats_offline.py`: all tests pass.
- A final re-check of every file listed above (the scratch checker: `load_all`
  bot_ready, `validate`, legal spots off the HUD, `usable`, `coverage`, the margin
  replay on the account's economy, and both threat simulations) passed for all 43.

The scratch tools used for this work (replay with the corrected routes, the
restricted optimizer, the round fixers) are not in the repo; the corrections they
make are listed under "Corrections used only in the checks" so they can be built
into `dps_model` / `tools/optimize_builds.py`.

