# Damage-model audit: support towers, heroes and buff handling (2026-11-12)

Read-only audit. No code, data or game state was changed.

**Scope**
- Support towers: Banana Farm, Spike Factory, Monkey Village, Engineer Monkey, Beast Handler.
- All 18 heroes in `data/game_model/attacks.json`.
- How `btd6bot/dps_model.py` credits buffs and heroes in general.

**Method**
- The model's own profiles were printed with one-off Python scripts run from the repo root (`dps_model.profile`, `_flatten_attack` on hero levels, and `station_for` buff logic).
- Game facts come from the full Fandom wiki pages, fetched as wikitext through `https://bloons.fandom.com/api.php?action=parse&page=<Page>&prop=wikitext`. Notes, tips and trivia sections were read.
- Reddit could not be read: old.reddit and www.reddit `search.json` both returned 403, and the libreddit mirrors refused the connection. Community views below come from search-result snippets only and are marked as such.
- bloonswiki.com returned 403, as in `docs/tower_research_2026-11.md`.

**Marking**
- **[UNVERIFIED]**: no fetched source confirmed it.
- **[ESTIMATE]**: my own arithmetic or judgement.
- `fandom:<Page>` means `https://bloons.fandom.com/wiki/<Page>`.

---

## 0. Summary of the main problems

1. **Heroes are worth exactly zero to every rating, and their cost is still spent.**
   - Every consumer drops the hero before building stations:
     - `forecast.py:144` and `:169` (`p.kind == "hero"`)
     - `tools/optimize_builds.py:550-557`
     - `tools/optimize_builds.py:767`, which writes the step note "hero: not counted by the model (extra safety)"
   - `dps_model.profile()` only reads `attacks()["towers"]`, so the 360 exported hero levels are never used.
   - The result:
     - The optimizer treats the hero as $540-$2,160 of dead money.
     - The hero is never chosen by value. The optimizer uses `account.selected_hero or "quincy"` (`optimize_builds.py:1212`).
     - The planner and strategy fallbacks are the fixed list `obyn, striker_jones, gwendolin, quincy` (`planner.py:503`, `strategy.py:1025`).
   - Across the 480 strategy files: Quincy 212, Obyn 138, Brickell 57, Etienne 48, Sauda 18, Psi 15. Adora and Benjamin appear once each, both in achievement or one-off plans.
2. **Support value that is not a passive stat line is missing.** This covers abilities (Call to Arms, Homeland Defense, Overclock, Ultraboost, Spike Storm), periodic effects (Carpet of Spikes' auto-storm, Perma-Spike's start-of-round boost), traps, decamo and income.
   - Support towers are therefore rated far below their game value.
   - The worst cases are Carpet of Spikes (passive storm missing, about 8x too little pierce), Ultraboost/Overclock (0), XXXL/Bloon Trap (0), Beast Handler (0 for every upgrade), and Cleansing Foam (decamo missing).
3. **The buff code has stacking errors in both directions.**
   - Two villages with the same buff stack in the model. The game, as far as I can tell, applies the strongest one only [UNVERIFIED].
   - Different range buffs from one village do not add, because the model takes `max`.
   - Additive range buffs, `damage`, `pierce_percent`, `damage_modifier` and `projectile_speed` are all dropped.
   - Buffs that sit on a sub-tower are ignored. **Etienne's Level 8 map-wide camo is one of these**: it lives on the UAV sub-tower.
4. **Hero bookkeeping that the bot already uses (abilities, level estimates) has wrong constants.**
   - XP ratio: Corvus and Silas are swapped.
   - Map-difficulty and Self Taught Heroes XP bonuses are left out.
   - At least 14 ability cooldowns are wrong.
   - Some abilities are attached to the wrong level (Ezili, Rosalia).

---

## 1. How the model treats support and heroes today

| Mechanism | What the code does | Where |
|---|---|---|
| Passive tower buffs | `profile().buffs` is the export's top-level `buffs` plus the Alchemist dip (`_potion_buffs`). `station_for` gives a tower each buff whose supporter's centre lies within `radius or q.range` (`buff_covers`) and whose filters pass (`buff_reaches`) | `dps_model.py:720-747`, `1760-1830` |
| Buff kinds applied | `rate` (shots / value), `pierce` (+value), `camo`, `damage_type` (MIB lifts every immunity, the dip lifts the named ones). `range` with a `value` sets `range_mult = max(range_mult, 1+value)` | `_buffed_sources` `1691-1716`, `station_for` `1806-1815` |
| Buff kinds silently ignored | `range` with only `additive`, `damage`, `pierce_percent`, `damage_modifier`, `projectile_speed`, `discount`. Any buff on a **sub-tower** (UAV) is also ignored | same |
| Abilities | Not exported (`export_attacks.py`: "Abilities (AbilityModel subtrees) are left out") | `export_attacks.py:32-33`, `tower()` filters `AbilityModel` |
| Slows / stuns / knockback | Exported as `zones` (Arctic Wind) and uninterpreted behaviours (`SlowOnPopModel` ×31, `BloonSlapModel`, ...). The model does not use them | `dps_model.py:52` docstring |
| Decamo / degrow / delead | Exported as projectile `effects.removes`. Never read by the model. The foam projectile has no damage, so it is not a source either | `engineer 030` raw |
| Income | `Profile.income` is computed (`dps_model.py:741`) but **nothing reads it**. The optimizer economy is round cash only (`optimize_builds.py:170-173`). Farms are only an "XP target" (`INCOME_KINDS`) | grep `.income` |
| Discounts | Exported (`discount` buffs: village xx1/xx2, Rosalia L6/L20, Silas L13). Optimizer prices ignore them (`T.tower_cost`, `upgrade_cost`) | `optimize_builds.py:529-535` |
| Heroes | Not profiled. Not placed into stations. Cost still paid | see section 0 |
| Calibration | `TOWER_EFFICIENCY = 1.0` and `SAFETY_MARGIN = 2.0` were fitted on 2,104 logged rounds **with the hero, abilities and slows uncounted**. That missing help is folded into the calibration | `dps_model.py:82-89`, `optimize_builds.py:92` |

**The calibration matters for every fix below.**
- Any credit added for heroes or abilities moves the model toward optimism, against a bar that was fitted assuming those things were absent.
- So every hero or ability credit should be added behind a switch, and the calibration (`--calibrate`) re-run before the 2.0 bar is trusted again.

---

## 2. Support towers

### 2.1 Monkey Village

Exported buffs, confirmed from the printed profiles:
- Base: +10% range.
- 2xx: rate ×0.85.
- 3xx: Primary +1 pierce, +10% range, +25% projectile speed.
- 4xx: Primary +5 range.
- 5xx: Primary +3 pierce.
- x2x: camo.
- x3x and up: `damage_type` (MIB).
- xx1/xx2: discounts.

**V1. Jungle Drums (2-x-x), Radar (x-2-x), MIB (x-3-x): the base mechanics are right.**
- Model:
  - Rate ×1/0.85 = +17.6%.
  - Camo.
  - MIB clears every immunity (`immune = frozenset()`) but keeps `only_tags` and `excluded_tags`. That correctly does **not** let a tower hit blimps it cannot target.
- Game: Jungle Drums gives a 0.85x cooldown. MIB gives normal-type popping but "will not grant power to attack ... MOAB-class ... if the tower cannot attack them" (fandom:Monkey_Intelligence_Bureau, fandom:Jungle_Drums).
- No change needed.

**V2. Several villages stack the same buff (over-rating).**
- Model: printed with a 0-0-0 Dart (1.053 shots/s):
  - One 2-0-0 → 1.238/s.
  - **Two 2-0-0 → 1.457/s (×0.85²)**.
  - Two 3-0-0 → pierce 2 → **4** (+1 twice).
