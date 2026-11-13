# Beginner maps: map builds and what was learned

Maps: Alpine Run, Candy Falls, Carved, End Of The Road, Frozen Over, Hedge,
Lotus Island, Park Path, Skates, Winter Park. Written October 2026 for the
medals the main account still lacked (Easy, Primary Only and Deflation on
Candy Falls; Primary Only and Deflation on Frozen Over; Medium, Military Only
and Reverse on all ten; Apopalypse on all ten since 2026-11-06, see
"Apopalypse builds").

## The builds

Worst damage-model margin over every round of each mode (2.0 = the defence
would still hold at half strength; see "How the builds were made and checked"
for the three replays). Medium and Military Only share the economy and the
track, so their numbers are equal.

| Build | Modes | Plan replay worst | Sight-strict worst | Executor-faithful, strict (with its extra towers / plan towers only) | Plan + fill |
|---|---|---|---|---|---|
| `alpinerun_medium.yaml` | Medium, Military Only, Reverse | 3.55 | 2.65 (Medium and Military Only); 2.80 (Reverse) | 3.83 / 2.65 (Medium and Military Only); 3.91 / 2.80 (Reverse) | - |
| `candyfalls_deflation.yaml` | Deflation | 2.92 | 2.46 | 4.18 / 4.00 | 5.08 (strict 4.00) |
| `candyfalls_easy.yaml` | Easy, Primary Only | 2.13 | 2.13 | 3.12 / 2.13 (Easy); 2.48 / 2.13 (Primary Only) | 4.51 (strict 4.51) |
| `candyfalls_medium.yaml` | Medium, Military Only, Reverse | 4.09 (Medium and Military Only); 3.67 (Reverse) | 3.29 (Medium and Military Only); 3.51 (Reverse) | 3.47 / 2.57 (Medium and Military Only); 3.83 / 2.86 (Reverse) | - |
| `carved_medium.yaml` | Medium, Military Only, Reverse | 3.63 (Medium and Military Only); 3.51 (Reverse) | 2.99 (Medium and Military Only); 3.12 (Reverse) | 3.12 / 2.35 (Medium and Military Only); 3.67 / 2.28 (Reverse) | - |
| `endoftheroad_medium.yaml` | Medium, Military Only, Reverse | 3.29 (Medium and Military Only); 3.08 (Reverse) | 3.05 (Medium and Military Only); 3.12 (Reverse) | 3.36 / 2.74 (Medium and Military Only); 3.63 / 2.95 (Reverse) | - |
| `frozenover_deflation.yaml` | Deflation | 3.33 | 3.26 | 5.08 / 5.08 | 5.84 (strict 5.08) |
| `frozenover_medium.yaml` | Medium, Military Only, Reverse | 5.19 (Medium and Military Only); 5.02 (Reverse) | 4.65 (Medium and Military Only); 4.51 (Reverse) | 4.65 / 3.19 (Medium and Military Only); 4.51 / 3.91 (Reverse) | - |
| `frozenover_primary_only.yaml` | Primary Only | 2.28 | 2.28 | 2.80 / 2.28 | 3.75 (strict 3.75) |
| `hedge_medium.yaml` | Medium, Military Only, Reverse | 3.55 (Medium and Military Only); 3.59 (Reverse) | 2.71 (Medium and Military Only); 2.74 (Reverse) | 3.75 / 2.71 (Medium and Military Only); 4.27 / 2.74 (Reverse) | - |
| `lotusisland_medium.yaml` | Medium, Military Only, Reverse | 2.99 (Medium and Military Only); 3.22 (Reverse) | 2.62 | 2.86 / 2.28 (Medium and Military Only); 2.89 / 2.33 (Reverse) | - |
| `parkpath_medium.yaml` | Medium, Military Only, Reverse | 2.89 (Medium and Military Only); 2.86 (Reverse) | 2.40 (Medium and Military Only); 2.18 (Reverse) | 3.67 / 2.20 (Medium and Military Only); 3.63 / 2.18 (Reverse) | - |
| `skates_medium.yaml` | Medium, Military Only, Reverse | 3.40 (Medium and Military Only); 3.36 (Reverse) | 2.77 (Medium and Military Only); 2.71 (Reverse) | 3.12 / 1.81 (Medium and Military Only); 2.92 / 1.85 (Reverse) | - |
| `winterpark_medium.yaml` | Medium, Military Only, Reverse | 2.95 | 2.71 (Medium and Military Only); 2.92 (Reverse) | 3.71 / 2.46 (Medium and Military Only); 3.79 / 2.54 (Reverse) | - |

## CHIMPS builds (2026-11-05)

