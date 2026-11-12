# Damage-model audit: Magic towers, Psi and Sauda (2026-11-12, game 57.4)

This is a read-only audit. No code was changed.

**What it covers.** It compares `btd6bot/dps_model.py` `profile()` (built from `data/game_model/attacks.json`) and the evaluator that uses it (`_Rates`, `_hit_rate`, `station_for`) against the game. The towers are Wizard, Super, Ninja, Alchemist, Druid and Mermonkey, plus the heroes Psi and Sauda.

**How it was checked.**
- Every tier 1-5 on each path and the 1/2 crosspaths at tiers 3-5 were printed with a one-off script, run from the repo root.
- The game side comes from the full fandom wiki pages, read as wikitext through `api.php`. Links below are `fandom:<Page>` = https://bloons.fandom.com/wiki/<Page>.
- The background was `docs/tower_research_2026-11.md`.

**Sources that could not be read.**
- **Reddit could not be fetched.** WebFetch refuses old.reddit.com, and the redlib mirrors returned 403. Nothing below rests on Reddit, and any community claim is marked **[UNVERIFIED]**.
- bloonswiki.com and bloon.games were not needed, because the wiki pages were complete.

**Labels.** "Under" means the model gives the tower less credit than the game does; "over" means more. Factors are my estimates unless a number is quoted from a source.

---

## 0. Summary

Four problems in the shared evaluator code distort these towers more than any single wrong number. They matter more than the per-tower data gaps:

1. **Overflow averaging** (finding 1). This bug makes Druid of the Jungle look about 16× stronger than it is on Rainbows and about 3-4× on Ceramics.
2. **Aimed sprays treated as "all-around" fire** (finding 3). Sun Avatar, every Druid's thorns and Bloonjitsu/Grandmaster are cut to about 40%.
3. **Lingering projectiles get one pierce load** (finding 4). Wall of Fire and the vine brambles are credited with 1 pierce load instead of one per refresh.
4. **The `pierce_percent` buff and the brew buffs are ignored** (findings 2 and 12).

**Your Druid of the Jungle example.**
- The 0.38 shots/s is the game's 2.6 s base cooldown, which is correct for Red to Zebra.
- The vine's real cooldown is longer on strong bloons:
  - Lead: 3.35 s.
  - Rainbow: 3.36 s.
  - Ceramic: 4.2 s.
- The model's station also turns every bramble tick into a whole-bloon instakill (finding 1). So per bloon the model **over**-credits the vine heavily.
- Still, on rounds that are many weak bloons it **under**-rates the tower:
  - R27: 0.75-0.97.
  - R34: 0.56 on short maps.
  - R36: 0.52-1.18.
  - The causes are that the brambles' density handling is wrong (finding 4) and the thorns are cut to 39% by the spray rule (finding 3).
- With a camo village, the model rates 1-3-0 alone at ≥1.0 for R6-39 on Monkey Meadow, Moon Landing and Cracked. That is still below the optimizer's SAFETY_MARGIN of 2.0, so the bot never trusts it to carry. That matches your complaint.
- Measured margins are in finding 1.

---

## 1. Ranked findings (by impact on CHIMPS / Impoppable)

### Finding 1 — OVER (large): overflow is averaged across a station's sources, so weak hits inherit an instakill's carry
- **Where.** `dps_model.py` `_Rates._compute` (lines ~1355-1381) and `_Rates.subtree`.
- **Towers affected.** Every tower that mixes a huge-damage hit with small hits in one station:
  - Druid x-3-x / x-4-x / x-5-x: vine Collidable, 9,999,999 damage, plus brambles.
  - Probably also Ninja Sticky Bomb plus shurikens, and Monarch's 100-damage tornado plus 1-damage thorns (not measured).

**Model numbers** (one 1-3-0 on Monkey Meadow, rho 0.05; my script):

| Layer | HP/s | Overflow per pop | Whole bloons per s |
|---|---|---|---|
| Red, Yellow, Rainbow, Lead | 6.15 | 625,000 | **6.15** |
| Ceramic | 9.62 | 4,000,000 | **0.96** |

- The vine alone gives 0.38 bloons/s.
- The brambles alone give:
  - Red: 5.77/s.
  - Yellow: 1.44/s.
  - Rainbow: 0.12/s.
  - Ceramic: 0.06/s.

**Why it happens.**
- `overflow += rate * (d - hp)` is averaged over all sources' HP rate. The vine is 6% of the hits but carries 10M overflow.
- So the *mean* carry per pop is 625k, and every bramble pop is treated as passing 625k damage to its children.
- In the game, only the vine's own grabs destroy the whole bloon. In other words, the expected carry is right, but the model then caps it at the bloon's total health once instead of per hit, which inflates the result.

