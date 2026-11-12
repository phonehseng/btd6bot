# Damage-model audit: Military towers, Etienne and Brickell (2026-11-12, game 57.4)

This is a read-only audit. No code was changed.

**Scope.**
- Towers: Sniper Monkey, Monkey Sub, Monkey Buccaneer, Monkey Ace, Heli Pilot, Mortar Monkey and Dartling Gunner.
- Heroes: Etienne and Admiral Brickell, as far as the model rates them.

**How the audit was done.**
- Every crosspath of the seven towers was printed from `dps_model.profile()`, run from the repo root. That is all 64 crosspaths per tower; the export has every legal crosspath.
- The printout covers each source's shots/s (crowd and single), pierce, damage, immunities, camo, bonuses, placement, reach and range.
- Each profile was compared with three things:
  - the raw entry in `data/game_model/attacks.json`;
  - the code paths in `btd6bot/dps_model.py` that read that entry;
  - the wiki.
- The wiki pages were read in full as wikitext, through `api.php`:
  - Fandom (`bloons.fandom.com`): Statistics, crosspath interactions, Tips and Strategy, for about 130 upgrade pages.
  - bloonswiki.com, which answered this time: Pre-emptive Strike, Advanced Intel, Cripple MOAB, Mortar, Spectre, Dartling, Elite Defender, Carrier Flagship and Navarch.
- To weigh impact, the bot's own builds were counted: the final crosspaths of every military tower in `strategies/**/*.yaml` (section 0).

**What could not be read.**
- **Reddit:** `old.reddit.com/r/btd6/search.json` and `www.reddit.com` both returned HTTP 403.
- **bloons.wiki:** did not resolve.
- Community views below come from web-search snippets and are marked as such.

**Links and marks.**
- `fandom:<Page>` means `https://bloons.fandom.com/wiki/<Page>`.
- `bw:<Page>` means `https://www.bloonswiki.com/<Page>`.
- **[UNVERIFIED]** means no fetched source confirmed the claim.
- **[EST]** means my own estimate.

Many Fandom stat blocks say "Updated as of 40-51". Where a later patch note or the export disagrees, the export (57.x game data) wins.

---

## 0. Short answer

Most raw numbers are right. Rates, pierce, damage, damage types, camo per tier and the tag bonuses match the wiki for nearly every crosspath (section 3).

The ratings are still badly off. The causes are how sources are placed, what is counted in parallel, and what is thrown away:

1. **Bomber Ace bombs are counted on the whole map at full rate** (over-credit, about 3-10×).
   - The game drops them only while the plane flies over the track, and only under the plane.
   - In the model, about 91% of a 2-3-0 Ace's rated throughput is these bombs.
   - The 2-3-0 Ace is the bot's second most-built military crosspath (193 builds).
2. **Every Mortar and every aimed Dartling is rated zero.**
   - That covers every Mortar crosspath, and every Dartling except x-x-4 and x-x-5.
   - So the optimizer cannot see Pop and Awe, The Biggest One, Signal Flare decamo, Plasma Accelerator, Ray of Doom or M.A.D. M.A.D is the research doc's best non-ability answer to the R100 BAD.
3. **Stuns and the cripple debuff are not modelled.**
   - Maim MOAB keeps a MOAB permanently stunned and a BFB stunned about 94% of the time.
   - Cripple MOAB adds +5 damage taken from every source.
   - 4-2-0 is built 181 times.
4. **Things that are really alternatives are counted in parallel** (over-credit, up to about 2×):
   - **Sub Airburst splits.** The export lists one spawn "on exhaust" and one "on expire"; both are counted.
   - **Buccaneer back-shots.** The rear copy fires only when bloons are behind the boat.
   - **Spectre and Flying Fortress barrage.** It alternates darts and shells; the darts are counted at the full rate.
   - **Submerged subs.** Their darts are counted, but a submerged sub does not shoot darts.
5. **Helis locked in place are credited as map-wide.**
   - The bot sets every heli below 2-x-x to Lock in Place (`strategy.py _aim`).
   - The model treats every heli as following the bloons over the whole map.
6. **Hidden reach is cut off.**
   - Sniper Bouncing Bullet and Supply Drop bounces: only 1 of the 3-5 hits is counted.
   - Neva-Miss homing darts get the 0.4 "circling plane" penalty.
   - The Ace's flight circle is 80 in the game, not 40. From 0-0-2 on, the Ace circles the *map centre* by default, not its runway.
7. **Whole attacks and buffs are missing from the export.**
   - Attacks: Pre-emptive Strike's 750-damage missile on every blimp, the Comanche Defense mini-helis.
   - Buffs: the Sub Commander ×2 damage and +4 pierce aura, the Carrier Flagship attack-speed buff, the Etienne UAV global camo (the export has it, but heroes are skipped), the Brickell +1 pierce aura (same).
   - All abilities, although the bot fires them on cooldown.

**What the bot builds (final crosspaths, all strategy files):**
- Sniper: 1-2-0 ×378, 4-2-0 ×181, 3-2-0 ×94, 0-2-2 ×87, 0-2-4 ×59, 1-3-0 ×59, 2-3-0 ×59, 2-2-0 ×55.
- Ace: 2-3-0 ×193, 1-3-0 ×51, 0-1-0 ×24, 2-4-0 ×17.
- Buccaneer: 2-0-2 ×81, 2-0-1 ×77, 3-0-2 ×49, 0-3-2 ×43, 4-0-2 ×36.
- Sub: 2-0-4 ×78, 2-0-3 ×53, 4-2-0 ×51, 4-0-2 ×39, 2-3-0 ×33.
- Heli: 3-0-2 ×47, 3-2-0 ×28, 4-2-0 ×21, 4-0-2 ×19, 1-0-2 ×11.
- Mortar ×8, Dartling ×9 (placements).

The two counts near the top fit an over-rated Bomber Ace and an invisible Mortar and Dartling.

---

## 1. Findings, ranked by impact on CHIMPS and Impoppable

### M1. Bomber Ace, Ground Zero and Exploding Pineapple bombs are counted on the whole map (huge over-credit)