Written for the owner's order of 2026-11-05: black borders map tier by tier,
Beginner maps first. Sixteen of the 26 Beginner maps had their black border
(checked on the game's map pages); the ten below lacked CHIMPS. A general
build stays under the planner's CHIMPS bar (0.80) until it has CHIMPS games
of its own, so only a build made for the map can be played there untested.

Each file was checked like the builds above, on the CHIMPS economy (round 6
with $650, no income towers - the end-of-round bonus is still paid - no
selling, no boosts), rounds 6-100. The gate
(`base_success.chimps`) is 0.85 only where every replay stays at 2.0 or
more; otherwise 0.5, and the planner does not play it.

Re-checked 2026-11-05 after Frozen Over CHIMPS was lost at round 56 (40 camo
rainbows; the model had rated the round 16), on the corrected damage model:
a support buff reaches a tower only when its centre is inside the buff
radius (the tower's footprint was added before: the Radar Scanner stood
49.3 units from an Aircraft Carrier, radius 48), and Aircraft Carrier /
Carrier Flagship planes count at a circling plane's share of the track
instead of full rate on the whole map. A fifth replay was added: **drift**,
every tower 5 world units further from its villages and alchemists (plan
replay and sight-strict, the worse taken), so a spot the game shifts a
little cannot take a buff away. Worst margin over rounds 6-100 (round):

| Build | Core | Plan | Sight-strict | Executor-faithful (extra / plan only) | Drift | Gate |
|---|---|---|---|---|---|---|
| `alpinerun_chimps.yaml` | tack to Inferno Ring, Spiked Mines, Druid of the Jungle, Cripple MOAB, MIB | 2.16 (R9) | 2.16 (R9) | 2.16 / 2.16 (R9) | 2.04 (R9) | 0.85 (opening steps just in time; no lead asked before round 16) |
| `candyfalls_chimps.yaml` | two buccaneers to Carrier Flagship + Aircraft Carrier, MIB | 2.18 (R95) | 2.18 (R95) | 2.23 / 2.18 (R95) | 2.18 (R95) | 0.85 |
| `carved_chimps.yaml` | buccaneers in the eyes to Carrier Flagship + two Carriers, MOAB Mauler; repaired: village below the right eye with Bigger Radius, lead-dip alchemist by the left eye; ace moved off a refused spot, Destroyer before the ace | 2.16 (R9) | 2.16 (R9) | 2.16 / 2.16 (R9) | 2.07 (R34) | 0.85 |
| `endoftheroad_chimps.yaml` | pool buccaneers to Destroyers and Carriers, Deadly Precision sniper; repaired: village 15 units lower, Carrier Flagship and a fifth Carrier | 2.11 (R15) | 2.11 (R15) | 2.18 / 2.18 (R15) | 2.09 (R95) | 0.5 (Double Shot, Destroyer and b3 bought one round before the rounds that need them) |
| `frozenover_chimps.yaml` | Ring of Fire tack, Maim MOAB sniper, two Carriers, MIB | 1.01 (R95) | 0.99 (R95) | 1.14 / 1.13 (R95) | 1.00 (R95) | 0.5 (fails R95, R98, R99; no village spot puts b2 or the sub inside the MIB) |
| `hedge_chimps.yaml` | tacks, Apache helis, Phoenix wizard | 0.52 (R95) | 0.52 | 0.22 / 0.19 | - | 0.5 (fails R90-99; not re-checked) |
| `lotusisland_chimps.yaml` | three Carriers (one to Flagship), Cripple MOAB sniper, MIB; repaired: west carrier moved inside the MIB and made the Flagship; MIB, b1 and alchemist moved off refused spots | 2.09 (R8) | 2.09 (R8) | 2.09 / 2.09 (R8) | 2.04 (R8) | 0.85 (opening steps just in time; no lead asked before round 16) |
| `parkpath_chimps.yaml` | pond Flagship + stream Carrier, Maim MOAB snipers, Perma-Spike; repaired: pond boat and alchemist moved inside the buffs, third pond Carrier | 2.07 (R8) | 2.02 (R55) | 2.07 / 2.07 (R8) | 2.04 (R55) | 0.85 |
| `skates_chimps.yaml` | tack to Inferno Ring, two Carriers, subs, dipped ninja | 1.51 (R94) | 1.41 (R98) | 1.41 / 1.41 (R98) | 0.06 (R95) | 0.5 (fails R94-98; drift R59-100) |
| `winterpark_chimps.yaml` | three fountain Carriers, MOAB Eliminator, MIB; repaired: early Hot Shot on the third ship | 2.09 (R98) | 2.09 (R98) | 2.20 / 2.20 (R95) | 2.07 (R98) | 0.85 |

**Rewritten 2026-11-07** (the table above is history for four of them):
Carved, Winter Park, Alpine Run and Lotus Island CHIMPS passed these checks
and still lost live (Winter Park and Alpine Run at round 6, Carved at round 33
twice, Lotus Island at round 95), while Cracked CHIMPS was won with a build
that follows a published guide and sets `plan_first`. The four now follow
bloon.games' written guides the same way (their own map pages hold only a
video, so Carved, Winter Park and Lotus Island use the Cracked/Spa Pits
Flagship recipe and Alpine Run the Monkey Meadow boomerang recipe; each
file's header has the sources and every change), open with Quincy alone
(`hero_opens`), and are gated at 0.5 to be played live, not on the model.
Executor-faithful replay on the learned map, final plan towers, rounds 95 /
99: Carved 2.51 / 1.96, Winter Park 2.00 / 1.59, Alpine Run 1.83 / 1.70,
Lotus Island 1.23 / 1.35 - against Cracked's winning board at 1.87 / 1.27.

Re-checked again 2026-11-05 after Lotus Island CHIMPS was lost at round 95
(table above: the newer numbers). The live cash was not short - the journal's
income over rounds 7-93 was $141,018 against the replay's $141,322 (pops plus
the end-of-round bonus) - but the game refused four of the build's spots, the
MIB village went to the other end of the map, and round 95 rated 0.36 on the
towers where they stood. The executor-faithful replay now plays on the map's
learned refusals (`simulate_threats.map_model(learned=True)`; CashGame refuses
the same clicks) and rates the towers where they really stand, and the
executor tries the cells round a refused `at` before any spot chosen by role
(`Executor._at_spots`). A build gets 0.85 only where every replay is at 2.0 or
more AND, from round 16 on, every plan step stands at least two rounds before
the first round the build without it fails. The $650 opening (rounds 6-15)
leaves no spare round for anyone, so there the margins alone decide. Alpine
Run and Lotus Island miss the lead only in the opening and are gated 0.85;
End Of The Road also misses it at round 38 and stays at 0.5.