- Game: same-type Village influence buffs do not stack between villages. Only Monkey Commerce says it "can stack with up to 2 other Villages" (fandom:Monkey_Village_(BTD6), Monkey Commerce entry). That exception implies the rule. **[UNVERIFIED for Jungle Drums specifically: no fetched page states it outright.]**
- Effect: two villages beside the same carry are over-rated by 17.6% rate, and two Primary Training villages by +1 pierce. The optimizer may buy a second village for nothing.
- Fix: in `station_for`, keep the best buff per `(kind, sets, towers)` key (max rate reduction, max pierce, any camo or MIB) instead of appending all of them. Keep the Commerce exception for discounts only.

**V3. Primary Training's extra +10% range is lost (under-rating), and Primary Mentoring's +5 range is ignored.**
- Model: `range_mult = max(range_mult, 1 + value)`. A Primary tower next to a 3-x-x village gets 1.10, not 1.20.
  - The `{"kind": "range", "additive": 5.0}` buff (4-x-x and 5-x-x) has no `value`, so it falls into `buffs_here` and `_buffed_sources` drops it.
  - The same applies to Obyn L11 (+5 to Magic) and Silas L8 (+5 to Ice), if heroes were ever counted.
- Game: "+10% range ... further +10% range ... +25% projectile speed" for Primary towers (fandom:Primary_Training). Mentoring adds "+5 additional range, -10% ability cooldowns, free Tier-1 Primary upgrades" (fandom:Primary_Mentoring).
- Effect: Primary towers near a 3xx or 4xx village are rated with 8-17% too little range, and so too little zone length and time-in-range. A 4-x-x village is rated almost the same as 3-x-x, which is consistent with the optimizer's existing `VILLAGE_PRIMARY_PATH` doubt.
- Fix: sum the percentage range buffs from different buff sources, add the `additive` ones after the multiplier (wiki: "Range buffs apply after all other range multipliers" for Obyn), then apply V2's de-duplication.

**V4. Call to Arms (x-4-x) and Homeland Defense (x-5-x) are worth nothing in the model.**
- Model: the profile of 0-4-0 equals 0-3-0. The tower costs $20,000 or $40,000 (medium, `towers.py:585-586`) and is rated as zero gain. The optimizer will never buy it.
- Game (fandom:Call_to_Arms, fandom:Homeland_Defense):
  - Call to Arms: **all towers on screen** get +50% attack speed and +50% pierce for 15 s, on a 45 s cooldown.
  - Homeland Defense: +100% speed and +100% pierce for 20 s, on a 45 s cooldown.
  - Since v57 neither can be fired over an active buff.
- Effect:
  - Pressed on cooldown, the average gain is [ESTIMATE] about 1/3 × (1.5×1.5−1) ≈ **+42% total capacity** for Call to Arms and 20/45 × (2×2−1) ≈ **+133%** for Homeland Defense.
  - For the 15-20 s window in which it is up, the gain is ×2.25 and ×4.
  - These are the strongest late-game support buttons, and the bot already presses them (`abilities.py:170-171`).
  - Bot constant: `"Homeland Defense": (60, ...)` is wrong. The game says 45 s.
- Fix: see section 5, "abilities as duty cycle". Give these two a global `rate` and `pierce` buff with value `1 + uptime·gain`, or apply it only on heavy rounds, matching `abilities.heavy_rounds_for`. Correct the cooldown to 45.

**V5. Monkey Business and Monkey Commerce discounts (x-x-1, x-x-2) are not priced in.**
- Model: the discount buffs are exported and never used. `T.tower_cost` and `upgrade_cost` are full price.
- Game:
  - Business takes 10% off base and tier 1-3 upgrades in range.
  - Commerce takes a further 5%, stacking up to 3 times.
  - Monkey City (x-x-4) adds +50% pop cash and +20% income, and **Monkey Town has given no income in CHIMPS since v1.5** (fandom:Monkey_City, fandom:Monkey_Town).
- Effect: a 0-0-2 village costs about $1,000 extra on Hard [UNVERIFIED exact] and saves 15% on every tier 0-3 bought in its circle. For a cluster of four Ninja 4-0-2s it saves [ESTIMATE] about $2,000-3,000, with no rating effect. The optimizer never takes it.
- Fix: in the optimizer's cost function, apply the best discount of any village whose radius covers the spot, to the base and tiers 1-3 only. It needs the same "centre within radius" rule as `buff_covers`.

**V6. Grow Blocker (x-1-x) is implicitly "free".**
- Model: regrow is not simulated ("regrowing bloons do not regrow", `dps_model.py:59`), so Grow Blocker and the regrow block on Radar and MIB add nothing. Nothing is lost either.
- Game: R76 (dense regrow ceramics) and R90/R95 (camo regrow) are hard partly because of regrow (fandom:Round_76, research doc section 2).
- Effect: a slight optimism on regrow rounds, and no reason to prefer a village there.
- Fix: low priority. If regrow is ever modelled, Grow Blocker becomes a per-zone "regrow off" flag.

**V7. Overclock on a village (+25% range) and Ultraboost (+2.5% range per stack) are not represented.** See E2.

### 2.2 Spike Factory

**S1. Carpet of Spikes (x-5-x) is missing its auto-storm: about 8x too little pierce, map-wide.**
- Model (`spike 050`): one source, 1.90 piles/s, pierce 10, damage 3 (+7 vs blimps), range 50. That is about 19 pile-hits/s inside a 50-unit circle.
- Game (fandom:Carpet_of_Spikes):
  - Every 15 s it fires a passive Spike Storm: **200 piles over the whole track in 1 s**, 10 pierce, 3 damage (10 vs blimps). The piles last 18-22 s and carry between rounds.
  - It keeps the active Spike Storm.
- Effect [ESTIMATE]:
  - The auto-storm alone is 200 × 10 / 15 s ≈ **133 pile-hits/s spread over the whole map**, against the main attack's 19.
  - Against blimps that is roughly 1,300 extra damage/s across the track.
  - Carpet is the research doc's R100 answer, "Spirit of the Forest + Carpet of Spikes". The model rates it like a slightly better MOAB SHREDR, so the optimizer never builds it.
- Fix: in the exporter, read the passive storm (the auto-cast is an ability model, which `tower()` drops). In the model, add a `placement="global"`, `bank`-type source with shots = 200/15 per s, pierce 10, damage 3, Moabs +7, lifespan 20 s, carried between rounds.

**S2. Spike Storm (x-4-x) ability: 200 piles every 45 s.**
- Model: ignored, so 0-4-0 is rated exactly like 0-3-0.
- Game: "produces 200 spike piles over the course of 1 second ... entire track, cooldown of 45 seconds". The piles last 9-11 s (fandom:Spike_Storm_(BTD6)).
- Bot constants: `abilities.py:168-169` have `"Spike Storm": (60, ...)` and `"Carpet of Spikes": (60, ...)`. The game says 45 s for Spike Storm. Carpet's own active cooldown was not stated on the fetched page [UNVERIFIED].
- Fix: duty-cycle credit (section 5), as a global track source of 200/45 piles per s. Correct the cooldown.

**S3. Perma-Spike (x-x-5): the stockpile and the start-of-round boost are under-credited.**
- Model (`spike 005`, `025`, `205`):
  - Cooldown 6.06 s (0-2-5: 3.64 s), pierce 50 (85 with 1-x-5), damage 10.
  - `lasts_rounds` 3. The carried stock is capped at `CARRIED_STOCK_SECONDS = 30` s of production, which is about 5 piles (0-0-5) or 8 piles (0-2-5).
  - No start-of-round boost.
