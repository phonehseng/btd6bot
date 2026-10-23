# Advanced maps, group B: map builds and what was learned

Maps: Midnight Mansion, Mushroom Grotto, Off The Coast, Party Parade, Pat's
Pond, Peninsula, Ship Capture, Spillway, Sunken Columns, Sunset Gulch,
Underground, X Factor. Written October 2026 for the medals the main account
still lacked: Easy, Primary Only, Deflation, Medium, Military Only, Reverse
(and Apopalypse) on all twelve, plus Hard on Party Parade, Pat's Pond and
Ship Capture.

## How the builds were made and checked

1. **Map analysis from the game's own data.** Routes, scenarios and
   untouchable stretches from `btd6bot/dps_model.py` `Track`; areas, sight
   blockers and removables from `data/map_geometry/<id>.json`
   (`btd6bot/mapgeom.py`) and `data/map_mechanics.json`; legal cells from
   `placement.valid_spots`; reach from `Track.zones` with line of sight.
   Each map was also rendered with a screen-fraction grid
   (`tools/render_map_mechanics.py`) to read the spots.
2. **Community research.** The per-map findings already in
   `docs/map_strategies.md` (bloonswiki, fandom, guide-video descriptions,
   BTD6 Index), plus a web pass for the modes asked here. Almost every
   written build is Hard or CHIMPS; bloon.games has a page per map and mode
   (`https://bloon.games/how-to-beat-<mode>-on-<map>/`, modes
   `standard-easy`, `primary-only`, `deflation`, `standard-medium`,
   `military-only`, `reverse`, `standard-hard`), but for these maps they are
   video-only, except Sunset Gulch whose pages give tower lists. So the
   community input is the choice of towers and the kind of spot (bays for
   subs, the ring on Underground, both junctions on Pat's Pond, the grate on
   Ship Capture, mirrored lanes on Party Parade, snipers where sight is
   blocked); each file names its sources.
3. **Order and spots.** `tools/optimize_builds.py`'s greedy optimizer, run
   from a scratch script (nothing written to `strategies/optimized/`),
   restricted to the towers the sources use, usually at a safety margin of
   2.6 so hand edits keep at least 2.0, with these extra rules:
   * one tower per tier-5 upgrade (the game allows one Sub Commander; the
     optimizer had planned two);
   * no spot under the top HUD (fy < 0.13, or fx > 0.68 and fy < 0.17) and
     no cell the live game refused (`data/maps/<map>.npz` refused layer):
     spots the optimizer chose there were moved to the nearest good legal
     cell with at least 90% of the coverage;
   * the map's model gaps patched in the scratch track (below).
   The XP target is Desperado (the account's most-needed tower XP) where
   the mode allows it, Sub in Military Only. Some builds were written by
   hand (their header says so).
4. **Validation of every file**, in the account's scenario (Double Cash +
   Fast Track, `optimize_builds.economy(mode, boosts)`: Easy from round 10
   with ~$3,832, Medium from round 15 with ~$6,057, Hard from round 22 with
   ~$8,930, Deflation round 31 with ~$40,000):
   * `strategy.load_all()`: bot_ready True, `validate()` and `readiness()`
     empty; every upgrade within the account's unlocked tiers;
   * **strict replay**: plan, then the fill steps that name a tower, bought
     in order as soon as the cash allows (like `optimize_builds.replay_plan`),
     `dps_model.round_margin` on every round: worst at least 2.0;
   * **executor replay**: the bot's own `strategy.Executor` on a cash-only
     game (`simulate_threats.CashGame`) with the account's economy - plan,
     fill (it buys the first affordable fill step), `surplus()`, threat
     answers, and a start that ticks until nothing more is bought like
     `match.Match.setup` - and the margin of the towers standing at each
     round's start (towers without an `at` are left out unless map-wide):
     worst at least 2.0;
   * `tools/simulate_threats.py simulate(...)` on the base economy (as the
     test runs it) and with the account's scenario: no gaps; in the Easy
     family the whole `plan` is bought on the base economy;
   * `strategy.coverage()` on a fully unlocked account: nothing missing;
   * every `at` legal in plan order (as `tests/test_map_hints_offline.py`);
   * `tests/test_map_hints_offline.py` and
     `tests/test_achievement_strats_offline.py` (results at the end).