**Tower.** Ace 0-1-x, 0-3-x, 0-4-x, 0-5-x and every crosspath with them: 2-3-0, 1-3-0, 2-4-0, 0-1-0, 3-2-0 and so on.

**Model.** `PineappleBombs>Explosion` is placement **global** with reach 86, at full rate:

| Crosspath | Bombs/s | Pierce | Damage |
|---|---|---|---|
| 0-1-0 | 0.62 | 20 | 1 |
| 2-3-0 | 3.33 | 20 | 3 |
| 2-4-0 | 3.33 | 40 | 15 |

- The attack is `air: true`, `unbounded: map`, so `_flatten_attack` makes it "global".
- Throughput (shots × pierce × damage) for 2-3-0: bombs 200, darts 19 (after the 0.4 air factor). The bombs are **91%** of the rating.
- For 2-4-0: bombs 2000, darts 19.

**Game.**
- **Bomber Ace** drops an array of 4 bombs (over 0.68 s, every 1.6 s, or 1.2 s with 1-x-x) under the plane. The weapon carries `CheckAirUnitOverTrackModel`: it fires **only while the plane is over the track**. The export already writes this as `over_track_only: true`, but `dps_model` never reads it.
- **Pineapples** (0-1-0) drop under the plane wherever it is, track or not. They explode after 1.5 s with a 25 blast radius. The Targeted Pineapples MK limits them to the track.
- The plane flies a circle of radius 80 around the runway (default flight Circle).
- Sources: fandom:Bomber_Ace, fandom:Exploding_Pineapple, fandom:Tsar_Bomba (statistics), `tools/export_attacks.py` lines 581-615.

**Effect.** Over-credited by roughly the inverse of the share of the flight circle that lies over the track. That share is about 10-30% on most maps [EST], so the over-credit is **3-10×** on the Bomber Ace line.
- The bombs also hit only the stretch of track under the circle, not the whole map.
- Ground Zero's 15-damage, 40-pierce bombs make 2-4-0 look like a whole-map carry.
- This is the single largest over-rating in this group. It probably explains the 193 Bomber Ace builds.

**Fix.**
1. Read `over_track_only`. Such a weapon is an "air" source.
   - Its zone is the track within its blast radius of the flight curve.
   - Its rate is multiplied by the share of the flight curve that lies within blast radius of the track. That is a geometry query on `Track`.
2. Give pineapples the same zone, with the rate multiplied by the share of drop points within 25 of the track.
3. Leave Fighter Plane and Sky Shredder anti-MOAB missiles global (they seek blimps; see M15).

---

### M2. Mortar and aimed Dartling are rated zero (huge under-credit)

**Tower.**
- Mortar: all 64 crosspaths.
- Dartling: every crosspath except x-x-4 BADS and x-x-5 BEZ.

**Model.** No sources at all, and `aim_bound=True`.
- `_flatten_attack` returns early for targeting "point" or "cursor".
- The docstring says the bot cannot aim them.

**Game.**
- **Mortar.** Shells land around a fixed reticle the player sets.
  - Deviation radius is 18, or 8 with Increased Accuracy (x-x-1).
  - Base blast radius is 20 with 25 pierce (fandom:Mortar_Monkey_(BTD6)).
- **Dartling.**
  - Darts deviate ±11.5° (±4.8° with Focused Firing) and fly across the entire map.
  - It has a **Locked** targeting option that fixes the aim on a point; the bloonswiki page says all Dartlings have it (bw:Dartling_Gunner_(BTD6)).
  - Plasma Accelerator and Ray of Doom fire beams through the point (Ray of Doom: "nearly endless").
  - M.A.D missiles deal +450 to blimps (fandom:M.A.D).
- **Upgrades that matter in CHIMPS:**
  - Pop and Awe: a permanent 0.0675 s attack, plus an ability that stuns everything except BADs 8 times in 8 s.
  - The Biggest One: 200 pierce, 25 damage (+30 to Ceramic and MOAB), 74 radius, plus stun waves.
  - Signal Flare: decamo in a 52 radius.
  - Shattering Shells: removes camo, regrow and fortified.
  - Blooncineration: 100 damage per 0.75 s burn on blimps.
  - Sources: fandom:The_Biggest_One, fandom:Pop_and_Awe, fandom:Signal_Flare, fandom:Shattering_Shells, fandom:Blooncineration, fandom:Plasma_Accelerator, fandom:Ray_of_Doom.

**The bot already half-supports aiming.**
- `Match._park_cursor` rests the cursor on the busiest track cell for Dartlings.
- No code sets a Mortar reticle: there is no "Set Target" anywhere in `btd6bot/`.

**Conflict on the Dartling default.**
- The Fandom version history says "Dartling Gunner now comes with Locked targeting by default". If that is right, its lock point defaults to the map centre, and cursor parking does nothing.
- `strategy.py` assumes "Dartlings keep Follow Touch".
- [UNVERIFIED which is true in 57.4. Check in game once.]

**Effect.** Under-credited from 100% of their value to zero.
- In particular, the optimizer can never pick M.A.D or Ray of Doom for R95-R100, or a Mortar for decamo or defortify.

**Fix: credit a fixed aim.**
1. Add a "point" placement. The aim point P is chosen per tower, like `_park_point`: the track cell with the most track within radius R.
2. **Mortar.**
   - Zone: the track within (deviation + blast radius) of P.
   - Per shell: expected hits = rho × (expected track length inside a blast disc that lands uniformly in the deviation disc), capped by pierce.
   - Apply only when P is reachable. A mortar has map-wide range but needs line of sight [UNVERIFIED].
3. **Dartling.**
   - Zone: the track inside the firing cone (tower → P, ± deviation) out to the projectile travel. For Locked aim, that travel is the map.
   - Per dart: reach = the length of the cone's centre line that runs inside the track's width.
   - Beams (Plasma Accelerator, Ray of Doom): the same zone, with beam width 2-9 and the export's pierce.
4. Have the executor set Mortar targets, and set Dartlings to Locked on P. That makes the model and the game agree.
5. Until then, rate them at the point the bot really uses (map centre or the cursor-park point), never at zero.

---

### M3. Stuns and the cripple debuff are thrown away (large under-credit on blimp rounds)