- Game (fandom:Perma-Spike):
  - Piles last **300 s or 4 rounds**.
  - Every round starts with **4x production for 10 s**.
  - Rates match the model: 6.06 s, 4.85 s, 3.636 s.
- Effect [ESTIMATE]:
  - 0-2-5: the boost adds about 11 piles per round (10 s at 0.909 s). That is 5,500 extra pile-damage per round.
  - A full 300 s stock is about 82 piles × 500 = 41,000 damage. The model credits about 8 × 500 = 4,000.
  - The model therefore misses most of what makes Perma-Spike the community's "last line" for R95-R100. That is consistent with the research doc's "Biggest gap: no blimp killer that works on R100".
  - An in-game cap on piles per factory is possible [UNVERIFIED]. Measure it before raising the cap.
- Fix:
  - Raise `CARRIED_STOCK_SECONDS` per source to its real lifespan, capped by the pile count the bot logs between rounds.
  - Add the start-of-round boost: the export must read the start-of-round rate model, and `Station.bank_start` should get `boost_rate × boost_s` at every round start.

**S4. Long Life Spikes (x-x-3) carry-over is not in the export.**
- Model: the `spike 003` raw model has no `lasts_rounds`, while 004 has 2 and 005 has 3. So `lasts=False`.
- Game: "spikes last up to 2 rounds or 140 seconds ... start-of-round ... 4x faster for 3s" (fandom:Long_Life_Spikes). Deadly Spikes lasts 3 rounds and Perma-Spike 4.
- Effect: a small under-rating of 0-x-3.
- Fix: check what flag the game uses for "1 extra round" in `export_attacks.py`, possibly a different model or a zero-based count [UNVERIFIED]. Add the 3 s ×4 boost the same way as S3.

**S5. Spiked Mines and Super Mines explosions are double-counted, and Spiked Mines hit black bloons and DDTs.**
- Model, two separate bugs:
  - **Double count.** The raw `spike 400` projectile has two spawns, `on: "exhaust"` and `on: "expire"`. `_flatten_projectile` counts both (`k = k1 = n` each), so every mine is credited with two explosions.
  - **Wrong immunity.** The explosion's damage is immune to `black` and its burn to `purple`. `immune = _immune_set(hit) & _immune_set(dot)` makes the intersection empty. The profile shows `imm=[]` for the Spiked Mines explosion.
- Game (fandom:Spiked_Mines, fandom:Super_Mines):
  - "Upon lifespan expiry, create two instances of Explosion. Upon pierce expiry, create one instance."
  - The Spiked Mines explosion is **explosion type**, so it cannot hurt black, zebra or DDT. The burn is applied on damage only.
  - Super Mines explosions are normal type.
- Effect:
  - On busy rounds mines are exhausted, so the model gives 2 explosions where the game gives 1 (+100% on that source).
  - On R95 and R99 the model lets 4-x-x mines damage DDTs, which they cannot.
  - The second error is an over-rating on exactly the rounds the bot loses.
- Fix:
  - Treat `exhaust` and `expire` spawns as alternatives. Use exhaust when the station is busy and expire otherwise, or simply take the max.
  - For the immunity, use the hit's immunities, and apply the burn only to layers the hit can damage.

**S6. Spikes at the end of the track as a last line: structurally fine.**
- Model: stations work in route order and leftovers flow on. A spike factory at the exit gets whatever leaks past the earlier stations, and its `bank` fills while nothing reaches it. This matches the game's use of spikes.
- What is missing is S1-S3 (storm, boost, real stockpile) and Smart Spikes' start-of-round 4x for 3 s (x-x-2, fandom:Long_Life_Spikes and MOAB_SHREDR crosspath notes).

**S7. MOAB SHREDR (x-3-x): correct.**
- Model: +7 vs Moabs, 1.05 s.
- Game: "+7 MOAB damage to every spike, for 8" (fandom:MOAB_SHREDR).

### 2.3 Engineer Monkey

**E1. Overclock (x-4-x) and Ultraboost (x-5-x) are worth nothing.**
- Model:
  - `engineer 040` is just a 15-pierce nail.
  - `050` is a 30-pierce nail. That is correct per the wiki: "30 (nail, e.a.u.)".
  - The tower buff is an ability, so it is not exported.
  - The bot marks both `"never"`, as "needs a tower picked" (`abilities.py:172-173`). The cooldowns written there are 45 and 45. Ultraboost's is really **35**.
- Game:
  - Overclock (fandom:Overclock_(BTD6)): one tower gets **+66.7% attack speed**. It lasts 60 s on tier 0-3 and heroes, 45 s on tier 4 and 30 s on tier 5, on a 45 s cooldown. That is **100% uptime on a tier 4**. On a village it gives +25% range, and on a farm +66.7% income.
  - Ultraboost (fandom:Ultraboost): the same +66.7% for 60 s on a 35 s cooldown (171% uptime). Each expired boost adds a permanent ×0.96 cooldown, stacking 10 times (≈ +50% speed permanently).
  - Sources disagree on a per-round cap for Ultraboost stacks (3 or 10) [UNVERIFIED; search snippets].
- Effect [ESTIMATE]:
  - Overclock pressed every 45 s on the main T4 carry is a permanent ×1.67 rate on that carry, for about $13,500 medium (`towers.py:605`).
  - Ultraboost ends at about ×2.5 rate on one tower.
  - Both are rated 0, so the optimizer cannot see the cheapest DPS multiplier in the game.
- Fix:
  - Bot side: `Game.targeted_ability` already exists for Blood Sacrifice (`abilities.py:194-201`), so the clicked target can be the plan's named carry.
  - Model side: add a `rate` buff ×1/0.6 to the one tower the plan names as the `overclock_target`. For Ultraboost, add the permanent stacks as a function of rounds since purchase.

**E2. Bloon Trap (x-x-4) and XXXL Trap (x-x-5) are absent.**
- Model: the trap projectile has no damage (`EatBloonModel` is uninterpreted), so the profiles of 004 and 005 equal 003. The planner lists Bloon Trap only as an income upgrade (`optimize_builds.income_tiers`).
- Game:
  - Bloon Trap holds 500 RBE of non-blimps, with a 2.8 s trap refresh (fandom:Bloon_Trap_(BTD6)).
  - XXXL Trap holds **10,000 RBE including MOABs, BFBs, ZOMGs and camo DDTs, but not BADs** (fandom:XXXL_Trap).
  - In CHIMPS the cash is banned, and the wiki calls XXXL "a support DPS role ... buffer for Spike stockpiles".
  - Since v57 the cash is paid immediately.
- Effect:
  - XXXL is a 10,000-RBE instant soak per trap cycle. One ZOMG (RBE 16,656 [UNVERIFIED exact]) overflows it.
  - Rated 0, it is invisible to the optimizer.
  - It matters little for R100, because BADs are immune.
- Fix: add a "soak" source with `placement="track"`, an HP budget of 500 or 10,000 per cycle, a cycle time of refresh plus deployment (2.0 + 5.8 s for 0-x-5 per the wiki infobox) and `excluded_tags` {Bad}. Treat its work as RBE absorbed, not as damage per hit.

**E3. Cleansing Foam (x-3-x) decamo, degrow and delead are absent.**
- Model: the foam attack has `targeting: "point"`, so `_flatten_attack` returns early. Its `Splat` projectile has no damage, only `effects.removes: [camo, lead, regrow]`. Engineer 030 is rated as a nail gun.
- Game:
  - Foam is laid every 2 s (1.2 s with 2-3-0) with 10 pierce (15 with Oversize Nails, x-3-1) and lasts 8.5 s.
  - It strips camo and regrow and turns leads into blacks.
  - It is auto-placed: "defaults to Close" (fandom:Cleansing_Foam_(BTD6)). The `point` targeting here is a default spot, **not a hand aim**.