Before the correction every build but Hedge had passed at 2.11-3.08; the
spot and step changes, and why the two held builds could not be repaired
within their budget, are in each file's header.

Skates (Impoppable) and Lotus Island (Medium sub-modes, Impoppable) still
lack a medal CHIMPS needs first; the medal sweep had recorded both as earned.

What every build had to work around:

* **The blimp check starved the plan.** `counters.json` `blimp_dps` gives
  villages and alchemists no credit, rates a 4-2-0 buccaneer like 4-0-0 and
  counts Carrier planes as short range, so the executor's ramp check called
  rounds 75-99 short where the damage model gave 16 and bought loose towers
  until the plan's last big step was never afforded. The builds point their
  `answers` for the blimp classes at their own plan steps, and since
  2026-11-05 the check gives way where the damage model rates the round at
  2.0 or more (`Executor._model_holds`). Alpine Run was validated with the
  answers off (`no_answers`), before that change.
* **`strategy.ANSWERS` lists no buccaneer** for ceramic, BFB, ZOMG, DDT, BAD
  or rush (MOAB only as Monkey Pirates 2-4-0). Without `answers` of its own
  the executor forced 2-4-0 on a planned 3-2-0 boat, and `coverage()`
  (`runner.py` drops a mode that fails it) needs a listed rush and BAD tower.
* **Round 9 caps the early margin near 2.2** on $650 + income.

## Apopalypse builds (2026-11-06)

Written for the owner's first goal, a black border on every Beginner map: on
2026-11-06 the map cards showed the ten Beginner maps without one all lack
Apopalypse (the earlier "Apopalypse medals" were misreads). The bot had never
won the mode: the general `apopalypse_ninja_sniper` lost Polyphemus
(2026-10-27, round 52) and Infernal (2026-11-05, round 45).

**How the mode works** (sources: the game's own data and code, read through
the cached Cpp2IL dump; bloonswiki Apopalypse_(BTD6) and
Strategy:Apopalypse_(BTD6); bloons.fandom.com Apopalypse_(BTD6)):

* Medium difficulty (150 lives, Medium prices), won by popping everything of
  rounds 1-60 (the Apopalypse Mod's EndRound; round 100 is the Survivor
  achievement, in freeplay). With Fast Track the account's games start at
  round 15, as Medium's (the bot's logs).
* No pause between rounds, Auto Start or not: the next round starts spawning
  the moment the last one has spawned its last bloon. Each round pays its pops
  (Medium cash per pop: 1.0 to round 50, 0.5 to 60) and, since v41, the
  end-of-round bonus once it is fully popped.
* Rounds are random (FreeplayRoundManager, the same generator freeplay uses
  from round 141): each round shuffles the 529 freeplay groups (each a bloon,
  a count, a spawn time and the rounds it may appear on), draws a budget -
  a formula of the round times 0.5-1.5 - and takes every group in turn that
  is allowed on the round and whose score (lives it costs, +10% camo, +10%
  regrow, a factor for how tightly it is packed) still fits; the groups run
  end to end. `btd6bot/apopalypse.py` rebuilds it; the pool is exported from
  the game's sim_model (`data/game_model/freeplay_groups.json`). Checked
  against the wiki pages: the 15 tight ceramics only fit round 48 (0.079% of
  games, the fandom page says 0.076%), a game averages 41.5 MOABs (41.5), and
  rounds 1-60 pay $35,200-49,500 over 1,500 drawn games (the page: $36,859 to
  $46,919 at the extremes).
* What that means against Medium's rounds: camo from round 19, lead 20,
  ceramics 33 (groups of 7-20, some camo or regrow), 40 fortified leads and
  fortified ceramics from the late 30s, MOABs from 41 (groups of 5-7),
  fortified MOABs 46, a BFB from 54 - and much less cash: a poor game (the
  poorest 10%) pays $39,300 over rounds 1-60, the median $41,800, Medium
  $54,500.