**Tower.** Sniper 4-x-x Maim MOAB and 5-x-x Cripple MOAB, with shrapnel at 66% duration on x-2-x. The same applies to:
- Heli MOAB Shove (x-x-3+): blimp knockback.
- Heli Downdraft (x-3-x): blowback.
- Mortar Shell Shock and The Biggest One stun waves.
- Ace Tsar Bomba (ability, 8 s stun).
- Brickell Mega Mine (5 s or 10 s stun).

**Model.**
- The export carries `effects.maim` (MOAB 7 s, BFB 6, ZOMG 3, DDT 4, BAD 0.75) on Cripple MOAB. `dps_model` reads no `effects`.
- Sniper 4-2-0: one 30-damage bullet per 1.59 s, rated as damage only.

**Game.**
- **Maim MOAB** stuns MOABs 3 s, BFBs 1.5 s, ZOMGs and DDTs 0.75 s per hit (fandom:Maim_MOAB).
- **Cripple MOAB** stuns 7/6/3/4 s, and debuffs a BAD for 0.75 s. While a blimp is crippled it takes **+5 damage from every source** (bw:Cripple_MOAB_(BTD6)).
- The Cripple debuff reaches full uptime on a BAD with 5-0-2 plus Jungle Drums or Berserker Brew (same page).
- **MOAB Shove** pushes blimps backwards (fandom:MOAB_Shove):
  - MOAB −130%, BFB −90%, ZOMG and DDT −39%;
  - Comanche Defense: −140% / −100% / −80%.

**Effect.**
- One 4-0-0 Sniper on Strong, at a 1.59 s cooldown:
  - keeps a lone MOAB at 3 s / 1.59 s, which means permanently stunned;
  - keeps a BFB stunned about 94% of the time;
  - keeps a ZOMG or DDT stunned about 47% of the time.
- Every other tower gets that much more exposure time. On R40-R80 blimp waves that is often worth more than the sniper's own damage.
- The +5 cripple debuff multiplies the damage of fast low-damage hitters: Spectre darts, sub darts, Sky Shredder darts and Elite Defender all deal 2-8 per hit. On R100 this can be +60-200% on the BAD for such towers [EST].
- These are all **under-credited**. Ranked third here only because the model is meant to be "safe side". The owner's complaint is exactly this.

**Fix.**
1. Model stuns as **stall time**. For each blimp lot, a station with stun effect s and rate r adds a stun share min(1, r_hits × duration). That stretches every station's exposure time for that lot.
   - A cheap first step: lengthen the zone time of MOAB-class lots by 1/(1 − stun share) for all stations downstream of the stunner.
2. Model the cripple debuff as a +5 "add" bonus on Moabs for every source, while the uptime share holds.
3. Read knockback the same way. MOAB Shove: a negative speed share while the heli is within reach.

---

### M4. Sub Airburst splits are counted twice (over-credit, about 1.6-1.8×)

**Tower.** Sub x-x-2 and up: 2-0-4, 2-0-3, 2-0-2, 4-0-2, 0-3-2, 0-1-3 and so on (about 250 builds).

**Model.** Two sources named `AirburstSplit`, each with the full split count. For 2-0-4: 11.94 shots/s twice, pierce 5.
- In the export, one spawn is `on: exhaust` and the other `on: expire`.
- `_flatten_projectile` adds both.

**Game.**
- "Upon collision with bloon, produce Airburst": 3 darts, or 5 with Sub Commander.
- The main dart is a 1-impact projectile (fandom:Airburst_Darts, fandom:Sub_Commander).
- A dart either hits (its pierce is exhausted) or flies out (its lifespan expires). The two spawns are alternatives.

**Effect.** Airburst is 88% of 2-0-4's crowd throughput and 75% of its single-target throughput. Halving it cuts the 2-0-4 rating by about 44% (crowd) and 37% (single).
- The main dart is also credited pierce 2. The export says `max_pierce 1`; the wiki says "1 impact".

**Fix.**
- When a projectile has an `exhaust` spawn and an `expire` spawn of the same projectile, count only the exhaust one. The model assumes no misses, so a miss never happens.
- Use `max_pierce` when it is lower than `pierce` for Impact darts.

---

### M5. Buccaneer rear shots are counted as always firing (over-credit up to 2×)

**Tower.** Every Buccaneer (about 500 builds), above all the cheap 2-0-1 and 2-0-2 boats.

**Model.** Each weapon appears twice ("Weapon" and "Weapon Secondary", the same for Grape Shot and Cannon). The secondary is fired at the primary's rate (`_trigger_rates`).
- For 2-0-2: two dart sources at 2.67 shots/s each.

**Game.** "Can shoot a second copy of *Dart* at 180° from first *Dart* **if bloons are detected behind**." The same holds for grapes and cannonballs (fandom:Grape_Shot_(BTD6), fandom:Cannon_Ship_(BTD6), fandom:Destroyer_(BTD6)).
- The rear copy needs bloons in the half of the range circle behind the boat, as seen from the current target.

**Effect.** Over-credited ×2 when the boat sees track on one side only, which is typical for a shoreline spot. It is right when the boat sits between two lanes.

**Fix.** Scale each "Secondary" weapon of a Buccaneer by the share of time a second target exists behind the boat.
- First step: 1 if the zone has track in two opposite half-planes (two lanes on opposite sides), else 0 [EST].
- Better: min(front, back) / front, using covered track length per half-plane.

**Verified (no fix needed).** Cannon Ship "replaces its ordinary dart attack". The model already drops the darts at x-3-x, because the dart primary is missing in the export.

---

### M6. Helis locked in place are credited as map-wide (over-credit); pursuit and the extras are flattened (mixed)

**Tower.** Every Heli. The bot sets **Lock in Place** below 2-x-x and **Pursuit** from 2-x-x (`strategy.py HELI_PURSUIT_TIER = 2`).

**Model.** `air_unit.movement == "follows"`, so every heli attack is placement "global", the whole track at full rate.
- Examples: 1-0-2 (11 builds), 0-2-4, 0-0-4.

