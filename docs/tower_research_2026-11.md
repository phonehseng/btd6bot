# Tower and hero research (November 2026, game version 57.4)

This is research for the bot's strategy tables. Nothing in the code was changed.

**Sources.**
- **Official patch notes**, read in full through the Steam news API for app 960090 (v52 to v57). These are the primary source.
- **Fandom wiki pages**, read in full through the wiki's `api.php`.
- **Costs** were computed from the wiki's price module (`Module:PricesBTD6/data`). Hard/CHIMPS is medium × 1.08 and Impoppable is medium × 1.2, each upgrade rounded to $5. They are checked against the patch notes below.
- **Not readable:** bloonswiki.com, steamdb and gamepatchnote returned 403, and reddit was not fetched. The community claims come from bloon.games and from search snippets.

**Marking.**
- **[UNVERIFIED]** marks a claim no fetched source confirmed.
- **[ESTIMATE]** marks my own estimate.

Wiki links below are written as `fandom:<Page>`, meaning https://bloons.fandom.com/wiki/<Page>.

---

## 1. Current version and recent balance changes

**Current version: 57.4, released 23 Oct 2026.**
- Earlier 57.x releases: 57.0 on 7 Oct, 57.1 on 13 Oct, 57.2 on 16 Oct and 57.3 on 21 Oct (fandom:Version_History_(BTD6)).
- The Steam feed has no update after 57.0. Version 58 is announced but not released. It is due to bring a new support tower, Mod System v1, and more Monkey Knowledge plus a higher level cap (v57.0 notes, "Looking Forward": https://steamstore-a.akamaihd.net/news/externalpost/steam_community_announcements/1846018067931512).
- `docs/research_strategies.md` says "v57.3". That was correct at the time it was written.

**Releases this year.**
- v53 (Feb)
- v54 (Apr): Druid Paragon *Root of all Nature*
- v55 (Jun), plus 55.2, which added the hero Dan D'Monke / Masqued Macaque
- v56 (Aug): new tower **Skywarden**
- v57 (Oct): Sniper Paragon **S.P.I.D.E.R. Monkey**

### Changes that matter for this research

**v57.0** (notes linked above)
- Sniper:
  - x4x Supply Drop can toggle to **Ammo Drop**. This gives shrapnel all-type popping and more pierce and damage. It is useful in CHIMPS now.
  - 57.1 fixed it so Ammo Drop grants lead popping (fandom:Bloons_TD_6/Balance_changes/Version_57.x).
- Super Monkey:
  - The $20,001 Magic sacrifice wind now **removes Camo**.
  - The $35,001 version hits DDTs. This is the new route to camo for the Temple.
- Bomb Shooter:
  - Bomb Blitz is limited to once a round.
  - MOAB Assassin frag pierce goes 2 → 4 and frag count 16 → 8.
- Glue Gunner: Glue Splatter is $970 → $650, Glue Strike is $4000 → $4500, and Stickier Glue duration is 24 s → 18 s. The wiki price module still shows the old Glue prices.
- Dart Monkey: Crossbow Master fires 2 parallel bolts at half the attack rate.
- Skywarden:
  - Large price shifts.
  - x2x now does Plasma damage and pops lead.
  - Thunder's Decree is $3500 and its ability lasts 9 s.
- Village: Call to Arms and Homeland Defense can no longer be activated over an active buff. This makes "use on cooldown" safe for a bot.
- Engineer: Bloon Trap pays its pop cash immediately.
- Brickell: Naval Tactics was reworked.
- Quincy: Lv4 adds a Focus toggle.
- Paragons: extra tiers no longer count toward degree. The cash and damage caps were raised.

**v56.0** (https://steamstore-a.akamaihd.net/news/externalpost/steam_community_announcements/1840310314340464)
- **Druid:**
  - **Monarch of Storms** blowback speed is doubled and its blowback is now capped at 400.
  - The Druid Paragon pauses regrow globally.
- Ice Monkey: Super Brittle attack cooldown goes 1.2 s → 1.56 s, and Snowstorm costs $4750.
- Mortar: **xx1 now hits Camo**.
- Super Monkey:
  - Sun Temple sub-attack projectile distances were cut.
  - Robo Monkey defaults to First/Strong targeting.
- Buccaneer: Pirate Lord costs $29,000.
- Beast Handler: Giganotosaurus was reworked.
- Heroes:
  - Obyn gains Skywarden synergies.
  - **Corvus Nourishment now pays cash per mana spent.**
  - Rosalia Lv13 has less stall and more damage.

**v55.0** (https://steamstore-a.akamaihd.net/news/externalpost/steam_community_announcements/1834602721186059)
- **Spectre is nerfed:**
  - Frontal darts deal 8 → 6.
  - The bomb bonus to Ceramics goes 5 → 4.
  - Flying Fortress goes $85k → $90k.
- **Monarch of Storms:**
  - Damage goes 150 → 100.
  - The pierce penalties fall: MOAB 4 → 2, BFB 14 → 8, DDT 7 → 6, ZOMG 44 → 32. It now blows back more blimps per tornado.
- Adora:
  - Lv20 Ball of Light deals 15 → 20.
  - True Adora is buffed.
- Glue Strike: soaks 5 layers on a 40 s cooldown.

**v54.0** (https://steamstore-a.akamaihd.net/news/externalpost/steam_community_announcements/1829528821308320)
- **Druid:**
  - Druid of the Storm pierce goes 24 → 35.
  - **Ball Lightning (4xx) gains camo detection.**
  - Monarch's tornado can re-hit every 1 s.
  - **Spirit of the Forest's Vine Crush drops brambles.**
- **Elite Defender:** shrapnel damage goes 2 → 1, with +1 to Ceramics.
- **Ray of Doom:** the damage-over-time lasts 5 s → 30 s.
- Glaive Ricochet: faster, but pierce goes 30 → 15.
- Aircraft Carrier and Pirate Lord are nerfed.
- MOAB Shove missile damage goes up.
- Silas Ice Walls hit DDTs.
- Overclock lasts a flat 30 s on heroes.

**v53.0** (https://steamstore-a.akamaihd.net/news/externalpost/steam_community_announcements/1824459501605428)
- Druid x4x Jungle's Bounty:
  - It now pays cash and lives passively.
  - Its ability became **Vine Crush**, which grabs 10 non-blimp bloons anywhere on the map.
- **Ground Zero** costs $18k → $16k.
- The Biggest One's stuns are cut.
- Deadly Precision is cheaper and deals +50 to Ceramics.
- The Sub's de-camo pulse is faster.
- Embrittlement is nerfed.
- Sun Temple's sacrifice bonuses are reshuffled.

**v52.0** (https://steamstore-a.akamaihd.net/news/externalpost/steam_community_announcements/1818118366174315)
- Psi Lv3 Psychic Blast cooldown goes 40 s → 45 s.
- Obyn Wall of Trees pierce goes 3000 → 2500.
- MOAB Shove ZOMG slow is nerfed.
- Striker Jones Concussive Shell is nerfed.
- Sun Temple thresholds are respaced.

---

## 2. Tier lists for CHIMPS and Impoppable

The only fully read list dated for v57 is bloon.games, published 30 Apr 2026 and labelled v57, so it is internally inconsistent (https://bloon.games/btd6-chimps-mode-tier-list-best-towers-and-heroes/):

- **Towers:**
  - S: Alchemist, Village, Ninja, Druid.
  - A: Wizard (Prince of Darkness), Dartling (Plasma Accelerator), Spike (Perma-Spike), Super (Sun Avatar), Ice (Super Brittle).
  - B: Dart, Boomerang, Tack, Sniper, Sub, Heli, Engineer, Mermonkey.
  - C: Bomb, Glue, Ace, Mortar, Buccaneer, Desperado, Beast Handler, Skywarden.
  - Banana Farm is unusable in CHIMPS.
- **Heroes:**
  - S: Sauda, Geraldo.
  - A: Corvus, Psi, Dan D'Monke, Quincy, Obyn.
  - B: Etienne, Ezili, Adora, Churchill, Silas, Rosalia.
  - C: Gwen, Pat, Striker, Brickell.
  - Avoid: Benjamin in CHIMPS.

Other SEO tier sites disagree, for example on Adora, and were not used (search results only).

### Core picks by game stage

Costs are Hard/CHIMPS, with Impoppable in brackets.

**Early game (R6-R40)**
- Ninja 0-0-2 or 2-0-1, then 4-0-2 Bloonjitsu: $5,940 ($6,600).
- Druid 1-3-0 Druid of the Jungle: $2,595 ($2,880). See section 7.
- Sub 2-0-4: $6,485.
- Sniper 2-0-2 or 2-2-0: $2,920-3,135. Infinite range, and it pops lead.
- Dart 0-2-4 Sharp Shooter.
- Village 0-2-0 Radar for camo: $3,725 ($4,140).

**Mid game (R40-R80)**
- Alchemist 4-2-0 Berserker Brew: $6,620. Alchemist 4-0-2: $7,020.
- Village 2-3-0 MIB, which lets towers in range pop all bloon types: $13,875 ($15,420).
- Sniper 4-2-0 Maim MOAB: $12,100.
- Sun Avatar 3-0-2: $33,695 ($37,440).
- Plasma Accelerator 4-2-0: $19,440.
- Ice 2-0-4 Icicles for R63.
- Druid 2-0-4 Poplust spam.

**Late game (R80-R100)**
- Perma-Spike 0-2-5 or 2-0-5: $40,880.
- Prince of Darkness 0-2-5: $35,375.
- Glaive Lord 5-0-2: $39,200 ($43,555).
- M.A.D 2-5-0: $83,970.
- Elite Defender 0-2-5: $25,540.
- Cripple MOAB 5-2-0: $46,660.
- Monarch of Storms 5-0-2 or 5-2-0: about $73,660.

### Late blimp answers and round checks

| Threat | What it is | Strong answers (source) |
|---|---|---|
| **R63** | Leads plus three waves of 40-42 hyper-dense Ceramics | Icicles 2-0-4 or 0-2-4, any Ice slow, high pierce plus slows (fandom:Round_63_(BTD6)) |
| **R76** | Dense Regrow Ceramic rush | High-pierce abilities (Ground Zero, Blade Maelstrom), regrow blocking from the Radar Scanner, Druid Paragon (fandom:Round_76) |
| **R90** | 50 Camo Regrow Fortified Leads plus 3 DDTs | MIB plus Radar with fast attackers (fandom:Round_90) |
| **R95** | 500 camo regrow purples and 250 fortified camo leads, then **30 DDTs over 50 Fortified MOABs** | Prince of Darkness, Bloon Sabotage, Glue Storm, Perma-Spike + Stronger Stimulant, Icicle Impale, 2× Ground Zero, M.A.D (one missile kills a DDT), Pre-Emptive Strike (fandom:Round_95) |
| **R98** | 30 Fortified BFBs plus 8 tight ZOMGs, and a flood of Super Ceramics | Apache Prime + Overclock, Sky Shredder + Stimulant, M.A.D, Perma-Spike with blimp damage, Arctic Wind or Cryo, Downdraft (fandom:Round_98) |
| **R99** | Fortified DDTs, straight after R98 | Ability cooldowns must cover both rounds (fandom:Round_98) |
| **R100** | One BAD (28,000 HP), **immune to slows, knockback and most instakills** | First Strike (20k damage), M.A.D (51 hits), Spike Storm, Carpet of Spikes, Cripple MOAB's debuff, Lv20 Ezili Hex (fandom:Round_100) |

**Rule.** Monarch of Storms, Psi's Scream, MOAB Shove and Glue cannot stop a BAD. Every build needs raw blimp damage for R100.

---

## 3. Whole-map coverage options

"Whole-map" below means the tower hits anywhere without good placement. All costs are Hard/CHIMPS.

| Option | Exact crosspath | Cost | Whole-map? | Weaknesses | Notes |
|---|---|---|---|---|---|
| **Spirit of the Forest** | Middle path, **x-5-x**, best as **1-5-0** (owner guessed 0-0-5) | 1-5-0 $45,685; 2-5-0 $46,605; Impoppable $50,760 | **Yes.** Vines spread 20 units every 0.5 s until the whole track is covered, with infinite pierce. Vines within 50 deal 4 damage (30 to Ceramics and blimps), within 100 deal 3 (15), and elsewhere deal 2 (10) | Vines pop camo, but **lead and frozen need Hard Thorns (1-x-x)** or MIB. Low damage far from the tower. Vines are weak on R98 and R100 | +$1000 at the end of each round and +25 lives per ability use (not in CHIMPS). Pairs with Carpet of Spikes (fandom:Spirit_of_the_Forest) |
| **Monarch of Storms** (renamed from Superstorm in v50) | **5-x-x**; 5-0-2 for range, 5-2-0 | ≈$73,660 ($81,840); 5-0-0 $73,225 | **Partial.** Lightning has infinite range. Tornadoes are thrown from range 35-45 and bounce off map borders | Since v55: 100 damage and 200 pierce, with penalties MOAB 2, BFB 8, DDT 6, ZOMG 32. Blowback is capped at 400 (v56), and ZOMGs are blown back half as far. **BADs are immune.** Lightning is plasma, so it cannot pop purples | **DDT blowback is real**: penalty 6, and the wiki shows 10 Fortified DDTs blown back. The tornado is normal type and has camo detection (fandom:Superstorm, v55 and v56 notes) |
| **Glaive Lord** | **5-0-2** (Red Hot Rangs gives lead and frozen) | $39,200 ($43,555) | **No.** The orbit has radius 30 (34.5 with 5-0-1). Thrown glaives have range 43-49.5 with infinite bounce distance | The orbiting glaives detect camo, but **thrown glaives need camo detection** (a camo Village). Weak against dense R98 without grouped popping | The orbit hits 200 targets for 4 (+4 Ceramic) every 0.05 s. Thrown glaives deal 6 (+12 Ceramic) and **Shred** the first blimp hit for 100/s over 10 s. Strong next to a curve (fandom:Glaive_Lord_(BTD6)) |
| **Spectre** | **x-x-4** (owner guessed 0-0-5; 0-0-5 is Flying Fortress). Use **0-2-4** for Spy Plane camo, or 2-0-4 with a camo source | 0-2-4 $30,620 ($34,020); 2-0-4 $31,105. Flying Fortress 0-0-5 $127,225 | **Mostly.** Use the Centered Path flight path (from 0-0-2) set on a fixed point | Darts cannot pop lead. **The bombs do not hit black, so it cannot hurt DDTs without MIB.** Nerfed in v55 | "Advanced targeting" is **Centered Path**: the Ace flies a circle around a point you choose. The fixed stream fires 15 shots/s with weak seeking. Flying Fortress's three guns target First, Last and Close (fandom:Spectre, fandom:Monkey_Ace_(BTD6)) |
| **Sun Avatar** | 3-0-2 (Ultravision camo) | $33,695 ($37,440) | No (range 50) | Plasma cannot pop purple without MIB | Strong value carry. Since v56 it shows sacrifice icons in its range (fandom:Sun_Avatar_(BTD6)) |
| **Sun Temple** | 4-0-2 | ≈$148k | No (range 65) | Needs 4-0-2 or the v57 Magic sacrifice for camo. Huge footprint | Sacrifice-dependent (fandom:Sun_Temple_(BTD6)) |
| **Ground Zero** | 0-4-0 (Spy Plane is included, so it has camo) | 0-4-0 $19,710; 2-4-0 $20,790 | **Ability yes:** 700 damage to up to 2000 bloons on the whole screen, penetrating blimp layers, 35 s cooldown | Bomb arrays cannot hit black. Good on R76 and R95 only if timed | Cheaper since v53 (fandom:Ground_Zero_(BTD6)) |
| **Elite Defender** | 0-2-5 or 2-0-5 | $25,540; 2-0-5 $26,570 | **Yes** (Sniper, infinite range) | Camo needs 0-1-x. Lead needs 2-x-x or the Ammo Drop | Fires faster as bloons go further along the track (up to +100%). Fires 4× faster for 7 s after a life is lost. v54 nerfed the shrapnel (fandom:Elite_Defender) |
| **Elite Sniper** | 0-5-2 or 2-5-0 | $25,545 / $26,360 | **Yes** | Low damage itself | All Snipers +33% attack speed. Supply Drop gives $3000 (not in CHIMPS) or, since v57, an **Ammo Drop** toggle (fandom:Elite_Sniper) |
| **Cripple MOAB** | 5-2-0 | $46,660 ($51,840) | **Yes** | Single target | 140 damage per shot. Stuns and cripples blimps (+5 damage taken). Against a BAD the stun lasts 0.75 s, but the debuff still applies (fandom:Cripple_MOAB) |
| **Plasma Accelerator / Ray of Doom** | 4-2-0 / 5-2-0 | $19,440 / $100,440 | **Yes, with Locked aim**: the beam is effectively infinite | Plasma Accelerator cannot pop purple. Camo needs x-1-x | Ray of Doom does normal damage, 1000 pierce, and a 30 s shock DoT (v54) (fandom:Ray_of_Doom) |
| **M.A.D** | 2-5-0 | $83,970 ($93,300) | **Yes, with Locked aim.** Missiles fly off-screen | Inaccurate. Low damage to small bloons | +450 to blimps per missile. The best non-ability answer to R100 (fandom:M.A.D, fandom:Round_100) |
| **Monkey Sub, Advanced Intel** | 2-0-4 | $6,485 | **Yes**: it shoots anything inside any tower's range | Camo through other towers or 3-x-x | The bot's existing water staple (fandom:Advanced_Intel) |
| **Energizer** | 5-2-0 | $35,425 ($39,365) | Yes, as a buff | Water only | Global −20% ability cooldowns, heroes +50% XP in range (fandom:Energizer) |
| **Mortar** | 5-2-0 The Biggest One $49,815; 0-5-x Pop and Awe ≈$51,295; 0-2-4 Signal Flare decamo $13,715 | — | **Yes**: it aims at a fixed point | Inaccurate on fast bloons | Pop and Awe stuns all bloons on screen 8 times over about 8 s (not BADs), with a 60 s cooldown. The v56 xx1 change hits camo (fandom:Pop_and_Awe) |
| **Navarch of the Seas** | Buccaneer Paragon (needs every Tier 5 Buccaneer) | Very high | — | Water only. Only one can exist. Unrealistic in CHIMPS | (fandom:Navarch_of_the_Seas) |
| **Others** | Heli Apache Prime 5-2-0 ($75,765) and Sky Shredder 5-0-2 | — | Fly anywhere | — | Top 2TC carries (fandom:2TC) |
| | Druid of the Jungle 1-3-0 | $2,595 | Vine is global | — | See section 7 |
| | Psi (hero) | — | Infinite range | — | See section 4 |

---

## 4. Heroes

Hero costs are Hard; CHIMPS starts with $650.

### Benjamin ($1,295)

**Abilities and levels** (fandom:Benjamin_(BTD6))
- **Biohack (Lv3):** the 4 nearest towers get +1 damage for 6 s, then cannot attack for 2 s, on a 30 s cooldown.
- **Bank Hack (Lv5):** banks earn +5%, rising to +12% at Lv9.
- **Bloon Trojan (Lv7):** a bloon it hits, up to a MOAB, spawns **no children** when popped.
- **Syphon Funding (Lv10):**
  - For 10 s, every *newly spawned* bloon is downgraded one rank and pays double cash. The cooldown is 65 s.
  - It affects DDTs from Lv18. At **Lv20** it lasts 20 s and pays triple cash.
  - BADs and Bosses are never affected.

**How it "takes out the first MOAB."**
- If Syphon is active when the R40 MOAB spawns, the MOAB enters as a **Ceramic**.
- Bloon Trojan can hit the MOAB, so its four Ceramics never appear.
- A bot using abilities on cooldown will often miss the spawn window. Syphon must be held and fired at the start of R40. [UNVERIFIED: the round when Lv10 is reached.]

**CHIMPS.**
- Benjamin generates no money, and the wiki and bloon.games call him useless there.
- The wiki notes a niche use: Syphon and Trojan reduce RBE, paired with Perma-Spike.

**Impoppable and other modes.** This is where he belongs: the best simple income hero, with no aiming at all.

### Etienne ($700 Hard, $650 medium after price changes)

Abilities (fandom:Etienne_(BTD6)):
- Lv3 Drone Swarm.
- **Lv5:** camo detection for himself.
- **Lv8 UAV:** "All non-Paragon towers on screen" get **camo detection**. This is confirmed as **Level 8 and map-wide**.
- Lv10 UCAV ability, on a 90 s cooldown, rising to 75 s later.
- Lv20 Perma-UCAV.

Notes:
- Weak early, and he has **no lead popping**.
- The UAV makes Radar villages unnecessary.
- It pairs with Apache Prime, Carrier Flagship, Sky Shredder and Glaive Lord.
- v57 fixed a lower-level Etienne overwriting a higher one's range buff.

**Automation:** excellent, with no aiming.

### The other heroes

| Hero | Hard cost | Key levels | CHIMPS role | Fit for automation |
|---|---|---|---|---|
| **Psi** | $1,080 | Infinite range. Lv3 Psychic Blast (stuns 200 bloons, 45 s cooldown). Lead at Lv6, Ceramics at Lv7, Lv10 Psionic Scream, purples at Lv11, MOABs at Lv14, **BFBs at Lv16**, DDTs and ZOMGs at Lv20 | A-tier late game. Lv16 is the practical goal for R94, R96 and R98 | **Best:** no placement and no aiming, and abilities can fire on cooldown (fandom:Psi_(BTD6)) |
| **Obyn** | $700 | Lv2 Druid +1 pierce. **Lv5: x-3-x Druids on screen +40% range.** **Lv8: Druids in his range get a Radar (camo) buff.** Lv10 Wall of Trees on a selected point, 2500 RBE | Best Druid and Magic hero | Very good. Wall of Trees needs only a fixed point (fandom:Obyn_Greenfoot_(BTD6)) |
| **Sauda** | $650 | Camo from Lv1. Range 23-29. Lv3 Leaping Sword, Lv10 Sword Charge | S-tier, but **placement on a tight curve is everything** | Good only on maps with a known curve |
| **Geraldo** | $810 | A shop of items placed by hand | S-tier for humans | **Poor:** items need choosing and placing |
| **Adora** | $1,080 | See section 6 | B-tier in CHIMPS (weak mid game, slow levelling) | Medium |
| **Brickell** | $970 | Water. Naval Tactics reworked in v57 (Lv8 hits all water towers) | Situational | Good on water maps |
| **Corvus** | $1,430 | Spellbook. v56 Nourishment pays cash | A-tier for experts | **Poor:** constant spell casting |
| **Rosalia** | $945 | Lv6 workshop discount on towers nearby | B | Medium |
| **Silas** | $920 | Ice synergy | B | Medium |
| **Quincy** | $585 | Cheap round-6 start, camo at Lv5 | A (cheap opener) | Good |
| **Dan D'Monke / Masqued Macaque** (v55.2) | $700 | Reposition and Rabble Rouser, which triggers Elite Defender's life-loss passive | A per bloon.games | Medium [UNVERIFIED details] |
| Ezili | $650 | Camo and lead at Lv1. Lv20 Hex kills a BAD | B | Good |

Sources for the table: fandom hero pages and https://bloon.games/best-heroes-to-use-in-chimps-mode-btd6/.

**Best heroes for a bot, in order:**
1. **Psi**
2. **Etienne**
3. **Obyn** with Druids
4. Quincy
5. **Benjamin** for Impoppable and standard modes only
6. Sauda on maps with a known curve

Avoid Geraldo and Corvus.

---

## 5. Proven CHIMPS strategies

**Works on many maps** (fandom:2TC, fandom:Round_95, fandom:Round_100)
- Prince of Darkness with a blimp tower. PoD + M.A.D and PoD + Ray of Doom are listed as among the easiest.
- Glaive Lord 5-0-2 + M.A.D 2-5-0. "Glaive Lord will pretty much solo until rounds 82-85", then M.A.D.
- Sauda or Wizard Lord Phoenix + Apache Prime.
- Spirit of the Forest + M.A.D, and Spirit of the Forest + Carpet of Spikes.
- Perma-Spike as the final defence.

**Least dependent on placement**
- **Snipers.**
- **Subs 2-0-4** with Advanced Intel.
- **Dartling or Mortar on Locked aim.**
- **Heli or Ace flight paths.**
- **Psi and Etienne.**
- The **Spirit of the Forest vine carpet.**
- The **Druid of the Jungle vine.**

bloon.games' Expert-map advice also points to global-range Sniper, Heli and Ace (search snippet).

**General Advanced and Expert guidance**
- Plan each stage before the game starts.
- Add slows, stuns and debuffs (Glue Strike, Embrittlement, Ice) instead of relying on raw damage alone.
- Have MIB by R90-95.
- Save ability charge for R95, R98, R99 and R100.

Sources: fandom:C.H.I.M.P.S./Strategies (search snippet) and https://bloon.games/common-mistakes-to-avoid-in-btd6-chimps-runs/ (search snippet).

**Why the bot never builds the owner's favourites.**
- The current roster (`docs/research_strategies.md`) uses Glaive Lord only as filler and never plans Monarch, Spirit of the Forest, Spectre, Etienne or Psi.
- Its "no Mortar, Dartling or Ace" rule rules out every aimed whole-map option, even though a Locked aim or Centered Path point needs only **one fixed point per tower**.

---

## 6. Adora, Spectre and Druid of the Jungle (owner's additions)

### Adora ($1,080 Hard, $1,200 Impoppable, levels 1.71× slower)

**Level curve** (fandom:Adora_(BTD6))

| Level | Gain |
|---|---|
| 1 | Seeking bolts: 1 damage, 5 pierce, pops lead and frozen, range 45 |
| 2 | Range 49 |
| 3 | Long Arm of Light: double range and pierce, normal damage type, for 10 s on a 45 s cooldown |
| 4 | 2 bolts |
| 5 | Pierce 8 |
| 6 | 3 bolts |
| 7 | Blood Sacrifice |
| 8 | 4 bolts |
| 9 | Range 54, +1 to fortified |
| 10 | Ball of Light: infinite range, 8 targets, follows her targeting |
| 11 | Faster attack |
| 12 | 5 bolts |
| 13 | Pierce 11 |
| 14 | 6 bolts |
| 15 | 2 damage |
| 16 | Long Arm of Light lasts longer and deals double damage |
| 17 | Faster attack |
| 18 | 8 bolts |
| 19 | Range 59 |
| 20 | Ball of Light 20 damage, normal type; sacrifice cap doubled |

**Weaknesses and CHIMPS view.**
- **No camo.**
- The wiki calls the mid game her greatest weakness in CHIMPS. She "is unable to naturally reach level 20" there.
- bloon.games rates her B-tier.
- The owner's view that she is "very popular" is not supported by the sources read.

**What a bot needs**
- **Placement:** her bolts *seek*, so place her where a circle of radius about 49 overlaps the most track, ideally inside a loop or at a corner where two lanes run close together. "At the edge of the track" means as close to the lane as allowed, so the circle is mostly track rather than grass. The coverage scorer the bot already has can do this with radius 49, later 54 and 59.
- **Targeting:** First (her default options are First, Last, Close and Strong). Ball of Light follows her priority, so use Strong for blimp rounds [ESTIMATE].
- **Abilities:** Long Arm of Light can fire on cooldown. **Do not automate Blood Sacrifice**, because it deletes a tower you choose.
- **Camo:** she needs camo support (a Village, Etienne at Lv8, or Obyn at Lv8 for magic towers only), or another camo tower.

### Spectre

**Crosspath.** It is **0-2-4** (Spy Plane camo, no Rapid Fire), costing $30,620 Hard or $34,020 Impoppable. With external camo, 2-0-4 costs $31,105.

**"Advanced targeting."** This is **Centered Path**, unlocked by the bottom path's 2nd tier.
- The Ace stops circling its runway and flies a circle around a **point you choose**.
- Its fixed stream of darts and bombs weak-seeks the bloons there.
- This is what separates it from the "random spray" of Circle and Figure-Eight flights.

**What a bot needs**
- **Placement:** the runway can go anywhere. Set Centered Path once onto the track point with the most overlapping lanes.
- **Targeting:** Centered Path, at one fixed point.
- **Weaknesses:** it **cannot damage DDTs or lead without MIB** (darts cannot pop lead, and the bombs ignore black). Pair it with a 2-3-0 Village MIB.
- **Upgrade order:** 0-1-0 → 0-2-0 (camo) → 0-2-2 → 0-2-3 → 0-2-4. Tier 4 alone costs $25,270.

### Druid of the Jungle

Sources: fandom:Druid_of_the_Jungle and fandom:Hard_Thorns.

**Crosspath and cost.**
- **1-3-0** costs **$2,595 Hard** or $2,880 Impoppable.
- Base $430, then 0-1-0 +$270, 0-2-0 +$380, 0-3-0 +$1,135, and Hard Thorns +$380.
- 2-3-0 (adding Heart of Thunder lightning) costs $3,515.

**Why it works early.**
- The vine grab has **infinite range and ignores line of sight**. It instakills one non-MOAB bloon at a time, chosen by target priority.
- After the grab, it leaves a bramble on the track that hits 20 bloons every 0.3 s for 4.5 s.
- Hard Thorns turns everything into **normal damage**, so it pops lead and frozen.
- Obyn Lv5 gives +40% range to x-3-x Druids.

**Limits.**
- **No camo:** it needs a Radar Village (0-2-0, $3,725), Obyn Lv8 within range of the Druid, or Etienne Lv8.
- **Only one vine at a time**, and a vine takes longer on stronger bloons. Dense rushes (R28 leads, the late-30s Ceramics) rely on the thorns (range 35) and brambles, so one Druid may not hold R36-39 everywhere [ESTIMATE].
- **The vine cannot grab blimps.**

**What a bot needs**
- **Placement:** anywhere near the track, preferably at a corner so the thorns help.
- **Targeting:** First early on; Strong once Ceramics appear [ESTIMATE].
- **Upgrade order:** 0-1-0 → 0-2-0 → 1-2-0 (cheap lead coverage) → 1-3-0.

---

## 7. Early whole-map opener: Druid of the Jungle

| Step | Buy | Hard cost | Target round [ESTIMATE] |
|---|---|---|---|
| 1 | Druid 0-0-0 then 0-1-0 (R6, $650 start) | $430 / +$270 | R6-7 |
| 2 | Obyn | $700 | R8-10 |
| 3 | 0-2-0, then 1-2-0 Hard Thorns | +$380, +$380 | before R10 (first leads) |
| 4 | 1-3-0 Druid of the Jungle | +$1,135 | R16-20 |
| 5 | **Camo**: Radar Village 0-2-0 *or* Obyn Lv8 next to the Druid (cheaper) | $3,725 | before R24 (camo greens) |
| 6 | Second Druid 1-3-0 | $2,595 | R28-33 |

- **Placement rule:** put the Druids inside Obyn's range (43) so his Lv8 radar buff covers them.
- **The round-cash timings are [ESTIMATE]** and should come from the bot's own cash model.

### Answering the R40 MOAB

The vine cannot grab blimps. Ranked by how well each answer suits a bot:

1. **Sniper 2-2-0** ($2,920, infinite range, pops lead, Strong targeting), moving to 4-2-0 Maim MOAB ($12,100) by R50 to R60.
   - Two or three Sniper 2-x-x are a placement-free MOAB answer.
2. **Druid 4-x-x Ball Lightning**: since v54 its camo is native and its lightning has infinite range. It is too expensive at R40 ($8,425 for 4-0-0).
3. Dart 0-2-4 Sharp Shooter or Ninja 4-0-x Sticky Bomb. These are known CHIMPS R40 answers, but they need a lane in range.
4. Benjamin's Syphon held for the R40 spawn. This is not CHIMPS-useful otherwise and is timing-dependent.

Then move to Druid 0-4-0 Jungle's Bounty and **1-5-0 Spirit of the Forest** ($45,685 total) for the late game. Add a blimp killer (M.A.D, Cripple MOAB or Perma-Spike) for R95-100.

---

## 8. Recommendations for the bot, in priority order

1. **Psi + Sniper core** (any map, zero placement).
   - Snipers: 2-2-0, then Maim 4-2-0 ×2, Elite Defender 0-2-5, and Cripple MOAB 5-2-0 for R100.
   - Add the Elite Sniper toggle and the v57 Ammo Drop. Abilities fire on cooldown.
   - Add a 2-3-0 MIB Village if any non-Sniper damage is used.
2. **Obyn + Druid line** (section 7).
   - 1-3-0 Druids early, then 1-5-0 Spirit of the Forest for whole-map cleanup.
   - Monarch of Storms 5-0-2 for blimp and DDT blowback on R95 and R98.
   - It **must** add BAD damage: M.A.D on Locked aim, or Perma-Spike.
3. **Etienne + any carry that lacks camo**.
   - Glaive Lord 5-0-2 next to a corner, Apache Prime, or Sky Shredder.
   - Lv8 removes the need for camo villages.
4. **Locked-aim tools**: one fixed point per tower.
   - Mortar 0-2-4 Signal Flare for decamo.
   - Pop and Awe on cooldown.
   - Dartling 4-2-0 → 5-2-0 Ray of Doom, or M.A.D.
   - This needs the executor to set "Locked" plus a point, which it already supports as "aim a cursor at a fixed point".
5. **Water maps**: Sub 2-0-4, Energizer 5-2-0, and First Strike 0-4-x saved for R100.
6. **Impoppable / standard**: **Benjamin** for income (with Double Cash; Fast Track OFF on Impoppable per owner), plus any of the above.

**Avoid for automation:**
- Geraldo and Corvus.
- Adora's Blood Sacrifice.
- Abilities that need precise timing as the main answer (Ground Zero on R95, Syphon on R40).
- Builds that rely only on slows or blowback for R100.

---

## Summary

- **The game is on version 57.4** (23 Oct 2026). Version 58 is announced but not out.
- **Checking the owner's guesses:**
  - **Spirit of the Forest** is the middle path, x-5-x. Use **1-5-0**, because Hard Thorns gives it lead.
  - **Superstorm** is now called **Monarch of Storms** (5-x-x). It really does blow DDTs back, but it never moves a BAD.
  - **Spectre** is **0-2-4**, not 0-0-5. Its "advanced targeting" is Centered Path around a point you choose, and it needs MIB to hurt DDTs.
  - **Glaive Lord 5-0-2** shreds blimps, but its orbit only covers a radius of 30.
  - **Etienne** gives every tower on screen camo detection from **Level 8**.
  - **Benjamin** is for income outside CHIMPS. To stop the first MOAB, Syphon Funding (Lv10) must be active when it spawns, or Bloon Trojan (Lv7) must hit it.
- **Best towers to cover the whole map:** Snipers, Druid of the Jungle and then Spirit of the Forest, Sub Advanced Intel, and Dartling or Mortar with Locked aim.
- **Best heroes for a bot:** Psi, Etienne and Obyn.
- **Biggest gap:** the bot plans no blimp killer that works on the R100 BAD. M.A.D, Cripple MOAB, Perma-Spike or First Strike would fill it.