5. **Easy family (Easy, Primary Only, Deflation).** The test's threat
   simulation runs the base economy (no boosts; Deflation on $20,000) and
   requires the whole `plan` to be bought, so `plan` is the core the base
   economy affords and the rest of the build is `fill`. The margins count
   plan + fill (both replays). Fill steps carry `round:` (the round the
   replay bought them in), so a cheap later fill step cannot jump ahead of
   an expensive earlier one (the executor buys the first affordable fill
   step). In Deflation the first buys pop round 31's black and zebra
   bloons (a sniper or sub first), because the test checks round 31 after
   only ten actions.
6. **Villages and alchemists carry `near:`.** The executor uses a buffer's
   `at` only when its `near` names a standing tower; without it the buffer
   goes wherever it buffs the most towers.

Apopalypse was not built for any map: its rounds are random and come without
a break, so the damage model (one standard round at a time) cannot validate
a build for it.

## The builds

Worst damage-model margin over every round of each mode (2.0 = the defence would still
hold at half strength), with the round in brackets: the strict replay (plan, then fill,
in order) and the executor replay (the bot's own Executor). Both use the current
`dps_model` (after the buccaneer and sniper line-of-sight fixes) and the scratch track
patches listed under the model gaps. Cost = what the replay bought in that mode.

| Build | Modes | Hero | Strict replay worst | Executor replay worst | Cost |
|---|---|---|---|---|---|
| `offthecoast_deflation.yaml` | Deflation | admiral_brickell | Deflation 3.40 (R51) | Deflation 3.40 (R51) | $38,670 |
| `offthecoast_easy.yaml` | Easy, Primary Only | sauda | Easy 2.54 (R27); Primary Only 2.54 (R27) | Easy 2.46 (R40); Primary Only 2.48 (R34) | $28,685 |
| `offthecoast_medium.yaml` | Medium, Military Only, Reverse | admiral_brickell | Medium 2.65 (R37); Military Only 2.65 (R37); Reverse 2.65 (R37) | Medium 2.65 (R37); Military Only 2.65 (R37); Reverse 2.65 (R37) | $83,720 |
| `partyparade_easy.yaml` | Easy, Primary Only | sauda | Easy 2.57 (R34); Primary Only 2.57 (R34) | Easy 2.11 (R34); Primary Only 2.11 (R34) | $32,745 |
| `patspond_deflation.yaml` | Deflation | obyn | Deflation 2.35 (R59) | Deflation 2.35 (R59) | $39,710 |
| `patspond_easy.yaml` | Easy, Primary Only | obyn | Easy 2.38 (R34); Primary Only 2.38 (R34) | Easy 2.38 (R34); Primary Only 2.38 (R34) | $31,635 |
| `patspond_reverse.yaml` | Reverse, Medium | obyn | Reverse 2.38 (R34); Medium 2.18 (R34) | Reverse 2.38 (R34); Medium 2.18 (R34) | $104,450 |
| `peninsula_deflation.yaml` | Deflation | admiral_brickell | Deflation 2.13 (R51) | Deflation 2.13 (R51) | $39,910 |
| `peninsula_easy.yaml` | Easy | admiral_brickell | Easy 2.77 (R15) | Easy 2.77 (R15) | $17,540 |
| `peninsula_medium.yaml` | Medium, Military Only, Reverse | admiral_brickell | Medium 4.36 (R37); Military Only 4.36 (R37); Reverse 4.56 (R37) | Medium 2.33 (R34); Military Only 2.33 (R34); Reverse 2.51 (R34) | $105,370 |
| `shipcapture_deflation.yaml` | Deflation | obyn | Deflation 2.13 (R59) | Deflation 2.18 (R59) | $39,160 |
| `shipcapture_easy.yaml` | Easy, Primary Only | obyn | Easy 2.13 (R12); Primary Only 2.13 (R12) | Easy 2.09 (R34); Primary Only 2.09 (R34) | $33,195 |
| `shipcapture_medium.yaml` | Medium, Military Only, Reverse | obyn | Medium 2.54 (R54); Military Only 2.54 (R54); Reverse 2.35 (R54) | Medium 2.59 (R43); Military Only 2.59 (R43); Reverse 2.65 (R49) | $75,550 |
| `spillway_deflation.yaml` | Deflation | psi | Deflation 2.57 (R54) | Deflation 2.57 (R54) | $39,975 |
| `spillway_easy.yaml` | Easy, Primary Only | sauda | Easy 2.09 (R34); Primary Only 2.09 (R34) | Easy 2.09 (R34); Primary Only 2.09 (R34) | $32,360 |
| `spillway_medium.yaml` | Medium, Military Only, Reverse | psi | Medium 2.62 (R54); Military Only 2.62 (R54); Reverse 2.43 (R56) | Medium 2.99 (R34); Military Only 2.99 (R34); Reverse 3.08 (R34) | $89,820 |
| `sunsetgulch_deflation.yaml` | Deflation | obyn | Deflation 2.71 (R56) | Deflation 2.54 (R60) | $22,870 |
| `sunsetgulch_easy.yaml` | Easy | obyn | Easy 2.77 (R15) | Easy 2.77 (R15) | $23,105 |
| `sunsetgulch_medium.yaml` | Medium, Military Only, Reverse | obyn | Medium 2.54 (R37); Military Only 2.54 (R37); Reverse 2.48 (R37) | Medium 2.51 (R60); Military Only 2.51 (R60); Reverse 2.51 (R60) | $88,950 |
| `underground_deflation.yaml` | Deflation | quincy | Deflation 2.35 (R54) | Deflation 2.35 (R54) | $39,885 |
| `underground_easy.yaml` | Easy, Primary Only | quincy | Easy 2.83 (R27); Primary Only 2.83 (R27) | Easy 2.30 (R27); Primary Only 2.30 (R27) | $33,180 |
| `underground_medium.yaml` | Medium, Military Only, Reverse | quincy | Medium 2.80 (R16); Military Only 2.80 (R16); Reverse 2.95 (R49) | Medium 3.05 (R27); Military Only 3.05 (R27); Reverse 3.12 (R50) | $71,840 |
| `xfactor_easy.yaml` | Easy | psi | Easy 3.29 (R15) | Easy 3.29 (R15) | $32,085 |
| `xfactor_medium.yaml` | Medium, Military Only, Reverse | psi | Medium 2.74 (R15); Military Only 2.74 (R15); Reverse 2.68 (R55) | Medium 2.74 (R15); Military Only 2.74 (R15); Reverse 2.89 (R55) | $70,350 |

## Per map: mechanics, sources, builds, what was skipped

### Midnight Mansion
* **Mechanics (game data).** Two lanes at once (`BloonTagOnlySplitter`)
  share the top floor, run down both sides and back up the middle stairs;
  55% of each lane is hidden track (`hidden_track` ranges 0-1 and 10-12).
  Fire walls (`MapEvent- KnightCycle`, every 2 rounds) block sight; the
  model counts every wall as always there. No water; heli, ace, super,
  village and spike factory fit nowhere unless the $250 drawers are bought.
* **Sources.** bloonswiki / fandom Midnight_Mansion (walls and fires block
  sight, Sauda strong on the shared top floor, drawers are the only spot for
  big towers); NamelessBandicoot CHIMPS (Tack Zone, Super Brittle); Steam
  threads (drawer snipers/aces).
* **Builds: none.** Six builds (Easy, Deflation, Medium, Military Only,
  Reverse) passed 2.0 while map-wide snipers counted the whole track; after
  the sniper line-of-sight fix in `dps_model` every one dropped to 0.06-0.42
  (snipers on the shelves see almost nothing past the walls) and they were
  withdrawn. A fresh Easy search without that assumption reached 0.78.
  Buying the drawers (bot capability) is the way in.

### Mushroom Grotto
* **Mechanics.** Two lanes at once loop twice through the centre. Towers
  stand only on lit ground and target only lit zones; without the mushrooms
  only a 45-unit circle round the centre is lit (about a sixth of each lane).
* **Sources.** bloonswiki Mushroom_Grotto; OneEyedDeacon, G-Horizon,
  HyperF3 and bloon.games CHIMPS (all buy the mushrooms by rounds 25-36).
* **Builds: none.** Deflation reached 2.04 before the sniper sight fix and
  1.94 after it (withdrawn); Easy, Primary Only, Medium, Military Only and
  Reverse never reached 2.0 (best 1.2-1.8). Buying the mushrooms is the way
  in.

### Off The Coast
* **Mechanics.** One 901-unit lane that starts and ends in the sea (559
  hittable); beach above, sea below; no obstacles.
* **Sources.** bloonswiki Off_The_Coast; BlueCliff Hard (ninja in the left
  bend, buccaneer in the left bay); BTD6 Fenix CHIMPS (subs 2-0-4, crow's-nest
  sniper); BTD6 Index (Pre-Emptive Strike 2TC); bloon.games mode pages.
* **Builds.** `offthecoast_easy` (Easy, Primary Only: Desperados inside both
  bends, Cluster/MOAB Mauler bombs); `offthecoast_deflation` (sub fleet in
  both bays, aces, cliff sniper); `offthecoast_medium` (Medium, Military
  Only, Reverse: sub fleet, cliff snipers, Brickell).

### Party Parade
* **Mechanics.** Two separate 411-unit lanes at once either side of a hedge
  wall that blocks placement and sight; everything is mirrored.
* **Sources.** bloonswiki Party_Parade (the wall; snipers see one side);
  BeatbloonsBob Double HP / ABR / Impoppable / Magic guides (one main tower
  per lane); bloon.games mode pages.
* **Builds.** `partyparade_easy` (Easy, Primary Only: Desperados in mirrored
  pairs inside both lane rectangles, MOAB Mauler at each exit).
* **Not reached.** Deflation (best 1.24-1.68), Medium / Military Only /
  Reverse (a sniper build passed before the sight fix and fell to 1.35;
  later searches 1.13-1.43), Hard (best 1.33).
* **Existing `partyparade_hard.yaml` fails validation:** worst margin 0.16
  (Medium, round 38) and 0.12 (Hard, round 38).

### Pat's Pond
* **Mechanics.** Two lanes at once round a pond in opposite directions,
  meeting at both junctions; four $500 obstacles not bought.
* **Sources.** bloonswiki Pat's_Pond (pack the junctions, right one
  preferred); BlueCliff Hard; fandom Pat's_Pond/Strategies; OneEyedDeacon and
  retrogaming fun CHIMPS.