**Game** (fandom:Heli_Pilot_(BTD6), fandom:Pursuit_(BTD6), fandom:Comanche_Defense, fandom:Comanche_Commander, fandom:Special_Poperations, fandom:Downdraft).
- **Lock in Place:** the heli stays on its point. Darts reach 42, or 54.6 on the bottom path.
- **Pursuit:** follows the *first* bloon, flying at 40-87.5 units/s. It fights in one bubble at the front, not along the whole track.
- **Bottom-path helis cannot Pursue without 2-x-x.** So 0-2-4 and 0-2-5 helis are locked by the bot.
- **Mini-Comanches are missing from the export.**
  - 0-0-4 summons 1, 2 and then 3 mini-helis at 25%, 50% and 75% track progress, each for 15 s, once per round.
  - 0-0-5 has a permanent wave: spray of 3 darts every 0.228 s, 3 damage, 4 pierce, plus missiles.
- **Special Poperations Marine** (ability, 25 s cooldown, 30 s life, so always present): 6 damage, 20 pierce, every 0.04 s, camo, lead. Not modelled.
- **Downdraft:** blowback of 2 bloons per 0.2 s, 32-150 units. Not modelled. That is stall time, an under-credit. Note that blowback also undoes glue and ice.

**Effect.**
- A locked 0-x-x or 1-x-x heli is over-credited by roughly (whole track) / (track within 42-55 of the lock point). That is often **5-20×** [EST].
- Pursuit helis are over-credited mildly on spread rounds [EST].
- Comanche 0-0-5 and Special Poperations are under-credited a lot.

**Fix.**
1. Pass the planned targeting into `profile`/`station_for`. Locked means radius = attack range around the placement (or lock) point. Pursuit stays global.
2. Comanche: add mini-Comanche sub-towers from the game model. Their stats are on the wiki pages above; re-export the subtower.
3. Marine: add it as a permanent sub-tower once abilities are modelled (M10).

---

### M7. Sniper bounces are dropped (under-credit on dense rounds, 1.5-2.5×)

**Tower.** Sniper x-3-x Bouncing Bullet, x-4-x Supply Drop, x-5-x Elite Sniper: 1-3-0, 2-3-0, 2-4-0, 2-5-0, 0-3-2 (about 180 builds).

**Model.**
- The bullet has `target_only` and reach 0, so `_bloons_met` returns 1. Pierce 3 or 5 is capped to **1 hit**.
- Shrapnel is spawned for min(pierce, 2) contacts.
- The export field `bounces: 1000000` is never read.

**Game.**
- The bullet bounces to the nearest bloon within 40 units (80 with x-2-x Large Calibre). It hits 3 bloons at x-3-x and 5 at x-4-x and x-5-x.
- **Each bloon hit** releases 5 shrapnel (fandom:Bouncing_Bullet, fandom:Supply_Drop_(BTD6)).

**Effect.**
- Under-credited on packed rounds: 3-5 bullet hits instead of 1, and 3-5 shrapnel sprays instead of 2.
- For 2-4-0 (7-damage bullet) the bullet part is under-rated up to 5× and the shrapnel 2.5×.
- Correct on lone bloons.

**Fix.** For bullets with `bounces`, set reach to about 2 × bounce radius (40 or 80). Use `_bloons_met` with pierce as the cap. Count shrapnel per bullet hit (up to pierce), not CONTACTS_PER_CARRIER.

---

### M8. Spectre and Flying Fortress: barrage darts doubled, homing darts halved, wrong flight circle (mixed)

**Tower.** Ace 0-0-4 Spectre, 0-0-5 Flying Fortress, 2-0-4, 0-2-4, and in part every ace at x-x-2 and up.

**Model.**

| Crosspath | Barrage darts | Shells | Neva-Miss darts |
|---|---|---|---|
| 0-2-4 | 16.67/s, pierce 4, damage 6 | 8.33/s, pierce 30, damage 3 (+4 Ceramic) | 4.76/s, pierce 8, damage 3 |
| 0-0-5 | 25/s in each of 3 streams | 12.5/s in each stream | |

- Barrage darts and shells: placement **global**, no AIR_PATTERN_EFFICIENCY.
- Neva-Miss darts: placement "air". They get ×0.4 and the zone's angular share.
- `pattern_radius` is 40 for every ace.

**Game.**
1. **The barrage "alternates between launching Dart and Shell"** every 0.06 s (0.04 s on Flying Fortress). That is 8.33 darts and 8.33 shells per second on Spectre (fandom:Spectre_(BTD6), bw:Spectre_(BTD6)).
   - The export has `alternate: {every: 2, count: 1}`.
   - `_flatten_attack` adds the alternate shells *on top of* the full-rate darts. It should take 1/every of the shots away from the darts.
   - This is the systemic "alternate projectile" bug, F9 in docs/model_audit_primary.md.
2. **The barrage is locked to First, with infinite range and weak homing.**
   - Global placement is right for *where* it can hit.
   - It does miss on fast late bloons ("may still miss bloons due to the long travel time of its projectiles", Strategy section of fandom:Spectre_(BTD6)).
   - So AIR_PATTERN_EFFICIENCY should **not** apply. An accuracy factor of about 0.7-0.85 past R80 is a reasonable [EST].
3. **Neva-Miss darts home aggressively and "practically never miss"** (fandom:Neva-Miss_Targeting_(BTD6)).
   - The 0.4 radial-spray factor, and the zone's angular share, should not apply from x-x-3 on.
4. **Flight circles** (fandom:Monkey_Ace_(BTD6), fandom:Centered_Path):
   - Circle (the default) has radius **80**. Figure-Eight and Figure-Infinite have 40+40. Centered Path has 90.
   - **Upgrading to x-x-2 sets the Ace to Centered Path automatically.** Its centre defaults to the **map centre**, wherever the runway is.
   - The model uses 40 around the runway for every ace.

**Spectre and Centered Path: how much track it covers.**
- The barrage reaches the whole map (First, infinite range). Centered Path only changes the shooting angle and the projectile travel time.
- The Neva-Miss darts and pineapples work around the 90-radius loop.
- On most maps the default loop is "too big ... without micromanagement" to stay above the track. The wiki advises placing the centre so the Ace flies ahead of the bloons (search snippet of the Spectre strategy section).
- So: barrage about 0.7-0.9 accuracy anywhere [EST], and Neva-Miss darts about 0.8-1.0 of their hits within about 90 + 100 of the loop centre [EST]. The model gives the barrage 1.0 and the darts 0.4 × angular share.

