# Intermediate maps, group A: map builds and what was learned

Maps: Adora's Temple, Ancient Portal, Balance, Bazaar, Bloonarius Prime,
Chutes, Covered Garden, Cracked, Downstream, Encrypted, Firing Range,
KartsNDarts. Written October 2026 for the medals the main account still
lacked on these maps (Easy, Primary Only and Deflation first, then Medium,
Military Only and Reverse, then Hard; Apopalypse last).

## How the builds were made and checked

1. **Map analysis from the game's own data.** Routes, scenarios and
   untouchable stretches from `btd6bot/dps_model.py` `Track` (and
   `map_routes`); areas, sight blockers and removables from
   `data/map_geometry/<id>.json` (`btd6bot/mapgeom.py`) and
   `data/map_mechanics.json`; legal cells from `placement.valid_spots`; reach
   and line of sight from `Track.zones` with `MapModel.sight`. Every map was
   rendered with `tools/render_map_mechanics.py` to read the ground.
2. **Community research.** Wikis (bloonswiki, fandom; their pages refuse
   plain fetching, so mostly through search snippets), guide-video titles and
   descriptions, btd6index.win, and the AutoBTD6 bot's fixed-spot playthrough
   scripts (github.com/ANRAR4/AutoBTD6). Almost no written build exists for
   Deflation, Military Only or Reverse on these maps: the community input is
   the choice of towers (helis and snipers on alternating or walled maps,
   boats in the canals and ponds, desperados and bombs where primary towers
   must stand far from the lane) and the kind of spot. Each file names its
   sources in its header.
3. **Order and spots.** Hand-written for Chutes Medium, Cracked, Downstream;
   the rest come from `tools/optimize_builds.py`'s greedy `Optimizer`, run in
   memory from a scratch script (nothing written to `strategies/optimized/`),
   restricted to bot-friendly towers (no mortar/dartling; no skywarden,
   mermonkey, beast handler, engineer, ice or glue as damage), with these
   extra rules:
   * a heli is never placed or upgraded without Pursuit (top path 2) first,
     and every heli place step is followed by an explicit `2-0-0` step;
   * snipers' candidate spots are ranked by the track they can SEE (the
     optimizer gives map-wide towers its worst cells, which left snipers
     behind walls);
   * the optimizer's map model also refuses the cells the live game refused
     (`data/maps/<map>.npz`, read only) and the top-HUD band (fy < 0.13, or
     fx > 0.68 and fy < 0.17: lives/cash/round, the gear, the red cancel X);
   * one tower per tier-5 upgrade (the optimizer does not know the rule);
   * an XP target (heli, buccaneer, sniper or bomb, by map) so that surplus
     cash raises the margins instead of lying idle.
   The hero goes to the best-covering cell that stays legal with every other
   tower standing (so it never blocks a later tower).
4. **Easy family and Deflation: plan + fill.** The offline test needs the
   whole `plan` bought in the threat simulation's base economy (Deflation
   $20,000, no Double Cash or Fast Track). So `plan` is the largest prefix
   the simulation finishes (the hero last) and the rest is `fill`, which the
   executor buys right after the plan with the account's money (Deflation
   $40,400; Easy from round 10 with Double Cash income).
