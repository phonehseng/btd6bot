# Damage-model audit: Primary towers, Quincy and Obyn (2026-11-12, game 57.4)

This is a read-only audit. No code was changed.

**Scope.**
- Towers: Dart, Boomerang, Bomb, Tack, Ice, Glue and Desperado.
- Heroes: Quincy and Obyn, as far as the model rates them.
- Checked against the Druid of the Jungle question in the brief (appendix A).

**How the audit was done.**
- Every crosspath x-0-0 to 5-0-0 on each path was printed from `dps_model.profile()`, run from the repo root.
- So was every common crosspath at tiers 3-5 (3-1-0, 3-2-0, 3-0-1, 3-0-2 and so on). That is 51 crosspaths per tower.
- Each profile was compared with the raw entry in `data/game_model/attacks.json` and with the full Fandom wiki pages, read as wikitext through `api.php`: the "Full Popology / Statistics", "Notes" and "Strategy" sections.
- **Reddit could not be read.** `old.reddit.com/.../search.json` returned empty bodies. Community claims below come from search snippets only and are marked.

**Wiki links.** `fandom:<Page>` means `https://bloons.fandom.com/wiki/<Page>`.

**Marks.**
- **[UNVERIFIED]**: no fetched source confirmed the claim.
- **[EST]**: my own estimate.

---

## 0. Short answer

Most of the base numbers are right. Rate, pierce, damage, the damage type (immunities), camo per tier and the ceramic, MOAB and fortified bonuses match the wiki for nearly every crosspath; section 3 has the verification table.

The ratings are still wrong, because of what the model throws away. In order of impact:

1. **Every status effect.** The export already carries slow, freeze, stun, knockback, push-back, MOAB slow, the Arctic Wind slow zone, and camo or regrow removal. `dps_model` reads none of them.
   - As a result the Glue Gunner's main paths have **no damage source at all**. They are rated as nothing.
2. **Every ability.** The export drops AbilityModel. Yet the bot fires abilities on cooldown (`btd6bot/abilities.py`).
   - Super Maelstrom, MOAB Eliminator, Glue Strike and Storm, Absolute Zero and Turbo Charge get most of their value from their ability.
3. **Debuffs that make other towers stronger.** Embrittlement adds +1 damage taken and Super Brittle +4. Embrittlement and Ice Shards remove camo and regrow. Glue Strike adds +2 damage. Bounty Hunter's mark doubles Desperado damage.
4. **One reach for all of a tower's attacks.**
   - Within a station every source is given the zone of the tower's *largest* range.
   - Glaive Lord's orbit, Desperado's pistol and Desperado's shotgun are credited far outside their real circles. That is an over-credit.
5. **Hidden range the model cuts off.**
   - Glaive Lord's thrown glaives seek bloons at infinite range.
   - Glaive Ricochet bounces 60 units and M.O.A.R. Glaives 180.
   - Absolute Zero's Ultrafreeze hits the whole screen.
   - Golden Justice fires a line with infinite pierce.
6. **Sub-projectiles the export never sees:** Ice Shards, Icicles, Liquefier and Solver puddles, and The Blazing Sun's fire.
7. **Smaller formula bugs.**
   - A narrow spread (Triple Shot, the Desperado shotgun) is treated as a 360° spray. This under-credits about 2×.
   - Recursive Cluster's alternate bomb is added on top of the normal bomb instead of replacing it. This over-credits about 25%.
   - Super Glue's 30 MOAB damage is floored to 0.
   - DoT bonuses against ceramics and MOABs are missing.
   - Frag pierce cost is ignored.
   - The anti-synergy of freezing next to sharp towers is ignored.
8. **Heroes count for nothing.** That includes Obyn's camo buff to Druids, which the export does carry.

---

## 1. Systemic findings, ranked by impact on CHIMPS and Impoppable

Each finding below gives the tower, what the model says, what the game does, the effect and a fix.

### F1. Slows, freezes, stuns and knockback are not modelled (huge under-credit)

**Where.** `_flatten_projectile` only makes a Source when a projectile has `damage` or `dot` (dps_model.py:474). `effects` and the tower's `zones` are never read. A grep for `effects`, `zones` and `slow` in `btd6bot/` finds no reader.

**Model says.**
- **Glue Gunner has no source at all at:**
  - 0-0-0, 1-0-0, 0-1-0, 0-2-0;
  - 0-3-0 Glue Hose, 0-4-0 Glue Strike, 0-5-0 Glue Storm, and their 1-x-0 crosspaths;
  - 0-0-1 to 0-0-4, including MOAB Glue (0-0-3) and Relentless Glue (0-0-4);
  - and all their x-1/x-2 crosspaths.
- `station_for` returns None for these, so the optimizer and `round_margin` cannot rate a glue at all.
- **0-0-5 Super Glue** is rated as a 1-damage, 6-pierce dart.

**Game does.** The export carries all of these numbers already:

| Upgrade | What the effect does |
|---|---|
| Glue 0-0-0 | 50% slow for 11 s on 3 layers |
| Stickier Glue (0-0-1) | lasts 18 s (v57) |
| x-0-2 | 75% slow |
| MOAB Glue 0-0-3 | MOAB-class slowed 37.5% for 24 s (fandom:MOAB_Glue) |
| Relentless Glue 0-0-4 | the splat when a glued bloon pops stuns bloons 1 s, MOABs and DDTs 0.25 s (fandom:Relentless_Glue) |
| Super Glue 0-0-5 | stops MOABs and DDTs for 5 s, BFBs 95% for 2 s, ZOMGs 90% for 0.75 s (fandom:Super_Glue) |
| Ice freeze | 1.5-3.0 s stop |
| Permafrost (1-x-x) | permanent 50% slow |
| Arctic Wind (0-3-0) | 40% slow zone in range (export `zones`: speed_scale 0.6) (fandom:Arctic_Wind_(BTD6)) |
| Absolute Zero (0-5-0) | 60% slow, MOABs 30% (fandom:Absolute_Zero_(BTD6)) |
| Icicle Impale (0-0-5) | freezes blimps |
| Bloon Impact (4-x-x) | stuns 1.4 s |
| Bloon Crush (5-x-x) | stuns everything up to a ZOMG for 2 s, visible DDTs included (export `stun` 2.0; fandom:Bloon_Crush) |
| Juggernaut | knockback |
| MOAB Press / MOAB Domination | push MOABs back 2-3 units, stun 0.25 s |
| Desperado Enforcer to Desert Phantom (x-x-3 to x-x-5) | knockback, MOABs from x-x-4 (fandom:Desperado) |