**Effect.**
- Barrage darts over-credited **2×**. That is about 35% of Spectre's single-target rating and 15% of crowd.
- Neva-Miss darts under-credited about **2.5×**.
- The local part of the station sits at the wrong place (runway ± 62 instead of map centre ± 90).
- The net is roughly a wash in crowd terms. Single-target and DDT/MOAB answers are over-rated. The 0.4 also wrongly under-rates Neva-Miss 0-0-3.

**Fix.**
1. In `_flatten_attack`, a weapon with `alternate` gives its primary `shots × (1 − count/every)`.
2. Skip the 0.4 and the angular factor for seeking projectiles (`motion: seeking` with large lifespan) from x-x-3 on.
3. `pattern_radius = 80` for Circle. For x-x-2+, centre the pattern on the planned Centered Path point. Default: the map centre; better, let the bot set it at the densest track.

---

### M9. Heroes rated zero: Etienne's UAV camo and Brickell's pierce are in the export but unused (under-credit for camo and water builds)

**Model.** Heroes are skipped everywhere: `forecast.py` line 144, and `optimize_builds.py` "hero: not counted by the model".
- The export (`attacks.json heroes`) holds:
  - Etienne Lv8+: a `UAVSpawner` subtower with `buffs: [{kind: camo, global: true}]`.
  - Etienne: a range buff of +10%.
  - Brickell Lv4+: `buffs: [{kind: pierce, value: 1}]` for water towers in range.

**Game.**
- **Etienne Lv8 UAV:** "All non-Paragon towers on screen will now receive external camo detection" (fandom:Etienne_(BTD6)).
  - UCAV ability (Lv10): 10 missiles every 0.6 s, 2 damage, 25 pierce, infinite range, 18 s, 90 s cooldown (75 s from Lv13).
  - Lv20: permanent UCAV.
- **Brickell** (fandom:Admiral_Brickell_(BTD6)):
  - Lv4: +1 pierce to water towers nearby, always on.
  - Naval Tactics: water towers ×1.5-2 attack speed; normal type at Lv5; camo at Lv8; global at Lv19.
  - Mega Mine (Lv10): 4,000 damage (11,000 at Lv20) and a 5 s stun (10 s) on the first blimp.
  - v57 reworked Naval Tactics. The wiki text is pre-v57 [UNVERIFIED current numbers].

**Effect.**
- With Etienne the optimizer still pays for Radar or Night Vision on every camo-blind carry: Apache Prime, Sky Shredder, Spectre 2-0-4, Glaive and so on.
- Or it rejects those carries. These carries are the ones the research doc pairs with Etienne.
- For CHIMPS, camo is a hard gate (R24+ and R90/95 camo), so this is a big **under-credit of whole builds**, not just a few percent.
- Brickell's +1 pierce matters for 2-0-4 subs and pierce-1 grapes: +50-100% on grapes [EST].

**Fix.**
1. Feed the hero to `station_for` as a pseudo-tower at the level the planner expects for the round. Use the hero XP curve in `docs/tower_xp.md` or the account's levels.
2. Apply its `buffs`, and collect subtower buffs: the UAV's global camo.
3. Apply Brickell's pierce buff with `buff_covers`, filtered to water towers.

---

### M10. Abilities are not modelled, though the bot fires them on cooldown (large under-credit on R95-R100)

**Tower and model.** None of these appear in the profiles. The export drops AbilityModel.

| Ability | What it does (source) | Who uses it |
|---|---|---|
| Sub First Strike (x-4-x) | 10,000 + 350 AoE, 60 s; Pre-emptive: 20,000 + 1,000, 30 s (bw:Pre-emptive_Strike_(BTD6)) | The R100 BAD answer in the research doc |
| Buccaneer MOAB Takedown (x-4-x) | Kills the strongest MOAB, BFB or visible DDT, 45 s (fandom:Monkey_Pirates_(BTD6)) | |
| Pirate Lord (x-5-x) | 6 hooks every 30 s, a ZOMG costs 3; +100% cash per hooked blimp (fandom:Pirate_Lord) | Blimp rounds; cash in Impoppable |
| Ace Ground Zero (x-4-x) | 1,000 damage to 2,000 bloons nearest the runway, 35 s (fandom:Ground_Zero_(BTD6)) | R76 and R95 |
| Ace Tsar Bomba (x-5-x) | 3,000 damage to 5,000 bloons + 8 s stun (not BAD), 35 s (fandom:Tsar_Bomba) | |
| Mortar Artillery Battery (x-4-x), Pop and Awe (x-5-x) | Pop and Awe stuns all non-BAD bloons 8× over 8 s, 20 dps, 60 s (fandom:Pop_and_Awe) | |
| Dartling Rocket Storm (x-4-x), M.A.D (x-5-x) | 15 waves of 10 missiles (fandom:Rocket_Storm, fandom:M.A.D) | |
| Heli Special Poperations (x-5-x) | Permanent Marine (M6) | |
| Sniper Supply Drop (x-4-x), Elite Sniper (x-5-x) | $1,100 / $3,000 crate, max 3 per round, 90 s; or since v57 Ammo Drop: +3 pierce, ×2 damage, normal type for 6 shots (fandom:Supply_Drop_(BTD6), fandom:Elite_Sniper) | Cash in Impoppable; Ammo Drop is minor |
| Brickell Mega Mine | M9 | |

**Effect.**
- Under-credited, heavily at tier 4-5.
- **Pre-emptive Strike's passive missile is also missing from the export.** It is not an ability: one 750-damage missile at every blimp that *enters the map*. With Sub Commander it one-shots R99 DDTs (bw:Pre-emptive_Strike_(BTD6)).
- The 0-5-x profile shows only darts and the ballistic missile.

**Fix.**
1. Model an ability as a periodic source: damage over cooldown, at the bot's firing policy (`abilities.py`), applied only on the rounds where it fires.
2. Prefer explicit "round-answer" credits for the R95-R100 checks: First Strike, MOAB Takedown and Ground Zero.
3. Re-export the Pre-emptive Strike missile (the `PreEmptiveStrikeLauncherModel` behaviour, or similar [UNVERIFIED model name]) as a blimp-only source with one hit per spawned blimp.
4. Add Supply Drop cash to `income` for non-CHIMPS modes, if the bot collects crates. [UNVERIFIED whether hover collects them, as it does bananas.]