**What the game does.**
- The vine instakills one bloon per grab.
- The bramble does 1 damage per tick and pops one layer per hit (fandom:Druid_of_the_Jungle).
- Real whole-bloon rate for one 1-3-0, vine plus brambles:
  - Rainbow: about 0.30 + 0.12.
  - Ceramic: about 0.24 + 0.06.

**Effect on ratings.**
- Over-credited about 15× on Rainbow, Zebra and Lead layers.
- About 3× on Ceramics.
- About 4× on Yellows.
- This is why the model's Druid of the Jungle survives rounds of Rainbows and Ceramics that it should not. It hides the real weakness (Super Ceramics; your R63/R76 plans).

**Fix.**
- When adding overflow, cap each source's overflow per hit at what can actually be passed on: `rate * min(max(0, d - hp), rbe(lay.id) - lay.hp)`.
- Better: keep an "instakill" fraction separately (the share of pops made by sources with `d >= rbe`) and give the full carry only to that share.
- Re-run the calibration (`tools/optimize_builds.py --calibrate`) afterwards.

### Finding 2 — UNDER (large) and OVER (medium): Alchemist brews are missing, and the dip is treated as permanent
- **Model.**
  - 3-x-x, 4-x-x and 5-x-x have **no** rate, pierce, damage or range buff. `BeserkerBrewAttack` is dropped, as `_potion_buffs` documents.
  - The 2-x-x Acidic Mixture Dip is a permanent `damage_type` buff for **every** tower within 45: lead popping plus +1 to Ceramic, MOAB, Lead and Fortified.
- **Game** (fandom:Acidic_Mixture_Dip, fandom:Berserker_Brew, fandom:Stronger_Stimulant, fandom:Permanent_Brew):
  - **Dip:** one tower per throw, every 10 s, lasting **10 shots** (12 at 2-2-0). Shots stack consecutively. It is permanent only with Permanent Brew.
  - **Berserker Brew:** +1 damage, +2 pierce, +10% range, ×0.9 cooldown. Thrown every 8 s at the closest unbrewed tower. Lasts 5 s or 25 shots.
  - **Stronger Stimulant:** +3 pierce, +15% range, ×0.85 cooldown, +1 damage. Lasts 12 s or 40 shots.
  - **Permanent Brew:** the brew and the dip last indefinitely on every tower it has hit.
- **Effect.**
  - The 5-x-x Permanent Brew carry is under-credited about 2-4× on low-damage, high-rate towers. Example: Ninja 4-0-x goes from damage 1 / pierce 4 to damage 2 / pierce 7 at ×1.18 rate, about 4× DPS. The same applies to Sun Avatar and Druid thorns. This is the main reason Alchemist is S-tier in CHIMPS.
  - The 3-x-x / 4-x-x brews are under-credited about 1.2-1.6× for the one or two towers they keep buffed.
  - Lead popping from the 2-x-x dip is **over**-credited for fast towers: about 1 dipped shot/s per Alchemist against, for example, 11.5 shots/s on Bloonjitsu, so about 10× on that tower's lead hits. This matters for the R28/R37/R90 lead rounds unless Permanent Brew stands.
- **Fix.**
  - Read the brew numbers from the AddBerserkerBrew behaviour in `tools/export_attacks.py`.
  - In `station_for`, give each Alchemist a budget of buffed shots per second: dip 10 shots per 10 s; brew min(25 shots, 5 s) per 8 s.
  - Spend that budget on the nearest towers in its range, scaling each buffed source's share. For 5-x-x, apply everything permanently to every tower in range.

### Finding 3 — UNDER (large): aimed sprays are treated as radial (all-around) fire
- **Model.** `_flatten_attack`: `radial = count >= 3 and motion straight`. Radial shots are multiplied by `zone.angular`; this was 0.39 for a Druid placed 15 units from the Monkey Meadow track.
- **Towers marked radial:**
  - Every Druid crosspath (thorns, 5 or 8 per volley).
  - Super 3-x-x Sun Avatar (3 beams).
  - Ninja 4-x-x and 5-x-x (5 and 8 shurikens).
  - Wizard x-3+-x Fireball (spray of 3).
- **Game.**
  - These are aimed shotgun or angular sprays at the target. Examples: "three angled solar rays (30° spray per side)" (fandom:Sun_Avatar_(BTD6)); "Shotgun Spray 8x" (fandom:Druid_of_the_Jungle).
  - Only Tack-style emissions fire all around.
  - The export loses the arc angle: `emission_count` in export_attacks.py around line 404 reads ArcEmissionModel.Count but not `angle`.