**Effect.**
- A 50% slow doubles the time a bloon spends in *every* zone after the glue. For whole-board RBE capacity that is like **×1.5 to ×2 board strength** on glued layers [EST].
- MOAB Glue's 37.5% slow over 24 s gives every tower about +60% time on blimps [EST].
- Super Glue holds R80-R99 MOABs and DDTs for 5 s per hit.
- **The planner can never pick a glue, an Arctic Wind or Super Glue**, and it under-rates Bloon Crush and Icicle Impale.
- This fits the CHIMPS advice in the research doc ("add slows, stuns and debuffs").

**Fix.**
1. In `_flatten_projectile`, keep effect-only projectiles as "control" sources with `slow`, `slow_layers`, `slow_s`, `stun_s`, `moab_mult` (from `slow_modifier`) and `knockback`.
2. In `_play`, give each station a slow factor. Lots that pass a slowing station get a stretched time-in-zone for downstream stations: deadline × 1/(slow multiplier), for the share of the lot it can hit (pierce × shots × slow lifespan ÷ bloons).
3. Treat a stun or freeze of `t` seconds as `t` seconds added to the deadline of the frozen share.
4. Read tower `zones` (Arctic Wind) as a permanent speed scale inside the radius.
5. Cap all of it at the BAD's rules: `slow_modifier` "Bad" and the BAD's immunities (research doc, R100).
6. Calibrate against logged games before trusting it; slows have diminishing returns.

### F2. Abilities are excluded although the bot uses them (large under-credit at tier 4-5)

**Where.** `tools/export_attacks.py`, `tower()`, drops `AbilityModel` ("Abilities are left out"). Yet `btd6bot/abilities.py` presses tower ability hotkeys on cooldown and in crisis rounds.

| Tower and crosspath | What the model counts | Ability left out (wiki) | Average value lost [EST] |
|---|---|---|---|
| Tack 0-5-0 Super Maelstrom (and 1-5-0, 2-5-0, 0-5-1, 0-5-2) | 8 blades of 5 dmg (+5 ceramic), 7.1 shots/s | 4 blades every 0.045 s, 300 pierce, 2 dmg (+8 ceramic), ignores line of sight, 9-12 s on a 20 s cooldown (fandom:Super_Maelstrom) | Pierce-limited, about 89 blades/s × 300 pierce, up for about 45% of the time. **Tens of times the passive** on dense rounds such as R63, R76 and R95 |
| Tack 0-4-0 Blade Maelstrom | 8 blades, 2 dmg | 2 blades per 0.045 s, 100 pierce, 3-4 s on a 20 s cooldown (fandom:Blade_Maelstrom_(BTD6)) | Several times the passive in crowds |
| Bomb 0-5-0 MOAB Eliminator | Missile +99 MOAB dmg, 1.21 shots/s, about 120 dps on blimps | 4500 damage that goes through layers, **infinite range**, every 10 s (fandom:MOAB_Eliminator) | +450 dps on blimps at infinite range: **about 4× the passive** |
| Bomb 0-4-0 MOAB Assassin | +30 MOAB | 750 damage at infinite range every 30 s (fandom:MOAB_Assassin_(BTD6)) | About +70% on blimps. Kills a lone MOAB early, e.g. the R40 MOAB |
| Bomb 0-0-5 Bomb Blitz | Recursive clusters | Bomb Storm on life loss: 2000 to everything, wipes MOABs and below, once per round (v57) (fandom:Bomb_Blitz) | Little in CHIMPS (fires only on a leak). A safety net in Impoppable |
| Boomerang 0-4-0 Turbo Charge | Same 6.67 shots/s as Bionic | 10 s at 0.03 s rate with 2 dmg, 45 s cooldown (fandom:Turbo_Charge_(BTD6)) | About ×2 average dps [EST] |
| Boomerang 0-5-0 Perma Charge | 33 shots/s of 4 dmg | 12 dmg for 15 s of every 45 s (fandom:Perma_Charge) | About +67% average |
| Dart 0-4-0 SMFC / 0-5-0 PMFC | 12.6 darts/s of 1 dmg | Up to 10 / 20 Dart Monkeys turn into super-speed shooters (0.06 s; PMFC: 0.03 s plasma, 2 dmg, 5 pierce) for 15 s (fandom:Super_Monkey_Fan_Club_(BTD6), fandom:Plasma_Monkey_Fan_Club_(BTD6)) | Nearly all of their value |
| Glue 0-4-0 Glue Strike / 0-5-0 Glue Storm | Nothing (see F1) | Whole-screen glue, +2 damage taken (+3 at 2-4-0), lead and frozen poppable by any type; Storm reapplies every 1 s for 20 s, 40 s cooldown (fandom:Glue_Strike, fandom:Glue_Storm) | Very high in R95 and R98 |
| Ice 0-4-0 Snowstorm / 0-5-0 Absolute Zero | Freeze in range | Whole-screen freeze of 3-6 s (Snowstorm, 30 s cooldown) or 10 s, blimps included, plus +50% attack speed for every Ice Monkey (Absolute Zero, 25 s cooldown) (fandom:Snowstorm, fandom:Absolute_Zero_(BTD6)) | Stall time on every blimp round. **Not on the BAD** |
| Desperado 0-3-x Take Aim; 0-4-x / 0-5-x Marked to Pop | Rifle and pistol only | Take Aim: +20% range (+50% at x-4-x), camo, and at x-4-x black, white and purple popping for a chosen tower. Marked to Pop: 10 marked bloons at infinite range, 30 dmg (300 at Golden Justice) that pops everything (fandom:Desperado) | A support camo / MIB-like buff. Take Aim needs a target tower, and the bot cannot aim it (see the gap below) |

