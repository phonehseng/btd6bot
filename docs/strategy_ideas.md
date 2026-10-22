# Strategy findings for a fully unlocked account

The main account is level 128, with nearly every tower and upgrade unlocked. It has
Double Cash and Fast Track, neither of which applies in CHIMPS.

This page covers three questions:

- what makes Hard and its sub-modes near-certain on every kind of map;
- what the offline checks showed;
- which build to pick per map type.

It complements `docs/research_strategies.md` (guides) and `docs/bloons.md` (the
knowledge base).

## Why games were lost (2026-10-22, main account)

| Map / mode | Strategy | Lost at | Cause (from `logs/bot.log`) |
|---|---|---|---|
| Dark Path / Hard | double_hp_sniper_sun | R25 | See below |
| Last Resort / Hard | farm_sun_avatar | R24 | Early leak at a Fast Track start |
| Luminous Cove / Hard | chimps_ninja_sun | R49 | Land towers reach only the end of the track (map fit 0.33) |
| Pat's Pond / Hard | primary_core | R40 | First MOAB with boomerangs/tacks only |
| Enchanted Glade / Hard | hard_ninja_alch_sun | R63 | All 100 lives lost inside R63 (the lives tracker recorded none): the 122-ceramic + 75-lead rush |

Dark Path lost at R25 for three reasons:

- Fast Track started the game at R22 with $9,700. The ninjas went where spots were
  refused, and 31 + 16 lives leaked in R22-23.
- Then every tower failed to select (phantom towers) and the game was lost.
- This was not a "cannot pop" loss.

None of these losses was a missing camo/lead/purple answer, but several came near it:
- After Fast Track, R24 camo, R25 purple, R26 zebra and R28 lead all arrive within a
  few rounds of the start.
- The threat checks now buy those answers before the first Play if the plan does not
  cover them (see `docs/bloons.md`).

## What the offline simulation shows

`tools/simulate_threats.py` plays every build order through each of its modes. It
uses the real prices and the game's base income, with no Double Cash and no farms.

- **Gaps.** No strategy/mode pair (57) meets a bloon it cannot pop.
- **Answers bought on top of the plan.** Most plans got the threat answers they needed
  for free:
  - ABR plans buy a camo tower at R3 and a lead popper at R7 (ABR: camo R5, lead R10,
    camo lead R24).
  - Water plans buy a ninja for camo at R21: the Sub has no detection before 4-x-x.
  - Plans whose lead answer was a $2,430 Flash Bomb now take a $405 Bomb Shooter when
    the Flash Bomb cannot be afforded before R28 (`minimal_sun_avatar` had answered
    lead at R30, two rounds late).
- **Blimp damage.** The plans reach the late game, but the rough estimate says these
  are thin against blimps:
  - Every CHIMPS/Impoppable plan in R81-R100 (0.1-0.5x of what the ramping blimps
    need).
  - Half Cash builds (0.15-0.3x).
  - Double HP builds (about 0.3-0.5x).

  The estimate is crude: unbuffed, no hero, track-reach heuristics. It agrees with
  experience on one point: one-life modes are decided by blimp damage after R80, not
  by camo or lead. See "CHIMPS" below.

## What makes Hard near-certain on every map type

Hard and its sub-modes never meet a DDT or a BAD; their hardest rounds are R63 and
R76-80. A Hard win needs five things:

1. **Camo before R24** (ABR: R5).
2. **Lead before R28** (ABR: R10).
3. **Purple-capable damage by R25.** Sun Avatar, Ring of Fire and pure Wizard builds
   do not have it.
4. **MOAB damage at R40.**
5. **Crowd damage for R63.** Then roughly 25-40k of blimp damage for R76-R80 (Hard
   R80 is one ZOMG; Double HP makes it 8,000 HP).

With everything unlocked, the remaining risk is no longer the knowledge. It is the
map: whether damage towers can stand where they reach the early track.