---

### M11. Support auras missing from the export (under-credit for water and air stacks)

| Upgrade | Game effect (source) | Model |
|---|---|---|
| **Sub Commander** 0-0-5 | **+4 pierce and ×2 damage to all Subs in its 42 radius, itself included** (fandom:Sub_Commander) | `buffs` is None. Its own dart reads 2 damage (the wiki says 4 with the self-buff). |
| **Carrier Flagship** 5-x-x | All water towers and Monkey Aces on screen: attack cooldown −15 to −20% (bw:Carrier_Flagship_(BTD6); the wiki pages disagree on 15/18/20%). Platforms for land towers. | No buff |
| **Energizer** 5-x-x | −20% ability cooldown globally, −40% for water towers in range; heroes +50% XP in range (fandom:Energizer) | No buff (only matters once abilities exist) |
| **Bloontonium Reactor** 4-x-x | −15% ability cooldown for water towers in range (fandom:Bloontonium_Reactor) | No buff |
| **Trade Empire** 0-0-5 | +$10 / +$20 per Merchantman / Favored Trades, capped at 20; +1 damage to x-x-3+ Buccaneers (fandom:Trade_Empire) | Income 800 only |
| **Navarch of the Seas** (Paragon) | 10 auto-hooks on blimps below BAD; cooldown reduction for all water towers and Aces; land platforms; $3,200 per round (bw:Navarch_of_the_Seas) | Not in the export at all (Paragons are not exported) |

**Effect.**
- Sub Commander builds are under-rated about **2×** for every sub in range, including itself.
- Flagship builds are under-rated 18-25% on every water tower and Ace.

**Fix.**
- Re-export these buffs. In the game model they are `SubCommanderSupportModel`, `RateSupportModel` with a filter, and similar [UNVERIFIED class names].
- The model already applies "rate" and "pierce" buffs. ×2 damage needs a new "damage_mult" kind in `_buffed_sources`.

---

### M12. Submerge: darts counted while submerged, decamo ignored (mixed)

**Tower.** Sub 3-x-x, 4-x-x and 5-x-x: 4-2-0 ×51, 4-0-2 ×39.

**Model.**
- The darts are kept as sources at 1.33-2.67 shots/s.
- The Reactor pulse is added on top (4-0-0: 3.57/s, pierce 50, damage 1).
- The decamo pulse (`effects.removes: [camo]`, pierce 100-1050, every 1.5 / 0.28 s) gives nothing.

**Game.** "While set on Submerge targeting, it cannot attack with darts" (fandom:Submerge_and_Support_(BTD6), fandom:Bloontonium_Reactor).
- Upgrading sets Submerge automatically.
- The decamo pulse **permanently strips camo** from bloons within 52, DDTs included. Every tower downstream can then hit them.

**Effect.**
- The darts are over-credited. They are small next to the Reactor and Energizer pulse: 5-15% [EST].
- The decamo is a large under-credit on camo rounds whenever the sub sits early on the track.

