# Map builds, group Advanced A

Builds for twelve Advanced maps: Another Brick, Ascent, Cargo, Castle Revenge,
Cornfield, Dark Path, Enchanted Glade, Erosion, Geared, High Finance, Last
Resort and Mesa. They are written for the modes whose medals the main
account still lacks, Easy family first (Easy, Primary Only, Deflation), then
the Medium family (Medium, Military Only, Reverse), then Hard.
Written October 2026; every number below comes from the model as it stands
after the two model fixes of 2026-10-22 (buccaneer secondaries, sniper line
of sight).

## How the builds were made

1. **Map facts from the game's own data.** Routes, scenarios and hidden
   stretches from `btd6bot/dps_model.py` `Track` (built from
   `data/map_geometry`); moving parts, removables and melting ground from
   `data/map_mechanics.json` and `mapgeom`; legal spots from
   `placement.valid_spots` on a `MapModel` filled by `mapgeom.apply`, exactly
   as `tests/test_map_hints_offline.py` checks them; line of sight from the
   model's sight grid.
2. **Community strategies.** The per-map research already in
   `docs/map_strategies.md` (bloonswiki, fandom, guide videos), plus a pass
   for the mode-specific pages (Deflation, Primary Only, Military Only,
   Reverse). Each YAML header cites the sources it used.
