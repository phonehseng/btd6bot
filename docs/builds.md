# Solo builds: tower XP for every tower

The owner's goal: "every build should be possible for every monkey if I need the
exp to unlock its paragon. A large part of the script should be to help unlock
needed paragons." This page describes `strategies/generated/solo_<tower>.yaml`:
one build per tower (all 26 towers of `btd6bot/towers.py`; heroes are not
towers), written by `tools/gen_builds.py` from the game's own data.

## How tower XP grinding works with them

- At every round end the round's tower XP is split between tower **types** in
  proportion to the cash invested in them (`docs/tower_xp.md`,
  `data/tower_xp.json`). Heroes take no share.
- So a game grinds XP for tower X when most of the money on the map is in X.
  Each solo build puts its plan's cash into one tower (`xp_target:` in the
  YAML); the "Plan share" column below says how much. Towers that carry a game
  alone get nearly all of it, support towers that need a defence beside them
  less.
- The planner reads that share from the plan (`strategy.invested_cash` ->
  `cost_share`) and, in games it is sure of (p >= 0.85), weights XP into towers
  still short of their paragon (`planner.paragon_status`, nearest paragon
  first). With a solo build for every tower, the nearest paragon always has a
  game that feeds it.
- The planner never replays a beaten map/mode, so a solo build is chosen for a
  first-time medal where it is confident enough; its prior (`base_success`)
  is calibrated from real wins and losses as they come in.

## How a build is made

`tools/gen_builds.py` (its docstring has the details):

1. **Carry or support.** A tower carries a game when it pops bloons itself,
   has a blimp damage figure in `data/counters.json`, is not a support/income
   tower or a buffer, and need not be aimed. Carries get a solo build. Every
   other tower gets a compact defence (two copies and one complement of the
   best carry that may stand beside it in the same modes - a camo-seeing one
   first) and the rest of the money goes into the tower itself. Banana Farms
   go to Marketplace first (`Game.drops_bananas`: paid without bananas to
   collect); buffers (Village, Alchemist) stand next to the defence.
2. **Main path.** Every path is judged at tier 4 and tier 5 by what one tower
   can do there (game model + `threats.py`): the share of the round
   calendar's bloon signatures it pops alone, the `strategy.ANSWERS` threats it
   answers, blimp damage per dollar, what it lends towers in range. Copies work
   at the highest tier a Medium game pays for four times over; one copy later
   goes to tier 4 and tier 5 (one tier 5 per upgrade, as the game allows).
3. **Complement.** One or two copies on another path, the one that adds most
   of what the main path misses; when it adds lead or camo, those tiers are
   bought before those bloons come. Its tier 5 is the build's second tier 5.
4. **Support only where needed.** A radar village (0-2-0) when no copy sees
   camo and one 2-0-0 exit spike factory as leak insurance.
   **Answers** (`answers:`, tried in order when a threat is due and nothing on
   the map answers it): the tower's own copy on its plan path first, then a
   helper of another kind - cheapest first, tier-0 answers before upgraded
   ones, never a gift-box tower, in category-only modes one of that category.
   The helper is what lets `coverage()` (and so the planner) accept the build
   on an account whose own tiers are still locked - exactly when the tower
   needs the XP. For MOAB-class threats the executor's blimp ramp check also
   runs these answers whenever its damage estimate is short, so there
   "another copy of the tower" comes between its own steps and the helper:
   a short estimate first buys more of the tower, the helper only when all
   copies stand or their tiers are locked. On a fully unlocked account this
   costs a few percent of the XP share (the "Simulated share" column), in
   exchange for every build being playable while its tower is still weak and
   for extra damage when the estimate says it is short.