* **Builds.** `patspond_easy` (Easy, Primary Only: Desperados and MOAB
  Mauler bombs beside both junctions); `patspond_deflation`;
  `patspond_reverse` (Reverse and Medium: towers packed at both junctions).
* **Not reached.** Military Only (sub fleets cannot pop lead or see camo,
  and rocks/trees block the snipers; best 0.94), Hard (best 1.23-1.35).
* **Existing `patspond_hard.yaml`:** Medium 2.35 (passes); Hard 0.41 at
  round 79 and 0.47 at round 63 (fails).

### Peninsula
* **Mechanics.** One short lane (705 units, 400 hittable) round a
  sight-blocking mountain; over 80% water; land only on the mountaintop and
  a small plot by the bottom bend; three $500 kelp rocks not bought.
* **Sources.** bloonswiki Peninsula (water builds); 0Python BTD6 CHIMPS with
  Brickell (2-0-4 sub spam); BlueCliff Hard (mountaintop sniper/heli).
* **Builds.** `peninsula_easy` (buccaneers, Mermonkeys, subs);
  `peninsula_deflation` (sub fleet); `peninsula_medium` (Medium, Military
  Only, Reverse: sub fleet and a sniper on the bottom-right plot - a
  mountaintop sniper does not see the lane once sight counts).
