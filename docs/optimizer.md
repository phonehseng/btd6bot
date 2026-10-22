# The build optimizer: attack stats, a damage model, and safe XP plans

The strategies place towers by role and hope they hold. This page describes
the pipeline that instead works out, from the game's own numbers, which
towers to buy, where, and in what order, so that every round pops with a
safety margin and the money nobody needs goes into the tower whose XP is
worth most:

    tools/export_attacks.py      attack stats of every crosspath -> data/game_model/attacks.json
    btd6bot/dps_model.py         does a defence pop a round? (margin, leaks, round length)
    tools/optimize_builds.py     greedy build order per map/mode -> strategies/optimized/<map>_<mode>.yaml
    tools/optimize_builds.py --calibrate   the model against the bot's own logged games

Same rules as all the decompiling work (`decompiling_notes.md`,
`game_model.md`): only copies of the game files in `~/.btd6bot_cache` are
read, nothing of the game is modified, no game code or DLL is run, no mods.

## 1. The attack export (`data/game_model/attacks.json`)

`tools/decode_sim_model.py` already decodes all 224,031 objects of the
game's `sim_model`, but exported only what towers *can* do. The game keeps
one finished `TowerModel` per tower and crosspath (`DartMonkey`,
`DartMonkey-200`, ...; upgrades are not deltas), so the export walks each
of them (and every hero level) and writes, per crosspath:

| field | from | meaning |
|---|---|---|
| `attacks[].range`, `camo`, `targeting`, `only_tags` / `excluded_tags` | `AttackModel`, its `AttackFilterModel`, target suppliers | reach, camo detection, MOAB-only / no-MOAB, how it aims: `normal` (first/last/close/strong), `track` (spikes), `cursor` (Dartling), `point` (Mortar), `random` |
| `weapons[].rate`, `count`, `burst` | `WeaponModel.rate` (seconds), emission `Count`/`count`/`projectileCount`, `BurstWeaponBehaviorModel` | shots and projectiles per shot |
| `weapons[].fires_weapon` / `triggered` | `FireAlternateWeaponModel` / `FireWhenAlternateWeaponIsReadyModel` | a weapon fired by another (a Buccaneer's second dart: its own rate 0.05 is only a readiness check) |
| `alternate`, `crit`, `per_round`, `max_subtowers`, `projectile_limit` | `AlternateProjectileModel`, `CritMultiplierModel`, `EmissionsPerRoundFilterModel`, `SubTowerFilterModel`, `LimitProjectileModel` | |
| `projectile.pierce`, `radius`, `motion`, `speed`, `lifespan` | `ProjectileModel`, `TravelStraitModel`, `AgeModel`, `ArriveAtTargetModel`, `FollowPathModel`, ... | |
| `projectile.damage` (`amount`, `immune`, `type`) | `DamageModel.damage`, `immuneBloonProperties` | the damage type is only the set of properties it cannot pop |
| `projectile.bonus`, `conditional_bonus` | `DamageModifierForTagModel` (Moabs, Ceramic, Fortified, ...), `DamageModifierForBloonTypeModel`, `...ForBloonStateModel` | |
| `projectile.dot` | `AddBehaviorToBloonModel` + `DamageOverTimeModel` | burns, acid, corrosive glue |
| `projectile.spawn[]` | `CreateProjectileOnContact/ExhaustFraction/Expire/Interval/ExhaustPierceModel`, `EmitOnDamageModel`, `LightningModel` | sub-projectiles: a bomb's explosion, shrapnel, ... |
| `projectile.subtowers[]` | `CreateTowerModel`, `CreateTypedTowerModel` | sentries (typed sentries share equally) |
| `projectile.effects` | `SlowModel`, `FreezeModel`, `KnockbackModel`, `WindModel`, `RemoveBloonModifiersModel`, `CashModel`, ... | recorded; not used by the evaluator yet |
| `buffs[]` | `RateSupportModel`, `RangeSupportModel`, `PierceSupportModel`, `VisibilitySupportModel`, ... | villages and other supporters |
| `income` | `PerRoundCashBonusTowerModel`, `BankModel`, banana `CashModel` x per-round cap | |
| `air_unit` | `AirUnitModel` + `PathMovementModel` / `HeliMovementModel` | planes circle the tower, helis follow the bloons |

Plus, from the game_data bundle's `Mod` assets, `"modes"`: each difficulty's
bloon speed (`GlobalSpeedModModel`: **Medium 1.1, Hard 1.25**, Easy none),
starting cash and lives, price multiplier, income multiplier (Half Cash 0.5,
Deflation 0), health mods (Double HP MOABs x2, Easy round 40 MOAB x2/3) and
first/last round. The simulation tick (60 frames per second) is derived from
weapons that store a burst interval in both seconds and frames.

1,665 crosspaths and 360 hero levels; 1.6 MB, one line per crosspath. 45
behaviour types are listed per projectile as `other` without being
interpreted (Skywarden, Silas and Brickell specials, pets, map-border
rebounds, ...; the counts are in `source.uninterpreted_behaviours`).

### How it was checked (`tests/test_dps_model_offline.py`)

- **Known numbers**: Dart Monkey 1 damage, pierce 2, every 0.95 s, range 32;
  Ninja 1 damage, pierce 2, camo, every **0.62 s** (the often quoted 0.7 s is
  an older game version); Super Monkey every 0.045 s; Sniper 2 damage every
  1.59 s, map-wide; Tack Shooter 8 tacks; Boomerang pierce 4; Spike Factory
  pierce 5; Bomb Shooter's damage is the explosion's (explosion type);
  Banana Farm 4 bananas x $20 per round. Upgrades: Dart 2-0-0 pierce 5,
  Crossbow 3 damage, Sniper 1-0-0 4 damage and pops lead, Maim MOAB 30
  damage, Plasma Blasts every 0.03 s.
- **Agreement with towers.json**: camo detection worked out from the attack
  tree agrees with the decoder's own `camo` capability for **all 1,665
  crosspaths**. Lead popping agrees for 1,631 of them; the other 34 get
  their lead damage from Beast Handler pets (30) and Skywarden specials (4),
  which the export does not interpret.
- `python tools/export_attacks.py --check` prints the base towers' headline
  numbers.

## 2. The damage model (`btd6bot/dps_model.py`)

**Routes.** A map's bloon paths (`data/map_geometry`) are joined into routes
the way the map's splitters send bloons: boss-only paths dropped, a plain or
toggle splitter named after a path X says where bloons go at X's end
(Ancient Portal's portal), a path starting where another ends continues it
unless the two are offered side by side by a spawn splitter (Pat's Pond's
two lanes) or join each other end to end (Quiet Street's two entrances),
MOAB-only lanes from `MoabOnlySplitter` flags. Maps whose spawn alternates
by round (`AlternateRoundSplitter`: Luminous Cove, Enchanted Glade, Last
Resort; Bloonarius Prime's prime-round rule) get one *scenario* per
alternative: every round is played in every scenario and the worst counts.
Tunnels and gates (a path's `invulnerable` ranges) and the off-screen part
are not hittable.

**Bloons** come from the game's round sets as lots (a group split into 6
slices per route), each one layer of one bloon id with the game's health,
speed (x the mode's speed multiplier), children, immunities and tags.

**Stations.** Every tower is a station: its zone is the stretch of route
inside its range (line of sight checked on the bot's map grid for towers
that need it), and a lot spends `zone length / speed` seconds there. A
station is a single server with deadlines: a lot's job arrives when its
bloons reach the zone and must be done before they leave; the server always
works on the job that leaves first (the game's "first" targeting).
Single-target towers (sniper bullets) are planned with "strong" targeting
and put MOAB-class jobs first. A job's work is

    health of the layer (less damage carried in from its parent)
    / sum over the tower's damage sources of
          projectiles per second x hits per projectile x min(damage, health)

- *projectiles per second*: count x burst / rate per weapon, through the
  projectile tree (an explosion per carrier contact, shrapnel per hit, sub
  projectiles per interval, sentries alive = spawn rate x lifespan, ...).
- *hits per projectile*: its pierce, but no more than the bloons it can
  meet - `1 + packing x reach`, where packing is bloons per world unit (from
  the group's spawn spacing, children multiplying it) and reach is the
  projectile's own diameter plus a bloon's, plus 35% of the distance it
  flies (capped at twice the tower's range). Projectiles that wait on the
  track (spikes) meet everything that passes; blasts as wide as the tower's
  range (Ice) meet everything in the zone; lingering projectiles may hit one
  bloon several times.
- *damage*: with the game's tag bonuses; zero if the damage type cannot pop
  the layer, if the layer is camo and the tower cannot see camo (or a
  village radar in range lends it), or if a MOAB filter excludes it.
- *overflow*: the game passes a hit's excess damage on to the children
  (`distributeToChildren`), so a 3-damage tack pops a lead and two more
  layers in one hit; the model carries the mean overflow into the children.
- tacks and planes fire all around: only the share of directions that cross
  the track counts (computed from the spot); a circling plane's darts count
  40%.
- spike piles are never idle: between bloons they stock up (up to the
  spikes' lifespan of production), and spikes that outlive the round start
  the next one with 30 s of production on the track.

A popped layer's children appear where it popped, as new jobs (small layers
- everything but ceramics and MOAB-class - are worked as one job with all
their children, which keeps a round at ~7 ms for 24 towers). Layers a
station cannot hurt and whatever it does not finish in time go on to the
next station along the route; what is left after the last one leaks and
costs the game's leak damage (children included).

**Margin.** `round_margin` finds by bisection the smallest strength factor
at which the round still pops without a leak: margin 2.0 = the defence
would hold at half strength; below 1.0 it leaks as modelled; 1/16 or less:
some bloon nobody can pop at all (camo, lead, ...).

**Left out, on the safe side:** heroes, abilities, Monkey Knowledge,
alchemist brews, slows/freezes/knockback/blowback (recorded in the export,
not used), Beast Handler pets, hand-aimed towers (Mortar, Dartling: they do
nothing for the bot). **Left out, on the optimistic side:** missed shots
(fast bloons dodging darts), several towers wasting shots on the same
bloon, regrow. The calibration below measures the net effect.

## 3. Calibration against the bot's own games

`python tools/optimize_builds.py --calibrate` replays every game in
`logs/bot.log`: every `placed <id> (<kind>) at fx,fy`, `upgraded`, and
`is really` correction rebuilds the towers standing at each `round N ...
lives L` line; screen positions become world positions on the map's
geometry (the camera's height tilt included). Each round's model margin is
compared with the lives really lost in it (lives at round N minus lives at
N+1; a defeat loses what was left). Lives readings above 1.2 x the mode's
starting lives are OCR misreads and skipped; outcomes the bot corrected
later (`logs/results.jsonl` notes) are applied. Hero-only rounds are skipped.

Result on 2026-10-22 (2,104 logged rounds, 39 of them lost lives):

| model margin | rounds | lost lives | rate |
|---|---|---|---|
| some bloon unpoppable | 18 | 9 | 50% (the rest: the hero popped it) |
| 0 - 0.5 | 102 | 12 | 11.8% |
| 0.5 - 1.0 | 250 | 7 | 2.8% |
| 1.0 - 1.5 | 283 | 4 | 1.4% |
| 1.5 - 2.0 | 222 | 1 | 0.5% |
| 2.0 - 3.0 | 313 | 4 | 1.3% |
| 3.0 - 4.0 | 254 | 1 | 0.4% |
| 4.0 - 6.0 | 329 | 1 | 0.3% |
| 6.0 and more | 333 | 0 | 0% |

Every defeat in the log came at a round the model rated below 1.0 or
unpoppable - Luminous Cove R49: 0.4; Dark Path R25: 0.3; Enchanted Glade
R63: 0.2; Covered Garden R76: 0.6; Castle Revenge R46: 0.9; Monkey Meadow
R63: 0.4; Ancient Portal R54: 0.7 and 0.4 (Deflation); Bloonarius Prime
Deflation R49: 0.3; Pat's Pond R40: 0.8; Last Resort R24 and two Logs games:
a bloon type nothing on the map could pop - except one Logs game (sub and
sniper, R49: 2.2).

The model is used unscaled (`TOWER_EFFICIENCY = 1.0`): it is already on the
safe side - most rounds it rates below 1.0 did not leak (heroes, abilities
and the executor's mid-round purchases help) - and the leak rate falls
steadily with its margin. The optimizer requires **margin >= 2.0 on every
round** (`SAFETY_MARGIN`): of 1,229 logged rounds at or above it, 6 lost
lives (0.5%), against 5.4% below 1.0.

The 6 leaks above 2.0 are on Logs (4) and Castle Revenge (2, of 2 and 6
lives). On Logs a round of fast yellows (R29, margin 3.5) leaked 109 lives:
fast bloons dodge darts, which the model does not know; a Double HP round
(90 lives, 2.6) and a sub/sniper game (12 and 138 lives at 2.5 and 2.2)
also overrated it. Logs deserves a higher bar until the model learns misses
(see "Next steps").

## 4. The optimizer (`tools/optimize_builds.py`)

**Economy.** The mode's start round and cash (Mod assets) and the game's
own income per round (`data/rounds.json`, pops + end-of-round bonus). With
the account's boosts (`account.boosts`, read on map select by
`btd6bot/boosts.py`):

- Fast Track starts at `start_round - 1 + end_round // 4` (Easy round 10,
  Hard 22 - every logged game) with the skipped rounds' income on top of the
  start cash, doubled by Double Cash, less 10% (logged: Hard $9,700 against
  $9,922 by this sum; the plans assume $8,930). No Fast Track in Deflation
  or CHIMPS.
- Double Cash doubles all income (and Deflation's $20,000 start: logged
  $40,400); never in CHIMPS (`boosts.double_cash_applies`).

The plans are made for the account's boosts (that is how the bot plays).
More money at every round only makes a plan safer; `--base` plans without
boosts, for an account that has none.

**Spots.** For each tower kind: cells where it may stand
(`placement.valid_spots` on the map geometry: surface, footprint, size
limits, moving ground), every second cell scored by the route length inside
its range (line of sight counted), best first, no two overlapping. Map-wide
towers take the *worst* spots, keeping the good ones free.

**Greedy order**, round by round from the start round:

1. while some round of the next 3 (`LOOKAHEAD`) would leak at the safety
   margin, buy the action that removes the most leaked bloon health per
   dollar (rounds nearer count more). Actions: place a tower of any allowed
   kind at its best free spot with up to 3 tiers at once, or upgrade a tower
   by up to 5 tiers on one path (legal crosspaths, unlocked tiers only).
   A quick yardstick (health the new tower adds against the bloons that
   leak, per dollar) shortlists 16 actions (+4 on the XP target) for the
   full simulation. If the best action costs more than the cash but less
   than what comes in before the first leaking round, nothing is bought:
   the money is saved for it - unless the round about to start leaks, when
   the best affordable action is bought;
2. the hero, once a tower stands (its damage is not modelled);
3. the same for the next 8 rounds (`SURPLUS_WINDOW`), buying ahead;
4. when all of those are safe, money goes into the XP target: the target
   action that adds most margin to the hardest coming round per dollar.

Without income (Deflation) every round is planned at once from the start
cash. Actions on the XP target count up to 2x (`XP_PREFERENCE`), on other
towers whose XP the account needs 1.5x.

**XP value.** Tower XP per round (`data/tower_xp.json`, x the map's
difficulty multiplier) is split by cash invested per tower type
(`docs/tower_xp.md`). Each tower's XP is weighted by what it is worth to the
account: towers still short of upgrades or of their paragon count
0.5 + 0.5 x closeness (as in `planner.paragon_status`: one Hard game or
less away counts fully), towers that have everything 0.1. Per map/mode the
three most valuable XP targets that can work on the map are optimized and
the safe plan with the most value-weighted XP per hour is written. Game
length: the bot's own median seconds per round in that mode
(`logs/results.jsonl`, wins).

**Output.** `strategies/optimized/<map id>_<mode>.yaml` in the strategy
format, with `map`, `planner.maps`, `xp_target`, an `optimizer` block
(scenario, worst margin, unsafe rounds, minutes, XP per hour) and per step a
comment: round bought, cost, which round it secures, cash left. Place steps
carry `role: dps`, a `segment` (the covered stretch of route, for the
executor's current spot picking) and **`at: [fx, fy]`, the exact spot the
model evaluated** (screen fractions of the 1920x1200 window). Snipers get a
`{do: target, mode: strong}` step (they are modelled that way). `fill:`
spends surplus on the target.

`python tools/optimize_builds.py --check FILE` replays a written plan the
way the executor buys (in order, as soon as cash allows) on its recorded
economy and prints its margins: an independent check of the file.

## 5. The plans

<!-- results:start -->
(filled in by the run of 2026-10-22, see the table below)
<!-- results:end -->

## 6. Integration (not done here: the executor and planner are other modules)

1. **Load them.** `strategy.load_all()`: also read
   `strategies/optimized/*.yaml` (source `optimized`, like `generated`), and
   accept the step key `at` (`STEP_KEYS`). `strategy.usable()` already
   rejects other maps through `planner.maps`.
2. **Exact spots.** `Executor._try_place` / `pick_spots`: when a place step
   has `at: [fx, fy]`, try `model.frac_to_cell(fx, fy)` first; if the game
   refuses it, fall back to the step's `role`/`segment` picking (the
   segment is the stretch the exact spot covers). Log when the fallback is
   used, so spots that do not work can be re-checked.
3. **Targeting.** `{do: target, id, mode: strong}` follows the sniper's
   placement; `Game.target()` cycles to "strong" already.
4. **Planner.** For a map/mode with an optimized plan, prefer it over the
   general strategies; its prior from the model, e.g. `base_success` 0.97
   when `optimizer.unsafe_rounds` is empty and `worst_margin` >= 2, 0.9 for
   a worst margin of 1-2, not auto-played below 1; then calibrate from real
   results as for the generated builds. Its `xp_target` and the `planner`
   block work as for `generated/solo_*.yaml`.
5. **Live check (optional, cheap).** Before each round the match loop could
   rebuild the standing towers (`D.Placed` from the game's own spot and
   crosspath, `Track.frac_to_world`) and call `dps_model.round_margin` for
   the next rounds (~10 ms each); below 1.0, run the threat answers or the
   panic step before pressing Play.
6. **Refresh.** After a game update run `python tools/export_attacks.py`
   (it decodes the cached `sim_model` itself), then the optimizer; or call
   `export_attacks.run()` from `gamemodel.refresh()` when it re-extracted.

## 7. Next steps

- Misses: a hit chance for straight projectiles from bloon speed x flight
  time (the Logs yellow leak), and overkill between several snipers on the
  same "first" bloon.
- Heroes: hero level by round and its attacks (the export has all 20
  levels); today the hero is free extra safety.
- Slows and freezes (exported, not used) lengthen every later zone's time.
- Re-run `--calibrate` as games come in: the table above is the evidence for
  `SAFETY_MARGIN`.

## Commands

    python tools/export_attacks.py              # data/game_model/attacks.json
    python tools/export_attacks.py --check      # headline numbers of the base towers
    python tools/optimize_builds.py             # all default maps x modes (hours; --nice beside the bot)
    python tools/optimize_builds.py "Dark Path" hard [--target ninja] [--base]
    python tools/optimize_builds.py --maps "Dark Path,Logs"
    python tools/optimize_builds.py --calibrate
    python tools/optimize_builds.py --check strategies/optimized/darkpath_hard.yaml
