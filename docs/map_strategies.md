# Map strategies from the community

How experienced players beat the maps the bot lost, and every Advanced and
Expert map (where it will struggle next), turned into data the bot can use.
Researched October 2026 (game v57/v58).

## Where it lives

| What | File |
|---|---|
| These findings, with sources | `docs/map_strategies.md` (this page) |
| Machine-readable hints per map | `data/map_strategy_hints.json` |
| Map-specific builds | `strategies/maps/<map>_<mode>.yaml` |
| Checks (spots legal, builds valid, threat simulation) | `tests/test_map_hints_offline.py` |

## How the research was done

- **Wikis.** The "Strategy", "Tips" and "Recommended towers" sections of
  bloonswiki.com and bloons.fandom.com, read through their MediaWiki API (the
  page URLs refuse plain fetching).
- **Guide videos.** YouTube search results and the full video descriptions.
  Many guides (BlueCliff, OneEyedDeacon, SnartFarts, BeatbloonsBob,
  G-Horizon, ApexZ and others) write the whole build in the description,
  round by round. This was the richest source.
- **Written guides.** Steam guides and bloon.games.
- **BTD6 Index** (btd6index.win). Community CHIMPS records per map: least
  tiers, least cash, CHIMPS starts. These are extreme challenges, so they
  are used only as evidence of which towers are strong on a map.
- **Reddit.** r/btd6 threads only appear as search-result snippets. Reddit
  serves a browser check to scripts, and that check was not worked around.

Placement words from the guides ("inside the spiral", "the open pocket by
the exit") were turned into screen positions using the map's own geometry:
the areas and paths in `data/map_geometry/<id>.json`, rendered with the
same colours as `tools/render_map_mechanics.py`. Each position was then
checked with `placement.valid_spots` on a `MapModel` filled by
`mapgeom.apply`. A spot that the model refused was moved to the nearest
legal cell: up to 6 grid cells, or 10 for heroes, alchemists, villages and
spike factories, whose job does not depend on the exact cell. Otherwise it
was dropped, and the drop is listed under "Model gap" when the guides
clearly use that spot.

Caveats:

- Most Hard guides are BlueCliff's no-Monkey-Knowledge videos from v25-v47.
  Prices and some upgrades have changed since; the build orders still match
  the current game's towers.
- Many guides sell towers, aim mortars or time abilities. The builds note
  where the bot must differ: it never sells in CHIMPS, cannot aim, and
  presses abilities blindly.
- "Inferred" marks a build or spot that no single guide states. Such builds
  were put together from the guides plus the map geometry.

## Patterns across the maps

1. **Lanes that alternate or run side by side beat single-cluster plans.**
   The lost games on Luminous Cove, Castle Revenge, Party Parade, Last Resort
   and Enchanted Glade (Hard) and Bloonarius Prime (Deflation) all had towers
   that reached one lane, or only some of the alternating routes. `lane_type` in the hints
   says which kind a map is. The fixes, in order of preference:
   - spots that reach every lane (the heart pond on Luminous Cove, the junction
     on Pat's Pond, the bottom-centre island on Enchanted Glade);
   - mirrored pairs, one per lane (Party Parade, Castle Revenge);
   - global towers (snipers with sight, Pursuit helis, aces).
2. **Line of sight and moving ground call for global towers.** This applies
   to Dark Path, Covered Garden, Geared, Sanctuary, Sunken Columns and
   Spillway. On Dark Path the only ground that sees the lane is the pocket by
   the exit, the pocket by the entrance and two raised rock stacks.
3. **Water maps want water towers.** Luminous Cove, Peninsula, Flooded
   Valley, #Ouch, Muddy Puddles and Off The Coast are all won with subs
   (2-0-4, then Sub Commander), buccaneers (Destroyer, then Carrier Flagship)
   and Admiral Brickell.
4. **Fast Track starts Hard at round 22 with about $9,700.** Dark Path, Last
   Resort and Party Parade leaked at once because the opening towers stood in
   the wrong places. The map strategies put their core in reachable spots
   first, so that money builds the core before Play.
5. **The planned crosspaths drift.** The bot logs for Enchanted Glade, Party
   Parade and Last Resort show ninjas that ended 0-0-4 instead of 4-0-2, and
   Super Monkeys at 0-2-3 instead of 3-0-2. The offline simulation shows the
   same with the new map strategies. `Executor.surplus()` buys the next tier
   on any legal path, which pushes a tower off its planned crosspath; the
   plan's later upgrades then become impossible. This is a bot bug, not a
   map problem.

## How the bot can use the hints

`data/map_strategy_hints.json` has one entry per map:

- `builds`: spot lists in buy order. Each build serves the modes it lists;
  the build marked `default` serves every other mode. Each build gives its
  `towers` (the preferred towers for those modes), its `hero`, and its
  `spots` (tower, `at` = [fx, fy] in screen fractions, a note and a `where`).
- `avoid`: towers that do not work as main damage on the map, with the
  reason, and optionally the modes it applies to.
- `removables`: obstacles worth buying, using the names
  `mapgeom.removables()` gives. Each says when to buy it (round) and whether
  it is `recommended`, `optional` or `never`.
- `mechanics_data`: machine-readable rules, such as Covered Garden's pane
  cycle, Bloonarius Prime's prime rounds and Erosion's melt rounds.
- `model_gaps`: places the guides use that the bot's map model gets wrong.
- `strategies`: the map strategies in `strategies/maps/`.

The map strategies use one step key the executor does not read yet:
`at: [fx, fy]`, an exact spot to try first. Without it, a step falls back to
its `role`, `near` and `segment`.

## Wiring still to do in the code

None of this is wired yet. The data and the tests are in place.

1. **Load the map strategies.** `strategy.load_all()` should read
   `strategies/maps/*.yaml` the way it reads `strategies/generated/`:
   - set `source: "maps"`;
   - set `bot_ready` from `readiness()`;
   - set `planner.maps` from `map:`.

   `usable()` already refuses a strategy with `map:` on any other map.
2. **Exact spots.** Add `"at"` to `strategy.STEP_KEYS`. In
   `Executor.pick_spots`, a place step with `at` puts the cell
   `self.m.frac_to_cell(*at)` first, if `placement.valid_spots` allows it now
   (the placed towers, `land_only` and `last_round` as for any spot).
   Otherwise it uses the nearest valid cell within about 6 cells. The usual
   role-based spots follow as fallbacks, so `Game.place` can still try them.
3. **Hint spots for every strategy.** A small loader for
   `data/map_strategy_hints.json` picks the build for (map, mode): the
   build listing the mode, else the `default` build. When a place step has no
   `at`, the executor tries the next unused hinted spot of the same tower
   kind first, if it is still valid. Hero spots apply to whatever hero is
   equipped (`valid_spots` checks that hero's footprint).
4. **Planner.** The win chance of a strategy should drop with the share of
   its cash that goes into towers the map `avoid`s (for example
   `p *= 1 - 0.5 * share`), and rise a little when its damage towers match the
   build's `towers`. A strategy in `strategies/maps/` for the map should then
   rank above general plans, whose losses are the reason it exists.
5. **Keep the planned crosspaths** (a bug, not map-specific).
   `Executor.surplus()` buys the next tier on any legal path. That sent
   4-0-2 ninjas to 0-0-4 and 3-0-2 Super Monkeys to 0-2-3 in the Enchanted
   Glade, Party Parade and Last Resort losses, and it shows in the offline
   simulation of these strategies. Surplus upgrades should stay within each
   tower's planned final crosspath (the highest `to` of its id in plan, fill
   and answers). Past it, they should extend only the paths that crosspath
   already uses.
6. **No opener in Deflation.** `Executor._with_opener` adds a $200 dart even
   when the game starts at round 31 with all its cash. Skip it when
   `start_round > 5` or `buy_all_upfront`.
7. **Removable obstacles.** A buyer for the `removables` marked
   `recommended` would:
   - click `at` from the given round;
   - check the price on the panel;
   - then place with `valid_spots(removed=[name])`.

   Mushroom Grotto needs this most: nothing big fits until its mushrooms are
   lit.
8. **Covered Garden panes.** `mechanics_data.pane_cycle` gives the open
   quarter per round. Allowing the open quarter as ground in that round, and
   saving each pane tower's upgrades for its open rounds, would unlock the
   best spots on the map.
9. **Model gaps.** Each map's `model_gaps` lists them. Two more apply across
   maps:
   - Psi's range is `None` in `towers.HEROES`, and `placement.reach_units`
     turns that into 0, so Psi counts as a zero-range hero, not a global one.
   - Towers on raised ground that see over walls, such as Dark Path's rock
     stacks, are rated blind.

## Contents

- **Maps the bot lost:** [Luminous Cove](#luminous-cove), [Covered Garden](#covered-garden), [Ancient Portal](#ancient-portal), [Bloonarius Prime](#bloonarius-prime), [Castle Revenge](#castle-revenge), [Dark Path](#dark-path), [Last Resort](#last-resort), [Pat's Pond](#pats-pond), [Party Parade](#party-parade), [Enchanted Glade](#enchanted-glade), [Logs](#logs)
- **Advanced maps:** [Off The Coast](#off-the-coast), [Cornfield](#cornfield), [Underground](#underground), [High Finance](#high-finance), [Another Brick](#another-brick), [Peninsula](#peninsula), [Cargo](#cargo), [Spillway](#spillway), [Geared](#geared), [Mesa](#mesa), [X Factor](#x-factor), [Sunken Columns](#sunken-columns), [Midnight Mansion](#midnight-mansion), [Erosion](#erosion), [Sunset Gulch](#sunset-gulch), [Mushroom Grotto](#mushroom-grotto), [Ascent](#ascent), [Ship Capture](#ship-capture)
- **Expert maps:** [Muddy Puddles](#muddy-puddles), [#Ouch](#ouch), [Dark Castle](#dark-castle), [Quad](#quad), [Workshop](#workshop), [Bloody Puddles](#bloody-puddles), [Infernal](#infernal), [Flooded Valley](#flooded-valley), [Ravine](#ravine), [Sanctuary](#sanctuary), [Dark Dungeons](#dark-dungeons), [Glacial Trail](#glacial-trail), [Tricky Tracks](#tricky-tracks)

## Maps the bot lost

### Luminous Cove

*Intermediate map. Bot record (logs/results.jsonl, 2026-10-22): hard **defeat at round 49** (chimps_ninja_sun, 96 lives lost).*

**Key insight.** Two lanes alternate by round and both loop round the heart-shaped pond in the middle; the only land is the strip along the bottom, and every land spot reaches one lane only. A land plan therefore defends every other round (lost at round 49). Build in the heart pond (subs, a buccaneer going to Carrier Flagship, Admiral Brickell) and add snipers on the bottom-left land, which see about 70% of both lanes.

**Lanes (alternating).** odd rounds: top-left entrance, clockwise round the heart pond, exit bottom-right; even rounds: top-right entrance, anticlockwise, exit bottom-left

**What the guides found** (detail from the sources):

- Alternating lanes per round: odd rounds = top-left entrance -> clockwise loop round the central heart pond -> exit bottom-right; even rounds = top-right entrance -> anticlockwise loop -> exit bottom-left (bloonswiki Layout; fandom Overview).
- The pre-waterfall track near both entrances (top-left and top-right, dotted on the map picture) is raised and line-of-sight blocked for most towers; heli and Carrier Flagship get round it (bloonswiki Strategy).
- Water: central heart pond (x 0.30-0.56, y 0.36-0.62) = the only spot reaching both lanes; bottom pond (x 0.28-0.58, y 0.72-0.95) between the two exits = ~14-23% of one lane + ~14% of the other for a buccaneer
- Land: only the bottom strip (x 0.0-0.30 and 0.57-0.85, y 0.63-0.97). Closest land to the loop: (0.254,0.666) left and (0.612,0.666) right; each covers one lane. Villages do not fit near the pond (nearest legal village spots (0.179,0.76) / (0.703,0.811)).

**Towers that work:**

- buccaneer 5-2-0: Carrier Flagship: planes ignore line of sight and hit the whole map, +~17% buff to water towers; wiki's top recommendation.
- buccaneer 0-5-2: Pirate Lord used as the late-game carry in BlueCliff's Hard win (0-3-2 R65 -> 0-5-2 R79).
- sub 2-0-5: Sub Commander (via 2-0-4 at R43) is BlueCliff's mid-game carry on Hard
- hero:Admiral Brickell -: Wiki: Naval Tactics buffs nearby water towers for the hardest rounds, +1 pierce to water towers, Mega Mines.
- mermonkey 0-x-x early: Amphibious: can sit in the heart pond (0.36,0.45) reaching ~18% of each lane
- sniper 4-0-2 / 0-2-4: Global range; from the bottom-left land (0.248,0.675) a sniper has line of sight to ~70% of BOTH lanes (geometry).

**Avoid:** ninja (every land spot reaches one of the two alternating lanes only (lost at R49 with a land plan)); wizard (land spots reach one lane only); tack (land spots reach one lane only); spike (can only stand by one of the two exits).

**Removable obstacles and map switches:**

- Mermonkey secret (stone carving in the middle) (free): never for the bot (needs a tier-5 Mermonkey on each of the three paths first, then a click on the carving). Only extra water placement; worth it only for buccaneer farming / water paragons.

**Builds (in buy order):**

*hard, used for the 'hard' hints* - inferred bot-friendly water build (not from a single source) (hero: Admiral Brickell; inferred, built from: wiki (Flagship + Brickell), BlueCliff Hard (Sub Commander) ...). Source: https://www.bloonswiki.com/Luminous_Cove

  R1-5: Sub 0-0-0 in the heart pond (0.35,0.53) -> 2-0-2 asap (Advanced Intel + twin guns); R6-12: second Sub at (0.51,0.53) 2-0-2; place Brickell in the heart pond (0.43,0.58) when affordable; R13-30: Buccaneer at (0.43,0.47) 2-0-0 -> 3-2-0 (Destroyer); subs 2-0-3; R30-45: Sniper 0-2-2 at (0.248,0.675) on Strong for camo/leads on both lanes; subs 2-0-4; R45-60: Buccaneer 4-2-0 (Aircraft Carrier); Sub 2-0-5 Sub Commander; R60-80: Buccaneer 5-2-0 Carrier Flagship; Alchemist cannot reach the pond from land (too far) - spend on more subs 2-0-4 in the pond instead

*chimps, used for the 'chimps' hints* - metaldevil CHIMPS with Brickell (Carrier Flagship + Crossbow Master + Spirit of the Forest) (hero: Admiral Brickell; youtube description, v45.3). Source: https://www.youtube.com/watch?v=O65H67unAwA

  R6: place Dart 'closer to the darker bottom path', then place the Buccaneer ('boat'); R7: Buccaneer 1-0-0; R12: place Brickell; R13: Buccaneer 2-0-0; R14-R18: Dart to 0-0-3; R19: Dart 2-0-3; R23: Buccaneer 2-2-0; R29: Dart 2-0-4; R35: Buccaneer 3-2-0, then place a Glue 'as high into the corner as possible' (only a marker for the village for now); before R40: Village 1-2-0 placed as high and close to the glue as possible, covering the dart; R40: Village 2-2-0; R48: Buccaneer 4-2-0, then Druid 1-3-0; R49: Druid 1-4-0; R71: Druid 1-5-0; R81: Buccaneer 5-2-0; R85: Dart 2-0-5; R88: Alchemist 4-2-0 next to the boat; R91: Glue 0-2-3; R94: Sniper 4-0-2 on Strong; R95: Village 4-2-0; R96: Glue 0-2-4; R97: Ice 4-0-2; R98-100: guide places Brickell's Mega Mine by hand near the top-right pool / near the BAD (micro - the bot can only press the ability blindly)

*hard* - BlueCliff Hard (Quincy, ninja + alch, Sub Commander, Pirate Lord) (hero: Quincy; youtube description, ~v44-45 (2 years old), no Monkey Knowledge). Source: https://www.youtube.com/watch?v=67rUzMWVE-Q

  Note: '~' in the guide = wait until the round ends, then buy (i.e. buy in the break before the next round).; R3: place Quincy; R6: place Ninja; R8: Ninja 0-0-1; R9: Ninja 1-0-1; R11: Ninja 2-0-1; R13: Ninja 2-0-2; R17: Ninja 3-0-2; after R24: Alchemist (left) 2-0-0, set targeting Strong; after R27: Alchemist (left) 3-0-1; R35: Ninja 4-0-2; after R37: Alchemist (left) to 4-0-1 (guide writes '402 Alch (left)'); R39: Sub 2-0-2; R41: Sub 2-0-3; R43: Sub 2-0-4; R57: Sub 2-0-5; R61: Alchemist (right) 4-0-1; R65: Buccaneer 0-3-2 + Village 2-0-0; R67: Buccaneer 0-4-2; R75: Village 2-1-0; R79: Buccaneer 0-5-2; R80: buccaneer ability (optional)

*chimps* - BTD6 Master 'Easy Peasy' CHIMPS (Obyn, ninja/alch/village/druid/spike) - LOW RELIABILITY text (hero: Obyn Greenfoot; web guide, ~v46-48 (1 year old); video https://www.youtube.com/watch?v=fzoVygeCjno). Source: https://bloon.games/how-to-beat-chimps-on-luminous-cove/

  Start: Ninja, upgrade 1-0-1 (path 1 first, then path 3); R12: place Obyn; Ninja 3-0-2, then 4-0-2 when affordable; Village 0-0-2; Alchemist next to the ninja, 4-2-0 before R40; Village to Jungle Drums (2-0-2 -> 2-?-2); Druid 2-4-0, then Spirit of the Forest (2-5-0); Spike Factory 2-5-0 (Carpet of Spikes); Village 5-2-0 (Primary Expertise); CAUTION: the page text looks machine-written (calls the map a 'Beginner Map'), gives no positions, and is a land build - which per the geometry covers one lane per ...

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC cheapest: Carrier Flagship 5-0-2 + Brickell lvl 17 (Huibui, v44.1); LTC og/heroless: Glaive Lord 5-0-2 + M.A.D 2-5-0 (Luggy, v44.0); LCC $41,145 (Huibui, v44.1). 2TC: Wizard Lord Phoenix + Pre-emptive Strike (Extreminator418, BTD6 Index video AdgXTcOTvxw). Subs-only CHIMPS black border exists (Brickbrock v44.1, video SomxhKhswRg).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 7 spots - sub, buccaneer, sniper, ninja; hero admiral_brickell; 'chimps' (impoppable, chimps): 6 spots - buccaneer, dart, druid, glue, village; hero admiral_brickell.
Map strategy: `strategies/maps/luminouscove_hard.yaml`.

**Sources:**

- https://www.bloonswiki.com/Luminous_Cove - Blooncyclopedia: Luminous Cove
- https://bloons.fandom.com/wiki/Luminous_Cove - Bloons fandom wiki: Luminous Cove
- https://www.youtube.com/watch?v=67rUzMWVE-Q - BlueCliff - Luminous Cove Hard (Quincy)
- https://www.youtube.com/watch?v=O65H67unAwA - metaldevil - CHIMPS on Luminous Cove with Brickell v45.3
- https://www.youtube.com/watch?v=SomxhKhswRg - Brickbrock - Luminous Cove CHIMPS with only Monkey Subs (v44.1)
- https://bloon.games/how-to-beat-chimps-on-luminous-cove/ - bloon.games CHIMPS on Luminous Cove
- https://www.youtube.com/watch?v=6px-blLOAU8 - NamelessBandicoot - CHIMPS w/ Energizer, Brickell & Icicle Impale

### Covered Garden

*Intermediate map. Bot record (logs/results.jsonl, 2026-10-22): hard **defeat at round 76** (ach_abracadabmonkey, lives lost not recorded).*

**Key insight.** Glass panes cover three of the four garden quarters and the open quarter moves clockwise every round, so a tower under the glass can only be placed or upgraded one round in four. The bot treats pane ground as closed and ran out of spots (lost at round 76 with $49,876 unspent). Build on the always-open strip left of the garden with global towers (heli, ace, sniper) and their supports; the top-left quarter is the best pane ground once the bot can time it.

**Lanes (single).** enters left (y~0.70), up the column x~0.33, round the fountain in the top-left quarter, along the top, down x~0.60 and out at the right (y~0.40)

**What the guides found** (detail from the sources):

- Pane cycle: bloonswiki 'bottom-left quarter is uncovered on Round 1, and the uncovered quarter rotates 90 degrees clockwise every round'; fandom gallery: sniper placeable top-left on R2, top-right on R3, bottom-right on R4.
- Quadrants (screen fractions, from the WindowUpperLeft/LowerLeft/UpperRight/LowerRight pane polygons in data/map_geometry/coveredgarden.json): TL x 0.127-0.457, y 0.01-0.50; BL x 0.127-0.459, y 0.47-0.96; TR x 0.455-0.786, y 0.01-0.50
- Track: enters from the left at y~0.70 into BL, down to y~0.80, right to x~0.34, up the column x~0.33 into TL, left to x~0.24, up to y~0.17, right along the top (y~0.17) through TL into TR, down x~0.60 to y~0.40, right to the exit at x~0.85, y~0.40 (between ...
- Per-quadrant best ninja coverage (geometry): TL 26% at (0.323,0.283); TR 18.5% at (0.521,0.274); BL 17% at (0.302,0.504) or 17% at (0.15-0.20,0.73-0.76); BR 11%; left strip 12% (entrance only); right strip 10% (exit only).

**Towers that work:**

- heli 2-0-5 / 5-2-0: Global, flies under the panes, pad outside the garden = always upgradable. Wiki recommends Comanche Commander
- ninja 4-0-2: BlueCliff Hard main DPS, in the TL pocket right of the fountain (26% of track), upgraded only on TL rounds.
- alchemist 4-0-1: BlueCliff Hard x2 next to the TL towers; fandom: top path mostly unaffected by glass.
- wizard 4-0-2: BlueCliff Hard (3-0-2 after R41, 4-0-2 after R49) in TL.
- village 5-2-0: BlueCliff Hard: 4-2-0 then Primary Expertise 5-2-0, bought on BL rounds (57, 77).
- bomb 4-2-0 and 0-2-4: BlueCliff Hard late game (after R57 / R61, TL rounds); fandom: Striker Jones + bombs near the entrance is solid.

**Avoid:** engineer (Overclock must click its target through the glass); farm (bank collection needs clicks the glass blocks; no room outside the garden); spike (does not fit on the open right strip by the exit).

**Builds (in buy order):**

*hard* - BlueCliff Hard (Quincy; ninja/alch/wizard/bombs in the top-left quadrant, village in bottom-left) (hero: Quincy; youtube description, ~v33-35 (3 years old), no Monkey Knowledge, no farms). Source: https://www.youtube.com/watch?v=ZYkvNNxSP_I

  Note: '~' = wait until the round ends, then buy. HUD round in [] = the round shown when the purchase happens, with the open quadrant.; R3 [3, TR open]: place Quincy (spot not given; TR is the open quadrant on R3 - or use the always-open left strip); R6 [6, TL]: place Ninja (TL pocket right of the fountain); after R9 [10, TL]: Ninja 1-0-1; after R13 [14, TL]: Ninja 2-0-2; after R17 [18, TL]: Ninja 3-0-2; after R21 [22, TL]: Alchemist (right) 2-0-0, target Strong; after R29 [30, TL]: Alchemist (right) 3-0-1; R34 [34, TL]: Ninja 4-0-2; after R37 [38, TL]: Alchemist (right) 4-0-1; after R41 [42, TL]: Wizard 3-0-2; after R49 [50, TL]: Wizard 4-0-2; after R56 [57, BL]: Village 4-2-0 (in BL, next to the TL/BL divider); after R57 [58, TL]: Bomb (right) 4-2-0; after R61 [62, TL]: Bomb (left) 0-2-4; after R76 [77, BL]: Village 5-2-0; after R77 [78, TL]: Alchemist (left) 4-0-1; GG at R80

*chimps* - OneEyedDeacon CHIMPS: Rosalia + Flying Fortress (v50.0) (hero: Rosalia; youtube description, v50.0 (full run: https://www.youtube.com/watch?v=I0ko3CZJEAU)). Source: https://www.youtube.com/watch?v=u0-X2o8hfQQ

  R6 [TL open]: Desperado1 0-0-0 next to the fountain + Desperado2 0-0-0 bottom-left of the fountain, seeing the start of the track; R9: Druid1 0-0-0 in front (under the entrance track, left strip); R13: Rosalia in front (over the entrance track, left strip); guide moves her to the bend (micro); R14: Druid1 0-1-0; R18 [TL]: Sniper1 0-1-0 on the bench, Strong; R21: Rosalia ability (scatter missile); R22: Druid1 0-3-0; R26 [TL]: Sniper1 0-2-1, target First; R27: Druid1 1-3-0; R30 [TL]: Sniper1 0-2-2; R32: Village1 0-0-0 above Rosalia (left strip); R33: Ace1 0-0-0 above Village1 (left strip); R34: Ace1 0-0-1; R35: Ace1 0-0-2, centered path on the top-right (bot cannot set this); R37: Ace1 0-0-3; R38: Ace1 2-0-3; R40: Alchemist1 3-0-0 above Ace1; R42: Village1 0-2-0; R43: Alchemist1 3-2-0; R44: Village1 2-2-0; R56: Ace1 2-0-4; R88: Ace1 2-0-5 (during the round)

*chimps* - inferred bot-friendly CHIMPS adaptation (BlueCliff layout + heli/sniper on the open strips) (hero: Quincy (or Etienne); inferred, adapts BlueCliff Hard + wiki heli advice; untested). Source: https://www.youtube.com/watch?v=ZYkvNNxSP_I

  R6 [TL]: Ninja at (0.323,0.283) + Desperado/Dart in the TL pocket; Quincy on the left strip (0.051,0.624) so he never needs the pane; R10 [TL]: Ninja 1-0-1 / 2-0-1 (buy everything for TL towers only on rounds 10,14,18,22,26,30,34,38,42,46,50,...); R14,R18 [TL]: Ninja 2-0-2 -> 3-0-2; Sniper 0-1-0 -> 0-2-2 on the TL bench (0.17,0.24); R22,R26,R30 [TL]: Alchemist next to the ninja 2-0-0 -> 3-0-1 -> 4-0-1; Ninja 4-0-2 by R34; Any round (open strip): Heli at (0.051,0.777) 2-0-0 (Pursuit) as soon as affordable after the ninja line, then 2-0-3 -> 2-0-4 -> 2-0-5 Comanche Commander by ~R80; Any round: Village 0-2-0 / 2-2-0 on the left strip (0.051,0.504) within range of the heli pad; Sniper 4-0-2 / 0-2-5 at (0.051,0.92) on the lower left strip; TL rounds 42-62: Wizard 4-0-2 and Bombs (4-2-0, 0-2-4) in TL as in BlueCliff; BL rounds 57/77: Village 4-2-0 -> 5-2-0 at (0.30,0.53); Rule for the bot: never queue an upgrade for a pane tower unless its quadrant is open now

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC og: Monarch Of Storms 5-0-2 + Geraldo lvl 20 (Chainsaw, v33.0); LTC heroless: Monarch Of Storms 5-0-2 + Golden Justice 2-5-0 (Kyara, v50.2); LTC cheapest: Monarch Of Storms 5-0-2 + The Blazing Sun 5-2-0 (urhere, v54.0); LCC $50,495 (bolaris, v34.2).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 7 spots - sniper, heli, village, ace, ninja, alchemist; hero etienne.
Map strategy: `strategies/maps/coveredgarden_hard.yaml`.

**Sources:**

- https://www.bloonswiki.com/Covered_Garden - Blooncyclopedia: Covered Garden
- https://bloons.fandom.com/wiki/Covered_Garden - Bloons fandom wiki: Covered Garden
- https://bloons.fandom.com/wiki/Covered_Garden/Strategies - fandom: Covered Garden/Strategies
- https://www.youtube.com/watch?v=ZYkvNNxSP_I - BlueCliff - Covered Garden Hard (Quincy)
- https://www.youtube.com/watch?v=u0-X2o8hfQQ - OneEyedDeacon - EASY Covered Garden Chimps w/ Flying Fortress (v50.0)
- https://www.youtube.com/watch?v=euheMfjy8Ho - BlueCliff - Covered Garden ABR (Quincy)
- https://www.youtube.com/watch?v=VFM94v1p7dg - H2K Zeus - Covered Gardens Chimps (Apache Prime strat)

### Ancient Portal

*Intermediate map. Bot record (logs/results.jsonl, 2026-10-22): medium **defeat at round 54** (hard_ninja_alch_sniper, 83 lives lost); hard won (double_hp_sniper_sun); easy won (starter_tack_dart); primary_only won (starter_tack_dart); deflation **defeat at round 54** (solo_spike, 194 lives lost).*

**Key insight.** One entrance spirals clockwise into a portal; bloons leave through the right lane unless the free 'Realign Portal' device at the bottom centre is clicked (the bot never clicks it). A lone Spike Factory by the exit sees under 40% of the right lane and none of the spiral (Deflation lost at round 54). Put ninjas and an alchemist on the land strip inside the spiral, the hero on the pedestal below it (+1 damage, +30% range for heroes) and boats/subs in the pond.

**Lanes (single).** spiral from the top into the portal, then the right lane (default) or the walled left lane (only after clicking the realign device)

**What the guides found** (detail from the sources):

- Portal realignment: clicking the scientist's device at the bottom centre (click area ~x 0.35-0.46, y 0.79-0.95) switches which exit portal is active; free, 10 s cooldown (bloonswiki
- Hero pedestals (heroes only): A topmost, inside the spiral near the entrance (x 0.554-0.610, y 0.162-0.262; centre ~(0.58,0.21)): camo detection + MIB; B below the spiral between spiral and right lane (x 0.588-0.643, y 0.385-0.485
- Totems: 15,000 pops within 70 units of the top-right portal charge the stone monkey carvings; clicking them when lit blasts every bloon on screen for 50 damage and stuns 9 s (bot cannot click yet).
- Boss bloons use a separate reversed route (bottom-right -> over both portals -> bottom-left); irrelevant outside boss events. Necromancer undead bloons and Sauda's charge behave oddly on the right lane because of it (fandom).

**Towers that work:**

- ninja 4-0-2: BlueCliff Hard + Eleado Deflation core; inside the spiral it reaches ~60% of the spiral (geometry).
- alchemist 4-0-1 / 4-2-0: Buffs the ninjas (BlueCliff Hard 4-0-1, Eleado Deflation 4-2-0, SnartFarts CHIMPS 4-2-0).
- boomerang 5-0-2: Glaive Lord carry in BlueCliff Hard (3-0-2 R39 -> 5-0-2 R65); between spiral and right lane it reaches both (geometry 0.66,0.453).
- sub 2-0-4: BeatbloonsBob CHIMPS core (Quincy + sub 2-0-4 in the pond): pond covers ~51% of the right lane
- wizard 5-2-0: Wizard Lord Phoenix in BeatbloonsBob CHIMPS (phoenix flies map-wide).
- glue 5-2-0: The Bloon Solver in BeatbloonsBob CHIMPS.

**Avoid:** spike (from the exit it sees under 40% of the right lane and nothing of the spiral (solo Spike Factory lost Deflation at R54), only in deflation).

**Removable obstacles and map switches:**

- Realign Portal device (free switch) (free): optional; keep the default right lane for the ninja/sub plans below. Only switch to the left (ruins) lane for short-range builds placed inside the ruins.. Changes the exit lane; 10 s cooldown.
- Totem blast (stone monkey carvings) (free): click whenever lit (after 15,000 pops near the top portal) - e.g. on MOAB/ceramic rushes. 50 damage to every bloon on screen + 9 s stun.

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff Hard (Quincy, ninja + alch, Glaive Lord, Primary village) (hero: Quincy; youtube description, ~v45 (2 years old), no Monkey Knowledge, no farms). Source: https://www.youtube.com/watch?v=-QdOnx826eA

  '~' = wait until the round ends, then buy; R3: Quincy; R6: Ninja; R8: Ninja 1-0-0; R9: Ninja 1-0-1; R11: Ninja 2-0-1; R14: Ninja 2-0-2; R17: Ninja 3-0-2; after R27: Alchemist 3-0-0, target Strong; R33: Ninja 4-0-2; after R37: Alchemist 4-0-1; R39: Boomerang 3-0-2; R41: Boomerang 4-0-2; R45: Village 3-2-0; R48: Village 4-2-0; R65: Boomerang 5-0-2; R79: Village 5-2-0

*chimps, used for the 'chimps' hints* - BeatbloonsBob CHIMPS 'No RNG' (Quincy, sub, alch, WLP, Bloon Solver, Perma-Spike) (hero: Quincy; youtube description, ~v54-55 (8 months old); order only, no rounds). Source: https://www.youtube.com/watch?v=RtSL6RUWAO4

  Quincy; Sub 2-0-1; Alchemist 2-0-0 (Strong); Sub 2-0-3; Alchemist 3-0-1; Sub 2-0-4; Wizard 4-2-0; Village 2-0-0; Glue 4-2-0; Village 3-2-0; Glue 5-2-0; Wizard 5-2-0; Village 4-2-0; Alchemist 4-0-1; Spike Factory 2-0-5 on Smart

*deflation, used for the 'deflation' hints* - Eleado Deflation AFK: 3 ninjas 4-0-2 + alch 4-2-0, no hero (hero: none; youtube description, ~v45-46 (2 years old), no MK). Source: https://www.youtube.com/watch?v=OmUQCYE8XQw

  Start ($20,000): buy everything at once: 3x Ninja 4-0-2 + Alchemist 4-2-0 (Easy = 85% of Medium: ninja 4-0-2 ~$4,675 each, alch 4-2-0 ~$5,205 -> ~$19,230 of the $20,000); Then just play R31-60 (AFK)

*chimps* - SnartFarts CHIMPS no ability/no micro (Obyn, ninja/alch, Spirit of the Forest, Popseidon, Flagship) (hero: Obyn Greenfoot; youtube description, v52.2; order only). Source: https://www.youtube.com/watch?v=QbIVmJ2EPKU

  Ninja; Ninja 2-0-1; Obyn; Ninja 3-0-1; Alchemist; Alchemist 3-2-0; Ninja 4-0-1; Alchemist 4-2-0; Druid; Druid 1-4-0; Mermonkey; Mermonkey 0-4-2; Druid 1-5-0; Mermonkey 0-5-2; Village; Village 2-3-0; Buccaneer; Buccaneer 5-2-0

*deflation* - Wiki general Deflation: 3 Neva-Miss aces (2-0-3) + alch 4-0-0 + village 0-2-0 + hero (hero: any (Quincy/Obyn); wiki, page last updated v57.1; not map-specific). Source: https://www.bloonswiki.com/Strategy:Deflation_(BTD6)

  Start: Monkey Village 0-0-2 (Monkey Commerce) for the discount if it fits the plan, then 2-3 Monkey Ace 2-0-3 (Neva-Miss) + Alchemist 4-0-0 + Village 0-2-0 + hero; Wiki: two Neva-Misses also work on the vast majority of maps; Aces need no aiming (default circle path); Neva-Miss darts seek bloons.

Other builds found:

- deflation: InstantKarma Deflation: Crossbow Master dart (hero: unknown) - https://www.youtube.com/watch?v=y4jZzmSDBLs

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC heroless: Cannon Ship 0-3-2 + The Anti-Bloon 0-5-2 (depression, v45.1); LTC og: Quincy lvl 20 + The Anti-Bloon 0-5-2 (explodingkitten, v45.0); LTC cheapest: Lord Of The Abyss 5-0-1 + Geraldo lvl 20 ($62,990, Luxray, v55.2); LCC $13,710 (Capsen, v51.2). Also a Deflation R100 run with only $575 using a Geraldo free-item bug (v56.2, BTD6 Index video juXBvg0cPEI).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 5 spots - ninja, alchemist, boomerang, village; hero quincy; 'chimps' (impoppable, chimps): 7 spots - sub, alchemist, wizard, glue, village, spike; hero quincy; 'deflation' (deflation): 4 spots - ninja, alchemist.
Map strategy: `strategies/maps/ancientportal_deflation.yaml`.

**Sources:**

- https://www.bloonswiki.com/Ancient_Portal - Blooncyclopedia: Ancient Portal
- https://bloons.fandom.com/wiki/Ancient_Portal - Bloons fandom wiki: Ancient Portal
- https://www.youtube.com/watch?v=-QdOnx826eA - BlueCliff - Ancient Portal Hard (Quincy)
- https://www.youtube.com/watch?v=RtSL6RUWAO4 - BeatbloonsBob - Ancient Portal CHIMPS Guide Easy (No RNG)
- https://www.youtube.com/watch?v=QbIVmJ2EPKU - SnartFarts - Ancient Portal CHIMPS no ability no micro (v52.2)
- https://www.youtube.com/watch?v=OmUQCYE8XQw - Eleado - Ancient Portal Deflation AFK
- https://www.bloonswiki.com/Strategy:Deflation_(BTD6 - Blooncyclopedia: Strategy:Deflation (BTD6)

### Bloonarius Prime

*Intermediate map. Bot record (logs/results.jsonl, 2026-10-22): easy won (starter_tack_dart); primary_only won (starter_tack_dart); deflation **defeat at round 49** (solo_spike, lives lost not recorded).*

**Key insight.** On prime-numbered rounds bloons drop into a swamp hole by the entrance and take the short right lane; every other round uses the long left lane. No land spot covers both lanes well, so a Spike Factory at one exit cannot hold the map (Deflation lost at round 49). Use global towers (aces, heli, snipers with sight of both lanes) or one defence per lane.

**Lanes (alternating).** prime rounds (2, 3, 5, 7, 11, ... 97): short right lane exiting top-right; other rounds: long left lane looping the left lake and exiting at the bottom

**What the guides found** (detail from the sources):

- Prime-round whirl path: on prime-numbered rounds the swamp holes open (vortex shown near the entrance at round start) and bloons take the right-hand prime path; all other rounds use the long composite path. Round 2 is prime since v33.3.
- Prime rounds 1-100: 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97.
- No Purple bloons on the prime lane before R101 and no DDTs on the prime lane in standard rounds (<=140) - the prime-lane defense needs no DDT/purple answer; the composite lane must handle DDTs and the R100 BAD (bloonswiki tips).
- Boss bloons use a special path (composite loop, across the rocks, then the prime path).

**Towers that work:**

- heli 2-0-4 / 5-2-0: Wiki: excels on the alternating lanes thanks to unlimited flying range; bot-friendly with Pursuit.
- ace 2-0-5 / 2-0-3: OneEyedDeacon CHIMPS carry (Flying Fortress, v49.3); BlueCliff Hard uses Ace 2-0-3 -> 2-0-4
- ninja 4-0-2: BlueCliff Hard main early/mid DPS with alch (right) 4-0-1 and alch (left) 4-0-1.
- alchemist 4-0-1: BlueCliff Hard: two alchs (right side first, left side at R69).
- boomerang 2-0-4: BlueCliff Hard R39 (MOAB Press + ability on ceramics R40).
- sniper 0-2-2 / 4-0-2: Global with good sight from the bottom centre / entrance (geometry); OneEyedDeacon sniper 0-2-2 'on bottom'

**Avoid:** spike (sits at one of two exits while the lanes alternate (solo Spike Factory lost Deflation at R49)).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff Hard (Quincy; ninja + 2 alchs, MOAB Press, Spectre ace, village, sniper) (hero: Quincy; youtube description, ~v31-33 (3 years old), no Monkey Knowledge, no farms). Source: https://www.youtube.com/watch?v=oIiUcr4qJAw

  '~' = wait until the round ends, then buy; R3: Ninja; after R3: Dart (left); R5: Dart (right); after R8: Quincy; R10: Ninja 1-0-0; R11: Ninja 1-0-1; R13: Ninja 2-0-1; R14: Ninja 2-0-2; R18: Ninja 3-0-2; after R25: Alchemist (right) 2-0-0, target Strong; guide sells Dart (right) here (bot: skip the sale); after R26: Alchemist (right) 3-0-0; R33: Ninja 4-0-2; after R34: Alchemist (right) 3-0-1; R39: Boomerang 2-0-4; R40: boomerang ability on ceramics (bot: press when ready); after R41: Alchemist (right) 4-0-1; R45: Village 2-0-0; R48: Ace 2-0-3; R49: Village 2-2-0; R61: Ace 2-0-4; after R69: Alchemist (left) 4-0-1; R74: Sniper 4-0-2, Strong

*chimps, used for the 'chimps' hints* - OneEyedDeacon CHIMPS: Rosalia + Flying Fortress (v49.3) (hero: Rosalia; youtube description, v49.3 (full run https://www.youtube.com/watch?v=bXFrGX1x9Ps)). Source: https://www.youtube.com/watch?v=mLpg86Zc7Rs

  R6: Dart1 0-0-0 on Strong at the left top intersection + Dart2 0-0-0 between the tracks at the bottom; R7: Sub1 0-0-0 on the right, splitting the 2 halves of the right lane; R8: Dart3 0-0-0 at the bottom-left intersection; R10: Sniper1 0-0-0 on Strong at the bottom; R14: Rosalia on top (leave room for a village above her); guide moves her left/right on R19/R20 (micro); R16: Druid1 0-0-0 on the right; R17: Druid1 0-1-0; R21: Rosalia grenade + scatter missile (micro); R22: Druid1 0-3-0; R24: Sniper1 0-1-0; R25: Druid1 1-3-0; R27: Sniper1 0-1-1; R28: Sniper1 0-1-2; R29: Sniper1 0-2-2 on First; R35: Village1 0-0-2; R36: Ace1 0-0-2; R38: Ace1 0-0-3; R39: Ace1 2-0-3; R40: Rosalia jetpack + scatter missile; R42: Village1 0-2-0 (guide writes 020); R43: Village1 2-2-0; R44: Alchemist1 3-0-0; R45: Alchemist1 3-2-0; R56: Ace1 2-0-4; R89: Ace1 2-0-5

*deflation* - inferred Deflation for Bloonarius Prime: Neva-Miss aces (wiki general) - covers both lanes (hero: Quincy (or Psi); inferred, wiki general Deflation build applied to this map). Source: https://www.bloonswiki.com/Strategy:Deflation_(BTD6)

  Start ($20,000): (optional) Village 0-0-2 Monkey Commerce first for the discount; 2-3 Monkey Ace 2-0-3 (Neva-Miss); Alchemist 4-0-0 in range of the aces; Aces are global and lane-independent, so prime and composite rounds are both covered; no aiming needed.; If cash remains: Sniper 0-2-2 at (0.25,0.20) on Strong (sees the whole composite lane and 44% of the prime lane).

*chimps* - inferred water build: one buccaneer group per lake (hero: Admiral Brickell; inferred, geometry-based, untested). Source: map geometry (data/map_geometry)

  Composite lake (left): Buccaneer at (0.243,0.717) 3-2-0 -> 4-2-0 (51% of the composite lane); Prime lake (right): Buccaneer at (0.639,0.283) 3-2-0 -> 4-2-0 (50% of the prime lane); Sub 2-0-4 at (0.655,0.453); Brickell in either lake; Carrier Flagship 5-2-0 (map-wide planes) as the late-game carry; snipers at (0.25,0.20)/(0.80,0.60) for camo/leads per lane

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC og & cheapest: Perma Charge 0-5-2 + Geraldo lvl 20 (Tremen, v31.0); LTC heroless: Glaive Lord 5-0-2 + M.A.D 2-5-0 (Ryan Mehalic, v44.1); LCC $30,825 (NoMercy, v49.3) / $44,235 (Chainsaw, v31.1). 2TC exists (Mehalic POPs, V-ZbZ95-QbM).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 9 spots - ninja, dart, alchemist, boomerang, ace, sniper; hero quincy; 'chimps' (impoppable, chimps): 9 spots - dart, sub, sniper, druid, village, ace; hero rosalia; 'deflation' (deflation): 3 spots - sniper, ace.
Map strategy: `strategies/maps/bloonariusprime_deflation.yaml`.

**Sources:**

- https://www.bloonswiki.com/Bloonarius_Prime - Blooncyclopedia: Bloonarius Prime
- https://bloons.fandom.com/wiki/Bloonarius_Prime - Bloons fandom wiki: Bloonarius Prime
- https://www.youtube.com/watch?v=oIiUcr4qJAw - BlueCliff - Bloonarius Prime Hard (Quincy)
- https://www.youtube.com/watch?v=mLpg86Zc7Rs - OneEyedDeacon - Bloonarius Prime Chimps with the BIG PLANE (v49.3)
- https://www.youtube.com/watch?v=zK3Q3JzP8k4 - MaxMonki - Bloonarius Prime CHIMPS (Obyn, no abilities)
- https://www.bloonswiki.com/Strategy:Deflation_(BTD6 - Blooncyclopedia: Strategy:Deflation (BTD6)
- https://www.youtube.com/watch?v=iBCl0MNnc0g - Bacanator Gamer - Bloonarius Prime Deflation with Psi

### Castle Revenge

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): hard **defeat at round 46** (hard_ninja_alch_sniper, 77 lives lost).*

**Key insight.** Two lanes run at the same time along the top and bottom castle walls; bloons are invulnerable while climbing the wheels (38% of the track). No ground spot lets a short-range tower hit both lanes, so one cluster leaks the other lane (lost at round 46). Build mirrored pairs (one per lane, in the right-hand corners) and lean on global towers: four snipers in the courtyard quarters, an ace on the raised central platform.

**Lanes (simultaneous).** top lane and bottom lane at the same time, both exiting on the left

**What the guides found** (detail from the sources):

- 4 entrances (2 wheel, 2 water routes) + MOAB routes straight to the plow; all merge into a top and a bottom lane that run simultaneously to 2 exits on the left (top (0,0.37), bottom (0,0.61)). Bloons are invulnerable until past the wheels
- Raised central platform (LandTop, x 0.218-0.533, y 0.352-0.570, height 31) inside sight-blocking walls (BlockingMiddle, height 30): wiki 'Towers may be placed on the platform to see the whole track'.
- Courtyard sniper sight (geometry, ground level): top-right (0.548,0.325) 84% top / 30% bottom; bottom-right (0.558,0.683) 83% bottom / 29% top; top-left (0.20,0.317) 80% top / 35% bottom; bottom-left (0.19,0.683) 78% bottom / 32% top.
- Best lane spots (geometry): top lane - ninja (0.612,0.232) 32%, dart (0.628,0.223) 26%, spike (0.601,0.257) 32%, buccaneer in the top-left pond (0.152,0.249) 40%

**Towers that work:**

- sniper 0-2-5 / 0-5-2 / 5-2-0 / 4-0-2: Global; Elite Defender is in the heroless LTC; OneEyedDeacon's Axis of Havoc CHIMPS
- dart 4-0-2 / 3-2-0: Wiki: Spike-o-pult/Juggernaut near the last bend of each side (walls bounce)
- spike 2-5-0: Wiki: Carpet of Spikes covers both lanes and breaks ZOMG shells; in the heroless LTC.
- ace 2-0-4: Spectre in BlueCliff Hard (R29-R35) and SnartFarts CHIMPS; global, ignores the walls.
- heli 2-0-5 / 2-0-4: SnartFarts CHIMPS: three helis (2-0-5 + 2x 2-0-4). Pursuit follows bloons on both lanes.
- alchemist 4-2-0 / 5-2-0: Brews the snipers (OneEyedDeacon Perma-Brew 5-2-0; BlueCliff 4-0-1).

**Avoid:** beast_handler (Giant Condor needs its drop-off point set by hand).

**Removable obstacles and map switches:**

- Pressure valve / Engine (paid switch, re-usable) ($500): mid/late game when a dense non-MOAB rush is about to leak (e.g. R63 ceramics, R76-R78) and $500 is spare; every 75 s at most. 15 s of strong knockback on non-MOAB bloons near the exits.

The pressure valve between the exits ($500, knocks back non-MOAB bloons for 15 s, 75 s cooldown) is a paid switch, not an obstacle; optional on dense ceramic rounds.

**Builds (in buy order):**

*hard, used for the 'hard' hints* - inferred bot-friendly mirrored build (hero: Quincy; inferred, mirrors BlueCliff/OneEyedDeacon ideas; untested). Source: map geometry (data/map_geometry)

  R1-6: Dart/Ninja at the top-right corner (0.612,0.232) AND at the bottom-right corner (0.612,0.76) - always buy in pairs; R6-15: Quincy on the platform (0.37,0.40); Sniper at (0.548,0.325) and (0.558,0.683) (one per lane), Strong; R15-35: both corner ninjas 3-0-2 -> 4-0-2 (or darts 4-0-2 Juggernaut), one Alchemist 3-0-1 per corner (0.59,0.283) / (0.59,0.717); R35-60: Sniper top 0-2-5 Elite Defender, sniper bottom 4-0-2 / 0-2-5; Ace 2-0-4 on the platform; R60-80: Village 2-3-0 / alchs 4-0-1; buy the $500 valve on dense ceramic rounds if leaking

*chimps, used for the 'chimps' hints* - OneEyedDeacon CHIMPS: Psi + Axis of Havoc (v50.0) (hero: Psi; youtube description, v50.0 (full run https://www.youtube.com/watch?v=9sVGDOkJS4Q)). Source: https://www.youtube.com/watch?v=XUfUa1MSU9g

  R6: Dart1 0-0-0 on top + Dart2 0-0-0 in the middle + Dart3 0-0-0 on the bottom; R8: Sub1 0-0-0; R9: Dart4 0-0-0 during the round; R11: Sniper1 0-0-0 on Strong (as far back as possible); R13: Sniper2 0-0-0 Strong; R14: Sniper3 0-0-0 Strong; R19: Psi in front on Strong (or during R18); R20: Dart3 0-2-0; R21: Dart3 2-2-0; R22: Dart3 3-2-0; R23: Sniper1 0-1-0; R25: Sniper1 0-2-0 on First; R27: Sniper3 1-0-0; R28: Sniper1 0-2-1; R29: Sniper1 0-2-2; R35: Sniper1 0-2-3; R39: Sniper1 0-2-4; R49: Sniper1 0-2-5 (during the round); R50: Village 2-0-2; R52: Sniper2 0-3-2 ON FIRST; R54: Alchemist1 3-2-0 for Sniper1 and Sniper2; R59: Sniper2 0-4-2; R60: Alchemist1 4-2-0; R81-83: Psi stun on BFBs/MOABs (ability); R82: Alchemist1 5-2-0 (during the round); R84: Sniper3 3-2-0; R85: Sniper3 4-2-0; R89: Sniper1... guide writes '052 sniper1 ON FIRST' (= Sniper2 0-5-2 Elite Sniper); R91-93: Sniper4/5/6 0-3-2; R95: Psi stun when the fourth DDT arrives; R99: Sniper3 5-2-0; R100: 3x tack sprayers

*hard* - BlueCliff Hard (Quincy, 4 snipers, Spectre ace, alch, village) (hero: Quincy; youtube description, ~v42-44 (2 years old), no Monkey Knowledge, no farms). Source: https://www.youtube.com/watch?v=au45yv7NhS8

  '~' = wait until the round ends, then buy; R3: Sniper (bottom right); after R3: Sniper (top right); R6: Sniper (top left); R9: Sniper (bottom left); after R10: Quincy; R13: Sniper (bottom right) 1-0-0, set Strong; R15: Sniper (bottom right) 1-0-1; Quincy lvl 3 ability; R17: Sniper (bottom right) 1-0-2; R19: Sniper (top right) 0-2-0; R21: Quincy ability; Sniper (top right) 0-2-1; R22: Sniper (top right) 0-2-2; R29: Ace 0-0-2; R34: guide sells Sniper (top left) and Sniper (bottom left) to fund Ace 0-0-3 (bot cannot sell: keep them and buy the ace upgrade when affordable); R35: Ace 2-0-3; after R37: Alchemist 3-0-0; after R38: Alchemist 3-0-1; R41: Village 1-2-0; R42: Village 2-2-0; after R45: Alchemist 4-0-1; R47: Sniper (top) 0-2-3; R49: Sniper (top) 0-2-4; R55: Sniper (top) 0-2-5; R61: Village 2-3-0; R64: Sniper (bottom) 3-0-2; R67: Sniper (bottom) 4-0-2; R76: guide sells Sniper (bottom) and buys Ace 2-0-4, then rebuys Sniper (bottom) 4-0-2 on Strong at R79 (bot: just buy Ace 2-0-4 when affordable, keep the sniper)

*chimps* - OneEyedDeacon CHIMPS: Sauda (v53.1) - more consistent than Axis (hero: Sauda; youtube description, v53.1 (full run https://www.youtube.com/watch?v=s0EoNASn5PY)). Source: https://www.youtube.com/watch?v=JfjH7gMVRGw

  R6: Dart1 0-0-0 on top (lined with the track) + Dart2 0-0-0 in the middle + Dart3 0-0-0 on the bottom (lined with the left part); R8: Sub1 0-0-0; R9: Dart4 0-0-0 during the round; R12: Sauda on the bottom; R14: Sniper1 0-0-0 Strong; R15: Sniper1 1-0-0; R16-19: Dart1 1-0-0 -> 2-0-0 -> 2-0-2 -> 3-0-2; R22-23: Dart3 3-0-0 -> 3-0-2; R29: Dart1 4-0-2; R30: Tack1 0-0-2 on top (as far left as possible, bottom-right range border touching the track); R31-33: Tack1 1-0-2 -> 1-0-3 -> 2-0-3; R37: Tack1 2-0-4; R40: Alchemist1 3-0-0 for Tack1; R41: Dart3 4-0-2; R42: Village1 0-0-2 on top (as far left as possible, just covering the middle dart); R43: Alchemist1 3-2-0; R45: Village2 0-0-2 on the bottom; R46: Wizard1 1-0-3 (double discounted, as central as possible); R48: Wizard1 1-0-4; R49: Wizard2 0-2-2 on the bottom; R50: Wizard2 0-3-2; R51: Village1 3-0-2 + Village2 3-0-2; R55: Ice1 4-1-0 on top; R57: Glue1 0-0-3 Strong (double discounted); R59: Alchemist2 3-2-0 for Wizard1; R65/R73: Sauda sword charge on BFBs (ability); R75: Wizard1 1-0-5; R76: Sub1 2-3-0; R80: Sub1 2-4-0 (First Strike on ZOMG); R82: Glue1 0-2-4; R84: Mermonkey1 0-4-1 (double discounted); R85-R100: Mermonkey/First Strike abilities timed on ZOMGs (micro); R94: Sub1 2-5-0; R96: Mermonkey2 0-4-1; R98: Mermonkey3 0-4-1

*chimps* - SnartFarts CHIMPS: Elite Defender + Psi + helis (v52.2) (hero: Psi; youtube description, v52.2; order only; R95-99 uses timed Psi abilities and heli retargeting (micro)). Source: https://www.youtube.com/watch?v=ATtcAJt_G4s

  2x Desperado; Desperado before R8; Sniper; Psi on Strong; Desperado before R16; Desperado during R17; Sniper 0-0-2; Sniper #2; Druid; Druid 0-0-1; Sniper #2 1-0-1; Sniper #1 0-2-5 (Elite Defender); Village; Village 2-2-0; Ace; Ace 2-0-4 with centered path at the back of the map (bot cannot set); Heli; Heli 2-0-5; Village 2-3-0; Heli #2 2-0-4; Heli #3 2-0-4; R95-R99: Psi abilities timed on MOAB/ZOMG/BFB at the corners; helis set to the front then back to Pursuit (micro); Sniper #2 2-0-4

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC og: Spirit Of The Forest 1-5-0 + Dark Knight 0-2-3 + Geraldo lvl 20 (depression, v44.0); LTC heroless: Elite Defender 0-2-5 + Carpet Of Spikes 2-5-0 + Monarch Of Storms 5-0-2 + Juggernaut 4-2-0 (depression, v49.3); LCC $84,070 (VDA, v57.2) / $92,445 (TIM418, v42.3).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 11 spots - ninja, alchemist, sniper, ace, village; hero quincy; 'chimps' (impoppable, chimps): 7 spots - dart, sub, sniper, alchemist; hero psi.
Map strategy: `strategies/maps/castlerevenge_hard.yaml`.

**Sources:**

- https://www.bloonswiki.com/Castle_Revenge - Blooncyclopedia: Castle Revenge
- https://bloons.fandom.com/wiki/Castle_Revenge - Bloons fandom wiki: Castle Revenge
- https://www.youtube.com/watch?v=au45yv7NhS8 - BlueCliff - Castle Revenge Hard (Quincy)
- https://www.youtube.com/watch?v=XUfUa1MSU9g - OneEyedDeacon - Castle Revenge Chimps Psi + Axis of Havoc (v50.0)
- https://www.youtube.com/watch?v=JfjH7gMVRGw - OneEyedDeacon - EASY Castle Revenge Chimps ft. Sauda (v53.1)
- https://www.youtube.com/watch?v=lkrli1pCqCk - OneEyedDeacon - Castle Revenge Chimps SNIPED by Axis of Havoc (v49.3)
- https://www.youtube.com/watch?v=ATtcAJt_G4s - SnartFarts - Castle Revenge CHIMPS ft. Elite Defender (v52.2)

### Dark Path

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): hard **defeat at round 25** (double_hp_sniper_sun, 51 lives lost).*

**Key insight.** One diagonal lane in a sunken gully; rock walls block line of sight almost everywhere, so ground towers 'next to the track' usually see nothing and the game refused the bot's spots (lost at round 25 after a Fast Track start). Build the ninja/alchemist/village cluster in the open pocket by the exit (bottom-left), add a 2-x-x Pursuit heli (Apache Prime later) and a Perma-Spike at the exit.

**Lanes (single).** enters top-right, runs straight down-left, exits bottom-left

**What the guides found** (detail from the sources):

- Single lane, 1 entrance (top-right) / 1 exit (bottom-left), length 18.8 RBS (BTD6 Index), no water at all (the 'river' is the track). Source: https://www.bloonswiki.com/Dark_Path, https://btd6index.win/ (fetch-map-info / fetch-ltc / fetch-lcc map=Dark Path)
- Line of sight: 12 rock walls (WallBlocker1-12, height 24.9) plus 8 buyable walls (height 30) block LOS for ground towers; the map edges are cliffs (height 100). Source: map geometry (data/map_geometry)
- Two raised rock stacks (StepL bbox x0.415-0.492 y0.187-0.319 and StepR bbox x0.570-0.641 y0.636-0.779, height 31) - 'can place up to a Monkey Ace or up to 4 small towers (such as four Sniper Monkeys)'; towers there see over walls (high ground).
- 'The high platform above the center can also be used to place down limited-range towers, both damage and support ones, in addition to global-range towers that cannot see over walls.' Source: https://www.bloonswiki.com/Dark_Path

**Towers that work:**

- heli 5-0-2 (Apache Prime) via 2-0-2 Pursuit: Flies over the walls, global; SnartFarts' v52.2 CHIMPS black border uses 3-0-2 -> 5-0-2 Heli as main DPS.
- ninja 4-0-2: Camo + crowd damage in the exit pocket (0.163,0.802 sees 23% of the track) and the entrance pocket (0.564,0.274 sees progress ...
- alchemist 4-2-0 (CHIMPS) / 4-0-1 (Hard): Buffs the ninja/heli; fits in the exit pocket (0.147,0.743).
- spike 0-2-5 Perma-Spike (or 2-0-5 Spike Storm): Single exit -> exit protection; 'It guarantees victory on this map'. Place in the exit pocket (0.067,0.888 or 0.163,0.794).
- village 2-2-0 -> 2-3-0: Jungle Drums/MIB for the heli and the exit cluster; fits at 0.099,0.794.
- dart 5-2-0 Ultra-Juggernaut: Balls bounce off the walls many times; keep walls, place on low ground near the track (exit pocket).

**Avoid:** tack (no spot outside the exit pocket sees more than ~10% of the lane).

**Removable obstacles and map switches:**

- Bottom-right cave (CaveB) wall bolt, tier 1-4 ($250): optional; tiers cost 250, 500, 1000, 1000. frees ground near the central loop for close-range towers ('removing the first tiers of walls may help place close-ranged towers')
- Top-left cave (CaveA) wall bolt, tier 1-4 ($250): optional; tiers 250, 500, 1000, 1000 ($5,500 for both caves fully). same as above for the top/left half

**Builds (in buy order):**

*chimps, used for the 'hard' hints* - SnartFarts CHIMPS black border ft. Apache Prime (Quincy/Ninja/Alch/Village/Heli/Perma-Spike) (hero: Quincy; youtube description, v52.2). Source: https://www.youtube.com/watch?v=4AAtx2p1bwE

  1 (R6): Quincy; 2: Ninja; 3: Ninja 3-0-2; 4: Alchemist; 5: Alchemist 3-2-0; 6: Ninja 4-0-2; 7: Alchemist 4-2-0; 8: Village; 9: Village 1-0-0; 10: Heli Pilot; 11: Heli 3-0-2; 12: Village 2-2-0; 13: Heli 5-0-2 (Apache Prime); 14: Village 2-3-0; 15: Spike Factory; 16: Spike 0-2-4; 17: second Alchemist; 18: Alchemist #2 4-2-0; 19: Spike 0-2-5 (Perma-Spike); (no round numbers given - buy in this order as cash allows; this build fits the bot: no aiming, Heli has Pursuit from 2-x-x)

*hard* - BlueCliff Hard, no MK, no farms (Quincy, Ninja, Alch, Mortar late) (hero: Quincy; youtube description, v39-40 (video ~3y old)). Source: https://www.youtube.com/watch?v=WZMh1KPqgyQ

  R3: Quincy; R8: Ninja 1-0-0; R10: Ninja 1-0-1; R11: Ninja 2-0-1; R13: Ninja 2-0-2; R16: Ninja 3-0-2; R26 (after round): Alchemist 3-0-0, target Strong; R35: Ninja 4-0-2; R37 (after round): Alchemist 4-0-1; R40: Quincy level-3 ability (optional); R45: Mortar 3-2-0; R46: Mortar 4-2-0; R62 (after round): sell Ninja + Alchemist, Mortar 5-2-0; R64: Village 0-2-0; R65: Village 2-2-0; R70 (after round): Alchemist 4-0-1; R75: Sniper 4-0-2, target Strong; GG (R80); BOT ADAPTATION (inferred): Mortar needs a target point - replace with Heli 2-0-2 -> 4-0-2/5-0-2 and Perma-Spike at the exit; skip the sell step.

*chimps* - BTD6 BluePrint 'Lazy CHIMPS' - Ultra-Jugg + Blazing Sun, 8 stops, no abilities, 63k spare (hero: Etienne; youtube description, recent (posted ~1 month before Oct 2026, v56-57)). Source: https://www.youtube.com/watch?v=eyIX-967nps

  R6: Desperado + Skywarden; Desperado -> Strong; R9: Dart Monkey; Skywarden -> Strong; R12: Etienne; R19: Dart 3-2-0; R28: Dart 4-2-0; R37: Desperado 3-2-0, Ice Monkey 3-2-0; R57: Dart 5-2-0 (Ultra-Juggernaut), Desperado 4-2-0, Ice 4-2-0, Skywarden 2-0-0; R85: Desperado 5-2-0, Ice 5-2-0 (Super Brittle), Tack 2-0-5 (Tack Zone), Village 3-0-0; R100: win; Rounds listed are the LATEST safe buy points; buying earlier is fine.; Keep the walls (Ultra-Jugg ricochets off them).

*chimps* - bloon.games CHIMPS (Obyn, Sniper Elite Defender, Druid Superstorm, Spike Storm) (hero: Obyn Greenfoot; web guide, posted 2024-10-26 (v44-45)). Source: https://bloon.games/how-to-beat-chimps-on-dark-path/

  Obyn; use his abilities early; Engineer + Dart Monkey; Sniper; Sniper 0-2-2 (bottom path first); Buy the two lower wall layers (cave clicks), then Village 1-0-2; Sniper 0-2-3; Before R40: Sniper 0-2-4 Full Auto Rifle; Village Jungle Drums; Alchemist 3-2-0 next to the Sniper; Sniper 0-2-5 Elite Defender; Druid 4-0-2; R83: Druid 5-0-2 Superstorm; Before R95: Spike Factory 2-0-5

*magic_only* - BlueCliff Magic Monkeys Only, no MK (Quincy, Ninja 4-0-2, Alch 4-0-1, Druid 2-5-0, Super 3-0-2) (hero: Quincy; youtube description, ~v45 (video ~1y old)). Source: https://www.youtube.com/watch?v=NbOGgMgqil0

  R3: Quincy; R7: Ninja; R8: Ninja 0-0-1; R9: 1-0-1; R11: 2-0-1; R13: 2-0-2; R17: 3-0-2; R21 (after round): Alch 2-0-0 Strong; R26: Alch 3-0-0; R28: Alch 3-0-1; R34: Alch 4-0-1; R37: Ninja 4-0-2; R39: Druid 2-3-0; R40: Quincy ability; R44: Druid 2-4-0 (use the druid ability whenever available - bot presses it blindly); R50 (after round): sell Ninja, Super Monkey 2-0-2 (bot: keep the ninja, just add the Super); R58: Super 3-0-2; R63: Quincy level-10 ability (optional); R75: sell Alch, Druid 2-5-0 (bot: keep alch); R78: Alch 4-0-1; GG

Other builds found:

- abr: BlueCliff Alternate Bloons Rounds, no MK (Ninja, Sniper, Quincy, Bomb, Heli 4-0-2, Village, Glue) (hero: Quincy) - https://www.youtube.com/watch?v=YxWFC5r7fD8
- impoppable: BlueCliff Impoppable, no MK (Quincy, Ninja 4-0-2, Alch, Sniper 2-5-0 Elite Sniper, Mortar 5-2-0, Heli 2-0-5) (hero: Quincy) - https://www.youtube.com/watch?v=Pbc_B8VGmMc
- chimps: Negativezer0 Dark Path CHIMPS v57 (tower list only) (hero: Quincy) - https://www.youtube.com/watch?v=Fz2ne-F_X3w
- medium/hard (inferred bot opener for a ...: inferred: what to buy with ~$9,700 at R22 so R22-25 do not leak (hero: Quincy or Etienne) - map geometry (data/map_geometry) ; btd6bot docs/strategy_ideas.md + logs/bot.log (2026-10-22 loss analysis)

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC (2-tower CHIMPS): og = MOAB Domination 0-2-5 Ace + Geraldo (v39.0, pinescutely); cheapest = Wizard Lord Phoenix 2-5-0 + Etienne; heroless = Glaive Lord 5-0-2 + M.A.D 2-5-0 (v41.2). LCC $41,585 (v39.0). Strong evidence that flying/global towers (Ace, Etienne, Phoenix, MAD) and wall-ricochet boomerangs dominate here.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 8 spots - ninja, alchemist, village, heli, spike; hero quincy.
Map strategy: `strategies/maps/darkpath_hard.yaml`.
Model gap: Towers on the two raised rock stacks (top-centre ~0.45,0.25 and bottom-centre ~0.60,0.70) see over the walls in game (wiki), but the bot's sight grid ignores the tower's height and rates them as seeing nothing.

**Sources:**

- https://www.bloonswiki.com/Dark_Path - Bloonswiki - Dark Path
- https://bloons.fandom.com/wiki/Dark_Path - Bloons fandom - Dark Path
- https://btd6index.win/ - BTD6 Index
- https://www.youtube.com/watch?v=4AAtx2p1bwE - SnartFarts - Dark Path CHIMPS ft. Apache Prime (v52.2)
- https://www.youtube.com/watch?v=WZMh1KPqgyQ - BlueCliff - Dark Path Hard no MK (Quincy)
- https://www.youtube.com/watch?v=eyIX-967nps - BTD6 BluePrint - Lazy CHIMPS Dark Path (Ultra-Jugg + Blazing Sun)
- https://bloon.games/how-to-beat-chimps-on-dark-path/ - bloon.games - How to Beat CHIMPS on Dark Path

### Last Resort

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): hard **defeat at round 24** (farm_sun_avatar, 64 lives lost).*

**Key insight.** Bloons always enter along the top edge, then take one of four loops in a 4-round cycle (big, medium, small, straight), each faster than the last; only the top lane is used every round. Short-range towers on the right block or inside the big loop miss the small-loop and straight rounds (lost at round 24, 64 lives on the small-loop round). Use snipers from the inner strip of the big loop (they see ~75% of the top lane), a Pursuit heli, and a Perma-Spike as far right as possible; the $1,000 frozen pool opens the best spot on the map for a sub or boat.

**Lanes (alternating).** round mod 4 = 1 big loop (+80% speed), 2 medium (+40%), 3 small (+25%), 0 straight along the top (+15%); all share the top lane and exit top-right

**What the guides found** (detail from the sources):

- Alternating paths, 4-round cycle from R1: big loop (+80% speed), medium (+40%), small (+25%), straight (+15%); boss bloons straight at normal speed. R63 and R99 use the small loop; R78 and R98 the medium loop; R40/R76/R100 are straight.
- Path lengths: straight 9.5, small 12.1, medium 15.2, big 18.5 (BTD6 Index/bloonswiki). Source: https://btd6index.win/ (map=Last Resort)
- Path geometry (screen fractions): Path1/big (-0.16,0.11)->(0.70,0.11)->(0.71,0.76)->(0.15,0.77)->(0.14,0.12)->(1.01,0.11); Path2/medium ...->(0.71,0.46)->(0.50,0.47)->(0.49,0.12)->exit; Path3/small ...->(0.71,0.28)->(0.64,0.29)->(0.63,0.12)->exit
- Thick snow, the raised platform with snowmen on chairs (also blocks line of sight), lamp post in the tight loop, palm trees and shrubs block placement; snow does NOT block line of sight. Source: https://www.bloonswiki.com/Last_Resort

**Towers that work:**

- sniper 4-2-0 / 0-2-4 / 0-5-2: Global, only needs LOS (snow does not block): from the inner big-loop strip (0.607,0.598) or bottom strip (0.665,0.913) the bot ...
- spike 0-2-5 Perma-Spike (Smart, with Jungle Drums + Berserker ...: Single exit: 'place Perma-Spike as far right as possible on the top section ... set it to Smart'.
- buccaneer 2-3-0/2-4-0 or sub 2-0-4: Only water spot (after $1,000 removal) sits between the medium and small loops right under the top lane - ~30% of all track in ...
- wizard 0-2-4 -> 0-2-5 (Phoenix line): SnartFarts CHIMPS: Wizard 0-2-0 before R28, 0-2-4 Summon Phoenix (global flier) then 0-2-5 Wizard Lord Phoenix.
- heli 2-0-4 (BlueCliff) / Pursuit: BlueCliff Hard: Heli 2-0-0 R39 'put Heli on top path', 2-0-2, 2-0-3, 2-0-4 (Comanche).
- ninja 4-0-2 (Hard) / 2-0-5 (CHIMPS): BlueCliff Hard core with Alchemist; SnartFarts ends at Ninja 2-0-5 (Grand Saboteur, map-wide effect).

**Avoid:** farm (the game refused the farm spots; too little defence for the small-loop and straight rounds); beast_handler (the wiki's Condor trick needs a hand-placed reticle).

**Removable obstacles and map switches:**

- Frozen pool sign/ice (RemovableWater) ($1000): as soon as $1,000 is spare (before ~R30 in Hard; ramon eller does it mid-game in CHIMPS before placing his Sub). opens the only water spot, the best-covering spot on the map (~30% of all track: top lane + medium/small loops) for a Sub/Buccaneer

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff Hard, no MK, no farms (Quincy, Ninja 4-0-2, Alch, Heli 2-0-4, Dart 5-0-2, Sniper, Wizard) (hero: Quincy; youtube description, ~v46-47 (video ~1y old)). Source: https://www.youtube.com/watch?v=z_4kPTV47MI

  R3: Quincy; R6: Ninja; R8: Ninja 0-0-1; R9: 1-0-1; R11: 2-0-1; R13: 2-0-2; R17: 3-0-2; R22 (after round): Alchemist #1 (top) 2-0-0, target Strong; R24: Alch #1 2-0-1; R28: Alch #1 3-0-1; R35: Ninja 4-0-2; R37: Alch #1 4-0-2; R39: Heli 2-0-0, 'put Heli on top path'; R40: Quincy ability; R41: Heli 2-0-2; R44: Heli 2-0-3; R45: Dart 4-0-2; R52: Dart 5-0-2; R56: Sniper 3-2-0 Strong; R59: Sniper 4-2-0; R62: Village 2-0-0; R66: Heli 2-0-4; R69: Wizard 3-0-2; R75: Wizard 4-0-2; R78 (after round): Alchemist #2 (bottom) 4-2-0; R80: Quincy level-3 ability. GG; FAST TRACK NOTE (inferred): when the game starts at R22 with ~$9,700, buy everything up to R22 at once (Quincy, Ninja 3-0-2, Alch 2-0-0) AND a Sniper 2-x-x + the $1,000 ...

*chimps* - SnartFarts CHIMPS ft. Perma-Spike (Quincy, Dart, Ninja, Spike, Wizard Phoenix, Alch, Village) (hero: Quincy; youtube description, v52.2). Source: https://www.youtube.com/watch?v=RUf6olKIK0k

  1: Quincy 'slightly left to the pole'; 2: auto-start off; 3: Dart; 4: Ninja; 5: Ninja 2-0-2; 6: Spike Factory; 7: Spike 0-0-2, target Smart; 8: Wizard; 9: Wizard 0-2-0 before R28; 10: Spike 0-2-4; 11: Alchemist; 12: Alch 3-2-0; 13: Wizard 0-2-4; 14: Ninja 2-0-4; 15: Alch 4-2-0; 16: Dart 4-0-2; 17: Village; 18: Village 2-0-0; 19: Wizard 0-2-5; 20: Spike 0-2-5; 21: Ninja 2-0-5; 22: Dart 5-0-2; 23: Village '0-2-3' (as written; probably 2-3-0)

*chimps* - OneEyedDeacon 'NO ABILITIES, NO MICRO ft. Axis of Havoc' (Quincy, 3 Snipers, Perma-Spike, Glue, Alchs, Village) (hero: Quincy; youtube description, v49.3). Source: https://www.youtube.com/watch?v=7fpYt6w9ziE

  R6: Quincy in middle of pole; R8: Sniper #1 0-0-0 Strong, right of Quincy; R13: Spike #1 as far right as possible; R16: Spike 0-0-2 Smart; R19: Spike 1-0-2; R20: Sniper #1 1-0-0; R26: Spike 1-0-3; R35: Spike 1-0-4; R36: Sniper #1 2-0-0; R37: 2-2-0; R39: 3-2-0; R40: Glue #1 0-0-0 left of Quincy, Strong; R42: Village 2-0-0 left of glue; R43: Sniper #2 0-2-1 left of the village; R44: 0-2-2; R46: 0-2-3; R49: 0-2-4; R50: Sniper #3 0-3-2 left of sniper #2; R51: Alch #1 3-2-0 for sniper #3; R52: Alch #1 4-2-0; R57: Sniper #3 0-4-2; R59: Alch #2 3-2-0 for the spike; R63: Sniper #1 4-2-0; R64: Alch #2 4-2-0; R80: Spike 2-0-5; R84: Sniper #3 0-5-2 target First; R94: Sniper #1 5-2-0 (during round); R97: Sniper #2 0-2-5; R98: Glue 0-1-3 -> 0-1-4 -> 0-2-4 Strong; R99: Village 2-2-0

*chimps* - ramon eller CHIMPS (Obyn + 6 druids row, Wizard, Village, Sub in the broken ice, Perma-Spike) (hero: Obyn Greenfoot; youtube description, ~v46-48). Source: https://www.youtube.com/watch?v=0aDpeF97GyU

  Dart 0-0-0 Strong; Ninja 0-0-0 -> 0-0-1 -> 2-0-1; Obyn 'in the middle of the 2nd and 3rd posts'; 2 Druids left of Obyn; leftmost 2-0-0; 3 Druids right of Obyn; Wizard right of them 'aligned with the 4th post' -> 2-0-2; rightmost druid 2-0-0; Wizard 3-0-2; R40: Obyn Brambles at the start (MOAB must pop in range of wizard + last druid); Village 1-2-0 + a druid next to it; Druids: 2-0-3, 0-1-3, (Obyn), 0-1-3, 0-1-3, 4-0-1, 0-1-3 (druid 6 below the track); Alchemist 3-0-1 next to the lower druid; Village 2-2-0; Break the ice ($1,000), Sub 2-3-0 -> 2-4-0 (First Strike on R80 ZOMG); Druid below the track 0-1-5; Village 2-3-0 (DDTs); Spike Factory close to the exit, 0-0-2, 'as far as you can on the right of the track'; Alch 2-0-0 next to it; Spike 0-2-2 -> 0-2-5; that Alch 3-0-1; R100: First Strike on the BAD

*chimps* - FroStee Mate 'EASY No Micro No Abilities' (Quincy, Sniper, Dart, Boomerang Glaive Lord, Perma-Spike) (hero: Quincy; youtube description, v46). Source: https://www.youtube.com/watch?v=VQd2aoDI_70

  R6 Quincy; R8 Sniper (Strong); R9 Dart; R10 Boomerang; R15 Spike Factory, R18 Smart Spikes (Smart), R21 Bigger Stacks; R22 Full Metal Jacket; R27 Long Life Spikes, R35 Deadly Spikes; R36 Glaives + Red Hot Rangs, R37 Ricochet; R39 Alchemist Berserker Brew; R42 Village Radar Scanner; R45 MOAR Glaives; R46 Jungle Drums; R50 Wizard Dragon's Breath w/ Monkey Sense, Alchemist, Tack Shooter Overdrive w/ Even Faster Shooting; R51 Berserker Brew, Perishing Potions; R62 Stronger Stimulant, Perishing Potions; R75 Glaive Lord, Primary Training; R84 Perma-Spike; R88 Spike Storm, White Hot Spikes; R99 Carpet of Spikes; R100 win

Other builds found:

- chimps: G-Horizon CHIMPS no abilities (Silas? + Engineer, Spike, Ice army, Tack) (hero: Silas) - https://www.youtube.com/watch?v=ZMNP7TvNo4U

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): No LTC records listed; LCC $63,210 (v48.2, dbsdbx, 'Last Resort CHIMPS with more than 115k spare' reddit). Map info: 4 'entrances' (the 4 alternating paths), 1 removable ($1,000), LOS yes, water yes.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 8 spots - ninja, alchemist, heli, sniper, dart, wizard; hero quincy.
Removables recorded: RemovableWater ($1000, recommended, ~R30).
Map strategy: `strategies/maps/lastresort_hard.yaml`.
Model gap: After buying RemovableWater the bot model still has no legal water cell in the pool (about 0.52-0.59, 0.22-0.34).
Model gap: Guides put Quincy 'slightly left of the pole' (the lamp post inside the small loop, ~0.67,0.21); the model marks the whole small-loop interior unplaceable. Test 0.65,0.20 in game.

**Sources:**

- https://www.bloonswiki.com/Last_Resort - Bloonswiki - Last Resort
- https://bloons.fandom.com/wiki/Last_Resort - Bloons fandom - Last Resort
- https://www.youtube.com/watch?v=z_4kPTV47MI - BlueCliff - Last Resort Hard no MK (Quincy)
- https://www.youtube.com/watch?v=RUf6olKIK0k - SnartFarts - Last Resort CHIMPS ft. Perma-Spike (v52.2)
- https://www.youtube.com/watch?v=7fpYt6w9ziE - OneEyedDeacon - Last Resort no abilities/no micro (v49.3)
- https://www.youtube.com/watch?v=0aDpeF97GyU - ramon eller - Last Resort CHIMPS black border
- https://www.youtube.com/watch?v=VQd2aoDI_70 - FroStee Mate - Last Resort CHIMPS (v46)

### Pat's Pond

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): hard **defeat at round 40** (primary_core, 64 lives lost).*

**Key insight.** Two lanes run at the same time round a big pond in opposite directions and meet at two junctions (each junction is one lane's entrance and the other's exit). Players pack short-range towers at the right junction plus a boat in the water next to it. The bot's boomerang/tack build had no MOAB damage at round 40: by then the junction needs Ninja 4-0-2 + alchemist and a 0-4-2 boat.

**Lanes (simultaneous).** top lane enters left and exits right; bottom lane enters right and exits left (the BAD uses the top lane, exiting right)

**What the guides found** (detail from the sources):

- 2 entrances / 2 exits, simultaneous; TopPath: left (0.06,0.50) -> (0.36,0.14) -> (0.51,0.12) -> right (0.78,0.50); BottomPath: right (0.78,0.50) -> (0.43,0.88) -> (0.28,0.88) -> left (0.06,0.50); PathBoss = TopPath. Lengths 13.7 (top) / 14.4 (bottom).
- 'Due to how far apart the lanes are in the middle, most strategies involve cramming short-range towers at either the left or the right entrance. Most global-range towers, such as Heli Pilots and Advanced Intel Monkey Subs, are susceptible to chasing' ...
- Overlapping entrances/exits make it hard to see whether bloons are leaking; Perma-Spike is harder (not impossible) because exits overlap entrances. Source: https://www.bloonswiki.com/Pat%27s_Pond, https://bloons.fandom.com/wiki/Pat%27s_Pond/Strategies
- Big central pond for water towers (subs/buccaneers/druid-in-water not possible - druids are land; Mathbrush places druids 'in the water' meaning on pond edge).

**Towers that work:**

- ninja 4-0-2: Main early DPS in the BlueCliff Hard guide and in Mathbrush's CHIMPS (Bloonjitsu behind the tree next to Obyn)
- buccaneer 0-4-2 (Monkey Pirates) -> 5-2-0 later: BlueCliff Hard uses Buccaneer 0-1-0 R21 -> 0-4-2 R38 for the first MOABs (its MOAB Takedown ability on R40), then a 5-2-0 Carrier ...
- alchemist 4-0-1 / 4-2-0: Buffs the junction cluster; used by BlueCliff, Chantity, Mathbrush, Deacon.
- bomb 0-2-4 (MOAB Assassin): BlueCliff Hard places two 0-2-4 bombs (one covering the bottom lane, one the top) at R55/R58 for BFBs/ZOMGs.
- super 3-0-2 (Sun Avatar w/ Ultravision): Mathbrush's CHIMPS: 0-0-0 Super right before R40, 3-0-2 with a 0-0-2 village carries R40-80; Chantity also uses Super 3-0-2.
- spike 0-0-2 'close' early, 0-2-5 / 2-0-5 late: Chantity's Sauda CHIMPS opens with a Spike Factory 0-0-2 set to Close at the junction

**Avoid:** heli (Pursuit helis chase back and forth between the far-apart lanes); tack (no MOAB damage by R40 when it is the main damage (the bot's R40 loss)).

**Removable obstacles and map switches:**

- Right rock in the water (RemovableRockRight) ($500): BlueCliff Hard: R40 right after the round ends ('Remove right obstacle'); any time before you want water towers on the right. removes a line-of-sight blocker and turns the rock into water next to the right junction (bot model: +750 water cells; best new buccaneer spot 0.687,0.394)
- Left rock in the water (RemovableRockLeft) ($500): retrogaming fun CHIMPS: R38 'Remove two islands' (both rocks). frees water/LOS at the left junction
- Top tree (RemovableTreeTop) ($500): optional. LOS blocker; also has a blocking part in the middle of the pond (0.39-0.53, 0.32-0.53)
- Bottom tree (RemovableTreeBotton) ($500): optional. LOS blocker

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff Hard, no MK, no farms (Obyn, Ninja 4-0-2, Buccaneer, Alch, Village, MOAB Assassins) (hero: Obyn Greenfoot; youtube description, ~v32-34 (video ~3y old)). Source: https://www.youtube.com/watch?v=PpP_z82AN9o

  R3: Ninja, then a Dart after the round; R6: Ninja 1-0-0; R8 (after round): sell Dart, place Obyn; R10: Ninja 1-0-1; R12: Ninja 2-0-1; R13: Ninja 2-0-2; R17: Ninja 3-0-2; R21: Buccaneer 0-1-0 ('red range must not cover Ninja'); R24: Buccaneer 0-2-0; R26: 0-2-2; R27: 0-3-2; R34: Alchemist 3-0-0; R36: Obyn ability; R38: Buccaneer 0-4-2; R40: Buccaneer ability (MOAB Takedown); R40 after round: sell Buccaneer, buy the RIGHT rock removal ($500), Ninja 4-0-2, Alchemist 4-0-1; R42: Buccaneer 2-2-0; R45: 3-2-0; R48: 4-2-0; R50: Village 4-0-0; R51: Village 4-2-0; R55: Bomb 0-2-4 (bottom lane); R58: Bomb 0-2-4 (top lane); R61: Obyn Wall of Trees at the intersection; level-10 ability; R62, R69, R77: level-10 ability; R74: Buccaneer 5-2-0; R79: Sniper 4-0-2 Strong; GG; BOT ADAPTATION (inferred): skip the sell/rebuy - keep the 0-4-2 boat and add a second boat 2-2-0 -> 4-2-0 in the freed right water

*chimps* - Mathbrush CHIMPS (wiki strategy page): darts -> sub in the right crack -> Obyn, Ninja 4-0-2, Alch, Super 3-0-2, druids late (hero: Obyn Greenfoot; wiki, old (pre-v30), check vs current balance). Source: https://bloons.fandom.com/wiki/Pat%27s_Pond/Strategies

  Start: three 0-0-0 Dart Monkeys near the LEFT exit (two on Strong); ASAP: Monkey Sub on the right side 'in the crack between the path and the rock'; Then: Obyn, Ninja 4-0-2, Alchemist 4-0-0, Super Monkey 0-0-0 (bought right before R40); Obyn brambles on the right track for R40; Mid: Village 0-0-2 by the Super, Super 3-0-2, Alchemist 4-0-2 (carries ~R40-80); Late: Ice Monkey 0-4-2 under the village; Druids 0-2-4 near Obyn; MIB covering the exit druid; that druid 0-2-5 Strong; 5 more Poplust druids; Ninja 0-4-0 before R95/99

*chimps* - Chantity CHIMPS black border (Sauda, Spike, Alch, Super 3-0-2, villages) (hero: Sauda; youtube description, ~v25-27 (5y old)). Source: https://www.youtube.com/watch?v=MVuaZ1rCUOo

  R6: Sauda; R7: Dart; R12: Spike Factory; R15: Spike 0-0-2, target Close; R28: Spike 3-0-2; R30: Alchemist #1; R34: Alch #1 3-0-0; R37: Village #1 0-0-2; R38: Village #2 0-0-2; R39: Alchemist #2 3-0-0; R41: Super Monkey; R48: Super 2-0-0 -> 2-0-2; R54: Sauda level-3 ability when right-side bloons reach the dart; R56: Super 3-0-2; R57: Village #2 2-0-2; R59: Alch #2 4-0-1; R60: Spike #2; R61: Spike #2 0-0-2 Smart; R62: Alchemist #3 3-2-0; R63: Spike #2 0-0-3; R65: Spike 0-0-4; R79: Sauda level-10 on regrow leaks; spike #2 0-0-5; R80: Spike #2 0-2-5, Village #2 3-0-2; R81: Glue 0-1-3 Strong; R82-84: 3 Boomerangs 2-0-4 Strong; R85: Village #3 3-0-2; R86-92: Glue #2 0-1-3 + 3 more Boomerangs 2-0-4; R95-100: Mortar 0-0-4 (micro), Ninja 0-4-0, Spike #3 0-4-2, Alch #4 4-0-1 (mortar/ability steps need aiming - skip/replace)

*chimps* - OneEyedDeacon 'Druids, Druids and more Druids' (Obyn + 8 druids, no abilities needed except brambles/trees) (hero: Obyn Greenfoot; youtube description, v50.1). Source: https://www.youtube.com/watch?v=dydRUL5zKw0

  R6: Sub #1 0-0-0 on the right + Dart #1 0-0-0 under the left track; R8: Druid #1 under the left track next to the dart; R11: Obyn; R13: Druid #1 0-1-0; R15: Druid #2 next to the sub; R16: Druid #1 0-2-0; R20: 0-3-0; R22: 1-3-0; R23: Dart 0-0-2 camo priority; R24: Dart 0-2-2; R26-28: Druids #3-#5 around Obyn; R29: Alchemist next to druid #5 and Obyn; R31: Dart 0-3-2; R33: Village as bottom-left as possible above the druids; R37: Village 0-2-0; R38: Druid #2 2-0-0; R39: 3-0-0; R40: Druids #6-#8, brambles on the MOAB; R41-57: druids to 0-0-3 -> 0-0-4 -> 0-1-4 one by one; R49 Village 2-2-0; R51 Alch 3-2-0; R53 Alch 4-2-0; R79: one druid 0-1-5 during the round; R83: Village 2-3-0; R84: Druid #1 1-4-0; R95: Druid #1 1-5-0; R97: Sub 0-4-0; R99: Glue 0-2-4 Strong; R100: First Strike

*chimps* - retrogaming fun CHIMPS black border, no abilities, no mid-round actions (Desperado, Subs, Churchill, Glue 5-2-0) (hero: Captain Churchill; youtube description, v50). Source: https://www.youtube.com/watch?v=CPBKQYUTSsU

  R6: 2x Desperado 0-0-0; R9: Sub; R11: Sub 0-0-1; R12: Sniper Strong; R14: second Sub as top-right as possible; R18: top sub 0-0-2; R20: bottom sub 0-0-1; R24: right Desperado 0-1-0; R28: Churchill; Sniper 1-0-0; R30: top sub 2-0-2; R33: left Desperado 0-1-0; R35: Village 0-0-2; R36: Alchemist; bottom sub 2-0-1; R37: bottom sub 2-0-2; R38: remove two islands (both $500 rocks); R40: Village 0-0-1 covering Churchill; Alch 3-0-0; R42: right village 0-0-2, left village 2-0-2; R43: Alch 3-2-0; R46: left village 4-0-2; Glue 3-1-0; R50: Glue 4-2-0; Alch 4-2-0; R51: village 0-2-2; R60: Wizard 4-2-0 (re-target Wall of Fire - aiming, skip); R74: Glue 5-2-0; R84: Wizard 5-2-0; R85: Spike 2-0-4 (re-target); R95: Spike 2-0-5; R97: Sniper 4-2-0 target Last; R98: Alch 0-3-1 Strong

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: og = Ring of Fire 4-0-2 Tack + Geraldo (v44.0); heroless = Popseidon 2-5-0 + Golden Justice 0-5-2 + Glaive Lord 5-0-2 (v53.0). LCC $66,410-76,100. Strong evidence: short-range crowd towers at a junction (Ring of Fire, Glaive Lord) and water (Popseidon buccaneer) work.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 8 spots - ninja, buccaneer, alchemist, village, bomb, sniper, sub; hero obyn.
Removables recorded: RemovableRockRight ($500, optional, ~R40).
Map strategy: `strategies/maps/patspond_hard.yaml`.

**Sources:**

- https://www.bloonswiki.com/Pat%27s_Pond - Bloonswiki - Pat's Pond
- https://bloons.fandom.com/wiki/Pat%27s_Pond - Bloons fandom - Pat's Pond
- https://bloons.fandom.com/wiki/Pat%27s_Pond/Strategies - Bloons fandom - Pat's Pond/Strategies (Mathbrush)
- https://www.youtube.com/watch?v=PpP_z82AN9o - BlueCliff - Pat's Pond Hard no MK (Obyn)
- https://www.youtube.com/watch?v=MVuaZ1rCUOo - Chantity - Pat's Pond CHIMPS (Sauda)
- https://www.youtube.com/watch?v=dydRUL5zKw0 - OneEyedDeacon - Pat's Pond CHIMPS druids (v50.1)
- https://www.youtube.com/watch?v=CPBKQYUTSsU - retrogaming fun - Pat's Pond CHIMPS no abilities (v50)

### Party Parade

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): hard **defeat at round 57** (magic_obyn_ninja_wizard, 39 lives lost).*

**Key insight.** Two separate short lanes run at the same time on either side of a wide hedge wall that blocks placement and sight. Everything must be built in pairs, one per lane (the bot stacked the left lane and leaked 39 lives on the right at round 50). Best spots are inside each lane's rectangle; a Neva-Miss ace between the left lane and the wall covers both lanes.

**Lanes (simultaneous).** left lane: top to bottom, bulging left (the boss lane); right lane: bottom to top, bulging right
**Rule:** never buy a second tower for one lane before its mirror exists on the other lane.

**What the guides found** (detail from the sources):

- Two simultaneous lanes, 2 entrances/2 exits, no water, no removables; horizontal mirror symmetry. Path1 (left) (0.30,-0.14)->(0.30,0.31)->(0.15,0.31)->(0.15,0.68)->(0.30,0.68)->(0.30,1.20)
- 'The wide wall separating the two sides of the map blocks placement and line of sight.' 'Snipers can only hit one side of the map, and Heli Pilots in Pursuit mode will be stuck moving back and forth between both lanes'.
- Rated 'one of the harder Advanced Maps, debatably leaning towards a casual Expert map'. Lane length 11.3 each (BTD6 Index). Source: https://www.bloonswiki.com/Party_Parade, https://btd6index.win/ (map=Party Parade)
- Land: inside each lane rectangle (left x0.19-0.28, y0.37-0.63; right x0.57-0.66, y0.37-0.63), the strip between each lane and the wall (left x0.32-0.36; right x0.50-0.54), and the outer margins.

**Towers that work:**

- ace 2-0-3 / 1-0-4 (Neva-Miss line, NOT Centered Path dependence): Flies over the wall and covers both lanes; wiki recommends all Ace paths except Wingmonkey
- spike 1-0-4 / 2-0-4 (Smart) at each exit: Carpet of Spikes covers both lanes, trivializes DDTs and R100 BAD (wiki)
- mermonkey 4-2-0 (one per lane): BeatbloonsBob opens Double HP, Impoppable and Magic Only with 2 Mermonkeys (one per side) -> 4-2-0
- sniper 0-2-4/0-2-5 or 1-2-0 -> 4-2-0 (one per lane, Strong): One sniper per side; Double HP guide uses two 0-2-4 snipers (Supply Drop) and 0-2-5 Elite Defender left.
- boomerang 2-0-4 (Strong) / 4-0-2: Late cleanup, 2-4 per side in Deacon CHIMPS and Bob Impoppable/Double HP.
- village 2-2-0 -> 4-2-0 (one per lane): Every guide puts one village per side.

**Avoid:** heli (Pursuit helis get stuck flying between the two lanes); sniper (a sniper only sees its own side of the wall - never the only answer for both lanes).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - inferred Hard plan: the bot's magic build MIRRORED on both lanes (no Hard-standard written guide was found; based on BeatbloonsBob's harder-mode guides + wiki) (hero: Sauda (or Obyn); inferred, n/a). Source: https://www.youtube.com/watch?v=t6BTGKOaVck ; https://www.bloonswiki.com/Party_Parade ; btd6bot logs/bot.log 2026-10-22 04:53-04:59 (Party Parade hard, magic_obyn_ninja_wizard)

  Fast Track start (R22, ~$9,700): place ONE damage tower per lane before the first Play - Ninja 2-0-2 left (0.216,0.581) and Ninja 2-0-2 right (0.644,0.581) - plus the ...; R22-28: Alchemist 2-0-0 per lane (left 0.265,0.581; right 0.607,0.581); Ninja 3-0-2 both; camo is covered by the ninjas, lead by the alchemist acid; R30-39: Mermonkey (or Super) per lane; Ace 2-0-3 at 0.329,0.504 (covers both lanes); Before R40: Ninja 4-0-2 on both lanes, Spike Factory 1-0-4 Smart at each exit (left 0.248,0.777; right 0.617,0.223); R45-60: Village 2-2-0 per lane, Alch 4-2-0 per lane, Super 3-0-2 per lane (left 0.216,0.504 / right 0.607,0.504); R60-80: Spike Factories 2-0-5/1-0-5 or 2-5-0 (Carpet of Spikes covers both lanes), glue 0-2-4 Strong per lane; RULE: never buy a second tower for one lane before its mirror exists on the other lane.

*double_hp, used for the 'double_hp' hints* - BeatbloonsBob Double HP MOABs (no abilities, no RNG, no micro) - also the best template for plain Hard (hero: Sauda; youtube description, v53 (posted ~8 months ago)). Source: https://www.youtube.com/watch?v=t6BTGKOaVck

  2x Mermonkey 0-0-0 (one per lane); both Mermonkeys 1-0-0; Sauda; right Mermonkey 2-0-0; Dart 0-3-2; 2x Wizard 0-2-2 (one per lane); BEFORE R40: Sniper 0-2-4; left Mermonkey 2-1-0; AFTER R40: right Mermonkey 3-2-0; Sniper #2 0-2-4; right Mermonkey 4-2-0; left Mermonkey 4-2-0; Village 4-2-0; Boomerang 4-0-2; Spike Factory 1-0-4 (Smart); left Sniper 0-2-5; Spike Factory #2 1-0-4 (Smart); Village #2 2-0-0; Alchemist 4-2-0; (optional ability R80)

*abr* - BeatbloonsBob Alternate Bloons Rounds (no RNG; abilities R40/R43) (hero: Sauda; youtube description, v53). Source: https://www.youtube.com/watch?v=1JQAJVKqS80

  Sauda on left; Dart 0-0-0 on right (Strong); Sniper on right (Strong); Dart 0-0-2 -> 0-2-2 -> 0-3-2; Sniper on left (Strong); both Snipers 1-0-0; left Sniper 1-1-0; right Sniper 1-1-0; Monkey Ace 1-0-3 on right; right Sniper 1-2-0; BEFORE R40: Spike Factory 1-0-4 on left; Ace 2-0-3; R40 ability; Spike Factory 1-0-2 on right; R43 ability; right Spike 1-0-4; 2x Boomerang 4-0-2; Village 0-2-0 ASAP -> 2-2-0; Boomerang 2-0-4 right (Strong); Village 2-2-0 left; Boomerang 2-0-4 left (Strong); 2x Mermonkey 4-2-0; left Spike 4-2-0; right Spike 3-2-0; Alchemist 4-0-0 right

*impoppable* - BeatbloonsBob Impoppable (no abilities, no RNG) (hero: Sauda; youtube description, v53). Source: https://www.youtube.com/watch?v=UgpXdf8u2qE

  2x Mermonkey + 2x Dart (Last); both Mermonkeys 2-0-0; Sauda; right Dart 0-3-2; 2x Sniper 1-0-0 (Strong); right Mermonkey 3-2-0; Sniper 1-2-0; left Mermonkey 3-2-0 -> 4-2-0 before R40; Village 2-2-0 right; right Mermonkey 4-2-0; Village 2-2-0 left; Spike 2-0-4 left (Smart); Spike 3-0-2 right (Smart); Ace 2-0-3; (sell left dart); Alch 3-0-1 left (Strong); right Spike 4-0-2; 2x Boomerang 2-0-4 left (Strong); Glue 0-2-4 (Strong); left Alch 4-0-1; both Villages 4-2-0; 2x Boomerang 2-0-4 right (Strong); Glue 0-2-4 right (Strong); Alch 4-0-1; (sell right dart); right Sniper 4-2-0; Alch 4-0-0 by a Mermonkey; right Spike 4-2-0; R100: sell-and-rebuild into Spike 2-0-5 + 2-5-0 (bot cannot sell/rebuy - instead have both spikes upgraded earlier)

*magic_only* - BeatbloonsBob Magic Monkeys Only (no abilities or micro) (hero: Sauda; youtube description, v53). Source: https://www.youtube.com/watch?v=nZMc8vxPkAQ

  2x Mermonkey; right Mermonkey 1-0-0; Sauda; another Mermonkey on the right; bottom-right Mermonkey 2-2-0 -> 3-2-0; 2x Alchemist 2-0-0 (Strong); top-right Mermonkey 2-0-2; left Mermonkey 3-2-0; top-right Mermonkey 3-0-2; left Mermonkey 4-2-0 before R40; 2x Alch 3-0-1; bottom-right Mermonkey 4-2-0; top-right Mermonkey 4-0-2; Wizard 0-2-4 left; Wizard 0-2-4 right; 2x Alch 4-0-1; left Wizard 0-2-5

Other builds found:

- chimps: OneEyedDeacon 'Party Parade Chimps is EASY with Sauda and Tack Zone' (hero: Sauda) - https://www.youtube.com/watch?v=FgmIs2s7cL0

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC og: Golden Justice 2-5-0 + Avenger 2-0-4 + Geraldo + Pop and Awe 2-5-0 (v53.0); LCC $86,870 (v57.3) / $157,895 'rof spam' (v53.2). Wizard Lord Phoenix 2MPC exists (BTD6 Index video, v56.2) - global flyers work.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 10 spots - ninja, ace, spike, alchemist, super; hero sauda; 'double_hp' (double_hp, impoppable, chimps): 9 spots - mermonkey, wizard, spike, village, super; hero sauda.
Map strategy: `strategies/maps/partyparade_hard.yaml`.

**Sources:**

- https://www.bloonswiki.com/Party_Parade - Bloonswiki - Party Parade
- https://bloons.fandom.com/wiki/Party_Parade - Bloons fandom - Party Parade
- https://www.youtube.com/watch?v=t6BTGKOaVck - BeatbloonsBob - Party Parade Double HP MOABs
- https://www.youtube.com/watch?v=1JQAJVKqS80 - BeatbloonsBob - Party Parade ABR
- https://www.youtube.com/watch?v=UgpXdf8u2qE - BeatbloonsBob - Party Parade Impoppable
- https://www.youtube.com/watch?v=nZMc8vxPkAQ - BeatbloonsBob - Party Parade Magic Monkeys Only
- https://www.youtube.com/watch?v=FgmIs2s7cL0 - OneEyedDeacon - Party Parade CHIMPS Sauda + Tack Zone (v53.0)

### Enchanted Glade

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): hard **defeat at round 63** (hard_ninja_alch_sun, lives lost not recorded).*

**Key insight.** Two lanes alternate (odd rounds bottom-left, even rounds top-right) but share the wavy stretch below the centre and the final climb into the cherry-tree exit. The bottom-centre island right under that stretch is the best ground on the map. Round 63 (122 ceramics + 75 leads, odd = bottom-left lane) needs crowd damage there: Ninja 4-0-2 + alchemist and a Glue Bloon Solver (5-2-0) by round 62. The bot lost all lives inside round 63 with its spike factories on an island that sees no track and ninjas on the wrong path.

**Lanes (alternating).** odd rounds enter bottom-left, even rounds top-right; both end going up into the exit at (0.43,0.39)

**What the guides found** (detail from the sources):

- Alternating lanes: AlternateRoundSplitter [PathLeftStart, PathRightStart] -> odd rounds bottom-left, even rounds top-right (R63 odd = bottom-left). Lengths: left 14.2, right 16.8 (BTD6 Index).
- PathLeftStart (0.13,1.12)->(0.08,0.95)->(0.01,0.82)->(0.05,0.78)->(0.14,0.92)->(0.23,0.91)->(0.28,0.72)->(0.35,0.76)->(0.44,0.72)->(0.51,0.76)->(0.59,0.63)->(0.55,0.58)->(0.49,0.66)->(0.46,0.65)->(0.43,0.39 exit).
- Four placement areas: top-left, right-centre, bottom-right (inside a water ring) and bottom-centre; water only in the ring around the bottom-right island; trees block line of sight.
- 'Strategies that succeed on this map use either the bottom-center space, the area right below the center, or global-range towers'. Source: https://www.bloonswiki.com/Enchanted_Glade

**Towers that work:**

- glue 3-2-0 -> 4-2-0 -> 5-2-0 The Bloon Solver (Strong) by R62: BlueCliff Hard: Glue 3-1-0 R39, 3-2-0 R41, 4-2-0 R45, 5-2-0 R62 - right before the R63 rush
- ninja 4-0-2 (Hard) / 2-0-3 -> 2-0-5 (CHIMPS): BlueCliff Hard core (Ninja 3-0-2 by R17, 4-0-2 R34) - NOT 0-0-4; SnartFarts uses 2-0-5 Grand Saboteur late.
- alchemist 4-0-2 (Strong): BlueCliff Hard: Alch 2-0-0 R23, 3-0-1 R28, 4-0-2 R37 buffing the ninja.
- village 3-0-0 -> 4-2-0 -> 5-2-0: BlueCliff Hard: Village 3-0-0 R47, 4-2-0 R49 (Primary Mentoring + MIB), 5-2-0 R77.
- spike 1-0-5 / 0-2-5 Perma-Spike (Smart) or 2-0-5 Spike Storm -> ...: Shared exit: Perma-Spike 'at the very top-middle spot right below chokepoint' tanks every round (wiki)
- druid 0-3-0 Druid of the Jungle (+ Hard Thorns) / 1-5-0 Spirit of ...: Wiki: Druid of the Jungle 'performs exceptionally well thanks to the long alternating lanes'

**Avoid:** sub (the only water (ring round the bottom-right island) is too far from the track); spike (the top-left island has no track in Spike Factory range (both bot factories stood there)).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff Hard, no MK, no farms (Quincy, Ninja 4-0-2, Alch 4-0-2, Glue Bloon Solver, Village 5-2-0) (hero: Quincy; youtube description, ~v47-48 (video ~1y old)). Source: https://www.youtube.com/watch?v=WTBG33Bey-M

  R3: Quincy; R6: Ninja; R8: Ninja 1-0-0; R10: 1-0-1; R11: 2-0-1; R13: 2-0-2; R17: 3-0-2; R23 (after round): Alchemist 2-0-0, target Strong; R28 (after round): Alch 3-0-1; R34: Ninja 4-0-2; R37 (after round): Alch 4-0-2; R39: Glue 3-1-0; R40: Quincy ability; R41: Glue 3-2-0; R45: Glue 4-2-0; R47: Village 3-0-0; R49: Village 4-2-0; R60: Quincy level-3 ability; R62: Glue 5-2-0 (The Bloon Solver) - the R63 answer; R77: Village 5-2-0; GG (R80); FAST TRACK NOTE (inferred): starting at R22 with ~$9,700, buy up to the R22 state at once (Quincy, Ninja 3-0-2, Alch 2-0-0) and keep saving for the glue line - never ...

*chimps, used for the 'chimps' hints* - SnartFarts CHIMPS ft. Carrier Flagship (Quincy, Buccaneer 5-2-0, Ninja 2-0-5, Village 2-3-0, Druid 1-5-0, Glue 0-2-4) (hero: Quincy; youtube description, v52.2). Source: https://www.youtube.com/watch?v=MEHLrD12TMk

  1: Quincy; 2: Buccaneer; 3: Buccaneer 2-2-0; 4: Ninja; 5: Ninja 2-0-2; 6: Buccaneer 3-2-0; 7: Ninja 2-0-3; 8: Village; 9: Village 2-0-0; 10: Buccaneer 4-2-0; 11: Village 2-2-0; 12: Buccaneer 5-2-0 (Carrier Flagship); 13: Druid; 14: Druid 1-5-0 (Spirit of the Forest); 15: Village 2-3-0; 16: Ninja 2-0-5; 17: Glue, target Strong; 18: Glue 0-2-4

*chimps* - CrimsonPlanet CHIMPS no micro (Obyn, Mermonkey, Druid, Wizard 5-0-2, Heli 5-0-2, Sub 0-4-0) (hero: Obyn Greenfoot; youtube description, v52.2). Source: https://www.youtube.com/watch?v=50CsJ1u4_xw

  Dart 0-0-0; Mermonkey 1-0-0; Obyn; Druid 1-1-0; Wizard 3-0-2; Druid 1-3-0; Mermonkey 4-0-0; R40: Obyn ability; Wizard 4-0-2; Heli 4-0-2; Village 0-2-0; Wizard 5-0-2; Village 2-3-0; Heli 5-0-2; Sub 0-4-0; (optional) Glue 0-2-4; R100: Sub ability (recommended)

*chimps* - FroStee Mate CHIMPS no micro (Sauda, Sub, Druid of the Jungle, Glue Bloon Solver at R63, Spike Storm/Carpet, Icicle Impale) (hero: Sauda; youtube description, v47.0). Source: https://www.youtube.com/watch?v=P5X5umWqjwA

  R6 Sauda; R8 Boomerang; R10 Sub; R12 Druid; R19 Druid of the Jungle; R20 Hard Thorns; R32 Sub Triple Guns + Advanced Intel, Dart Monkey; R36 Armor Piercing Darts; R40 Alchemist Berserker Brew; R42 Village Radar Scanner; R47 Primary Mentoring; R48 Glue Bloon Dissolver + Glue Splatter; R50 Bloon Liquifier; R63 Bloon Solver; R70 Spike Factory Spike Storm; R71 White Hot Spikes; R85 Carpet of Spikes; R87 Ice Icicles + Deep Freeze; R96 Icicle Impale; R100 win

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: og = MOAB Domination 0-2-5 + Geraldo (v47); heroless = Golden Justice 2-5-0 + Popseidon 0-5-2 (v51.2); cheapest = Carrier Flagship 5-2-0 + Geraldo (v47.0). LCC $59,245 (v53.2). Global flyers (Ace/Carrier planes) clearly dominate; Talk page also notes Inferno Ring, Churchill (good line of fire) and MOAB Domination placed in the very middle.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 6 spots - ninja, alchemist, glue, village; hero quincy; 'chimps' (impoppable, chimps): 4 spots - buccaneer, ninja, druid, glue; hero quincy.
Map strategy: `strategies/maps/enchantedglade_hard.yaml`.

**Sources:**

- https://www.bloonswiki.com/Enchanted_Glade - Bloonswiki - Enchanted Glade
- https://www.bloonswiki.com/Talk:Enchanted_Glade - Bloonswiki - Talk:Enchanted Glade
- https://bloons.fandom.com/wiki/Enchanted_Glade - Bloons fandom - Enchanted Glade
- https://www.youtube.com/watch?v=WTBG33Bey-M - BlueCliff - Enchanted Glade Hard no MK (Quincy)
- https://www.youtube.com/watch?v=MEHLrD12TMk - SnartFarts - Enchanted Glade CHIMPS ft. Carrier Flagship (v52.2)
- https://www.youtube.com/watch?v=50CsJ1u4_xw - CrimsonPlanet - Enchanted Glade CHIMPS (v52.2)
- https://www.youtube.com/watch?v=P5X5umWqjwA - FroStee Mate - Enchanted Glade CHIMPS (v47.0)

### Logs

*Beginner map. Bot record (logs/results.jsonl, 2026-10-22): medium **defeat at round 4** (hard_ninja_alch_sniper, 142 lives lost); medium **defeat at round 30** (starter_tack_dart, 119 lives lost); double_hp won (double_hp_sniper_sun); easy won (solo_tack).*

**Key insight.** An easy, very long single lane that zig-zags and crosses itself; the only trap is placement: towers squeezed against a log or in a corner see one lane, the open squares either side of the central pond see 4-6 crossings and a buccaneer in the pond ~30% of the track. Both Medium losses were not map problems (a roster-probe error at R4, corner placements and no lead answer at R30).

**Lanes (single).** one lane in four vertical columns and three horizontal rows

**What the guides found** (detail from the sources):

- Single lane, 1 entrance (top-left, y~0.19) / 1 exit (bottom-left, y~0.73); path corners ...
- Six logs block line of sight (towers unaffected by LOS still damage bloons under them); small central pond fits 5 subs/mermonkeys or 4 buccaneers. Source: https://www.bloonswiki.com/Logs
- 'Considered to be the easiest map in BTD6' - most 2TC completions, cheapest CHIMPS ever ($1,215: Corvus + one 0-0-0 Dart). Source: https://www.bloonswiki.com/Logs, https://btd6index.win/ (map=Logs)
- Bot losses: Medium R4 (hard_ninja_alch_sniper) - 'roster probe' returned every tower as locked, only Quincy was placed at (0.607,0.325) and the plan was 'exhausted' with $6,507 idle

**Towers that work:**

- buccaneer 3-2-0 Destroyer (+camo) / 2-5-0 Pirate Lord: Central pond is surrounded by track on all sides - both broadside guns fire constantly
- ninja 4-0-2: Askaii CHIMPS core; from a centre square it covers many crossings.
- heli 5-0-2: Askaii CHIMPS main DPS (Heli 3-0-2 -> 4-0-2 -> 5-0-2).
- boomerang 0-4-2 / 5-2-0 / 0-2-5: Baumfall black-bordered with all three T5 boomerangs + Etienne.
- any medium-range tower -: 'Logs has arguably the widest variety of working strategies out of all maps'.

**Builds (in buy order):**

*medium/hard (safe placement note), used for the 'hard' hints* - inferred safe opener + placement for the bot (from map geometry and the wiki) (hero: Quincy; inferred, n/a). Source: map geometry (data/map_geometry) ; https://www.bloonswiki.com/Logs

  R1: Ninja (or Dart) in the left-centre square (0.281,0.521) - it covers progress 0.06-0.91 including the very first column, so R1-10 cannot leak; R2-5: Quincy in the same square or the right-centre square; Alchemist at 0.281,0.462; ~R10-20: Buccaneer in the central pond (0.414,0.53) -> 2-2-0 -> 3-2-0 Destroyer (needs camo by R24: ninja/village 0-2-0) or 2-5-0 Pirate Lord later; Then any standard Hard build (e.g. Askaii's below) placed in the two centre squares and the pond.

*chimps* - Askaii Logs CHIMPS 2021 (Quincy, Ninja, Alch, Heli Apache Prime, Village, Glue, Boomerang, Wizard) (hero: Quincy; youtube description, ~v24-26 (2021)). Source: https://www.youtube.com/watch?v=5ZIo6byrgqs

  Quincy; Ninja 3-0-1; Alch 2-0-0; Ninja 4-0-2; Alch 4-0-2; Village 2-0-0; Heli 3-0-2; Village 2-2-0; Heli 4-0-2; Heli 5-0-2; Village 2-3-0; Glue 0-2-4 Strong; Boomerang 0-2-4 Strong; Wizard 2-0-4; Wizard 2-0-5

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: og/heroless = Energizer 5-0-2 + The Anti-Bloon 2-5-0 (v2.1); cheapest = 0-0-0 Dart + Corvus (v40.0, masmaves, $1,215 - the cheapest CHIMPS ever).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 5 spots - ninja, alchemist, buccaneer, super, spike; hero quincy.

**Sources:**

- https://www.bloonswiki.com/Logs - Bloonswiki - Logs
- https://bloons.fandom.com/wiki/Logs - Bloons fandom - Logs
- https://bloons.fandom.com/wiki/Logs/Strategies - Bloons fandom - Logs/Strategies
- https://www.youtube.com/watch?v=5ZIo6byrgqs - Askaii - Logs CHIMPS guide 2021
- https://www.youtube.com/watch?v=E3JDteg5egk - Baumfall - Logs CHIMPS all T5 boomerangs
- https://btd6index.win/ - BTD6 Index

## Advanced maps

### Off The Coast

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Single lane that starts and ends in the sea: beach towers only cover the middle. Use subs in the bays beside the track, a Carrier Flagship, and global towers (sniper on the shipwreck).

**Lanes:** single.

**What the guides found** (detail from the sources):

- Track: enters bottom-left in the sea (~0.20,0.95), runs up the left side (x~0.10 at y 0.45-0.6), arches over the beach (top at ~0.40,0.15), comes down the right side (x~0.75 at y 0.5) and exits bottom-right in the sea (~0.68,0.95).
- Water: the whole lower half. Best water spots are the left bay just inside the track near the entrance (~0.18-0.24, 0.53-0.60; covers progress ~0.06-0.37) and the right bay beside the exit (~0.71-0.75, 0.75-0.82; covers the last ~18% of the track).
- Shipwreck in the middle of the sea is unbuildable except three land pieces: left piece (~0.30,0.73), the crow's nest/crane (~0.39,0.62) and the right piece (~0.53,0.74). The crane slightly blocks line of sight
- Two rocky cliffs in the top corners (~0.05,0.08 and ~0.70,0.08) block line of sight a little and cannot hold towers.

**Towers that work:**

- buccaneer 5-2-0: Carrier Flagship: global planes ignore the lack of compact track; ~17% attack-speed buff to all water towers
- heli 2-0-5: Comanche Defense/Commander: single lane, mini-Comanche 25% thresholds sit near the apexes of the wide loops
- sub 2-0-4: Lots of water right beside the start and the end of the track; Advanced Intel lets them shoot anything other towers see.
- ninja 4-0-2: Early/mid DPS on the beach inside the left bend (BlueCliff Hard no-MK guide).
- sniper 4-0-2: Maim MOAB on the crow's nest sees the whole track; BlueCliff adds it at R79.
- tack 2-0-5: Inferno Ring late-game DPS in BlueCliff's Hard guide.

**Avoid:** spike (no land near the exit (it is in the sea)); druid (no land next to the entrance or exit).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff - Off the Coast Hard, no Monkey Knowledge, no heroes (written guide) (hero: none (works with any; Quincy/Obyn optional); youtube description, ~v30 (video 4 years old); towers used are unchanged staples). Source: https://www.youtube.com/watch?v=Oc2ihV126QM

  settings: turn auto-start OFF until R63 (source: reduces Alchemist RNG); R3: Ninja 0-0-0 (inner side of the left bend), targeting Strong; R3 (after round ends): Dart 0-0-0 next to the Ninja; R6: Ninja 1-0-0; R8: Ninja 1-0-1, set Ninja targeting to First; R10: Ninja 1-0-2; R11: Ninja 2-0-2; R15: Ninja 3-0-2; R21: Buccaneer 0-2-0 in the left bay, targeting Strong; R26: Buccaneer 2-2-0; R33: Ninja 4-0-2; R36: Buccaneer 3-2-0; R39 (after round): set Buccaneer to First; source sells the Dart here (bot: skip the sell); Alchemist 3-0-1 touching Ninja and Buccaneer; R41 (after round): Alchemist 4-0-1; R48 (after round): Buccaneer 4-2-0; Village 2-0-0; R50: Village 2-2-0; R62 (after round): Buccaneer 5-2-0 (source: sell Ninja if short - with Double Cash/MK the bot should not need to); auto-start may be turned back on; R67: Tack 2-0-4; Village 4-2-0; R77: Tack 2-0-5; R79: Sniper 4-0-2 on the crow's nest, targeting Strong; GG (R80 win on Hard)

*chimps, used for the 'chimps' hints* - BTD6 Fenix - Off the Coast CHIMPS, no ability activations (Quincy, Subs, Apache Prime, PoD) (hero: Quincy; youtube description, ~v22-24 (video 5 years old); every tower used has only been buffed since - ...). Source: https://www.youtube.com/watch?v=hV74wqAusLI

  R6: Dart 0-0-0 + Sub 0-0-0 (sub at the water's edge near the last bend - fandom trivia); R8: Sub 0-0-1; R11: Quincy; R14: Sub 2-0-1; R18: Sub 2-0-2; R23: Sub 2-0-3; R25: Sniper 0-0-0 on the crow's nest, targeting Strong; R26: Sniper 1-0-0; R31: Heli 0-0-0; R32: Heli 2-0-0; R35: Heli 3-0-0; R36: Heli 3-0-2; R37: Alchemist 0-0-0; R38: Alchemist 3-0-0; R39: Alchemist 3-2-0; R40: (optional Quincy level-3 ability); R41: Village 0-2-0; R42: Village 2-2-0; R45: Alchemist 4-2-0; R47: Wizard 0-0-0; R49: Wizard 0-2-4; R59: Heli 4-0-2; R75: Wizard 0-2-5 (Prince of Darkness); R76/R78/R85/R87/R99/R100: Quincy abilities 'for safety' only (bot fires on cooldown); R88: Heli 5-0-2 (Apache Prime); R91: Dart 0-2-4; R96: Dart 0-2-5 (Crossbow Master); R97: Alchemist 4-2-0 (source repeats; second alchemist if the first is done); R98: Spike Factory 3-2-0 + Alchemist 0-3-1; GG

Other builds found:

- chimps: Chantity - Off The Coast CHIMPS, no abilities, AFK late game (order only) (hero: Etienne) - https://www.youtube.com/watch?v=z50TUm7KE4Y
- magic_only: BlueCliff - Off the Coast Magic Monkeys Only, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=q_9bbPR3A84
- double_hp: BlueCliff - Off the Coast Double HP MOABs, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=5afL4NDEuYU
- impoppable: BlueCliff - Off the Coast Impoppable, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=pAsSlw1z0Ps

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): 2TC: Pre-Emptive Strike (Sub 2-5-0) + Geraldo (v31, Light_Sama); cheapest 2TC Perma Charge (Boomerang 0-5-2) + Geraldo; heroless 2TC Glaive Lord (Boomerang 5-0-2) + M.A.D (Dartling 2-5-0) (v43.3, Mehalic). LCC ~$44.5k (v44.1). => Subs/Buccaneers on the water and boomerangs are proven strong here.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 7 spots - ninja, dart, buccaneer, alchemist, village, tack, sniper; hero quincy; 'chimps' (impoppable, chimps): 10 spots - dart, sub, sniper, heli, alchemist, village, wizard, spike; hero quincy.

**Sources:**

- https://www.bloonswiki.com/Off_The_Coast - bloonswiki Off The Coast
- https://bloons.fandom.com/wiki/Off_The_Coast - fandom Off The Coast
- https://bloons.fandom.com/wiki/Off_the_Coast/Strategies - fandom Off the Coast/Strategies
- https://www.youtube.com/watch?v=Oc2ihV126QM - BlueCliff - Off the Coast Hard No MK (ft. No Heroes)
- https://www.youtube.com/watch?v=rVR3aH1S1FQ - CurlyFrys - OFF THE COAST Easy CHIMPS Tutorial
- https://www.youtube.com/watch?v=TZDZm3yxfSM - NamelessBandicoot - CHIMPS Off the Coast w/ Flying Fortress
- https://www.youtube.com/watch?v=WnYzI5d781A - OneEyedDeacon - [BTD6] Off The Coast - Chimps

### Cornfield

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Only the small plot in the middle is buildable without buying corn, and the corn blocks sight. A dense core in the middle plot wins (Ultra-Juggernaut balls bounce off the corn, Glaive Lord, homing magic, Bloon Solver); the $700 corn just below the plot is the cheapest overflow room.

**Lanes:** single.

**What the guides found** (detail from the sources):

- Track: enters top-left (~0.14,0.03), down the 1st chute (x~0.14) to the bottom, right along y~0.90 to x~0.36 (2nd bend), up the 2nd chute to y~0.38, right to x~0.49, down the 3rd chute to y~0.68, right along y~0.68 to x~0.72 (6th bend), up the 4th chute to ...
- Free plot = the dirt square inside the 2nd-3rd chutes (~0.39-0.46 x 0.45-0.59 usable). Towers there reach roughly track progress 0.42-0.72 (the inner U) only.
- 13 corn removables ($350-$1,500, $9,300 total) block placement AND line of sight until removed; small gaps between plots let some shots through (a Sniper can shoot through the gap between the scarecrow plot and the plot below it).
- Secret No-Harvest spots (not legal in the placement check's model, need pixel-precise placement): right of the 2nd bend (medium tower), above the 3rd bend (small), left of the 5th bend (medium, harder), the 6th bend (small, sub-pixel), plus a 2025-found ...

**Towers that work:**

- dart 5-0-2: Ultra-Juggernaut: balls bounce off the corn repeatedly and re-hit bloons; core of the BeatbloonsBob No-Harvest CHIMPS build.
- boomerang 5-0-2: Glaive ricochet ignores the corn (homing bounces); 2-0-4 MOAB Press for MOABs. Glaive Lord + M.A.D is the heroless 2TC.
- glue 5-2-0: Bloon Solver puddles work regardless of line of sight; BlueCliff Hard and BeatbloonsBob CHIMPS both use it.
- ninja 4-0-2: Seeking shuriken partly ignore obstacles; BlueCliff Hard core.
- village 4-2-0: Primary Mentoring + Radar Scanner buffs the dart/boomerangs and gives camo in the tiny plot.
- spike 2-5-0: Carpet of Spikes: residue on the track, no line of sight needed; finisher in BeatbloonsBob's build.

**Avoid:** sniper (corn blocks most sight lines from the free plot); super (sight blocked by corn; too big for the plot); farm (no room in the free plot).

**Removable obstacles and map switches:**

- Corn patch - Top far-left ($500): optional: after the $350 ones. corner plot next to the entrance; good for farms or early towers near the start
- Corn patch - Middle far-left ($350): first buy if buying any (R10-R25): cheapest, opens an offensive spot left of the 1st chute. cheapest; left of the 1st chute; good spot for general offensive towers
- Corn patch - Bottom far-left ($500): optional: after the $350 ones. corner plot beside the 1st bend
- Corn patch - Top middle-left ($700): last or never. between the 1st and 2nd chutes, top; low value
- Corn patch - Middle middle-left (scarecrow) ($1000): mid game if a long-range tower in the free plot must see the 1st chute. scarecrow plot; removing it lets long-range towers in the free plot see the 1st chute
- ... and 8 more (see the sources)

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff - Cornfield Hard, no Monkey Knowledge, no farms (ft. Quincy) (hero: Quincy; youtube description, ~v33-35 (video 3 years old)). Source: https://www.youtube.com/watch?v=qcnDjtGW6DU

  settings: auto-start OFF; R3: Ninja 0-0-0 (free middle plot); R3 (after round): Dart 0-0-0 (free plot); R7: Quincy (free plot); R9: Ninja 1-0-0; R10: Ninja 1-0-1; R12: Ninja 2-0-1; R14: Ninja 2-0-2; R18: Ninja 3-0-2; R25 (after round): Alchemist 2-0-0 touching the Ninja, targeting Strong; R26: Alchemist 3-0-0; R34: Ninja 4-0-2; R37 (after round): Alchemist 4-0-1; R39: Village 2-0-0; R49: Village 4-0-0; Glue 4-2-0; R60: Quincy level-3 ability (bot presses abilities anyway); R61: Glue 5-2-0; source removes the 'bottom middle' corn (the $700 patch below the free plot) here - optional for the bot; R63: Village 4-2-0; R77: Village 5-2-0; GG

*chimps, used for the 'chimps' hints* - BeatbloonsBob - Cornfield CHIMPS without removing any corn (No Harvest), Ultra-Juggernaut core (hero: Sauda; youtube description, ~v52-53 (video 8 months old)). Source: https://www.youtube.com/watch?v=f_J04Y_M5c4

  order only (no rounds in source); rounds below are inferred milestones; R1: Sauda in the free middle plot; R1-2: Dart 0-0-0 on the bottom of the map, targeting Strong (a secret spot below the bottom track; bot may skip or put it in the plot); R3-12: Dart 3-0-1 in the middle plot (main dart); R13-30: main Dart -> 4-0-2 (Juggernaut + Enhanced Eyesight camo); ~R30: Village 0-0-0 as low in the plot as possible; ~R33-40: Boomerang 4-0-2 (MOAR Glaives); ~R40-45: Boomerang 2-0-4 (MOAB Press), targeting Strong, as low and as far left in the plot as possible; ~R50-60: main Dart -> 5-0-2 (Ultra-Juggernaut); ~R60-65: Village -> 4-2-0; ~R65-75: Boomerang (4-0-2) -> 5-0-2 (Glaive Lord); ~R75-85: Glue 5-2-0 (Bloon Solver) as low as possible; ~R85-95: Spike Factory 2-5-0 (Carpet of Spikes)

Other builds found:

- chimps: HyperF3 - Cornfield CHIMPS (No Harvest), v56 - Desperado/Wizard/Bomb core (hero: Quincy) - https://www.youtube.com/watch?v=q2JUXF2I_S8
- chimps: unescaped - Cornfield CHIMPS + No Harvest, easy no micro (Sauda/Quincy, Spirit of the Forest, Perma-Spike) (hero: Sauda (author recommends over Quincy)) - https://www.youtube.com/watch?v=HMfHgEdJv_k
- magic_only: BlueCliff - Cornfield Magic Monkeys Only, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=GAaZqmz24sU
- abr: BlueCliff - Cornfield Alternate Bloons Rounds, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=6BApEGJJLuI
- impoppable: BlueCliff - Cornfield Impoppable, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=PYePCFwgqmY

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): 2TC: Sauda + Wizard Lord Phoenix 0-5-2 (v28.3); heroless 2TC Glaive Lord (Boomerang 5-0-2) + M.A.D (Dartling 2-5-0) (v43.3). LCC as low as $16.8k (v51.1, Capsen). Old 3TC (v13.1): Quincy + Permanent Brew + Apache Prime. => flying/global towers (Phoenix, Apache), glaive ricochet and the free-plot-only approach are proven.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 6 spots - ninja, dart, alchemist, village, glue; hero quincy; 'chimps' (impoppable, chimps): 6 spots - dart, village, boomerang, glue; hero sauda.
Removables recorded: Cornfield6 ($700, optional, ~R39).

**Sources:**

- https://www.bloonswiki.com/Cornfield - bloonswiki Cornfield
- https://bloons.fandom.com/wiki/Cornfield - fandom Cornfield
- https://bloons.fandom.com/wiki/Cornfield/Strategies - fandom Cornfield/Strategies
- https://www.bloonswiki.com/No_Harvest - bloonswiki No Harvest
- https://www.youtube.com/watch?v=qcnDjtGW6DU - BlueCliff - Cornfield Hard No MK (ft. Quincy)
- https://www.youtube.com/watch?v=f_J04Y_M5c4 - BeatbloonsBob - Cornfield CHIMPS without removing corn
- https://www.youtube.com/watch?v=q2JUXF2I_S8 - HyperF3 - Cornfield CHIMPS (v56) No Harvest

### Underground

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Two very short lanes run every round, but both loop through the central ring and cross at its left and right edges: put the core inside the ring, stall with glue, add snipers outside.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- Lane A enters at the top (~0.46,0.0), runs down the right side of the outer bulb, through the inner ring, and exits at the bottom (~0.45,1.0). Lane B enters at the bottom (~0.38,1.0), runs up the left side and exits at the top (~0.38,0.0).
- The inner ring (ellipse ~x 0.30-0.55, y 0.40-0.60) is shared by both lanes; the lanes cross at its left (~0.29,0.50) and right (~0.55,0.50) edges.
- Space above (~0.42,0.28) and below (~0.42,0.72) the ring sits between both lanes; open cave floor left and right of the bulbs is good for Banana Farms and global towers.
- Cave walls only block line of sight slightly; no water, no removables.

**Towers that work:**

- glue 5-2-0: Stall is especially valuable on such short lanes (Relentless Glue / Bloon Solver chain).
- boomerang 5-0-2: Glaive Lord rangs bounce between the two lanes inside the ring.
- spike 2-5-0: Carpet of Spikes: all ability spikes see action every round, trivialises the BAD with cleanup.
- wizard 0-2-5: Prince of Darkness on the intersecting paths is a strong midgame; Wall of Fire at the crossings for cleanup
- desperado 0-0-0: Early only: two 0-0-0 Desperados inside the ring hold the start (retrogaming fun, v50).
- sniper 5-2-0: (4-2-0 first) Global range covers both lanes; Cripple MOAB/strong targeting for blimps.

**Avoid:** farm (do not let farms take the ring spots).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff - Underground Hard, no Monkey Knowledge, no farms (ft. Quincy) (hero: Quincy; youtube description, ~v30 (video 4 years old)). Source: https://www.youtube.com/watch?v=9jvPhl28e5E

  settings: auto-start OFF; R3: Quincy (inside the ring); R4: Dart 0-0-0; R7: Ninja 0-0-0; R9: Ninja 1-0-0; R10: Ninja 1-0-1; R12: Ninja 2-0-1; R14: Ninja 2-0-2; R18: Ninja 3-0-2; R25 (after round): Alchemist (a) 2-0-0; R31: Ninja 4-0-2; R35 (after round): Alchemist (a) 3-0-1; R38 (after round): Alchemist (a) 4-0-1; R39 (after round): source sells the Dart (bot: skip); Bomb (a) 0-2-3; R40: Quincy ability when the MOAB hits the first intersection (bot presses abilities on cooldown anyway); R42: Village 2-0-0; R44: Bomb (a) 0-2-4; R48: Bomb (b) 0-2-4; R49: Alchemist (b) 4-0-1; R50: Village 4-0-0; R53: Village 4-2-0; R59: Bomb (c) 0-2-4; R72: Village 5-2-0; R78: Sniper 4-0-2, targeting Strong; GG

*chimps, used for the 'chimps' hints* - retrogaming fun - Underground CHIMPS, no abilities, no mid-round actions (hero: Captain Churchill; youtube description, tested on v50). Source: https://www.youtube.com/watch?v=eXTI3EzbFgc

  R6: 2x Desperado 0-0-0 (inside the ring, left and right); R9: Dart 0-2-0; R11: Dart -> 0-3-0; R13: Sniper 0-0-0 (top), targeting Strong; R15: second Sniper 0-0-0 (bottom), targeting Strong; R16: Dart -> 0-3-2; R17: top Sniper -> 1-0-0; R19: bottom Sniper -> 1-0-0; R27: Captain Churchill, top right; R30: Village 0-0-0; R33: Village -> 0-0-2; top Sniper -> 1-1-0; R36: second Village 0-0-2 covering Churchill; R39: Village -> 3-0-2 (source wording 'village into 302'); Glue 2-1-0; R40: Alchemist 3-0-0; R42: Village -> 0-2-2 (source: 'village into 022' - presumably the second village); R43: Glue -> 3-1-0; R44: Glue -> 3-2-0; R46: second Glue 3-2-0 'under double discount' (inside both villages' range); R49: left Glue -> 4-2-0; R51: right Glue -> 4-2-0; R59: Wizard 4-2-0 (source retargets its Wall of Fire; the default targets the nearest track - leave it); R60: Alchemist -> 4-2-0; R62: Village -> 4-2-0 (source text; a 3-0-2 village cannot become 4-2-0 - follow the source's intent: one village ends 4-2-0 or 3-0-2, the other 0-2-2); R76: left Glue -> 5-2-0; R85: Wizard -> 5-2-0; R88: bottom Sniper -> 4-2-0; R97: bottom Sniper -> 5-2-0; R98: Alchemist 4-0-0 (second alchemist per source wording '400 alchemist'); R99: Sniper -> 4-2-0 (source did 4-1-0 by mistake); GG

Other builds found:

- magic_only: BlueCliff - Underground Magic Monkeys Only, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=T_X46zgnkfo
- double_hp: BlueCliff - Underground Double HP MOABs, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=l8nnc5ZfWKU
- abr: BlueCliff - Underground Alternate Bloons Rounds, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=Z8iD-mi6eSI

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): 2TC: Perma Charge (Boomerang 0-5-2) + Geraldo (v31). LCC $46k (v31.2). Other CHIMPS guides: OneEyedDeacon Bomb Axis (Striker Jones + 4 darts + bombs 0-2-5/5-2-0/1-4-0, v49.3, later obsoleted by the Bomb Blitz nerf), OneEyedDeacon PMFC + Geraldo (v53.2, needs ability timing), sYnce Striker + Perma-Spike + Lord of the Abyss (v55.2).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 10 spots - dart, ninja, alchemist, bomb, village, sniper; hero quincy; 'chimps' (impoppable, chimps): 12 spots - desperado, dart, sniper, village, glue, alchemist, wizard; hero churchill.

**Sources:**

- https://www.bloonswiki.com/Underground - bloonswiki Underground
- https://bloons.fandom.com/wiki/Underground/Strategies - fandom Underground/Strategies
- https://www.youtube.com/watch?v=9jvPhl28e5E - BlueCliff - Underground Hard No MK (ft. Quincy)
- https://www.youtube.com/watch?v=eXTI3EzbFgc - retrogaming fun - Underground CHIMPS no abilities no mid round actions (v50)
- https://www.youtube.com/watch?v=h0GpxS2xX_w - OneEyedDeacon - Underground Chimps by Bomb Axis (v49.3)
- https://www.youtube.com/watch?v=qgB5zf-TXwY - OneEyedDeacon - Underground Chimps w/ abilities and micro (v53.2)
- https://www.youtube.com/watch?v=T_X46zgnkfo - BlueCliff - Underground Magic Monkeys Only, no MK (ft. Quincy)

### High Finance

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Lanes alternate (odd rounds the long S lane, even rounds - including the first MOAB - the short U lane); free space is only the central park and its pond, which touch both lanes. Boat in the pond, ninja/alchemist on the park corners; buildings can be bought for room.

**Lanes:** alternating.

**What the guides found** (detail from the sources):

- Odd rounds (S lane): enters top-right (~0.80,0.13), runs left along the top (y~0.14) to ~0.16, down the left side to y~0.48, right along y~0.48 across the pond bridge to ~0.68, down to y~0.85, left along the bottom and exits bottom-left (~0.0,0.86).
- Even rounds (U lane): enters top (~0.32,0.0), down x~0.32 past the park's left side, round the bottom of the park (y~0.88), up x~0.52 past the park's right side, exits top (~0.53,0.0).
- Free land (the placement check-legal): four small corners of the park - top-left (~0.371,0.40), top-right (~0.484,0.39), bottom-left (~0.371,0.68), bottom-right (~0.489,0.66) - plus the lower pond (~0.425,0.62) for Buccaneer/Sub.
- 15 removable building lots (total $12,550) - see removables; $1,500 lots are the only Heli/Farm spots; buildings block line of sight once built and before (construction fences).

**Towers that work:**

- buccaneer 5-2-0: Carrier Flagship from the pond; planes are global so the line-of-sight buildings do not matter.
- glue 5-2-0: Bloon Solver on top-centre of the $750 park building covers both lanes; puddle chains clean up ceramics/MOABs.
- heli 2-0-5: Comanche Commander (with Geraldo's items) - single-lane alternating map suits helis; needs a $1,500 building.
- heli 5-2-0: Apache Prime ignores line of sight and the long straight lanes suit its laser/plasma (fandom tip).
- ninja 4-0-2: Early DPS from a park corner (3-0-2 first) (BlueCliff Hard).
- boomerang 5-0-2: Glaive Lord late in BlueCliff Hard.

**Avoid:** farm (only fits on bought buildings); super (too big for the park corners); tack (park corners touch only short stretches of each lane).

**Removable obstacles and map switches:**

- Building lot - Upper-middle far-left ($1500): mid game when a Heli (Comanche/Apache) or farm is wanted. fits Heli Pilot / Banana Farm (only the $1,500 buildings do)
- Building lot - Lower-middle far-left ($1500): mid game when a Heli (Comanche/Apache) or farm is wanted. fits Heli Pilot / Banana Farm
- Building lot - Upper-middle middle-left ($1000): only when more space is needed. fits up to Village size; inside the S-lane's top-left loop
- Building lot - Lower-middle middle-left ($750): only when more space is needed. fits up to Spike Factory size
- Building lot - Bottom middle-left ($350): only when more space is needed. fits up to Boomerang size; below the S-lane exit stretch
- ... and 10 more (see the sources)

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff - High Finance Hard, no MK, no heroes, no farms, NO buildings bought (hero: none; youtube description, ~v30 (video 4 years old)). Source: https://www.youtube.com/watch?v=C5QklAgqeGQ

  settings: auto-start OFF; R3: Ninja 0-0-0 (park corner); R3 (after round): Dart 0-0-0 (park corner); R6: Ninja 1-0-0; R8: Ninja 1-0-1; R10: Ninja 1-0-2; R11: Ninja 2-0-2; R15: Ninja 3-0-2; R17 (after round): Buccaneer 0-0-0 in the lower pond; R19: Buccaneer 0-1-0; R21: Buccaneer 1-1-0; R23: Buccaneer 1-2-0; R25: Buccaneer 2-2-0; R32: Buccaneer 3-2-0; R35 (after round): source SELLS the Dart, then Alchemist 3-0-0 (bot: no sell - put the Alchemist in the free corner); R39: Alchemist 4-0-1; R41: Village 0-2-0; R44: Village 2-2-0; R49: Buccaneer 4-2-0; R59 (after round): source SELLS the Ninja (and the Village if still short) for Buccaneer 5-2-0 (bot with Double Cash/MK: just buy 5-2-0 when affordable); R75 (after round): Boomerang 4-0-2 (source puts it where a sold tower stood); R79: Boomerang 5-0-2; Village 3-2-0; GG

*chimps, used for the 'chimps' hints* - unescaped - High Finance CHIMPS ft. Quincy: Pirate Lord + Perma-Spike-ish spike + Inferno Ring + Glue Storm (hero: Quincy (Cyber Quincy skin); youtube description, v34.3, author: 'updated for v44.1'). Source: https://www.youtube.com/watch?v=YSHTM5sTkqU

  WARNING: ability-heavy (Pirate Lord hook, Quincy Rapid Shot/Storm of Arrows, Glue Storm). The bot fires abilities on cooldown, which wastes hooks on early MOABs; R6: Quincy; R7: Dart, targeting Strong; R10: Buccaneer (lower pond); R12: Buccaneer 0-1-0; R15: Quincy Rapid Shot on pinks; R17: Spike Factory; R19: Spike 0-0-2, targeting Smart; R20: Buccaneer 1-1-0; R21: Buccaneer 2-1-0; R26: Buccaneer 2-2-0; R27: Buccaneer 2-3-0; then Spike -> 3-0-2; R39: Buccaneer 2-4-0 (Monkey Pirates, source buys mid-round); R40: Rapid Shot on the MOAB; R42: Alchemist 3-0-0; R43: Village 0-0-0; R44: Village 0-2-0; R45: Village 2-2-0; then Spike -> 4-0-2; Alchemist -> 4-2-0; R60-R87: use the Buccaneer hook on BFBs/ZOMGs (bot: on cooldown); R70: Buccaneer 2-5-0 (Pirate Lord); then Tack 3-0-0; R74: Tack 4-2-0; R87: Tack 5-2-0 (Inferno Ring) on Strong; Alchemist 4-2-0 (second); Village 4-2-0; Glue 0-4-2; R95: Glue Strike (ability); R96: Glue 0-5-2 (Glue Storm); R100: Ice 4-2-0; optional extra tower e.g. Sniper 2-0-4 below the Glue

Other builds found:

- hard: Bot adaptation (inferred): Obyn + park corners + pond Flagship, then buy the $750 park building for a Bloon Solver (hero: Obyn Greenfoot) - https://bloons.fandom.com/wiki/High_Finance
- magic_only: BlueCliff - High Finance Magic Monkeys Only, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=vpjIMoJXle8
- abr: BlueCliff - High Finance Alternate Bloons Rounds, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=9Q0XfBns-C0

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): 2TC: Perma Charge (Boomerang 0-5-2) + Geraldo (v31); heroless/cheapest 2TC Bounty Hunter (Desperado 2-4-0) + Popseidon (Mermonkey 0-5-2) (v52). LCC $42.1k (v49.3, used an edef ability bug). CHIMPS guides seen: wellordering PoD + Sky Shredder (v45 beginner), sYnce Sauda + Ray of Doom (v55.2, aiming), G00SE Archmage + Popseidon (v46.3), Kaka Cake no-abilities (v27), Jajajosh WLP without ...

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 4 spots - ninja, dart, buccaneer, alchemist; 'chimps' (impoppable, chimps): 5 spots - dart, buccaneer, spike, alchemist; hero quincy.
Removables recorded: Removable ($750, optional, ~R30).

**Sources:**

- https://www.bloonswiki.com/High_Finance - bloonswiki High Finance
- https://bloons.fandom.com/wiki/High_Finance - fandom High Finance
- https://www.youtube.com/watch?v=C5QklAgqeGQ - BlueCliff - High Finance Hard No MK (ft. No Heroes), no obstacles removed
- https://www.youtube.com/watch?v=w53Z25TUIrQ - wellordering - High Finance CHIMPS guide for beginner (v45)
- https://www.youtube.com/watch?v=Ud32kDtLoYY - G00SE - High Finance CHIMPS w/ Archmage and Popseidon (v46.3)
- https://www.youtube.com/watch?v=9G6DQGSBA94 - sYnce - High Finance CHIMPS w/ Sauda & Ray of Doom (v55.2)
- https://www.youtube.com/watch?v=YSHTM5sTkqU - unescaped - High Finance CHIMPS ft. Cyber Quincy (v34.3, updated v44.1)

### Another Brick

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** A brick wall separates the outgoing and returning halves of the lane, so most towers see only one half. Use towers that ignore the wall (Flagship, heli, sniper, guided wizard) and the land right of the U-turn at the far right, which sees both halves.

**Lanes:** single.

**What the guides found** (detail from the sources):

- Track: enters at the top (~0.245,0.0), runs down to y~0.40, right along y~0.40 to the far right (~0.77), U-turns (~0.78,0.47), returns left along y~0.55 to x~0.25 and exits at the bottom (~0.245,1.0).
- Wall (line-of-sight blocker) fills the strip between the two horizontal stretches (y~0.43-0.52, x~0.22-0.73) and the vertical strip left of the entrance/exit lane (x~0.15-0.22).
- Two flooded potholes for water towers: top-right pond (~0.55-0.72, 0.15-0.30; sees only the top half) and bottom-left pond (~0.30-0.42, 0.63-0.88; sees the exit stretch, progress ~0.76-1.0).
- Left of the wall: small free patch plus two brick pallets ($1,000 each) that clear the whole left side; towers there are LOS-blocked from the track (farms, Heli, Ace, Sniper, Mortar only). The pallets do NOT block line of sight (only placement).

**Towers that work:**

- buccaneer 5-2-0: Carrier Flagship sees over the wall and uses the whole track; Destroyer/Aircraft Carrier carry the midgame; pair with Brickell.
- spike 0-0-5: Perma-Spike near the exit with Jungle Drums / Berserker Brew effectively guarantees the win (single lane).
- wizard 0-0-5: (or 4-0-2) Prince of Darkness raises graveyard over the walls; Guided Magic sees over walls (BlueCliff uses 4-0-2).
- heli 5-2-0: Apache Prime - long straight segments; core of the fandom CHIMPS build. Pursuit included.
- alchemist 4-2-0: (or 4-0-1) Brews on Sauda/Heli/Spike (fandom CHIMPS) or Ninja (BlueCliff Hard).
- ninja 4-0-2: BlueCliff Hard early/mid DPS.

**Avoid:** tack (sees one half of the track from almost anywhere); farm (no room without buying a pallet).

**Removable obstacles and map switches:**

- Brick pallet (upper) ($1000): only if spare cash and the build wants farms/global towers (Hard). clears space left of the wall; towers there cannot see the track except global ones (Heli, Ace, Sniper, Mortar, Sun Temple, Arcane Mastery)
- Brick pallet (lower) ($1000): same as above. same as above; pallets do not block line of sight, only placement

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff - Another Brick Hard, no MK, no farms (ft. Quincy) (hero: Quincy; youtube description, ~v32 (video 4 years old)). Source: https://www.youtube.com/watch?v=igJ6Bsvrnwc

  settings: auto-start OFF; R3: Ninja 0-0-0; R3 (after round): Dart 0-0-0; R6: Ninja 1-0-0; R8: Ninja 1-0-1; R10: Quincy; R13: Ninja 2-0-1; R14: Ninja 2-0-2; R17: Ninja 3-0-2; R21: Alchemist (a) 0-0-0; R22: Alchemist (a) 1-0-0; R26 (after round): Alchemist (a) 2-0-0; R27 (after round): Alchemist (a) 3-0-0; R33: Ninja 4-0-2; R35 (after round): Alchemist (a) 3-0-1; R37 (after round): Alchemist (a) 4-0-1; R39 (after round): Wizard 3-0-0; R40: Quincy ability; R41: Wizard 3-0-2; R42: Village 2-0-0; R49: Wizard 4-0-2; R55: Super Monkey 0-3-0; R56: Super 1-3-0; R58: Super 2-3-0; R62 (after round): Alchemist (b) 4-0-1; R74: Super 2-4-0; R75: Village 2-2-0; R78: Quincy level-10 ability on the 1st rush, Super ability on the 2nd (bot fires on cooldown); R79: Sniper 4-0-2, targeting Strong; GG

*chimps, used for the 'chimps' hints* - Fynn BTD6 - Another Brick CHIMPS, no abilities, no RNG (Sauda, Ninja, Heli, PoD, MOAB Press, Perma-Spike) (hero: Sauda; youtube description, v27.3 (old)). Source: https://www.youtube.com/watch?v=a6PNBW8MGtE

  R6: Sauda; R9: Ninja 0-0-0; R10: Ninja 0-0-1; R12: Ninja 1-0-1; R13: Ninja 2-0-1; R17: Ninja 3-0-1; R19: Ninja 3-0-2; R24: Alchemist 1, 0-0-2; R27: Alchemist 1 -> 0-0-3; R34: Ninja 4-0-2; R37: Village 1, 2-0-0; R39: Heli 1-0-0; R40: Heli 2-0-0; R41: Village 1 -> 2-0-2; R44: Heli 3-0-2; R55: Heli 4-0-2; R57: Alchemist 2, 4-2-0; R60-62: Wizard 0-0-4 -> 2-0-4; R77: Wizard 2-0-5 (Prince of Darkness); R79: Village 1 -> 3-0-2; R80-82: Glue 0-1-3 (Strong); 3x Boomerang 2-0-4 (MOAB Press, Strong); R85: Spike Factory 0-0-4 (Smart); Alchemist 3-0-0; R94: Spike Factory 0-0-5 -> 0-2-5 (Perma-Spike); R96: optional Ninja 0-0-4 for safety (source says not needed); R97-98: Mortar 0-0-3 -> 0-0-4 (bot: skip, needs aiming)

Other builds found:

- chimps: fandom wiki - Another Brick CHIMPS: Sauda + Apache Prime + Perma-Spike (minimal micro) (hero: Sauda) - https://bloons.fandom.com/wiki/Another_Brick/Strategies
- magic_only: BlueCliff - Another Brick Magic Monkeys Only, no MK (ft. Quincy) (video title says Hard) (hero: Quincy) - https://www.youtube.com/watch?v=YOv2WNX_vQY
- double_hp: BlueCliff - Another Brick Double HP MOABs, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=NSk5nrLLD3I
- impoppable: BlueCliff - Another Brick Impoppable, no MK (ft. Quincy) (hero: Quincy) - https://www.youtube.com/watch?v=cFAsQskNYA0

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): 2TC: Perma Charge (Boomerang 0-5-2) + Geraldo (v31); heroless 2TC Wizard Lord Phoenix 2-5-0 + Golden Justice 2-5-0 (as listed by the index) (v49.3). LCC $44.7k (v44.1). Chewie's Archmage LCC under $90k (v34). Other CHIMPS: BTD Flagship all T5 Helis no abilities/no micro (v44.1), Bloons mind Archmage no micro (v55.1), Cosmos Quincy no abilities.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 9 spots - ninja, dart, alchemist, wizard, village, super, sniper; hero quincy; 'chimps' (impoppable, chimps): 13 spots - ninja, alchemist, village, heli, wizard, glue, boomerang, spike; hero sauda.

**Sources:**

- https://www.bloonswiki.com/Another_Brick - bloonswiki Another Brick
- https://bloons.fandom.com/wiki/Another_Brick - fandom Another Brick
- https://bloons.fandom.com/wiki/Another_Brick/Strategies - fandom Another Brick/Strategies
- https://www.youtube.com/watch?v=igJ6Bsvrnwc - BlueCliff - Another Brick Hard No MK (ft. Quincy)
- https://www.youtube.com/watch?v=_HvZV1bq8Bo - BTD Flagship - Another Brick CHIMPS with all T5 Helis v44.1 (No Abilities / No Micro)
- https://www.youtube.com/watch?v=GJbsdCb_XTI - Bloons mind - Another Brick CHIMPS v55.1
- https://www.youtube.com/watch?v=a6PNBW8MGtE - Fynn BTD6 - Another Brick CHIMPS No Abilities (v27.3)

### Peninsula

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Short lane round a mountain that blocks sight; over 80% of the space is water. Land is the mountaintop (global towers and supports only) and a small plot by the bottom bend. Water builds win: spam 2-0-4 subs along the lane with Brickell, or snipers/heli on the mountaintop.

**Lanes:** single.

**What the guides found** (detail from the sources):

- Track: enters top-left (~0.20,0.03), runs down the left side of the mountain (x~0.25), along the bottom (y~0.72, x 0.30-0.52) and up the right side (x~0.58-0.62) to the exit at the top (~0.67,0.03).
- Mountain (centre) is a big line-of-sight blocker; mountaintop green area (~0.38-0.47, 0.03-0.33) is high ground - a Sniper there sees the whole track; short-range towers there reach nothing (the placement check).
- Small land plot at the bottom-right of the peninsula (~0.55-0.60, 0.67-0.78) right next to the bottom bend (covers progress ~0.54-0.70) - the only real land DPS spot; fits 2-3 small towers.
- Water everywhere else: best sub spots are the water right of the exit side (~0.64-0.69, 0.30-0.46; covers progress ~0.67-0.96), left of the entrance (~0.15-0.17, 0.23-0.28; progress ~0-0.27) and below the bottom bend (~0.33-0.43, 0.85-0.87).

**Towers that work:**

- sub 2-0-4: (2-0-5 for the Sub Commander) Sub Commander strategies are among the most used here: lots of water and a decent straight line for ...
- buccaneer 5-2-0: Carrier Flagship sees over the mountain and covers the whole lane; water buff; pair with Brickell.
- spike 0-0-5: Perma-Spike on the top-right seaweed rock (removable, near the exit) with a 3-0-1 Berserker Brew catches leaks on this short lane.
- sniper 2-5-0: (or 4-0-2) From the mountaintop it sees everything (BlueCliff Hard uses 2-5-0 Elite Sniper with Supply Drop cash).
- heli 2-0-5: Comanche Commander from the mountaintop (BlueCliff Hard, retrogaming fun CHIMPS, NamelessBandicoot).
- beast_handler 4-0-0: Orca (max power) + Overclock wipes most rounds; needs the left seaweed rock and 6 Great Whites merged in.

**Avoid:** tack (no land next to the track except the tiny bottom-right plot); druid (no land near the track); farm (only on the mountaintop).

**Removable obstacles and map switches:**

- Seaweed rock - top-right island ($500): mid/late game (retrogaming fun R91; Zareef ~R45). Perma-Spike/Spike Factory spot right by the exit (wiki); last line of defence
- Seaweed rock - left of the peninsula ($500): early (retrogaming fun R18 'unlock the first island' for Etienne). land next to the first third of the lane; Orca/Beast Handler spot (wiki)
- Seaweed rock - bottom-left island ($500): late (Zareef ~R75 for an Ice Monkey 0-3-1). far from the track; Ice monkey spot to freeze water for land towers

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff - Peninsula Hard, no MK, no heroes, no water towers, no farms (hero: none; youtube description, ~v30 (video 4 years old)). Source: https://www.youtube.com/watch?v=H01urmdcmRc

  settings: auto-start OFF; Sniper cash abilities (Supply Drop) are used, source says winnable without; R3: Ninja 0-0-0 (bottom-right plot); R3 (after round): Dart 0-0-0 (bottom-right plot); R6: Ninja 1-0-0; R8: Ninja 1-0-1; R10: Ninja 2-0-1; R11: Ninja 2-0-2; R15: Ninja 3-0-2; R18: Sniper 1-0-0 on the mountaintop, targeting Strong; R20: Sniper 1-1-0; R21: Sniper 1-2-0; R30 (after round): Heli 2-0-0 on the mountaintop; R34: Heli 2-0-2; R35 (after round): Alchemist (a) 3-0-0; R39 (after round): Heli 2-0-3; Alchemist (a) 3-0-1; Alchemist (b) 2-0-0; R42 (after round): Ninja 4-0-2; R45: Sniper 1-3-0; R49: Sniper 2-4-0; R50: Sniper targeting First; R51/54/57/61/63/66/69/72/74/77: Sniper (Supply Drop) ability - bot fires on cooldown; R54 (after round): Alchemist (b) 4-0-1; R58: Sniper 2-5-0, targeting First; R62 (after round): Heli 2-0-4; R67: Village 2-2-0; R77: Heli 2-0-5; GG

*chimps, used for the 'chimps' hints* - 0Python BTD6 - EASIEST Peninsula CHIMPS ft. Brickell, no micro / no abilities (Sub spam) (hero: Admiral Brickell; youtube description, ~v52 (video 10 months old)). Source: https://www.youtube.com/watch?v=bkeuo0q7XbY

  source: no abilities needed; R14/R63/R99 are risky, R100 recommends First Strike on the last BAD layer (bot fires abilities on cooldown anyway); R7: Dart (bottom-right plot) - source starts with a sub before this (the line reads 'sub upgrade 001 R9'); start: Sub (1) 0-0-0 in the water right of the exit side (implied); R9: Sub (1) 0-0-1; R11: Sub (1) 1-0-1; R14 (mid-round in source; bot: buy as soon as affordable): Admiral Brickell in the water; R19: Sub (1) 1-0-2; R22: Buccaneer 0-0-2; R27: Buccaneer 0-2-2; R29: Sub (1) 2-0-3; R36: Sub (1) 2-0-4; R39: Alchemist 3-2-0; R40: Buccaneer 0-3-2; R44: new Sub (2) 2-0-4; R49: new Sub (3) 2-0-4; R50: new Sub (4) 2-0-4; R62: 2 Darts -> 4-2-0; R70: bottom-left Sub -> 2-0-5 (Sub Commander); R71: Buccaneer 0-0-2 right of the T5 Sub; R72-R81: 4 more 2-0-4 Subs (total 8); R83: Ice 4-1-0; R84: Village 2-3-0; R90-R93: 2 more 2-0-4 Subs; R94: Sub 2-4-0 (First Strike); R96-R100: Mermonkey 4-0-2; keep spamming 2-0-4 Subs

Other builds found:

- chimps: retrogaming fun - Peninsula CHIMPS, no abilities, no mid-round actions (uses 2 removables) (hero: Etienne) - https://www.youtube.com/watch?v=_QrcbP0y2Fw
- magic_only: BlueCliff - Peninsula Magic Monkeys Only, no MK (ft. Quincy) - buys 2 seaweed rocks (hero: Quincy) - https://www.youtube.com/watch?v=LH33NGnW1jk

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): 2TC: Cleansing Foam (Engineer 0-3-2) + Geraldo (v44); heroless 3TC Carrier Flagship 5-0-2 + Spirit of the Forest 2-5-0 + Carpet of Spikes 2-5-0 (v44.1). LCC $47.2k (v18.1). Index CHIMPS start: 'Engi start' (https://www.reddit.com/r/btd6/comments/flot20/engineer_start_in_peninsula/).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 7 spots - ninja, dart, sniper, heli, alchemist, village; 'chimps' (impoppable, chimps): 13 spots - dart, sub, buccaneer, alchemist, mermonkey; hero admiral_brickell.

**Sources:**

- https://www.bloonswiki.com/Peninsula - bloonswiki Peninsula
- https://bloons.fandom.com/wiki/Peninsula/Strategies - fandom Peninsula/Strategies
- https://www.youtube.com/watch?v=H01urmdcmRc - BlueCliff - Peninsula Hard No MK (no heroes, no water)
- https://www.youtube.com/watch?v=bkeuo0q7XbY - 0Python BTD6 - EASIEST Peninsula CHIMPS ft. Brickell (no micro/abilities)
- https://www.youtube.com/watch?v=_QrcbP0y2Fw - retrogaming fun - Peninsula CHIMPS no abilities (v51)
- https://www.youtube.com/watch?v=w_2iqqkna8M - OneEyedDeacon - Peninsula Chimps with Flying Fortress (v49.3)
- https://www.youtube.com/watch?v=vjKCjFYtV1s - NamelessBandicoot - Peninsula CHIMPS Flagship/Perma-Spike/Comanche

### Cargo

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** The parked trucks block sight from the big dock until round 39, when they drive off and open a MOAB-only lane that crosses the main road. Put the short-range core in the strip inside the main road's top-right bend (it hits both lanes) and add snipers.

**Lanes (single).** main road for bloons; a MOAB-only lane opens at round 39

**What the guides found** (detail from the sources):

- Main (bloon) lane: left edge fy~0.28 -> right to fx~0.67 -> down to fy~0.80 -> exits right. Short (13.9 RBS per BTD6 Index).
- MOAB-only lane opens at the start of R39 (since v33.3; R40 before): enters from the bottom edge at fx~0.54, up to fy~0.35, left to fx~0.31, up across the main road at (0.31,0.28), exits at the top. MOAB lane length ~10.7-11.7 (one of the shortest).
- The parked trucks along the MOAB lane are line-of-sight blockers and unplaceable until R39 (game event destroys those areas). BOT NOTE: in the bot's geometry the truck sight-blocker is permanent and the MOAB path is flagged hidden, so the placement check ...
- Best dual-lane spot: the green strip right of the MOAB lane / left of the road's vertical leg, fx 0.607-0.625, fy 0.37-0.70 (only ~1 tower wide; stack towers vertically).

**Towers that work:**

- sniper 0-2-4 -> 0-2-5 / 0-5-2 / 5-2-0: Global range from the dock (no lane split problem); the 3 tier-5 snipers + 4-2-0 alch + 3-0-2 village win CHIMPS with no ...
- wizard 0-2-5: Prince of Darkness: 'great cleanup tower for this map' (zombie bloons walk both lanes).
- boomerang 0-0-2 early, 2-0-4 at R100; 5-0-x Glaive Lord late: Cheap early pierce in the corner strip; Glaive Lord just below the MOAB lane's first bend covers both lanes (bloonswiki).
- alchemist 4-2-0 (3-2-0 earlier): Buffs the main sniper / sub; every listed build uses one.
- village 2-0-2 -> 3-0-2 (CHIMPS) / 4-2-0 (Hard): Discount + range; camo via 2-x-x/x-2-x.
- sub 2-0-4 / 3-0-1 / x-4-x: Water all around; 3-0-1 in the top-left water strips camo; 2-0-4 sub + 4-2-0 alch carries R40-80 in the Mathgodpi and fandom ...

**Avoid:** tack (almost no legal spot touches the road).

**Removable obstacles and map switches:**

- Graffiti truck (top-left) ($500): only purchasable after R38 is beaten (unlocks with the R39 MOAB lane); optional, any time cash is spare. Frees a dock spot next to the lane intersection (0.31,0.28) and removes a sight blocker; no guide required it.
- Graffiti truck (bottom-right) ($500): after R38; optional. Extends the corner strip downward next to the exit and removes a sight blocker; no guide required it.

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Quincy + Ninja 4-0-2 + Alch + Wizard + 3x Bomb 2-0-4 + Ice 2-0-5 (no Monkey Knowledge) (hero: Quincy; youtube description, ~v27-v30 (2021-22); bot also has MK so it is easier). Source: https://www.youtube.com/watch?v=JwH3d8_WOBQ

  R3: Quincy (corner strip top); R4: Dart (optional, saves a couple of lives); R5: Quincy targeting Strong; R7 (after round): Quincy back to First, place Ninja; R9: Ninja 0-0-1; R10: 1-0-1; R12: 2-0-1; R13: 2-0-2; R18: 3-0-2; R25: (sell Dart - optional, bot may skip) Alchemist 2-0-0, targeting Strong; R29: Wizard 3-0-0; R35: Wizard 3-0-2; R39 (after round): Bomb 2-0-3; Ninja 4-0-2; Alch 3-0-1; R40: Quincy level-3 ability at round start (blind ability press is fine); R48: Wizard 4-0-2; R49: Bomb 2-0-4; Alch 4-0-1; R59: second Bomb 2-0-4; Village 3-2-0; R62: Village 4-2-0; Ice 2-0-4 (0-2-4 works too) on Strong; R63: Ice to First; R76/R78: Quincy level-10 ability (optional); R78: Ice 2-0-5; R79: third Bomb 2-0-3; R80: Quincy ability (optional) - win

*chimps, used for the 'chimps' hints* - Sauda + Axis of Havoc snipers + Prince of Darkness, no abilities, no micro (hero: Sauda; youtube description, v49.3). Source: https://www.youtube.com/watch?v=9OiV2P_YvCA

  R6: Sauda at the top-right corner (inside the road's bend); R8: Boomerang 0-0-0 left of Sauda (as top-left as possible); R10: Sniper1 0-0-0 targeting Strong (across the barriers - on the dock); R12: Sniper1 0-0-1; R14: 0-0-2; R15: 0-1-2; R17: 0-2-2, targeting First; R18: Boomerang 0-0-1; R19: Boomerang 0-0-2; R29: Sniper1 0-2-3; R37: Sniper1 0-2-4; R40: Village1 2-0-2; R42: Wizard1 0-0-3; R44: 0-0-4; R45: 0-2-4; R47: Alch1 3-2-0 next to Sniper1; R60: Wizard1 0-2-5 (Prince of Darkness); R63: Alch1 4-2-0; R65: Sniper2 0-3-2; R71: 0-4-2; R78: 0-5-2 targeting First; R79: Sniper3 3-2-0 targeting Strong; R80: 4-2-0; R90: 5-2-0; R95: Sniper1 0-2-5; R96: Alch2 4-2-0 for Sniper3; R97: Village1 3-0-2; R98: Glue1 0-2-4 on Strong, as low as possible inside village range; R99: Engineer1 0-3-1 next to Glue1 in village range (foam target in front of the MOAB lane - bot cannot aim, skip or leave default); R100: Tack1 2-0-4 under Sniper3 + Boomerang1 2-0-4 on Strong + Tack3 2-0-4 under Wizard1 in discount range

Other builds found:

- chimps: Striker Jones + darts + subs -> Sub Commander + Perma Brew + Elite Defender/Sniper (no abilities, no micro) (hero: Striker Jones) - https://www.youtube.com/watch?v=hzVxMvuAEOI
- chimps: Old meta (v26.2): Obyn, 3 darts + sub, 2-0-4 sub, six 0-1-4 druids, 4-2-0 alch -> Avatar of Wrath, 2-3-0 village, 0-4-0 ... (hero: Obyn) - https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Perma Charge (boomerang 0-5-2) + Geraldo L20 (v31); heroless Carrier Flagship 5-0-2 + Glaive Lord 5-0-2 + M.A.D 0-5-2 (v44.1); cheapest MOAB Domination (ace 0-2-5) + Geraldo (v31.2). LCC 51,750 (v31, Chainsaw); others 66-80k. Removal cost listed $1,000 total.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 7 spots - dart, ninja, alchemist, wizard, bomb, village; hero quincy; 'chimps' (impoppable, chimps): 9 spots - boomerang, sniper, village, alchemist, glue; hero sauda.
Model gap: The trucks are modelled as a permanent sight blocker and the MOAB lane as hidden: dock spots read 0 reach although they cover the MOAB lane from round 39.

**Sources:**

- https://www.bloonswiki.com/Cargo - Cargo - Blooncyclopedia
- https://bloons.fandom.com/wiki/Cargo - Cargo - Bloons Wiki (fandom)
- https://bloons.fandom.com/wiki/Cargo/Strategies - Cargo/Strategies (fandom)
- https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies - C.H.I.M.P.S./Strategies (fandom)
- https://www.youtube.com/watch?v=9OiV2P_YvCA - OneEyedDeacon - Cargo CHIMPS no abilities/no micro, Axis of Havoc (v49.3)
- https://www.youtube.com/watch?v=JwH3d8_WOBQ - BlueCliff - Cargo Hard, no MK, Quincy
- https://www.youtube.com/watch?v=hzVxMvuAEOI - Mathgodpi - Cargo CHIMPS zero effort (subs)

### Spillway

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Four lanes, all active, circle a small central pool behind four inflatable walls that block sight from almost everywhere. Players put a ninja on the metal barrel in the exact centre of the loop and use damage that ignores the walls (Prince of Darkness, Carrier Flagship, Neva-Miss).

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- Entrances: the 4 corners (top-left, top-right, bottom-left, bottom-right); all four active each round; 22-23.6 RBS each.
- Central loop centred ~(0.43,0.49); every lane enters it, loops 1.75 times counter-clockwise and leaves on the next lane clockwise.
- Central barrel at ~(0.425, 0.49) (bbox fx 0.41-0.44, fy 0.46-0.51): fits exactly ONE small-footprint tower (Dart, Tack, Ice, Glue, Sniper, Ninja, Alchemist; small heroes such as Ezili/Silas). Not legal in the bot model - hard-code it.
- Four removable inflatable walls ($2,000 each) between the side pools and the loop: LEFT wall ~(0.31,0.48), TOP ~(0.43,0.27), RIGHT ~(0.545,0.47), BOTTOM ~(0.43,0.69) (note: the game's internal names are mirrored - 'RemovableObjectRight' is the screen-left ...

**Towers that work:**

- ninja 0-0-0 -> 0-0-1 -> 1-0-1 -> 2-0-1 -> 2-0-2/3-0-2 -> 4-0-2 ...: On the barrel it covers the whole loop; standard CHIMPS start for most modes.
- wizard 2-0-5 / 0-2-5 Prince of Darkness, 5-2-0 Archmage: Guided Magic ignores walls; zombie bloons from PoD circle the loop like real bloons; Archmage 5-2-0 is the wiki's recommendation.
- sub 2-0-4 -> 2-0-5 Sub Commander (Hard) / 5-0-0 Energizer ...: Right pool after buying the right wall (BlueCliff Hard); reactor sub ignores line of sight.
- buccaneer 3-2-0 -> 5-2-0 Carrier Flagship: Global planes; towers on the flagship deck see over the walls (wiki).
- ace 2-0-3 (Neva-Miss): Global; OED CHIMPS build.
- heli 2-x-x Pursuit: Global, ignores walls (inferred from map geometry; wiki lists Sky Shredder/Dart Storm for centred path).

**Avoid:** sniper (outside the walls it sees only the straight lanes).

**Removable obstacles and map switches:**

- Inflatable wall (one of four; RIGHT wall most used) ($2000): Hard (BlueCliff): R29, right wall, before placing a 2-0-0 sub in the right pool; CHIMPS: bottom wall R21-40 for a Buccaneer (Fungoid v31), left wall R40 for a .... Opens line of sight from that pool/side to the central loop so water towers and pool-side towers can hit the loop; adds a land spot near the loop.

**Builds (in buy order):**

*hard, used for the 'hard' hints* - No hero: Ninja on barrel + Sniper + Sub Commander (right wall removed) + Prince of Darkness (hero: none (bot may add Psi); youtube description, v28.2 (2021-22); no MK). Source: https://www.youtube.com/watch?v=e-cqKdIJ7pM

  R3: Ninja on the barrel; R5: Ninja 0-0-1; R6: 1-0-1; R9: 2-0-1; R13: 3-0-1; R14: 3-0-2; R19: Sniper 1-0-2 as close to the bottom-left lane as possible, targeting Strong; R29: buy the RIGHT wall ($2,000); Sub 2-0-0 in the right pool as close to the track as possible; R31: Sub 2-0-1; R33: 2-0-2; R35: 2-0-3; R38: Ninja 4-0-2; R39 (end of round): Sub 2-0-4; R43: Village 2-0-0; R47: Wizard 2-0-4 near the top-right lane and inside village range (optional Alch 3-0-1 near sub+wizard); R59: (sell Sniper - optional) Wizard 2-0-5 (Prince of Darkness); R63: (sell Ninja and rebuy as 2-0-4 on Strong - bot may simply keep the 4-0-2 ninja); R77: Sub 2-0-5 (Sub Commander) - win R80

*chimps, used for the 'chimps' hints* - Ninja barrel + Etienne + Wizard Archmage + Mermonkey + sniper (no abilities, no mid-round actions) (hero: Etienne; youtube description, v49). Source: https://www.youtube.com/watch?v=WVzGzQM5RPA

  R6: Ninja 0-0-0 as centred as possible (the barrel); R7: Sniper 0-0-0 targeting Strong; R11: Etienne; R13: Wizard 1-0-0; R15: 2-0-0; R19: 2-2-0 (relocate Wall of Fire into the loop - bot: skip relocation); R21: Sniper 1-0-0; R22: 1-1-0; R27: Village 0-0-0; R32: Village 0-0-2; Wizard 3-2-0; R35: Sniper 2-1-0; R37: Village 2-0-2; R40: buy the LEFT wall ($2,000); Mermonkey 3-2-0; Etienne targeting First; R44: Mermonkey 4-2-0; R50: Wizard 4-2-0; R63: Mermonkey 5-2-0; R80: Wizard 5-2-0 (Archmage); R83: Spike Factory 2-4-0 (ability not needed); R95: Spike 2-5-0; R98: Mortar 0-0-4 aimed at the loop (bot: replace with a 1-4-0 spike or First Strike sub); R99: Sniper 4-2-0

Other builds found:

- chimps: Psi L20 + barrel Ninja 2-0-2 + Mortar 2-3-0 + Ace 2-0-3 + Energizer sub + PoD/Archmage wizards (hero: Psi) - https://www.youtube.com/watch?v=KW-50Pa14jU
- chimps: Adora + barrel Ninja 4-0-1 + Carrier Flagship (bottom wall removed) + PoD wizard + Tack Zone (hero: Adora) - https://www.youtube.com/watch?v=4Rj8lYN4odE
- chimps: Striker Jones + barrel Ninja 1-0-1 -> 2-0-4 -> 2-0-5 + two mortars (TBO, Blooncineration), no abilities (hero: Striker Jones) - https://bloon.games/how-to-beat-chimps-on-spillway/

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Perma Charge 0-5-2 + Geraldo (v31); cheapest Tyrannosaurus Rex (beast 0-4-1) + Geraldo (v44); heroless Blooncineration 2-0-5 + Apache Prime 5-0-2 (v51). LCC 42,105 (v40.2) / 44,820 (v44). Indexed CHIMPS start: Beast Handler start R6-7. Removal cost listed $8,000 total (4 x $2,000).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 4 spots - sniper, sub, village, alchemist; hero psi; 'chimps' (impoppable, chimps): 5 spots - wizard, village, sniper, spike; hero etienne.
Removables recorded: RemovableObjectLeft ($2000, optional, ~R29).
Model gap: The barrel in the centre of the loop (0.425, 0.49) has no legal cell in the model; every guide puts a ninja there (~28% of all four lanes).

**Sources:**

- https://www.bloonswiki.com/Spillway - Spillway - Blooncyclopedia
- https://bloons.fandom.com/wiki/Spillway - Spillway - Bloons Wiki (fandom)
- https://bloons.fandom.com/wiki/Spillway/Strategies - Spillway/Strategies (fandom)
- https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies - C.H.I.M.P.S./Strategies (fandom)
- https://www.bloonswiki.com/Strategy:CHIMPS - Strategy:CHIMPS (bloonswiki)
- https://www.youtube.com/watch?v=e-cqKdIJ7pM - BlueCliff - Spillway Hard no MK no heroes
- https://www.youtube.com/watch?v=WVzGzQM5RPA - retrogaming fun - Spillway CHIMPS no abilities v49

### Geared

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** The land is a big gear and a small gear that turn after every round and carry their towers, so a finite-range tower is carried away from the track. Only global towers keep working: spam snipers on Strong early, then heli, with alchemist/village where they fit.

**Lanes:** single.

**What the guides found** (detail from the sources):

- Track: enters at the left edge at fy~0.58, climbs over the top of the big gear (highest point ~(0.43,0.31)), comes down the right side and exits at the right edge at fy~0.58. Single lane, ~13.9 RBS. No water, no removables, no line-of-sight blockers.
- Big gear rotates 45 deg clockwise after every round (cycle 8 rounds); small centre gear 108 deg (cycle 10). Clockwise on screen moves the left rim UP along the track arc, so a tower placed on the left rim near the entrance stays near the track for ~2-3 rounds ...
- The ring between the two gears (approx fx 0.29-0.56, fy 0.37-0.80 minus the small gear) is unplaceable.
- The big gear's placeable circle extends over the teeth (towers can sit 'in the air' between teeth).

**Towers that work:**

- sniper 0-0-0 spam on Strong early; 0-2-4 / 0-2-5, 0-5-2, 2-0-4 ...: Global range and no line-of-sight blockers: unaffected by rotation
- heli 2-0-0 asap, 3-0-2 / 3-2-0 -> 4-0-2 / 4-2-0 -> 5-0-2 Apache ...: Global with Pursuit; heli path tier 5 works as a win condition (wiki).
- alchemist 3-2-0 -> 4-2-0 -> 5-2-0 (Permanent Brew) or 4-0-1: Buffs the main sniper/heli; place adjacent - rotation keeps it adjacent.
- village 2-0-2 (Jungle Drums + discount) / 2-2-0: Discount and attack speed for the sniper cluster; camo via 0-2-0.
- druid 1-3-0 (-> 1-5-0 Spirit of the Forest late): Used in both G-Horizon and OneEyedDeacon builds for R21-40 crowd damage.
- ace any: Flies a global pattern - unaffected by rotation (fandom tips).

**Avoid:** tack (finite range: carried away from the track by the gear); ice (finite range: carried away from the track by the gear); glue (finite range: carried away from the track by the gear); bomb (finite range: carried away from the track by the gear); boomerang (finite range: carried away from the track by the gear); ninja (finite range: carried away from the track by the gear); spike (finite range: carried away from the track by the gear).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - (inferred, legal in the CURRENT bot model) snipers + Heli only - BlueCliff's Hard build without darts/alch/village (hero: none; inferred, derived from the v27-30 BlueCliff guide; Hard + MK + Double Cash makes it easier). Source: https://www.youtube.com/watch?v=EvHgMjxOhtM

  R1: Sniper(a) on Strong; add Snipers (b)(c)(d) on Strong as cash allows (target 4 base snipers by ~R10; one of them on First); R10-15: Sniper(a) 1-0-0 (lead) and Sniper(b) 0-1-0 (camo) early enough for R28 leads / R24 camo; ~R15: Heli Pilot (pad on the gear); 2-0-0 (Pursuit) as soon as possible - from here the bot can leave it on Pursuit; R26-32: Heli 2-1-0 -> 2-2-0 (IFR camo) -> 3-2-0; R39-61: Sniper(a) 1-0-2 -> 3-0-2 -> 4-0-2 (Maim MOAB, Strong); Sniper(b) 1-2-0 -> 1-3-0 -> 2-3-0 -> 2-4-0 -> 2-5-0 (Elite Sniper, First); R62-74: Heli 4-2-0; spare cash: more 0-2-4 snipers on First; Win R80 (Hard)

*chimps, used for the 'chimps' hints* - Sniper spam + Psi + Druid + Village + Alch (no abilities, no micro) (hero: Psi; youtube description (chapter list), v53). Source: https://www.youtube.com/watch?v=6QOiPh3CY1w

  R6: Dart (front, near the entrance) + Sniper1 on Strong; auto-start ON; R7: auto-start OFF (G-Horizon toggles it; bot can ignore); R8: Sniper2 on Strong; R10: Sniper3 on Strong; R12: Sniper4 on Strong; R13: Sniper5 on Strong (mid-round); R15: Sniper6 on Strong; R19: Psi, targeting Strong; R21: Druid 0-0-0; Sniper1 targeting First; R22: Druid 0-1-0; R27: Druid 0-3-0; R28: Druid 1-3-0; R30: Sniper1 0-2-0; R32: Sniper1 0-2-2; R36: Sniper1 0-2-3; R40: Sniper1 0-2-4; R44: Village 2-0-2 (covering the snipers); R46: Alchemist 3-2-0 (next to Sniper1); R53: Sniper1 0-2-5 (Elite Defender); R55: Alchemist 4-2-0; R80: Alchemist 5-2-0 (Permanent Brew); R81: Sniper2 0-3-2 on First; R82: Sniper2 0-4-2; R85: Sniper2 0-5-2 (Elite Sniper) on First; R90-96: Snipers 3-6 to 0-2-4 on First; R97: Sniper7 2-0-4 on Strong

Other builds found:

- hard: No hero: darts + snipers -> Heli 4-2-0 + Alch 4-0-1 + Elite Sniper 2-5-0 + Sniper 4-0-2 (no MK) (hero: none) - https://www.youtube.com/watch?v=EvHgMjxOhtM
- chimps: Geraldo + snipers + druid + villages (Axis of Havoc, no abilities) (hero: Geraldo) - https://www.youtube.com/watch?v=x66sSCIgVe0

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Overclock 0-4-0 + Perma Charge 0-5-2 + Geraldo (v31); heroless Overclock 1-4-0 + Elite Defender 0-2-5 + Spirit of the Forest 1-5-0 + Dark Champion 2-0-4 (v44.1). LCC 59,590 (v31) / 69,940 (v38.3). Indexed CHIMPS starts: 'shitton of snipers into R19 heli', '2 sniper, 2 dart, 1 boomer into R18 heli', 'R12 dartling into R19 heli', 'Adora early'.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 6 spots - sniper, heli; 'chimps' (impoppable, chimps): 7 spots - sniper; hero psi.

**Sources:**

- https://www.bloonswiki.com/Geared - Geared - Blooncyclopedia
- https://bloons.fandom.com/wiki/Geared - Geared - Bloons Wiki (fandom)
- https://bloons.fandom.com/wiki/Geared/Strategies - Geared/Strategies (fandom)
- https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies - C.H.I.M.P.S./Strategies (fandom)
- https://www.bloonswiki.com/Strategy:Sniper_Monkey_(BTD6 - Strategy:Sniper Monkey (bloonswiki)
- https://www.youtube.com/watch?v=6QOiPh3CY1w - G-Horizon - Geared CHIMPS easy guide (no abilities/micro) Update 53
- https://www.youtube.com/watch?v=x66sSCIgVe0 - OneEyedDeacon - UPDATED Geared CHIMPS Axis of Havoc (v54.1)

### Mesa

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Two simultaneous lanes separated by sight-blocking rock walls; only the strip just top-right of the centre reaches both. Snipers on the top-left plateau, the core on that strip, the rock island covers the bottom lane.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- Top lane (path 0): (0.05,0.91) -> (0.09,0.65) -> (0.21,0.67) -> (0.30,0.48) -> (0.37,0.38) -> (0.46,0.38) -> (0.55,0.17) -> (0.65,0.17) -> (0.79,0.06) -> exit (0.85,0.05). Lower elevation; most towers in the valley cannot see the bottom lane.
- Bottom lane (path 1): (0.31,0.98) -> (0.48,0.89) -> (0.54,0.67) -> (0.52,0.51) -> (0.56,0.42) -> (0.66,0.55) -> (0.74,0.58) -> exit (0.85,0.47). Shorter, so it leaks first; MOABs of R40/60/80/100 come on the top lane (fandom).
- Top-left plateau (fx 0.05-0.50, fy 0.05-0.45) is high ground and large: snipers, heli pads, villages, farms fit there and see the whole map.
- Small high-ground rock island inside the bottom lane's loop at ~(0.59,0.53): best bottom-lane spot (dart covers 22% of the bottom lane there; spike factory 15%).

**Towers that work:**

- sniper 0-0-0 early; 2-0-4/2-0-5 Elite Defender, 0-5-2 Elite ...: Global from the top-left plateau; Axis of Havoc CHIMPS with no abilities.
- boomerang 3-0-2 -> 4-0-2 -> 5-0-2 Glaive Lord: Main short-range carry in the dual-lane strip (OED); also 2-0-4 x3 in the old meta.
- dart 0-0-0 x3 (CHIMPS R6): One per lane start + one in the dual-lane strip solo the first rounds.
- spike 0-0-5 Perma-Spike / 0-2-3 / 1-4-0: Tanks leaks on both lanes; Perma-Spike reaches both exits (Smart targeting, focus the shorter bottom lane).
- village 0-0-2 -> 2-0-2 -> 3-0-2 -> 4-0-2: Primary mentoring for boomerang/glue in the strip; discount.
- alchemist 3-0-0 -> 4-2-0: Buffs the main carry.

**Avoid:** sub (no water); buccaneer (no water).

**Removable obstacles and map switches:**

- Rock growth 'LeftRock' (Hoodoo) ($500): optional, mid game when you need more dual-lane space. Becomes line-of-sight-free high ground between the lanes (wiki: rock growths are good tower spots). Not used in the guides found.
- Rock growth 'RightRock' ($500): optional; best of the three for exit defence. High ground beside the bottom lane's last third (40-range from (0.738,0.411) covers bottom-lane 0.69-0.80) and close to the top lane's exit.
- Rock growth 'LonerRock' ($500): rarely. Space for big towers (farms/villages/supers); far from both lanes.

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Quincy + Ninja 4-0-2 + 3x Bomb 0-2-4 + Alch 4-0-1 + Village 4-2-0 + Wizard 5-0-2 Archmage (no MK) (hero: Quincy; youtube description, ~v30-33 (2022-23), no MK). Source: https://www.youtube.com/watch?v=5CIkTZyOHoY

  R3: Quincy; R4: Dart; R6 (after round): (sell Dart - optional) Ninja; R8: Ninja 0-0-1; R11: 2-0-1; R13: 2-0-2; R17: 3-0-2; R21 (after round): Bomb1 0-0-2 on Strong; R24: 0-0-3; R27: 0-2-3; R33: Ninja 4-0-2; R35: Bomb2 0-2-2; R36: Bomb2 0-2-3; R39: Bomb2 0-2-4; Bomb1 targeting First; Alch 2-0-0 nearest to Quincy; R40: Quincy level-3 ability when the MOAB is near (blind press ok); R43: Alch 4-0-1; R45: Bomb1 0-2-4; R48: Village 2-2-0; R59: (sell Bomb1 - optional) Wizard 4-0-1; R60: Quincy level-3 (optional); R62: Bomb2 and Bomb3 0-2-4 (all bombs must have the village buff); Village 4-2-0; R76/R78: Quincy level-10 (optional); R79: Wizard 5-0-2 (Archmage); R80: abilities (optional) - win

*chimps, used for the 'chimps' hints* - Axis of Havoc snipers + Etienne + Glaive Lord, no abilities, no micro (hero: Etienne; youtube description, v54.1). Source: https://www.youtube.com/watch?v=CVxEdZq3I2c

  R6: Dart1 0-0-0 on Strong at the left (top lane start) + Dart2 0-0-0 'splitting tracks' (dual-lane strip) + Dart3 0-0-0 on Strong hugging the cliff at the bottom (bottom ...; R8: Sniper1 0-0-0 mid-round, as high as possible on the plateau (leave on First); R10: Sniper2 0-0-0 on Strong mid-round, left of Sniper1; R14: Etienne in front of Dart2; R15: Boomerang1 0-0-0 behind Dart2; R16: 1-0-0; R17: 2-0-0; R19: 3-0-0; R20: 3-0-1; R21: 3-0-2; R22: Sniper2 1-0-0; R24: 1-0-1; R26: 1-0-2; R27: Sniper1 0-1-0; R28: 0-2-0; R29: 0-2-1; R30: 0-2-2; R35: Boomerang1 4-0-2; R36: Sniper2 2-0-2; R39: 2-0-3; R42: 2-0-4 on First; R44: Village1 0-0-2; R46: Sniper1 0-3-2; R47: Alch1 3-0-0; R48: Village1 2-0-2; R49: 3-0-2; R51: Sniper1 0-4-2; R60: Sniper2 2-0-5 (Elite Defender); R63: Alch1 4-2-0; R71: Sniper1 0-5-2 (Elite Sniper) on First; R83: Boomerang1 5-0-2 (Glaive Lord); R84: Sniper3 3-2-0 on Strong; R85: 4-2-0; R86: Village1 4-0-2; R87: Glue1 0-2-3 on Strong in front of Etienne; R89: 0-2-4; R97: Sniper3 5-2-0 (Cripple MOAB)

Other builds found:

- hard: (inferred for Hard) same OED build through R80, Monkey Knowledge on (hero: Etienne) - https://www.youtube.com/watch?v=CVxEdZq3I2c
- chimps: Etienne + Ninja 4-0-2 + Alch + Sun Avatar + Perma-charge/Sabo (uses abilities) (hero: Etienne) - https://www.youtube.com/watch?v=QTjQn-C0640
- chimps: Old meta (v26.2): Quincy, 5 darts, 4-0-1 ninja, 0-2-3 spikes, 4-2-0 alch -> Ultra-Juggernaut, Perma-spike, MOAB ... (hero: Quincy) - https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Monarch of Storms (5-1-0) + Dark Knight (2-0-3) + Geraldo (v31.2); heroless Monarch of Storms 5-0-2 + Crossbow Master 0-2-5 + Elite Defender 0-2-5 + Archmage 5-0-2 (v49.3). LCC 71,025 (v44.1). Removal cost listed $1,500 total (3 x $500).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 7 spots - ninja, alchemist, wizard, bomb, village; hero quincy; 'chimps' (impoppable, chimps): 10 spots - dart, sniper, boomerang, alchemist, village; hero etienne.

**Sources:**

- https://www.bloonswiki.com/Mesa - Mesa - Blooncyclopedia
- https://bloons.fandom.com/wiki/Mesa - Mesa - Bloons Wiki (fandom)
- https://bloons.fandom.com/wiki/Mesa/Strategies - Mesa/Strategies (fandom)
- https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies - C.H.I.M.P.S./Strategies (fandom)
- https://www.youtube.com/watch?v=CVxEdZq3I2c - OneEyedDeacon - Mesa CHIMPS no abilities/no micro, Axis of Havoc (v54.1)
- https://www.youtube.com/watch?v=cz7PaKRVwyM - OneEyedDeacon - Mesa CHIMPS is EASY with Axis of Havoc (v50.0)
- https://www.youtube.com/watch?v=QTjQn-C0640 - Baumfall - Mesa CHIMPS with Etienne

### X Factor

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Bloons spawn from two adjacent corners and cross diagonally, the spawn side turning 90 degrees each round; the middle is a tunnel where they are invulnerable (36%). One corner sees one diagonal only: put short-range towers in two adjacent corners and use snipers.

**Lanes:** rotating.

**What the guides found** (detail from the sources):

- 8 path variants (2 per corner); 4 active per round (2 entrances x 2 variants); spawn side rotates clockwise each round (top, right, bottom, left).
- Path pairs: TL<->BR diagonal (paths 0,4,6,7,8 in bot geometry), TR<->BL diagonal (paths 1,2,3,5). Path lengths 14.5-21.1 RBS depending on entrance (BTD6 Index: TR 14.5, BL 15.8, TL 21.0, BR 20.9).
- Central tunnels: bloons inside are invulnerable (incl. blimps and undead bloons); ~36% of the track hidden. The bot geometry flags those parts as invulnerable (purple on the map).
- Corner loop clusters (attackable): TL fx 0.05-0.30 fy 0.05-0.33; TR fx 0.55-0.75 fy 0.05-0.35; BL fx 0.08-0.32 fy 0.62-0.95; BR fx 0.52-0.75 fy 0.62-0.95. Best single spots (bot model): TR (0.59,0.164), TL (0.259,0.181), BL (0.158,0.768), BR (0.703,0.785).

**Towers that work:**

- sniper 0-0-0 spam on Strong; 0-2-4 -> 0-2-5, 0-5-2, 2-0-4, 4-0-2 ...: Hit any part of the track, catch the frequent sudden leaks; Maim MOAB stalls blimps for global towers.
- desperado 0-0-0 x2 at R6: G-Horizon opener (one per right-side corner).
- druid 1-3-0: R21-40 crowd damage in both CHIMPS guides.
- alchemist 3-2-0 -> 4-2-0 -> 5-2-0: Buffs the main sniper; Permanent Brew.
- village 2-0-2 / 2-2-0 -> 4-2-0: Discount/camo for the sniper cluster.
- spike 0-5-0 Carpet of Spikes / 2-4-0: Spikes land everywhere bloons walk; trivialises DDTs and the R100 BAD (wiki).

**Avoid:** farm (no room advantage; never in CHIMPS).

**Removable obstacles and map switches:**

- Military stack (centre) ($2000): optional mid/late game, only if a tower is wanted in the exact centre (e.g. Crossbow Master / Dartling). Gives a central platform (fits everything except Banana Farm) whose range reaches the inner edges of all four corner clusters

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Quincy + Ninja 4-0-2 + Alch 4-0-1 + Village 4-2-0 + Bombs 0-2-4 + Snipers 4-0-2 / 0-2-5 (no MK) (hero: Quincy; youtube description, ~v27-30 (2021-22)). Source: https://www.youtube.com/watch?v=htKjB3Ct3lI

  R3: Dart, Dart (both on Strong); Boomerang; R6: (sell boomerang - optional) Quincy; R9: Ninja; R10: 0-0-1; R12: 1-0-1; R13: 2-0-1; R14: 2-0-2; R18: 3-0-2; R21: Sniper(a) 0-0-1 Strong; R22: 0-0-2; R25: 1-0-2; R32: Ninja 4-0-2; R34: (sell darts - optional) Alch(a) 2-0-0; R35: 3-0-0; R37: Village 1-0-0; R38: 2-0-0; R39: Bomb(a) 0-1-3; R40: Quincy ability; R41: Bomb(a) 0-2-3; R43: Alch(a) 4-0-1; R45: Bomb(a) 0-2-4; R46: Village 3-0-0; R48: 4-0-0; Bomb(b) 0-2-3; R49: Bomb(b) 0-2-4; R50: Village 4-2-0; Sniper(a) 2-0-2; R53: 3-0-2; R55: 4-0-2; R59: Sniper(b) 0-2-3; R62: 0-2-4; R70: 0-2-5; R63: Quincy level-10 ability if leaking; R75: Bomb(c) 0-2-4; R77: Bomb(d) 0-2-4; R78: Alch(b) 4-0-1 - win R80

*chimps, used for the 'chimps' hints* - Desperado x2 -> Sniper spam -> Psi -> Druid -> Village + Alch -> Elite Defender / Elite Sniper / Perma Brew (no abilities, no micro) (hero: Psi; youtube description (chapter list), v53.2). Source: https://www.youtube.com/watch?v=cbqYU4k5f0o

  R6: Desperado x2 (one per right-side corner - R6 spawns from the two right corners); R8: Sniper1 on Strong (mid-round); R10: Sniper2 on Strong (mid-round); R12: Sniper3 on Strong; R14: Sniper4 on Strong; R15: Sniper5 on Strong; R19: Psi on Strong; R21: Druid 0-0-0; R27: Druid 0-3-0; R28: Druid 1-3-0; R32: Sniper1 0-2-2 on First; R36: Sniper1 0-2-3; R40: Sniper1 0-2-4; R44: Village 2-0-2; R46: Alchemist 3-2-0; R53: Sniper1 0-2-5; R55: Alchemist 4-2-0; R80: Alchemist 5-2-0; R81: Sniper2 0-3-2 on First; R83: Sniper2 0-4-2; R85: Sniper2 0-5-2 on First; R88-96: Snipers 3-6 to 0-2-4 on First; R97: Sniper7 2-0-4 on Strong

Other builds found:

- chimps: Sauda + darts + snipers (Axis of Havoc) + druid + village + PoD + glue, no abilities, no micro (hero: Sauda) - https://www.youtube.com/watch?v=IRdVGDWzArY
- chimps: Old late-game (fandom table): 5-0-2 Grandmaster + Shinobi + Sabo + 2-4-0 Spike Storm + 0-1-3 MOAB Glue (hero: -) - https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Perma Charge 0-5-2 + Inferno Ring 5-0-2 + Geraldo (v31); heroless Sprockets 3-0-0 + Wizard Lord Phoenix 0-5-2 + Elite Defender 0-2-5 + Permanent Brew 5-0-0 (v49.3). LCC 77,310 (v31.2). May-2021 chart: worst CHIMPS win rate of any map except Ravine.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 9 spots - dart, ninja, alchemist, village, bomb, sniper; hero quincy; 'chimps' (impoppable, chimps): 13 spots - desperado, sniper, druid, village, alchemist; hero psi.

**Sources:**

- https://www.bloonswiki.com/X_Factor - X Factor - Blooncyclopedia
- https://bloons.fandom.com/wiki/X_Factor - X Factor - Bloons Wiki (fandom)
- https://bloons.fandom.com/wiki/X_Factor/Strategies - X Factor/Strategies (fandom)
- https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies - C.H.I.M.P.S./Strategies (fandom)
- https://www.youtube.com/watch?v=cbqYU4k5f0o - G-Horizon - X Factor CHIMPS easy guide (no abilities/micro) Update 53.2
- https://www.youtube.com/watch?v=IRdVGDWzArY - OneEyedDeacon - X Factor CHIMPS no abilities/no micro, Axis of Havoc (v54.1)
- https://www.youtube.com/watch?v=htKjB3Ct3lI - BlueCliff - X Factor Hard no MK ft. Quincy

### Sunken Columns

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Two lanes cross twice; the big hexagonal columns in the middle are deep depressions whose view the track itself blocks, so only fliers, farms and supports belong there. Guides camp the top column and use the outer land.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- Lane A (path 0): enters top at fx 0.31 -> down to (0.31,0.13) -> top crossing (0.43,0.24) -> (0.59,0.09) -> (0.80,0.28) -> down the right side to (0.80,0.69) -> (0.58,0.88) -> bottom crossing (0.43,0.75) -> (0.31,0.85) -> exits down at fx 0.31.
- Lane B (path 2): mirror image - enters top at fx 0.55 -> top crossing -> (0.27,0.09) -> (0.07,0.27) -> down the left side -> (0.27,0.89) -> bottom crossing -> (0.56,0.86) -> exits down at fx 0.55. Both ~18.8 RBS.
- Raised placeable land (per game areas; NOT legal in the bot model): top column fx 0.33-0.53, fy 0.00-0.15 (spawn camp); bottom column fx 0.33-0.53, fy ~0.80-1.00; bottom-left corner fx 0.08-0.25, fy 0.75-1.00
- Middle depressions (legal in bot model): left column fx 0.12-0.42, right column fx 0.44-0.74, fy 0.26-0.82, each with a pond. Line of sight from here is blocked by the track walls except 4 narrow river gaps

**Towers that work:**

- sniper Axis of Havoc: 2-0-5, 0-5-2, 5-2-0: Global from the raised spots (NOT from the middle depressions).
- dart 0-0-0 x4 (CHIMPS R6-8): On the top column they cover both entrances and the top crossing.
- druid 1-3-0 -> 1-4-0 -> 1-5-0 Spirit of the Forest: SotF vines cover the whole track; OED carries R13-R100 with it.
- ninja 3-0-2 -> 4-0-2: Hard Quincy build early-mid carry (top column).
- glue 0-2-3/0-2-4, 2-0-4; Super Glue 0-0-5: Short crossings - stalls keep bloons in the crossing zone (wiki: Super Glue vital, pairs with Sauda).
- boomerang 5-0-x Glaive Lord: Near a crossing: rotating glaives + ricochets between the two lanes.

**Avoid:** sub (the ponds are inside the sight-blocked depressions); buccaneer (same as subs).

**Removable obstacles and map switches:**

- Left pond ($1000): rarely - only for more space for farms/villages/fliers. Turns water into land; it stays line-of-sight blocked.
- Right pond ($1000): rarely. Same.

**Builds (in buy order):**

*chimps, used for the 'hard' hints* - Old (v32.2) table: Etienne/Psi, Dart+Sniper start, druids, 4-0-0 Ace for R40, 0-2-4 wizards, 0-2-4 spactory -> Sky Shredder, Permaspike, 2-0-4 glue, Super Brittle (hero: Etienne; wiki, v32.2). Source: https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies

  Start: Dart, Sniper; 2nd dart, Druid, Etienne; 2nd Druid, 1st Druid 1-3-0, Sniper 1-2-0; R40: 4-0-0 Ace; Mid: 2x 0-2-4 Wizards near the entrance; 0-2-4 Spike Factory (alch'd); Alch for Ace; 2-0-0 Village; Late: Sky Shredder 5-0-1; Permaspike; 2-0-4 Glue; Super Brittle 5-2-0; Etienne/Psi abilities R78/80/98

Other builds found:

- hard: Quincy + Ninja 4-0-2 + Alch 4-0-1 + 3 snipers (2-5-0 Elite Sniper, 0-2-5, 5-0-2) + Village 2-2-0 (no MK) (hero: Quincy) - https://www.youtube.com/watch?v=_pMozxcSlgQ
- chimps: Darts on the top column + Sauda + Druid -> Spirit of the Forest + Axis of Havoc snipers (no abilities, no micro) (hero: Sauda) - https://www.youtube.com/watch?v=_GHS1QFoyUY
- chimps: Sauda + Snipers + Spike Factory -> Tack Zone + Perma-Spike -> Carrier Flagship (no abilities) (hero: Sauda) - https://www.youtube.com/watch?v=VQebEc-GpNg

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Perma Charge 0-5-2 + Geraldo (v31); heroless Perma Charge 0-5-2 + M.A.D 2-5-0 + Carrier Flagship 5-0-2 (v44.1). LCC 48,065 (v31.2). Removal cost listed $2,000 total (2 x $1,000).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 1 spots - ace; hero etienne.
Model gap: The raised outer land (top column, bottom column, both bottom corners) is unplaceable in the model; every guide builds there. Only the sunken middle columns are legal, and the track blocks their view.

**Sources:**

- https://www.bloonswiki.com/Sunken_Columns - Sunken Columns - Blooncyclopedia
- https://bloons.fandom.com/wiki/Sunken_Columns - Sunken Columns - Bloons Wiki (fandom)
- https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies - C.H.I.M.P.S./Strategies (fandom)
- https://www.youtube.com/watch?v=_GHS1QFoyUY - OneEyedDeacon - Sunken Columns CHIMPS no abilities/no micro (v54.2)
- https://www.youtube.com/watch?v=_pMozxcSlgQ - BlueCliff - Sunken Columns Hard no MK ft. Quincy
- https://www.youtube.com/watch?v=VQebEc-GpNg - Fynn BTD6 - Sunken Columns CHIMPS no abilities v31
- https://www.youtube.com/watch?v=yGIHp0QdnM0 - Spiffy BTD - Sunken Columns CHIMPS heroless no abilities (Axis of Havoc) v30

### Midnight Mansion

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Both lanes walk the same top floor, then go down opposite staircases to a central exit. Magic fire walls block sight and swap every 2 rounds; heli and farms fit nowhere, villages/supers/aces only on the two $250 drawers. A compact crowd-damage stack in the top-left corner (tack, glue, ninja, alchemist, ice) works.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- Rounds 1+4n and 2+4n (1,2,5,6,...): fires on the top-middle line (vertical, x~0.40-0.44 across the top floor) and bottom-middle line (under the exit) - block line of sight between the left and right halves of the top floor.
- Rounds 3+4n and 4n (3,4,7,8,...): fires on the left and right staircases (horizontal lines, y~0.53-0.60 on each stair) - block sight between the top and bottom halves of each staircase.
- Towers on the two drawers ignore the fires (fandom: flames block line of sight 'for all towers except those placed on the upstairs drawers').
- Both lanes share the whole top floor, so a tower next to the top floor hits both lanes; Sauda's Sword Charge does double damage there (bloonswiki).

**Towers that work:**

- sauda hero: Beginner-friendly, best in the top-left or top-right corner, trivialises the early game, Sword Charge double-hits the overlapping ...
- tack 2-0-4 -> 2-0-5: Overdrive / Tack Zone benefit from the bends; Overdrive best near a top corner as the main chokehold, saves cash for a win ...
- glue 0-2-5 (or 4-0-2 / 5-2-0): Super Glue stalls clumps on the short coverable top floor and synergises with Sauda (wiki)
- boomerang 5-0-2: Glaive Lord: orbiting glaives clean the bends, ricochets bounce between the two entrances.
- tack 5-0-2: Inferno Ring cleans up in the bends; meteors hurt blimps/DDTs with pierce buffs (Overclock, Stimulant, Primary Training ...
- ice 2-0-4 -> 2-0-5 and 5-x-x: NamelessBandicoot CHIMPS: 204 ice -> Icicle Impale and a Super Brittle alongside Tack Zone.

**Avoid:** heli (cannot be placed anywhere); farm (cannot be placed anywhere); super (only fits on a drawer); ace (only fits on a drawer); spike (only fits on a drawer); sub (no water); buccaneer (no water).

**Removable obstacles and map switches:**

- Drawer (left) - clutter on the top-left desk/drawer ($250): as soon as a Village or drawer Sniper is planned (CHIMPS NamelessBandicoot uses a village; Hard: ~R15-25). Only place for a Village/Super/Ace/Spike Factory; towers here ignore fire and wall line of sight. BTD6 Index lists $500 total for both.
- Drawer (right) ($250): when a second large tower or 2-3 drawer snipers are wanted. Same as the left drawer; Steam players put Super/Ace or 'a couple of Snipers' there.

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Top-left corner AoE stack: Sauda + Overdrive + Glue + Ninja + Brew (optional drawer village/snipers) (hero: Sauda; inferred, v56 wiki recommendations; inferred plan - no written Hard guide found (Hard ...). Source: https://www.bloonswiki.com/Midnight_Mansion

  R1: Sauda in the top-left corner (the bot has Double Cash on Hard; Sauda carries alone to ~R20+); R5-8: Tack Shooter on the top-left shelf above the top floor; 0-0-2 then 1-0-2; R12-15: Ninja on the shelf (camo safety for R24 camo greens / R30s) -> 2-0-1; R18-22: Glue on the shelf 0-2-3 (strong) ; Tack -> 2-0-3; R25-30: Ninja -> 3-0-1 -> 4-0-1 -> 4-0-2; Alchemist on the shelf 3-0-0 -> 3-2-0; R32-38: Tack -> 2-0-4 Overdrive before R40 (first MOAB); Alchemist -> 4-2-0; R40-55: Ice 2-0-4 below Sauda; Glue -> 0-2-4; OPTIONAL: buy the top-left drawer ($250) and put a 2-2-0 Village on it; buy the top-right drawer and add a 0-2-4 Sniper; R55-75: Tack -> 2-0-5 Tack Zone (wiki: strong vs most late rounds; weak vs ceramics -> keep glue/ninja); second drawer sniper 4-0-2 for MOAB/BFB/ZOMG; If the left lane leaks (it is only covered near its start from the top-left corner), mirror the build into the top-right corner (x~0.644 strip and the shelf at x ...

*chimps, used for the 'chimps' hints* - Sauda + Tack Zone + Super Brittle + Icicle Impale (NamelessBandicoot) (hero: Sauda; youtube description, video ~11 months old (v50-v52 era); description lists the order but no rounds ...). Source: https://www.youtube.com/watch?v=KVlfBvOU0F0

  R6+: Sauda + early towers (exact early order not in the description); Upgrade the Village and Alchemist for the Overdrive (tack 0-0-4) first (village needs a drawer bought); R37: Sauda ability for the camo whites (bot presses abilities on cooldown anyway); Then a 2-0-4 Ice 'for later'; Then Tack Zone, then Super Brittle (5-x-x ice), then Icicle Impale (2-0-5 ice) in succession 'without having to worry about leaks'; By R92: 4-0-2 Glue (alternative: Spirit of the Forest druid instead of the glue, inside village range; then tier-5 order tack - druid - impale - brittle); R92-100: turn off auto-start and buy upgrades before each round; Sauda level-10 ability after the BAD pops on R100

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Monarch of Storms 5-0-2 + Geraldo (v38, Extreminator418); heroless 3 towers: Elite Defender 0-2-5 + Archmage 5-0-2 + Monarch of Storms 5-0-2 (v49.3). LCC $55,050 (v39.1) / $60,750 (v33.3, bolaris). CHIMPS start listed: 'double beast handler r6' (youtube zLirtefoQ7k).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 4 spots - glue, alchemist, ice; hero sauda; 'chimps' (impoppable, chimps): 3 spots - alchemist, glue; hero sauda.
Removables recorded: RemovableLeft ($250, optional, ~R20).
Model gap: The shared top floor has no track cells in the model, so spots there read ~0 reach.

**Sources:**

- https://www.bloonswiki.com/Midnight_Mansion - Midnight Mansion - Blooncyclopedia
- https://bloons.fandom.com/wiki/Midnight_Mansion - Midnight Mansion - Bloons Wiki (fandom)
- https://steamcommunity.com/app/960090/discussions/0/3720565944184253127/ - Steam: How To Midnight Mansion Military Only?
- https://steamcommunity.com/app/960090/discussions/0/3485249057166005241/ - Steam: Midnight Mansion (large towers)
- https://steamcommunity.com/app/960090/discussions/0/4200239074420214057/ - Steam: Midnight Madness CHIMPS
- https://www.youtube.com/watch?v=KVlfBvOU0F0 - NamelessBandicoot - CHIMPS Midnight Mansion w/ Tack Zone, Super Brittle & Icicle Impale
- https://www.youtube.com/watch?v=TC_QN-SJ2VI - Doreo - Midnight Mansion CHIMPS (v43.3)

### Erosion

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** One of six lanes is active at a time and the active lane moves across the map; after rounds 17, 35, 53, 71 and 89 the ice melts and towers on it are sold. Only the top-right glacier is permanent: snipers, alchemist and village there, global damage, Perma-Spike late.

**Lanes:** alternating.

**What the guides found** (detail from the sources):

- Lane schedule (BTD6 Index lengths): R1-17 lane 1 bottom-left (7.2), R18-35 (9.1), R36-53 (11.9), R54-71 (11.1), R72-89 (7.9), R90+ top-right (5.2). Boss bloons always use lane 3.
- Erosion events fire after rounds 18/36/54/72/90 in the geometry (AfterRoundTrigger) - i.e. at the end of R17/35/53/71/89 per the wikis; towers on the melted ice are sold (Hard refund) and the polar bear jumps (decoration only).
- Amphibious/water-tolerant towers survive the melt and become water towers: Pat Fusty, Ice Monkey, Mermonkey (gets the water range bonus), Sun Temple/True Sun God; towers in range of Arctic Wind ice platforms are also saved.
- Glacier: no Heli (artificially blocked), max 3 villages in-game (bot model: 1), one Banana Farm.

**Towers that work:**

- sniper 0-2-4 -> 0-2-5, 0-5-2, 5-2-0, 4-0-2: Global range - unaffected by lane changes; all Erosion CHIMPS text guides are sniper cores on the glacier (Elite Defender, Elite ...
- sub 1-0-2 / 2-0-2: Permanent bottom-left water; Airburst + Advanced Intel carries the early game (wiki: Advanced Intel adapts to lane changes).
- spike 2-0-5: Perma-Spike 'works very well on this map, due to the short track length'; place at the bottom of the glacier strip.
- spike 0-4-2 / 0-5-2: Spike Storm / Carpet of Spikes on the tiny R90+ lane wipes DDTs and the BAD
- alchemist 4-2-0: Berserker Brew on the snipers / Perma-Spike (all text guides).
- village 2-0-2 / 2-2-0: Only one fits on the glacier in the bot model; buffs the sniper core.

**Avoid:** farm (only one fits on the glacier); tack (wasted when its lane moves or its ice melts).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - No MK, no hero: snipers + Heli + Alchemist (BlueCliff) (hero: none (bot may add Psi on the glacier); youtube description, ~3 years old (v37-v38 era)). Source: https://www.youtube.com/watch?v=jlkIyVLVjmI

  Turn off auto-start; R3: Dart; Sub; R6: Sub 0-0-1; R7: Sub 1-0-1; R9: Sniper (bottom); R13: Sub 1-0-2; R16: Sniper (bottom) 1-0-1, set to Strong; R18: Sniper (bottom) 1-0-2; R23: Heli; R27: Heli 1-0-0; R28: Heli 2-0-0; R30: Heli 2-2-0; R34: Heli 3-2-0; R35 (after the round): sell Sub, Alchemist 3-0-0 (bot: skip the sell); R36: Alchemist 3-0-1; R38: Sniper (bottom) 2-0-2; R39: Bomb 0-3-2 (sold after R40 in the source - optional); R41: Alchemist 4-0-1; R45: Sniper (top) 1-3-0; R49: Sniper (top) 2-4-0; Sniper (bottom) 3-0-2; R51/55/58/63/65/69/71/75: Sniper Supply Drop ability (bot fires on cooldown); R55: Sniper (bottom) 4-0-2; R59: Sniper (top) 2-5-0, set back to First; R62: Village 2-0-0; R71: Heli 4-2-0; R74: Village 4-2-0; R75: Glue 0-2-4; GG at R80

*chimps, used for the 'chimps' hints* - No abilities/micro: Psi + Elite Defender + Druid + Perma-Spike (G-Horizon) (hero: Psi; youtube description, v53 (Update 53)). Source: https://www.youtube.com/watch?v=No3NYnNZV1c

  R6: Dart + Sub at pixel [450,890] (1080p) - 'no RNG if you place on the listed rounds'; R9: Sub 1-0-1; R14: Sub 1-0-2; R19: Psi; R20: Sniper; R27: Druid 0-3-0 (mid-round); R28: Druid 1-3-0; R30: Sniper 0-2-0; R32: Sniper 0-2-2; R36: Sniper 0-2-3; R40: Psi to Strong; Sniper 0-2-4; R44: Village1 2-0-2; R47: Alchemist 3-2-0; R53: Sniper 0-2-5; R55: Alchemist 4-2-0; R76: Village2 0-0-2, Ice1, Engineer 4-0-2; R77: Engineer 5-0-2 (mid-round); R78: Village2 0-2-2 (mid-round); R79: Ice1 0-3-0; R88: Ice2 5-2-0, Village1 3-0-2, Ice1 0-3-1; R92: Glue 0-2-4 on Strong; R92-99: Spike 2-0-5 on Smart; NOTE: Engineer 5-0-2 (Ultraboost) and the 2nd village/ice need room the bot model's glacier does not have - treat as optional.

Other builds found:

- hard: Alternative Hard (full MK): Benjamin + snipers + Druid + banks (Unwilling) (hero: Benjamin) - https://www.youtube.com/watch?v=mK6fHcm_veg
- chimps: No abilities / no micro: Psi + Axis of Havoc snipers + Perma-Spike (OneEyedDeacon) (hero: Psi) - https://www.youtube.com/watch?v=KOT6M9kcoUE

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Carrier Flagship 5-2-0 + Geraldo (v44, Chocbox); cheapest 2TC: First Strike Capability 2-4-0 + Geraldo (v44); heroless: First Strike 0-4-1 + Elite Defender 0-2-5 + Cripple MOAB 5-2-0 + Permanent Brew 5-2-0 (v49.3). LCC $72,125 (v44.1, pi61) / $86,090 (v39.2). CHIMPS start: 'sub ada' (youtube qA8VR_gu_W4).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 7 spots - sub, sniper, heli, alchemist, village, glue; hero psi; 'chimps' (impoppable, chimps, apopalypse): 7 spots - sub, sniper, village, alchemist, spike, glue; hero psi.

**Sources:**

- https://www.bloonswiki.com/Erosion - Erosion - Blooncyclopedia
- https://bloons.fandom.com/wiki/Erosion - Erosion - Bloons Wiki (fandom)
- https://www.youtube.com/watch?v=KOT6M9kcoUE - OneEyedDeacon - Erosion Chimps w/ NO ABILITIES and NO MICRO ft. Axis of Havoc (v50.0)
- https://www.youtube.com/watch?v=No3NYnNZV1c - G-Horizon - Erosion CHIMPS Easy Guide (No Abilities/Micro) Update 53
- https://www.youtube.com/watch?v=jlkIyVLVjmI - BlueCliff - Erosion Hard No MK no heroes
- https://www.youtube.com/watch?v=mK6fHcm_veg - Unwilling - Erosion Hard Mode Guide
- https://www.youtube.com/watch?v=G5AX8dvEoKE - OneEyedDeacon - Erosion Chimps Rosalia + Flying Fortress (v49.3)

### Sunset Gulch

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): hard won (magic_obyn_ninja_wizard).*

**Key insight.** From round 40 MOAB-class bloons take a straight rail lane whose exit is under the shop panel; a defence on the winding bloon path leaks the first MOAB. The right-hand loop pocket just past the bridge covers both lanes.

**Lanes (single).** winding bloon path; MOAB-only rail lane from round 40

**What the guides found** (detail from the sources):

- MOAB-only railway lane (geometry: MoabOnlySplitter + PathActiveAction after R40 or on the first 'Moabs' spawn); Bosses use the rail too.
- Bloon path and railway share the bridge segment (x~0.18-0.68, y~0.36), so towers near the bridge hit both.
- Railway exit is at x~0.96 - beyond the right edge of the playfield (shop panel), so blimps must die before x~0.85.
- Top rock (centre top, ~0.53,0.16) fits large towers like a Spike Factory; bottom rock (~0.37,0.70) fits extra-large towers like a Super Monkey (bloonswiki).

**Towers that work:**

- desperado 2-0-5 / 0-5-0: Desert Phantom (2-0-5) knocks back and hits hard along the straight MOAB rail
- spike 2-0-5: Perma-Spike at the lane intersection handles the short MOAB lane and the bloon lane
- glue 5-2-0: Bloon Solver clears super ceramics near the MOAB lane with decent bloon-lane coverage.
- sniper 0-2-5 / 0-5-2 / 5-2-0: Global range ignores the split; every text guide (Axis of Havoc, bloon.games CHIMPS/Hard alt modes) is sniper-based.
- alchemist 4-2-0 / 5-0-0: Berserker/Permanent Brew on the main sniper.
- druid 1-3-0 -> 2-4-0 / 5-0-2: Hard: Jungle's Bounty economy; CHIMPS: Superstorm by R83 (bloon.games).

**Avoid:** tack (misses the separate MOAB rail); sub (no water); buccaneer (no water).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Druid economy + Ninja + Spectre (bloon.games Standard Hard) (hero: Obyn Greenfoot; web guide, June 2025 (v48-v49)). Source: https://bloon.games/how-to-beat-standard-hard-on-sunset-gulch/

  Start: Druid; When affordable: Sniper Monkey; Obyn Greenfoot; Ninja -> 4-2-0 (path 1 first); Druid -> 1-3-0, later 2-4-0 (Jungle's Bounty ability = extra cash); Alchemist -> 4-2-0; Village -> 2-0-2 (camo + speed); Monkey Ace in village radius -> 0-2-4 Spectre; Second Alchemist -> 4-2-0 buffing the Spectre; Spend the rest freely; Rounds are not given by the source; the bot should have the druid + sniper + Obyn by ~R10, ninja 2-x-x by R24 (camo), something that hits the RAIL (sniper/ace) strong ...

*chimps, used for the 'chimps' hints* - No abilities / no micro: Sauda + Axis of Havoc + Permanent Brew (OneEyedDeacon) (hero: Sauda; youtube description, v53.1). Source: https://www.youtube.com/watch?v=uZcfkclocAs

  R6: Sauda in back, as top left as possible; R9: 0-0-0 sniper1 on Strong in back between two planks; R11: sniper1 1-0-0; R12: 0-0-0 sniper2 on Strong; R14: sniper2 0-0-1; R16: sniper2 0-0-2; R17: sniper2 0-1-2; R19: sniper2 0-2-2 on First; R28: sniper2 0-2-3; R36: sniper2 0-2-4; R39: village1 0-0-2 lined up with plank on right of track; R40: alch1 3-0-0 for sniper2; R42: alch1 4-0-0; R44: village1 2-0-2; R45: sniper3 0-2-0; R46: sniper3 0-3-2; R50: sniper3 0-4-2; R56: sniper3 0-5-2 on First; R57: sniper1 2-0-0; R58: sniper1 3-0-0; R59: sniper1 3-2-0 on First; R63: sniper1 4-2-0; R83: alch1 5-0-0 Permanent Brew (during round); R88: sniper1 0-2-5?? (text says '025 sniper1' - sniper1 is 4-2-0; likely sniper2 0-2-4 -> 0-2-5 Elite Defender); R89: sniper4 0-3-2; R92: sniper5 0-3-2 + sniper6 0-3-2; R99: sniper1 5-2-0 Cripple MOAB; Placement words are the author's; 'in back' is interpreted as north of the railway (top-left cliff).

Other builds found:

- chimps: Obyn + Elite Defender + Superstorm + Perma-Spike (bloon.games 'Easy Peasy') (hero: Obyn Greenfoot) - https://bloon.games/how-to-beat-chimps-on-sunset-gulch/
- half_cash: Sauda + boomerangs + darts + village (bloon.games) (hero: Sauda) - https://bloon.games/how-to-beat-half-cash-on-sunset-gulch/
- double_hp: Benjamin + Druid + 3 snipers (bloon.games) (hero: Benjamin) - https://bloon.games/how-to-beat-double-hp-moabs-on-sunset-gulch/
- magic_only: Obyn + Druids + Ninja + Dark Knight (bloon.games) (hero: Obyn Greenfoot) - https://bloon.games/how-to-beat-magic-monkeys-only-on-sunset-gulch/
- abr: Ninja + Alchemist + Benjamin + Sub?? + snipers (bloon.games) (hero: Benjamin) - https://bloon.games/how-to-beat-alternate-bloons-rounds-on-sunset-gulch/

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: MOAB Domination 0-2-5 + Geraldo (v49.2, Gijssie, 'A bridge too far'); heroless: Popseidon 2-5-0 + Golden Justice 2-5-0 (v52.0). LCC $64,120 (v52.2) / $80,435 (v49.3). Evidence: boomerang (MOAB Domination), desperado and buccaneer-free sniper/druid cores are strong.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 8 spots - village, druid, sniper, ninja, alchemist, ace; hero obyn; 'chimps' (impoppable, chimps): 9 spots - sniper, village, alchemist; hero sauda.

**Sources:**

- https://www.bloonswiki.com/Sunset_Gulch - Sunset Gulch - Blooncyclopedia
- https://bloons.fandom.com/wiki/Sunset_Gulch - Sunset Gulch - Bloons Wiki (fandom)
- https://www.youtube.com/watch?v=uZcfkclocAs - OneEyedDeacon - Sunset Gulch Chimps NO ABILITIES/NO MICRO ft. Axis of Havoc (v53.1)
- https://www.youtube.com/watch?v=y1PU-nNaKQE - OneEyedDeacon - CRUSH Sunset Gulch Chimps (v49.3)
- https://bloon.games/how-to-beat-standard-hard-on-sunset-gulch/ - bloon.games - Standard (Hard) on Sunset Gulch
- https://bloon.games/how-to-beat-chimps-on-sunset-gulch/ - bloon.games - CHIMPS on Sunset Gulch
- https://bloon.games/how-to-beat-half-cash-on-sunset-gulch/ - bloon.games - Half Cash on Sunset Gulch

### Mushroom Grotto

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Towers can only be placed on lit ground and only target bloons in lit zones; at the start only the centre is lit. Players buy the four $250 mushrooms and then the $400 centre one around rounds 25-30; no village fits before that.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- Lit targeting zones (geometry EnablePathTargetZoneAction): centre 45 at start; each small mushroom +30 around itself; after buying the centre: centre 70, corners 60.
- Placement is only allowed on lit ground; the small-mushroom circles become placeable once bought (bot model: village only fits after lighting).
- The centre mushroom ($400) can only be bought after all four small ones.
- Two lanes (18.6 / 18.8) from the left and right edges cross through the centre twice (inner and outer square loops) before exiting top-left and bottom-right.

**Towers that work:**

- spike 0-5-2 / 2-0-5: Carpet of Spikes: with no mushrooms lit every spike lands on the middle section
- mermonkey 0-0-0 early / 5-0-2: Opening towers in the lit ring in OneEyedDeacon, HyperF3 and bloon.games CHIMPS; Lord of the Abyss in G-Horizon.
- dart 0-3-0 / 4-0-2: Cheap early pops in the lit ring (all CHIMPS guides).
- sniper 2-0-5 / 0-5-2 / 5-2-0 / 0-2-5: Axis of Havoc and bloon.games Elite Defender cores; strong once the mushrooms are lit.
- boomerang 5-0-2 / 0-2-4: Glaive Lord in the centre (OneEyedDeacon); MOAB Press 0-2-4 x2 on Strong (G-Horizon); 2-0-4 Strong (HyperF3).
- tack 2-3-0: Blade shooters in the centre handle the early game (G-Horizon).

**Avoid:** ninja (v54 bug: ninjas could not attack in the dark (check in game)); heli (Pursuit needs a lit target; most of the map is dark early); village (fits nowhere until the mushrooms are lit).

**Removable obstacles and map switches:**

- Small mushroom top-left (RemoveableMushroom_TL) ($250): R25 (G-Horizon: TL+BR at R25) / R32-36 (others). lights the top-left corner (targeting zone 30) and frees placement there
- Small mushroom bottom-right (RemoveableMushroom_BR) ($250): R25 (G-Horizon). lights the bottom-right exit corner
- Small mushroom top-right (RemoveableMushroom_TR) ($250): R28 (G-Horizon). lights the top-right (right lane entrance side)
- Small mushroom bottom-left (RemoveableMushroom_BL) ($250): R28 (G-Horizon). lights the bottom-left
- Big centre mushroom (RemoveableAreaTriggerMushroom_Main) ($400): R30 (G-Horizon) / R36 together with the 4 small ones (OneEyedDeacon) / R32 (retrogaming fun). enlarges all lit zones (centre 70, corners 60); villages and most late towers need it

**Builds (in buy order):**

*chimps, used for the 'hard' hints* - No abilities: Mermonkeys + darts + Sauda -> Axis of Havoc + Glaive Lord (OneEyedDeacon) (hero: Sauda; youtube description, v54.0). Source: https://www.youtube.com/watch?v=hO9LkFVka6M

  R6: mermonkey1 + mermonkey2; R8: dart1 bottom left; R9: dart2 top right; R12: Sauda on Close above mermonkey2; R13: dart1 0-1-0; R14: sniper1 on Strong; R15: tack1 top left; R16: dart2 0-2-0; R17: dart1 0-2-0; R19: dart2 0-3-0; R21: dart1 0-3-0; R22: sniper1 0-0-1; R24: sniper1 0-0-2; R26: sniper1 1-0-2; R27: sniper2 on First; R28: sniper2 0-2-0; R30: sniper2 0-2-1; R31: sniper2 0-2-2; R32: boomerang1; R33: boomerang1 2-0-0; R34: boomerang1 2-0-2; R35: boomerang1 3-0-2; R36: BUY the 4 outer mushrooms + the middle mushroom ($1,400); R39: sniper1 1-0-3; R40: sniper1 2-0-3; R42: village1 0-2-0; R44: village1 2-2-0; R46: boomerang1 4-0-2; R48: sniper2 0-3-2; R49: sniper1 2-0-4 on First; R50: alch1 3-0-0 for sniper2; R54: sniper2 0-4-2; R63: sniper1 2-0-5; R64: village1 3-2-0; R66: alch1 4-2-0; R81: boomerang1 5-0-2; R82: sniper3 3-2-0 on Strong; R84: sniper3 4-2-0; R86: sniper2 0-5-2 on First; R89: glue1 0-2-3 on Strong on right; R97: sniper3 5-2-0; R99: glue1 0-2-4 + glue2 0-2-3 on Strong on left

Other builds found:

- hard: Hard: run the CHIMPS order from R1 (adapted) - needs the mushroom buyer by ~R30 (hero: Sauda) - https://www.youtube.com/watch?v=hO9LkFVka6M
- chimps: No abilities/micro: Tacks + Dart + Psi -> Lord of the Abyss + Carpet of Spikes (G-Horizon) (hero: Psi) - https://www.youtube.com/watch?v=eU_eTtiYX_o
- chimps: Obyn + Druids + Elite Defender + Monarch of Storms + Perma-Spike (bloon.games 'Easy Peasy') (hero: Obyn Greenfoot) - https://bloon.games/how-to-beat-chimps-on-mushroom-grotto/
- chimps: Obyn + Desperado + Wizard + Glue Storm/Solver (HyperF3) (hero: Obyn Greenfoot) - https://www.youtube.com/watch?v=5-0zT6UDEN0
- chimps: Sauda + darts + boomerangs + Super + Wizard (retrogaming fun) (hero: Sauda) - https://www.youtube.com/watch?v=gpmuxP0hs-w

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC (og = cheapest = heroless): Monarch of Storms 5-0-2 + The Blazing Sun 5-2-0 (v54.2, Extreminator418) - druid and super monkey strong here. No LCC/CHIMPS start listed. Chom Chom: Final Harmonic / Bomb Blitz; Doreo: Superstorm (no-ability CHIMPS).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 10 spots - mermonkey, dart, sniper, tack, boomerang; hero sauda.
Removables recorded: RemoveableMushroom_TL ($250, recommended, ~R25), RemoveableMushroom_BR ($250, recommended, ~R25), RemoveableMushroom_TR ($250, recommended, ~R28), RemoveableMushroom_BL ($250, recommended, ~R28), RemoveableAreaTriggerMushroom_Main ($400, recommended, ~R30).
Model gap: Darkness is not modelled: global towers show full reach although they only hit bloons in lit zones.

**Sources:**

- https://www.bloonswiki.com/Mushroom_Grotto - Mushroom Grotto - Blooncyclopedia
- https://bloons.fandom.com/wiki/Mushroom_Grotto - Mushroom Grotto - Bloons Wiki (fandom)
- https://www.youtube.com/watch?v=hO9LkFVka6M - OneEyedDeacon - Mushroom Grotto Chimps SHREDDED by Axis of Havoc (v54.0)
- https://www.youtube.com/watch?v=eU_eTtiYX_o - G-Horizon - Mushroom Grotto CHIMPS Easy Guide (No Abilities/Micro)
- https://www.youtube.com/watch?v=5-0zT6UDEN0 - HyperF3 - BTD6 Chimps Guide Mushroom Grotto (v56)
- https://www.youtube.com/watch?v=gpmuxP0hs-w - retrogaming fun - Mushroom Grotto CHIMPS No abilities (v54)
- https://bloon.games/how-to-beat-chimps-on-mushroom-grotto/ - bloon.games - CHIMPS on Mushroom Grotto

### Ascent

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** One of the easiest Advanced maps: two long lanes with few sight blockers. Cover the top edge of the big central island where both lanes pass, plus global towers.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- Both lanes are used every round; the right lane is ~40% longer than the left (bloonswiki). Boss bloons have their own path tag.
- Line-of-sight blockers: pointed grey rocks (left side near the entrances, right side near the exits) and the elevated rock pool on the second-biggest island.
- Heli Pilots in Pursuit may get confused by the multiple paths (bloonswiki) - still usable.
- Water: top pond (legal for subs in bot model), right pond by the exits and a tiny bottom-left pond by the entrances (both not legal for subs in the bot model).

**Towers that work:**

- spike 2-0-5: Perma-Spike on the middle platform at the bottom right hits both paths near the end (better than the isolated island further ...
- sub 3-0-1: Submerged sub at the start decamos all bloons (3-0-1 makes it consistent); optional Bloontonium Reactor.
- wizard 4-0-2: CrimsonPlanet CHIMPS core (Dragon's Breath -> Phoenix).
- druid 2-5-0 / 0-1-4: Spirit of the Forest on long tracks (CrimsonPlanet); 6 Poplust druids + Avatar of Wrath (HyperF3); LTC heroless uses SotF.
- heli 2-0-5: Comanche Commander with Pursuit (CrimsonPlanet).
- village 2-3-0: Both CHIMPS lists use a 2-3-0 village.

**Avoid:** buccaneer (little usable water (only the top pond)).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Hard: CrimsonPlanet CHIMPS order from R1 (adapted) (hero: Obyn Greenfoot; inferred, adapted from v56 CHIMPS; Hard text guides not found (BTD6 Fenix / Mr.). Source: https://www.youtube.com/watch?v=KEmm-iPaHl0

  R1: Mage on the big island top edge; R2-4: sub(s) in the top pond; R5-8: Obyn beside the mage; R10-20: Mage 3-0-2, Druid 1-3-0; R25-35: Heli 2-0-3 (Pursuit), Village 2-3-0 (camo for the druid/mage); R38-50: Mage 4-0-2, Druid 2-5-0; R55-75: Heli 2-0-5; optional glue 0-2-4; Placements: same spots as the CrimsonPlanet CHIMPS build.

*chimps, used for the 'chimps' hints* - Subs + Ninja + Druids (Poplust) + Avatar of Wrath + Perma-Spike (HyperF3) (hero: Obyn Greenfoot; youtube description, v56). Source: https://www.youtube.com/watch?v=TZg8hFFquZA

  Sub; Dart; Sub 0-0-1; Obyn; Ninja; Sub 0-0-2; Ninja 0-0-1; Druid; Druid 1-3-0; Spike Factory; Spike Factory 0-0-2 -> 2-0-4; Village; 6x Druids; Druid 0-1-4; Village 2-2-0; 5x Druids 0-1-4; Glue Gunner -> 0-1-3; Druid 0-1-5 Avatar of Wrath; Village 2-3-0; Spike Factory 2-0-5; Alchemist 4-2-0; Glue 0-2-4; $26,463 left

Other builds found:

- chimps: No micro/abilities: Mage + 2 Subs + Obyn + Druid + Heli (CrimsonPlanet) (hero: Obyn Greenfoot) - https://www.youtube.com/watch?v=KEmm-iPaHl0

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: MOAB Domination 0-2-5 + Geraldo (v56.0, urhere); heroless: Spirit of the Forest 1-5-0 + M.A.D 1-5-0 (v56.0, Edge); cheapest: The Blazing Sun 5-0-2 + Geraldo (v56.0). LCC $38,255 (v57.3, Capsen) / $53,130 (v56.0, Chom Chom). Wiki CHIMPS start video eIzkhsbqUCQ.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 8 spots - wizard, sub, druid, heli, village, alchemist, glue; hero obyn; 'chimps' (impoppable, chimps): 10 spots - sub, dart, ninja, druid, spike, village, glue, alchemist; hero obyn.

**Sources:**

- https://www.bloonswiki.com/Ascent - Ascent - Blooncyclopedia
- https://bloons.fandom.com/wiki/Ascent - Ascent - Bloons Wiki (fandom)
- https://www.youtube.com/watch?v=KEmm-iPaHl0 - CrimsonPlanet - Ascent CHIMPS Guide (No Micro & Abilities) v56.0
- https://www.youtube.com/watch?v=TZg8hFFquZA - HyperF3 - BTD6 Chimps Guide Ascent (v56)
- https://www.youtube.com/watch?v=G2mIVaspiIw - MaxMonki - Ascent CHIMPS
- https://btd6index.win/ - BTD6 Index

### Ship Capture

*Advanced map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Bloons board the central ship from one side at a time (both sides from round 45 on some rounds) over short plank lanes that converge at the central hatch. Build on the hatch/grate where all four lanes meet.

**Lanes:** alternating.

**What the guides found** (detail from the sources):

- Ship rotation (bloonswiki table): Left 5-9, 15-19, 25-29, 35-39, 50-54, 65-69, 80-84, 95-99, ...; Right 1-4, 10-14, 20-24, 30-34, 40-44, 55-59, 70-74, 85-89, 100-104, ...; Both 45-49, 60-64, 75-79, 90-94, ...
- Bot geometry: AlternateBloonSplitter over the 4 plank paths; boss path override.
- Hatch ($1000, 'RemoveableAreaLand', click ~0.427,0.62): supports land towers; removing it (only possible with nothing on it) turns it into water (area 2161).
- Crow's nest supports up to 5 small towers; quarterdeck at the bottom has a lot of land.

**Towers that work:**

- spike 2-0-5: Short lanes leak easily; Perma-Spike targeted between the two main lanes catches everything (wiki, dq7 guide).
- mermonkey 4-x-x / 5-0-x: Abyssal Warrior/Lord of the Abyss excel at cleanup from the central water and carry past R40 (needs the hatch removed for the ...
- desperado 4-2-0: High range covers both lanes; dq7 opens with 2 Desperados on the grate.
- druid 1-5-0 / 3-0-1: Spirit of the Forest vines cover both approaches (dq7); Hbomb's black border used Obyn + Druids + Permabrew.
- boomerang x-x-4: Three MOAB Presses on Strong delay R95-100 blimps (dq7).
- glue 0-2-4: Relentless glue on Strong slows blimps before the spike pile (dq7).

**Avoid:** sub (the sea around the ship is not water; only after buying the hatch); buccaneer (same as subs); tack (one side covers only one ship's lanes).

**Removable obstacles and map switches:**

- Hatch / central grate ('RemoveableAreaLand') ($1000): only if planning water towers (Mermonkey water bonus / Lord of the Abyss / Carrier Flagship / subs) - BEFORE placing anything on it (cannot be removed with .... turns the grate into water for water towers

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Hard: dq7 CHIMPS layout from R1 on the central grate (adapted) (hero: Obyn Greenfoot; inferred, adapted from v57 CHIMPS; no Hard text guide found (BTD6 Master / Mr.). Source: https://dq7reimagined.com/btd6/ship-capture-chimps/

  R1: Desperado on the upper grate (bot has Double Cash); R2-5: second Desperado below it, Skywarden below; R6-10: second Skywarden, Obyn under them; R12-18: Druid left of Obyn, Spike Factory above the druid 0-0-2; R20-30: Spike 1-0-3, Mermonkey beside the druid, Village above the spike (2-0-0 -> 2-2-0 for camo); R30-39: Druid 1-3-0, Spike 1-0-4 before R40; R40-60: Druid #2 3-0-1, Desperado 4-2-0 Strong, Mermonkey 4-x-x; R60-80: Druid 1-5-0 Spirit of the Forest, Spike 2-0-5, Glue 0-2-4 Strong, MOAB Press boomerangs; Placements: same spots as the dq7 CHIMPS build.

Other builds found:

- chimps: No micro: Desperados + Skywardens + Obyn + Spirit of the Forest + Perma-Spike + MOAB Press (dq7reimagined write-up) (hero: Obyn Greenfoot) - https://dq7reimagined.com/btd6/ship-capture-chimps/

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC heroless: The Final Harmonic + Pop and Awe 0-5-2 + The Bloon Solver 5-2-0 (v57.1, Skucha). 2TC: Popseidon + Geraldo (Extreminator418, BTD6 Index YouTube ByDZVUVtbps). Other CHIMPS: Etienne + Carrier Flagship + Pirate Lord + Pre-emptive Strike (hatch removed), Silas + Carpet of Spikes (sYnce), Obyn + Druids + Permabrew (Hbomb), Jones + Primary Expertise + MOAB Maulers (Zeroprince).

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 15 spots - desperado, skywarden, druid, spike, mermonkey, village, glue, boomerang, alchemist; hero obyn.

**Sources:**

- https://www.bloonswiki.com/Ship_Capture - Ship Capture - Blooncyclopedia
- https://bloons.fandom.com/wiki/Ship_Capture - Ship Capture - Bloons Wiki (fandom)
- https://dq7reimagined.com/btd6/ship-capture-chimps/ - dq7reimagined - How to Beat Ship Capture CHIMPS in BTD6 Without Micro
- https://www.youtube.com/watch?v=QSYsmdxsa3M - Hbomb Extras - Ship Capture CHIMPS
- https://www.youtube.com/watch?v=MmIHEDOuMwI - 신사알파카 - Ship Capture CHIMPS v57.0
- https://www.youtube.com/watch?v=GkC3sViEC3w - sYnce - Ship Capture CHIMPS w/ Silas & Carpet of Spikes
- https://www.youtube.com/watch?v=scOAepinmGA - Zeroprince - Ship Capture CHIMPS

## Expert maps

### Muddy Puddles

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Four lanes take turns, one per round, in a 6-round cycle; lanes 2 and 3 get two thirds of the rounds, so the middle pond between them is the key spot. Advanced-Intel subs there plus snipers and crossbow darts between lanes.

**Lanes:** alternating.

**What the guides found** (detail from the sources):

- Lane schedule (since v9.0): lane 1 = rounds 1,7,13,...(r%6==1); lane 2 = r%6==2 or 0 (2,6,8,12,...,96,98); lane 3 = r%6==3 or 5 (3,5,9,11,...,95,99); lane 4 = r%6==4 (4,10,16,...,94,100). Source: https://bloons.fandom.com/wiki/Muddy_Puddles/Strategies
- Boss Bloons always appear on lane 2 (middle-left). Source: https://www.bloonswiki.com/Muddy_Puddles
- Key rounds by lane: R40 MOAB -> lane 4 (40%6=4); R60 BFB -> lane 2; R63 -> lane 3; R78 -> lane 2 (78%6=0); R80 ZOMG -> lane 2; R95 -> lane 3; R98 -> lane 2; R100 BAD -> lane 4. (computed from the wiki formula)
- Lane x-positions on the 16:10 screen (screen fractions): lane 1 x~0.12-0.21, lane 2 x~0.28-0.39, lane 3 x~0.46-0.57, lane 4 x~0.62-0.73; all run top (entrance) to bottom (exit), ~9.7 RBS each.

**Towers that work:**

- heli 2-0-5: Comanche Commander: Heli shines on single-lane-per-round maps; wiki calls a buffed Comanche Commander a solid win condition here ...
- sub 2-0-4 / 2-0-5: Cheap early power; Advanced Intel (2-x-x) gives effectively global range so a sub in the middle pond hits every lane
- buccaneer 5-0-2: Boat in the middle pond covers lanes 2 and 3; Carrier Flagship planes are global. Used in the G-Horizon CHIMPS run.
- sniper 1-0-1 / 4-0-2: Global range with no LOS blockers on this map - handles leads/camo/MOAB on every lane.
- desperado 0-1-0: Long-range cheap early damage between lanes; G-Horizon uses four 0-1-0 desperados.
- beast_handler x-x-x (Adasaurus / Velociraptor): Wiki: merged Beast Handlers save into Adasaurus/Velociraptor that ignore the lane problem (needs merging micro - probably not ...

**Avoid:** tack (covers one lane: most rounds bypass it).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff 'Muddy Puddles - Hard | No MK (No Heroes & Farms)' - crossbow darts between lanes + Advanced-Intel subs in the middle pond + Alch/Village, Sub Commander (hero: none (author used no hero; the bot may add Quincy/Psi between lanes 2 and 3); youtube description, old (~4 years, ~v25-28); Hard ends at R80). Source: https://www.youtube.com/watch?v=2oT7VyTQKKk

  R3: Dart (right-mid) 0-0-0; Sniper 0-0-0 targeting Strong; R5: Sub (a) in the middle pond; R6 (after round): Dart (left); R7: Sub(a) 1-0-0; R9 (after round): Sub(a) 2-0-0; author SELLS Dart (left) [bot: keep it]; Dart (right-mid) 0-0-1; R12: Sub(a) 2-0-1; R13 (after round): Dart (top); R14: Dart (top) 0-0-1; R15 (after round): Dart (right-top); R18: Sub(a) 2-0-2; R19: Dart (left) again; R21 (after round): Dart (right-top) 0-0-1; R23: Dart (top) 0-0-2; R25: Sub(a) 2-0-3; R26: Sniper 1-0-0; R27: Sniper 1-0-1; R32 (after round): Alchemist 3-0-0 next to the subs; R34 (after round): Alch 3-0-1; R35 (after round): Sub (b) 2-0-1; R37: Dart (left) 0-0-2; R38 (after round): Alch 4-0-1; R39 (after round): Sub(b) 2-0-2; Dart (right-top) 0-0-2; Dart (right-mid) 0-0-2; R41: Sub(b) 2-0-3; R44: Sub(a) 2-0-4; R48: Village 2-0-0, also covering the Alch; R54: Dart (left) 0-0-3; Sub(b) 2-0-4; R55: Dart (left) 0-2-3; R58 (after round): Village 2-2-0; R62 (after round): author sells the village to afford Sub(a) 2-0-5 (Sub Commander) and re-buys Village 2-0-0 at R63 [bot with Double Cash: no sell]; Dart (top) 0-0-3; R64: Dart (right-top) 0-0-3; R66: Sub (c) 2-0-3; R68: Sub(c) 2-0-4; R74: Dart (right-mid) 0-2-4; R76 (after round): Sniper 4-0-2; R78: Dart (top) 0-2-4; Village 2-2-0; R79: Dart (left) 0-2-4; Sub (d) 2-0-4; after the round a Dart near the spawn; R80: win

*chimps, used for the 'chimps' hints* - G-Horizon 'Muddy Puddles CHIMPS Easy Guide (1 Ability, No Micro)' - boat/sniper/sub start, Psi, 2-0-4 subs + Pre-Emptive Strike (hero: Psi; youtube description, ~v55 (uploaded ~7 months before Oct 2026; exact version not stated)). Source: https://www.youtube.com/watch?v=gJLFvkHiOBk

  R6: 0-0-0 Buccaneer (boat) in the MIDDLE pond (between lanes 2 and 3), targeting Strong (author pixel [624,674] @1080p); R7: 0-0-0 Sniper (author gives no spot - map has no line-of-sight blockers, put it on open land at the top between lanes); R8: Sniper targeting Strong; R9: Sub1 0-0-0 in the RIGHT pond (left of lane 4) (author pixel [1249,420] @1080p); R10: Boomerang 0-0-0, targeting Last, bought mid-round (spot not given; author warns Rounds <15 can leak by RNG because of the boomerang timing); R12: Desperado1 0-0-0 targeting Strong, just left of lane 2 at mid height (pixel [623,507]); switch Boat to First; R14: Sub2 1-0-0 (Sub2 spot not given - assume middle pond next to the boat); R16: Sub2 2-0-0 (Advanced Intel); R18: Sub2 2-0-1 (mid-round); R22: Sub2 2-0-2; R24: Desperado1 0-1-0; R27: place Psi (spot not given; Psi has global range); R28: Sniper 1-0-1; R32: Sub2 2-0-3 (Airburst); R36: Sub2 2-0-4 (Armor Piercing); R40: Sub3 2-0-2, Alchemist 3-0-0 (next to the subs), Desperado2 0-1-0, Psi targeting Strong; R42: Desperado3 0-1-0; R45: Village 2-0-2; R47: Sub4 2-3-0, Alchemist 3-2-0; R48: Sub3 2-0-3, Boat 0-0-2; R60: Sub2 2-0-5 (Sub Commander); R63: Sub3 2-0-4, Desperado4 0-1-0; R82: Sub4 2-5-0 (Pre-Emptive Strike; its First Strike ability is the single ability used); ASAP after: Boat 5-0-2 (Carrier Flagship); Optional (author note, not in video): Glue 0-2-4 above the sub to clear Round 98 safely; R100: author fires the 2-5-0 ability after the BAD passes the middle of the track (a blind ability press may fire too early)

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC og: Turbo Charge 0-4-2 boomerang + Glaive Lord 5-0-2 + Geraldo (v44.0, RealLenny); heroless LTC: MOAB Press 0-2-4, MOAB Domination 2-0-5 (ace), Elite Defender 0-2-5, Permanent Brew 5-0-2 (v49.4). LCC ~60,160 (v49.3 doreo). Listed CHIMPS starts: 'Muddy Ada early' (Adasaurus by R19), r19-21 Airburst sub starts with 1-2 buccaneers or 2 snipers, 'no-steal r19 airburst with Skywarden'.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 11 spots - dart, sniper, sub, alchemist, village; hero quincy; 'chimps' (impoppable, chimps): 11 spots - buccaneer, sniper, sub, boomerang, desperado, alchemist, village; hero psi.

**Sources:**

- https://www.bloonswiki.com/Muddy_Puddles - Muddy Puddles - Bloonswiki
- https://bloons.fandom.com/wiki/Muddy_Puddles/Strategies - Muddy Puddles/Strategies - Bloons fandom
- https://www.youtube.com/watch?v=gJLFvkHiOBk - G-Horizon - BTD6 Muddy Puddles CHIMPS Easy Guide (1 Ability, No Micro)
- https://www.youtube.com/watch?v=2oT7VyTQKKk - BlueCliff - Muddy Puddles Hard No MK (No Heroes & Farms)
- https://www.youtube.com/watch?v=86YZVykWpfc - BTD6 Index - Muddy Puddles CHIMPS w/ 102k spare by GreenKookie56
- https://www.youtube.com/watch?v=J64bIRAsOHI - NovaGoBoom - Muddy Puddles Updated Deflation Guide (Full AFK, no MK)
- https://www.youtube.com/watch?v=vbC1grMiUdA - NomadTech - Easiest One Tower Expert Deflation (v44+)

### #Ouch

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Four very short lanes are all active every round; everything must reach from the central pond: 2-0-4 subs, a Pirate Lord, alchemist and village. Do not drain the pond.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- 4 entrances, 4 exits, all simultaneous every round; vertical lanes are ~22% shorter than horizontal ones (8.0 vs 10.2). Source: https://www.bloonswiki.com/Ouch
- Screen fractions: left vertical lane x~0.30-0.33, right vertical lane x~0.54-0.57 (enter at top, exit at bottom); top horizontal lane y~0.32-0.37, bottom horizontal lane y~0.65-0.70 (enter at the left edge, exit under the shop panel on the right).
- Central pond (x~0.35-0.52, y~0.40-0.60) holds up to 9 buccaneers or 13 subs (fandom); it is the only water. Source: https://bloons.fandom.com/wiki/Ouch
- Pond can be drained for $1,000 ONLY if no water tower is on it; draining opens the centre for land towers (GMN + Shinobi strategy). Source: https://bloons.fandom.com/wiki/Ouch

**Towers that work:**

- sub 2-0-4: Advanced Intel subs in the central pond hit all 4 lanes; core of both BlueCliff and CurlyFrys Hard builds.
- buccaneer 5-2-0: Pirate Lord in the centre pond reaches all 4 lanes and hooks MOAB-class (Hard win condition in BlueCliff and CurlyFrys).
- sniper 1-0-2 / 4-0-2 / 0-2-5: No LOS blockers; cheap leads answer (1-0-0 for R28/R30) and Maim MOAB for R40 stall; fandom recommends it.
- alchemist 4-2-0: Brew on the sub/boat cluster; range buff lets towers cover all lanes.
- village 2-2-0: Range buff + MIB/camo for the centre cluster.
- mermonkey x-x-x Symphonic Resonance: Wiki: from the central pond its water range covers all 4 lanes and stalls MOABs/DDTs.

**Avoid:** tack (away from the centre it covers 1-2 of the 4 lanes).

**Removable obstacles and map switches:**

- Central pond (drain the water) ($1000): Only for a land-centre strategy (e.g. OneEyedDeacon drains at R26 before buying the centre Ninja); impossible once any water tower is on it. Turns the pond into land that reaches all 4 lanes for Grandmaster Ninja + Shinobi; do NOT buy it in a sub/boat build

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff '#Ouch - Hard | No Monkey Knowledge (ft. Quincy)' - subs in the pond + sniper + alch, then 5-2-0 Pirate Lord and 0-2-5/4-0-2 snipers (hero: Quincy; youtube description, old (uploaded ~4 years ago, ~v25-28); tower stats changed since, Hard is now ...). Source: https://www.youtube.com/watch?v=Kxojxz7wJlE

  R3: Dart (top-right); Sub (a) in the pond, bottom-left part; after the round: Dart (bottom-right); R7 (after round): Quincy; R8: Sub(a) 1-0-0; R10: Sub(a) 2-0-0; R13: Sub(a) 2-0-1; R14: Sniper, targeting Strong; R18: Sub(a) 2-0-2; R21: Sniper 1-0-0, after the round 1-0-1; R22 (after round): Sniper 1-0-2; R25: Sub (b) in the pond; R26: Sub(b) 1-0-0; R27: Sub(b) 2-0-0 then 2-0-1; R31: Sub(b) 2-0-2; R32: top-right Dart 0-0-2; R35 (after round): Alchemist 3-0-0 (next to the subs), top-right Dart 0-0-3; R36: Quincy ability on the 3rd rush (bot: blind ability press is acceptable); R38 (after round): Alchemist 4-0-0; R39: Alchemist 4-0-1, Sub(a) 2-0-3; author then SELLS the bottom-right dart and re-places a Dart top-left near the spawn (bot: skip the sell, just add the top-left dart); R40: Quincy ability; R41: bottom-right Dart 0-0-2; R43: Sub(a) 2-0-4; R44: Sub(b) 2-0-3; R45: Sub(b) 2-0-4; R48: Village (a) 2-0-0, very close to the track; R49 (after round): Banana Farm (a) 0-2-3 near the track [optional for the bot - it has Double Cash]; R52 (after round): Farm (b) 0-2-3; Village (b) placed to buff main village range; R53 (after round): Buccaneer 0-2-0 in the pond, inside village range; R54: Buccaneer 1-2-0 then 2-2-0; R55: Buccaneer 3-2-0; R58: Buccaneer 4-2-0; after the round Village(a) 2-2-0; R62 (after round): author sells all subs, darts, farms and the sniper to afford Buccaneer 5-2-0 (Pirate Lord) and an Ice Monkey 0-2-3 on Strong [bot: with Double Cash ...; R64: (sells ice) Sniper 0-2-3; R66: Sniper 0-2-4; R74: Sniper 4-0-2 on Strong (second sniper); R79: Sniper 0-2-5; Author uses Quincy level-10 / level-3 abilities on rushes R55-R80 (bot fires them blindly)

Other builds found:

- hard: CurlyFrys '#OUCH Hard Standard Easy Tutorial' - tower list only (Sauda + subs + Pirate Lord) (hero: Sauda) - https://www.youtube.com/watch?v=UYXG9xnWkX0
- chimps: OneEyedDeacon '#Ouch Chimps Strategy is NERF-PROOF' v49.2 - 5 darts start, Geraldo, spikes, DRAIN THE POND at R26 ... (hero: Geraldo) - https://www.youtube.com/watch?v=UvU1PYOKxg4

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC og: Sun Avatar 3-2-0 + Pre-Emptive Strike 0-5-2 (sub) + Geraldo (v31.0); heroless LTC (v49.3): Elite Defender 0-2-5, Permanent Brew 5-0-0, Pirate Lord 2-5-0, Avenger 0-2-4 (name as listed by the index), Bounty Hunter 2-4-0. LCC 64,405 (v57.2 Capsen). => sub (Pre-Emptive), Pirate Lord, perma-brewed snipers and global towers win here.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 8 spots - dart, sub, sniper, buccaneer, village; hero quincy.
Removables recorded: Water ($1000, never).

**Sources:**

- https://www.bloonswiki.com/Ouch - #Ouch - Bloonswiki
- https://bloons.fandom.com/wiki/Ouch - #Ouch - Bloons fandom
- https://bloons.fandom.com/wiki/Ouch/Strategies - Ouch/Strategies - Bloons fandom
- https://www.youtube.com/watch?v=Kxojxz7wJlE - BlueCliff - BTD6 #Ouch Hard No MK (ft. Quincy)
- https://www.youtube.com/watch?v=UYXG9xnWkX0 - CurlyFrys - #OUCH Hard Standard Easy Tutorial
- https://www.youtube.com/watch?v=UvU1PYOKxg4 - OneEyedDeacon - #Ouch CHIMPS NERF-PROOF guide v49.2
- https://btd6index.win/ - BTD6 Index (idx.py '#Ouch')

### Dark Castle

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Four entrances merge into one short exit through the castle door, and bloons are immune under the tree packs. Stack towers at the merge point (grass above/below it), a sub in the river, and buy the trees ($1,000 each) to lengthen the lanes.

**Lanes:** merging.

**What the guides found** (detail from the sources):

- 4 entrances (left edge, y~0.16/0.38/0.66/0.87) under 4 removable tree packs ($1,000 each); bloons are IMMUNE while under the trees; lengths with trees ~6.9-7.2, without ~9.1-10.2 RBS (btd6index).
- The top lane is always the first lane of each round - removing the TOP trees first lets MOAB stall (Maim MOAB) work earlier (fandom tip). Source: https://bloons.fandom.com/wiki/Dark_Castle
- Lanes converge around x~0.30-0.50, y~0.50 and run right through the castle door (x~0.70) to the exit; bloons start shrinking at the door; the door opens each round.
- Water: a river from top to bottom at x~0.54-0.68 (gap where the track crosses at y~0.42-0.62) - subs/boats/mermonkeys go there next to the track.

**Towers that work:**

- druid 0-1-4 -> 0-1-5: Avatar of Wrath / Poplust stack at the convergence; wiki: 6 Poplusts save up to AoW with little help
- spike 2-0-5 / 0-2-5: Perma-Spike covers the single convergent exit and AoW's DDT/end-of-round weakness (wiki).
- village 5-2-0 / 2-0-2: Everything sits in one spot, so villages are very effective (wiki: Primary Expertise).
- sub 2-0-4 / 2-0-5: River next to the merged track; BlueCliff Hard and Yoboi3li start.
- ninja 4-0-2 / 5-0-1: Seeking shuriken at the convergence (BlueCliff Hard; fandom GMN tip).
- bomb x-x-x Cluster/Bomb Blitz: Grouped bloons at the merge - fandom/wiki recommend cluster bombs, Bomb Blitz.

**Avoid:** sniper (castle walls and tree packs block its sight).

**Removable obstacles and map switches:**

- Top tree pack (covers the top entrance) ($1000): R39 in BlueCliff Hard (before the R40 MOAB); best first removal per fandom. Bloons are immune under trees; the top lane is always the first lane each round, so removing it lets stall towers (Maim MOAB) act sooner
- Remaining 3 tree packs (upper-middle, lower-middle, bottom entrances) ($1000): R47 in BlueCliff Hard (all three at once). Longer usable track for every lane; needed for Pre-Emptive Strike passive

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff 'Dark Castle - Hard | No MK (ft. Obyn)' - Ninja 4-0-2 + Sub 2-0-5 + Alch, crossbow darts, buys the tree removals (hero: Obyn; youtube description, old (~3 years, ~v33-35); Hard ends at R80). Source: https://www.youtube.com/watch?v=QB0bitxGZn0

  R3: Ninja 0-0-0 (by the convergence); after the round Dart (middle); R8: Obyn; R10: Ninja 1-0-0; R11: Sub (first) 0-0-0 in the river; R14: Sub 2-0-0; R15: Ninja 1-0-1; R17: Sub 2-0-1; R21: Sub 2-0-2; R25: Sub 2-0-3; R27: Alchemist, set targeting Strong; R28 (after round): Alch 1-0-0; R32: Ninja 3-0-2; R35 (after round): Alch 3-0-1; R38 (after round): Alch 4-0-1; R39: REMOVE THE TOP TREE obstacle ($1,000); Dart (top) 0-0-3; R40: Obyn ability (blind press ok); R42: Ninja 4-0-2; R45: Sub 2-0-4; R47: REMOVE ALL REMAINING TREE obstacles (3 x $1,000); Dart (bottom) 0-0-3; R48: Dart (left mid) 0-0-3; R49: Village 2-2-0; R50: author sets Obyn's Wall of Trees target to the end of the track (micro - skip); R55: Obyn level-10 ability; R62 (after round): author sells the village to afford Sub 2-0-5 (Sub Commander), then re-buys Village 2-0-0 [bot: with Double Cash just buy both]; R70: Sub (second) 2-0-4; R74: Sub (third) 2-0-4; R77: Sub (fourth) 2-0-4; R79: Sniper 4-0-2 targeting Strong; Dart (top left); R80: win

*chimps, used for the 'chimps' hints* - Yoboi3li 'Dark Castle Chimps - Safe Black Border Guide (No Abilities, No Micro)' - Sub+Skywarden start, Obyn, 7 druids -> Poplust -> Avatar of Wrath, Perma-Brew (hero: Obyn; youtube description, ~v57 (uploaded ~1 month before Oct 2026)). Source: https://www.youtube.com/watch?v=YUR_SIL0trE

  All actions are done AFTER the given round ends (autostart off); Start (R6): Sub 0-0-0 and Skywarden 0-0-0 (author's placement shown only on video); R7: Boomerang 0-0-0; R10: Obyn 'pretty far left'; R13: Sniper, targeting Strong; R15: 2 Druids; R20: Sniper 0-2-1 (author: 1-2-0 may be better), switch it to First; R27: Village 0-0-2; R30: Druid 0-1-1 upgrades; R31: Druid 1-0-1 placed; R33: that druid 2-0-1; R35: that druid 3-0-1; R37: more 0-1-1 druids until 7 druids total (6 x 0-1-1 + the 3-0-1); Alchemist 0-0-0; R39: Alch 3-0-1; R44: the 3-0-1 druid -> 4-0-2; R48: two druids 0-1-4 (Poplust); R49: third Poplust; R50: Village 2-0-2, Alch 4-0-1; R51-78: nothing (AFK); after R78: Alch 5-0-1 (Permanent Brew); R81: remaining 3 druids -> Poplust (0-1-4); R94: centre Poplust -> Avatar of Wrath (author writes '510' = 0-1-5); No abilities, no micro

Other builds found:

- chimps: BlueCliff 'Dark Castle - CHIMPS | Black Border (ft. Quincy)' - 2 darts + sub start, Sub 2-0-4, Alch 4-0-1, Perma-Spike ... (hero: Quincy) - https://www.youtube.com/watch?v=oePssmHJDTc
- magic_only: BlueCliff 'Dark Castle - Magic Monkeys Only | No MK (ft. Quincy)' - Ninja 4-0-2 + Alch, Druids 4-1-0, Wizards 4-0-2 ... (hero: Quincy) - https://www.youtube.com/watch?v=iIjUXUJvZzM
- abr: BlueCliff 'Dark Castle - Alternate Bloons Rounds | No MK (ft. Quincy)' - Ninja 4-0-2, Elite Sniper 2-5-0 + Maim sniper ... (hero: Quincy) - https://www.youtube.com/watch?v=eBbLW2xyTgw
- impoppable: BlueCliff 'Dark Castle - Impoppable | No MK (ft. Quincy)' - darts + Sub 2-0-4 + Alch, Elite Sniper 2-5-0 + 4-0-2 ... (hero: Quincy) - https://www.youtube.com/watch?v=AIhDzKj_4QE
- chimps: BeatbloonsBob 'World's Easiest Dark Castle CHIMPS Guide EVER' - Desperados, Mermonkey 4-2-0, Silas, Spike Factory ... (hero: Silas) - https://www.youtube.com/watch?v=W0naQh_vc7E

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC og/cheapest: Perma Charge 0-5-2 (boomerang) + Geraldo (v31.0); heroless LTC: Perma Charge 0-5-2, M.A.D 1-5-0 (dartling), Carrier Flagship 5-0-2 (v44.1). LCC ~54,850 (v40.2). => boomerang/perma-charge at the merge is extremely strong; the map is easy for most comps.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 9 spots - ninja, dart, sub, alchemist, village, sniper; hero obyn; 'chimps' (impoppable, chimps): 14 spots - sub, skywarden, boomerang, sniper, druid, alchemist, village; hero obyn.
Removables recorded: Trees1 ($1000, optional, ~R39), Trees2 ($1000, optional, ~R47), Trees3 ($1000, optional, ~R47), Trees4 ($1000, optional, ~R47).

**Sources:**

- https://www.bloonswiki.com/Dark_Castle - Dark Castle - Bloonswiki
- https://bloons.fandom.com/wiki/Dark_Castle - Dark Castle - Bloons fandom
- https://bloons.fandom.com/wiki/Dark_Castle/Strategies - Dark Castle/Strategies - Bloons fandom
- https://www.youtube.com/watch?v=QB0bitxGZn0 - BlueCliff - Dark Castle Hard No MK (ft. Obyn)
- https://www.youtube.com/watch?v=YUR_SIL0trE - Yoboi3li - Dark Castle Chimps Safe Black Border (No Abilities, No Micro)
- https://www.youtube.com/watch?v=W0naQh_vc7E - BeatbloonsBob - World's Easiest Dark Castle CHIMPS Guide
- https://www.youtube.com/watch?v=_nvTG8wSnI0 - Yoboi3li - Dark Castle Impoppable No MK

### Quad

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Four entrances are all active and each path loops through two quadrants; bloons are immune under the trusses. Defend two kill zones (bottom-left and top-right edges of the diamond) with a dart in each corner early, then subs, snipers, bombs and villages.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- 4 entrances/exits active every round; each exit is at the same truss as another entrance; paths 11.3-12.3 RBS (wiki). Source: https://www.bloonswiki.com/Quad
- Diamond corners on screen: top (0.43,0.16), left (0.13,0.52), right (0.73,0.52), bottom (0.43,0.88); entrances/exits under trusses at top (0.43,0.04), left edge (0.0,0.5), right (0.85,0.5), bottom (0.43,0.95).
- 4 removable trusses ($1,500 each): block line of sight AND make all bloons/blimps immune underneath; removing also clears the bush in front, freeing space. Pre-Emptive Strike passive and Pre-Game Prep spikes do nothing under trusses.
- Killzones: bottom-left edge (x~0.2-0.35, y~0.6-0.8) receives bottom+right entrances, top-right edge (x~0.5-0.7, y~0.25-0.45) receives top+left entrances (fandom 'The Killzones'). Source: https://bloons.fandom.com/wiki/Quad/Strategies

**Towers that work:**

- spike 3-x-x / 4-x-x (Spiked Balls/Mines): Wiki/fandom: two spike factories turn Quad into a two-lane map and make leaks visible
- bomb 0-3-x / 0-2-4: MOAB Maulers combo with Spiked Balls (classic black border); BlueCliff Hard uses 0-2-4 cluster bombs at the corners.
- boomerang 5-0-2: Glaive Lord rangs bounce all over Quad after v43 (wiki).
- beast_handler x-x-4 Giant Condor: Moves blimps into one lane, effectively halving the lanes (wiki).
- sniper 4-0-2 / 2-0-5 / 0-5-2: Global range to all four lanes (BlueCliff Hard, OneEyedDeacon CHIMPS).
- sub 2-0-3 / 2-0-4: Airburst handles early rounds 15/22/27/35/36; Advanced Intel needed to reach from the pond; weak late (perpendicular shots).

**Removable obstacles and map switches:**

- Left truss and right truss ($1500): R74 in BlueCliff Hard; fandom: removing left+right lets a First Strike/Reactor combo fire twice on the R100 BAD. Bloons are immune under trusses and they block LOS; removal adds track length (left/right path 9.3->12.4 RBS with both overhangs removed)
- Top truss and bottom truss ($1500): R79 in BlueCliff Hard (before R80). Same - more track, LOS, frees the bush space

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff 'Quad - Hard | No MK (ft. Quincy)' - a dart in each diamond corner, Quincy, 2-0-4 sub + mid Alch, sniper 4-0-2, wizard 4-0-2, 0-2-4 recursive cluster bombs, villages; buys all 4 trusses late (hero: Quincy; youtube description, old (~4 years, ~v25-28); Hard ends at R80). Source: https://www.youtube.com/watch?v=DAJAobKFCLE

  R3: Dart (top), Dart (left), Dart (right) - one inside each corner of the diamond; R6 (after round): Quincy; R7: Dart (bottom); R9 (after round): Sub in the pond; R10: Sub 1-0-0; R13: Sub 2-0-0; R14: Sub 2-0-1; R19: Sub 2-0-2; after the round Sniper, targeting Strong; R21 (after round): Sniper 0-0-1; R22 (after round): Sniper 1-0-1; R27: Sub 2-0-3, Sniper 1-0-2; R30: Dart (bottom) 0-0-2; R34 (after round): Alchemist (mid) 3-0-0 - it should buff the sub only; R35 (after round): Alch (mid) 3-0-1; Dart (bottom) 0-2-3; R36/R40: Quincy ability (optional); R38 (after round): Alch (mid) 4-0-1; R39 (after round): Dart (left) 0-0-2; Sniper 2-0-2; R41: Dart (right) 0-0-2; R43: Sub 2-0-4; R45: Dart (top) 0-0-2; Sniper 3-0-2; R48: Village (top left) 2-0-0 covering Quincy and the Sub (not Alch mid); R49 (after round): author SELLS Dart (bottom) [bot: skip]; Wizard 3-0-2; Alchemist (bottom) 3-0-1 buffing only the wizard; R55 (after round): Wizard 4-0-2; R59 (after round): Bomb (a, right) 0-2-4 inside Alch (mid) range; R61: Bomb (a, left) 0-2-4 inside Village (top left) range; R62 (after round): Village (top left) 3-0-0; R64 (after round): Alch (bottom) 4-0-1; R66: Village (bottom right) 3-0-0 covering wizard and bomb, not Alch (mid); R70: Sniper 4-0-2; R72 (after round): Bomb (b, right) 0-2-3 in range of Village (bottom right) and Alch (mid); R73 (after round): Bomb (b, right) 0-2-4; R74: REMOVE right truss and left truss ($1,500 each); R75 (after round): Village (bottom right) 4-0-0; R77: Village (bottom right) 4-2-0; R79: REMOVE top and bottom trusses ($1,500 each); Bomb (b, left) 0-2-4; R80: win; author times Quincy L3/L10 abilities on R55-R80 rushes

*chimps, used for the 'chimps' hints* - OneEyedDeacon 'Quad Chimps ft. Axis of Havoc' v54.2 - 2 desperados, Psi, sub 2-0-3, Elite Defender + Elite Sniper + Cripple MOAB snipers, Druid 2-3-0, Prince of Darkness (hero: Psi; youtube description, 54.2). Source: https://www.youtube.com/watch?v=Q2IEAOx5pVo

  R6: desperado1 0-0-0 on the left (middle, range border touching the barrier) + desperado2 on the right (middle, range border touching the barrier); R9: sniper1 Strong right of the bottom bush; R10: dart1 on top; R14: Psi on Strong, bottom-left of desperado1; R15: dart2 on top (right of dart1); R16: sub1 on top of the pond, Strong; R17: sub1 1-0-0; R19: sub1 2-0-0 on First; R21: sub1 2-0-1 (Psi stun); R22: sniper1 1-0-0; R24: sniper2 on First; R27: sub1 2-0-2; R28-30: sniper2 0-0-1 -> 0-1-1 -> 0-2-1; R32-36: druid1 next to sniper1 -> 0-1-0 -> 1-2-0 -> 1-3-0 -> 2-3-0 (Strong, then First); R37-40: sniper1 1-0-2 -> 2-0-2 -> 2-0-3; R42-47: village1 0-0-2 -> 0-2-2, village2 0-0-2 -> 2-0-2; R46: sniper2 0-3-2; R49: Alch 3-0-0 for sniper2; R50: sniper1 2-0-4 First; R54: sniper2 0-4-2; R61: sniper2 0-5-2 (Elite Sniper) First; R71: sniper1 2-0-5 (Elite Defender); R73: Alch 4-0-0; R75-78: sniper3 3-2-0 -> 4-2-0 Strong; R79-86: wizard1 bottom-left of the pond 0-0-4 -> 1-0-4 -> 1-0-5 (Prince of Darkness) with Alch2 3-2-0; R88-90: glue1 0-1-3 -> 0-2-4 Strong next to the wizard; R98: sniper3 5-2-0; R99: Ice 2-4-0; R100: Tack 1-0-4 up top; Uses Psi stun/scream timing many times from R21 on - blind presses may waste them; otherwise bot-friendly (snipers, no aiming)

Other builds found:

- chimps: ApexZ 'BTD6 CHIMPS Quad Guide | Full Auto Start' - desperados + darts, Churchill, Druid 0-3-0, 10 Mermonkeys in the ... (hero: Churchill) - https://www.youtube.com/watch?v=6R0hyblW2_A

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC og: Sun Avatar 3-0-2 x2 + Pre-Emptive Strike 2-5-0 + Geraldo (v31.0); heroless LTC: Sentry Champion 5-2-0, Prince of Darkness 2-0-5, Elite Defender 0-2-5, Permanent Brew 5-0-2 (v49.3). LCC ~76,655 (v52.2 Capsen). => global towers (sniper/PoD/subs) and engineer sentries win; spikes at killzones are the usual black-border base.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 13 spots - dart, alchemist, sniper, village, wizard, bomb; hero quincy; 'chimps' (impoppable, chimps): 7 spots - desperado, sniper, dart, druid, wizard; hero psi.
Removables recorded: RemovableGazeboLeft ($1500, optional, ~R74), RemovableGazeboRight ($1500, optional, ~R74), RemovableGazeboTop ($1500, optional, ~R79), RemovableGazeboBottom ($1500, optional, ~R79).

**Sources:**

- https://www.bloonswiki.com/Quad - Quad - Bloonswiki
- https://bloons.fandom.com/wiki/Quad - Quad - Bloons fandom
- https://bloons.fandom.com/wiki/Quad/Strategies - Quad/Strategies - Bloons fandom
- https://www.youtube.com/watch?v=DAJAobKFCLE - BlueCliff - Quad Hard No MK (ft. Quincy)
- https://www.youtube.com/watch?v=6R0hyblW2_A - ApexZ - BTD6 CHIMPS Quad Guide Full Auto Start
- https://www.youtube.com/watch?v=Q2IEAOx5pVo - OneEyedDeacon - Quad Chimps ft. Axis of Havoc (v54.2)
- https://www.youtube.com/watch?v=23wqu8uv6Bg - NovaGoBoom - Quad Deflation (No Knowledge, Fully AFK)

### Workshop

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Bloons ride a conveyor 50% faster than normal and MOABs drop from a chute onto the last third of the belt. Spike Factories at the bottom-right exit are the core of every guide, with ninja + alchemist on the belt and villages.

**Lanes:** single.

**What the guides found** (detail from the sources):

- Conveyor: all bloons +50% speed while on the belt; Reverse Motor gizmo cancels this for 30 s (cooldown 30 s, full uptime possible). Source: https://www.bloonswiki.com/Workshop_(BTD6)
- Track Extensions gizmo: 4 small loops (at x~0.14 top, x~0.23 bottom, x~0.62 bottom, x~0.72 top) become part of the track for 20 s; regular path 6.8 -> 18.4 RBS with all extensions. Source: https://www.bloonswiki.com/Workshop_(BTD6)
- Gizmo prices: first activation of each is FREE; then Reverse Motor = 50*((round-1)//10+1) + 50*uses, Track Extensions = 100*((round-1)//15+1) + 150*uses (bloonswiki formula; fandom gives 100/250 base).
- Two entrances, one exit: bloons enter at the left edge (x=0, y~0.51) and exit at the right edge of the play field (x~0.85); MOAB-class drop down the blue chute at x~0.566 from the top (bot geometry 'MoabRamp'), so the MOAB route is only x 0.57-0.85 of the ...

**Towers that work:**

- spike 2-0-5 / 4-2-0 / 0-2-4: Wiki: fast bloons + single exit make spike factories very strong; Spiked Mines carries mid-game, Perma-Spike trivialises late ...
- hero Sauda: Wiki: Sauda's L7/L11 synergy with stunning glue; she can cover both the bloon belt and the MOAB drop
- glue 0-2-4 / 0-2-5 / 0-1-3: Stuns/slows MOABs on the short blimp route (MOAB Glue, Relentless/Super Glue).
- druid 1-3-0: Druid of the Jungle vines carry the early/mid game in both v53+ CHIMPS guides.
- alchemist 4-2-0: Brew on the exit spike factory and tack.
- village 2-0-2 / 4-0-2: Jungle Drums/commerce for spikes; Primary Mentoring for the Super Maelstrom tack.

**Avoid:** sniper (tables block sight across much of the map).

**Removable obstacles and map switches:**

- Reverse Motor (paid gizmo, not an obstacle) (free): First use FREE; then 50*((round-1)//10+1)+50*uses. Guides fire it on the hardest rounds: R4/R6 early rush (BlueCliff, Baumfall), R39->40 MOAB, R59->60 BFB .... Removes the conveyor's +50% bloon speed for 30 s (cooldown 30 s)
- Track Extensions (paid gizmo, a.k.a. Power Core before v14) (free): First use FREE; then 100*((round-1)//15+1)+150*uses. ApexZ: R10 when the last blue wave enters, and R100; BlueCliff: R39, R59, R62, R77. Adds 4 loops for 20 s: regular path 6.8 -> up to 18.4 RBS, MOAB path 5.7 -> 11.6

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff 'Workshop - Hard | No MK (ft. Quincy)' - Ninja 4-0-2 + Alch, two Spike Factories at the exit (0-2-4 + 4-2-0), villages, sniper, boomerangs (hero: Quincy; youtube description, old (~4 years, ~v25-28); Hard ends at R80). Source: https://www.youtube.com/watch?v=sukBmxvnnk4

  R3: Ninja 0-0-0; after the round Dart, targeting Strong; R4: author activates the REVERSE MOTOR during the rush (map gizmo, first use is free) - bot cannot click map objects yet; optional; R6: Ninja 0-0-1; R8: Ninja 1-0-1; R10: Ninja 1-0-2; R11: Ninja 2-0-2; R13 (after round): Quincy; R18: Ninja 3-0-2; R22 (after round): Spike Factory (a) near the exit - leave room for a second spike factory; R27 (after round): Alchemist (a) 2-0-1, targeting Strong (buffs the ninja); R29 (after round): Spactory(a) 0-0-2, targeting Close; R31: Spactory(a) 0-1-2; R34: Spactory(a) 0-1-3; R35 (after round): Alch(a) 3-0-1; R36: Spactory(a) 0-2-3; R39: Spactory(a) 0-2-4 as soon as affordable; after the round author activates Reverse Motor + Track Extension (gizmos) for R40; R40: Quincy level-3 ability at round start (blind press ok); R43: Ninja 4-0-2; R44 (after round): Alch(a) 4-0-1; R48 (after round): Spactory (b) 3-2-0 next to spactory (a); R49 (after round): Village (a) 2-0-0 covering Ninja and Quincy; R52 (after round): Village (b) 2-0-0 covering both spactories; R55 (after round): Spactory(b) 4-2-0 (Spiked Mines); R59 (after round): Alchemist (b) 4-0-1 (buffing the spactories); gizmos again for R60 (and Track Extension again before R63 and R78); R68 (after round): Sniper 4-0-2, targeting Strong (LOS: place with a clear view of the exit stretch); R73: Boomerang (a) 2-0-4 Strong, Village(a) 4-0-0; R75 (after round): Boomerang (b) 2-0-4 Strong; R80: win (Hard)

*chimps, used for the 'chimps' hints* - OneEyedDeacon 'Easiest Workshop Chimps w/ NO ABILITIES' v53.2 - 4 darts, Druid of the Jungle, Sauda, Perma-Spike 2-0-5 + Spiked Mines 4-2-0, Super Maelstrom tack (hero: Sauda; youtube description, 53.2). Source: https://www.youtube.com/watch?v=e2jZofvcaNQ

  R6: dart1 0-0-0 on Last (left, shoved next to the desk) + dart2 0-0-0 on Strong + dart3 0-0-0 right next to dart2 (precise; 'hair aligned with line'); R8: dart4 0-0-0 on Strong next to dart1; R10: druid1 0-0-0 under the track next to the hammer by the bottom machine ($240); R14: spike1 0-0-0 as bottom-right as possible (exit); R17: Sauda; R18: spike1 0-0-1; R19: spike1 0-0-2 (author uses MANUAL targeting - bot: use Close/Smart instead); R22: spike1 1-0-2; R23: druid1 0-1-0; R25: druid1 1-1-0; R26: druid1 1-2-0; R29: druid1 1-3-0; R32: village1 0-0-0 covering spike1; R35: village1 0-0-2; R36: spike1 1-0-3; R37: alch1 2-0-0 covering spike1; R38: alch1 3-0-0; R41: spike1 1-0-4; R43: alch1 4-0-0; R44: alch1 4-2-0; R46: village1 2-0-2; R48: spike2 3-0-0; R49: spike2 3-2-0; R50: village2 3-0-2; R51: village2 4-0-2; R52: tack1 2-0-3; R54: tack1 2-0-4; R59: spike2 4-2-0; R62: glue1 0-0-3 on Strong; R79: spike1 2-0-5 (Perma-Spike); R80: ice1 4-1-0; R81: alch2 4-0-0 covering tack1; R85: tack1 2-0-5; R86: alch2 4-2-0; R88: glue1 0-2-4; R97: ice1 5-2-0; No abilities and no gizmos used

Other builds found:

- chimps: ApexZ 'BTD6 CHIMPS Workshop | Full Auto Start' - 4 darts, druid 1-3-0, Sauda, Perma-Spike + Spiked Mines, Primary ... (hero: Sauda) - https://www.youtube.com/watch?v=J5pN-jskVLo
- abr: BlueCliff 'Workshop - Alternate Bloons Rounds | No MK (ft. Sauda)' - Sauda, Ninja 3-0-2 -> 4-0-2, Spactory 0-2-4 + ... (hero: Sauda) - https://www.youtube.com/watch?v=4NUXJx-hhZE
- chimps: unescaped 'Workshop CHIMPS Black Border Guide ft. NEW BUFFS for Benjamin' v42.2 - 4 darts WITH 1080p PIXEL SPOTS, Druid ... (hero: Benjamin) - https://www.youtube.com/watch?v=VlEiNksfE0E
- chimps: Bloons fandom 'Black Border CHIMPS strategy' - triple darts, Obyn, Ninja 4-0-2 + Alch, Sun Avatar 3-0-2 with commerce ... (hero: Obyn) - https://bloons.fandom.com/wiki/Workshop_(BTD6)/Strategies
- chimps: Baumfall 'Workshop Chimps Blackborder (Guide in Description)' - Pat Fusty + ninja/boomerang/spactories (ability-heavy) (hero: Pat Fusty) - https://www.youtube.com/watch?v=s8KRb8QXeMY

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC og: Geraldo + MOAB Domination 0-2-5 (v31.0); heroless LTC: MOAB Domination 0-2-5, Elite Defender 0-2-5, Prince of Darkness 0-2-5 (v49.3). LCC ~58,630 (v40.2). Listed CHIMPS start: '3 darts placements'. => ace/sniper/wizard tier-5s with 0-2-x crosspaths can solo it; spikes are the common defence.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 8 spots - ninja, dart, spike, alchemist, village, sniper, boomerang; hero quincy; 'chimps' (impoppable, chimps): 9 spots - dart, druid, spike, village, glue; hero sauda.

**Sources:**

- https://www.bloonswiki.com/Workshop_(BTD6 - Workshop (BTD6) - Bloonswiki
- https://bloons.fandom.com/wiki/Workshop_(BTD6 - Workshop (BTD6) - Bloons fandom
- https://bloons.fandom.com/wiki/Workshop_(BTD6 - Workshop (BTD6)/Strategies - Bloons fandom
- https://www.youtube.com/watch?v=sukBmxvnnk4 - BlueCliff - Workshop Hard No MK (ft. Quincy)
- https://www.youtube.com/watch?v=e2jZofvcaNQ - OneEyedDeacon - Easiest Workshop Chimps w/ NO ABILITIES (v53.2)
- https://www.youtube.com/watch?v=J5pN-jskVLo - ApexZ - BTD6 CHIMPS Workshop Full Auto Start
- https://www.youtube.com/watch?v=s8KRb8QXeMY - Baumfall - Workshop Chimps Blackborder

### Bloody Puddles

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Every round spawns from two far-apart entrances whose pair changes each round, on short lanes. Global or long-range damage that sees every lane: Advanced-Intel subs in the ponds with an alchemist, snipers; the jeep can be bought away around round 41.

**Lanes:** rotating.

**What the guides found** (detail from the sources):

- Spawn pairs repeat every 4 rounds: R1+4k: top of lane 1 + bottom of lane 5; R2+4k: top of lane 2 + bottom of lane 4; R3+4k: top and bottom of lane 3; R4+4k: top lane 2 + bottom lane 4 (fandom).
- MOAB-class on R40, R60, R80 and R100 enter from the bottom of the 2nd path (fandom); Boss Bloons always at the top of the middle path (wiki).
- Lane x-positions (screen fractions): lane 1 x~0.10-0.18, lane 2 x~0.21-0.30, lane 3 x~0.36-0.46, lane 4 x~0.52-0.61, lane 5 x~0.65-0.74.
- Ponds: left (x0.04-0.16, y0.30-0.50), middle-left (x0.24-0.34, y0.55-0.73, between lanes 2 and 3), top-right (x0.56-0.67, y0.04-0.20, between lanes 4 and 5), bottom-middle (x0.47-0.59, y0.78-0.96, between lanes 3 and 4).

**Towers that work:**

- sub 2-0-3 / 2-0-4 / 2-0-5: Airburst Darts is 'basically essential' early game; Advanced Intel lets pond subs hit every lane
- beast_handler x-x-4 Giant Condor: Moves blimps to one lane, turning two-spawn rounds into single-lane (wiki).
- desperado 0-0-0: Two desperados beat R6-7 with far less precision than dart+sub (wiki).
- sniper 2-5-0 / 4-0-2 / 0-2-5: Global range (use top-edge spots to avoid the jeep LOS); BlueCliff Hard wins with Elite Sniper + Maim MOAB
- alchemist 4-0-1 / 5-0-2: Brew on the pond subs / Perma-brew for sniper armies.
- bomb 2-4-0 / 0-2-4: MOAB Assassin spam black border (OneEyedDeacon v53.2) - ability-based.

**Removable obstacles and map switches:**

- Broken jeep (step 1) ($1000): BlueCliff Hard R41 (both steps together); OneEyedDeacon ABR R55; CHIMPS R93. Step 1 only makes a Chinook crash onto it (MORE line-of-sight blocking) - always buy step 2 right after
- Crashed chinook + jeep + rocks (step 2) ($500): Immediately after step 1. Clears line of sight for snipers and frees land between lanes 2-4

**Builds (in buy order):**

*hard, used for the 'hard' hints* - BlueCliff 'Bloody Puddles - Hard | No MK (ft. Quincy)' - Advanced-Intel subs + Alch, snipers (Elite Sniper 2-5-0, 4-0-2), buys the jeep removal (hero: Quincy; youtube description, old (~4 years, ~v25-28); Hard ends at R80). Source: https://www.youtube.com/watch?v=7LdEUBMskzk

  R3: Sub (mid, a); after the round Sub (top right); R4 (after round): Dart (top left); R6: Sub(mid a) 1-0-0; R8: Sub(mid a) 2-0-0; R10: Sub(mid a) 2-0-1; R14 (after round): author sells Dart (top left) [bot: keep]; Sub(mid a) 2-0-2; R15 (after round): Dart (top left); R18: Quincy - his range must cover the two bottom-right spawn points (bottom entrances of lanes 4 and 5); R19 (after round): Sniper (top), targeting Strong; R21: Sniper(top) 0-0-1; R22: Quincy ability; R23: Sniper(top) 1-0-1; after the round Dart (top left) 0-0-2; R27: Sub(mid a) 2-0-3; R32 (after round): Alchemist (mid, a) 3-0-0; R34 (after round): Alch 3-0-1; R35 (after round): Sub (top right) 2-0-1; R37: Sniper(top) 1-0-2; R38: Sub(mid a) 2-0-4; R39 (after round): Sub (top right) 2-0-2; R41: REMOVE THE VEHICLE OBSTACLE TWICE (jeep $1,000 -> chinook crashes, then $500 to clear jeep + chinook + rocks); R43 (after round): Alch 4-0-1; R44: Dart (mid) 0-0-2; R47: Sniper (mid) 1-3-0; R48: Sniper(mid) 2-3-0; R50: Sniper(mid) 2-4-0 ASAP (Supply Drop); R51: Sniper(top) 2-0-2; R53: Sniper(top) 3-0-2 (+ sniper ability); R54: Sub (top right) 2-0-3; R55: Village 2-0-0; R53-R78: author fires Supply Drop / Quincy abilities whenever up (bot: blind presses fine); R59: Sniper(top) 4-0-2; R62 (after round): author sells Sub (top right) for Sniper(mid) 2-5-0 Elite Sniper and sets it back to First [bot: no sell needed with Double Cash]; R63 (after round): Dart (top right) 0-0-2; R65: Sub (mid, b) 2-0-4; R75: Sub(mid a) 2-0-5; R77: Alch (mid, b) 4-0-2; R78: Sub (mid, c) 2-0-4; R80: Dart near the spawn point; win

*chimps, used for the 'chimps' hints* - Wiki CHIMPS start options: 2x 0-0-0 Desperados (less precise than dart+sub), then darts/snipers and Airburst subs (hero: any later; wiki, wiki text (current)). Source: https://www.bloonswiki.com/Bloody_Puddles

  R6: left Desperado top-left, shoved into the border of the LEFT lake - covers all left-side lanes; Follow up with 0-0-0 Darts and 0-0-0 Snipers; Airburst Darts sub (x-x-3) is 'basically essential' to beat it without micro; Fandom alternative (pixel-perfect): Sub in the bottom-middle puddle (top-left of its range through the jeep's front-wheel spokes) + Dart left (on Last for R6)

Other builds found:

- chimps: mdroueg 'round 21 airburst' Bloody Puddles CHIMPS start (BTD6 Index listed early game) - 2 subs + 2 darts with exact ... (hero: none early (sniper + engineer 'guess')) - https://www.youtube.com/watch?v=8Rdls9yEZL8
- chimps: OneEyedDeacon 'Bloody Puddles Chimps MOGGED by Sigma Assassinmaxxing Strat' v53.2 - desperados/darts/4 snipers, sub ... (hero: Striker Jones) - https://www.youtube.com/watch?v=kRpOZgXz1Eo
- abr: OneEyedDeacon 'EASY Bloody Puddles Alternate Bloons Rounds Strategy' v52.0 - dart/ninjas/sniper, Sauda above the truck ... (hero: Sauda) - https://www.youtube.com/watch?v=JjESGAUREkw

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC heroless/cheapest: Elite Defender 0-2-5, Permanent Brew 5-0-2, Sub Commander 2-0-5, Avenger 0-2-4, Bounty Hunter 2-4-0 (v49.3). LCC ~56,625 (v49.3 mdrouge). Listed CHIMPS starts: r21 airburst (reddit) and 'easier r21 airburst early' (mdroueg video). => perma-brewed global snipers + subs are the proven core.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 10 spots - sub, dart, sniper, alchemist, village; hero quincy; 'chimps' (impoppable, chimps): 4 spots - desperado, sub, sniper.
Removables recorded: RemoveableFakeHaha ($1000, optional, ~R41).

**Sources:**

- https://www.bloonswiki.com/Bloody_Puddles - Bloody Puddles - Bloonswiki
- https://bloons.fandom.com/wiki/Bloody_Puddles - Bloody Puddles - Bloons fandom
- https://bloons.fandom.com/wiki/Bloody_Puddles/Strategies - Bloody Puddles/Strategies - Bloons fandom
- https://www.youtube.com/watch?v=7LdEUBMskzk - BlueCliff - Bloody Puddles Hard No MK (ft. Quincy)
- https://www.youtube.com/watch?v=8Rdls9yEZL8 - mdroueg - roudn 21 airbustr
- https://www.youtube.com/watch?v=kRpOZgXz1Eo - OneEyedDeacon - Bloody Puddles CHIMPS MOAB Assassin (v53.2)
- https://www.youtube.com/watch?v=JjESGAUREkw - OneEyedDeacon - Bloody Puddles ABR (v52.0)

### Infernal

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** The easiest Expert map: two long lanes alternate by round, but space is tiny. The two middle pillars inside the waves reach both lanes; subs in both ponds, ace and village on the right island.

**Lanes:** alternating.

**What the guides found** (detail from the sources):

- Odd rounds spawn at the top-left and exit top-right; even rounds spawn bottom-left and exit bottom-right (fandom). Both lanes ~19.3-19.5 RBS. Sources: https://bloons.fandom.com/wiki/Infernal , https://btd6index.win/
- Placement islands (screen fractions): top-left island (0.24,0.21), top middle pillar inside the upper wave (0.43,0.32), bottom middle pillar inside the lower wave (0.43,0.70), bottom-right island (0.61,0.79), left-edge half island (0.04,0.53), right-edge half ...
- Water: top-right pond (0.62,0.20) and bottom-left pond (0.24,0.78), each fits up to 3 water towers (3 boats only if the first is put in the top-left corner of the bottom pool / bottom-right of the top pool). Source: https://bloons.fandom.com/wiki/Infernal
- Banana Farms only fit on the left/right edge islands; outside CHIMPS Pontoons on the ponds add farm space. Source: https://bloons.fandom.com/wiki/Infernal

**Towers that work:**

- sniper 0-5-2 / 0-2-5 / 0-2-4 / 0-3-2: Wiki: Elite Sniper + Elite Defender with Jungle Drums/Stronger Stimulant on the right island save into Perma-Brew, then spam ...
- heli 5-0-2 / 2-0-5: Alternating single lanes favour Heli Pilots; Comanche Commander or Apache Prime with Village + Alch on a side island ...
- alchemist 4-2-0 / 5-0-2: Brew/Perma-brew for the island cluster.
- ace 2-0-4: Global coverage from the right island (TNR Omega Hard).
- sub 2-0-2 / 2-0-4: Ponds are small; Advanced Intel subs cover both lanes (fandom CHIMPS start, TNR Omega Hard).
- ninja 4-0-2: Middle pillar ninja reaches both lanes (BlueCliff, TNR Omega Hard).

**Avoid:** farm (very little space).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - TNR Omega 'How to Beat Infernal on Hard with No MK' - Quincy + Ninja 4-0-2 + Alch on the middle pillars, Advanced-Intel subs in both ponds, Ace 2-0-4 + Village on the right island, Buccaneer 4-2-0 (hero: Quincy; youtube description, ~v30 (uploaded ~3 years before Oct 2026); Hard ends at R80). Source: https://www.youtube.com/watch?v=MrI-1g5eITI

  Quincy on the bottom part of the TOP middle pillar (inside the upper wave); Ninja 3-0-1 on the top part of the BOTTOM middle pillar; Sub (a) 2-2-0 in the left part of the top-right pond; Sub (b) 2-0-4 top-right of Sub (a) (same pond); Ninja 4-0-2; R40: Quincy level-3 ability (blind press ok); Alchemist (a) 4-2-0 beneath the Ninja (bottom pillar); Monkey Ace 2-0-3 at the very top of the RIGHT island; Village 2-2-0 beneath the Ace (right island); R60: Quincy level-3, then level-10 when the MOABs pop; R62: author sells Alch (a) [bot: skip the sell]; Monkey Ace 2-0-4; Alchemist (b) 4-2-0 beneath the Ninja; Buccaneer 4-2-0 top-right part of the bottom-left pond; Sub (c) 2-0-4 bottom-right part of the top-right pond; Sub (a) 2-3-0; Sub (d) 2-0-4 bottom part of the bottom-left pond; GG (R80); Order only; author gives no round numbers - buy in this order as cash allows

*chimps, used for the 'chimps' hints* - Hbomb 'Infernal CHIMPS Guide' build order (v23) + fandom Quincy start - Quincy/dart/sub start, Apache Prime 5-0-2 with Alch 4-2-0 + Village 2-2-0 on a side island, Wizard Lord Phoenix, Cripple MOAB, MOAB Eliminator (hero: Quincy; youtube description, 23.0 (old; still a valid bot-friendly comp: no aiming, heli has Pursuit)). Source: https://www.youtube.com/watch?v=VJWGAoCqXus

  Start (fandom): Quincy on the small island in the middle of the BOTTOM wave (reaches the upper path too); After R6 (fandom): Dart 0-0-0 on the small island in the middle of the UPPER wave; for R7 switch it to Strong after the 2nd blue wave (bot: set Strong); Sub in the top-right pond -> 2-0-2 (fandom: by ~R20 the rest is easy); Hbomb order: Quincy, Dart 0-0-0, Sub 2-0-2, Sub (second) 2-0-0, Dart 0-0-2, Sniper 1-0-0 (Strong), Sub (second) 2-0-2, Village 0-0-0; Heli Pilot 2-0-0 (Pursuit) on a side island, Alch 3-0-0, Heli 2-0-2, Village 2-2-0, Heli 3-0-2, Alch 4-2-0, Heli 4-0-2, Wizard 0-2-5 (Wizard Lord Phoenix), Heli 5-0-2 ...; Wiki tip: Apache Prime fits with an Alchemist and Village on the left island; fandom: you can fit Alch + Heli pad + Village on either side island (place them carefully; Quincy abilities on R49/R76/R78 help (blind press)

Other builds found:

- hard: BlueCliff 'Infernal - Hard | No MK (ft. Quincy)' - Quincy, Ninja 4-0-2 + Alchs, boat 1-4-0 for R40, then Elite Sniper ... (hero: Quincy) - https://www.youtube.com/watch?v=5vrEQFKBWmI
- magic_only: BlueCliff 'Infernal - Magic Monkeys Only | No MK (ft. Quincy)' - Ninja 4-0-2 + Alch, then Wizard 4-0-2 / 0-4-2 Phoenix ... (hero: Quincy) - https://www.youtube.com/watch?v=_mXriemvP3A
- double_hp: BlueCliff 'Infernal - Double HP MOABs | No MK (ft. Quincy)' - Ninja 4-0-2 + Alchs, Monkey Pirates boat -> 0-5-2 Pirate ... (hero: Quincy) - https://www.youtube.com/watch?v=tInLGP89gEE
- abr: BlueCliff 'Infernal - Alternate Bloon Rounds | No MK (ft. Quincy)' - Ninja 4-0-2 + Alch, boat 0-4-1 for R40, Elite ... (hero: Quincy) - https://www.youtube.com/watch?v=vTCfikbP5ak
- impoppable: BlueCliff 'Infernal - Impoppable | No MK (ft. Quincy)' - two Advanced-Intel subs 2-0-4, Elite Sniper 2-5-0, Ace 2-0-5 ... (hero: Quincy) - https://www.youtube.com/watch?v=z6sM1kPjOks

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC og: Perma Charge 0-5-2 + Geraldo (v31.0); heroless LTC: Pop and Awe 2-5-0 (mortar) + M.A.D 2-5-0 (dartling) (v50.2). LCC ~42,045 (v49.3 Gijssie). Listed CHIMPS starts: 0-1-0 Engineer start (reddit), Boomer into r18 Airburst (reddit), Mortar start (video). => global/aimed military towers dominate; for the bot use snipers/heli/ace instead of mortar/dartling.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 8 spots - ninja, sub, alchemist, ace, village, buccaneer; hero quincy; 'chimps' (impoppable, chimps): 8 spots - dart, sub, sniper, heli, village, wizard; hero quincy.

**Sources:**

- https://www.bloonswiki.com/Infernal - Infernal - Bloonswiki
- https://bloons.fandom.com/wiki/Infernal - Infernal - Bloons fandom
- https://bloons.fandom.com/wiki/Infernal/Strategies - Infernal/Strategies - Bloons fandom
- https://www.youtube.com/watch?v=MrI-1g5eITI - TNR Omega - How to Beat Infernal on Hard with No MK
- https://www.youtube.com/watch?v=5vrEQFKBWmI - BlueCliff - Infernal Hard No MK (ft. Quincy)
- https://www.youtube.com/watch?v=_mXriemvP3A - BlueCliff - Infernal Magic Monkeys Only No MK (ft. Quincy)
- https://www.youtube.com/watch?v=tInLGP89gEE - BlueCliff - Infernal Double HP MOABs No MK

### Flooded Valley

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Bloons walk along the top of a dam that blocks sight, so towers on the big left land hit nothing. Everything goes in the water at the dam's two bends: mermonkeys, subs, a buccaneer to Carrier Flagship, ice monkeys, Silas.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- Two simultaneous, fully overlapping lanes on the dam (top->bottom and bottom->top); leaks are hard to see.
- Dam = line-of-sight wall for land towers on the left land. Exceptions: towers on the right-most raised rocks near the top-left and bottom-left of the land (v23.0 raised them
- No towers can be placed on the dam itself.
- Water on the right (x ~0.47-0.85): the best spots are in the water hugging the bottom bend (~0.52, 0.70) and the top bend (~0.49, 0.16) of the track, and the middle bulge (~0.55-0.58, 0.43-0.64).

**Towers that work:**

- mermonkey 0-0-0 x2 at R6 -> 3-0-1 -> 4-0-1 Abyssal Warrior -> 5-0-1 ...: Water tower that sees the track; current no-micro CHIMPS black-border guides open with two of them (one per bend).
- sub 0-0-0 start; 2-0-4/2-0-5 Sub Commander or 4-x-x Bloontonium ...: Cheap water tower that reaches both overlapping lanes from the bend; Submerge and Support handles camo through walls.
- buccaneer 2-2-0 -> 3-2-0 Destroyer -> 5-2-0 Carrier Flagship: Main water DPS; Carrier Flagship planes cover the map and its decks are placement platforms.
- ice 4-1-0 Embrittlement -> 5-2-0 Super Brittle: Ice Monkeys can stand on water next to the track; immune to the dam problem.
- village 2-0-2 -> 4-0-2 Primary Mentoring: Buff for the water cluster; must stand on Silas/Arctic-Wind ice (land tower).
- spike 1-4-0 Spike Storm -> 2-5-0 Carpet of Spikes: Late-game cleanup; spike placement ignores the dam wall.

**Avoid:** dart (land towers on the left cannot see over the dam); tack (blocked by the dam); bomb (blocked by the dam); farm (uses land that is useless otherwise; never in CHIMPS).

**Removable obstacles and map switches:**

- Dam breach (secret flood button) ($5000): Never for normal play.. Floods the left land; every non-amphibious tower on low ground is sold. Players and fandom say it is not worth it (enough water already

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Hard: run the G-Horizon water build (no abilities needed), stop at R80 (hero: Silas; inferred, 53). Source: https://www.youtube.com/watch?v=68Jbc9m1zts

  R1-R5 (Hard gives more starting cash): Mermonkey at the bottom bend, then Mermonkey at the top bend as soon as affordable; Then Silas, Mer upgrades to 1-0-1, Buccaneer 2-2-0 -> 3-2-0, Mer1 3-0-1 -> 4-0-1 by ~R40; Ice1 4-1-0 before R40 (lead/MOAB), Village 2-0-2 -> 4-0-2 inside Silas aura, Ice2 0-1-4; Mer1 5-0-1 Lord of the Abyss and Spike Storm 1-4-0 by ~R70; Buccaneer 5-2-0 if cash allows

Other builds found:

- chimps: G-Horizon 'Flooded Valley CHIMPS Easy Guide (No Abilities/Micro)' - 2 Mermonkey start, Silas, Destroyer, Lord of the ... (hero: Silas) - https://www.youtube.com/watch?v=68Jbc9m1zts
- chimps: bloon.games written CHIMPS route (Silas, 2 Subs, Mermonkey, Buccaneer -> Carrier Flagship, Lord of the Abyss) (hero: Silas) - https://bloon.games/how-to-beat-chimps-on-flooded-valley/
- chimps: Tiggy Gaming written guide (Buccaneer start, Sub, Brickell, Carrier Flagship, Glaive Lord) (hero: Admiral Brickell) - https://www.youtube.com/watch?v=5x1IfnoZy2c

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC (least towers): Carrier Flagship 5-2-0 + Geraldo (v44); heroless: Carrier Flagship 5-0-2 + Popseidon 0-5-2 + Pre-Emptive Strike 0-5-2. 2TC: Geraldo + Carrier Flagship / Aircraft Carrier / Pirate Lord. LCC ~$59k (v51.2). CHIMPS start listed: 'Single Sub at Bottom' (youtu.be/if72mnfqyrg). => Water towers (Buccaneer/Sub/Mermonkey) + Geraldo are the proven core.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 6 spots - mermonkey, buccaneer, ice; hero silas.
Removables recorded: RemovablePlate ($5000, never).
Model gap: Silas's ice on the water lets land towers (village, spike) stand there; the model marks it illegal.

**Sources:**

- https://www.bloonswiki.com/Flooded_Valley - Bloons Wiki - Flooded Valley
- https://bloons.fandom.com/wiki/Flooded_Valley - Fandom - Flooded Valley
- https://bloons.fandom.com/wiki/Flooded_Valley/Strategies - Fandom - Flooded Valley/Strategies
- https://www.bloonswiki.com/Silas_(BTD6 - Bloons Wiki - Silas
- https://www.youtube.com/watch?v=68Jbc9m1zts - G-Horizon - Flooded Valley CHIMPS Easy Guide (U53)
- https://www.youtube.com/watch?v=IzjGW0sUoic - ApexZ - BTD6 CHIMPS Flooded Valley Full Auto Start
- https://www.youtube.com/watch?v=SLFBUvLkDPo - G-Horizon - Flooded Valley CHIMPS Easy Guide (U52)

### Ravine

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Two entrances alternate and each splits in two, giving four lanes behind bridges and trees; the river is too low for water towers. Cheap darts where one reaches two lanes, the real defence in the big bottom-left area where the exits converge, spikes at the exits, aces later.

**Lanes:** alternating.

**What the guides found** (detail from the sources):

- Lanes (bot 16:10 fractions): LEFT entrance (0.36,0.0) -> lane L-a down the left side (0.21,0.21)->(0.16,0.44)->(0.09,0.68)-> exits left edge ~y0.83; lane L-b (0.49,0.21)->(0.44,0.50)->(0.42,0.69)->(0.47,0.86)-> exits bottom ~x0.52.
- Odd rounds use the right entrance, even rounds the left entrance; both splits are active together.
- Usable ground (bot grid): big bottom-left area (0.02-0.33, 0.64-0.94) - touches L-a, R-b and R-a (best: (0.152,0.641), (0.30,0.777)); fork between the left entrance's two lanes (0.31-0.45, 0.10-0.27)
- Line of sight: bridge walls + trees block most towers; water in the river is too low (water towers only via Carrier planes, First Strike, Monkey Pirates ability, Bloontonium range, or 2-3-0 Ballistic Missile with Advanced Intel).

**Towers that work:**

- dart 0-0-0 x3-5 early; 0-3-2 Triple Shot; 4-0-2 Juggernaut: Cheap starters placed where range covers two lanes.
- ace 2-0-3 -> 2-0-4; 4-0-0 -> 5-2-0 Sky Shredder: Unaffected by line of sight; Sky Shredder is the standard win condition.
- druid 1-3-0 Druid of the Jungle (Strong): Jungle vines grab bloons regardless of walls; early-mid backbone in OneEyedDeacon routes.
- spike 0-0-2 Smart -> 1-0-2 -> 3-0-2 Spiked Balls (-> 4-0-2): Exit guards on the short lanes.
- glue 1-1-0 early; 0-2-3/0-2-4; Relentless Glue: Hold blimps on short diverging lanes.
- alchemist 3-2-0 / 4-2-0: Buffs aces and spikes.

**Avoid:** sub (the river is too low to shoot from); buccaneer (same as subs); tack (walls and four lanes); heli (players re-aim it every round).

**Removable obstacles and map switches:**

- Sword in the stone (one-shot easter-egg attack, free) (free): CHIMPS: click 23 times during R6, the 24th on R7 as the second/last green bloon passes the bridge. Hard/other modes: whenever a leak is imminent (or never).. Pops 3 layers of the strongest bloon on screen; the only way to pass CHIMPS R6+R7 (version 24.0 change).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Hard: Etienne + darts + Druid of the Jungle + Spikes + Aces -> Sky Shredder (OneEyedDeacon Etienne route without sword/heli micro) (hero: Etienne; inferred, 50.2 base route). Source: https://www.youtube.com/watch?v=OpHwKwqMcOY

  Pre-R1 (Hard cash): Dart A bottom-left (Strong), Dart B under the sword (Last), Dart C bottom-left lower; R2-R4: Dart D in the right fork.; R5-R10: Etienne in the bottom-left area; Dart A 0-2-0 -> 0-3-0 -> 0-3-2; Dart C 0-2-0 -> 0-3-2.; R11-R20: Druid in the left fork 0-1-0 -> 1-1-0 -> 1-3-0 (Strong); Spike1 near the left exits 0-0-2 (Smart); Glue1 1-1-0 (Strong) in the left fork.; R20-R30: Spike2 at the bottom exit 0-0-2 (Smart); Village 0-0-2 -> 2-0-2 next to Etienne; Dart B/Dart D 0-3-0 for camo/leads.; R30-R40: Ace1 0-0-3 -> 2-0-3 (camo via Village/Etienne lvl 8); Alchemist 3-2-0 next to Ace1; Spikes 1-0-2 -> 3-0-2 before R40.; R40-R60: Ace2 3-0-0 -> 4-0-0 in Alch range; Bombs 4-2-0 next to the spikes; Glue 0-2-3.; R60-R80: Ace2 5-2-0 Sky Shredder; Spikes 3-0-2 -> 4-0-2 if cash; 2-0-4 MOAB Press boomerangs before R76-R80.; Abilities: Etienne Drone Swarm/UCAV can be pressed blindly; the sword (24 clicks) is a free emergency button if the lead wires it.

Other builds found:

- chimps: OneEyedDeacon 'Ravine Chimps is SIMPLE with Etienne + Sky Shredder' (v50.2) - needs the sword + heli micro (hero: Etienne) - https://www.youtube.com/watch?v=OpHwKwqMcOY
- chimps: ApexZ 'Ravine | Full Auto Start' - 6 darts, Geraldo items, Druid, Aces, sword (hero: Geraldo) - https://www.youtube.com/watch?v=drVwDHoVG6M
- chimps: OneEyedDeacon 'DOMINATE Ravine Chimps' (v54.1) - Ezili, darts, druids, Wizard Prince of Darkness, Spiked Balls (hero: Ezili) - https://www.youtube.com/watch?v=JtP8VQc5Leo

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): No LTC with a hero listed; heroless LTC: Bounty Hunter 2-4-0 + Golden Justice 2-5-0 + Elite Defender 0-2-5 + MOAB Press 0-2-4 + Bloon Crush 5-2-0 (v49.3). LCC ~$54k (v40.2). No 2TC and no CHIMPS start recorded (map is too hard for 2 towers). => Desperado/Engineer/Bomb late game also proven; Sky Shredder/PoD per wiki.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 16 spots - dart, druid, spike, glue, ace, alchemist, village, bomb, boomerang; hero etienne.

**Sources:**

- https://www.bloonswiki.com/Ravine - Bloons Wiki - Ravine
- https://bloons.fandom.com/wiki/Ravine - Fandom - Ravine
- https://bloons.fandom.com/wiki/Ravine/Strategies - Fandom - Ravine/Strategies
- https://www.youtube.com/watch?v=OpHwKwqMcOY - OneEyedDeacon - Ravine Chimps is SIMPLE with Etienne + Sky Shredder (v50.2)
- https://www.youtube.com/watch?v=i5YIBkeTklg - OneEyedDeacon - UPDATED EASY Ravine Chimps w/ Geraldo + Sky Shredder (v51.2)
- https://www.youtube.com/watch?v=JtP8VQc5Leo - OneEyedDeacon - DOMINATE Ravine Chimps (v54.1)
- https://www.youtube.com/watch?v=drVwDHoVG6M - ApexZ - BTD6 CHIMPS Ravine Full Auto Start

### Sanctuary

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Towers stand only on round platforms that move every round, so a short-range tower loses its lane. Use global or seeking towers on the moving platforms and put Perma-Spike, village and alchemist on the bottom-middle platform, which barely moves.

**Lanes:** merging.

**What the guides found** (detail from the sources):

- Platform motion (decoded from the map data, units ~0.0028 screen-x per unit): statue platform (top centre, Psi statue + two tiny ponds) slides horizontally between x-27, 0, +27 units (4-round cycle)
- Reference layout in screen fractions (platforms at their map-load position): statue (0.27-0.40, 0.03-0.27), middle-left (0.23-0.35, 0.40-0.55), middle-right (0.50-0.62, 0.40-0.55), bottom-left (0.19-0.28, 0.73-0.88), bottom-right (0.57-0.67, 0.73-0.88) ...
- Lanes (bot fractions): left entrance (0.16,0.0)->(0.29,0.28)->(0.42,0.42); right entrance (0.69,0.0)->(0.56,0.28)->(0.44,0.42); merged central lane down to (0.43,0.63)
- The Psi-statue platform has two tiny ponds (one Sub/Buccaneer each).

**Towers that work:**

- sniper 1-0-2 / 0-2-2 (Strong): Infinite range - platform motion does not matter.
- desperado 0-0-0 x2 at R6; later 5-2-0 / 2-4-0: Both recent no-micro guides open with two Desperados (middle-left and middle-right platforms).
- wizard 2-0-1 -> 3-0-2 -> 4-0-2 -> 5-0-2 Archmage: Guided Magic seeks bloons wherever the platform drifts.
- spike 1-0-3 -> 1-0-5 Perma-Spike (or 2-0-5) on the bottom-middle ...: Catches all leaks at the central split; makes late game trivial.
- village 0-0-2 -> 2-0-2 / 4-0-2: Camo + range for the bottom-middle cluster.
- alchemist 3-0-0 / 4-0-0 Stronger Stimulant: Buffs the Perma-Spike.

**Avoid:** tack (short range on a moving platform); ice (short range on a moving platform); farm (no room).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Hard: v53 Perma-Spike route, stop at R80 (hero: Obyn Greenfoot; inferred, 53.0). Source: https://www.youtube.com/watch?v=auCq92xN0nk

  Before R1: two Desperados (middle-left/right platforms) + Sniper on the bottom-right platform; second Sniper by ~R5.; Then Obyn, Wizard -> 2-0-2 -> 3-0-2 -> 4-0-2, Village 0-0-2 + Perma-Spike route + Alch on the bottom-middle platform, Glue 4-2-0, Wizard 5-0-2 by ~R70.; Extra safety for a bot: 1-2 more Snipers (infinite range, 0-2-2/1-0-2) on the bottom-left/right platforms instead of anything short-range.

Other builds found:

- chimps: OneEyedDeacon 'Sanctuary Chimps is EASY with Permaspike' (v53.0) - Obyn, Desperados, Snipers, Archmage, Perma-Spike ... (hero: Obyn Greenfoot) - https://www.youtube.com/watch?v=auCq92xN0nk
- chimps: ApexZ 'Sanctuary | Full Auto Start' - Silas, Desperados, Snipers, MOAB-Press boomerang, 5 Ice Monkeys (Absolute Zero ... (hero: Silas) - https://www.youtube.com/watch?v=YcYjHojsqnM
- chimps: OneEyedDeacon 'VERY EASY Sanctuary' (v50.0) - Striker Jones + Bomb Blitz (Bomb Blitz later nerfed) (hero: Striker Jones) - https://www.youtube.com/watch?v=NBBIRhJve8M

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Perma Charge 0-5-2 + Wizard Lord Phoenix 1-5-0 + Geraldo (v49.3); heroless: Archmage 5-0-2 + Elite Defender 0-2-5 + Base Boomer 2-0-2 + Permanent Brew 5-2-0. LCC ~$61k (v40.2). CHIMPS start in the Index: 'Sniper + 3 Darts into Dartling into Heli' (Bvx4KZGPruM). => Archmage, Perma Charge boomerang, Phoenix, Sniper/Heli all work.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 5 spots - sniper, village, alchemist, glue; hero obyn.

**Sources:**

- https://www.bloonswiki.com/Sanctuary - Bloons Wiki - Sanctuary
- https://bloons.fandom.com/wiki/Sanctuary - Fandom - Sanctuary
- https://bloons.fandom.com/wiki/Sanctuary/Strategies - Fandom - Sanctuary/Strategies
- https://www.youtube.com/watch?v=auCq92xN0nk - OneEyedDeacon - Sanctuary Chimps is EASY with Permaspike (v53.0)
- https://www.youtube.com/watch?v=NBBIRhJve8M - OneEyedDeacon - VERY EASY Sanctuary Chimps (v50.0)
- https://www.youtube.com/watch?v=YcYjHojsqnM - ApexZ - BTD6 CHIMPS Sanctuary Full Auto Start
- https://www.reddit.com/r/btd6/comments/ntkpd4/pspike_placement_on_new_map_hits_100_of_bloons_on/ - r/btd6 - Pspike placement on new map hits 100% of bloons

### Dark Dungeons

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Six walled rooms and four lanes at once (three bloon lanes from the bottom, MOABs alternating with a long top lane); the middle lane sits lower so other rooms cannot see it. A cheap dart in each bottom room early, per-room defence, Spike Factories at the exits.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- Lanes (bot 16:10 screen fractions): LEFT bloon lane enters bottom (0.12,0.96), S-bends in the bottom-left room ((0.13,0.93)->(0.21,0.93)->(0.21,0.81)->(0.04,0.81)->(0.03,0.69)->(0.12,0.68)) then runs straight up x=0.12 to the top exit, crossing the top MOAB ...
- Non-MOAB bloons roughly cycle left->middle->right; MOABs alternate middle-bottom then top-right entrance.
- Middle lane is at a lower elevation: most towers cannot see up/down the stairs or the central ledge.
- Sludge pool in the bottom-right room (~0.68-0.79, 0.74-0.88): water towers fit there (Sub/Mermonkey; max 6 subs). Water towers barely see out; Mermonkey there is decent (Trance reaches both MOAB entrances with range buffs).

**Towers that work:**

- dart 0-0-0 x3 at R6 (one per bottom room); 0-3-2 Triple Shot: Cheap per-room starters; Juggernaut balls bounce around the walled rooms.
- spike 1-0-3/1-0-4 or 3-0-2/4-0-2 Spiked Balls/Mines at each exit: Exit guards for random leaks; only 2 MOAB exits need heavy ones.
- tack 2-0-3 -> 2-0-4 Overdrive -> 2-0-5 The Tack Zone: MOAB lanes have tight bends; best right below the middle lane's 2nd turn or right above the top MOAB lane's 1st turn.
- ice 4-1-0 Embrittlement -> 5-2-0 Super Brittle: Boosts tack/dart damage on blimps.
- glue 2-1-0, 0-2-3/0-2-4 (MOAB Glue/Relentless): Hold blimps in the kill-zones.
- alchemist 3-0-0 / 3-2-0 / 4-2-0: Buffs spike/tack/dart groups.

**Avoid:** sniper (walls limit its sight lines); buccaneer (only the small sludge pool).

**Removable obstacles and map switches:**

- Spike-trap torches (2) (free): CHIMPS R7 (right torch), R15/R36/R39/R43 (both) in OneEyedDeacon's routes; any round with a leak scare. 60 s cooldown each.. Free 5-damage stun spikes at the two top crossings; needed by most expert CHIMPS starts except ApexZ's no-trap route.
- Dungeon Statue (activate) ($30000): Not recommended (fandom: weak for its price); upgrades $50k / $100k.. Seeking magic bolt; struggles vs super ceramics and BFB swarms.

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Hard: ApexZ no-ability route, stop at R80 (hero: Silas; inferred, ~v55). Source: https://www.youtube.com/watch?v=wqGrbHhDv3U

  Use the ApexZ CHIMPS order (above) with the same placements; with Hard's starting cash place all three R6 darts before R1 plus Dart4/Dart5 by R5.; Priority by R40: Dart1 0-3-2, Dart2 0-3-0, Dart4 4-0-2, Spikes at all three exits, Alch1, Ice1 4-1-0 before the R40 MOAB.; By R80: Tack1 2-0-5 + Ice1/Ice2 Super Brittle + Juggernauts in every side room + Village/Alch buffs.

Other builds found:

- chimps: ApexZ 'Dark Dungeons | Full Auto Start' - no abilities, no traps (darts, Silas, glue, spikes, Juggernauts, Tack Zone ... (hero: Silas) - https://www.youtube.com/watch?v=wqGrbHhDv3U
- chimps: OneEyedDeacon 'CLASSIC and EASY Dark Dungeons w/ Sauda' (uses torch traps + Sauda abilities) (hero: Sauda) - https://www.youtube.com/watch?v=zVL8Gs1MyLw

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Base Super 0-0-0 + 2x Dark Knight (2-0-3 / 0-2-3) + Elite Defender 2-0-5 + Geraldo lvl20 (v44); heroless: Triple Shot 0-3-2, Juggernaut 5-2-0, Ultra-Juggernaut 4-0-2, Elite Defender 0-2-5, Jungle's Bounty 2-4-0, Carpet of Spikes 2-5-0, Bomb Blitz 0-2-5 (v49.3). LCC ~$39.5k (v52.2). => Juggernaut darts, Sentry/Elite Defender engineers and spike factories are the proven pieces

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 23 spots - dart, sub, glue, spike, alchemist, village, ice, tack, mermonkey; hero silas.

**Sources:**

- https://www.bloonswiki.com/Dark_Dungeons - Bloons Wiki - Dark Dungeons
- https://bloons.fandom.com/wiki/Dark_Dungeons - Fandom - Dark Dungeons
- https://bloons.fandom.com/wiki/Dark_Dungeons/Strategies - Fandom - Dark Dungeons/Strategies
- https://www.youtube.com/watch?v=wqGrbHhDv3U - ApexZ - BTD6 CHIMPS Dark Dungeons Full Auto Start
- https://www.youtube.com/watch?v=zVL8Gs1MyLw - OneEyedDeacon - CLASSIC and EASY Dark Dungeons Chimps w/ Sauda (v50.2)
- https://www.youtube.com/watch?v=P-pNLDMPspc - OneEyedDeacon - Arctic Knight Spam (v51.2)
- https://www.youtube.com/watch?v=GE0HFZiU8oY - OneEyedDeacon - Dark Dungeons Chimps Made SIMPLE (v49.2)

### Glacial Trail

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** One long lane, but every tower except ice monkeys, Silas and Dan freezes for 2 rounds every 10 rounds counted from its placement round. Build round ice monkeys and Silas, spread placements over different rounds, Perma-Spike at the end.

**Lanes:** single.

**What the guides found** (detail from the sources):

- Freeze rule: a tower placed on round r is frozen on rounds r+9, r+10, r+19, r+20, r+29, r+30 ... (placed R1 -> frozen R10-11, R20-21...; placed R5 -> R14-15, R24-25).
- Frozen towers still give passive buffs (Village, Striker Jones); Benjamin/Merchantman still pay end-of-round cash; Banana Farms produce nothing while frozen; Monkey Banks keep accruing (collect after thaw); Heli Pilots stop moving; Aces fly but do not shoot.
- Placement-round planning (wiki): place most late-game towers on a round ending in 2 or 4 (frozen x1-x2 / x3-x4, so R95-R100 all active); a lead popper on a round ending in 2; a camo detector on a round ending in 0.
- Bot implication: before clicking a tower for an upgrade/targeting, check whether it is in its frozen window; postpone instead of clicking a frozen tower (the click does nothing). Abilities of frozen towers cannot be pressed.

**Towers that work:**

- ice 3-1-0 -> 4-1-0 Embrittlement -> 5-2-0 Super Brittle: Immune to the freeze; the backbone of every recent no-micro CHIMPS guide.
- spike 2-0-3 -> 2-0-4 -> 2-0-5 Perma-Spike (Smart Spikes ...: Spike piles last 4 rounds, longer than a 2-round freeze, so the defence keeps working while the factory is frozen.
- dart 0-0-0 early; 4-x-x / 5-0-0 Juggernaut at the end of the ...: Juggernaut balls bounce off the many ice walls; cheap early pops.
- ninja 1-0-0 early: Early camo/seeking pops in the G-Horizon/ApexZ start.
- heli 2-x-x (Pursuit) or higher: Single lane + global movement; place on the big far land. Do not make it the only DPS (it freezes too).
- village x-x-x: Wiki: a Village/Alchemist fits on the bottom-right glacier in range of one tower near the path.

**Avoid:** farm (produces nothing while frozen); sub (water too low); buccaneer (water too low); sniper (ice sight blockers around the edges).

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Hard: G-Horizon ice/Perma-Spike route, stop at R80 (hero: Silas; inferred, 53). Source: https://www.youtube.com/watch?v=Hv8M3AOfwS0

  Same tower list and order as the CHIMPS route, bought as soon as affordable (Double Cash).; Keep placements on different rounds: never place more than 2 non-ice towers on the same round; Optional extra DPS that does not hurt: 1-2 Heli Pilots 2-x-x on the far top-right land, placed on rounds that differ from the Spike Factory's.

Other builds found:

- chimps: G-Horizon 'Glacial Trail CHIMPS Easy Guide (No Abilities/Micro)' - Silas, 3 Ice Monkeys, Perma-Spike, Carpet of Spikes (hero: Silas) - https://www.youtube.com/watch?v=Hv8M3AOfwS0
- chimps: ApexZ 'Glacial Trail | Full Auto Start' (same route as G-Horizon) (hero: Silas) - https://www.youtube.com/watch?v=L7JnwJOokNc
- chimps: bloon.games written CHIMPS route (Sauda, Juggernaut, Perma-Spike, Sentry Champion, Mortar) (hero: Sauda) - https://bloon.games/how-to-beat-chimps-on-glacial-trail/

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Monarch of Storms 5-0-2 + Geraldo (v44); heroless Pop and Awe 0-5-2 + Lord of the Abyss 5-0-2 + Carpet of Spikes 2-5-0; cheapest Glaive Lord 5-0-2 + Geraldo. 2TC with Geraldo: Pop and Awe, Popseidon, Glaive Lord, Monarch of Storms, Perma Charge, Sentry Champion, Spirit of the Forest, Blooncineration. LCC $50,530 (v40.2). => many single tier-5s work on this single lane

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 4 spots - dart, ninja, ice; hero silas.
Model gap: Only about five legal spots near the track; guides fit about eight towers near the loops.

**Sources:**

- https://www.bloonswiki.com/Glacial_Trail - Bloons Wiki - Glacial Trail
- https://bloons.fandom.com/wiki/Glacial_Trail - Fandom - Glacial Trail
- https://www.youtube.com/watch?v=Hv8M3AOfwS0 - G-Horizon - Glacial Trail CHIMPS Easy Guide (U53)
- https://www.youtube.com/watch?v=Pb5TtbZ1gtA - G-Horizon - Glacial Trail CHIMPS Easy Guide (U52)
- https://www.youtube.com/watch?v=L7JnwJOokNc - ApexZ - BTD6 CHIMPS Glacial Trail Full Auto Start
- https://bloon.games/how-to-beat-chimps-on-glacial-trail/ - bloon.games - How to Beat CHIMPS on Glacial Trail
- https://www.pocketgamer.com/bloons-td-6/glacial-trail-guide - Pocket Gamer - Glacial Trail guide

### Tricky Tracks

*Expert map. Bot record (logs/results.jsonl, 2026-10-22): not played yet.*

**Key insight.** Six short lanes run at once on three diagonal tracks and bloons stop briefly in the middle of each. Starters go on the strips between tracks near the middle, where one tower reaches both lanes of a track; mermonkeys, Etienne, boomerangs, overdrive tacks late.

**Lanes:** simultaneous.

**What the guides found** (detail from the sources):

- Lane centres / stop points (bot 16:10 fractions): top track lanes 'Path 3' and 'Path 4' around (0.30-0.33, 0.31-0.34); middle track 'Path 1' and 'Path 2' (also the boss path) around (0.40-0.43, 0.48-0.51)
- Strips between the tracks: between top and middle tracks e.g. (0.33,0.43), (0.30,0.50); between middle and bottom tracks e.g. (0.45,0.58), (0.43,0.64); below the bottom track e.g. (0.58,0.73). A range-32 dart at (0.329,0.428) reaches lanes 3,4,1
- Train (station lights at ~(0.47,0.23), (0.57,0.39), (0.68,0.55) in the bot window, one per track): click a light -> pay $2,500 (+$2,500 every further use, no limit) -> a train runs down that track, one-shots non-MOAB bloons, 10 damage + 10 s stun to ...
- Bananas Farms take less space here (farms can squeeze onto the tracks a little) - lots of room for farms on Hard.

**Towers that work:**

- mermonkey 0-0-0 x6 early; 0-0-2, 3-0-2/4-0-2, 0-3-2: Range 40 from a between-track strip reaches 4 lanes; core of both ApexZ and OneEyedDeacon routes.
- hero Etienne: His global range buff lets limited-range towers reach more of the three tracks (wiki); drone swarm/UCAV.
- wizard 1-0-0 -> 3-2-0 -> 4-2-0 -> 5-2-0 Archmage: Seeking attacks across tracks; with range buffs (wiki).
- desperado 0-3-0 Deadeye: Range buff for limited-range towers (wiki).
- sniper 1-0-2 -> 3-0-2 -> 4-0-2: Global; stand it on the parked train (high ground).
- tack 2-0-4 Overdrive (several, late): Late-game blimp damage next to the tracks.

**Avoid:** ace (separated simultaneous lanes); heli (chases one lane while five leak); sub (no water); buccaneer (no water).

**Removable obstacles and map switches:**

- Train (station light) - repeatable paid ability ($2500): Only in emergencies (e.g. round 98 per fandom); price rises by $2,500 per use; 60 s cooldown for all lights.. One-shots every non-MOAB bloon on that track and stuns blimps 10 s.

**Builds (in buy order):**

*hard, used for the 'hard' hints* - Hard: ApexZ route (no micro needed beyond blind ability presses), stop at R80 (hero: Etienne; inferred, ~56-57). Source: https://www.youtube.com/watch?v=fWry_CuR6GI

  Before R1 (Hard cash): the three darts at the strip spots; then Mermonkeys 1-4 as cash allows (by ~R8 with Double Cash).; Then Etienne, Boomerang1 -> 4-0-2, Sniper on the train -> 1-1-0, all Mermonkeys 0-0-2, Boomerang2 0-2-4 before R40, Village 4-0-2, Mer1/Mer3 4-0-2, Tack1 2-0-4, Engineer ...

Other builds found:

- chimps: ApexZ 'Tricky Tracks | Full Auto Start' - 3 darts, 6 Mermonkeys, Etienne, Glaive/MOAB Press boomerangs, Overdrives (hero: Etienne) - https://www.youtube.com/watch?v=fWry_CuR6GI
- chimps: OneEyedDeacon 'I was BULLIED into making this Tricky Tracks Chimps Guide' (v53.2) - darts, Mermonkeys, Etienne ... (hero: Etienne) - https://www.youtube.com/watch?v=ZaqClazQHSM
- half_cash: OneEyedDeacon 'Half Cash for Tricky Tracks' (v52.1) - Obyn, Druid of the Jungle, Crossbow-ish darts, M.O.A.R. (hero: Obyn Greenfoot) - https://www.youtube.com/watch?v=AqjseFieEDw
- abr: OneEyedDeacon 'Alternate Bloons Rounds for Tricky Tracks' (v53.2) - darts/ninjas/snipers/wizards early, Benjamin, MOAB ... (hero: Benjamin) - https://www.youtube.com/watch?v=8KdBr8JdCB4

**BTD6 Index records** (extreme CHIMPS challenges - evidence of which towers are strong here): LTC: Golden Justice 2-5-0 + Popseidon 0-5-2 + Geraldo (v52.0); heroless Golden Justice + Popseidon + Glaive Lord 5-0-2. LCC $78,855 (v52.0). => Mermonkey (Popseidon) and Golden Justice (Desperado) are the proven single carries; Glaive Lord works.

**Bot data:** `data/map_strategy_hints.json` builds 'hard' (every mode not listed elsewhere): 20 spots - dart, mermonkey, boomerang, sniper, village, engineer, alchemist, ice, ninja, glue; hero etienne.

**Sources:**

- https://www.bloonswiki.com/Tricky_Tracks - Bloons Wiki - Tricky Tracks
- https://bloons.fandom.com/wiki/Tricky_Tracks - Fandom - Tricky Tracks
- https://www.youtube.com/watch?v=fWry_CuR6GI - ApexZ - BTD6 CHIMPS Tricky Tracks Full Auto Start
- https://www.youtube.com/watch?v=ZaqClazQHSM - OneEyedDeacon - I was BULLIED into making this Tricky Tracks Chimps Guide (v53.2)
- https://www.youtube.com/watch?v=XxBPMVU-P68 - OneEyedDeacon - EASY Tricky Tracks Chimps Strategy (v53.2)
- https://www.youtube.com/watch?v=A6OGHATEzTg - wellordering - Tricky Track CHIMPS Black Border Guide
- https://www.youtube.com/watch?v=AqjseFieEDw - OneEyedDeacon - Half Cash for Tricky Tracks (v52.1)