**Fix.**
1. Export an `abilities` block per crosspath: cooldown, duration, the projectile tree, and a whole-screen or self-centred flag.
2. In `profile()`, add each ability as Sources scaled by duty cycle (duration ÷ cooldown) for sustained ratings.
3. For crisis-round ratings, add a `burst` field so `round_margin` can credit one use per round.
4. Abilities the bot cannot aim (Take Aim) or never presses should stay out. `abilities.py` already holds that list.

### F3. Debuffs and support effects on bloons (large under-credit for Ice 4-x-x and 5-x-x)

**Model says.**
- 4-0-0 Embrittlement is a 1-damage, 40-pierce zone every 2.4 s.
- 5-0-0 Super Brittle is 5 damage (+5 ceramic) every 1.56 s.
- Nothing else.
- The export lists `AddBonusDamagePerHitToBloonModel`, `RemoveDamageTypeModifierModel` and `effects.removes: ["camo","regrow"]` but marks them uninterpreted or unused.

**Game does.**
- **Embrittlement:** bloons it hits take **+1 damage from every attack, DoTs included**, for 2 s. It works through 3 layers, or 1 blimp layer.
  - They also lose lead and frozen immunity for that time.
  - It **strips camo and regrow permanently**: "the only Primary Monkey to decamo bloons", used on R78 and on DDTs in R95 and R99 (fandom:Embrittlement).
- **Super Brittle:** **+4 damage from all sources** for 3 s, and it reaches MOABs (fandom:Super_Brittle).
- **Ice Shards (3-x-x)** and higher also remove camo and regrow (fandom:Ice_Shards_(BTD6)).
- **Glue Strike and Storm:** +2 damage taken (F2).
- **Bounty Hunter:** marked bloons take 2× damage from every Desperado (fandom:Desperado).

**Effect.**
- Next to a 1-damage, high-projectile carry (Tack Zone, Overdrive, Perma Charge, Glaive orbit, Plasma or MIB darts), Embrittlement roughly **doubles** that carry's damage. Super Brittle adds about 4× its base damage per hit [EST].
- Decamo lets every non-camo tower in the debuffed stretch hit camo DDTs. The planner instead buys Radar villages or forbids builds.
- The search snippet calls Super Brittle "considered underrated among experienced players" (bloonswiki snippet, not fetched in full) [UNVERIFIED].

**Fix.**
1. Export the numbers: bonus per hit, duration, layers.
2. Model it as a station-level "debuff zone". Every *later* station's sources get `+bonus` per hit on the debuffed share of a lot. The share is capped by the debuffer's pierce × shots × duration ÷ bloons per second.
3. For `removes: camo`, let later stations hit the de-camoed share as non-camo, like the Advanced Intel `camo_paths` logic but per lot.

### F4. One zone per station: each source's own range is ignored (over-credit for some, under-credit for others)

**Where.**
- `_make_station` builds one zone list from `reach_radius` = max(tower range × buffs, own_radius, pattern + range) (dps_model.py:1834-1838 and 1918).
- `Source.range` is stored but never used in `_hit_rate`.

**Cases.**
- **Glaive Lord 5-0-0 / 5-0-2.** The orbit (`OrbitingGlaive`, zone_wide, 20 pulses/s, 200 pierce) has radius 30 or 34.5. It is credited over the 43 / 57.2-unit throwing circle.
  - zone_wide means "meets every bloon in the zone", so its hits and time scale with the covered track length: about ×1.4 at 5-0-0 and **about ×1.7 at 5-0-2** too much [EST, track-dependent].
  - The wiki says the orbit is "30 unbuffable range" (fandom:Glaive_Lord_(BTD6)).
- **Desperado 0-3-x to 0-5-x.** The pistol has range 40, and at 0-5-0 its explosion too. It is credited over the rifle's 80-unit circle: about ×2 coverage.
- **Desperado x-x-3 to x-x-5.** The shotgun's range is 36 but the tower's is 60: about ×1.7.
- **Boomerang 0-0-5 MOAB Domination.** The Heavy Kylie (range 100) is limited to 57.2. This is an under-credit.

**Fix.**
- Group a tower's sources by `Source.range`, and by own_radius for "self" attacks. Build one Station part per group with its own zones, the way `Station.parts` already does for global plus local sources.
- Keep one server for the shared "time" only where the game shares one weapon cooldown: alternatives, not parallel attacks.

### F5. Hidden range: seeking, bouncing and whole-screen projectiles (under-credit)