5. **Validation of every file** (scratch scripts that mirror the repo
   checks):
   * `strategy.load_all()`: bot_ready True, `validate()` and `readiness()`
     empty;
   * damage model in the account's scenario (`optimize_builds.economy(mode,
     {double_cash, fast_track})`: Easy R10 $3,832, Medium R15 $6,057, Hard
     R22 $8,930, Deflation R31 $40,000): plan bought in order as cash allows
     (tier by tier, cheapest path first, like `Executor._next_path`), then
     the fill the way `Executor.tick` buys it (the first affordable fill step
     each time), `dps_model.round_margin` on every round with the towers
     standing at its start. Worst at least 2.0 for every mode (with the fill
     where there is one);
   * `tools/simulate_threats.py simulate()`: no gaps; Easy family and
     Deflation: plan finished;
   * every `at` legal in plan/fill order in the test's model AND in the bot's
     live model (refused cells), and outside the HUD band;
   * `S.usable` / `S.coverage` on a full account, base_success 0.5-0.85;
   * `python tests/test_map_hints_offline.py` and
     `python tests/test_achievement_strats_offline.py` (run at idle
     priority): both pass in full after the final copies (an extra run of the
     map-strategy tests restricted to this group's 30 files passes too).

## The builds

Worst damage-model margin over every round of each mode, in the account's
scenario (2.0 = the defence would still hold at half strength). For the
Easy-family and Deflation files the first number includes the `fill`
(bought with the account's Double Cash money); the plan alone is what an
account without Double Cash would get.

| Build | Modes | Worst margin (account scenario) | Plan alone |
|---|---|---|---|
| `adorastemple_deflation.yaml` | deflation | 6.65 | 1.92 |
| `adorastemple_hard.yaml` | medium, military_only, reverse, hard | 3.19, 3.19, 3.75, 2.62 | (no fill) |
| `ancientportal_deflation.yaml` | deflation | 2.77 | 1.54 |
| `ancientportal_medium.yaml` | medium, military_only, reverse | 4.32, 4.32, 4.46 | (no fill) |
| `balance_deflation.yaml` | deflation | 2.04 | 1.59 |
| `balance_medium.yaml` | medium, military_only, reverse | 2.62, 2.62, 2.89 | (no fill) |
| `bazaar_deflation.yaml` | deflation | 2.35 | 1.02 |
| `bazaar_medium.yaml` | medium, military_only, reverse | 2.80, 2.80, 2.80 | (no fill) |
| `bloonariusprime_deflation.yaml` | deflation | 2.18 | 1.33 |
| `bloonariusprime_military_only.yaml` | military_only, reverse | 2.83, 3.08 | (no fill) |
| `chutes_deflation.yaml` | deflation | 2.04 | 1.63 |
| `chutes_hard.yaml` | hard | 2.18 | (no fill) |
| `chutes_medium.yaml` | medium, military_only, reverse | 2.95, 2.95, 2.89 | (no fill) |
| `coveredgarden_easy.yaml` | easy | 2.02 | 0.87 |
| `cracked_deflation.yaml` | deflation | 2.48 | 1.66 |
| `cracked_medium.yaml` | medium, military_only, reverse | 4.00, 4.00, 4.76 | (no fill) |
| `downstream_deflation.yaml` | deflation | 3.55 | 1.66 |
| `downstream_medium.yaml` | medium, military_only, reverse | 3.51, 3.51, 4.46 | (no fill) |
| `encrypted_deflation.yaml` | deflation | 2.07 | 1.11 |
| `encrypted_easy.yaml` | easy | 3.12 | 1.87 |
| `encrypted_medium.yaml` | medium, military_only, reverse | 3.47, 3.47, 4.22 | (no fill) |
| `encrypted_primary_only.yaml` | primary_only | 2.30 | 0.79 |
| `firingrange_deflation.yaml` | deflation | 2.99 | 1.94 |
| `firingrange_easy.yaml` | easy | 4.60 | 2.51 |
| `firingrange_military_only.yaml` | military_only, reverse | 2.40, 2.48 | (no fill) |
| `firingrange_primary_only.yaml` | primary_only | 2.09 | 0.95 |
| `kartsndarts_deflation.yaml` | deflation | 2.28 | 1.94 |
| `kartsndarts_easy.yaml` | easy | 3.26 | 1.89 |
| `kartsndarts_medium.yaml` | medium, military_only, reverse | 2.51, 2.51, 2.54 | (no fill) |
| `kartsndarts_primary_only.yaml` | primary_only | 2.09 | 1.07 |

## Per map

### Adora's Temple
*Needed: Deflation, Medium, Military Only, Apopalypse, Reverse, Hard.*
* **Mechanics.** Four entrances (AlternateRoundMultiPathSplitter): odd rounds
  left+right, even rounds top+bottom; every lane loops the temple base and
  climbs it. The temple is one line-of-sight block (a sniper outside sees
  ~44% of a lane); ground towers reach 10-14%; the four corner ponds each
  touch two lanes (~14% of each for a boat).
* **Sources.** bloonswiki and fandom Adora's Temple (Carrier Flagship, avoid
  Pursuit helis), Bacanator Gamer's Medium Military Only (Buccaneer, Etienne,
  Sniper), btd6index.
* **Builds.** `adorastemple_hard.yaml` (Medium, Military Only, Reverse,
  Hard): two boats per pond, Etienne; worst margin medium 3.19, military_only 3.19, reverse 3.75, hard 2.62. **Played live
  on Hard at 22:51 and won: round 80, 0 lives lost, 14.8 minutes.** The game
  refused three pond spots, the executor moved those boats to other cells
  of the ponds, and the threat check bought its sniper and ninja answers;
  the file now uses the cells the game accepted where the live model has
  room (one boat of the top-right pond still has none and is placed by the
  executor's fallback, as in the won game).
  `adorastemple_deflation.yaml`: boats and two bombs; worst margin deflation 6.65 with the fill (plan alone 1.92).
* **Skipped.** Apopalypse (no round data).

### Ancient Portal
*Needed: Deflation, Medium, Military Only, Apopalypse, Reverse.*
* **Mechanics.** One spiral into a portal, then the right lane (the left lane
  only after a click on the realign device); ground inside the spiral reaches
  ~50% of it; hero pedestals above and below the spiral.
* **Sources.** bloonswiki Ancient Portal, AutoBTD6 CHIMPS script (Sniper,
  two helis, Village, Glue), BlueCliff Hard.
* **Builds.** `ancientportal_medium.yaml` (Medium, Military Only, Reverse):
  seven Pursuit helis and a camo sniper; worst margin medium 4.32, military_only 4.32, reverse 4.46.
  `ancientportal_deflation.yaml`: Pursuit helis plus helpers;
  worst margin deflation 2.77 with the fill (plan alone 1.54). The earlier `ancientportal_deflation.yaml`
  (Eleado's three ninjas + alchemist) rated 0.46 in the damage model (the
  alchemist's brew is not modelled) and was removed from strategies/maps;
  the new file takes its name.
* **Skipped.** Apopalypse.

### Balance
*Needed: Deflation, Medium, Military Only, Apopalypse, Reverse, Hard.*
* **Mechanics.** Two entrances at once (left and right edge), four sub-paths
  each winding round a central loop; hedges leave small plots; most central
  plots are refused in the live model (gap 6); only the right entrance is
  modelled (gap 3).
* **Sources.** bloonswiki Balance, sarahs-btd6-site guide, Bloonyah Bloons
  Medium Military Only, CarlyleX2 Deflation, btd6index (456 2TC wins).
* **Builds.** `balance_medium.yaml` (Medium, Military Only, Reverse): a ring of snipers where the hedges leave them sight (the central plots are refused live), Advanced Intel subs and a boat in the bottom pond; worst margin medium 2.62, military_only 2.62, reverse 2.89. `balance_deflation.yaml`: snipers, Advanced Intel subs, a bomb and a Super Monkey; worst margin deflation 2.04 with the fill (plan alone 1.59).
* **Skipped.** Hard (best live-aware draft 1.63 at round 63: the refused central plots leave only snipers and the pond), Apopalypse.

### Bazaar
*Needed: Deflation, Medium, Military Only, Apopalypse, Reverse, Hard.*
* **Mechanics.** Two lanes alternating by round (top left-to-right, bottom
  right-to-left), each S-bending through the middle; stalls and $500 palm
  trees block sight; no heli pad fits; the canal by the bridge reaches both
  lanes' middle stretches.
* **Sources.** bloonswiki and fandom Bazaar (Carrier Flagship + Brickell,
  Comanche, Armor Piercing subs, Destroyer), btd6index.
* **Builds.** `bazaar_medium.yaml` (Medium, Military Only, Reverse): Advanced Intel subs in the canal (one Sub Commander), snipers on the open grass, Brickell; worst margin medium 2.80, military_only 2.80, reverse 2.80. `bazaar_deflation.yaml`: the same towers; worst margin deflation 2.35 with the fill (plan alone 1.02). A first version built on canal boats was withdrawn when the buccaneer bug (gap 1) and then the live refused cells (gap 6) came to light: the live game refuses most of the grass, which the boats needed snipers on.
* **Skipped.** Hard (best 1.76: the boats and snipers run out on rounds 34/78), Apopalypse.

### Bloonarius Prime
*Needed: Deflation, Military Only, Apopalypse, Reverse.*
* **Mechanics.** Prime-numbered rounds take the short right lane, the others
  the long lane round the left lake (RuleSplitter); the rock column blocks
  sight between them; a sniper at the top middle sees ~90% of both.
* **Sources.** bloonswiki Bloonarius Prime (heli/global towers), OneEyedDeacon
  CHIMPS, AutoBTD6 CHIMPS/Impoppable scripts.
* **Builds.** `bloonariusprime_military_only.yaml` (Military Only, Reverse):
  Pursuit helis, subs and snipers; worst margin military_only 2.83, reverse 3.08.
  `bloonariusprime_deflation.yaml`: Pursuit helis, bombs, Advanced Intel
  subs; worst margin deflation 2.18 with the fill (plan alone 1.33). The earlier
  `bloonariusprime_deflation.yaml` (two Neva-Miss aces and a sniper) rated
  0.44 and was removed from strategies/maps; the new file takes its name.
* **Skipped.** Apopalypse.

### Chutes
*Needed: Deflation, Medium, Military Only, Apopalypse, Reverse, Hard.*
* **Mechanics (the leaks).** Two lanes that ALTERNATE every round
  (AlternateRoundSplitter), each very short (~460 hittable world units, ~16 s
  for a red on Hard), crossing in an X at the bottom middle. Anything that
  covers one lane defends every other round, and a ground tower in the X
  reaches only ~16% of each lane - which is why the general land builds
  leaked 112 and 90 lives on Easy and Primary Only. The statues ($350) block
  sight; each pool reaches one lane only. A sniper on the top strip sees
  ~85% of both lanes: map-wide towers are the answer.
* **Sources.** bloonswiki Chutes (Comanche Commander + Geraldo, Carrier
  Flagship + Brickell), fandom Chutes/Strategies (heli/ace, Advanced Intel
  subs in the pools), btd6index 2TC records.
* **Builds.** `chutes_medium.yaml` (Medium, Military Only, Reverse): Pursuit
  heli to Apache Prime with IFR, snipers, a boat per pool and a sub;
  worst margin medium 2.95, military_only 2.95, reverse 2.89. `chutes_hard.yaml`: heli to Apache Prime, a row of
  snipers, Bomber Aces; worst margin hard 2.18. `chutes_deflation.yaml`: bombs, wizards and a ninja in and around the X, snipers on the top strip, a boat; worst margin deflation 2.04 with the fill (plan alone 1.63).
* **Skipped.** Apopalypse.

### Covered Garden
*Needed: Easy, Primary Only, Deflation, Medium, Military Only, Apopalypse,
Reverse, Hard.*
* **Mechanics.** One lane; three of four garden quarters under glass at any
  time, the open quarter moving every round; the bot uses only the strips
  left and right of the garden, from which ground towers reach ~10% (the
  entrance or exit) and a sniper on the lower left strip ~60-67%. One cell
  fits a heli pad, and the live game refused part of the left strip.
* **Sources.** bloonswiki and fandom Covered Garden, Touch Tap Play guide.
* **Builds.** `coveredgarden_easy.yaml` (Easy): snipers on the strips;
  worst margin easy 2.02 with the fill (plan alone 0.87).
* **Skipped.** Primary Only (best 1.07: primary towers on the strips reach
  only the entrance), Deflation (best 1.04 with the full $40,400), Military
  Only and Reverse (best ~1.8 with snipers + the one heli, the Apache bought
  at any point), Medium (a snipers-only draft reached exactly 2.0; not
  written, as `coveredgarden_hard.yaml` already serves Medium), Hard (not
  attempted after Medium failed), Apopalypse. All of these need the pane
  timing (capability gap). The existing `coveredgarden_hard.yaml` (now
  Medium only) rates 1.45 (round 33) in the current model: it fails the 2.0
  bar.

### Cracked
*Needed: Deflation, Medium, Military Only, Apopalypse, Reverse.*
* **Mechanics.** One long winding lane (the longest Intermediate track); the
  rock in the middle hides the only pond; no water otherwise; a sniper right
  of the rock sees ~93%.
* **Sources.** bloonswiki Cracked, AutoBTD6 CHIMPS script (Sniper, two
  helis), bloonswiki Deflation strategy, btd6index.
* **Builds.** `cracked_medium.yaml` (Medium, Military Only, Reverse): three
  Pursuit helis and a sniper; worst margin medium 4.00, military_only 4.00, reverse 4.76. `cracked_deflation.yaml`: two Inferno Ring tacks, a cluster bomb and a Sharp Shooter in the bends, a Maim MOAB sniper, a Bomber Ace and two Bloonjitsu ninjas with the Double Cash half; worst margin deflation 2.48 with the fill (plan alone 1.66).
* **Skipped.** Apopalypse.

### Downstream
*Needed: Deflation, Medium, Military Only, Apopalypse, Reverse.*
* **Mechanics.** One lane with two loops; no sight blockers; the river left
  of the start reaches ~27% of the lane for a boat.
* **Sources.** bloonswiki Downstream, AutoBTD6 CHIMPS script, Bacanator Gamer
  Deflation (a buccaneer is the key tower).
* **Builds.** `downstream_medium.yaml` (Medium, Military Only, Reverse):
  sniper, Destroyer boats, Pursuit heli, Brickell; worst margin medium 3.51, military_only 3.51, reverse 4.46.
  `downstream_deflation.yaml`: the same towers plus ninjas in the loops;
  worst margin deflation 3.55 with the fill (plan alone 1.66).
* **Skipped.** Apopalypse.

### Encrypted
*Needed: Easy, Primary Only, Deflation, Medium, Military Only, Apopalypse,
Reverse.*
* **Mechanics.** One entrance, two exits (half the bloons each); the walled
  middle and the four $250 class pads are closed to the bot; the grass
  outside reaches 8-10% of an exit, a sniper on the bottom grass ~44% of
  each.
* **Sources.** bloonswiki Encrypted, AutoBTD6 CHIMPS script, Rydeon Gaming
  Deflation.
* **Builds.** `encrypted_easy.yaml` worst margin easy 3.12 with the fill (plan alone 1.87);
  `encrypted_primary_only.yaml` (bombs and desperados)
  worst margin primary_only 2.30 with the fill (plan alone 0.79); `encrypted_medium.yaml` (Medium, Military Only,
  Reverse: Pursuit helis and snipers) worst margin medium 3.47, military_only 3.47, reverse 4.22;
  `encrypted_deflation.yaml` worst margin deflation 2.07 with the fill (plan alone 1.11).
* **Skipped.** Apopalypse.

### Firing Range
*Needed: Easy, Primary Only, Deflation, Military Only, Apopalypse, Reverse.*
* **Mechanics.** Two lanes at the same time, crossing; the fence and the
  $1,000 outpost keep ground towers off the early track (<10% of a lane); a
  sniper on the bottom grass sees ~84% of both lanes.
* **Sources.** bloonswiki Firing Range, Bacanator Gamer Deflation, btd6index.
* **Builds.** `firingrange_easy.yaml` worst margin easy 4.60 with the fill (plan alone 2.51);
  `firingrange_primary_only.yaml` (darts and desperados)
  worst margin primary_only 2.09 with the fill (plan alone 0.95); `firingrange_military_only.yaml` (Military
  Only, Reverse: a line of snipers, subs; no Pursuit helis with two live
  lanes) worst margin military_only 2.40, reverse 2.48; `firingrange_deflation.yaml`
  worst margin deflation 2.99 with the fill (plan alone 1.94).
* **Skipped.** Apopalypse.

### KartsNDarts
*Needed: Easy, Primary Only, Deflation, Medium, Military Only, Apopalypse,
Reverse.*
* **Mechanics.** One figure-eight lane; 24% of it in tunnels (non-MOAB
  bloons untouchable); the $500 tyre stacks fill both loops; no sight
  blockers.
* **Sources.** bloonswiki KartsNDarts, AutoBTD6 Hard no-MK and CHIMPS
  scripts.
* **Builds.** `kartsndarts_easy.yaml` worst margin easy 3.26 with the fill (plan alone 1.89);
  `kartsndarts_primary_only.yaml` (desperados above the tunnel)
  worst margin primary_only 2.09 with the fill (plan alone 1.07); `kartsndarts_medium.yaml` (Medium, Military
  Only, Reverse: Pursuit helis and snipers) worst margin medium 2.51, military_only 2.51, reverse 2.54;
  `kartsndarts_deflation.yaml` (helis and bombs) worst margin deflation 2.28 with the fill (plan alone 1.94).
* **Skipped.** Apopalypse.

## Model gaps found on the way

1. **Buccaneer secondary weapons (fixed in the repo).** attacks.json linked a
   buccaneer's Grape Shot secondary (and the Cannon Ship / Monkey Pirates
   secondary cannon) to the wrong weapon, so dps_model read its 0.05 s
   readiness check as its rate: 100 grape shots per second at 0-1-0, 480
   frags per second at 0-4-2. Every boat with a middle-path upgrade looked
   many times stronger than it is (my first Chutes and Bazaar boat builds
   showed margins of 3-7 that were really 0.3-1.8). Reported; the
   coordinator fixed it (`dps_model._trigger_rates`) and removed the
   optimized builds that fell under 2.0.
2. **Snipers without line of sight (fixed in the repo).** `station_for`
   skipped the sight test for map-wide towers, so a sniper behind a hedge
   counted the whole track (Balance Medium fell from 2.46 to 1.65 once sight
   was applied). Reported; fixed with `MAP_WIDE_NEEDS_SIGHT = ("sniper",)`.
3. **Balance: only the right entrance is modelled.** Its paths form a loop,
   so `map_routes` starts from the first spawn path only and builds twelve
   routes from the right edge; the left entrance (half the bloons in play)
   is not modelled. The builds lean on map-wide towers and mirrored ground
   towers; the model sends every bloon one way, which is stricter than the
   real half-and-half split, but a route-order effect cannot be ruled out.
4. **Ancient Portal: the left (realigned) lane is played as a second
   scenario.** The bot never clicks the realign device, so only the right
   lane is used in play; the model keeps the worst of both (stricter).
5. **Adora's Temple: each of the four lanes is its own scenario.** In play a
   round uses a pair (left+right or top+bottom), half the bloons each; the
   model sends every bloon down one lane (stricter). The temple's peak and
   steps (the wiki's best spots) are not placeable in the bot's map model.
6. **The live refused layer is wide.** `data/maps/<map>.npz` refuses large
   parts of Balance (635 land cells: most central plots), Covered Garden
   (747) and Cracked (963), and many heli pads on Bloonarius Prime. The
   executor avoids those cells, so every `at` here was moved off them (the
   damage was re-checked after the move). If many of those refusals came
   from held-tower runs rather than real limits (as group B suspects), a way
   to forget them would give Balance its central plots back.
7. **Threat table vs boats.** `strategy.coverage` counts only snipers (and a
   few other fixed tiers) as ceramic/BFB/ZOMG answers and no military tower
   as the round-63 rush answer, so boat- and heli-heavy builds carry answer
   steps (sniper 2-2-0 / 4-2-0, a ninja 4-0-2 for Hard) that the threat
   check may buy even though the damage model does not need them.
8. **Answers with `at`.** `test_map_strategy_spots_are_legal` allows an `at`
   in an answer step only to re-place a planned tower at its own spot;
   answer towers the plan never places carry no `at` (spot by role).

9. **Boat top path read as closed in play.** In the won Adora's Temple game
   the upgrade panel showed no price on the top path of three boats after
   their first top tier ("path 1 is closed or maxed ... not buying it this
   game"), and later of two snipers, so those towers stopped short of their
   planned crosspaths (the build still won with 0 lives lost). The account
   has every buccaneer and sniper upgrade unlocked, so this looks like a
   panel-reading problem worth a look.

## Capability gaps (not changed in code)

* **Removable obstacles** (none bought): Chutes statues ($350, open sight for
  snipers on the middle), Bazaar palm trees ($500, sight), Cracked rock
  ($1,000, uncovers the only pond: a boat there is the bloon.games CHIMPS
  core), Downstream rocks ($350, room inside the loops), Encrypted class
  pads ($250 each, inside the walls: the best ground on the map), Firing
  Range outpost ($1,000, the Deflation video's centre spot), KartsNDarts tyre
  stacks ($500, the loop interiors).
* **Ancient Portal**: the realign device (free switch) and the totem blast
  (clickable when lit) are never used.
* **Covered Garden panes**: three garden quarters are closed on any round
  and the open one moves every round. Towers under the glass can only be
  placed or upgraded on their quarter's rounds; a pane-aware executor
  (`mechanics_data.pane_cycle` in the hints) would unlock the ground the
  guides use and probably every mode skipped below.
* **Heli targeting**: only Pursuit is reliable; the bot cannot set Lock in
  Place or Patrol Points, so helis were left out where two lanes run at once
  (Firing Range, Adora's Temple, Balance: Pursuit chases back and forth).
* **Abilities**: Monkey Pirates' hook, MOAB Assassin, Tsar Bomba and the
  hero abilities are pressed blindly or not at all; the damage model counts
  none of them.
* **Apopalypse**: random continuous rounds with no round data
  (`data/rounds.json` says so), so no build can be validated round by round;
  skipped on every map.