* **Skipped:** Primary Only (only the small plot reaches the lane; best
  1.04).

### Ship Capture
* **Mechanics.** Four short plank lanes under the ship; rounds board from
  the left, the right or both (patched in the scratch track, see gaps); the
  $1,000 hatch is not bought.
* **Sources.** bloonswiki Ship_Capture (side table; build on the grate);
  dq7reimagined CHIMPS without micro; bloon.games Military/Hard text.
* **Builds.** `shipcapture_easy` (Easy, Primary Only: Desperados and bombs
  on the grate and decks); `shipcapture_deflation`; `shipcapture_medium`
  (Medium, Military Only, Reverse: snipers, aces, a heli).
* **Not reached.** Hard (best 1.26).

### Spillway
* **Mechanics.** Four lanes at once into a central loop; four $2,000 walls
  block sight; the centre barrel has no legal cell in the model.
* **Sources.** bloonswiki / fandom Spillway; BlueCliff Hard (barrel ninja,
  sniper, Sub Commander in the right pool); retrogaming fun CHIMPS; a Steam
  thread on Guided Magic wizards.
* **Builds.** `spillway_easy` (Easy, Primary Only: Desperados, darts and
  MOAB Maulers beside the diagonal lanes); `spillway_deflation` (bombs,
  aces, snipers, subs); `spillway_medium` (Medium, Military Only, Reverse:
  subs, snipers, helis, an ace).