| Tower and crosspath | Model | Game | Fix |
|---|---|---|---|
| **Glaive Lord 5-x-x** thrown glaives | Aimed, range 43 / 57.2, reach 61-71 | "Projectile **seeks to the closest bloon within infinite range** with 0.05 s delay", lifespan 2-5 s, re-hits every 0.6 s, infinite bounce distance (fandom:Glaive_Lord_(BTD6)) | Treat it as global over the lane parts within speed × lifespan (about 300 × 2 s) of the tower, or as `placement="global"` with a seeking efficiency of about 0.5 [EST] |
| **Glaive Ricochet 3-x-x** | Aimed, range 43; export `bounces: 1000000` ignored | Ricochets to bloons **up to 60 units** from the glaive, ignores line of sight (fandom:Glaive_Ricochet_(BTD6)) | Use reach = pierce × bloon spacing, capped by a 60-unit bounce; zone = range + 60 |
| **M.O.A.R. Glaives 4-x-x** | Same | Ricochets up to **180 units** from the glaive (fandom:M.O.A.R._Glaives) | Zone = range + 180, i.e. most of a small map |
| **Juggernaut / UJ 4-x-x and 5-x-x** | Travel capped at 2 × range | Balls rebound off map borders and blockers and **can re-hit after a rebound** (export `MapBorderReboundModel`; fandom:Juggernaut_(BTD6)) | Small; let reach use the full lifespan on maps with walls nearby [EST] |
| **Absolute Zero 0-5-x** `GlobalProjectile` (Ultrafreeze) | Placed in the aimed station, so only the 40-unit circle | "Whole screen, burst, 1 damage, +3 ceramics, 999 pierce", every 1.8 s once its main freeze lands (fandom:Absolute_Zero_(BTD6)) | `radius >= 1e6` gives placement "global": up to 999 hits per 1.8 s map-wide |
| **Golden Justice 0-5-x** rifle | radius 6, static: reach 28 (one blob) | "Shoots a **line** with infinite pierce", 280 (+280 fortified) (fandom:Desperado) | Reach = the length of lane the line crosses, about the zone length on straight lanes |
| **Quincy** (if heroes are added) | — | Arrows ricochet up to 50 units between 3-9 targets (fandom:Quincy_(BTD6)) | The same bounce logic |

### F6. Sub-projectiles the export never captured (under-credit)

- **Ice Shards 3-x-x, Embrittlement 4-x-x and Super Brittle 5-x-x.**
  - Frozen bloons popped by *any* tower spray 3 shards (6 at Super Brittle) of 2 dmg (5 at Super Brittle) with 3 pierce (fandom:Ice_Shards_(BTD6), fandom:Super_Brittle).
  - The model's 3-0-0 has only the freeze. The shards hang off a bloon behaviour, which the export does not follow (`AddBehaviorToBloonModel`, where only DoT is read).
- **Icicles 0-0-4 and Icicle Impale 0-0-5.** Frozen bloons grow icicles of 3 dmg and 3 pierce (fandom:Icicles, fandom:Icicle_Impale). The model has only the snowball.
- **Bloon Liquefier 4-x-x and The Bloon Solver 5-x-x.** Popped glued bloons drop acid **puddles** on the track: 3-4 pierce, 2 dmg (Liquefier) or 15 dmg (Solver), lasting 7.7-16.8 s (fandom:Bloon_Liquefier_(BTD6), fandom:The_Bloon_Solver). These are missing.
- **The Blazing Sun 5-x-x.**
  - Every 50th shot sets the target ablaze: 75 dmg per 1.5 s for 12 s (600 in total), spreading to 8 nearby bloons (v50 notes in fandom:Desperado).
  - The raw `Desperado-500` entry has no fire at all [where the game keeps it: UNVERIFIED].
  - At about 40 shots/s that is about 0.8 ignitions/s, roughly +50% against grouped blimps [EST].
- **The Desert Phantom x-x-5.** The shrapnel "can explode and catch fire" (fandom:Desperado). Only the 10-per-1.5 s DoT is exported [UNVERIFIED].

**Fix.** In `export_attacks.py`, follow `AddBehaviorToBloonModel.behaviors` for `CreateProjectileOnBloonPop/Destroy`-type models and `ShardsOnPop`. Export them as `spawn: {on: "pop"}`, then let `_flatten_projectile` count one spawn per popped layer.

### F7. DoT numbers wrong or lost (mixed)

- **Super Glue 0-0-5.**
  - Export: `dot {amount 30, interval 1.0, lifespan 0.95, only Moabs}`.
  - `ticks = floor(0.95/1.0) = 0`, so `dot_total = 0` (dps_model.py:478). The wiki lists **30 MOAB damage** per hit (fandom:Super_Glue).
  - The "20 damage every 2 s for 24 s" glue DoT is also not exported (`AddBehaviorModifierForTagModel` is uninterpreted).
  - **Fix:** `ticks = max(1, round(lifespan/interval))` when the lifespan is less than the interval; export the modifier DoT.
- **Bloon Liquefier / Solver.**
  - The model has 1 dmg per 0.1 s with no tag bonus.
  - The game deals **3 per tick to ceramics** (Liquefier), and **9 to ceramics and 5 to MOABs** per tick (Solver) (wiki pages above).
  - So the model is ×3 / ×9 / ×5 low on exactly the R63, R76 and R95 threats.
  - **Fix:** read the `DamageModifierForTagModel` that sits inside the DoT behaviour and carry `dot.bonus`.
- **Glue Soak / corrosive glue across layers.** The DoT soaks all layers (`layers: 9999999`), so it keeps burning the children. The model only gives `min(hits × dot_total, in_zone × dot_rate)` on the hit layer. Under-credit on multi-layer bloons [EST, moderate].
- **Glue 3-1-0 / 3-0-1 / 3-0-2.**
  - A 0-damage glue projectile carries `bonus Ceramic +2`.
  - `damage_vs` turns that into a **2-damage hit on every ceramic**.
  - This is probably the Dissolver's ceramic DoT bonus put in the wrong place by the export: a small over-credit on the hit and an under-credit on the DoT [UNVERIFIED].

### F8. Narrow spreads read as 360° sprays (under-credit about 2×)

**Where.** `_flatten_attack` sets `radial = count >= 3 and motion straight` (dps_model.py:671). `_hit_rate` then multiplies shots by `zone.angular`.

**Cases.**
- Dart 0-3-0 Triple Shot is "3 per shot at 30° total spread" (fandom:Triple_Shot_(BTD6)). The same holds for 0-4-0, 0-5-0 and every crosspath.
- The Desperado shotgun (x-x-3 to x-x-5, 3 buckshot) is a forward cone.