**The check** (`tools/apopalypse_check.py`, test
`tests/test_apopalypse_offline.py`): the build is played the executor's way
on the live map model's refused spots (Fast Track round 15 with $6,057, Double
Cash, a poor game's income each round) and the towers standing at each round
are rated, strict model, against windows of two rounds laid end to end (the
continuous spawn: round r + 1 arrives on round r's leftovers): the worst ones
the game can send - the largest budget, the hardest groups first, for two
meanings of hardest (the group this board does worst against alone; the most
load per point of budget) - and 24 random ones. Every round 15-60 must rate
2.0 or more, and again with every tower 5 units further from its supporters
(drift). Before this the Medium builds rated (same check, 8 random windows):
Frozen Over 2.16, Alpine Run 1.92, Hedge 1.59, Winter Park 1.53, Park Path
1.37, Carved 1.33, Lotus Island 0.69, Skates 0.71, Candy Falls 0.63, End Of
The Road 0.55 - the openings against 40 tight pinks, the ceramic groups of
rounds 33-36 and the fortified leads of 38-43.

**What the builds changed** (each file's header has its reasons):

* the first Destroyer (3-0-2, $5,000) is bought with the Fast Track cash. A
  single tier of $2,500 or more is hardly ever bought later in the replay:
  the surplus spending takes the cash above $800 every round (gap 1 below),
  and Apopalypse pays too little to outrun it;
* an alchemist's Acidic Mixture Dip (2-0-0) by the main towers gives them
  lead and more ceramic and MOAB damage, instead of a second boat's Hot Shot
  (the wiki has Airburst Darts cover lead with it); Berserker Brew is left
  out (the model does not count it, and the replay would spend $1,400 on it);
* a Druid of the Jungle (1-3-0, $2,400 in cheap tiers) on Carved, End Of The
  Road, Frozen Over, Hedge, Lotus Island and Park Path - the cheapest lift for
  the ceramic rounds the model found (Hedge 1.87 -> 4.27 at round 35);
* Bomber Aces (all tiers under $1,000) instead of Neva-Miss and of steps the
  surplus spending starves; a Really Big Bombs shooter on Lotus Island for
  the round-60 MOABs.

| Build | Core | Worst (round) | Drift (round) | Plan bought | Gate |
|---|---|---|---|---|---|
| `alpinerun_apopalypse.yaml` | Bomber Aces over the zig-zags with an Acidic Mixture Dip alchemist among them, Maim MOAB snipers in the bottom-left corner | 2.30 (R35) | 2.30 (R35) | 22/22 | 0.85 |
| `candyfalls_apopalypse.yaml` | a Destroyer at the river's upper bend with an alchemist beside it, Airburst subs, Bomber Aces, Maim MOAB snipers on the right-hand lawn | 2.68 (R35) | 2.68 (R35) | 18/20 | 0.85 |
| `carved_apopalypse.yaml` | a Destroyer in the right eye with an alchemist and a Druid of the Jungle by it, Airburst subs, two Bomber Aces above the mouth, Maim MOAB snipers | 2.80 (R53) | 2.62 (R56) | 22/22 | 0.85 |
| `endoftheroad_apopalypse.yaml` | a Destroyer in the pool with an alchemist and a Druid of the Jungle by the road, Airburst subs, two Bomber Aces, Maim MOAB snipers | 2.28 (R60) | 2.09 (R60) | 22/22 | 0.85 |
| `frozenover_apopalypse.yaml` | the Medium build's two Destroyers in the central pond, Armor Piercing sub and Maim MOAB snipers, with a Druid of the Jungle at the start | 2.57 (R35) | 2.43 (R60) | 22/22 | 0.85 |
| `hedge_apopalypse.yaml` | six Bomber Aces over the hedges with an Acidic Mixture Dip alchemist among three of them, a Druid of the Jungle on the right, Maim MOAB snipers on the bottom strip | 2.18 (R15) | 2.18 (R15) | 23/23 | 0.85 |
| `lotusisland_apopalypse.yaml` | a Destroyer in the southern bay with an alchemist and a Druid of the Jungle on the shore, Airburst subs, two Bomber Aces, a Really Big Bombs shooter, a second Destroyer at the entrance, a Maim MOAB sniper | 2.43 (R35) | 2.40 (R35) | 21/21 | 0.85 |
| `parkpath_apopalypse.yaml` | a Destroyer in the central pond with an alchemist and a Druid of the Jungle beside it, an Airburst sub up the stream, two Bomber Aces, Maim MOAB snipers on the lower-right lawn | 2.71 (R60) | 2.77 (R60) | 22/22 | 0.85 |
| `skates_apopalypse.yaml` | a Destroyer in the central crack with an alchemist beside it, Airburst subs, Bomber Aces, Maim MOAB snipers on the left edge | 2.51 (R47) | 2.51 (R47) | 18/20 | 0.85 |
| `winterpark_apopalypse.yaml` | two Destroyers at the fountain with an alchemist between them, two Bomber Aces, Maim MOAB snipers on the left edge | 2.46 (R33) | 2.40 (R33) | 17/17 | 0.85 |

The gate (`base_success.apopalypse`) is 0.85 where every round passes both
replays, else 0.5. **Planner calibration:** `planner._Calibration` is per
build: the general build's two losses give it a factor of 0.44 on Beginner
maps (p 0.35), but a map build has no games and keeps 1.0 - unless it sets
`xp_target`, which `build_family` counts as one of the generated "solo"
builds, whose Medium-family record (0.87) then caps it. So a map build gated
0.85 plans at p 0.91-0.92 (no `xp_target`) or 0.79 (`xp_target: sub`), both over
the 0.75 bar; no planner change was needed.

## How the builds were made and checked

1. **Map analysis from the game's own data.** Routes, scenarios and
   untouchable stretches from `btd6bot/dps_model.py` `Track`; areas, water,
   sight blockers and removables from `data/map_geometry/<id>.json`
   (`btd6bot/mapgeom.py`) and `data/map_mechanics.json`; legal cells from
   `placement.valid_spots`; reach from `Track.zones` (line of sight counted
   where the tower needs it). All ten maps have a single route and a single
   scenario (no alternating or simultaneous lanes).
2. **Community research.** bloonswiki pages of each map (Layout, Strategy,
   Recommended towers), read through the wiki's MediaWiki API, and the
   wiki's mode strategy pages (Strategy:Military_Only, Strategy:Primary_Only,
   Strategy:Deflation_(BTD6), Reverse_(BTD6)) and tower pages (Bomber Ace,
   Crossbow, Desperado). The web-search budget of the session ran out before
   video guides could be searched, so the community input is the wiki's. For
   the beginner maps the wiki's advice is consistent: Destroyers (Buccaneer
   3-x-x) wherever there is water surrounded by track, Carrier Flagship on
   Lotus Island and Skates, and global or flying towers where sight is
   blocked (Hedge).
3. **Spots and order.** Each spot was chosen with the map geometry: the
   covered route length within the tower's range (line of sight counted), on
   cells that are legal on the **live** map model (`data/maps/<map>.npz`,
   which adds the cells the game refused in earlier play) and outside the top
   HUD band (fy < 0.13, or fx > 0.68 and fy < 0.17). Finite-range damage
   towers stand where they reach at least ~40% of the track the best legal
   spot reaches on the executor's own screen grid (`Executor._reach`), so
   `sell_useless` (below 25%) never sells them. `tools/optimize_builds.py`
   was run from a scratch script (nothing written to `strategies/optimized/`)
   only to see which towers the model favours.