### Sunken Columns
* **Mechanics.** Two lanes cross twice round two sunken columns. In the
  model only the sunken middle is legal and the track walls block its sight
  (the raised outer land the guides use is not placeable).
* **Builds: none.** Easy, Deflation, Medium, Reverse and Military Only all
  passed while snipers counted the whole track; with sight they fell to
  0.68-1.66 and were withdrawn. Primary Only never had a tower that reaches
  a lane (0.1).

### Sunset Gulch
* **Mechanics.** One winding lane; MOAB-class bloons take a straight rail
  from round 40 (patched, see gaps).
* **Sources.** bloonswiki Sunset_Gulch; bloon.games per-mode guides (the
  only text guides for these modes); OneEyedDeacon Axis of Havoc CHIMPS.
* **Builds.** `sunsetgulch_easy` (Easy); `sunsetgulch_deflation` (snipers
  and druids); `sunsetgulch_medium` (Medium, Military Only, Reverse: snipers
  on Strong).
* **Skipped.** Primary Only (best 1.87 at rounds 34 and 40 with the rail
  added back).

### Underground
* **Mechanics.** Two short lanes at once, both looping through the central
  ring and crossing at its edges; lots of floor.
* **Sources.** bloonswiki Underground; BlueCliff Hard (Quincy in the ring);
  retrogaming fun CHIMPS.
* **Builds.** `underground_easy` (Easy, Primary Only: Desperados in and
  round the ring); `underground_deflation`; `underground_medium` (Medium,
  Military Only, Reverse: aces over the ring, snipers, a heli).

### X Factor
* **Mechanics.** Eight paths (`AlternateRoundMultiPathSplitter`), four
  active per round, rotating; the middle of every path is a tunnel (31-44%
  hidden). Towers left of centre reach four paths, right of centre the other
  four; snipers reach all.
* **Sources.** bloonswiki / fandom X_Factor; G-Horizon CHIMPS (Desperados in
  the corners, sniper spam on Strong); BlueCliff Hard.
* **Builds.** `xfactor_easy` (Easy: snipers on Strong); `xfactor_medium`
  (Medium, Military Only, Reverse: snipers and aces).
* **Not reached.** Primary Only (best 0.67), Deflation (best 1.24).

Apopalypse: skipped on every map (random rounds; the model cannot validate).

## Model gaps found (validated around them in a scratch track; no code changed)

1. **Sunset Gulch: the MOAB rail is missing from `dps_model.Track`.** The
   spawn splitter (`MoabOnlySplitter`) sends MOAB-class bloons down
   `PathSpecial`, but the same path is the splitter's `overrideBossPath`,
   so `map_routes` drops it as a boss path and the model lets MOABs walk the
   winding bloon lane. In the game they take the straight rail along the
   top from round 40, and its exit is past the right edge of the play area.
   The Sunset Gulch builds were checked with `PathSpecial` added back as a
   MOAB-only route (scratch helper `fix_sunset_gulch`). A fix in
   `map_routes`: do not drop a path that a `MoabOnlySplitter` flags as the
   MOAB path, even if it is also the boss override.
2. **Ship Capture: the sides are not modelled.** `AlternateBloonSplitter`
   is not an `AlternateRound...` splitter, so the model shares every round
   over all four plank lanes. In the game a round boards from the LEFT side,
   the RIGHT side or both (bloonswiki table). The builds were checked with
   three scenarios (left two lanes, right two lanes, all four), the worst
   counting (`fix_ship_capture`).