**Effect.** On Monkey Meadow, at 15 units from the lane, `zone.angular` ranged from 0.22 to 0.75 (median about 0.5). Triple Shot and SMFC darts lose that share although all three darts fly at the target.

**Fix.** Export the arc angle (`ArcEmissionModel.angle`) and set `radial` only when the angle is 180° or more (tacks, Tack Zone).

### F9. Alternate projectiles counted on top of the normal shot (over-credit)

**Where.** `_flatten_attack` adds `alternate` sources at `crowd × count/every` without reducing the main weapon (dps_model.py:681-685).

**Case.** Bomb 0-0-4 Recursive Cluster (and 1-0-4, 2-0-4, 0-1-4, 0-2-4).
- The wiki: "**every second shot, replaced** with Recursive Bomb" (fandom:Recursive_Cluster).
- The model counts the normal bomb and its clusters at 0.667 shots/s plus the recursive bomb at 0.333/s.
- In the game it is 0.333/s plus 0.333/s.
- About +24% on that path's hit total [EST from the profile: 148 vs 120 hits/s in a crowd].
- Quincy's every-2nd-shot exploding arrow follows the same pattern, if heroes are added.

**Fix.** Scale the main weapon by `(1 - count/every)`, the way the `crit` branch already *replaces* damage.

### F10. Freezing next to sharp towers (over-credit for some boards)

**Where.** `IMMUNITIES = ("lead","black","white","purple")` leaves out `frozen`, although the export marks sharp damage `immune: ["lead","frozen"]`.

**Game does.** Frozen bloons cannot be hit by sharp attacks. Embrittlement exists partly to undo this ("prevents dissynergy with its own freezing": fandom:Embrittlement).

**Effect.** An Ice Monkey 0-x-x to 3-x-x, or Cryo or Icicles (0-0-3+), next to darts, tacks, boomerangs or glaives turns part of their hits to zero.
- The model credits them in full.
- And it credits the ice with nothing for it (F1).

**Fix.** Once freezes are modelled (F1), mark the frozen share of a lot as immune to sources whose damage lists `frozen`. Embrittlement, and a Glue Strike in force, lift that.

### F11. Frag pierce cost ignored (over-credit about 2× on frags)

**Case.** Bomb x-x-2 frags with no 3-x-x (0-0-2, 0-1-2, 0-2-2, 0-3-2, 0-4-2, 0-5-2, 1-0-2, 2-0-2).
- The export has `pierce 2, extra_pierce_cost {"": 1}`: each hit costs 2 pierce, so 1 hit per frag.
- The wiki gives the frag as "1 pierce" (fandom:Frag_Bombs_(BTD6)).
- 3-0-2 and above have cost 0, which is correct there.

**Fix.** Effective pierce = pierce ÷ (1 + extra cost) when the tag is "" (any bloon).

### F12. Heroes rated zero, including support the export already carries (under-credit)

**Where.**
- `forecast.py:144/169` and `tools/optimize_builds.py:550-557, 768` drop `kind == "hero"`.
- `dps_model.profile()` reads only `towers`, never `heroes`.

**Effect.** See section 4.

### F13. Burst weapons may be rated too fast (Desperado, over-credit) [UNVERIFIED]

- The model counts `count × burst / rate`. Desperado 3-0-0 has burst 6 and rate 1.2, which the model reads as 5 shots/s.
- The wiki says shots go at 0.1 s apart, then a 1.2 s reload. That is 6 ÷ (1.2 + 0.5) ≈ 3.5 shots/s, about 30% lower.
- The burst interval is in the model (`BurstWeaponBehaviorModel`; `export_attacks.py:239` uses it to derive the tick) but is not exported per weapon.
- Standoff and Quickdraw (+60-120% with few bloons in range), Wanderer (+45%) and Bullseye crit (4×/8×) are not exported either. These push the other way on sparse rounds.
- **Fix:** export the burst interval and use cycle = rate + (burst − 1) × interval.
- Leave the conditional speed buffs out. With one life, the safe reading is the crowd case.

---

## 2. Findings per tower

Each tower below lists what matches the wiki, then what is missing or wrong.

### Dart Monkey

**Matches.** All of these agree with the wiki:
- Sharp Shots and Razor Sharp: pierce 3 / 5.
- Spike-o-pult: 1.15 s, 2 dmg, 18 pierce.
- Juggernaut: 1 s, 2 dmg, +3 ceramic, +2 fortified, 60 pierce.
- Ultra-Juggernaut: 5 dmg, +8 ceramic, +5 fortified, +20 lead, 210 pierce.
  - It splits **twice** into 6 balls of 50 pierce. Its two `exhaust` spawns are therefore correct, not a double count (fandom:Ultra-Juggernaut).
- Quick and Very Quick Shots.
- Triple Shot: 0.477 s.
- SMFC base: 0.238 s.
- Sharp Shooter: 0.475 s, 6 dmg, crit 50 averaged to 11.4.
- Crossbow Master: 0.2375 s, 8 dmg, crit 80 every 5th averaged to 22.4. The v57 change to two bolts at half rate gives the same shots per second.
- x-0-2 camo and range +8 / +16.

**Missing or wrong.**
- F8: Triple Shot, SMFC and PMFC under-credited about 2×.
- F2: SMFC and PMFC abilities missing. That is nearly all of the value of 0-4-0 and 0-5-0.
- F5: Juggernaut and UJ wall rebounds. Minor.
- Knockback: minor.

### Boomerang Monkey

**Matches.**
- Glaives 2-x-x: 13 pierce.
- Ricochet: 1.2 s, 15 pierce. The v54 nerf (30 → 15) is in the data.
- M.O.A.R. Glaives: 0.4 s, +1 ceramic, 60 pierce.
- Glaive Lord: 6 dmg, +10 ceramic, 60 pierce, shred 1000 over 10 s on the first MOAB (counted as DoT, capped per bloon).
- Orbit: 200 pierce, 4 dmg (+4 ceramic) every 0.05 s.
- Bionic: +2 MOAB in the wiki, +1 in the export. The wiki says "1 damage, 2 damage to MOAB-Class" (+1), so they agree.
- Kylie: 18 pierce, re-hits.
- MOAB Press: 10 s, 200 pierce, +4 MOAB.
- MOAB Domination: the explosion of 100 + 200 burn.