4. **Validation of every file**, in the account's scenario (Fast Track +
   Double Cash: `optimize_builds.economy(mode, boosts)`; Medium family starts
   at round 15 with $6,057, Easy at round 10 with $3,832, Deflation at round
   31 with $40,000):
   * `strategy.load_all()`: bot_ready True, `validate()` empty;
   * the plan replayed the way the executor buys (`optimize_builds.
     replay_plan`: in order, each step as soon as the cash allows) and
     `dps_model.round_margin` on every round: worst margin at least 2.0;
   * the same replay **sight-strict**: the stock model gives map-wide towers
     the whole track whatever blocks their sight, gives Advanced Intel subs
     the whole map and lets an ace's pineapples and bombs fall anywhere. The
     strict replay limits snipers to the track they can see, subs to their
     own range and aces to their flight circle (range + pattern radius).
     Worst margin at least 2.0 there too;
   * an **executor-faithful** replay: `tools/simulate_threats.simulate`'s
     loop (plan ticks, then the match loop's surplus spending, income, buying
     during the round) on the account's economy, with the damage model run on
     the towers the executor really has at each round start. Surplus spending
     buys extra copies of the main tower when the plan waits for a big step;
     those were put at the best free spot of their kind. This check is what
     ruled out single big purchases (see "Executor and model gaps", 1);
   * `tools/simulate_threats.py simulate(strat, mode, map_name, scenario=...)`
     on the account's economy and on the base economy the offline test uses:
     no gaps; `strategy.coverage()` and `usable()` on a full and on the real
     account: nothing missing;
   * every `at` legal in plan + fill order (as
     `tests/test_map_hints_offline.py` checks) and on the live model;
   * `tests/test_map_hints_offline.py` and
     `tests/test_achievement_strats_offline.py` (results at the end).
5. **Buccaneer model fix.** `dps_model` counted the buccaneer's Grape Shot and
   cannon secondaries at a readiness-check rate until `_trigger_rates` was
   added (2026-10-22 20:47). Every build here was validated again after the
   fix, from scratch; the numbers on this page are all post-fix. The fix
   lowered the Destroyer builds' worst margins by roughly 0.04 to 0.8 (End Of
   The Road the most: plan replay 4.09 before, 3.29 after; the first sniper
   also moved to the front of the plans at the same time); none fell below
   2.0 and none had to be dropped.
6. **Easy family (Easy, Primary Only, Deflation).** The offline test's threat
   simulation runs the base economy (no boosts; Deflation on $20,000) and
   requires the whole `plan` to be bought. So in those files `plan` is the
   core the base economy affords, and the extra the account's Double Cash
   pays for (Twin Sixes on Easy; the second $20,000 in Deflation) is `fill`.
   The margins quoted are for the plan alone unless the text says "plan +
   fill".