- **Effect.** Under-credited about 2-2.5× on Sun Avatar (an A-tier CHIMPS carry), Bloonjitsu and Grandmaster (S-tier Ninja), and every Druid's thorns.
- **Fix.** Export `ArcEmissionModel.angle` (and RandomArc). Set `radial` only when the arc is ≥ 180°. Otherwise treat the volley as aimed, with hits ≈ min(count × pierce, bloons inside the cone).

### Finding 4 — UNDER in dense rounds and OVER in sparse rounds: lingering projectiles get one pierce load and fixed hits
- **Model.**
  - `_single_hits` returns min(pierce, lifespan / rehit).
  - `_hit_rate` uses min(pierce, max(met, single_hits)).
  - So `pierce_refresh` never multiplies capacity.
- **Wizard Wall of Fire** (x-2-x): 10 pierce, refreshed every 0.15 s, 4.5 s life. The model credits **10 hits per wall**.
  - Game (fandom:Wall_of_Fire): pierce refreshes 30 times, so up to about 300 hits. A bloon crossing the 15-radius patch is re-hit every 0.15 s, about 10 hits per bloon.
  - At 4-x-x (x-4-x / x-5-x: 20 pierce per 0.1 s, 5 damage at 0-5-0) the gap is the same.
- **Druid of the Jungle bramble:** 20 pierce per 0.3 s, 4.5 s, 1 damage. The model credits about 15 hits per bramble whatever the density, even on a lone bloon.
  - Game: a lone bloon crossing the 2-radius bramble gets about 1-3 ticks.
  - In a dense stream the bramble gets up to 20 × 15 = 300 hits (fandom:Druid_of_the_Jungle).
- **The same applies to:**
  - Jungle's Bounty / Spirit of the Forest brambles (30-40 pierce per 0.1-0.2 s, 9 s life).
  - Alchemist acid pools.
- **Effect.**
  - Wall of Fire is under-credited about 10-30× on dense rounds.
  - Brambles are over-credited about 5× on sparse rounds and under-credited about 5-20× on dense slow rounds (R28 leads, Ceramic waves).
  - My rough flux test moved Cargo's R27/R36 Druid of the Jungle margins from 0.84/0.75 to 1.85/2.13, and lowered them on Dark Castle. The effect depends on map and round.
- **Fix.** For static, track or contact projectiles with `pierce_refresh`:
  - Total capacity = pierce × lifespan / refresh.
  - Hits = min(capacity, bloons passing the patch during its life × ticks per pass).
  - Bloons passing = rho × bloon speed × lifespan. `layer.speed` and the lot speed are available in `_Rates`.
  - Ticks per pass = ceil((2r + 2 × bloon radius) / speed / rehit).

### Finding 5 — UNDER (very large): Spirit of the Forest's whole-track vines are missing
- **Model.** `profile('druid',(0,5,0))` / `(1,5,0)` has only:
  - thorns (6 damage);
  - a vine (0.38/s at 0-5-0, **1.54/s** at 1-5-0);
  - brambles (5 damage, 30 pierce).
  - It has no on-track bush-vine source. The export never reads that behaviour.
- **Game** (fandom:Spirit_of_the_Forest):
  - Vines grow 20 units every 0.5 s until **the whole track** is covered.
  - They have **infinite pierce** and tick every 0.5 s:
    - Within 50: 4 damage (30 to Ceramics and MOAB-class).
    - Within 100: 3 damage (15).
    - Beyond: 2 damage (10).
  - They pop camo. They need 1-x-x or MIB for lead and frozen.
  - "On lengthy maps such as Logs, Spirit of the Forest can solo all rounds up to 82, provided MIB is applied."
- **Effect.**
  - This is the Spirit's main attack, so its rating is wrong by more than an order of magnitude on dense Ceramic and blimp rounds.
  - Example: a MOAB crossing 400 units of outer vine at 25 u/s takes 16 s × 2 ticks/s × 10 = 320 damage, from one tower, to every blimp on screen at once.
- **Vine rate.**
  - The Spirit reduces digestion to 0.3 s but keeps the 2.6 s base cooldown ("spray of 2": two vine attacks, per the wiki infobox).
  - 0-5-0 at 0.38/s per vine is right. 1-5-0 at 1.54/s (export rate 0.65) is inconsistent with 0-5-0's 2.6. **[UNVERIFIED]** which one is right; at most 2 vines × 0.38 ≈ 0.77/s.
- **Fix.**
  - Add a synthetic "track carpet" source for x-5-x: placement "track", infinite pierce, rehit every 0.5 s, damage by distance band (2/3/4; Ceramic and MOAB 10/15/30), covering every route.
  - Its per-bloon damage = band damage × 2 × (time in the band).
  - Model it as a DoT over the bloon's path length rather than as a station server: every bloon gets it, independent of the other jobs.