- Effect:
  - The foam is a cheap decamo for every tower downstream. That is the "camo sharing" the owner wants credited.
  - The bot cannot see it, and buys Radar villages or camo crosspaths instead.
- Fix:
  - Do not treat engineer foam as aim-bound. Its default is Close, near the engineer.
  - Add a decamo station type: layers that leave its zone (up to its pierce rate, 10 per 2 s) continue with `camo=False` and `lead→black`. See section 5.

**E4. Pin (x-x-2) and Sentry stuns or slows are not counted.** This is the general slow and stun gap; see section 5.

**E5. Sentries.**
- Model: up to `MAX_SUBTOWERS = 6` alive.
- 5-x-x Sentry Champion's sentries come out at 83 shots/s, 5 pierce, 3 damage. That is plausible but **[UNVERIFIED]** against the wiki: the Sentry Champion page was fetched but the per-sentry rates were not cross-checked.

### 2.4 Beast Handler

**B1. Every upgraded Beast Handler is worth 0.**
- Model:
  - The base handler is one source (1 damage, 4 pierce, range 20).
  - **Every upgraded crosspath (1-0-0 through 0-0-4, and all tier 5s) has no sources.** The export lists `PetSpawnerAttack...` attacks with no weapons, because the beasts are spawned units that are not exported.
- Game (fandom:Beast_Handler):
  - Fish need water. Dinosaurs need land. Birds need track in range and move bloons along the track.
  - "Beast Power" grows with tier and with merging other handlers. Tier 5 needs 3 merged tier-4 handlers.
  - Examples: Velociraptor 9 damage, 14 pierce, 1.0 s. T-Rex 26 damage (+8 vs stunned), 24 pierce, with a Stomp stun up to ZOMG and DDT. Orca drags MOABs and BFBs. Megalodon drags BADs.
  - The beast's position is set with a Place Beast button (manual targeting).
- Effect:
  - Correctly nothing for now: the bot has the `i` hotkey but cannot place beasts.
  - If the bot ever uses it, the model will need the pet stats.
- Fix (low priority):
  - Export the beast sub-towers with base Beast Power (no merging).
  - Treat the beast's default position (near the handler) as the tower spot.
  - Mark Megalodon and Giganotosaurus as needing merges, so they are never planned.

### 2.5 Banana Farm

**F1. Farm cash is computed but never used.**
- Model: `Profile.income` (for example 0-0-0 $80, 2-0-0 $160, 4-0-0 $1,500, 5-0-0 $6,000, and 0-3-0 bank 7,000 at 15%) is never read. `INCOME_KINDS = {"farm"}` is an "XP target only".
- Game:
  - Farms are locked in CHIMPS, so this is irrelevant there.
  - In the other modes they are the main eco: Banana Plantation 16 bananas, Banana Research Facility 5 crates of $300, Monkey Wall Street (farm x-x-5) +$4,000 at round end (fandom:Banana_Farm_(BTD6), fandom:Monkey_Wall_Street).