**Missing or wrong.**
- F5: thrown glaives seek at infinite range, and Ricochet bounces 60 / 180. Large under-credit for 3-x-x to 5-x-x on winding maps.
- F4: Glaive Lord orbit over-credited ×1.4-1.7.
  - The orbit's damage is "layer-unpenetrating" (fandom:Glaive_Lord_(BTD6)), but the model passes its overflow to children. A small extra over-credit.
- F2: Turbo Charge and Perma Charge abilities.
- F1: MOAB Press and Domination push MOABs back. 2-0-4 / 2-0-5 push 50% further. The stall is not counted.
- Minor data difference: 5-2-0 is 5 shots/s in the model, while the wiki says 0.225 s (4.4/s). The game data is newer, so trust it.

### Bomb Shooter

**Matches.**
- Base: 1.5 s, 22 pierce, black immune.
- Bigger and Heavy Bombs.
- Really Big Bombs: 4 dmg, 80 pierce, 1.5 s.
- Bloon Crush: 24 dmg.
- Mauler / Assassin / Eliminator: +15 / +30 / +99 MOAB, 0.875 s (data 0.826 s, close).
- Cluster and Recursive numbers.
- v57: MOAB Assassin frag pierce 4, count 8.

**Missing or wrong.**
- F1: Bloon Impact stun 1.4 s; Bloon Crush stun 2 s up to ZOMG, visible DDTs included; knockback.
- F2: Assassin and Eliminator abilities. Eliminator's 4500 every 10 s at infinite range is about 4× its passive blimp damage.
- F9: Recursive Cluster over-credit about 24%.
- F11: frag over-credit 2× on 0-x-2 and 1-0-2 / 2-0-2.
- Correct as is: bombs cannot hurt DDTs (black). Note that Mauler, Assassin and Eliminator therefore do nothing to DDTs without MIB.

### Tack Shooter

**Matches.**
- Ring of Fire: 0.315 s, 5 dmg, 30 pierce, zone; purple immune is correct for fire.
- Inferno Ring:
  - ring 0.1 s, 8 dmg (+4 MOAB, i.e. 12 in total), 45 pierce;
  - meteor 4 s, 700 (1000 at 5-0-2) damage at infinite range;
  - explosion 50 + 4 s × 50 burn.
- Blade Shooter / Maelstrom / Super Maelstrom base attacks.
- Overdrive: 16 tacks at 0.373 s.
- Tack Zone: 32 tacks at 0.224 s, +1 MOAB.
- Tacks are correctly radial.

**Missing or wrong.**
- F2: Blade Maelstrom and Super Maelstrom abilities. This is the largest omission for this tower; Super Maelstrom is a standard R76 / R95 answer.
- Nothing else of note. Tack is the most accurate tower in the model.

### Ice Monkey

**Matches.**
- Base: 2.4 s, 40 pierce, does not hit MOABs.
- Metal Freeze 2-x-x: camo.
- Super Brittle: 1.56 s since v56, 5 dmg, +5 ceramic.
- Cryo: 1.2 s.
- Icicles: 0.75 s, 2 dmg, +8 MOAB.
- Icicle Impale: +48 MOAB.
- Absolute Zero: 300 pierce.

**Missing or wrong.** Almost everything that gives this tower its value:
- F1: freeze 1.5-3 s; Permafrost 50% slow; Arctic Wind 40% / Absolute Zero 60% slow zones; Icicle Impale freezes blimps.
- F3: Embrittlement +1 and Super Brittle +4 to all damage, decamo and degrow.
- F6: Ice Shards (3 or 6 shards from every frozen bloon popped) and Icicles.
- F5: Absolute Zero's whole-screen Ultrafreeze, 999 pierce, 1 dmg (+3 ceramic) per 1.8 s, limited to 40 units in the model.
- F2: Snowstorm and Absolute Zero abilities.
- F10: freezing blocks sharp towers.
- **Net effect.** Today the model rates every Ice Monkey as a very weak pulse.
  - The research doc lists Ice 2-0-4 Icicles for R63 and Super Brittle as A-tier.
  - The model can therefore never choose them for the right reason. When it does pick ice, it does so while hurting nearby sharp towers.
- Data detail [UNVERIFIED]: Embrittlement's exported `slow multiplier 1.0` disagrees with the wiki's "Permafrost 50%" for 4-0-0 crosspaths that include 1-x-x. It may be the brittle marker read as a slow.

### Glue Gunner

**Matches.**
- Corrosive Glue: 1 dmg per 2 s for 11 s.
- Bloon Dissolver: 1 per 0.5 s.
- Bloon Liquefier: 1 per 0.1 s (110 in total).
- Solver: 8 globs/s.
- These rates agree.

**Missing or wrong.**
- F1: **no source at all** on the middle path, the bottom path to tier 4, and tier 0-1. Super Glue is rated as a 1-damage dart.
- F7:
  - Solver is ×9 low on ceramics and ×5 low on MOABs; Liquefier is ×3 low on ceramics.
  - Super Glue's 30 MOAB damage is floored to 0.
  - The corrosive-soak DoT across layers is not counted.
- F6: Liquefier and Solver puddles.
- F2: Glue Strike and Storm abilities. Glue Strike lets anything pop lead and frozen for 11 s and adds +2 damage taken.
- **Glue has no camo at any tier.** The model agrees.
- Research-doc v57 changes (Splatter $650, Strike $4500, Stickier 18 s): the export has 18 s, so it matches.

### Desperado