3. **Build order from the damage model.** The guides are written for Hard and
   CHIMPS and for players who sell, aim and press abilities. The order and
   spots here were chosen with the repo's optimizer
   (`tools/optimize_builds.py`), run from a scratch wrapper without changing
   any repo file:
   - only towers the guides use on the map, the towers the account needs XP
     for (Desperado, Skywarden, Mermonkey, Ice, Bomb, Sub; their hotkeys are
     verified now) and cheap helpers; never Mortar or Dartling (aimed by
     hand), Heli (its Pursuit targeting cannot be set: `strategy.TARGET_MODES`
     has no "pursuit") or Beast Handler;
   - the mode's tower filter (`strategy.MODE_TOWER_FILTER`);
   - the account's unlocked tiers and its Double Cash + Fast Track economy
     (`optimize_builds.economy(mode, boosts)`);
   - a margin goal above the required 2.0 where the money allows (3.0 for
     Medium, 2.5 for the Easy family), falling back to 2.2 / 2.0;
   - spots kept 4 grid cells apart (the executor blocks a 7x7 box round every
     tower it places, so a closer exact spot would be shifted);
   - on maps whose rounds take alternative lanes (Enchanted Glade, Erosion,
     High Finance, Last Resort) the cheapest map-wide towers are always
     simulated too, and on maps with several routes one plain placement of
     every kind: the optimizer's quick shortlist ranks a tower by its best
     lane and never offered snipers on Erosion (where a single-lane tower
     adds nothing to the worst lane) or Spike Factories on Mesa;
   - ground that lasts the whole game for the mode only
     (`valid_spots(last_round=...)`, for Erosion's melting ice);
   - on Cornfield no cheap filler towers (Skywarden, Mermonkey, Engineer,
     Tack, Ice, Ace, Druid, Spike Factory) and no XP surplus: the free plot
     holds about five towers and fillers left no room for the upgrades.
4. **Spots the executor can use and keeps.** After the optimizer, every
   spot is checked against what `strategy.Executor` does in play, and moved
   to the nearest legal cell that passes (map-wide snipers: the cell among
   the nearest that sees the most track; others: the nearest that keeps 90%
   of the covered track), then the margins are re-checked:
   - not under the top HUD (fy < 0.13, or fx > 0.68 and fy < 0.17): the
     optimizer puts map-wide towers on the least useful cells, which were
     along the top edge;
   - a finite-range damage tower must reach at least 30% of the track the
     best legal cell for its kind reaches (`Executor.sell_useless` sells it
     under 25%);
   - villages and alchemists stand within range of a damage tower and carry
     `near:` (the executor uses a buffer's `at` only when a `near` tower
     stands, and sells a buffer with nothing to buff);
   - never two towers of one kind with tier 5 on the same path (the game
     allows one; none of these builds has two).
   A tower that has no acceptable cell left is dropped and the build
   re-checked without it: three dock towers of Cargo Medium (they covered
   the MOAB lane, which the bot's map grid does not show, so the executor
   would sell them) and one top-pond sub of Another Brick Military Only.
5. **Turned into the strategy format** with exact `at` spots, the hero first
   (the executor adds a $200 opener dart at a spot of its own choosing when a
   plan opens with anything else), answers for every threat the
   `strategy.ANSWERS` table wants (upgrades of the build's own towers where a
   legal crosspath allows, else a cheap tower without a spot), and comments
   saying where each tower stands and how much of the lane it sees.

## How they were checked

For every build and every mode it lists:

- (a) `strategy.validate` and `strategy.readiness` return nothing, and
  `strategy.load_all()` loads it with `bot_ready: True`;
- (b) `dps_model.round_margin` of every round, replaying the purchases the
  way the executor makes them in the account's scenario. "Plan" is the plan
  alone bought in order as cash allows (`optimize_builds.replay_plan`);
  "with fill" adds the fill the way `Executor.tick` buys it: once the plan is
  done, any affordable fill step, scanning in order. Every build kept has
  2.0 or more on every round with its fill; most also have it on the plan
  alone (column "plan");
- (c) `tools/simulate_threats.py simulate()` in the account's scenario and in
  the base one the test uses: no gaps;
- (d) `tests/test_map_hints_offline.py` and
  `tests/test_achievement_strats_offline.py`.

Why some plans need their fill: the offline test plays Easy-family modes on
base income (no Double Cash, no Fast Track) and requires the plan to finish
by round 40 (Deflation: within $20,000). Where the build costs more than a
base game earns, the rest goes to fill, which the bot buys right after the
plan with the account's real income (Deflation: all at once before round 31).

## Summary

| Map | Build file | Modes | Worst round margin: plan / with fill | Hero |
|---|---|---|---|---|
| Another Brick | `strategies/maps/anotherbrick_deflation.yaml` | Deflation | Deflation 2.35 / 2.46 | quincy |
| Another Brick | `strategies/maps/anotherbrick_easy.yaml` | Easy | Easy 2.00 / 2.89 | quincy |
| Another Brick | `strategies/maps/anotherbrick_medium.yaml` | Medium, Reverse | Medium 2.99 / 2.99; Reverse 2.43 / 2.43 | quincy |
| Another Brick | `strategies/maps/anotherbrick_military_only.yaml` | Military Only | Military Only 2.80 / 2.80 | quincy |
| Another Brick | `strategies/maps/anotherbrick_primary_only.yaml` | Primary Only | Primary Only 0.91 / 2.54 | quincy |
| Ascent | `strategies/maps/ascent_easy.yaml` | Easy | Easy 1.26 / 2.54 | obyn |
| Ascent | `strategies/maps/ascent_medium.yaml` | Medium | Medium 2.09 / 2.09 | obyn |
| Ascent | `strategies/maps/ascent_military_only.yaml` | Military Only | Military Only 2.99 / 2.99 | obyn |
| Ascent | `strategies/maps/ascent_primary_only.yaml` | Primary Only | Primary Only 0.91 / 2.04 | obyn |
| Ascent | `strategies/maps/ascent_reverse.yaml` | Reverse | Reverse 2.00 / 2.00 | obyn |
| Cargo | `strategies/maps/cargo_easy.yaml` | Easy | Easy 3.19 / 3.19 (MOAB lane 2.20) | quincy |
| Cargo | `strategies/maps/cargo_medium.yaml` | Medium | Medium 2.71 / 2.71 (MOAB lane 2.71) | quincy |
| Cargo | `strategies/maps/cargo_military_only.yaml` | Military Only | Military Only 3.67 / 3.67 (MOAB lane 3.22) | quincy |
| Castle Revenge | `strategies/maps/castlerevenge_easy.yaml` | Easy | Easy 0.93 / 2.00 | quincy |
| Castle Revenge | `strategies/maps/castlerevenge_medium.yaml` | Medium | Medium 2.16 / 2.16 | quincy |
| Castle Revenge | `strategies/maps/castlerevenge_military_only.yaml` | Military Only | Military Only 2.20 / 2.20 | quincy |
| Cornfield | `strategies/maps/cornfield_deflation.yaml` | Deflation | Deflation 0.23 / 2.99 | quincy |
| Cornfield | `strategies/maps/cornfield_easy.yaml` | Easy | Easy 0.54 / 2.25 | quincy |
| Cornfield | `strategies/maps/cornfield_medium.yaml` | Medium, Reverse | Medium 2.00 / 2.00; Reverse 2.23 / 2.23 | quincy |
| Cornfield | `strategies/maps/cornfield_primary_only.yaml` | Primary Only | Primary Only 1.23 / 2.74 | quincy |
| Dark Path | `strategies/maps/darkpath_deflation.yaml` | Deflation | Deflation 0.24 / 2.38 | quincy |
| Dark Path | `strategies/maps/darkpath_easy.yaml` | Easy | Easy 1.01 / 2.30 | quincy |
| Enchanted Glade | `strategies/maps/enchantedglade_deflation.yaml` | Deflation | Deflation 0.58 / 2.02 | quincy |
| Enchanted Glade | `strategies/maps/enchantedglade_easy.yaml` | Easy | Easy 2.83 / 2.83 | quincy |
| Enchanted Glade | `strategies/maps/enchantedglade_medium.yaml` | Medium | Medium 2.07 / 2.07 | quincy |
| Enchanted Glade | `strategies/maps/enchantedglade_military_only.yaml` | Military Only | Military Only 3.47 / 3.47 | quincy |
| Enchanted Glade | `strategies/maps/enchantedglade_reverse.yaml` | Reverse | Reverse 2.09 / 2.09 | quincy |
| Erosion | `strategies/maps/erosion_easy.yaml` | Easy | Easy 1.13 / 2.51 | psi |
| Erosion | `strategies/maps/erosion_military_only.yaml` | Military Only | Military Only 2.86 / 2.86 | psi |
| Geared | `strategies/maps/geared_deflation.yaml` | Deflation | Deflation 1.48 / 2.04 | quincy |
| Geared | `strategies/maps/geared_easy.yaml` | Easy | Easy 2.51 / 2.51 | quincy |
| Geared | `strategies/maps/geared_medium.yaml` | Medium, Reverse | Medium 3.05 / 3.05; Reverse 3.22 / 3.22 | quincy |
| Geared | `strategies/maps/geared_military_only.yaml` | Military Only | Military Only 3.05 / 3.05 | quincy |
| High Finance | `strategies/maps/highfinance_deflation.yaml` | Deflation | Deflation 1.20 / 4.41 | quincy |
| High Finance | `strategies/maps/highfinance_easy.yaml` | Easy | Easy 2.43 / 2.51 | quincy |
| High Finance | `strategies/maps/highfinance_medium.yaml` | Medium, Reverse | Medium 2.86 / 2.86; Reverse 2.77 / 2.77 | quincy |
| High Finance | `strategies/maps/highfinance_military_only.yaml` | Military Only | Military Only 2.43 / 2.43 | quincy |
| Last Resort | `strategies/maps/lastresort_easy.yaml` | Easy | Easy 2.51 / 2.51 | quincy |
| Last Resort | `strategies/maps/lastresort_medium.yaml` | Medium | Medium 2.20 / 2.20 | quincy |

Not written (details per map below):

- Another Brick, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Ascent, Deflation: best design 1.54 (round 59) with all $40,000 spent; the greedy plan cannot hold rounds 54-59 on both lanes, and aces (the wiki's Neva-Miss answer) rate near zero in the model
- Ascent, Hard: best design 1.41 (round 34), also 1.70 at round 78 and 1.79 at round 59; a longer lookahead did not help
- Ascent, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Cargo, Primary Only: best 1.40 on the repo model and 0.66 once the MOAB-only lane is added: primary towers in reach of that lane cannot hold the round-40 MOAB
- Cargo, Deflation: best 0.86 with the MOAB lane (rounds 52-60)
- Cargo, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Cargo, Reverse: 2.77 on the repo model but 1.78 once the MOAB-only lane is added (round 40 onwards); not written, as the game sends MOABs down that lane (the Medium build of the same design holds 2.71 there but its reverse run did not)
- Castle Revenge, Primary Only: best 0.84: ten routes, short-range primary towers reach one lane each
- Castle Revenge, Deflation: best 1.28
- Castle Revenge, Reverse: best 1.51 (rounds 34 and 49); 1.15 with a longer lookahead
- Castle Revenge, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Castle Revenge, Hard: not written: castlerevenge_hard.yaml (not edited) serves Medium and Hard but fails the 2.0 bar (numbers in the map's section); a second Hard file would break the <map>_<mode> naming, so no new Hard build was attempted
- Cornfield, Military Only: best 1.79: corn blocks the snipers' sight from the plot and aces barely count
- Cornfield, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Dark Path, Primary Only: best 0.92: walls block sight for every primary tower outside the exit pocket
- Dark Path, Medium: best 1.48 (reverse 1.58) after the sniper line-of-sight fix
- Dark Path, Reverse: best 1.58 (see Medium)
- Dark Path, Military Only: best 1.41: snipers need sight, aces barely count, no water
- Dark Path, Hard: not attempted: Medium already fails in the model (the existing darkpath_hard.yaml now lists Medium only)
- Dark Path, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Enchanted Glade, Primary Only: best 1.74 with the fill (2.13 with an older draft whose new-tower answers carried spots the test rejects); no single added tower lifts it
- Enchanted Glade, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Enchanted Glade, Hard: not written: enchantedglade_hard.yaml (not edited) serves Medium and Hard but fails the 2.0 bar (numbers in the map's section); no new Hard build attempted for the same reason
- Erosion, Primary Only: no design at all: the model plays every round on all six lanes and no primary tower is map-wide
- Erosion, Deflation: best 1.51
- Erosion, Medium: best 1.10 (reverse 1.30)
- Erosion, Reverse: best 1.30 (see Medium)
- Erosion, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Geared, Primary Only: no primary tower is map-wide and none fits on a steady cell with track in reach, so nothing can be placed in the model
- Geared, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- High Finance, Primary Only: best 1.53: the park fits about six towers and primary towers there cannot hold both alternating lanes
- High Finance, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Last Resort, Primary Only: best 0.33: the small-loop and straight rounds outrun short-range primary towers
- Last Resort, Deflation: best 1.92 (round 53); no single added tower lifts it to 2.0
- Last Resort, Military Only: best 1.35 (1.27 with a longer lookahead)
- Last Resort, Reverse: best 1.72 (round 60); 1.08 with a longer lookahead
- Last Resort, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Last Resort, Hard: attempted (lastresort_hard.yaml was removed from the repo during this work), stopped unfinished after 20 minutes of CPU at idle priority to free the slot for the final checks
- Mesa, Easy, Primary Only, Deflation, Medium, Military Only, Reverse: the model sees Mesa's bottom lane from no legal spot for towers that need sight (the rock island inside its loop is rated blind); best Easy 0.06, Medium 0.06, Deflation 0.80
- Mesa, Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it

## Another Brick

Mechanics (game data):

- One lane (572 hittable world units). A sight-blocking brick wall runs between the outgoing top half and the returning bottom half, so ground towers see one half; the land right of the U-turn sees both but only ~11-15% of the lane in the model.
- Two $1,000 removable brick piles on the left (RemovableMedOffset, RemovableLargeOffset); they free room behind the wall that sees little track, so the builds leave them.
- Water: a pond top-right and a pond bottom-left beside the exit bend; the bottom pond sees the last stretch best (subs/buccaneers there see 20-29% of the lane).

Sources used:

- bloonswiki: towers that ignore the wall (Flagship, sniper, guided magic) and the exit stretch: https://www.bloonswiki.com/Another_Brick
- fandom strategies: water towers in the ponds, Perma-Spike by the exit: https://bloons.fandom.com/wiki/Another_Brick/Strategies
- BlueCliff, Another Brick Hard (Quincy, ninja, alchemist): https://www.youtube.com/watch?v=igJ6Bsvrnwc
- Bacanator, Another Brick Primary Only: bomb for lead, dart for camo: https://www.youtube.com/watch?v=_H05l61THCQ
- Another Brick Deflation run: https://www.youtube.com/watch?v=XsXdWiQfT0o
- Another Brick Military Only run: https://www.youtube.com/watch?v=ICYRjlf2NsA

Builds:

- `anotherbrick_deflation.yaml` (Deflation), hero quincy; towers (highest tiers per kind): skywarden 1-0-0, buccaneer 0-3-2, sub 2-1-3, bomb 0-2-3, sniper 0-2-1, desperado 2-4-0.
  - Deflation: worst round margin 2.35 (round 55) on the plan alone, 2.46 (round 55) with the fill; plan $19,990; threat simulation: no gaps; base-income test run bought 35/35 plan steps (all, as the test requires); the executor's own checks also buy ans_blimps_sniper in the account-scenario simulation.
- `anotherbrick_easy.yaml` (Easy), hero quincy; towers (highest tiers per kind): skywarden 1-0-1, desperado 4-2-0, buccaneer 2-0-2, bomb 0-2-3.
  - Easy: worst round margin 2.00 (round 37) on the plan alone, 2.89 (round 40) with the fill; plan $11,695; threat simulation: no gaps; base-income test run bought 42/42 plan steps (all, as the test requires); the executor's own checks also buy ans_blimps_ace, ans_moab in the account-scenario simulation.
- `anotherbrick_medium.yaml` (Medium, Reverse), hero quincy; towers (highest tiers per kind): skywarden 1-0-1, desperado 4-2-0, sub 2-3-4, buccaneer 3-0-2, bomb 0-2-3, mermonkey 0-1-1, sniper 1-2-2, boomerang 0-2-3.
  - Medium: worst round margin 2.99 (round 34) on the plan alone, 2.99 (round 34) with the fill; plan $71,335; threat simulation: no gaps; base-income test run bought 72/107 plan steps (only the Easy family must finish).
  - Reverse: worst round margin 2.43 (round 37) on the plan alone, 2.43 (round 37) with the fill; plan $71,335; threat simulation: no gaps; base-income test run bought 72/107 plan steps (only the Easy family must finish).
- `anotherbrick_military_only.yaml` (Military Only), hero quincy; towers (highest tiers per kind): sub 4-4-2, sniper 2-3-3.
  - Military Only: worst round margin 2.80 (round 58) on the plan alone, 2.80 (round 58) with the fill; plan $78,025; threat simulation: no gaps; base-income test run bought 38/56 plan steps (only the Easy family must finish).
- `anotherbrick_primary_only.yaml` (Primary Only), hero quincy; towers (highest tiers per kind): desperado 3-2-0, bomb 0-2-3, boomerang 2-3-3, dart 1-0-4, glue 2-2-0.
  - Primary Only: worst round margin 0.91 (round 40) on the plan alone, 2.54 (round 31) with the fill; plan $14,585; threat simulation: no gaps; base-income test run bought 32/32 plan steps (all, as the test requires); the executor's own checks also buy ans_blimps_boomerang in the account-scenario simulation.

Not written:

- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it

## Ascent

Mechanics (game data):

- Two lanes at the same time (Path1, Path2; one scenario), both from the bottom-left up, across the top and down to exits at the bottom right. Few sight blockers.
- Land: the big central island inside both lanes, the top-centre land with a pond, small right islands. Ponds: top centre, by the right-hand crossing, bottom-left.
- Aces are rated almost nothing here: the model's ace zone is its own small circle, which the lanes barely cross (the wiki's Neva-Miss deflation build cannot be credited).

Sources used:

- bloonswiki: one of the easiest Advanced maps; Perma-Spike on the bottom-right platform, submerged sub at the start: https://www.bloonswiki.com/Ascent
- CrimsonPlanet, Ascent CHIMPS no micro: wizard, druid, sub, village on the central island: https://www.youtube.com/watch?v=KEmm-iPaHl0
- HyperF3, Ascent CHIMPS: sub in the top pond, druids on the island: https://www.youtube.com/watch?v=TZg8hFFquZA
- Ascent Deflation run: https://www.youtube.com/watch?v=rBOohMsKIXo
- Ascent Primary Only run: https://www.youtube.com/watch?v=NE1ckrFcds8
- Ascent Military Only run: https://www.youtube.com/watch?v=_nqlccGB1YU
- Ascent Reverse run: https://www.youtube.com/watch?v=TEeXjGthZyY
- Ascent Hard with Quincy, no micro: https://www.youtube.com/watch?v=P9Ieyck0Q5w
- Ascent Hard, no abilities: https://www.youtube.com/watch?v=buzDHh-CCPY

Builds:

- `ascent_easy.yaml` (Easy), hero obyn; towers (highest tiers per kind): skywarden 1-0-1, desperado 4-2-0, buccaneer 2-0-1, bomb 0-2-3, sniper 0-2-2, super 0-2-0.
  - Easy: worst round margin 1.26 (round 40) on the plan alone, 2.54 (round 40) with the fill; plan $15,200; threat simulation: no gaps; base-income test run bought 37/37 plan steps (all, as the test requires).
- `ascent_medium.yaml` (Medium), hero obyn; towers (highest tiers per kind): skywarden 1-0-1, desperado 4-2-0, sub 2-0-4, bomb 0-2-3, sniper 2-3-0, super 0-3-2.
  - Medium: worst round margin 2.09 (round 58) on the plan alone, 2.09 (round 58) with the fill; plan $56,490; threat simulation: no gaps; base-income test run bought 42/51 plan steps (only the Easy family must finish).
- `ascent_military_only.yaml` (Military Only), hero obyn; towers (highest tiers per kind): sub 2-0-5, sniper 4-3-0, ace 2-4-0.
  - Military Only: worst round margin 2.99 (round 54) on the plan alone, 2.99 (round 54) with the fill; plan $91,405; threat simulation: no gaps; base-income test run bought 29/36 plan steps (only the Easy family must finish).
- `ascent_primary_only.yaml` (Primary Only), hero obyn; towers (highest tiers per kind): desperado 4-3-3, bomb 0-2-4, boomerang 0-3-2.
  - Primary Only: worst round margin 0.91 (round 40) on the plan alone, 2.04 (round 40) with the fill; plan $14,570; threat simulation: no gaps; base-income test run bought 24/24 plan steps (all, as the test requires); the executor's own checks also buy ans_blimps_bomb, ans_moab in the account-scenario simulation.
- `ascent_reverse.yaml` (Reverse), hero obyn; towers (highest tiers per kind): skywarden 1-0-1, desperado 4-2-0, sub 2-0-4, ninja 0-0-1, sniper 2-5-0, spike 3-2-0, super 2-3-3.
  - Reverse: worst round margin 2.00 (round 21) on the plan alone, 2.00 (round 21) with the fill; plan $91,065; threat simulation: no gaps; base-income test run bought 49/57 plan steps (only the Easy family must finish).

Not written:

- Deflation: best design 1.54 (round 59) with all $40,000 spent; the greedy plan cannot hold rounds 54-59 on both lanes, and aces (the wiki's Neva-Miss answer) rate near zero in the model
- Hard: best design 1.41 (round 34), also 1.70 at round 78 and 1.79 at round 59; a longer lookahead did not help
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it

## Cargo

Mechanics (game data):

- One road (PathStandard). The map file also has PathSpecial, a MOAB-only lane that opens after round 39 when the parked trucks drive off; it comes up at x 0.54 between the dock and the right-hand strip, runs left along y 0.355 and leaves at the top (x 0.31). The repo's dps_model leaves it out (it is inactive/hidden at load), so MOAB-class bloons are modelled on the road. Every Cargo build here was designed and checked with that lane added for MOAB-class bloons (scratch wrapper) and on the repo model as it is; both are reported.
- The trucks (CentreTrucksBlocking) block line of sight until round 39; the model counts them as always there (safe side). Two $500 truck removables, left alone.

Sources used:

- bloonswiki: separate bloon and MOAB lanes; trucks block sight: https://www.bloonswiki.com/Cargo
- fandom strategies: water towers right of the MOAB exit, Glaive Lord below the first bend, Perma-Spike where the lanes meet: https://bloons.fandom.com/wiki/Cargo/Strategies
- BlueCliff, Cargo Hard (Quincy, ninja, wizard, bombs): https://www.youtube.com/watch?v=JwH3d8_WOBQ
- Mathgodpi, Cargo CHIMPS with subs: https://www.youtube.com/watch?v=hzVxMvuAEOI

Builds:

- `cargo_easy.yaml` (Easy), hero quincy; towers (highest tiers per kind): skywarden 1-0-1, sub 2-3-2, buccaneer 2-3-2, sniper 0-2-0, desperado 4-2-0.
  - Easy: worst round margin 3.19 (round 15) on the plan alone, 3.19 (round 15) with the fill; plan $16,465; threat simulation: no gaps; base-income test run bought 42/42 plan steps (all, as the test requires); with the MOAB lane added 2.20 (round 40); the executor's own checks also buy ans_blimps_bomb in the account-scenario simulation.
  - All Cargo builds were designed with the MOAB-only lane added; the table gives the repo-model margins and the MOAB-lane margin in brackets.
- `cargo_medium.yaml` (Medium), hero quincy; towers (highest tiers per kind): skywarden 1-0-1, buccaneer 4-3-2, sub 4-3-3, dart 0-0-0, desperado 4-2-0, mermonkey 3-1-1, sniper 2-3-0, alchemist 0-1-0, spike 3-0-1.
  - Medium: worst round margin 2.71 (round 33) on the plan alone, 2.71 (round 33) with the fill; plan $81,550; threat simulation: no gaps; base-income test run bought 75/93 plan steps (only the Easy family must finish); with the MOAB lane added 2.71 (round 33).
- `cargo_military_only.yaml` (Military Only), hero quincy; towers (highest tiers per kind): sub 4-5-2, sniper 1-3-2.
  - Military Only: worst round margin 3.67 (round 58) on the plan alone, 3.67 (round 58) with the fill; plan $102,230; threat simulation: no gaps; base-income test run bought 40/50 plan steps (only the Easy family must finish); with the MOAB lane added 3.22 (round 58).

Not written:

- Primary Only: best 1.40 on the repo model and 0.66 once the MOAB-only lane is added: primary towers in reach of that lane cannot hold the round-40 MOAB
- Deflation: best 0.86 with the MOAB lane (rounds 52-60)
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Reverse: 2.77 on the repo model but 1.78 once the MOAB-only lane is added (round 40 onwards); not written, as the game sends MOABs down that lane (the Medium build of the same design holds 2.71 there but its reverse run did not)

## Castle Revenge

Mechanics (game data):

- Four entrances, two exits: ten routes in one scenario (all at once), bloons invulnerable while on the wheels (31-100% of the entrance paths are hidden). Top and bottom lanes along the castle walls; no ground spot reaches both with a short-range tower.
- Pressure valve (paid switch, $500) not used.

Sources used:

- bloonswiki: the raised platform sees the whole track; Juggernaut near each last bend: https://www.bloonswiki.com/Castle_Revenge
- BlueCliff, Castle Revenge Hard: snipers in the courtyard quarters, Spectre ace: https://www.youtube.com/watch?v=au45yv7NhS8
- OneEyedDeacon, Castle Revenge CHIMPS with Sauda: mirrored damage top and bottom: https://www.youtube.com/watch?v=JfjH7gMVRGw

Builds:

- `castlerevenge_easy.yaml` (Easy), hero quincy; towers (highest tiers per kind): engineer 0-0-0, tack 2-3-0, sub 2-0-3, sniper 1-2-0, skywarden 1-0-0, desperado 4-2-0, village 0-0-0, mermonkey 0-0-0, bomb 0-1-2.
  - Easy: worst round margin 0.93 (round 38) on the plan alone, 2.00 (round 22) with the fill; plan $14,110; threat simulation: no gaps; base-income test run bought 44/44 plan steps (all, as the test requires).
  - One tower added by hand to the optimizer's plan: an Engineer 0-0-0 bought first in the top-right corner, the cheapest single addition that lifts round 16 from 1.94 to 2.0.
- `castlerevenge_medium.yaml` (Medium), hero quincy; towers (highest tiers per kind): tack 3-3-4, skywarden 1-0-0, sub 2-0-4, buccaneer 4-2-0, desperado 4-4-0, bomb 0-2-3, sniper 2-2-4.
  - Medium: worst round margin 2.16 (round 47) on the plan alone, 2.16 (round 47) with the fill; plan $90,050; threat simulation: no gaps; base-income test run bought 69/86 plan steps (only the Easy family must finish).
- `castlerevenge_military_only.yaml` (Military Only), hero quincy; towers (highest tiers per kind): sub 4-2-4, sniper 4-3-0, ace 2-4-0.
  - Military Only: worst round margin 2.20 (round 49) on the plan alone, 2.20 (round 49) with the fill; plan $98,550; threat simulation: no gaps; base-income test run bought 40/58 plan steps (only the Easy family must finish).
- Existing `castlerevenge_hard.yaml` (not edited): fails the 2.0 bar with the fixed model: medium worst 0.60 (round 15), 27 of 46 rounds under 2.0; hard worst 0.53 (round 43), 31 of 59 rounds under 2.0.

Not written:

- Primary Only: best 0.84: ten routes, short-range primary towers reach one lane each
- Deflation: best 1.28
- Reverse: best 1.51 (rounds 34 and 49); 1.15 with a longer lookahead
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Hard: not written: castlerevenge_hard.yaml (not edited) serves Medium and Hard but fails the 2.0 bar (numbers in the map's section); a second Hard file would break the <map>_<mode> naming, so no new Hard build was attempted

## Cornfield

Mechanics (game data):

- One long lane; only the small middle plot and thin strips beside the lane are free. Fourteen corn patches ($350-$1,500) block placement and sight; left alone.
- The plot holds about five towers: the optimizer's habit of filling space with cheap towers (Skywardens) left no room for the later upgrades, so these builds leave out Skywarden, Mermonkey, Engineer, Tack, Ice, Ace, Druid and Spike Factory and spend no surplus on XP.

Sources used:

- bloonswiki: Ultra-Juggernaut (balls bounce off the corn), Obyn/Quincy: https://www.bloonswiki.com/Cornfield
- fandom strategies: corn prices, the middle plot: https://bloons.fandom.com/wiki/Cornfield/Strategies
- BlueCliff, Cornfield Hard (ninja, alchemist, Bloon Solver in the middle plot): https://www.youtube.com/watch?v=qcnDjtGW6DU

Builds:

- `cornfield_deflation.yaml` (Deflation), hero quincy; towers (highest tiers per kind): bomb 3-2-2, sniper 1-3-0, dart 0-2-5.
  - Deflation: worst round margin 0.23 (round 59) on the plan alone, 2.99 (round 53) with the fill; plan $12,540; threat simulation: no gaps; base-income test run bought 15/15 plan steps (all, as the test requires); the executor's own checks also buy ans_blimps_sniper in the account-scenario simulation.
- `cornfield_easy.yaml` (Easy), hero quincy; towers (highest tiers per kind): wizard 0-3-2, desperado 3-0-0, bomb 0-2-4.
  - Easy: worst round margin 0.54 (round 39) on the plan alone, 2.25 (round 26) with the fill; plan $8,895; threat simulation: no gaps; base-income test run bought 18/18 plan steps (all, as the test requires).
- `cornfield_medium.yaml` (Medium, Reverse), hero quincy; towers (highest tiers per kind): dart 0-3-5, desperado 4-1-0.
  - Medium: worst round margin 2.00 (round 27) on the plan alone, 2.00 (round 27) with the fill; plan $50,075; threat simulation: no gaps; base-income test run bought 18/19 plan steps (only the Easy family must finish); the executor's own checks also buy ans_blimps_ace in the account-scenario simulation.
  - Reverse: worst round margin 2.23 (round 28) on the plan alone, 2.23 (round 28) with the fill; plan $50,075; threat simulation: no gaps; base-income test run bought 18/19 plan steps (only the Easy family must finish); the executor's own checks also buy ans_blimps_ace in the account-scenario simulation.
- `cornfield_primary_only.yaml` (Primary Only), hero quincy; towers (highest tiers per kind): boomerang 1-3-3, desperado 4-1-4.
  - Primary Only: worst round margin 1.23 (round 40) on the plan alone, 2.74 (round 36) with the fill; plan $11,330; threat simulation: no gaps; base-income test run bought 17/17 plan steps (all, as the test requires); the executor's own checks also buy ans_blimps_bomb, ans_blimps_boomerang, ans_moab in the account-scenario simulation.

Not written:

- Military Only: best 1.79: corn blocks the snipers' sight from the plot and aces barely count
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it

## Dark Path

Mechanics (game data):

- One diagonal lane; rock walls block sight almost everywhere. Raised rock stacks see over the walls in game, but the model ignores a tower's height (rated blind).
- Cave wall removables ($250-$1,000 per tier) left alone.

Sources used:

- bloonswiki: walls block sight; the raised platforms see over them; Perma-Spike at the exit: https://www.bloonswiki.com/Dark_Path
- SnartFarts, Dark Path CHIMPS: everything in the exit pocket: https://www.youtube.com/watch?v=4AAtx2p1bwE
- BlueCliff, Dark Path Hard (Quincy, ninja, alchemist): https://www.youtube.com/watch?v=WZMh1KPqgyQ

Builds:

- `darkpath_deflation.yaml` (Deflation), hero quincy; towers (highest tiers per kind): ninja 0-0-0, skywarden 1-0-0, mermonkey 3-0-1, alchemist 0-2-0, desperado 4-3-0, spike 4-0-1, super 1-2-0.
  - Deflation: worst round margin 0.24 (round 59) on the plan alone, 2.38 (round 58) with the fill; plan $15,190; threat simulation: no gaps; base-income test run bought 26/26 plan steps (all, as the test requires).
  - One tower added by hand: a Ninja 0-0-0 in the exit pocket at the start of the plan. Without it the offline test found camo zebras (rounds 42 and 51) that the $20,000 plan could not pop; it also lifts the full build from 2.04 to 2.38.
- `darkpath_easy.yaml` (Easy), hero quincy; towers (highest tiers per kind): skywarden 1-0-1, desperado 4-2-0, mermonkey 3-2-0, dart 3-0-2, alchemist 1-1-0, spike 1-2-0.
  - Easy: worst round margin 1.01 (round 38) on the plan alone, 2.30 (round 34) with the fill; plan $15,985; threat simulation: no gaps; base-income test run bought 42/42 plan steps (all, as the test requires); the executor's own checks also buy ans_blimps_ace, ans_moab in the account-scenario simulation.
- Existing `darkpath_hard.yaml` (not edited): now lists Medium only; fails the 2.0 bar: medium worst 0.51 (round 30), 11 of 46 rounds under 2.0.

Not written:

- Primary Only: best 0.92: walls block sight for every primary tower outside the exit pocket
- Medium: best 1.48 (reverse 1.58) after the sniper line-of-sight fix
- Reverse: best 1.58 (see Medium)
- Military Only: best 1.41: snipers need sight, aces barely count, no water
- Hard: not attempted: Medium already fails in the model (the existing darkpath_hard.yaml now lists Medium only)
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it

## Enchanted Glade

Mechanics (game data):

- Two lanes alternate by round (AlternateRoundSplitter: two scenarios); the model plays every round on both and keeps the worst. Short hidden bits at the cherry-tree exit.
- Land: top-left, right-centre and bottom-centre islands, a bottom-right island in a water ring.

Sources used:

- bloonswiki: use the bottom-centre space, the area below the centre, or global towers: https://www.bloonswiki.com/Enchanted_Glade
- BlueCliff, Enchanted Glade Hard (ninja, alchemist, Bloon Solver): https://www.youtube.com/watch?v=WTBG33Bey-M
- SnartFarts, Enchanted Glade CHIMPS with Carrier Flagship: https://www.youtube.com/watch?v=MEHLrD12TMk

Builds:

- `enchantedglade_deflation.yaml` (Deflation), hero quincy; towers (highest tiers per kind): skywarden 1-0-0, mermonkey 3-0-1, sub 4-3-2, sniper 2-2-0.
  - Deflation: worst round margin 0.58 (round 59) on the plan alone, 2.02 (round 58) with the fill; plan $19,560; threat simulation: no gaps; base-income test run bought 34/34 plan steps (all, as the test requires).
- `enchantedglade_easy.yaml` (Easy), hero quincy; towers (highest tiers per kind): skywarden 1-0-0, mermonkey 3-0-1, sub 2-3-2, sniper 1-2-0.
  - Easy: worst round margin 2.83 (round 34) on the plan alone, 2.83 (round 34) with the fill; plan $11,305; threat simulation: no gaps; base-income test run bought 28/28 plan steps (all, as the test requires).
- `enchantedglade_medium.yaml` (Medium), hero quincy; towers (highest tiers per kind): skywarden 1-0-1, sub 4-3-4, mermonkey 3-0-1, sniper 2-2-2, super 0-2-0.
  - Medium: worst round margin 2.07 (round 54) on the plan alone, 2.07 (round 54) with the fill; plan $45,315; threat simulation: no gaps; base-income test run bought 57/62 plan steps (only the Easy family must finish).
- `enchantedglade_military_only.yaml` (Military Only), hero quincy; towers (highest tiers per kind): sub 4-2-2, ace 2-5-0, sniper 1-5-0.
  - Military Only: worst round margin 3.47 (round 54) on the plan alone, 3.47 (round 54) with the fill; plan $84,005; threat simulation: no gaps; base-income test run bought 20/25 plan steps (only the Easy family must finish); the executor's own checks also buy ans_bfb in the account-scenario simulation.
- `enchantedglade_reverse.yaml` (Reverse), hero quincy; towers (highest tiers per kind): skywarden 1-0-1, sub 4-3-2, sniper 2-3-3, mermonkey 0-2-1, tack 2-3-0, super 2-3-2, village 0-0-0.
  - Reverse: worst round margin 2.09 (round 50) on the plan alone, 2.09 (round 50) with the fill; plan $80,245; threat simulation: no gaps; base-income test run bought 56/68 plan steps (only the Easy family must finish).
- Existing `enchantedglade_hard.yaml` (not edited): fails the 2.0 bar: medium worst 0.63 (round 30), 12 of 46 rounds under 2.0; hard worst 0.55 (round 30), 23 of 59 rounds under 2.0.

Not written:

- Primary Only: best 1.74 with the fill (2.13 with an older draft whose new-tower answers carried spots the test rejects); no single added tower lifts it
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Hard: not written: enchantedglade_hard.yaml (not edited) serves Medium and Hard but fails the 2.0 bar (numbers in the map's section); no new Hard build attempted for the same reason

## Erosion

Mechanics (game data):

- Six lanes, one active at a time (six scenarios). In the game the active lane changes with the melts (after rounds 17, 35, 53, 71, 89); the model plays every round on all six lanes, which is far on the safe side.
- Ice melts away under its towers (they are sold). Spots are taken only from ground that lasts the whole game for the mode (placement.valid_spots last_round), so nothing is lost to a melt.

Sources used:

- bloonswiki: lane changes and melting ice; Ice Monkeys turn into water towers: https://www.bloonswiki.com/Erosion
- fandom: Neva-Miss aces in Deflation; sub start into snipers: https://bloons.fandom.com/wiki/Erosion
- G-Horizon, Erosion CHIMPS: sub, snipers, village and alchemist on the glacier: https://www.youtube.com/watch?v=No3NYnNZV1c
- BlueCliff, Erosion Hard (sub, snipers, glacier): https://www.youtube.com/watch?v=jlkIyVLVjmI

Builds:

- `erosion_easy.yaml` (Easy), hero psi; towers (highest tiers per kind): sniper 2-2-0, skywarden 1-0-1, sub 2-2-3, mermonkey 2-1-0, alchemist 0-1-0, ace 2-3-0, buccaneer 2-0-1, desperado 3-2-0.
  - Easy: worst round margin 1.13 (round 40) on the plan alone, 2.51 (round 40) with the fill; plan $17,000; threat simulation: no gaps; base-income test run bought 43/43 plan steps (all, as the test requires); the executor's own checks also buy ans_blimps_super in the account-scenario simulation.
- `erosion_military_only.yaml` (Military Only), hero psi; towers (highest tiers per kind): sub 4-3-4, sniper 3-3-0, ace 2-3-1, buccaneer 4-0-2.
  - Military Only: worst round margin 2.86 (round 55) on the plan alone, 2.86 (round 55) with the fill; plan $99,525; threat simulation: no gaps; base-income test run bought 43/86 plan steps (only the Easy family must finish).

Not written:

- Primary Only: no design at all: the model plays every round on all six lanes and no primary tower is map-wide
- Deflation: best 1.51
- Medium: best 1.10 (reverse 1.30)
- Reverse: best 1.30 (see Medium)
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it

## Geared

Mechanics (game data):

- A big gear (8 positions, 45 degrees a round) and a small gear (10 positions, 108 degrees) turn after every round from round 2 and carry their towers. valid_spots allows finite-range towers only on cells that barely move, so the builds are snipers and aces.
- Psi cannot be placed at all: its range is None in towers.HEROES, placement turns that into 0 and allows no cell on moving ground. Quincy fits on the one steady cell.
- Primary Only is not possible in the model: no primary tower is map-wide and none fits on a steady cell with track in reach.

Sources used:

- bloonswiki: global towers; the early game is the hard part: https://www.bloonswiki.com/Geared
- fandom strategies: four snipers on Strong + heli; 1-1-0 snipers for the R59 camo leads: https://bloons.fandom.com/wiki/Geared/Strategies
- G-Horizon, Geared CHIMPS: sniper spam on Strong: https://www.youtube.com/watch?v=6QOiPh3CY1w

Builds:

- `geared_deflation.yaml` (Deflation), hero quincy; towers (highest tiers per kind): ace 2-3-0, sniper 3-4-0.
  - Deflation: worst round margin 1.48 (round 58) on the plan alone, 2.04 (round 58) with the fill; plan $19,780; threat simulation: no gaps; base-income test run bought 22/22 plan steps (all, as the test requires).
- `geared_easy.yaml` (Easy), hero quincy; towers (highest tiers per kind): ace 2-3-0, sniper 1-2-2.
  - Easy: worst round margin 2.51 (round 39) on the plan alone, 2.51 (round 39) with the fill; plan $10,540; threat simulation: no gaps; base-income test run bought 18/18 plan steps (all, as the test requires).
- `geared_medium.yaml` (Medium, Reverse), hero quincy; towers (highest tiers per kind): sniper 3-3-4, ace 2-3-0.
  - Medium: worst round margin 3.05 (round 54) on the plan alone, 3.05 (round 54) with the fill; plan $52,040; threat simulation: no gaps; base-income test run bought 38/41 plan steps (only the Easy family must finish).
  - Reverse: worst round margin 3.22 (round 54) on the plan alone, 3.22 (round 54) with the fill; plan $52,040; threat simulation: no gaps; base-income test run bought 38/41 plan steps (only the Easy family must finish).
- `geared_military_only.yaml` (Military Only), hero quincy; towers (highest tiers per kind): sniper 3-3-4, ace 2-3-0.
  - Military Only: worst round margin 3.05 (round 54) on the plan alone, 3.05 (round 54) with the fill; plan $52,040; threat simulation: no gaps; base-income test run bought 38/41 plan steps (only the Easy family must finish).

Not written:

- Primary Only: no primary tower is map-wide and none fits on a steady cell with track in reach, so nothing can be placed in the model
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it

## High Finance

Mechanics (game data):

- Two lanes alternate by round (S lane odd rounds, U lane even rounds; two scenarios). The only free ground is the central park and its two ponds; 15 buildings ($350-$1,500) can be bought for room, left alone.
- The park fits about six towers; the hero often finds no room left (its step has no `at` and the executor tries wherever it fits).

Sources used:

- bloonswiki: Carrier Flagship in the pond: https://www.bloonswiki.com/High_Finance
- fandom: buccaneer in the pond, Bloon Solver on the $750 building: https://bloons.fandom.com/wiki/High_Finance
- BlueCliff, High Finance Hard (ninja on the park corners, buccaneer): https://www.youtube.com/watch?v=C5QklAgqeGQ

Builds:

- `highfinance_deflation.yaml` (Deflation), hero quincy; towers (highest tiers per kind): skywarden 1-0-1, buccaneer 0-5-2, mermonkey 3-0-1, ice 0-1-4.
  - Deflation: worst round margin 1.20 (round 58) on the plan alone, 4.41 (round 55) with the fill; plan $14,880; threat simulation: no gaps; base-income test run bought 22/22 plan steps (all, as the test requires); the executor's own checks also buy ans_ceramic in the account-scenario simulation.
- `highfinance_easy.yaml` (Easy), hero quincy; towers (highest tiers per kind): skywarden 1-0-0, buccaneer 0-3-2, mermonkey 3-2-0, ice 0-1-4.
  - Easy: worst round margin 2.43 (round 38) on the plan alone, 2.51 (round 38) with the fill; plan $7,240; threat simulation: no gaps; base-income test run bought 19/19 plan steps (all, as the test requires); the executor's own checks also buy ans_ceramic in the account-scenario simulation.
- `highfinance_medium.yaml` (Medium, Reverse), hero quincy; towers (highest tiers per kind): skywarden 1-0-1, buccaneer 0-5-2, mermonkey 3-2-0, ice 0-1-4.
  - Medium: worst round margin 2.86 (round 43) on the plan alone, 2.86 (round 43) with the fill; plan $46,845; threat simulation: no gaps; base-income test run bought 25/26 plan steps (only the Easy family must finish); the executor's own checks also buy ans_bfb, ans_ceramic in the account-scenario simulation.
  - Reverse: worst round margin 2.77 (round 60) on the plan alone, 2.77 (round 60) with the fill; plan $46,845; threat simulation: no gaps; base-income test run bought 25/26 plan steps (only the Easy family must finish); the executor's own checks also buy ans_bfb, ans_ceramic in the account-scenario simulation.
- `highfinance_military_only.yaml` (Military Only), hero quincy; towers (highest tiers per kind): sub 4-0-2, sniper 5-5-0.
  - Military Only: worst round margin 2.43 (round 47) on the plan alone, 2.43 (round 47) with the fill; plan $96,045; threat simulation: no gaps; base-income test run bought 17/23 plan steps (only the Easy family must finish).

Not written:

- Primary Only: best 1.53: the park fits about six towers and primary towers there cannot hold both alternating lanes
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it

## Last Resort

Mechanics (game data):

- Four routes in a 4-round cycle (big, medium, small loop, straight; four scenarios). The model plays every round on all four, so a build must hold the fast small-loop and straight rounds.
- The $1,000 frozen pool (RemovableWater) opens the best water spot; not bought (no buyer in the bot, and the model has no legal water cell there even after removal).

Sources used:

- bloonswiki: loop cycle; Perma-Spike as far right as possible: https://www.bloonswiki.com/Last_Resort
- BlueCliff, Last Resort Hard (Quincy, ninja, alchemist, heli, sniper): https://www.youtube.com/watch?v=z_4kPTV47MI
- OneEyedDeacon, Last Resort CHIMPS no abilities: snipers from the inner strip, Perma-Spike: https://www.youtube.com/watch?v=7fpYt6w9ziE

Builds:

- `lastresort_easy.yaml` (Easy), hero quincy; towers (highest tiers per kind): skywarden 1-0-1, sniper 1-2-0, druid 1-3-0, desperado 4-2-0.
  - Easy: worst round margin 2.51 (round 36) on the plan alone, 2.51 (round 36) with the fill; plan $9,230; threat simulation: no gaps; base-income test run bought 22/22 plan steps (all, as the test requires).
- `lastresort_medium.yaml` (Medium), hero quincy; towers (highest tiers per kind): skywarden 1-0-0, sniper 4-5-0, desperado 3-2-0, druid 0-3-1.
  - Medium: worst round margin 2.20 (round 60) on the plan alone, 2.20 (round 60) with the fill; plan $105,230; threat simulation: no gaps; base-income test run bought 56/67 plan steps (only the Easy family must finish).
- Existing `lastresort_hard.yaml` (not edited): the file was removed from strategies/maps during this work (it rated 0.14 at round 27 in Hard before the model fixes).

Not written:

- Primary Only: best 0.33: the small-loop and straight rounds outrun short-range primary towers
- Deflation: best 1.92 (round 53); no single added tower lifts it to 2.0
- Military Only: best 1.35 (1.27 with a longer lookahead)
- Reverse: best 1.72 (round 60); 1.08 with a longer lookahead
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it
- Hard: attempted (lastresort_hard.yaml was removed from the repo during this work), stopped unfinished after 20 minutes of CPU at idle priority to free the slot for the final checks

## Mesa

Mechanics (game data):

- Two lanes at the same time. In the model the bottom lane is invisible from every legal spot for towers that need sight: the rock island inside its loop sees it in game (the guides build there), but the sight grid ignores the island's height. Only Spike Factories, Alchemists and Aces count there, and they cannot reach a 2.0 margin.
- Three $500 rock removables, left alone.

Sources used:

- bloonswiki: cliffs block sight; MOABs take the top lane: https://www.bloonswiki.com/Mesa
- fandom strategies: build top-right of the centre, snipers on the cliffs: https://bloons.fandom.com/wiki/Mesa/Strategies
- OneEyedDeacon, Mesa CHIMPS no abilities: snipers on the plateau, Glaive Lord in the strip: https://www.youtube.com/watch?v=CVxEdZq3I2c

Builds:

- none

Not written:

- Easy, Primary Only, Deflation, Medium, Military Only, Reverse: the model sees Mesa's bottom lane from no legal spot for towers that need sight (the rock island inside its loop is rated blind); best Easy 0.06, Medium 0.06, Deflation 0.80
- Apopalypse: random waves with no round calendar: the damage model and tools/simulate_threats.py cannot rate it

## Apopalypse

Not written for any of the twelve maps. Apopalypse sends random waves with
no round calendar; `dps_model` rates rounds from the game's round sets and
`tools/simulate_threats.py` skips the mode for the same reason, so no build
could be validated.

## Model fixes during this work

Two fixes landed in `btd6bot/dps_model.py` while these builds were made, and
every build was redone or re-checked after both:

- **Buccaneer secondaries** (Grape Shot, cannons) had been counted at
  20 shots/s, so middle-path buccaneers were rated many times too strong.
  Every design that had a buccaneer was thrown away and made again. Example:
  the first High Finance Easy build leaned on a 0-3-2 buccaneer and failed
  once the fix was in (worst margin 0.06); the build kept now passes with
  2.43 on the plan alone.
- **Sniper line of sight**: map-wide snipers are now held to line of sight.
  Every design with a sniper was made again. This is what turned Mesa into a
  skip (see below) and pushed several Dark Path and Last Resort modes under
  2.0.

## Capability gaps found (not changed: other modules)

1. **Cargo's MOAB lane is missing from the damage model.** `PathSpecial` in
   the map file is inactive and hidden at load and opens after round 39, so
   `dps_model.map_routes` never sees it and models MOAB-class bloons on the
   road. Every Cargo build was designed and checked with the lane added for
   MOAB-class bloons (a scratch copy of `Track` with the path appended as a
   MOAB-only route in the same scenario) and also on the repo model as it is.
   Suggested fix: in `map_routes`, add paths opened by a `path_opens` event
   (data/map_mechanics.json) as MOAB-only routes from that round.
2. **Erosion lanes by round.** The model plays every round on all six lanes.
   In game the active lane follows the melts (rounds 1-17, 18-35, 36-53,
   54-71, 72-89, 90+). The builds pass the stricter model; a lane-by-round
   scenario would let cheaper builds through and might rescue Medium and
   Deflation.
3. **Height ignored by the sight grid.** Mesa's rock island (inside the
   bottom lane's loop) and Dark Path's rock stacks see over the walls in game
   but are rated blind. On Mesa this leaves the bottom lane reachable only by
   Spike Factories, Alchemists and Aces, and no build reaches 2.0 in any
   mode.
4. **Aces barely count.** An ace's zone is its own small flight circle, so
   Neva-Miss aces (homing darts, the wiki's generic Deflation answer) rate
   near zero.
5. **Psi cannot be placed on moving ground.** `towers.HEROES["psi"]["range"]`
   is None, `placement.reach_units` turns it into 0 and `valid_spots` then
   allows no cell on Geared's gears. The Geared builds use Quincy on the one
   steady cell instead.
6. **Heli Pursuit cannot be set.** `strategy.TARGET_MODES` has no "pursuit"
   (Game.target cycles to a named mode), so helis were left out although the
   guides use them on Dark Path, Geared, High Finance and Last Resort.
7. **The executor's blimp check does not know the new hotkey towers.**
   `data/counters.json` `blimp_dps` has no Desperado, Skywarden or Mermonkey,
   so `Executor._answer_ramp` underrates builds that use them and buys an
   extra blimp tower before round 40 (seen in the account-scenario
   simulation as `ans_blimps_*`). Harmless for safety, but it spends fill
   money on towers at spots of its own choosing.
8. **Fill is bought in any order, and surplus spends idle cash.**
   `Executor.tick` buys the first affordable fill step, so a cheap later
   step can go before an expensive one that waits for cash; the match loop
   also spends idle cash over $800 on planned upgrades after a short wait.
   The "with fill" margins above replay the any-order fill; the surplus
   reordering is not modelled. Most plans hold 2.0 on their own.
9. **Removable obstacles are never bought.** The guides open space with
   Cornfield's corn, High Finance's buildings, Last Resort's frozen pool and
   Mesa's rocks; the bot has no buyer (docs/map_strategies.md, "Wiring still
   to do", item 7), so these builds use only the free ground.
10. **Easy-family plans are capped by the offline test.** The test plays
    Easy, Primary Only and Deflation without Double Cash or Fast Track and
    wants the plan finished by round 40 (Deflation: on $20,000). Builds that
    need more than that keep the rest in fill; their plan-alone margin is
    lower (see the table) and they rely on the account's boosts.

## Test results

- `python tests/test_map_hints_offline.py`: all 8 tests pass with the 39 builds installed
  (the hints file no longer has to list a build: the test was relaxed during
  this work, so these files are not listed in `data/map_strategy_hints.json`).
- `python tests/test_achievement_strats_offline.py`: all 14 tests pass.
- `strategy.load_all()`: all 39 load with `bot_ready: True` (source `maps`).