7. **Surplus cash and XP.** On the water maps `xp_target: sub` sends the
   executor's surplus spending into more subs (the account still needs Monkey
   Sub XP: weight 0.56 in `optimize_builds.xp_weights`), with a fill step
   `{do: upgrade, kind: sub, to: 2-0-4}` that caps those extra subs at Armor
   Piercing Darts. On the Easy-family builds the target is the Desperado
   (weight 1.0, the account's most wanted tower XP). On land maps the extra
   copies are aces, capped at Bomber Ace (2-3-0).

## The maps

Route lengths are world units (hittable part in brackets: off-screen and
tunnel stretches cannot be hit). "Sniper sight" is the largest share of the
route a sniper sees from any legal spot (`Track.zones` with
`MapSetup.sight`). Land and water are shares of the placement grid.

### Alpine Run

* **Mechanics.** One route, 1,389 (933): four zig-zags down the left, the
  ski-lift lane up the middle, three zig-zags down the right; the top 17%
  runs off screen. Land 69%, no water, no sight blockers (sniper sight 100%),
  no removables or map events. The best range spot (an ace circle at
  (0.37, 0.69)) reaches only 36% of the route.
* **Sources.** bloonswiki Alpine_Run ("above-average in terms of difficulty
  ... due to its dispersed track layout"; no line-of-sight blockers);
  Strategy:Military_Only; Bomber_Ace_(BTD6); Strategy:Deflation_(BTD6)
  (Neva-Miss aces).
* **Build.** `alpinerun_medium.yaml` (Medium, Military Only, Reverse): five
  aces (four Bomber Aces, one Neva-Miss) spread over the zig-zags, three
  snipers (two Maim MOAB, one Full Auto Rifle with Night Vision) in the
  bottom-left corner, Quincy. Worst margin: plan replay 3.55; sight-strict
  2.65 (Medium and Military Only); 2.80 (Reverse); executor-faithful, strict
  (with its extra towers / plan towers only) 3.83 / 2.65 (Medium and Military
  Only); 3.91 / 2.80 (Reverse).
* **Note.** The model's favourite here is a Spectre (Ace 2-0-4): with it the
  replay reached 3.5 (standard) and 2.4 (strict), but the executor-faithful
  replay showed it is never bought (see gaps, 1); the plan now buys only
  steps of a few thousand dollars.

### Candy Falls

* **Mechanics.** One very long route, 1,406 (1,290), snaking across a
  vertical chocolate river (water, 10% of the map), with small loops at the
  top left and bottom right. Sight blockers 8% (candy house, watermill), but
  snipers on the right-hand lawn see 100%. A buccaneer at the river's upper
  bend reaches 28% of the route, at the lower bend 27%; subs 16-17%. No
  removables. No logged game on this map yet.
* **Sources.** bloonswiki Candy_Falls (one of the easiest maps; Destroyer
  recommended: both broadsides fire; Brickell); Strategy:Military_Only;
  Strategy:Primary_Only; Crossbow_(BTD6); Desperado_(BTD6);
  Strategy:Deflation_(BTD6).
* **Builds.**
  * `candyfalls_easy.yaml` (Easy, Primary Only): two Tack Sprayers, three
    Desperados (3-2-0; Twin Sixes in fill), two bombs (MOAB Mauler, Cluster
    Bombs), a Crossbow, Quincy. Worst margin: plan replay 2.13; plan + fill
    4.51; executor-faithful (with its extra towers / plan towers only) 3.12 /
    2.13 (Easy); 2.48 / 2.13 (Primary Only).
  * `candyfalls_deflation.yaml`: two Destroyers (3-0-2, 3-2-0), MOAB
    Assassin, Bomber Ace, 2-2-0 sniper, Brickell; fill adds two Armor
    Piercing subs, an ace and a sniper with the second $20,000.
    Worst margin: plan alone 2.92 (sight-strict 2.46); plan + fill 5.08.
  * `candyfalls_medium.yaml` (Medium, Military Only, Reverse): the water
    template (below). Worst margin: plan replay 4.09 (Medium and Military
    Only); 3.67 (Reverse); sight-strict 3.29 (Medium and Military Only); 3.51
    (Reverse); executor-faithful, strict (with its extra towers / plan towers
    only) 3.47 / 2.57 (Medium and Military Only); 3.83 / 2.86 (Reverse).
* **Note.** The bottom-right loop's inside, the best tack spot on the
  geometry, is blocked on the live model by refused cells; the tack went to
  the first S-bend instead.

### Carved

* **Mechanics.** One route, 1,312 (1,187): round the jack-o-lantern's
  outline, into the mouth's zig-zag loop and out at the top. Water: the two
  eyes and the cauldron (4%); a buccaneer in the right eye reaches 31% of the
  route, in the left eye 27%. The wiki says two trees by the entrance and
  exit block sight; the map file marks no sight blockers (model gap 5). The
  live model refuses the ground just below the mouth (the wiki's best
  tack/glaive spot), so the aces stand above the mouth.
* **Sources.** bloonswiki Carved (best spots: the right water patch, right
  below it, below the mouth); Strategy:Military_Only.
* **Build.** `carved_medium.yaml`: the water template. Worst margin: plan
  replay 3.63 (Medium and Military Only); 3.51 (Reverse); sight-strict 2.99
  (Medium and Military Only); 3.12 (Reverse); executor-faithful, strict (with
  its extra towers / plan towers only) 3.12 / 2.35 (Medium and Military Only);
  3.67 / 2.28 (Reverse).

### End Of The Road

* **Mechanics.** The shortest beginner map, 994 (818). Bloons go out along
  the top lane of the road, loop round the pool at the far right and come
  back along the bottom lane, so every spot near the road sees both lanes.
  The pool (4%) is the key: a buccaneer there reaches 50% of the route, a sub
  40%. Land 82%, cacti block almost nothing. No removables.
* **Sources.** bloonswiki End_Of_The_Road (Destroyers in the pool, both
  broadsides; Brickell; camo from elsewhere); Strategy:Military_Only.
* **Build.** `endoftheroad_medium.yaml`: the water template (no second
  ace). Worst margin: plan replay 3.29 (Medium and Military Only); 3.08
  (Reverse); sight-strict 3.05 (Medium and Military Only); 3.12 (Reverse);
  executor-faithful, strict (with its extra towers / plan towers only) 3.36 /
  2.74 (Medium and Military Only); 3.63 / 2.95 (Reverse).

### Frozen Over

* **Mechanics.** One long route, 1,503 (1,087; the first 15% off screen)
  that crosses itself in figure-eights. The small central pond sits inside
  the crossings: a buccaneer there reaches 52% of the route, a sub 34% - it
  holds two buccaneers and one sub. Big pond on the left (Brickell), small
  ones at the bottom. The cliff at the top blocks sight (9%) but snipers in
  the bottom-right corner see 100%. The live model has 630 refused land cells
  in scattered 3x3 blocks all over the ice (gap 6); several spots had to
  move off their best cells. The only logged game, Easy with solo_ice, was
  won.
* **Sources.** bloonswiki Frozen_Over (one of the easiest maps, many loops,
  Overdrive and Glaive Lord); Strategy:Primary_Only; Crossbow_(BTD6);
  Strategy:Deflation_(BTD6); Strategy:Military_Only.
* **Builds.**
  * `frozenover_primary_only.yaml`: one Tack Sprayer, three Desperados
    (Twin Sixes in fill), three Crossbows, two bombs (MOAB Mauler, Cluster
    Bombs), Quincy. Tack spots near the crossings are refused on the live
    model, so Crossbows took their place.
    Worst margin: plan replay 2.28; plan + fill 3.75; executor-faithful (with
    its extra towers / plan towers only) 2.80 / 2.28.
  * `frozenover_deflation.yaml`: two Destroyers in the central pond, MOAB
    Assassin, Bomber Ace, 2-2-0 sniper, Brickell; fill: an Armor Piercing
    sub, two aces, a sniper. Worst margin: plan alone 3.33 (sight-strict
    3.26); plan + fill 5.84.
  * `frozenover_medium.yaml`: the water template. Worst margin: plan replay
    5.19 (Medium and Military Only); 5.02 (Reverse); sight-strict 4.65 (Medium
    and Military Only); 4.51 (Reverse); executor-faithful, strict (with its
    extra towers / plan towers only) 4.65 / 3.19 (Medium and Military Only);
    4.51 / 3.91 (Reverse).

### Hedge

* **Mechanics.** One route, 1,538 (1,196), meandering up and down between
  three hedges. The hedges block sight on 21% of the map's cells: no sniper
  sees more than 64% of the route (best on the bottom strip), and range
  towers between the lanes see one or two lanes. No water, no removables (the
  statue only turns when clicked).
* **Sources.** bloonswiki Hedge (hedges are line-of-sight blockers; among the
  hardest beginner maps; Comanche Commander, Prince of Darkness, Archmage,
  Ultra-Juggernaut recommended); Strategy:Military_Only; Bomber_Ace_(BTD6).
* **Build.** `hedge_medium.yaml`: five aces (four Bomber Aces, one Neva-Miss)
  that fly over the hedges, three snipers on the bottom strip, Quincy.
  Worst margin: plan replay 3.55 (Medium and Military Only); 3.59 (Reverse);
  sight-strict 2.71 (Medium and Military Only); 2.74 (Reverse);
  executor-faithful, strict (with its extra towers / plan towers only) 3.75 /
  2.71 (Medium and Military Only); 4.27 / 2.74 (Reverse).
* **Note.** The wiki's military pick, Comanche Commander, needs a Heli Pilot
  in Pursuit (gap 2).

### Lotus Island

* **Mechanics.** A short, spread-out route, 1,107 (1,000), round an island
  in open water (38% of the map). The lotus plants and the stone podium block
  sight (6%): the best sniper spot (south shore) sees 79% of the route, most
  spots 60%. The southern bay inside the bottom loop is the best water (a
  buccaneer 30%), then the bottom right (the entrance, 29%) and the top right
  (the exit, 20%). The five lotus pods stun bloons when clicked (a map event
  the bot does not use; not needed).
* **Sources.** bloonswiki Lotus_Island (2nd hardest beginner map; water
  strategies stand out; Carrier Flagship); Strategy:Military_Only.
* **Build.** `lotusisland_medium.yaml`: the water template with a third
  Destroyer on the exit stretch instead of the second ace. Worst margin: plan
  replay 2.99 (Medium and Military Only); 3.22 (Reverse); sight-strict 2.62;
  executor-faithful, strict (with its extra towers / plan towers only) 2.86 /
  2.28 (Medium and Military Only); 2.89 / 2.33 (Reverse).
* **Note.** The wiki says towers on the stone podium are not blocked by
  sight; the model marks the podium as an unplaceable sight blocker (gap 5).

### Park Path

* **Mechanics.** A short route, 667 (586), that coils round the central pond:
  a buccaneer there reaches 78% of the route, the best spot of any beginner
  map. Water is scarce: the pond takes one boat, the stream above it two
  more water towers. Trees block sight (9%) but snipers on the lower-right
  lawn see 100%.
* **Sources.** bloonswiki Park_Path_(BTD6) (Destroyer in the central water,
  both broadsides; 3-2-0 with camo from elsewhere); Strategy:Military_Only.
* **Build.** `parkpath_medium.yaml`: the water template with one ace and no
  sub `xp_target` (no water left for extra subs). Worst margin: plan replay
  2.89 (Medium and Military Only); 2.86 (Reverse); sight-strict 2.40 (Medium
  and Military Only); 2.18 (Reverse); executor-faithful, strict (with its
  extra towers / plan towers only) 3.67 / 2.20 (Medium and Military Only);
  3.63 / 2.18 (Reverse).

### Skates

* **Mechanics.** One route, 1,247 (1,172), with three loops; the middle loop
  runs round the big central ice crack (water 11%), where a buccaneer reaches
  32% of the route. The houses on the right (over a second, small crack) and
  the snowy trees block sight (22%), yet snipers on the left edge see 94%.
  The houses are a removable ($500, frees the small crack); the bot never
  buys removables and the build does not need it.
* **Sources.** bloonswiki Skates (global-range towers stand out; Carrier
  Flagship; Destroyers in the central crack); Strategy:Military_Only.
* **Build.** `skates_medium.yaml`: the water template. Worst margin: plan
  replay 3.40 (Medium and Military Only); 3.36 (Reverse); sight-strict 2.77
  (Medium and Military Only); 2.71 (Reverse); executor-faithful, strict (with
  its extra towers / plan towers only) 3.12 / 1.81 (Medium and Military Only);
  2.92 / 1.85 (Reverse).

### Winter Park

* **Mechanics.** One route, 1,228 (1,071), with one square loop in each
  quarter of the map round a small central fountain (2% water) that takes two
  buccaneers, each reaching a third of the route. No room for subs. The edge
  barrier barely blocks sight (snipers on the left edge see 100%).
* **Sources.** bloonswiki Winter_Park (buccaneers at the leftmost or
  rightmost point of the fountain cover four sections; Destroyer 3-2-0 with
  camo); Strategy:Military_Only.
* **Build.** `winterpark_medium.yaml`: two Destroyers, two Bomber Aces, two
  Maim MOAB snipers, Quincy. Worst margin: plan replay 2.95; sight-strict 2.71
  (Medium and Military Only); 2.92 (Reverse); executor-faithful, strict (with
  its extra towers / plan towers only) 3.71 / 2.46 (Medium and Military Only);
  3.79 / 2.54 (Reverse).

### The water template (Medium, Military Only, Reverse)

Seven of the Medium-family builds (all but Alpine Run, Hedge and Winter Park)
share one shape, from the wiki's Military
Only advice and the map geometry: a 1-2-0 sniper first (camo + lead +
shrapnel; a cheap first tower also stops the executor adding its $200 dart
opener), a buccaneer at the best water spot to 2-0-2 then Destroyer 3-0-2
(camo), Admiral Brickell in the water (Quincy where water is scarce), a
second buccaneer to 2-2-0 then Destroyer 3-2-0 (lead), a Bomber Ace 2-3-0
(camo and lead bombs), an Armor Piercing sub 2-0-4, a second sniper, then
both snipers to Maim MOAB 4-2-0 (the MOAB answer and the round-60 BFB
answer `strategy.coverage` asks for). Military towers only, so one file
serves Medium, Military Only and Reverse; Reverse was validated on the
reversed track (`Track(reverse=True)`, rounds in reverse order). Heli Pilots
were left out (gap 2), and Mortar and Dartling as aimed by hand. A rebuild
leaves out only the Mortar: the executor now sets a Heli's Lock in Place and
then Pursuit, and the Dartling is rated by the damage model like any tower
(docs/tower_exclusions_audit.md item 2).

## Executor and model gaps found (no code was changed)

1. **Surplus spending starves big single purchases.** While a plan step
   waits for cash, the match loop calls `Executor.surplus()` after 3 s (12 s
   when "saving"): it buys the next tier of a placed tower within its planned
   crosspath, else places another copy of the main tower (`_main_kind`, or
   `xp_target`) - and those copies have no cap unless a kind-level step
   gives one. A step costing several rounds of income is therefore never
   bought: the offline replay of `simulate_threats`' loop never reached a
   $23,400 Spectre on Alpine Run or Hedge (eight extra 4-2-0 aces instead),
   and on Easy the $4,930 Twin Sixes arrived only at round 40. The builds
   avoid such steps (or put them in `fill`) and cap copies with a
   kind-level fill step. A fix in code: let `surplus()` hold back cash for
   the waiting plan step when the income of the next one or two rounds
   covers it.
2. **Heli Pilot targeting.** `TARGET_MODES` cycles first/last/close/strong;
   a Heli Pilot starts in Follow Touch (it follows the mouse) and needs
   Pursuit (2-x-x) set from its panel. The damage model already treats helis
   as pursuing. Until `{do: target, mode: pursuit}` exists, no build here
   uses helis - which leaves out the wiki's pick for Hedge (Comanche
   Commander).
3. **Line of sight of map-wide towers is not modelled.** `dps_model.
   station_for` passes `sight` only to finite-range towers, so a sniper is
   rated on the whole route even on Hedge, where no spot sees more than 64%
   of it (Lotus Island 79%, Skates 94%). Advanced Intel subs (2-x-x) are
   modelled map-wide, and an ace's pineapples and Bomber Ace bombs
   (`placement: global` sources) fall anywhere on the route. The "strict"
   replay used for these builds (scratch wrapper, not in the repo) limits
   them to what they see, their own range and their flight circle; worth
   adding to `dps_model` as an option.
4. **The executor's opener.** `Executor._with_opener` reads the mode's
   `start_round` (1 for Medium) and so adds a $200 dart at round 15 of a
   Fast Track game whenever the first placement is not a cheap tower. The
   builds open with a sniper to avoid the wasted placement.
5. **Map-file gaps.** Carved's two trees by the entrance and exit block line
   of sight in the game (wiki) but carry no sight flag in
   `data/map_geometry/carved.json`. On Lotus Island the wiki says towers on
   the stone podium ignore line of sight; the model marks the podium as an
   unplaceable sight blocker. Neither changes these builds.
6. **Refused cells.** The live map models refuse many cells in scattered 3x3
   blocks: Frozen Over 630, Lotus Island 450, Carved and Park Path 360,
   Skates 306 (Candy Falls went from 27 to 117 while this work ran). On
   Frozen Over they cover most of the ground near the crossings, so the
   Primary Only build lost its best tack and Desperado spots (about 0.3 of
   margin). As group B noted for other maps, long runs of refusals look like
   a held-tower problem rather than real map limits; a way to expire such
   refusals would give the builds their best spots back.
7. **Removables and map objects.** Skates' houses ($500, free a small ice
   crack) and Lotus Island's pods (a click stuns bloons) are never used by
   the bot. No build here needs them.
