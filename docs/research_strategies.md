# Strategy research (v57.3, Oct 2026)

Fourteen new role-placed strategies in `strategies/`. They are built for the
bot's executor (`btd6bot/strategy.py`): placement by role, ordered steps, and
`answers:` as a backup for the threat calendar. Every file loads with
`load_all()`. A static check (crosspaths, ids, the order of plan targets, and
threat-table coverage) passed for every file.

## Sources and how much to trust them

Fandom and bloonswiki block fetching, and old.reddit.com could not be fetched,
so the research relied on search snippets, Steam threads and GitHub.

- **linus-jansson/btd6farmer gameplans** (fetched raw from GitHub). These are the only
  machine-proven plans found. They are coordinate-based and tested on Dark Castle only.
  - Hard Standard: Sub 2-0-4, Dart 0-0-2, Alchemist 4-2-0 x2, Super 3-0-2, two Villages
    2-0-2, Spike, then Boomerangs, Glue and Mortar after R85.
  - Hard CHIMPS: Sub 2-0-4 and Dart opener, Obyn, Alchemist 3-2-0/4-2-0 x3, six Druids
    0-1-4 (Poplust), Village 2-2-0, Spike 0-2-5 (as listed in the gameplan).
  - These are the basis of `water_sub_alch` and `chimps_sub_druid_water`.
- **Steam threads.** Several threads suggest these approaches:
  - "Spam 2-0-4 subs whenever there's water."
  - A "ninja + alchemist" start, with a Village discount into a 3-0-2 Super.
  - A heli top path with Village and Alchemist "carries most maps".
  - For Magic Monkeys Only, Obyn plus Ninja 4-0-1 and Alchemist 3-0-0 handles R40.
- **Bloonswiki snippets.**
  - Mode facts:
    - Impoppable: Super Ceramics after R80 and bloons speed up after R80.
    - R90: camo, fortified lead, then 3 DDTs. The usual failure is a lack of
      camo, lead and black coverage.
    - Half Cash halves every income source.
    - Apopalypse has continuous random rounds with all bloon properties early.
  - ABR: camo at about R5 (a Ninja, Dart 0-0-2 or Wizard 0-0-2 is enough), lead at
    R10, a camo rush at R27, MOAB R40, BFB R54, ZOMG R79, DDT R88.
  - Farms: 2-0-3 Marketplace pays about $400 per round with no collecting. EZ Collect
    auto-collects spoiled bananas at 50%.
- **Gaps.** No source gave a universal "placement-free" Hard recipe. The builds below use
  my own community knowledge of standard BTD6 meta (Sun Avatar 3-0-2, Bloonjitsu 4-0-2,
  Sticky Bomb, Stronger Stimulant, MIB, Poplust and Maim MOAB). Tower prices come from
  `towers.py`, which marks itself approximate. **Treat every `base_success` as a prior
  for the planner to overwrite.**

## Design rules used

1. **The first step must cost no more than the starting cash.** Hard starts at R3 with $650.
   - Obyn costs about $700 on Hard, so a cheap tower (Ninja, Sub or Druid) always comes
     before the hero.
   - Quincy-first works ($585).
2. **No aiming.**
   - No Mortar, Dartling or Ace.
   - Snipers set to Strong. Subs, Heli and Spike need no aiming.
   - Ninjas, Druids, Supers and Alchemists cluster with `role: support, near: [...]`.
3. **Every threat is covered by the plan itself, before its calendar window opens.**
   - The threat table is the `ANSWERS` table in `strategy.py`.
   - Windows open at round r-3, or r-6 in one-life modes.
   - `answers:` repeats the same upgrade as a backup. The pattern is
     `[upgrade X to T, place X]`: the upgrade runs if X exists, otherwise X is placed.
4. **`answers:` only uses tower kinds that already appear in plan or fill.** Otherwise the
   kind could be locked: every step would skip, and the executor would hold cash for
   the whole window.
5. **Farms (`uses_income`) go straight to 2-0-3 Marketplace**, because the bot never
   collects bananas.

## Strategy roster