### Finding 6 — UNDER (large): Prince of Darkness and Necromancer scaling and undead bloons
- **Model.**
  - 0-0-4: undead 0.67/s, pierce 1, damage 2, "track" inside range 60.
  - 0-0-5: main bolt 3.64/s, damage **1**; undead 0.67/s, p1, d2; undead MOAB 0.33/s, p20, d40.
- **Game** (fandom:Necromancer:_Unpopped_Army, fandom:Prince_of_Darkness):
  - Each summon makes **1-5 (PoD 1-4) undead bloons with pierce 2-11**.
  - Damage 2-4 at Necromancer, **3-13 at PoD** by graveyard size.
  - Fire every 1.0-1.5 s, with **+10% attack speed per 100 graveyard, up to +100% at PoD**.
  - Lifespan 10 s, or 15 s with PoD. They walk **toward the entrance**, meeting oncoming bloons.
  - PoD's bolts get **+1 damage per 300 graveyard, up to +10**.
  - Undead BFBs at 2000+ pops: 100 damage, 50 pierce.
  - (The undead spawn near the Wizard, within 60, not at the track end. Their spawn point can be moved by manual targeting.)
- **Effect.** With a full graveyard, the undead go from about 1.3 to about 400 HP/s, and the bolts from 1 to 11 damage. Under-credited about 10× or more on late CHIMPS rounds. Prince of Darkness is listed as one of the easiest CHIMPS carries (research doc §5).
- **Fix.**
  - Assume a filled graveyard after R40 (or derive it from pops in range over the last 2-3 rounds).
  - Use the mean pierce of 6.5, 2.5 bloons per summon, damage 13, and rate ×2.
  - Make the undead a source that meets the oncoming flow at relative speed (v_bloon + 25) over 250-375 units.

### Finding 7 — UNDER (large): Wizard Lord Phoenix's permanent Phoenix is missing; Shimmer and Archmage decamo is ignored
- **0-5-0 model:** bolt, Fireball, Wall of Fire, Dragon's Breath. **No Phoenix.**
  - Game (fandom:Wizard_Lord_Phoenix): a permanent Wizard-Lord Phoenix circles the map centre (radius 90). Its flame does 20 damage, 50 pierce, every 0.1 s. The Lava Phoenix ability is extra.
  - Under-credited by more than 5× on any map where the circle covers track.
  - Fix: export the permanent Phoenix sub-tower as an "air" source with pattern radius 90 around the map centre (like `_plane_share`).
- **Shimmer** (x-x-3) and **Archmage** (5-x-x):
  - Game (fandom:Shimmer, fandom:Archmage): an attack with `removes: ["camo"]`, 500 pierce, radius 75 (Archmage) / 75-100, every 1-2 s. It strips camo from bloons in range, including DDTs.
  - The model drops it: the projectile has no damage, so `detects_camo` is false and the Archmage's own bolts show `camo=0`.
  - Effect: Archmage and 0-0-3/0-0-4 cannot touch camo in the model, so they are treated as dead on camo rounds (R24+, R90, R95 camo leads). Their range also gives free decamo to every other tower. Under-credited from "zero" to full on camo rounds.
  - Fix: treat a `removes camo` projectile as camo detection for the tower's own sources. Add a "decamo zone" that makes the covered stretch of track camo-free for every later station, the way Advanced Intel uses `camo_paths`.
- **Possible OVER:** 0-5-0 Dragon's Breath DoT is exported as 30 per 1.5 s for 15.1 s (300 total, 20/s per bloon in the zone). The wiki infobox says 10 per 1.5 s for 3 s. **[UNVERIFIED]**. If the wiki is right, the DoT is about 15× too high. Check in game or in the asset.

### Finding 8 — UNDER (large): Bloon Master Alchemist and Unstable Concoction do nothing in the model
- **Bloon Master Alchemist** (0-0-5):
  - The export has `ShrinkPotion`: global, every 10 s (the wiki says 7.5 s), 200 pierce, MorphBloon to Red, with extra pierce cost MOAB 19, BFB/DDT 49, ZOMG 99.
  - The model gives it nothing, because there is no damage field.
  - Game (fandom:Bloon_Master_Alchemist): it turns the strongest bloons on screen (any MOAB-class except BAD) into Red Bloons, so damage = RBE − 1. One throw deletes a ZOMG, 2 BFBs/DDTs or 10 MOABs.
  - Effect: under-credited from 0 to the strongest anti-blimp in its group (R95/R98).
  - Fix: a global "instakill-to-red" source. Shots 1/7.5 s, capacity 200 pierce with the MOAB pierce costs, "strong" priority. Exclude BAD.