| Map type | Examples (data/map_fit.json, early-track reach of land towers) | What works | Why |
|---|---|---|---|
| Land, long single track | Logs, Resort, Spa Pits, Cubism (1,400-1,700 units) | Anything. Ninja/Alchemist, Glaive Lord, snipers | Long crossing time: every DPS check passes with margin |
| Land, short track or many lanes | Quad, Dark Castle, Bloody Puddles, Sanctuary, Workshop, Ravine (60-370 units per lane) | Map-wide damage: `hard_sniper_elite`; Sun Avatars near a village | Ranged towers cover one lane at a time; blimps cross in seconds |
| Little land near the early track | Luminous Cove 0.33, Castle Revenge 0.31, Water Park 0.29, High Finance 0.2, Flooded Valley 0.12 | Snipers (global range), plus subs or buccaneers where there is water | Land-only plans defend only the end of the track. That was the Luminous Cove loss |
| Water-heavy | Peninsula (sub 0.96), Flooded Valley (sub 1.0), Spice Islands, Lotus Island | `military_sub_sniper_water`, `water_sub_alch`, `chimps_sub_druid_water`; snipers | Subs reach everything. Note the Sub sees camo only at 4-x-x: the plans now buy a ninja or sniper for camo |
| Loops and bends | In The Loop, Four Circles, Moon Landing, Tinkerton | `hard_glaive_lord` | Glaives ricochet along overlapping lanes; the dps role prefers spots covering more track |
| No placeable early track at all (map_fit 0.0 for land towers) | Cornfield, Quarry, Glacial Trail, Sulfur Springs, Firing Range | Snipers only, until the map-fit numbers are re-checked | Either the geometry really leaves no spot near the early track, or the fit computation needs a look. Worth a live check |

### Build recommendations (fully unlocked)

These rank the builds; they do not decide them. The planner chooses with the map-fit
numbers, the account's win/loss record and the declared priors.

- **Hard, Double HP, Half Cash on any map** → `hard_sniper_elite` (written by the
  lead).
  - Map-wide damage removes the placement risk that caused most losses.
  - Radar village for camo; Full Metal Jacket for lead and DDT damage.
  - One Elite Defender, with the other snipers at x-x-4.
  - A Glaive Lord boomerang for R63.
- **Hard on maps with loops, and Medium** → `hard_glaive_lord` (new).
- **Hard on open land maps** → `hard_ninja_alch_sun` / `chimps_ninja_sun` (proven
  wins).
- **ABR** → plans that see camo by R5 and pop lead by R10. The threat checks add a
  ninja and a bomb when a plan does not. `abr_ninja_alch` is the native one.
- **Magic Only** → ninja + alchemist (the Alchemist pops lead at 0-0-0; Ninja Flash
  Bomb at 0-0-3 for camo lead).
- **Military Only** → `military_heli_sniper` (Sniper 1-1-0 is the cheapest camo-lead
  answer in the game).
- **Primary Only** → `primary_core` / `primary_glaive_dart`.
  - Lead from Red Hot Rangs (which also pops purple).
  - Camo from Dart 0-0-2.
  - Camo lead from Dart 4-0-2 or Glaive Lord (5-0-0 sees camo).
- **CHIMPS / Impoppable** → `chimps_ninja_sun` on land, `chimps_sub_druid_water` on
  water. Keep the declared rates low: one leak loses.
  - DDTs (R90+) need camo + lead + black in one attack (Sticky Bomb, a Night Vision
    sniper with Full Metal Jacket, White Hot Spikes, MIB).
  - The estimate says blimp damage after R80 is the real limit.
  - A third Sun Avatar or a Perma-Spike should come before R95.

## Strategy changes

- **New: `strategies/hard_glaive_lord.yaml`** (Medium, Hard, ABR). It answers each
  threat as follows:
  - Camo: Sniper 0-1-0.
  - Lead: Red Hot Rangs.
  - Camo lead: Radar village 2-2-0.
  - MOAB: MOAB Press 2-0-4.
  - Rush: MOAR Glaives under Stronger Stimulant.
  - ZOMG: Maim MOAB 4-0-2.
  - Glaive Lord at the end, and only one tier 5.

  The damage towers have role `dps` and the support towers role `support`, as map fit
  expects. Declared base_success:
  - Medium 0.85, Hard 0.75, ABR 0.65.
  - These are below the proven builds because the build is untested and boomerangs
    depend on loops. The planner caps untested Hard priors at 0.85 anyway.
- **`hard_sniper_elite.yaml`** is the lead's. It passes the offline threat simulation
  in all four of its modes.
- **No base_success values were raised.** The simulation shows that plans can pop
  everything in time. It says nothing about whether their damage suffices, so the
  live record must decide.

## Worth verifying live

- That the bot logs a `threat ... covered by` line for each early threat, and a
  `blimp check round N` line per blimp round.
- Whether the ramp's estimates match what happens. Tune `counters.json` →
  `blimp_dps` if MOAB rounds are lost although the check said 1.0x or more.
- Maps with 0.0 land map fit (Cornfield, Quarry, Glacial Trail, Sulfur Springs,
  Firing Range): are they really unplayable for land towers?
- `hold_round`: Play must wait only while an answer is being bought (at most 30 s).