- Effect: the planner can never trade defence for eco. That is acceptable under "never lose", but it leaves the XP and MM-per-hour objective on the table in Easy and Medium.
- Fix: add `profile.income` (× the mode's cash multiplier × the Double Cash rule) to `Economy.income(r)` for farms already placed, so a farm can pay for itself in the greedy search.

---

## 3. General buff handling: specific code defects

| # | Defect | Where | Effect | Fix |
|---|---|---|---|---|
| G1 | Buffs carried by a **sub-tower** are ignored. Etienne's L8 global camo is `attacks[UAVSpawner].weapons[0].projectile.subtowers[UAV].buffs = [{"kind":"camo","global":true}]`, while the top-level buffs are only `[range 0.1]` | `profile()` reads only `entry["buffs"]` | Even if heroes were profiled, Etienne would give no camo | When flattening, gather `subtowers[*].buffs` up to the tower's `Profile.buffs` |
| G2 | Same-type buffs from several supporters stack | `station_for` appends every covering buff | Over-rating; see V2 | Keep the best per kind and filter |
| G3 | Different range buffs from one supporter do not add (`max`) | `station_for:1813` | Under-rating; see V3 | Add percentages from distinct buffs, then add the additive ones |
| G4 | The kinds `damage`, `pierce_percent` (Mermonkey), `damage_modifier` (Mortar x5x), `projectile_speed` and additive `range` are dropped | `_buffed_sources` | Under-rating. Also Gwendolin L17 +1 damage, Pat's Roar and Benjamin's Biohack would need `damage` | Implement `damage` (+value per hit, before tag bonuses) and `pierce_percent` (×value) |
| G5 | Ability buffs are not exported at all | `export_attacks.py:32` | V4, S2, E1, all hero abilities | Export ability models with cooldown, duration and effect, and credit them by duty cycle (section 5) |
| G6 | Slow, stun and knockback effects are not used, though the slow zones are exported | `dps_model.py:52` | Ice, Glue, Obyn totems, Pat, Striker's Concussive Shell, Silas and Psi Blast count as 0 | Section 5: scale a zone's time by 1/speed factor |
| G7 | Decamo is not modelled | none | Cleansing Foam, Ezili L9, Corvus Vision, and Signal Flare (out of scope) count as 0 | Section 5: a decamo station |
| G8 | Income and discount are not in the optimizer economy | `optimize_builds.Economy` | F1, V5, Benjamin, Rosalia L6, Silas L13 | Add them |
| G9 | `buff_covers` is centre-in-radius | `dps_model.py:1774` | Deliberately strict, as the docstring explains | Keep |
| G10 | The hero is excluded from every station list | `forecast.py:144`, `optimize_builds.py:550` | Section 4 | Hero profiles at the hero's estimated level per round |

---

## 4. Heroes

### 4.1 Levelling in CHIMPS: who has which level when

Rules (fandom:Heroes_(BTD6), "Hero Leveling"):
- Heroes earn the tower XP formula at each round end: 20r+20 up to R20, 40r−380 up to R50, 90r−2880 after.
- The level costs are the Quincy table that `abilities._LEVEL_STEP` already holds. It matches the wiki.
- XP ratios:
  - **1.0**: Quincy, Gwen, Striker, Obyn, Etienne, Geraldo.
  - **1.425**: Ezili, Pat, Brickell, Sauda, Corvus, Rosalia, Dan.
  - **1.5**: Benjamin, Psi, Silas.
  - **1.71**: Churchill, Adora.
- Multipliers:
  - Map difficulty: +10% per difficulty above Beginner.
  - Monkey Knowledge: Self Taught Heroes +10%, Monkey Education +8%, Monkeys Together Strong +5%. Together that is ×1.2474, and the wiki uses that figure.
  - Energizer +50% in range.

**Check against the wiki table.**
- The wiki's "placed R1, L20 at round" table says base ratio on Beginner reaches L20 at R98 without MK and R90 with all MK.
- `abilities.estimate_hero_level` reproduces that: placed R6, L20 at R100 without MK, L19 at R90 with MK.

**Levels by round, computed with `abilities.estimate_hero_level`, placed at R6** (placing at R10 is at most one level lower):

| Ratio, conditions | R20 | R30 | R40 | R50 | R60 | R70 | R80 | R90 | R100 |
|---|---|---|---|---|---|---|---|---|---|
| 1.0, Beginner, no MK | 5 | 6 | 7 | 9 | 10 | 12 | 14 | 17 | 20 |
| 1.0, Beginner, all MK | 5 | 7 | 8 | 9 | 11 | 13 | 16 | 19 | 20 |
| 1.0, Expert, all MK | 5 | 7 | 9 | 10 | 12 | 15 | 19 | 20 | 20 |
| 1.425, Beginner, all MK | 4 | 6 | 7 | 8 | 10 | 11 | 14 | 16 | 19 |
| 1.5, Beginner, all MK | 4 | 6 | 7 | 8 | 10 | 11 | 13 | 16 | 18 |
| 1.71, Beginner, all MK | 4 | 6 | 7 | 8 | 9 | 11 | 12 | 15 | 17 |
| 1.71, Expert, all MK | 5 | 6 | 7 | 9 | 10 | 12 | 14 | 17 | 19 |

Consequences:
- **Etienne L8 (global camo) arrives around R40-45** on Beginner (about R36-40 on Expert with MK). Camo rounds before that, such as the R24 camo greens and the 30s, still need another camo source. **L10 UCAV arrives around R55-60.**
- **Adora (1.71)**:
  - L10 Ball of Light arrives around R62-68.
  - L15 (bolts 2 damage, Ball 5 damage) around R88-90.
  - L20 is not reached in CHIMPS without Blood Sacrifice or Energizer. The wiki says so directly: she "is unable to naturally reach level 20".
- **Benjamin (1.5)**: L10 Syphon around R60. That is too late for the R40 MOAB without buying levels, which CHIMPS allows with cash.
- **Psi (1.5)**: L14 (MOABs) around R75-80 and L16 (BFBs) around R88. That matches the research doc's "Lv16 is the practical goal for R94-R98".

**H-XP. The bot's own level estimate is low and uses wrong ratios.**
- `HERO_XP_SCALE` has **Corvus 1.5 (wiki 1.425)** and **Silas 1.425 (wiki 1.5)**.
- `strategy._hero_level_now` applies only `EDUCATION_MULT = 1.08`. It leaves out the map multiplier (×1.1-1.3), Self Taught Heroes (+10%) and Monkeys Together Strong (+5%), if the level-127 account owns them [UNVERIFIED which MK the account has].
- Effect: on an Expert map the bot thinks the hero is 1-3 levels lower than it is from R60 on, so ability gating (`unlock_round`) waits too long. Panel reads override this when they work.
- Fix:
  - Correct the two ratios.
  - Pass `map_mult × MK_mult` with MK from `account`.
  - Optionally add Energizer (×1.5 while in range).

**H-CD. Ability constants in `towers.HEROES` and `abilities.TOWER_ABILITIES` are often wrong.** Game values from the fandom pages read:

| Ability | Bot (level, cooldown) | Game | Source |
|---|---|---|---|
| Benjamin Biohack | L3, 45 s | L3, **30 s** | fandom:Benjamin_(BTD6) |
| Benjamin Syphon Funding | L10, 60 s | L10, **65 s** | same |
| Adora Long Arm of Light | L3, 35 s | L3, **45 s** | fandom:Adora_(BTD6) |
| Adora Blood Sacrifice | L7, 45 s | L7, **30 s** | same |
| Adora Ball of Light | L10, 90 s | L10, **60 s** | same |
| Etienne Drone Swarm | L3, 35 s | L3, **70 s** (55 s at L6, 50 s at L16) | fandom:Etienne_(BTD6) |
| Etienne UCAV | L10, 60 s | L10, **90 s** (75 s at L13) | same |
| Ezili | L7 MOAB Hex, L10 Totem | **L7 Sacrificial Totem, L10 MOAB Hex** (60 s, 40 s at L20) | fandom:Ezili_(BTD6) |
| Ezili Heartstopper | 20 s | **45 s** (40 s at L12) | same |
| Rosalia | L3 Kinetic Charge, L10 Reposition | **L3 Scatter Missile, L10 Kinetic Charge** (45 s at L16) | fandom:Rosalia |
| Gwendolin Cocktail of Fire | 20 s | **30 s** | fandom:Gwendolin_(BTD6) |
| Striker Artillery Command | 60 s | **80 s** | fandom:Striker_Jones_(BTD6) |
| Psi Psychic Blast | 15 s | **40 s** on the wiki level text; 45 s after v52 per the research doc | fandom:Psi_(BTD6) |
| Churchill MOAB Barrage | 60 s | 60 s (**30 s at L20**) | fandom:Captain_Churchill_(BTD6) |
| Pat Rallying Roar | 45 s | 45 s (**30 s at L20**) | Pat_Fusty_(BTD6) |
| Spike Storm | 60 s | **45 s** | fandom:Spike_Storm_(BTD6) |
| Homeland Defense | 60 s | **45 s** | fandom:Homeland_Defense |
| Ultraboost | 45 s | **35 s** | fandom:Ultraboost |

Effect:
- A cooldown set too long loses ability uptime: Ball of Light −33%, Spike Storm and Homeland Defense −25%.
- A cooldown set too short wastes presses and can mis-schedule `heavy_rounds` saves: Drone Swarm and UCAV are listed as about twice as frequent as they really are.
- Fix: correct the table, ideally from exported `AbilityModel.cooldown` per level instead of hand values.

### 4.2 Per hero: what the model has, what the game does

The "model" columns come from running the existing `_flatten_attack` on the exported hero levels. That is what the model *would* rate if heroes were let in.
- "single" is the shots_single × damage sum.
- "crowd" caps pierce at 20.

| Hero | Model L10 single / crowd / vs MOAB | Model L20 | What the export misses or gets wrong | Game role (sources) |
|---|---|---|---|---|
| **Etienne** | **0 sources at L1-19** | 1 source (Perma-UCAV, 2 damage, 25 pierce, 6.7/s, global, camo) | The drones are missing entirely. At L1 one drone: 1 damage, 2 pierce, 0.7 s; L5 0.55 s and camo; L7 2 drones; L11 3; L19 4; damage up to 4 and pierce up to 9. **The L8 UAV global camo sits in a sub-tower buff (G1).** The UCAV ability (L10) is not exported | Mid- and late-game support. Global camo replaces Radar. UCAV can "almost single-handedly obliterate" R75-76. No lead before UCAV. Ignores line of sight (fandom:Etienne_(BTD6)). The wiki's view, via search snippet: the UAV should not be the main reason to pick him in CHIMPS |
| **Adora** | 4.0 / 32 / 4.0 (L10: 4 bolts, 1 damage) | 22.9 / 251 / 22.9 (8 bolts, 2 damage, 0.7 s) | The bolts "aggressively seek". The model treats them as aimed shots with a 45-59 range zone, which is fine. **Ball of Light**: L10 3 damage ×8 targets every 0.05 s = 480/s; L15 800/s; **L20 3,200/s** (+20 vs fortified), infinite range, 12 s per 60 s. That averages 96 / 160 / 640 per s: **about 28x her passive at L20**. Long Arm: ×2 range and pierce, normal type, 10-15 s per 45 s, and ×2 damage at L16. **Blood Sacrifice**: 4 XP per $1 sacrificed, plus up to +25% range and 0.75x cooldown (L20: +50%, 0.5x, 60 s) | B-tier in CHIMPS: weak mid-game, slow levelling. Cannot pop camo. **In CHIMPS selling is banned, so Blood Sacrifice is the only way to clear obsolete early towers and turn them into XP.** The wiki's tip says exactly this. Ball of Light follows her targeting, so Strong is best (fandom:Adora_(BTD6)) |
| **Benjamin** | no damage; income export $250/round | income $5,000/round | Income is exported per level ($90, $140, $250, $1,000 at L11, $2,500 at L15, $5,000 at L17) but **unused** (G8). Missing: Skimming ($1, then $2 per spawned bloon, L6 and L12), Bank Hack (+5% at L5, +12% at L9), **Bloon Trojan** (L7: every 5-7 s one bloon up to MOAB spawns no children), **Syphon** (L10: for 10 s new bloons spawn one rank lower, double cash; 20 s and triple cash at L20; DDT from L18; never BAD), Biohack (+1 damage to the 4 nearest towers for 6 s, then 2 s disabled), heals 5 lives/round (L4) | "Largely useless in CHIMPS and Deflation" (wiki). The best no-aim income hero elsewhere. Syphon and Trojan cut RBE even in CHIMPS (fandom:Benjamin_(BTD6)) |
| **Psi** | **0 damage** | 0 damage | The export has no damage amount. The vibration attack works "per HP unit" (0.15 s per layer, then 4 damage per 0.1 s at L14), so `damage: {type: normal}` has no `amount`. Psychic Blast stun (200 bloons, 6 s) and Scream (instakill or blowback) are missing | Infinite range, no aiming. Targets lead from L6, ceramics L7, purples L11, MOABs L14, BFBs L16, DDTs and ZOMGs L20 (fandom:Psi_(BTD6)) |
| **Corvus** | **56.7 / 833** (from L8) | 287 / 4,113 | **Over-counted**: the mana spells Ancestral Might and Malevolence are exported as permanent attacks. In the game they cost mana and drain it per second. The permanent Spirit sub-tower (1-5 damage, 5-8 pierce, map-wide) is missing | Needs constant spellbook use. Not automatable (fandom:Corvus) |
| **Geraldo** | 4.0 / 20 | 22.5 / 236 | The shop items are the hero's power, and none are modelled: See Invisibility Potion (camo for one tower), Sharpening Stone, Blade Trap, Gerry's Fire, Genie, Rejuv Potion (resets all cooldowns). The Rare Quincy figure and Fertilizer are disabled in CHIMPS | S-tier for humans. Each item must be bought and placed by hand (fandom:Geraldo) |
| **Rosalia** | 5.0 / 30 / 10 | 15 / 150 / 60 | The laser source is marked `placement=global` (the unit), which is probably too generous [UNVERIFIED]. The grenade launcher (L2) is missing. The L6 discount (Ace and Heli −10% in the workshop's range) and the L20 discount (−30% on Anti-Bloon) are exported but unused (G8) | Medium fit; her position is semi-random (fandom:Rosalia) |
| **Silas** | **0 damage** | 0 | The rime and freeze attack has no damage amount. Ice Walls, the Advanced-Intel-like reach through Ice Monkeys (L6) and the freeze-duration buffs are missing. The L8 +5 range to Ice Monkeys (global) is exported but additive (G3). The L13 25% discount on tier-5 Ice is unused | Ice synergy hero (fandom:Silas) |
| **Gwendolin** | 8.0 / 32 | 40 / 320 | Heat It Up (L4: every 40 shots a blast of 3 damage on 100 bloons, plus fire added to nearby towers; L17 +1 damage and +2 vs lead to buffed towers) is missing (G4). Cocktail and Firestorm (abilities) are missing. Purple immunity until L16 is correct | Early-game hero (fandom:Gwendolin_(BTD6)) |
| **Striker Jones** | 4.0 / 80 | 26.7 / 533 | Not exported: L4 Bomb and Mortar +11% speed (global), L5 50% black-pop for all explosives, **L8 towers in range +5% range and +25% pierce**, L18 another +11%, L19 removes black immunity entirely. Also missing: Concussive Shell stun (L3) and Artillery Command (L10 reset; ×2 damage and pierce at L20) | Bomb and Mortar support (fandom:Striker_Jones_(BTD6)). The bot's note says "gives them camo detection"; that is **not on the wiki page** |
| **Pat Fusty** | 10.1 / 101 | 37.8 / 411 | Rallying Roar (+1 damage, +3 at L14, to towers within 30-40, 8-10 s per 45 s, 30 s at L20) is missing (ability, plus G4). Slap knockback (L5) and stuns (L6) are missing. **Camo: never** | Range 24-29 is very short. Needs a tight spot (Pat_Fusty_(BTD6)) |
| **Ezili** | 2.0 / 6 / 40 | 2.5 / 26 / 125 | The curse DoT is mostly captured. Missing: **L9 strips camo, regrow and fortified** (a decamo source, G7), L16 decamos DDTs, **MOAB Hex** (L10: 4% HP +1 per s for 25 s, no children; **BAD-capable at L20**, 5%), Heartstopper (regrow block, purple vulnerable), and the Totem (costs 10 lives, so impossible in CHIMPS; 1 life from L16) | Late-game BAD killer, but only at L20, which arrives around R100+ at 1.425x (fandom:Ezili_(BTD6); snippet "only gets level 20 past r100") |
| **Churchill** | 45 / 415 | 188 / 4,049 | MOAB Barrage (L10: up to 10 blimps, 200-1,000 per missile every 0.5 s, up to 16 per target) is missing. Armor Piercing Shells is missing | Strong late game, very slow levelling (1.71x), $2,160 Hard [UNVERIFIED exact] |
| **Obyn** | 3.6 / 33 | 16 / 224 | Exported buffs: L2 Druid +1 pierce, L8 radar for Druids and Skywardens, L11 Magic +2 pierce and +5 range (additive, dropped by G3). **Missing**: L5 x-3-x Druids on screen +40% range, Nature's Ward totems (L4: slow 30-60%), Brambles, Wall of Trees (2,500-7,500 RBE soak) | Research doc's #3 bot hero |
| **Quincy** | 7.0 / 48 / 21 | 60 / 555 / 240 | Mostly exported. Rapid Shot and Storm of Arrows (abilities) are missing | Cheap opener |
| **Sauda** | 11.1 / 67 / 22 | 40 / 320 / 80 | Mostly exported. Leaping Sword and Sword Charge (abilities) are missing. Range 23-29, so placement is everything | |
| **Admiral Brickell** | 14.2 / 80 | 132 / 528 | Exported: global +1 pierce (L4+). Missing: Naval Tactics (reworked in v57), mines | Water only |
| **Dan D'Monke** | 7.0 / 74 | 32 / 320 | Missing: the two forms, Rabble Rouser (+50% damage, −20% speed in range, triggers "no life lost" passives such as Elite Defender's), the exit shield and blowback (L5, L12), and the net-trap slow (L4) | The v55.2 hero. Medium fit |

Effect of keeping all heroes out:
- **Cheap heroes win by default.** With zero credit, the optimizer and planner should prefer the cheapest hero (Quincy $540 medium). The hand-written fallback list does prefer Obyn and Quincy. Adora ($1,080 Hard) and Benjamin ($1,295 Hard) look strictly worse: a dead outlay of about 2-3 early CHIMPS rounds of income [ESTIMATE].
- **Early-game margins are understated** where they matter most. In R6-R30 the hero is often 20-50% of the board's damage [ESTIMATE]. Examples: Quincy L5-7 at 2-7 single DPS versus a 0-0-2 Dart at about 1-2 single DPS.
- **Late-game support is invisible.** No Etienne camo, Obyn Druid buffs, Striker Bomb buffs or Benjamin RBE cut.
- Because of the calibration (section 1), adding hero damage without recalibrating moves every rating up by an unknown amount.

### 4.3 What the owner rates highly: verdicts

**Adora "at the edge of the track to cover as much as possible."**
- This is right for her **passive**: seeking bolts with a range of 45, then 49, 54 and 59.
- Her **Ball of Light has infinite range**, so placement matters only for the bolts and for Blood Sacrifice's buffs.
- For the bot: use the existing coverage scorer with radius 49 (54 from L9, 59 from L19) and Strong targeting once Ball of Light is unlocked (fandom:Adora_(BTD6) tips).
- In CHIMPS, her value depends on two automation tasks:
  1. firing Ball of Light on heavy rounds;
  2. Blood Sacrifice on towers the plan no longer needs, since CHIMPS cannot sell. The bot already has `Game.targeted_ability`.
- Without (2) she stays around L15 at R90 and her mid-game is weak.

**Etienne's map-wide camo.**
- Confirmed: Level 8, "all non-Paragon towers on screen", the same icon as Radar, and it does not stack with Radar (fandom:Etienne_(BTD6)).
- Arrival: about R40-45 Beginner and R36-40 Expert with MK.
- In the model it is lost twice: heroes are excluded, and the buff is on a sub-tower (G1).
- Value once credited [ESTIMATE]:
  - It removes the need for a 0-2-0 Radar ($3,725 Hard) or camo crosspaths from about R45.
  - It frees village placement for Jungle Drums or MIB only.
  - It makes Glaive Lord, Apache Prime, Sky Shredder and Carrier Flagship camo-capable without their camo paths.

**Benjamin.**
- In CHIMPS he has no cash effect. His RBE effects (Trojan from L7, Syphon from about L10 at R60) are real but small and timing-bound. Correctly a non-pick for CHIMPS.
- In Impoppable, Hard, Medium, Half Cash and similar modes, his cumulative cash placed at R6 on Impoppable with MK is [ESTIMATE, round levels from the table above]:
  - R6-50 at $90-250: about $10k
  - R50-70 at $250: about $5k
  - R70-88 at $1,000: about $18k
  - R88-95 at $2,500: about $17k
  - R95-100 at $5,000: about $25k
  - **Total about $75k, plus Skimming of $1-2 per spawned bloon** and Trojan bonuses.
- Whether Double Cash doubles his end-of-round income is [UNVERIFIED].
- The model cannot see any of it (F1 and G8).
- Note the timing: most of the cash comes after R80. For the bot's games-per-hour goal it matters most in long modes (Impoppable, Hard).

---

## 5. How a damage-only model should credit support

This keeps the model's current form: stations, zones, deadlines and calibration.

1. **Passive stat buffs** (rate, pierce, damage, range, camo, MIB). Apply them per station, as now, but fix G1-G4:
   - collect sub-tower buffs;
   - de-duplicate by type, keeping the max;
   - sum distinct range percentages, then add the additive ones;
   - implement `damage` and `pierce_percent`.
2. **Abilities as a duty cycle.** For an ability with cooldown C, duration T and effect E (a rate multiplier, pierce multiplier, map-wide source or soak):
   - **Average mode** (normal rounds): add E with uptime u = min(1, T/C). For a multiplier m that means 1 + u(m − 1).
   - **Saved mode** (rounds in `abilities.heavy_rounds_for`): count the ability **once at full strength** for its T seconds, positioned at the round's first blimp (`first_blimp_s`). That is how the bot presses it.
   - Always take the lower of the two when the bot's press is not certain. A hero ability counts only from its estimated unlock round.
   - Recalibrate with the abilities on.
3. **Slows and stuns** (Ice, Glue, Obyn totems, Pat stuns, Striker Concussive Shell, Silas, Psi Blast, Dan's nets):
   - A slow to speed factor f in a zone multiplies every **downstream** station's time-in-zone by 1/f for the affected layers, within the slow's pierce budget per second.
   - A stun of s seconds adds s to time-in-zone.
   - The slow zones are already exported (`zones` → `SlowBloonsZoneModel`), and `excluded_tags` already tells you BAD immunity.
   - This is safer than adding "damage", and it reproduces why slows help.
4. **Camo sharing and decamo.** Two different things:
   - *Sharing* (Radar, Etienne L8, Obyn L8 for Druids, Ezili's Totem) is a `camo` buff on stations. It is already supported for villages. It needs G1 for Etienne.
   - *Decamo* (Cleansing Foam, Ezili L9, Corvus Vision, Mortar Signal Flare): a station whose zone strips `camo` (and regrow, and lead→black for foam) from up to its pierce rate of layers. **Downstream** stations see those lots as non-camo.
   - This fits the existing lot flow: a lot that leaves a decamo zone keeps its id with `Camo` removed.
5. **Soaks** (Bloon Trap, XXXL Trap, Wall of Trees, Obyn Brambles): an RBE budget per cycle that removes whole lots (by subtree RBE) before damage. Respect `excluded_tags` (Moabs for Bloon Trap, Bad for XXXL).
6. **RBE transforms** (Benjamin's Syphon and Trojan): change the spawned lots, not the stations:
   - Syphon downgrades each lot spawned during its window by one rank (MOAB → Ceramic and so on, DDT from L18, never BAD).
   - Trojan removes the children of one non-blimp (or MOAB) lot every 5-7 s (3-4 s from L16).
7. **Income and discounts**: optimizer economy only (F1, V5). Never part of `round_margin`.

---

## 6. Top 10 fixes (in order of value for an automated bot)

1. **Let heroes into the stations at their estimated level**, behind a switch, then recalibrate.
   - Add `dps_model.hero_profile(hero, level)`, the same code as `profile()` but on `attacks()["heroes"]`.
   - In `forecast._build_stations` and `optimize_builds.station_of`, add the hero as a `Placed` at `estimate_hero_level(...)` (H-XP corrected) for each rated round.
   - Mark Psi, Silas, Etienne L1-19 and Corvus as "not exportable yet": Psi and Silas have no damage numbers, Etienne's drones are missing, and Corvus's spells are counted as permanent.
2. **Fix G1 and credit Etienne's L8 global camo.** Hoist sub-tower buffs into `Profile.buffs`; `station_for` then already honours `global`. Even without (1), the planner can then drop Radar villages from about R45 when Etienne is the hero.
3. **Credit village abilities and Spike Storm by duty cycle** (section 5.2): Call to Arms +42% average, Homeland Defense +133% average or full strength on heavy rounds, Spike Storm 200 piles every 45 s. Correct the cooldowns (H-CD).
4. **Carpet of Spikes' passive auto-storm (S1)** and **Perma-Spike's real stockpile plus start-of-round boost (S3).** Together these make the Spike Factory the R95-R100 last line that the research doc and community sources describe.
5. **Fix the Spiked Mines double explosion and black-immunity bug (S5).** It over-rates mines on R95 and R99 DDTs, where the bot loses.
6. **Fix buff stacking (G2, G3, G4):** de-duplicate same-type village buffs, add range buffs from distinct sources and apply additive range, and implement `damage` and `pierce_percent`.
7. **Overclock and Ultraboost on a named carry (E1):** bot press through `Game.targeted_ability`, and a model rate buff ×1.67 (plus Ultraboost stacks). This is the cheapest large multiplier in the game.
8. **Decamo stations (E3, Ezili L9) and slow and stun time-scaling (section 5.3).** This gives support towers a non-damage value the optimizer can buy.
9. **Correct hero bookkeeping:**
   - XP ratios: Corvus 1.425, Silas 1.5.
   - XP multipliers: map × MK.
   - Ability levels and cooldowns, per the H-CD table: Ezili, Rosalia, Ball of Light 60, UCAV 90/75, Drone Swarm 70/55/50, Biohack 30, Syphon 65, Long Arm 45.
   - Read the cooldowns from the game model rather than typing them in.
10. **Put income and discounts into the optimizer economy (F1, V5, Benjamin):** farm `profile.income`, Benjamin's per-level income with Skimming, village Business and Commerce discounts, Rosalia's and Silas's discounts. Then choose the hero per mode by **value**, not by `selected_hero or "quincy"`.

---

## 7. Recommended hero per situation (automated bot)

"Automated" means: no hand-placed items, no spellbook, abilities pressed on cooldown or at a scripted round.

| Situation | Hero | Why (and what the bot must do) |
|---|---|---|
| CHIMPS, any map, late-game safety | **Psi** | Infinite range, no aim, no placement. BFBs from L16 (about R88), DDTs and ZOMGs at L20. Press Blast and Scream on heavy rounds. Model work needed: Psi's damage is not in the export, so rate Psi from the wiki rules |
| CHIMPS, a carry that lacks camo (Glaive Lord, Apache Prime, Sky Shredder, Carrier Flagship, Druids without Obyn) | **Etienne** | L8 global camo at about R40-45 replaces Radar; UCAV for R75-76. Needs another camo source until L8, and lead from towers. Needs fix 2 |
| CHIMPS, Druid line | **Obyn** | L2/L11 pierce, L5 +40% range for x-3-x Druids, L8 radar for Druids in range, totems slow. Wall of Trees on a fixed point |
| CHIMPS, the owner's Adora plan | **Adora**, only once the bot can (a) press Ball of Light on heavy rounds with Strong targeting and (b) Blood Sacrifice towers the plan retires (CHIMPS has no selling) | Placement: maximum track inside radius 49-54, as the owner says. Without (b) she is about L15 at R90; the wiki and bloon.games rate her B-tier for CHIMPS |
| CHIMPS, cheap R6 start or short-range maps | Quincy, or Sauda on a known tight curve | Quincy: cheap, camo at L5. Sauda: placement is everything |
| Impoppable, Hard, Half Cash and other long income modes | **Benjamin**, if the defence holds R40-60 without hero damage | About $75k by R100 placed at R6 [ESTIMATE], most of it after R80, plus Trojan and Syphon RBE cuts. Needs fix 10 to show up in plans |
| Bomb- or Mortar-heavy builds | Striker Jones | L4/L18 +11% rate each, L5/L19 black popping, L8 +25% pierce in range. Needs G4 and an export of his buffs |
| Ice builds | Silas | Not rated at all now (0 damage exported). Avoid until it is modelled |
| Avoid for automation | Geraldo, Corvus | Hand-placed items and a spellbook. Corvus is also over-counted in the export |
| Avoid in CHIMPS | Ezili's Totem (it costs lives), Benjamin for cash, Pat (no camo, very short range) | |

---

## 8. Unverified or not checked

- Whether two villages' same-type buffs (Jungle Drums, Primary Training) really do not stack. The Commerce wording implies it, but no page states it outright.
- Whether there is an in-game cap on Perma-Spike piles on the track. This affects how far S3's carry cap can safely go.
- Why Long Life Spikes' one-round carry-over is missing from the export (S4).
- The per-round cap on Ultraboost stacks (3 or 10; search snippets disagree).
- Carpet of Spikes' own active-ability cooldown.
- Whether Double Cash doubles Benjamin's end-of-round income, and how Half Cash scales it.
- Which Monkey Knowledge the level-127 account owns (it decides the hero XP multiplier).
- Rosalia's laser exported as `placement=global`: real map-wide reach or an export artefact.
- Sentry Champion's per-sentry rates against the wiki.
- Etienne's exported "range 0.1" support buff from L2: the wiki levels list only self range (55 → 60 → 80). The v57 note "lower-level Etienne overwriting a higher one's range buff" says some range buff exists, but who receives it was not found.
- Reddit was not readable (403 everywhere). Community opinions here are search snippets only: an old r/btd6 2019 CHIMPS tier list via a mirror snippet, and the Steam and tier sites in section 4.3.

### Sources

**Fandom wiki pages (wikitext read in full through api.php):**
- https://bloons.fandom.com/wiki/Etienne_(BTD6)
- https://bloons.fandom.com/wiki/Adora_(BTD6)
- https://bloons.fandom.com/wiki/Benjamin_(BTD6)
- https://bloons.fandom.com/wiki/Geraldo
- https://bloons.fandom.com/wiki/Gwendolin_(BTD6)
- https://bloons.fandom.com/wiki/Striker_Jones_(BTD6)
- https://bloons.fandom.com/wiki/Pat_Fusty_(BTD6)
- https://bloons.fandom.com/wiki/Ezili_(BTD6)
- https://bloons.fandom.com/wiki/Captain_Churchill_(BTD6)
- https://bloons.fandom.com/wiki/Corvus
- https://bloons.fandom.com/wiki/Rosalia
- https://bloons.fandom.com/wiki/Silas
- https://bloons.fandom.com/wiki/Dan_D'Monke
- https://bloons.fandom.com/wiki/Obyn_Greenfoot_(BTD6)
- https://bloons.fandom.com/wiki/Psi_(BTD6)
- https://bloons.fandom.com/wiki/Heroes_(BTD6)
- https://bloons.fandom.com/wiki/Self_Taught_Heroes
- https://bloons.fandom.com/wiki/Monkey_Village_(BTD6)
- https://bloons.fandom.com/wiki/Monkey_Intelligence_Bureau
- https://bloons.fandom.com/wiki/Radar_Scanner
- https://bloons.fandom.com/wiki/Call_to_Arms
- https://bloons.fandom.com/wiki/Homeland_Defense
- https://bloons.fandom.com/wiki/Jungle_Drums
- https://bloons.fandom.com/wiki/Primary_Training
- https://bloons.fandom.com/wiki/Primary_Mentoring
- https://bloons.fandom.com/wiki/Monkey_Town
- https://bloons.fandom.com/wiki/Monkey_City
- https://bloons.fandom.com/wiki/Monkey_Wall_Street
- https://bloons.fandom.com/wiki/Perma-Spike
- https://bloons.fandom.com/wiki/Carpet_of_Spikes
- https://bloons.fandom.com/wiki/Spike_Storm_(BTD6)
- https://bloons.fandom.com/wiki/MOAB_SHREDR
- https://bloons.fandom.com/wiki/Spiked_Mines
- https://bloons.fandom.com/wiki/Super_Mines
- https://bloons.fandom.com/wiki/Long_Life_Spikes
- https://bloons.fandom.com/wiki/Deadly_Spikes
- https://bloons.fandom.com/wiki/Overclock_(BTD6)
- https://bloons.fandom.com/wiki/Ultraboost
- https://bloons.fandom.com/wiki/Bloon_Trap_(BTD6)
- https://bloons.fandom.com/wiki/XXXL_Trap
- https://bloons.fandom.com/wiki/Cleansing_Foam_(BTD6)
- https://bloons.fandom.com/wiki/Beast_Handler
- https://bloons.fandom.com/wiki/Banana_Farm_(BTD6)

**Search snippets only:**
- https://nerdlodge.com/btd6-adora-guide
- https://www.bloonswiki.com/Etienne_(BTD6) (the page itself returned 403)
- https://www.bloonswiki.com/Perma-Spike_(BTD6)
- https://nyc1.lr.ggtyler.dev/r/btd6/comments/eefaum/comprehensive_tier_list_for_chimps_by_path (an r/btd6 mirror, 2019)
- https://bloon.games/best-heroes-to-use-in-chimps-mode-btd6
- https://steamcommunity.com/app/960090/discussions/0/3187992943272748431 (Ultraboost and Overclock stacking)