- **Unstable Concoction** (x-3-x): the model has 0 damage (`hits_nothing`).
  - Game (fandom:Unstable_Concoction): a blimp coated by the potion (every 6 s, 3 pierce) explodes when popped. The blast has radius 40 and 50 pierce (MOAB/BFB cost 2, ZOMG/DDT 4), and damage depends on the blimp. Since a later patch the blast no longer hits the blimp's own children.
  - Fix: add on-pop splash damage to nearby blimps in the station. This is low priority, since the exact damage table was not read.
- **x-4-x Transforming Tonic** (60 s cooldown: 15 s of 3 damage × 6 pierce every 0.03 s, range 72) and **x-5-x Total Transformation** are abilities. They are excluded by design (see finding 15).

### Finding 9 — UNDER (medium-large): Ninja support and conditional damage are missing
- **Shinobi Tactics** (x-3-x+):
  - Model: no buff.
  - Game (fandom:Shinobi_Tactics): +8% attack speed **and** pierce to nearby Ninjas, stacking up to 20 times (+160%).
  - Effect: under-credited about 1.5-2.5× on ninja-spam builds.
  - Fix: export it as a stacking rate/pierce buff, one stack per Shinobi in range.
- **Flash Bomb / Sticky Bomb / Master Bomber** (x-x-3 to 5):
  - The export carries `conditional_bonus` "Stun" +4 / +19 and "StickyBomb" +4 / +19 on the shurikens, and the model ignores it.
  - Flash Bomb stuns 30 bloons for 1.3 s every 4th shot. Master Bomber stuns blimps for 1 s.
  - The sticky also has a 100 / 600 secondary explosion that is not modelled (fandom:Flash_Bomb, fandom:Sticky_Bomb, fandom:Master_Bomber).
  - Effect: Master Bomber's shurikens on a stuck blimp do 20 instead of 1, so shuriken damage on blimps is about 20× too low; the tower overall is perhaps 1.3-2× low.
  - Fix:
    - Apply `conditional_bonus` to the share of targets carrying that status.
    - Stun share = stun time × stun rate / time in the zone, capped at 1.
    - Sticky share = blimps with a bomb attached.
- **Counter-Espionage** (x-2-x): its hits strip camo (fandom:Counter_Espionage). Not modelled; the same decamo-zone fix as finding 7.
- **Bloonjitsu / Grandmaster** shot rates are right (5 shurikens / 0.434 s; 8 / 0.217 s, 2 damage). They are only hurt by finding 3.

### Finding 10 — UNDER (medium): Druid bottom-path ramps and Poplust are flattened
- **Model.**
  - 0-0-3 and 0-0-4 are identical to 0-0-1 (4.55 thorns/s, damage 1).
  - 0-0-5 is a flat 4 damage at 9.09 shots/s.
  - There are no Poplust buffs.
- **Game** (fandom:Druid_(BTD6) path 3 text, fandom:Druid_of_Wrath, fandom:Poplust, fandom:Avatar_of_Wrath):
  - **Druid of Wrath:** +0.5% attack speed per damage dealt, up to **+100%**. It resets after 2 s idle, so in a round it is normally maxed.
  - **Poplust:** +15% attack speed **and** pierce to nearby Druids per Poplust, up to 5 stacks (+75%). This is why "Druid 2-0-4 Poplust spam" is a listed mid-game strategy.
  - **Avatar of Wrath:** 4 damage +1 per 3,000 RBE on screen, up to +30, so up to 34 damage. Lightning gets the same ramp with 2-x-x.
- **Effect.** 0-0-3+ is under-credited about 2× for the Druid of Wrath speed. Poplust stacks give a further 1.75 × 1.75 ≈ 3×. Avatar of Wrath on blimp and Ceramic rounds (RBE often >30k) is under-credited about 5-8×.
- **Fix.**
  - Druid of Wrath: rate ×2 while a round has bloons in range.
  - Poplust: rate and pierce +15% per Poplust Druid in range, max 5, as a buff of kind rate+pierce.
  - Avatar of Wrath: damage 4 + min(30, round RBE on screen / 3000). Use the round's mean on-screen RBE from the lots.
  - Heart of Vengeance needs lost lives, so it adds nothing in CHIMPS. That is correct to ignore.