8. **`optimize_builds.lower_priority()` does not lower the priority.** It
   calls `SetPriorityClass` through ctypes without `argtypes`/`restype`, so
   the pseudo-handle of `GetCurrentProcess()` is passed truncated on 64-bit
   Python: measured on this PC, a process stays at NORMAL (0x20) after the
   call. With `wintypes.HANDLE` declared, IDLE (0x40) applies. Every
   optimizer run "beside the bot" has been competing with the game at
   normal priority.
9. **Threat answers in Easy.** Around round 37 the executor's blimp check
   (`blimp_ratio`) still rates these plans short for the round-40 MOAB and
   buys an extra ace or sniper (Easy) or MOAB Mauler (Primary Only) on top of
   the plan's own MOAB Mauler. Harmless (a few hundred dollars), but the
   check could use the damage model's round-40 margin instead.

## Test results

Run on 2026-10-22 with all fourteen files in `strategies/maps/` (and the
other groups' files present at the time):

* `python tests/test_achievement_strats_offline.py`: all passed.
* `python tests/test_map_hints_offline.py`: every test passed except
  `test_map_strategy_spots_are_legal`, which stopped at another group's file
  (`adorastemple_deflation.yaml`: an answer step re-places sniper `s1` at a
  different spot from its plan step) before reaching these files. The same
  check run on these fourteen files alone (the test's own `illegal_spots`,
  in plan + fill order, answers included): all spots legal.
* `test_map_strategies_pass_the_threat_simulation` passed with these files:
  no gaps in any listed mode, and the whole plan of each Easy-family file is
  bought on the base economy.

The scratch tools behind the numbers (validator with the strict and
executor-faithful replays, spot ranking on the live model, the optimizer
wrapper) stayed outside the repo. They ran at idle CPU priority once the
group-wide CPU limit was set; the first runs relied on `lower_priority()`,
which turned out not to work (gap 8).