| id | hero | modes | core (final crosspaths) | camo / lead | MOAB-class answer | late |
|---|---|---|---|---|---|---|
| hard_ninja_alch_sun | obyn | med, hard, dhp, half | Ninja 4-0-2, Ninja 2-0-4, Alch 4-2-0, Village 2-0-2 | Ninja / Alch, Flash Bomb | Flash -> Sticky Bomb | Sun Avatar 3-0-2, Spike 2-0-4 |
| hard_ninja_alch_sniper | obyn | med, hard | Ninja 4-0-2 x3, Ninja 2-0-4, Alch 4-2-0 x2, Sniper 4-2-0 x2 | Ninja / Alch | Sticky, Maim MOAB | for accounts without support towers |
| magic_obyn_ninja_wizard | obyn | med, hard, **magic_only** | Ninja 4-0-2/2-0-4, Wizard 0-2-4 (Necro), Alch 4-2-0 | Ninja / Alch, Wizard | Sticky | Sun Avatar 3-0-2, Wizard 0-2-5 (tier 5, optional) |
| obyn_druid_poplust | obyn | med, hard, half | Druid 2-0-4 x5 clustered, Alch 4-2-0, Village 2-2-0 -> 2-3-0 | Dart 0-0-2, then radar / Heart of Thunder, Alch | Dart 0-2-4 Sharp Shooter | Spike 2-0-4 |
| water_sub_alch | quincy | med, hard, dhp (water maps) | Sub 2-0-4 x3+, Alch 4-2-0, Village 2-0-2 | Sub / Alch, APD | Sub 2-0-3/2-0-4 | Spike 2-0-4, Sun Avatar |
| military_sub_sniper_water | quincy | med, **military_only**, hard (water maps) | Sub 2-0-4 x3, Sub 4-0-2, Sniper 4-2-0 x2 | Sub / Sniper FMJ | Maim MOAB | more subs |
| farm_sun_avatar (`uses_income`) | obyn | med, hard | Farm 2-0-3 x3, Ninja 4-0-2/2-0-4, Alch 4-2-0, Village 2-0-2 | Ninja / Alch | Sticky | Sun Avatar 3-0-2 x2, Spike |
| minimal_sun_avatar | obyn | med, hard | Ninja x2, Super 2-0-2 -> 3-0-2, Village 2-0-2 (4 towers) | Ninja / Flash, Plasma | base Super, then Sun Avatar | second Sun Avatar |
| abr_ninja_alch | obyn | **abr** | as hard_ninja_alch_sun, Alch bought 2nd (R5-8) | early | Sticky before R54 | Sun Avatar |
| apopalypse_ninja_sniper | obyn | **apopalypse** | Ninja 4-0-2/2-0-4, Alch, Sniper 4-2-0 x2 | early | Maim, Sticky | Spike 2-0-4 (DDT), Sniper 5-2-0 Cripple MOAB (BAD, tier 5) |
| double_hp_sniper_sun | obyn | hard, **double_hp** | hard core + Sniper 4-2-0 x2 (stuns) | Ninja / Alch | Sticky + Maim | Sun Avatar x2, Spike |
| primary_glaive_dart | quincy | easy, **primary_only**, med | Boomerang 4-0-2 x3, Dart 0-2-4, Glue 0-2-3 | Dart 0-0-2 / Red Hot | MOAR Glaives | Glaive Lord 5-0-2 (fill, tier 5) |
| chimps_ninja_sun | obyn | hard, **impoppable, chimps** | Ninja 4-0-2 x2, Ninja 2-0-4, Alch 4-2-0 x2, Village 2-0-2 + 2-3-0 MIB | Ninja / Alch | Sticky | Sun Avatar x2, Spike 2-0-4 -> 2-0-5 Perma-Spike (BAD, tier 5) |
| chimps_sub_druid_water | obyn | hard, **impoppable, chimps** (water maps) | Sub 2-0-4 x2, Dart 0-2-4, Druid 2-0-4 x6, Alch 4-2-0 x2, Village 2-3-0 | Sub / Alch, APD | Sub, Sharp Shooter | Spike 2-0-4 (DDT) -> 2-0-5 (BAD) |

Every mode now has at least one dedicated option:

| Mode | Strategies |
|---|---|
| hard | 11 |
| medium | 9 |
| magic_only | 1 |
| military_only | 1 new + military_heli_sniper |
| primary_only | 1 new + primary_core, starter_tack_dart |
| half_cash | 2 |
| double_hp | 3 |
| abr | 1 new + primary_core, military_heli_sniper |
| apopalypse | 1 |
| impoppable | 2 |
| chimps | 2 |

**2TC note.** Real two-tower CHIMPS combos all need tier 5s (Glaive Lord, Grandmaster,
Sun Temple, Archmage and similar) and exact spots. A coverage-based placer cannot
guarantee those spots, so none are implemented. `minimal_sun_avatar` is the low-tower
substitute: four towers and no tier 5.

**Tier 5s referenced:**
- Plan steps:
  - Sniper 5-2-0 Cripple MOAB (apopalypse BAD)
  - Spike 2-0-5 Perma-Spike (CHIMPS BAD)
  - Wizard 0-2-5 Prince of Darkness (last step of the magic plan)
- Fill only: Boomerang 5-0-2 Glaive Lord
- A locked tier is capped and skipped.

**Water maps.** The allowlist in `planner.maps` was written from memory. It covers 24 maps
with water next to the track. If the map model finds no water spot, the sub steps skip,
so verify the list against the learned map models.

## Executor and table issues found (not fixed, since .py files were off limits)

1. **The `ANSWERS` table has false positives and gaps.**
   - Camo:
     - It lists Alchemist (0,0), Druid (0,0) and Heli (0,0), none of which see camo.
       Heli needs IFR (path 2, tier 2).
     - Engineer (3,3) should be (2,3) Cleansing Foam.
   - Lead:
     - Super (1,1) should be (1,2) Plasma.
     - Heli (0,0) and Ace (0,0) cannot pop lead (Ace needs path 2, tier 3 Bomber).
     - Ninja (3,2) Caltrops is doubtful; Flash Bomb (3,3) is the real answer.
     - Druid (1,2) Heart of Thunder is missing.
   - Ceramic: Wizard and Sub are missing.
   - MOAB:
     - Ninja 4-0-x is missing.
     - Druid (2,4) is Jungle's Bounty, an income upgrade. The intended entry is
       probably (1,4) Ball Lightning.
   - DDT:
     - Sniper (2,4) is Supply Drop; the real answer is Maim MOAB (1,4) plus camo.
     - Dart (3,4) Sharp Shooter is sharp and cannot pop lead.
     - `NEEDS_CAMO` is declared but `has_answer` never checks it.
   - My plans add real coverage wherever the table is wrong.
2. **Stalls.** `answer_threat` treats any step that returns `done` as "bought an answer".
   - A completed upgrade returns `done`, and so does a `place` for an id that already
     exists. If that step does not satisfy the table, `tick()` returns True every tick for
     the whole window and the plan stops spending.
   - The same happens when the needed tier is XP-locked (capped), and with the generic
     answer when the tower's crosspath conflicts with the generic target.
   - Suggested fix: skip steps that are already complete. If the threat is still
     unanswered after the list, mark it unanswerable.
3. **Holding cash.** If every `answers:` step returns `skip` (for example, the kind is
   locked), the executor holds cash for the whole window. A fallback should mark the
   threat unanswerable.
4. **The ABR calendar only shifts DDTs.**
   - ABR has camo at about R5, lead at about R10, BFB at R54 and ZOMG at R79. Suggested
     `threat_shift`: `{camo: 5, lead: 10, bfb: 54, zomg: 79, ddt: 88}`.
   - Apopalypse threats are random. Something like `{camo: 8, lead: 10, ceramic: 20}`
     with a bigger lookahead would be safer.
5. **Abilities.** The ability hotkeys `1`/`2` fire whatever sits in those slots, which can
   be a tower ability bought earlier. Avoid targeted tower abilities: Support Chinook,
   or anything that needs a click.
6. **Hero cost.** A hero-first step that costs more than the $650 start (Obyn and most
   others on Hard and above) leaves R3 undefended. The older YAMLs use Quincy first, which
   is fine.