3. **Mushroom Grotto: darkness is not modelled.** Towers only target bloons
   in lit zones (`EnablePathTargetZoneAction`: 45 units round the centre at
   the start; 60-70 after buying mushrooms, which the bot cannot). The model
   lets every tower hit dark track. The builds were checked with each lane
   cut to the 45-unit circle round the centre mushroom (~124 of 787 units
   per lane; `fix_mushroom_grotto`). The circle's centre is assumed to be
   the centre mushroom's position; the scene data gives only the radius.
4. **X Factor: one path per scenario.** `AlternateRoundMultiPathSplitter`
   activates a group of four paths per round; the model plays each of the
   eight paths alone with the whole round on it. That is harsher than the
   game (a round's bloons are shared by four paths), so every X Factor
   build must hold a full round on each path; the optimizer also needed a
   patch (leaks summed over scenarios) because a tower that fixes only some
   paths never improved the worst scenario.
5. **Advanced Intel subs (2-x-x) are map-wide in the model.** In the game
   they shoot what other towers see. Every sub fleet here has a map-wide
   sniper (or the hero and many towers) for that sight.
6. **Buccaneer middle path was overrated (fixed in `dps_model` during the
   day).** Before `_trigger_rates`, Grape Shot / Cannon secondaries counted
   at a readiness-check rate. Builds with buccaneers were re-checked after
   the fix: `offthecoast_medium` (1.46) and `offthecoast_deflation` (0.98)
   fell below 2.0 and were replaced by sub-fleet builds; `peninsula_easy`
   kept 2.77; the Pat's Pond Deflation proposal with a 0-3-2 boat was
   replaced too. (Account note: sub path 1 became unlocked to tier 4 during
   the day - the Peninsula fleets use Bloontonium Reactors, 4-x-x.)
7. **Snipers ignored line of sight (fixed in `dps_model` during the day).**
   Map-wide snipers counted the whole track even behind walls. Every build
   with snipers was re-checked after the fix: 13 fell below 2.0 and were
   withdrawn (all of Midnight Mansion and Sunken Columns, Mushroom Grotto
   Deflation, Party Parade Medium, Peninsula Deflation and Medium, Spillway
   Medium); Peninsula Medium/Deflation and Spillway Medium were rebuilt
   (sub fleets; a sniper on the plot that sees the lane), the others stay
   withdrawn. The executor replay places an answer or surplus sniper (no
   `at`) on the legal cell that sees most track, as `pick_spots` would.
8. **Non-monotonic upgrades.** On Mushroom Grotto, upgrading snipers from
   1-3-0 to 2-3-0, or a bomb from 0-2-2 to 0-4-2, lowered the round-56/60
   margin in the model (strong targeting reorders single-target work). The
   builds avoid those upgrades; it may be worth a look in `dps_model`.

## Executor and test gaps found (no code changed)

1. **Auto ids clash with plan ids.** `Executor._new_tid(kind)` names an
   unnamed tower `<kind><n>` (`sub1`, `ice1`, `ace1`, ...). A surplus or
   panic sub placed while a plan tower `sub1` stands overwrote the plan
   tower's record in the offline replay (the real game would then upgrade
   the wrong tower). The builds here use ids that cannot clash (`sb1`,
   `ic1`, `ac1`, `snp1`, `dsp1`, ...); other strategies with ids like
   `sub1` are exposed. `_new_tid` should skip ids already used by the
   strategy or standing on the map.
2. **Buffers ignore `at` without `near`.** `_spots_widening` sends a
   village/alchemist without a standing `near` tower straight to
   `_buff_spots`, so its `at` is never tried. The builds give every buffer a
   `near:` list.
3. **Fill order.** The executor buys the first affordable fill step, so a
   cheap later step can jump ahead of an expensive earlier one. The builds
   gate fill steps with `round:`.
4. **Deflation start in the test.** `simulate_threats.simulate` without a
   scenario gives the first round only 10 actions, so a Deflation plan
   whose first ten actions do not pop round 31's bloons (black, zebra) shows
   a gap although the bot buys everything before Play (`Match.setup`).