**Matches.**
- Pistol 1.2 s with bursts of 2 / 6 / 12.
- Big Iron: lead pops at 3-x-x.
- Deadeye rifle: 10 dmg, 4 pierce, +10 fortified at 0-3-0.
- Bounty Hunter: +10 ceramic or fortified.
- Golden Justice: rifle 280 (+280) every 3.18 s; pistol 24 (+24 ceramic) plus an explosion of 8 pierce.
- Avenger and Desert Phantom pistol and shotgun damage.

**Missing or wrong.**
- F4: the pistol (40) and the shotgun (36) get the tower's 80 / 60 circle. Over-credit ×1.7-2.
- F8: the shotgun is treated as radial. Under-credit about 2×; this partly cancels F4.
- F5: Golden Justice's infinite-pierce line is read as one 28-unit blob.
- F6: The Blazing Sun's fire, and the Desert Phantom shrapnel fire.
- F3: Bounty marks give 2× damage from Desperados.
- F13: burst timing, and the Standoff / Quickdraw / Wanderer / Nomad / Bullseye modifiers.
- F2: Take Aim, which works as a support MIB / camo for one tower, and Marked to Pop.
- F1: Enforcer to Desert Phantom knockback, MOABs from x-x-4.

---

## 3. Verified numbers (the model agrees with the wiki)

All profile numbers, for every tower × 51 crosspaths, are in the scratch dump. Spot checks against the "Full Popology" sections:

| Crosspath | Model | Wiki | OK |
|---|---|---|---|
| Dart 0-3-0 | 3 darts / 0.477 s, 2 pierce | 3 per shot, 0.47475 s, 2 pierce | yes, except radial (F8) |
| Dart 0-0-4 | 2.11/s, 6 dmg, crit averaged to 11.4 | 0.475 s (wiki has 0.6 s in its header, stale), crit 50 every 10th | yes |
| Dart 0-0-5 | 4.21/s, 8 pierce, 22.4 dmg | 0.2375 s, 8 dmg, 80 crit every 5th | yes |
| Dart 5-0-0 | 210 / 50 pierce; 5 / 2 dmg; two splits | "splits twice into 6" | yes |
| Boomerang 5-0-0 | orbit 20/s, 200 pierce, 4 (+4) | 0.05 s, 200 pierce, 4 (+4) | yes, except coverage (F4) |
| Bomb 0-5-0 | +99 MOAB, 22 pierce | +99, 22 pierce | yes, except ability |
| Bomb 5-0-0 | 24 dmg, 80 pierce, 1.5 s | same | yes, except stun |
| Tack 5-0-0 | ring 0.1 s, 8 (+4 MOAB); meteor 700, global | same | yes |
| Tack 0-0-5 | 143 tacks/s (32 / 0.224) | same | yes |
| Ice 5-0-0 | 1.56 s, 5 (+5 ceramic) | v56 cooldown 1.56 s | yes, except brittle |
| Ice 0-0-5 | 2 dmg, +48 MOAB, 0.75 s | same | yes, except icicles and freeze |
| Glue 5-0-0 | 8 globs/s, DoT 1 per 0.1 s | 0.25 s × 2 globs, 1 per 0.1 s (×9 ceramic, ×5 MOAB) | partly: tag DoT missing |
| Desperado 0-5-0 | rifle 280 + 280, 3.18 s | same | yes, except line (F5) |

---

## 4. Heroes: Quincy and Obyn

**The model rates both at zero.**
- Hero levels exist in `attacks.json` (`heroes.<id>.levels.1-20`).
- No code path flattens them: `forecast` and `optimize_builds` drop `kind == "hero"`, and the optimizer notes "hero: not counted by the model (extra safety)".