**Fix.**
1. Drop the sub's "Attack" sources when a `SubmergedAttack` exists. Or take the larger of the two if the plan can choose targeting.
2. Model "removes camo" as a de-camo zone. A camo lot that crosses that zone is treated as non-camo by every later station (`order` greater than the sub's). The same mechanism serves Signal Flare and Shattering Shells (Mortar), Brickell Lv15 mines and Ice.

---

### M13. Elite Defender's distance bonus and Elite Sniper's own rate (small under-credit)

**Tower.** Sniper 0-x-5 (0-2-5 ×15) and 0-5-x (2-5-0 ×20).

**Model.**
- 0-0-5: 15.40 shots/s flat.
- 0-5-0: 1.57 shots/s, which is right: ×0.4 cooldown for itself (fandom:Elite_Sniper).
- The ×0.75 global buff to other Snipers is applied.

**Game.**
- Elite Defender attacks +1% faster per 1% of track the **furthest bloon** has reached, up to +100%.
- It also attacks ×4 for 7 s after a life is lost. That is irrelevant in CHIMPS (bw:Elite_Defender_(BTD6)).

**Effect.** Under-credited up to 2× exactly when bloons are deep in the track, which is when it matters. On a strong board it is near the 1.0 floor.

**Fix.** Scale the source's rate by (1 + the deepest progress of lots still alive). Cheap approximation: (1 + the mean entry fraction of the lots this station works).

---

### M14. Advanced Intel lending is slightly too strict (small under-credit)

**Model.** Map-wide towers lend nothing (`intel_lent_circles`): Snipers, Helis, Aces, Mortars.

**Game.** Advanced Intel uses each tower's **display range**: "it only uses the small radii of Sniper Monkeys and the landing pads of flying towers instead of their true range" (bw:Advanced_Intel_(BTD6)). That is 20 for a Sniper, 22 for an Ace or Heli pad.
- It also detects MOAB-class in a larger range ("One interesting quirk", fandom:Advanced_Intel). [UNVERIFIED how much larger.]

**Effect.** Small under-credit. The loss case that motivated the current rule is consistent with this: a 20-unit circle rarely touches the track.

**Fix.** Lend `profile.range` (the display range: 20 or 22) for map-wide towers, instead of nothing.

---

### M15. Anti-MOAB missiles, Carrier planes and MOAB bonuses (verified; small points)

- **Fighter Plane, Dart Storm and Sky Shredder missiles.** Model 0.67/s, 1.33/s, 1.33/s. Wiki: twin missiles every 4 s / 2 s / 2 s, with Rapid Fire (prerequisite of 3-x-x) ×0.75 cooldown. That works out to 0.67, 1.33 and 1.33. Correct. Global at full rate is right: they seek blimps on Strong with infinite range (fandom:Fighter_Plane, fandom:Sky_Shredder).
- **Fighter Plane missile pineapples (3-1-0 and up).** The second `Anti-MoabMissile>Explosion` source (pierce 20, damage 1) is the pineapple dropped where the missile exploded. It inherits `only: [Moabs]` from the attack. In the game the pineapple hits any bloon. Tiny under-credit. Clear `only_tags` on spawned pineapples.
- **Aircraft Carrier planes.**
  - Model: radial darts 8.00/s and forward darts 11.43/s after ×0.4, missiles 1.0/s at full rate.
  - Wiki: 3 planes; radial 8 darts every 1.2 s; forward twin darts every 0.18 s, "strongly homing", 250 range; missiles every 3 s each (fandom:Aircraft_Carrier).
  - The forward darts home aggressively. Like M8, the 0.4 is too harsh for them [EST 1.5-2× under-credit on that source].
- **MOAB-class bonuses checked:** Sniper Full Auto +2 and Elite Defender +4; Sub Armor Piercing +2 and +1 fortified; Flying Fortress +14; Apache Prime rockets +15; Pirate Lord bombs +8. All match the export.
  - Model gaps: the stunned-bloon bonus (Heavy Shells: +2 to stunned bloons) and Laser Shock's "+X from Dartlings to shocked bloons" are not read. Both towers are rated zero anyway (M2).

### M16. Verified correct, or not an issue

- **Sniper rates** 1.59 → 1.11 → 0.779 → ×3 → ×2 → ×2. **Damage** 2/4/7/20/30/140, Deadly Precision +50 Ceramic (v53), Cripple collateral 28 damage / 10 pierce / radius 8. **Camo** +2 with Night Vision. **Shrapnel** 5 pieces at pierce 2 (5 at x-4-x, 6 on Cripple) and damage 1/2/3/4/6/12.
- **Sub** rates and damage, Reactor 1 damage per 0.28 s, Energizer 5 damage per 0.28 s, Heat-tipped lead bonus. Ballistic Missile 0-5-0 at 10 damage, +15 MOAB, +20 Ceramic.
- **Buccaneer** Destroyer ×5, Grape Shot 5 grapes per 1.3 s, Hot Shot burn, Pirate Lord 8 damage +8 Ceramic grapes. Cannon Ship removes the darts.
- **Heli** Apache Prime lasers are "energy" and cannot pop Lead or Purple. That is correct per the wiki: "the lasers pop neither Purples nor Leads". Apache Dartship machine gun 1 damage / 7 pierce / 0.05 s; rotors 2/4/8 damage.
- **Ace** Sky Shredder 32 darts every 0.315 s at 3 damage +2 Ceramic. **Spy Plane** ×2 camo damage, which the export writes as "+base damage vs Camo". That is real since v31 (fandom:Spy_Plane_(BTD6)).

---

## 2. Notes per tower

### Sniper Monkey
- **Placement.** Global with line of sight (`MAP_WIDE_NEEDS_SIGHT`) on Strong. That is right.
- **Biggest gaps:**
  - M3: Maim and Cripple stun and debuff.
  - M7: bounces on x-3-x and above.
  - M13: Elite Defender's distance bonus.
  - M10: Supply Drop cash in Impoppable.
- The *most-built* crosspath, 1-2-0, is modelled about right. It is a single bullet with 5 shrapnel, and the off-struck rule already fixed the old over-credit.
- **Elite Sniper.** The ×0.75 buff to all other Snipers is modelled. The Elite targeting option is not; it has no damage effect.
- **Ammo Drop (v57):** 6 buffed shots per drop, at most 3 drops per round. Negligible.

### Monkey Sub
- **Advanced Intel (2-x-x) shared vision** is modelled sensibly.
  - It shoots camo only on paths where a camo-detecting tower reaches (`camo_paths`).
  - It borrows the other towers' circles.
  - Remaining gap: M14, the display ranges of map-wide towers.
  - The wiki adds a subtlety the model ignores: without its own camo detection, the sub's darts pass *through* camo bloons unless it targeted a camo bloon (bw:Advanced_Intel_(BTD6)). So its pierce is wasted on mixed camo and non-camo groups. Small over-credit on mixed rounds [EST].
- **First Strike and Pre-emptive Strike against BAD and DDT** (M10).
  - First Strike: 10,000 on the strongest blimp (20,000 at x-5-x) plus a 75-radius AoE, camo-capable.
  - Pre-emptive: 750 on *every* blimp that enters, plus the stronger First Strike at 30 s.
  - With Sub Commander, that kills every DDT through R100, and two First Strikes on the R100 BAD on short maps (bw:Pre-emptive_Strike_(BTD6); a Steam thread in the search results agrees on DDTs).
  - The model sees none of it. This is the largest *R95/R100-specific* under-credit in the military group.
- **Energizer:** global −20% ability cooldown. Matters only once abilities are modelled.
- **Airburst double count:** M4. **Sub Commander aura:** M11. **Submerge:** M12.

### Monkey Buccaneer
- **Grapes and hooks.**
  - Grapes are correct per shot (5 per 1.3 s, a 100° spray, both sides) apart from the rear-copy rule (M5).
  - The grape spray is "radial" (count ≥ 3), so the zone's angular share applies. With a 100° spray that is an under-credit (see primary audit F8).
  - The hooks (MOAB Takedown, Pirate Lord) are abilities (M10). Pirate Lord's +100% blimp cash matters for Impoppable income.
- **Navarch's map-wide buff:** not exported (M11). Unrealistic in CHIMPS anyway.
- **Carrier and Flagship planes:** `_plane_share` applies 0.4 to all non-missile plane attacks. The forward homing darts deserve more (M15). The Flagship buff is missing (M11).
- **Merchantman and Favored Trades income** (200 / 500 / 800) is right. Trade Empire's stacking bonus is missing.

### Monkey Ace
- **AIR_PATTERN_EFFICIENCY = 0.4** is fine for *non-seeking* radial darts (x-x-0 to x-x-2, top path). For those darts, the radial share and the 0.4 overlap: the zone's angular share *and* 0.4 are both applied (`_hit_rate`), so non-seeking darts may be discounted twice [EST: 0.4 × angular ≈ 0.15-0.3 effective].
  - It should not apply to Neva-Miss or Spectre (M8).
- **Ground Zero, Tsar Bomba:** M1 (bombs) and M10 (ability).
- **Flying Fortress:** the three streams (First, Last, Close) really are parallel. The darts are doubled within each stream (M8).
- **Sky Shredder:** rates are right. Its darts are radial: 0.4 × angular share is probably too low on an 80-radius circle over track, but not verifiable without measurement [UNVERIFIED].
- **Flight radius 40 → 80; Centered Path centre = map centre:** M8.

### Heli Pilot
- **Pursuit, Apache, Comanche:** M6. Apache Dartship and Prime numbers match the wiki (rockets 4 per 1 s, 40 pierce; machine gun 0.05 s).
- **Pursuit** follows *First* only. A global zone is optimistic when two lanes are far apart [EST].
- **MOAB Shove and Downdraft stall:** M3 and M6.
- **Support Chinook** (crate cash, not in CHIMPS) and the Redeploy ability are not modelled. They are irrelevant to damage.

### Mortar Monkey
- Rated zero (M2).
- **How a fixed aim should be credited:** see M2. In short:
  - a station whose zone is the track within (deviation + blast) of P;
  - per-shell hits = rho × the expected track length in the blast, for a landing point uniform in the deviation disc;
  - a reach that collapses to a small value when P lies on a straight single lane, and grows at bends and lane crossings.
- **Utility to add with it:** Signal Flare and Shattering Shells decamo, defortify and de-regrow (M12 mechanism). Shell Shock and The Biggest One stun (M3).

### Dartling Gunner
- **Rated:** only BADS and BEZ (x-x-4, x-x-5). Their barrels target independently (First, Last, Close, Strong).
  - Model: 4 or 6 sources at 5-15 shots/s; "radial", range 130.
  - The BEZ wiki says 12 buckshots of 8 damage; the model has 6 damage [UNVERIFIED which version].
- **Everything else is rated zero (M2).** For a fixed aim, see M2: a cone from the tower through P, darts flying across the whole map, and beams with their width and pierce cap.
- Before scoring Dartlings, decide the default targeting conflict (Locked at map centre vs Follow Touch), in game.

---

## 3. Etienne and Brickell

**Etienne.** The model rates him at zero.
- The export already has the Lv8 UAV global camo buff, and the Lv2+ +10% range buff [UNVERIFIED what the range buff covers: the wiki's Lv2 text says Etienne's own range 55 → 60].
- The single most valuable fix for camo-blind military carries is to apply the UAV camo once the expected hero level is 8 or more (M9).
- Drones: 1 damage, 2-9 pierce, 0.7 / 0.55 s; no lead. UCAV is an ability (M10).

**Brickell.** The model rates her at zero.
- Lv4+ +1 pierce to water towers in range is in the export (M9).
- Naval Tactics (rate ×1.5 → ×2, normal type at Lv5, camo at Lv8, global at Lv19) and Mega Mine are abilities.
- v57 "reworked Naval Tactics (Lv8 hits all water towers)" per the research doc. The wiki pages still show the old levels [UNVERIFIED].

---

## 4. Not verified

- The Dartling default targeting in 57.4: Locked at map centre (wiki) vs Follow Touch (`strategy.py`).
- Whether a Mortar placed by the bot has any default reticle.
- The share of a Bomber Ace's flight over the track (needs per-map geometry). The 3-10× in M1 is an estimate.
- The Spectre barrage miss rate in late rounds (0.7-0.85 is an estimate).
- Whether the bot collects Supply Drop crates (Impoppable cash).
- The exact Carrier Flagship buff size (wiki pages say 15%, ~18% and 20%).
- The game class names for the missing auras and the Pre-emptive missile.
- The BEZ damage (6 in the export vs 8 on the wiki).
- The current Naval Tactics numbers after v57.
- The Advanced Intel enlarged blimp-detection range.
- Reddit discussions: blocked (403). No Reddit claims are used.

---

## Top 10 fixes, by CHIMPS and Impoppable impact

1. **Bomber Ace, Ground Zero and pineapple bombs: read `over_track_only` and place them on the flight curve (M1).**
   - Credit only the share of the flight that lies over the track.
   - This removes a 3-10× over-rating behind the most-built Ace crosspath (2-3-0, 193 builds) and 2-4-0.
2. **Credit a fixed aim for Mortar and Dartling instead of zero (M2).**
   - Add a "point" placement and choose the point.
   - Make the executor set Mortar targets and Dartling Locked aim.
   - This unlocks M.A.D, Ray of Doom, Pop and Awe and Signal Flare for R76-R100.
3. **Model stuns and the Cripple debuff as stall time and +5 damage taken (M3).**
   - Maim and Cripple are on 4-2-0 (181 builds) and 5-x-x. The same mechanism covers MOAB Shove, Downdraft and The Biggest One.
4. **Count the Sub Airburst spawn once, the exhaust spawn only (M4).** About a 40% overrating on every x-x-2+ sub (about 250 builds).
5. **Credit Buccaneer rear shots only when the boat sees track behind it (M5).** Up to a 2× overrating on about 500 boat builds.
6. **Rate helis by the targeting the bot sets (M6).**
   - Lock in Place means a local circle; Pursuit stays global.
   - Re-export the Comanche mini-helis.
7. **Apply hero buffs: Etienne Lv8 UAV global camo, Brickell +1 pierce (M9).**
   - The data is already in `attacks.json heroes`.
   - This changes which camo-blind carries are allowed at all.
8. **Abilities and the Pre-emptive passive missile (M10):** First Strike and Pre-emptive on R95-R100 DDTs and the BAD; MOAB Takedown and Pirate Lord hooks; Ground Zero; Supply Drop cash in Impoppable.
9. **Fix the Ace geometry and homing (M8).**
   - Split the alternating barrage, which halves Spectre and Fortress darts.
   - Drop the 0.4 on Neva-Miss and Spectre homing darts.
   - Use a flight radius of 80 for Circle, and a Centered Path centre at the map centre (or a bot-set point) for x-x-2+.
10. **Model sniper bounces and missing auras (M7, M11).**
    - Bouncing Bullet and Supply Drop: 3-5 hits within 40-80, with shrapnel per hit.
    - Sub Commander: ×2 damage and +4 pierce to subs in range.
    - Carrier Flagship: −15 to −20% cooldown for water towers and Aces.