5. **Water towers** (Sub, Buccaneer) play only the maps where they reach at
   least 60% of the track (`data/map_fit.json`, the planner's `FULL_FIT`);
   the Mermonkey stands on land or water and plays everywhere.

## Which modes, and why

Every build is played through `tools/simulate_threats.py` in each candidate
mode (real prices of the mode's difficulty, the game's own round income, no
Double Cash; water maps both with and without water; both tick counts the
tests use). Candidates: Easy family (easy, primary_only for primary towers,
deflation), Medium family (medium, military_only for military towers,
reverse, apopalypse) and Hard (hard, magic_only for magic towers). A mode is
dropped when:

- the strategy is not usable or `coverage()` misses a threat in that mode (in
  primary/military/magic only, with the towers that mode forbids taken out);
- any round brings a bloon nobody on the map can pop (a "gap");
- the blimp damage estimate (`threats.blimp_capacity`, pessimistic) falls
  below the executor's panic bar 0.4 (Easy/Medium), or below its "enough" bar
  1.0 for Hard and Apopalypse - which must also reach it without the build's
  blimp helpers and without the executor buying blimp damage elsewhere;
- the tower being levelled ends with less than a fifth of the cash spent (no
  XP game for it);
- it is a category-only mode whose standard mode (easy for primary_only,
  medium for military_only, hard for magic_only) did not pass.

Aim-bound towers (Mortar, Dartling) must also pass with their own damage
taken out: the bot does not aim them, so the defence has to hold alone.

`base_success` is conservative because no generated build has been played:
Easy 0.92 / Medium 0.86 / Hard 0.80 at most (below every hand-tested strategy
of that difficulty), minus 0.03 for each other tower kind the simulation had
to buy, 0.03 for a support build (its defence is small on purpose) and up to
0.05 for blimp damage short of 1.0. The planner calibrates it from results.

## The builds

Generated from the last run of `python tools/gen_builds.py`. Crosspaths are
the copies' working crosspaths. "Plan share" is the tower's share of the
plan's cash (what the planner reads as the XP split); "Simulated share" is
its share of all cash spent at the end of the simulated games in the kept
modes (lower: answers, the exit spike and the executor's surplus spending
take some). Modes come with their `base_success`; the last column says why
the other modes were dropped.

<!-- builds:start -->
| Tower | Build | Plan share | Simulated share | Modes (base_success) | Why not the others |
|---|---|---|---|---|---|
| Dart Monkey | solo: 0-2-4 Sharp Shooter + 4-0-2 Juggernaut (+ exit spike) | 96% | 70%-98% | easy 0.86, primary_only 0.89, deflation 0.87, medium 0.80, reverse 0.80 | apopalypse: blimp damage 0.14 < 1.00; hard: blimp damage 0.48 < 1.00 |
| Boomerang Monkey | solo: 4-0-2 M.O.A.R Glaives + 0-4-2 Turbo Charge (+ radar village, exit spike) | 94% | 61%-85% | easy 0.83, primary_only 0.86, deflation 0.91, medium 0.77, reverse 0.77 | apopalypse: blimp damage 0.12 < 1.00; hard: blimp damage 0.57 < 1.00 |
| Bomb Shooter | solo: 0-4-2 MOAB Assassin + 0-2-4 Recursive Cluster (+ radar village, exit spike) | 94% | 76%-100% | easy 0.89, primary_only 0.92, deflation 0.92, medium 0.83, reverse 0.83, hard 0.77 | apopalypse: blimp damage 0.16 < 1.00 |
| Tack Shooter | solo: 4-0-2 Ring of Fire + 0-2-4 Overdrive (+ radar village, exit spike) | 95% | 54%-82% | easy 0.83, primary_only 0.84, deflation 0.86, medium 0.75, reverse 0.75 | apopalypse: blimp damage 0.08 < 1.00; hard: blimp damage 0.56 < 1.00 |
| Ice Monkey | defence Dart Monkey 0-2-4, then Ice Monkey 2-0-4 Icicles | 88% | 51%-68% | easy 0.82, primary_only 0.84, medium 0.76, reverse 0.76 | deflation: blimp damage 0.35 < 0.40; apopalypse: blimp damage 0.07 < 1.00; hard: blimp damage 0.41 < 1.00 |
| Glue Gunner | defence Dart Monkey 0-2-4, then Glue Gunner 4-2-0 Bloon Liquefier | 87% | 54%-64% | easy 0.82, primary_only 0.84, deflation 0.83, medium 0.76, reverse 0.76 | apopalypse: blimp damage 0.06 < 1.00; hard: blimp damage 0.59 < 1.00 |
| Desperado | defence Dart Monkey 0-2-4, then Desperado 4-2-0 Twin Sixes | 89% | 50%-57% | easy 0.82, primary_only 0.84, medium 0.77, reverse 0.77 | deflation: blimp damage 0.34 < 0.40; apopalypse: blimp damage 0.07 < 1.00; hard: blimp damage 0.50 < 1.00 |
| Sniper Monkey | solo: 4-2-0 Maim MOAB + 2-0-4 Full Auto Rifle (+ exit spike) | 97% | 84%-100% | easy 0.89, deflation 0.92, medium 0.83, military_only 0.83, reverse 0.83, hard 0.74 | apopalypse: blimp damage 0.19 < 1.00 |
| Monkey Sub | solo: 0-2-4 Armor Piercing Darts + 4-2-0 Bloontonium Reactor (+ exit spike) | 97% | 78%-96% | easy 0.86, deflation 0.91, medium 0.76, military_only 0.80, reverse 0.76 | apopalypse: blimp damage 0.13 < 1.00; hard: blimp damage 0.42 < 1.00 |
| Monkey Buccaneer | solo: 0-4-2 Monkey Pirates + 4-0-2 Aircraft Carrier (+ exit spike) | 98% | 75%-99% | easy 0.92, deflation 0.89, medium 0.80, military_only 0.83, reverse 0.80 | apopalypse: blimp damage 0.12 < 1.00; hard: blimp damage 0.76 < 1.00 |
| Monkey Ace | solo: 4-2-0 Operation: Dart Storm + 0-2-3 Neva-Miss Targeting (+ exit spike) | 97% | 73%-90% | easy 0.92, deflation 0.89, medium 0.83, military_only 0.86, reverse 0.83, hard 0.74 | apopalypse: blimp damage 0.45 < 1.00 |
| Heli Pilot | solo: 3-2-0 Razor Rotors + 2-0-3 MOAB Shove (+ exit spike) | 98% | 88%-98% | easy 0.92, deflation 0.92, medium 0.86, military_only 0.86, reverse 0.86, hard 0.77 | apopalypse: blimp damage 0.21 < 1.00 |
| Mortar Monkey | defence Sniper Monkey 4-2-0, then Mortar Monkey 4-0-2 The Big One | 77% | 28%-54% | easy 0.86, deflation 0.89, medium 0.80, military_only 0.77, reverse 0.80 | apopalypse: blimp damage 0.18 < 1.00; hard: blimp damage 0.78 < 1.00 |
| Dartling Gunner | defence Sniper Monkey 4-2-0, then Dartling Gunner 0-4-2 Rocket Storm | 62% | 30%-62% | easy 0.86, deflation 0.89, medium 0.80, military_only 0.77, reverse 0.80 | apopalypse: blimp damage 0.08 < 1.00; hard: blimp damage 0.37 < 1.00 |
| Wizard Monkey | solo: 0-4-2 Summon Phoenix + 4-0-2 Arcane Spike (+ exit spike) | 97% | 93%-93% | deflation 0.87 | easy: blimp damage 0.37 < 0.40; medium: blimp damage 0.35 < 0.40; reverse: blimp damage 0.35 < 0.40; apopalypse: blimp damage 0.11 < 1.00; hard: blimp damage 0.33 < 1.00; magic_only: blimp damage 0.38 < 1.00 |
| Super Monkey | solo: 2-0-2 Plasma Blasts + 0-2-2 Epic Range (+ exit spike) | 98% | 56%-73% | easy 0.89, medium 0.83, reverse 0.83 | deflation: gap R45: camo+purple (dart could pop it but cannot see camo); apopalypse: blimp damage 0.14 < 1.00; hard: blimp damage 0.71 < 1.00; magic_only: blimp damage 0.81 < 1.00 |
| Ninja Monkey | solo: 0-2-4 Sticky Bomb + 4-2-0 Bloonjitsu (+ exit spike) | 98% | 75%-99% | easy 0.84, deflation 0.88, medium 0.77, reverse 0.77 | apopalypse: blimp damage 0.18 < 1.00; hard: blimp damage 0.48 < 1.00; magic_only: blimp damage 0.56 < 1.00 |
| Alchemist | defence Ninja Monkey 0-2-4, then Alchemist 2-4-0 Transforming Tonic | 83% | 39%-39% | deflation 0.85 | easy: Alchemist gets only 12% of the cash: no XP game for it; medium: Alchemist gets only 18% of the cash: no XP game for it; reverse: Alchemist gets only 18% of the cash: no XP game for it; apopalypse: blimp damage 0.14 < 1.00; hard: blimp damage 0.42 < 1.00; magic_only: blimp damage 0.58 < 1.00 |
| Druid | solo: 4-0-2 Ball Lightning + 2-4-0 Jungle's Bounty (+ exit spike) | 97% | 69%-95% | easy 0.87, medium 0.81, reverse 0.81 | deflation: blimp damage 0.36 < 0.40; apopalypse: blimp damage 0.12 < 1.00; hard: blimp damage 0.50 < 1.00; magic_only: blimp damage 0.53 < 1.00 |
| Mermonkey | defence Ninja Monkey 0-2-4, then Mermonkey 4-0-2 Abyssal Warrior | 68% | 25%-42% | easy 0.80, deflation 0.88, medium 0.77, reverse 0.77 | apopalypse: blimp damage 0.06 < 1.00; hard: blimp damage 0.75 < 1.00; magic_only: blimp damage 0.47 < 1.00 |
| Skywarden | defence Ninja Monkey 0-2-4, then Skywarden 2-0-4 Frozen Verdict | 71% | 28%-57% | easy 0.86, deflation 0.85, medium 0.80, reverse 0.80 | apopalypse: blimp damage 0.07 < 1.00; hard: blimp damage 0.74 < 1.00; magic_only: blimp damage 0.47 < 1.00 |
| Banana Farm | defence Ninja Monkey 0-2-4, then Banana Farm 2-0-3 Marketplace | 67% | 31%-34% | easy 0.80, medium 0.75, reverse 0.75 | deflation: gap R37: lead (nothing pops it); apopalypse: blimp damage 0.08 < 1.00; hard: blimp damage 0.75 < 1.00 |
| Spike Factory | defence Ninja Monkey 0-2-4, then Spike Factory 2-0-4 Deadly Spikes | 74% | 35%-59% | easy 0.80, deflation 0.89 | medium: blimp damage 0.23 < 0.40; reverse: blimp damage 0.23 < 0.40; apopalypse: blimp damage 0.11 < 1.00; hard: blimp damage 0.52 < 1.00 |
| Monkey Village | defence Ninja Monkey 0-2-4, then Monkey Village 2-3-0 Monkey Intelligence Bureau | 85% | 24%-37% | easy 0.80, deflation 0.85, medium 0.77, reverse 0.77 | apopalypse: blimp damage 0.09 < 1.00; hard: blimp damage 0.42 < 1.00 |
| Engineer Monkey | defence Ninja Monkey 0-2-4, then Engineer Monkey 4-2-0 Sentry Expert | 72% | 27%-36% | easy 0.83, deflation 0.86, medium 0.74, reverse 0.74 | apopalypse: blimp damage 0.12 < 1.00; hard: blimp damage 0.49 < 1.00 |
| Beast Handler | defence Ninja Monkey 0-2-4, then Beast Handler 3-2-0 Great White | 80% | 36%-44% | easy 0.83, medium 0.77, reverse 0.77 | deflation: Beast Handler gets only 18% of the cash: no XP game for it; apopalypse: blimp damage 0.08 < 1.00; hard: blimp damage 0.78 < 1.00 |
<!-- builds:end -->

## Regenerating

    python tools/gen_builds.py              # rewrite every build and the table above
    python tools/gen_builds.py ninja sub    # only these towers (the table is left alone)
    python tools/gen_builds.py --check      # report only, write nothing

Run it after a game update (once `data/game_model` is refreshed), after
changes to `data/counters.json`, `strategy.ANSWERS`, the executor's threat
checks or `data/map_fit.json`, and then `python tools/check.py`.
`tests/test_generated_builds_offline.py` fails when a file no longer matches
what the generator makes from the current data, or when a build stops
passing the simulation in one of its modes. Files are written through a
temporary file and a rename, so the running bot never reads half a file;
`strategy.load_all()` also skips a generated file that does not parse and
never auto-plays one that fails `readiness()`.

## Known limits

- The simulation checks what can be popped and a rough blimp damage ramp, not
  early-round damage, placement or pierce: the plans open with two copies and
  the executor's own opener/starter rules, and the priors stay low until real
  games calibrate them.
- `Executor.surplus()` spends idle cash on the biggest towers' own paths and
  then on any tower (a radar village's other paths, the executor's opener
  dart), so the real XP share is below the plan's (the simulation shows it).
- Banana Farm income is not simulated (pessimistic for the farm build).
- Heli Pilots buy Pursuit first, like the hand-written heli strategy; target
  modes other than first/last/close/strong cannot be set by the bot.