**What a flattening would show** (dps_model's own `_flatten_attack` run on the export):

### Quincy

**Main arrow by level.**
- L1: 1.05 shots/s, 3 pierce, 1 dmg, sharp.
- L5: camo.
- L7: exploding arrow every 2nd shot.
- L10: +2 MOAB.
- L20: 15 shots/s, 9 pierce, +3 MOAB.

**Gaps if heroes are added.**
- **Two weapons, `BaseProjectile` and `LongProjectile`, would both be counted.** The second is almost certainly the v57 Lv4 Focus mode, which gives +20% range and 20% slower fire (fandom:Quincy_(BTD6) and the v57 notes). It is an alternative, not a second arrow, and would double Quincy [UNVERIFIED: which weapon is which].
- Ricochet: up to 3-9 targets within 50 units of each other. This is `bounces` in the export, and it is ignored (F5).
- The exploding arrow is the F9 alternate pattern.
- Abilities are missing: Rapid Shot (Lv3) and Storm of Arrows (Lv10, range 100 around Quincy's target).

**Role.** Quincy carries the CHIMPS early game: rounds 6-24 camo at L5, and "with Rapid Shot, he is able to solo all pre-Round 40 camos" (fandom:Quincy_(BTD6)).
- **Under-credit:** today the optimizer buys extra towers for early camo rounds that Quincy covers.

### Obyn

**Main attack.** Spirit wolves with **moderate seeking**: 1.35 s → 0.5 s, 4 → 14 pierce, 2 → 8 dmg, purple immune.

**Missing from the model.**
- Nature's Ward Totem (L4): a 30-60% slow near the track, 15-30% on MOABs. It is F1-type and not counted.
- Brambles (L3 ability).
- Wall of Trees (L10 ability: 2500 / 7500 RBE).

**Support the export already has but the model never applies, because the hero is not in `placed`.**
- L2: Druids and Skywardens in range get +1 pierce.
- **L8: Druids and Skywardens in range get camo** (the export's `camo` buff, towers `Druid`, `Skywarden`).
- L11: magic towers get +2 pierce and range.

**Support missing from the export itself.**
- **L5: x-3-x Druids on screen get +40% range and +50% income** (fandom:Obyn_Greenfoot_(BTD6)). This is not among the exported buffs, so even putting the hero in `placed` would not apply it.

**Effect on the owner's Druid line (research doc section 7).**
- The planner thinks a 1-3-0 Druid next to an L8+ Obyn has no camo.
- So it either buys a $3,725 Radar Village it does not need or rejects the plan.

**Fix.**
1. Give heroes a `Placed` entry with a level estimate: `abilities.py` already estimates hero level from XP, pessimistic and optimistic.
2. Flatten `heroes.<id>.levels[L]` with the same machinery.
3. At minimum, apply hero `buffs` (camo, pierce) to towers. That needs no damage model and only helps.
4. Add Obyn's L5 Druid range buff to the export.

---

## Appendix A. Druid of the Jungle (1-3-0), the owner's example

**Model** (`profile('druid','130')`):
- `is_global=True`.
- `JungleVine>Collidable`: global, 0.385 shots/s (rate 2.6 s), pierce and damage 9,999,999, reach 0 (one bloon), no camo, MOABs excluded. It instakills a whole bloon and its children through overflow.
- `JungleVine>Projectile` (the bramble): global, 0.385/s, 20 pierce, 1 dmg, reach 20.
- Thorns: aimed, 7.27 shots/s, range 35.

**Game** (fandom:Druid_of_the_Jungle):
- The vine is global, ignores line of sight, takes no camo, and grabs any bloon up to ceramic. **The global flag and the one-bloon vine are right.**
- **But the vine's cooldown is the larger of 2.6 s and a digestion time**: (√(lives the bloon would cost) + 1) ÷ 4 + 1.4 s.
  - A ceramic is worth about 104 lives, so its digestion is about 4.2 s.
  - The model's 0.385 grabs/s is therefore **about 1.6× too high on ceramics**, the R63 / R76-type threats.
  - It is right for small bloons.
- The bramble lasts 4.5 s and damages "every 0.3 s with 20 pierce per contact tick": up to 15 × 20 = 300 hits on bloons walking through.
  - The model caps one bramble at 20 hits (`pierce_refresh` sets `single_hits` but `per_shot = min(pierce, …)`), and gives it a 20-unit reach instead of "lies on the track".
  - This is an **under-credit of up to 15×** on dense lanes.
- Obyn L5 (+40% thorn range) and L8 (camo) are not credited (section 4).

**Fix.**
1. Add a digestion term to the vine's rate per target layer: rate = 1 / max(2.6, (√leak + 1)/4 + 1.4).
2. Treat a `static` spawn with `pierce_refresh` as `placement="track"`, with pierce × lifespan ÷ refresh hits, banked for its 4.5 s lifespan.

---

## Appendix B. Not verified

- **Burst timing** for Desperado (F13): whether `rate` already includes the time between burst shots.
- **The Blazing Sun fire** and **Desert Phantom shrapnel fire**: where the game keeps them. They are absent from the export.
- **Quincy's `LongProjectile`**: is it the Focus mode, or a long-range alternative?
- **Embrittlement's exported slow of 1.0** against the wiki's Permafrost 50%.
- **Glue 3-1-0 / 3-0-x** ceramic +2 on a 0-damage hit: an export placement artifact?
- **All Reddit claims.** Reddit JSON endpoints returned empty. The "Super Brittle underrated" and "Embrittlement decamos DDTs for R95/R99" views come from search snippets and the wiki's own strategy text.
- **Every [EST] multiplier** (slow ×1.5-2, orbit ×1.4-1.7, ability duty cycles) is a back-of-envelope figure. Replay calibration (`optimize_builds.py --calibrate`) should confirm each fix before the safety margin is changed.

---

## Top 10 fixes, by CHIMPS and Impoppable impact

1. **Model status effects (F1).** Slows, MOAB slows, freeze and stun extend downstream time-in-zone. Effect-only projectiles become sources, and tower `zones` are read. This brings back Glue, Arctic Wind, Super Glue, Bloon Crush and Icicle Impale.
2. **Export and credit abilities by duty cycle (F2):** Super Maelstrom, MOAB Eliminator and Assassin, Glue Strike and Storm, Snowstorm and Absolute Zero, Turbo and Perma Charge, SMFC and PMFC. Only the ones `abilities.py` actually presses.
3. **Bloon debuffs as station-level buffs to later stations (F3):** Embrittlement +1, Super Brittle +4, Glue Strike +2, decamo and degrow.
4. **Give each source its own zone (F4).** This fixes the Glaive Lord orbit and Desperado pistol and shotgun over-credit, and Heavy Kylie's under-credit.
5. **Hidden range (F5):** Glaive Lord seeking (global-ish), Ricochet and M.O.A.R. bounce (+60 / +180), Absolute Zero Ultrafreeze as global, Golden Justice as a line.
6. **Export bloon-pop spawns (F6):** Ice Shards, Icicles, acid puddles, and Blazing Sun fire.
7. **DoT fixes (F7):** at least one tick when the lifespan is shorter than the interval (Super Glue 30 MOAB); DoT tag bonuses (Liquefier ×3 ceramic, Solver ×9 ceramic and ×5 MOAB); corrosive soak across layers.
8. **Put heroes on the board (F12, section 4):** apply hero buffs at once (Obyn's camo and pierce for Druids; add the L5 range buff to the export), then flatten hero attacks, with Quincy's Focus weapon counted as an alternative.
9. **Spread and alternate fixes (F8, F9):** only call an emission radial when its arc is 180° or more (Triple Shot, SMFC, PMFC and the Desperado shotgun go about ×2 up). Alternate projectiles replace the main shot (Recursive Cluster down about 24%).
10. **Over-credit clean-up (F10, F11, appendix A):** freezes block sharp damage; frag `extra_pierce_cost`; the Druid of the Jungle vine's digestion cooldown (about 1.6× too high on ceramics) together with the bramble as a track pile with pierce refresh.