5. **Threat answers trigger on the executor's own heuristic.** In several
   Easy games the executor bought an extra ace/super/sniper "for blimps"
   around round 37 (`_answer_ramp`) although the damage model rates the
   round safe; the money is not lost (the tower helps), but it delays the
   fill. Those towers are not counted in the executor replay (no `at`).
6. **Two tier-5 towers of a kind** are impossible in the game; nothing
   stops a strategy (or the optimizer) from planning two. A `validate()`
   rule would catch it.

## Capabilities the bot is missing (they would open better builds)

* **Buying removable obstacles** (`mapgeom.removables()` gives names,
  prices and positions): Mushroom Grotto's mushrooms ($250 x4 + $400) light
  the map and open placement - every guide buys them by rounds 25-36, and
  without them Mushroom Grotto is the weakest map here; Midnight Mansion's
  two $250 drawers (the only spots for villages, supers, aces, spike
  factories, and sight over the fires); Spillway's $2,000 walls (sight into
  the loop from the side pools); Pat's Pond's $500 rocks; Peninsula's $500
  kelp rocks (land by the lane); Ship Capture's $1,000 hatch (water for
  subs/buccaneers on the grate).
* **Spillway's centre barrel** has no legal cell in the bot's model; every
  guide puts a ninja there. Placement would need a hand-calibrated cell.
* **Sunken Columns' raised outer land** is unplaceable in the model (the
  model gap in `docs/map_strategies.md`); guides camp the top column. With
  it, Primary Only would be possible.
* **Aimed abilities and targets** (Perma-Spike target on Ship Capture, Wall
  of Fire relocation on Spillway, MOAB Assassin / UCAV in the Sunset Gulch
  guides) are left out of every build.

## Medals covered

`-` = no build (reason in the map's section above); Apopalypse is skipped on
every map.

| Map | Easy | Primary Only | Deflation | Medium | Military Only | Reverse | Hard |
|---|---|---|---|---|---|---|---|
| Midnight Mansion | - | - | - | - | - | - | |
| Mushroom Grotto | - | - | - | - | - | - | |
| Off The Coast | offthecoast_easy | offthecoast_easy | offthecoast_deflation | offthecoast_medium | offthecoast_medium | offthecoast_medium | |
| Party Parade | partyparade_easy | partyparade_easy | - | (partyparade_hard, fails) | - | - | (partyparade_hard, fails) |
| Pat's Pond | patspond_easy | patspond_easy | patspond_deflation | patspond_reverse (also patspond_hard, 2.35) | - | patspond_reverse | (patspond_hard, fails) |
| Peninsula | peninsula_easy | - | peninsula_deflation | peninsula_medium | peninsula_medium | peninsula_medium | |
| Ship Capture | shipcapture_easy | shipcapture_easy | shipcapture_deflation | shipcapture_medium | shipcapture_medium | shipcapture_medium | - |
| Spillway | spillway_easy | spillway_easy | spillway_deflation | spillway_medium | spillway_medium | spillway_medium | |
| Sunken Columns | - | - | - | - | - | - | |
| Sunset Gulch | sunsetgulch_easy | - | sunsetgulch_deflation | sunsetgulch_medium | sunsetgulch_medium | sunsetgulch_medium | |
| Underground | underground_easy | underground_easy | underground_deflation | underground_medium | underground_medium | underground_medium | |
| X Factor | xfactor_easy | - | - | xfactor_medium | xfactor_medium | xfactor_medium | |

Hard was asked only for Party Parade, Pat's Pond and Ship Capture; the
greedy search never reached 2.0 there (best 1.33, 1.35 and 1.26: the
round-34 and round-63/78 crowds and the ZOMG rounds), so no Hard build was
written. The existing `partyparade_hard.yaml` and `patspond_hard.yaml` fail
Hard in the current model (0.12 and 0.41).

## Tests (run at idle priority, after the last build was written)

* `python tests/test_map_hints_offline.py`: every check passes for these 24
  files (load/valid/ready, usable and covered, threat simulation including
  the Easy-family plan completion, spot legality - the last checked file by
  file for these builds). The one failure in the run is another group's
  file: `adorastemple_deflation.yaml`, sniper `s1` at (0.836, 0.624) is not
  a legal spot.
* `python tests/test_achievement_strats_offline.py`: all passed.