### Finding 11 — OVER and UNDER (medium): Druid of the Jungle vine rate per bloon type
- **Model.** The vine fires at a flat 0.38/s (2.6 s) on every non-MOAB layer, and 1-5-0 at 1.54/s (see finding 5).
- **Game** (fandom:Druid_of_the_Jungle):
  - Cooldown = max(2.6 s base, which buffs can shorten; 1.4 + (√lives-lost + 2 if lead + 1)/4, which buffs cannot shorten).
  - Example times: Red 1.9 s → 2.6 s; Zebra 2.85 s; Lead 3.35 s; Rainbow 3.36 s; Ceramic 4.12 s (the wiki's own example). One vine at a time. Infinite range, ignores line of sight.
  - Targets by the tower's priority (First by default since v40; Strong recommended).
  - Leads and frozen need 1-x-x.
- **Effect.** Over-credited about 1.6× on Ceramics and 1.3× on Leads and Rainbows. This is separate from finding 1.
- **Fix.** In `_Rates._compute`, for a `CollideOnlyWithTargetModel` instakill, use the digestion-time rate: 1 / max(rate, 1.4 + (√leak + 1 + 2·lead)/4). `layer.leak` already holds lives-lost.

### Finding 12 — UNDER (medium): Mermonkey buffs, slow and DoT detonation
- **Abyss Dweller / Abyssal Warrior / Lord of the Abyss** (3/4/5-x-x):
  - The export has `pierce_percent` buffs of +10% / +20% / +40% for towers in range. `_buffed_sources` handles only rate, pierce, camo and damage_type, so **this buff is silently dropped**.
  - 4-x-x tridents slow bloons 40% and MOAB/BFB 28%; not modelled.
  - Source: fandom:Mermonkey.
  - Fix: add `pierce_percent` in `_buffed_sources` (`pierce *= value`).
- **Alluring Melody / Symphonic Resonance / The Final Harmonic** (x-x-3 to 5):
  - Model: tridents only.
  - Game: a spiral pulls bloons off the track (a stall), **strips camo**, and detonates all DoT on a bloon at once. The cap is 50 / 125 / 10,000. The 5th tier also buffs heroes (−15% cooldown, +15% range) and gives Magic monkeys +3 pierce (fandom:Mermonkey).
  - Under-credited for the stall and the decamo, and strongly with DoT partners (Alchemist acid, Dragon's Breath, Sauda's "harmed" bonus).
- **Riptide Champion / Arctic Knight / Popseidon** (x-3+-x): trident damage grows +50% / +75% per second of flight. The model uses base damage. Under-credited about 1.3-1.5× **[ESTIMATE]**.

### Finding 13 — UNDER (medium, stall): stuns, slows and blowback are not counted at all
The module docstring says slows "only help". In CHIMPS they are what holds R63, R76, R95 and R98, so leaving them out under-rates whole builds and pushes the optimizer away from them:

- **Monarch of Storms** (5-x-x): its tornado blows bloons and **blimps** back 100-400 units, re-hits every 1 s, travels about 450 units and bounces off map borders (export and fandom:Monarch_of_Storms).
  - The model confines it to range 35 "aimed".
  - It counts 200 pierce against MOAB-class, ignoring `extra_pierce_cost` (MOAB +2, BFB +8, DDT +6, ZOMG +32). That part is an over-count, but small.
- **Druid of the Storm / Ball Lightning:**
  - Tornado blowback 100-250 on 24-60 non-blimps every 2.5 s.
  - The Ball Lightning ball freezes for 4.5 s (fandom:Druid_of_the_Storm, fandom:Ball_Lightning_(BTD6)).
- **Super Monkey Knockback / Dark Knight / Dark Champion / Legend of the Night** (x-x-1+):
  - Hit blimps move 30% slower, Leads and Ceramics 60% / 90% / **fully halted**, and other bloons are pushed 25% back.
  - The export carries `knockback` and the model ignores it (fandom:Dark_Knight, fandom:Dark_Champion).
  - Legend of the Night also makes a black hole that eats leaks for 8 s (2 per round, 3-minute cooldown). It is life insurance that is never counted.
  - The x-x-3 to 5 blimp bonuses (+2, +3, +13/+25 to MOABs) **are** in the model. Correct.
- **Ninja Distraction:** 15% chance per shuriken of 100-150 blowback (fandom:Counter_Espionage). Flash Bomb stun: see finding 9.
- **Fix.** Add a "delay" term per station: seconds of extra dwell time it gives bloons in the zones that come after it.
  - Blowback distance / speed.
  - Slow: time in zone × s / (1 − s).
  - Stun time.
  - In `_play`, push the lots' t0 back by that dwell for stations further along the route, so their deadline windows grow.
  - Honour the game's immunities: BAD is immune; ZOMG blowback is halved.

### Finding 14 — UNDER (medium): Heart of Thunder lightning chain is truncated
- **Model.** `on: "lightning"` count 2 makes 3 bolts × 5 pierce = 15 hits per strike. This affects 2-x-x, 4-x-x and 5-x-x lightning.
- **Game** (fandom:Heart_of_Thunder): the bolt splits into 2 recursively, 5 times, up to **31** bloons.
- **Effect.** About 2× under on dense rounds. Monarch's lightning is 30 damage, so it matters there.
- **Fix.** Treat a lightning spawn as a geometric chain: 2^depth − 1 hits, with depth from the export (5).

### Finding 15 — by design, but large: abilities are excluded
- The model counts no abilities. In this group the ones a bot can fire on cooldown are:
  - Bloon Sabotage: 50% global slow for 15 s.
  - Grand Saboteur: 30 s of slow, and blimps spawn at 75% health.
  - Transforming Tonic.
  - Jungle's Bounty Vine Crush: grabs 10 non-blimps anywhere.
  - Summon Phoenix.
  - Tech Terror / Anti-Bloon.
  - Psi's Psychic Blast and Psionic Scream.
  - Lava Phoenix.
- The research doc says "abilities fire on cooldown".
- **Fix.** A per-ability uptime source: effect × duration / cooldown, applied only to abilities the executor actually fires.

### Finding 16 — UNDER (large for the hero slot): Psi and Sauda are rated at zero
- **Model.**
  - `forecast.py` and `optimize_builds.py` skip `kind == "hero"` ("hero: not counted by the model (extra safety)").
  - `attacks.json` does export every hero level, but nothing reads it.
  - Even if it did, Psi's main attack has **no damage amount** (an instakill-over-time effect), so `profile()` would give it 0.
- **Psi** (fandom:Psi_(BTD6)):
  - Infinite range and ignores line of sight.
  - Instakills one bloon at a time: 0.15 s per HP layer from Lv2, 0.1 s from Lv13.
  - Cooldown 1.0 s, 0.85 s from Lv5. Two independent attacks from Lv9, three at Lv20 (the export has Attack3).
  - Small chain blast (1-3 bloons) and Destructive Resonance.
  - Unlocks over levels: Lead at Lv6, Ceramics at Lv7, Purples at Lv11, MOABs at Lv14 (4 damage per 0.1 s), BFBs at Lv16, DDT/ZOMG at Lv20.
  - In the model, it would need an instakill source like the Druid of the Jungle vine, with rate 1 / (cooldown + 0.15 × layers).
- **Sauda:**
  - The export has slash data (rate 0.45 → 0.1 s, pierce 3 → 8, damage 1 → 4, bonus to Ceramic/Fortified/MOAB, a MOAB DoT from Lv10).
  - It also has `SaudaAfflictionDamageModifierModel`, which the model leaves uninterpreted. Game (fandom:Sauda_(BTD6)): +2 damage to bloons, +10 to MOABs, on any bloon with a lingering status (slow, DoT); more in later levels.
  - Range 23-29 means placement on a curve decides everything.
- **Effect.** The hero slot that the research ranks first for a bot (Psi) is worth 0 in every rating. So builds paired with Psi are rated as if alone.
  - With one life and a 2.0 margin this is "safe", but it wastes cash. It also stops the optimizer from choosing Psi-dependent cheaper builds.
- **Fix.**
  - Read `heroes[hero]["levels"][str(level_at_round(r))]`, with the level from hero XP per round in heroes.json.
  - Build a profile from it with `profile()`'s machinery.
  - For Psi, add a special instakill source (global, per-layer time).
  - For Sauda, add an `afflicted` bonus that applies when another station applying DoT or slow covers the same stretch.

### Finding 17 — minor
- **Jungle's Bounty** 0-4-0 has no `income` in the export, while 0-5-0 has $1,000/round.
  - Neither is used by the optimizer, since `Profile.income` is read nowhere.
  - In CHIMPS, tower income is off anyway (game rule; **[UNVERIFIED]** for Jungle's Bounty specifically).
- **Heart of Oak** (x-2-x) degrow: correctly worth nothing, since the model ignores regrow. Its +1% pierce per life gained is 0 in CHIMPS.
- **Sun Temple / True Sun God** (4-x-x / 5-x-x): only the base beam (20/s × 20 pierce × 5 / 15 damage). Sacrifice attacks are absent. That is correct only if the bot never sacrifices; if it does, they are under-credited.
- **Monarch's ball lightning spawn rate** (1.07 balls/s, about 34 strikes/s × 10 damage, ≈1,700 HP/s potential) comes from the export's interval spawn on a 12.9 s tornado. The wiki says "per 1 second in the front 180°". **[UNVERIFIED]** whether this is high; check against a recording.
- **Dark Champion / Legend of the Night** blades bounce (8 / 16). The model counts pierce only. That is fine.

---

## 2. Your Druid of the Jungle question, in one place

| | Model (`profile('druid',(1,3,0))`) | Game (fandom:Druid_of_the_Jungle, fandom:Hard_Thorns) |
|---|---|---|
| Vine | global, 0.38/s, kills any non-blimp outright | infinite range, ignores line of sight. Cooldown max(2.6 s, 1.4 + (√lives-lost + 1 + 2·lead)/4 s): weak bloons 0.38/s, Ceramics 0.24/s. One vine at a time. Follows targeting priority (First default, Strong recommended); not blimps; camo needs support |
| Damage per grab | 9,999,999 (whole bloon) | whole bloon. The "crush" is only how long it takes, and that is the digestion time above |
| Bramble | p20, d1, 15 hits per bramble at any density | 20 pierce per 0.3 s tick for 4.5 s at the grab spot, radius 2, Normal type with 1-x-x. 1-3 hits per passing bloon; up to 300 per bramble in a dense stream |
| Station | vine and bramble together give **6 whole bloons/s for any layer up to Rainbow** (finding 1) | about 0.3-0.4 vine kills/s, plus bramble chip damage |
| Thorns | 8 × p2, cut to 39% (finding 3) | 8-thorn shotgun spray aimed at the target, range 35 (+40% with Obyn Lv5) |

**Measured model margins**, 1-3-0 plus a 0-2-0 village beside it (CHIMPS):
- Monkey Meadow: R6-39 all ≥1.01. R27 1.01, R34 1.45, R36 1.18.
- Cargo: R27 0.84, R36 0.75.
- Dark Castle and Bloody Puddles: R27 ~0.76, R34 ~0.56, R36 ~0.52.
- Encrypted / Spring Spring / Haunted: R27 0.88-0.97.
- Moon Landing / Cracked: all ≥1.

**What the wiki says.** It confirms "incredible early-game and mid-game popping power". It says DotJ with camo "can solo most Intermediate and Advanced Maps" in boss events. It also confirms the tower falls off at Super Ceramics.

So the model's verdict, "barely holds, below the 2.0 bar", understates DotJ on weak-bloon rounds and overstates it on Rainbow/Ceramic/Lead rounds. The owner's "carries R1-39 alone" is consistent with the wiki. **[UNVERIFIED]** on Expert maps: the multi-lane Expert maps tested (Dark Castle, Bloody Puddles) genuinely spread the bloons thin, and nothing confirms it there.

---

## 3. Top 10 fixes, in order

1. **Cap overflow per source** in `_Rates._compute` (finding 1). This removes the largest false strength: Druid of the Jungle ×3-16. It is a one-line fix, then a calibration rerun.
2. **Export the arc angle; spray ≠ radial** (finding 3). Sun Avatar, Bloonjitsu/Grandmaster and all Druids gain about ×2-2.5.
3. **Alchemist brew and dip as a shot budget** (finding 2). Add Berserker Brew, Stronger Stimulant and Permanent Brew. Limit the dip to 10 shots per 10 s unless 5-x-x.
4. **Refresh-aware lingering projectiles** (finding 4). Wall of Fire and brambles become density-correct.
5. **Spirit of the Forest whole-track carpet** (finding 5). Also settle the 1-5-0 vine rate.
6. **Decamo as a capability and a zone.** Shimmer/Archmage/PoD, Counter-Espionage and Alluring Melody (findings 7, 9, 12). This fixes Archmage being worth 0 on camo rounds, and gives free camo to neighbours.
7. **PoD / Necromancer graveyard scaling and undead pierce/damage** (finding 6), plus the **WLP permanent Phoenix** (finding 7).
8. **Hero profiles**, Psi first (finding 16). Use the exported hero levels, with a special instakill source.
9. **Missing support buffs:** `pierce_percent` (Mermonkey), Shinobi stacks, Poplust stacks, Druid of Wrath ×2, Avatar of Wrath RBE ramp, and `conditional_bonus` (Flash Bomb / Sticky) (findings 9, 10, 12).
10. **A stall term** for blowback, knockback, stun and slow: Monarch, Druid of the Storm, Dark Knight line, Abyssal Warrior, Flash Bomb (finding 13). Add **BMA's global shrink potion** as an instakill source in the same pass (finding 8).

Re-check the pinned loss-case tests after fixes 1 and 4: `test_druid_vine_one_bloon_offline` (Bazaar Half Cash R63) and the Ninja + Alchemist lead case in `_potion_buffs`. The first fix makes the Druid weaker on Ceramics, which matches that loss. The third fix makes the dip weaker on fast towers.

---

## 4. Not verified
- Reddit discussion of the 1-3-0 solo: fetching was blocked.
- The 0-5-0 Dragon's Breath DoT size: export says 300, wiki says 20.
- The 1-5-0 vine rate: export 0.65 s against 2.6 s at 0-5-0.
- The Monarch ball-lightning spawn rate.
- Unstable Concoction's explosion damage table: not read in full.
- The exact Bloon Master Alchemist shrink interval: export 10 s, wiki 7.5 s.
- Jungle's Bounty income in CHIMPS.
- All "×N" effect sizes, other than the measured margins and station rates, are my estimates.
