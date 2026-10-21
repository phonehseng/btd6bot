# Rounds database (BTD6 v57, Oct 2026)

`data/rounds.json` holds every standard round (1-140) and every Alternate Bloons Rounds (ABR)
round (1-140). Each round has:

- its bloon groups, with modifiers and spawn times;
- RBE, cash, duration and flags;
- top-layer blimp HP.

The file also has first appearances, mode notes, blimp HP and scaling, an answers catalogue
(tower + crosspath + Hard/Impoppable cost) and per-mode checkpoints.
`tests/test_rounds_data.py` validates it.

## Sources and verification

- **Group contents.** The cyberquincy `rounds_topper.json` export (topper64 data, last changed
  2024-08) and the bloonswiki round tables (published 2026-08 and 2026-07) were compared.
  The bloon, modifier and count of every group match in all **280 rounds**, so the round sets
  have not changed between v44 and v57.
- **RBE.** cyberquincy and bloonswiki agree. The test also recomputes RBE for rounds 1-80 from
  the groups and gets the same value every time.
- **Cash.** `cash` is pop cash plus the end-of-round bonus (100 + round). For rounds 101-140
  the bloonswiki values are used, because they reflect the current 0.05/0.04 cash-per-pop
  multipliers.
- **Blimp HP, speeds, immunities and mode rules** come from bloonswiki. Children RBE was
  cross-checked: for example, BAD 55,760 = 20,000 + 2 x 16,656 + 3 x 816.

## Key facts

| | Standard | ABR |
|---|---|---|
| Regrow | 17 | 3 |
| Black (explosion-immune) | 20 | 7 |
| White (freeze-immune) | 22 | 14 |
| **Camo** | **24** (1 camo green) | **5** (12 camo reds) |
| Purple (no energy/plasma/fire) | 25 | 15 |
| **Lead** | **28** (6 leads) | **10** (2 leads) |
| Ceramic | 38 | 32 |
| **MOAB** | **40** (1 MOAB, 200 HP, 616 RBE) | **40** (1 **fortified** MOAB, 400 HP, 856 RBE) |
| Fortified lead | 45 | 44 |
| Fortified ceramic | 46 | 46 |
| Camo ceramic | 51 | 51 |
| **Camo lead** | **59** (50 camo leads) | **24** (1 camo lead) |
| **BFB** | **60** | **54** |
| Fortified MOAB | 62 | 40 |
| Fortified BFB | 79 | 60 |
| **ZOMG** | **80** | **79** |
| **DDT** | **90** | **88** |
| Fortified ZOMG | 97 | 97 |
| Fortified DDT | 99 | 93 |
| **BAD** | **100** | **99** (Fortified BAD R100) |

- **No DDTs or BADs** spawn in any 3-80 game, standard or ABR. DDTs are only a CHIMPS,
  Impoppable or freeplay concern.
- **Hard R80** is a single ZOMG. **ABR R80** is two ZOMGs.

### Mode notes

- **Hard**
  - Starts at R3 with $650 and ends after R80. 100 lives.
  - Prices are 1.08x Medium, rounded to $5 per item.
  - Bloons move about 13.6% faster than on Medium (25% faster than Easy). Bloon HP is not
    scaled.
- **Impoppable**
  - R6-100, $650 start, 1 life.
  - Prices are 1.2x Medium.
- **CHIMPS**
  - Same rounds as Impoppable.
  - No continues, Monkey Knowledge, powers, selling, farms or hero boosters.
  - The end-of-round bonus *is* paid.
- **Freeplay ramping (R81+)**
  - Blimp HP x(1 + 0.02(r-80)), reaching 1.40 at R100. Speed ramps the same way.
  - Ceramics become 60-HP super ceramics (120 when fortified).
  - Non-blimp bloons release only one child.
- **Double HP MOABs:** every blimp has x2 HP, so R40 is 400 HP and R80 is 8,000.
- **Half Cash:** all income is halved, including the starting cash ($325).

### Blimps

| Blimp | HP | Fortified HP | RBE | Fortified RBE | Speed (u/s, base) | Children |
|---|---|---|---|---|---|---|
| MOAB | 200 | 400 | 616 | 856 | 25 | 4 ceramic |
| BFB | 700 | 1,400 | 3,164 | 4,824 | 6.25 | 4 MOAB |
| ZOMG | 4,000 | 8,000 | 16,656 | 27,296 | 4.5 | 4 BFB |
| DDT | 400 | 800 | 816 | 1,256 | 66 | 4 camo regrow ceramic |
| BAD | 20,000 | 40,000 | 55,760 | 98,360 | 4.5 | 2 ZOMG + 3 DDT |

- **DDT immunities:** sharp, shatter, cold, energy and explosion. DDTs are also camo.
- **BADs** cannot be stunned by Maim MOAB.
- **Ramped HP examples:**
  - R90 DDT: 480
  - R97 fortified ZOMG: 10,720
  - R99 fortified DDT: 1,104
  - R100 BAD: 28,000

**Damage-budget rule for a blimp checkpoint.** A blimp of HP `H` moving at `v` u/s spends
`L / v` seconds in a tower's coverage, where `L` is the track length inside the tower's
range. Require:

```
sum over towers (blimp_DPS_i * L_i / v)  >=  1.5 * H        (v_hard = base * 1.136 * speed_mult)
```

`damage_per_100_track_units_needed` in the checkpoints is `H * v / 100`. Reference blimp DPS
values from bloonswiki stats:

| Tower | Blimp damage | Notes |
|---|---|---|
| Bomb 0-3-0 MOAB Mauler | ~19 DPS | 16 dmg every 0.825 s |
| Sniper 2-0-0 | ~4.4 DPS | 7 dmg / 1.59 s, map-wide |
| Sniper 3-0-0 | ~12.6 DPS | 20 dmg / 1.59 s, map-wide; +50 dmg vs ceramics |
| Sniper 4-x-x Maim | 30 dmg/shot | stuns a MOAB for 3 s |
| Ninja x-x-4 Sticky Bomb | ~100 DPS | 450 dmg every 4.5 s |
| Bomb 0-4-0 MOAB Assassin | 750 per ability | 30 s cooldown; one-shots an unramped BFB layer |
| Super 3-0-x Sun Avatar | ~100 DPS | single target |
| Spike 0-3-0 MOAB SHREDR | 40 per pile | 80 per pile with Bigger Stacks |
| Alchemist 0-2-0 Perishing Potions | 20 per potion vs fortified blimps | |

Worked example: the Hard R40 MOAB moves at ~28.4 u/s. A Mauler covering 90 track units
deals only ~61 damage to it. A Sniper 3-0-0 solos the MOAB layer if the MOAB spends more
than 16 s on the track.

### Bot notes (corrections to `btd6bot/towers.py`, not applied there)

- **Base Wizard does not pop lead.** Its magic bolts are Energy, so they cannot pop lead or
  purple. Use Wizard 0-1-0 Fireball or higher for lead.
- **The Monkey Sub has no innate camo detection.** It gets camo from Submerge and Support
  (3-0-0, a decamo aura) or from another tower's detection through Advanced Intel (2-x-x).
- **Mortar 0-0-1** (Increased Accuracy) grants camo detection.
- **Large Calibre** was renamed **Large Caliber** in v57.0. OCR may see either name.

## Answer key (by category, with Hard costs)

The costs are totals on Hard, computed from `towers.py`.

| Need | Primary | Military | Magic | Support |
|---|---|---|---|---|
| Camo | Dart 0-0-2 ($525) | Sniper 0-1-0 ($650); Mortar 0-0-1 | Ninja 0-0-0 ($430); Wizard 0-0-2 ($920) | Spikes hit camo ($1,080); Village 0-2-0 Radar ($3,725) |
| Lead | Bomb 0-0-0 ($405); Boomerang 0-0-2 ($775) | Sniper 1-0-0 ($760); Sub 0-2-0 | Alchemist 0-0-0 ($595); Wizard 0-1-0 ($595) | Spike 2-0-0; Engineer 0-3-0 Foam; Village 0-3-0 MIB |
| Camo lead | Dart 4-0-2; Boomerang 0-0-2 + Radar | **Sniper 1-1-0 ($1,030)** | Wizard 0-2-2 ($2,110); Ninja 0-0-3 Flash Bomb ($3,670) | Spike 2-0-0; Village 0-2-0 + any lead popper |
| Black / white | Bomb 0-0-2 Frag (black); Ice 2-0-0 Cold Snap (white) | any non-explosive / non-cold | Ninja | Spike |
| Regrow | Tack 0-0-3 | Sniper 0-2-0 | Druid 0-2-0 Heart of Oak | Village 0-1-0 Grow Blocker; Engineer 0-3-0 |
| Ceramic / rush | Boomerang 3-0-2 ($1,940); Tack 4-2-0 Ring of Fire; Dart 4-0-2 | Sniper 3-2-0 ($5,295); Sub 2-0-4 | Ninja 4-0-2 + Alch 4-2-0; Super 3-0-2 | Spike 3-2-0 Spiked Balls; Village 2-0-2 |
| MOAB (R40) | **Bomb 0-3-0 Mauler ($2,185)**; Boomerang 0-3-0 Bionic | **Sniper 3-0-0 ($4,540)** or 2x 2-0-0; Sub 0-3-0 | Super 0-0-0 ($2,700); Alch 0-2-0 ($1,380) | Spike 0-2-0; Engineer 0-2-0 Deconstruction |
| BFB / fortified MOAB | Bomb 0-4-0 Assassin ($5,910); Boomerang 2-0-4 | Sniper 4-2-0 Maim ($12,100); Sub 2-0-4 | Ninja 2-0-4 Sticky ($9,830); Alch 4-2-0 | Spike 2-3-0 SHREDR ($6,810) |
| ZOMG | 2+ Bomb 0-4-0 | 2+ Sniper 4-2-0 | 2-3 Sticky; Sun Avatar 3-0-2 | Spike 2-3-0; Village 2-3-0 |
| DDT | Boomerang 0-4-2 + Radar (bombs can't, DDT is black) | **Sniper 4-2-0** (Normal dmg + camo + stun) | **Ninja 0-2-4** (decamos DDT); Sun Avatar 3-0-2 | Spike 2-3-0; **Village 2-3-0 MIB + Radar** |
| BAD | Bomb 0-5-0 | Sniper 5-2-0 | 2-3 buffed Sun Avatars; 4+ Sticky | Spike 2-0-5; Spike 0-4-0 Storm |

## Hard (rounds 3-80) critical rounds

Read the "by" column as: have the answer bought **before** starting that round.

| By | Round contents (RBE) | Danger | Primary | Military | Magic | Support |
|---|---|---|---|---|---|---|
| 3 | 10 red, 5 blue, 15 red (35) | $650 start | Dart 0-0-0 ($215) | Sniper ($380) | Ninja ($430) | - |
| 17 | 12 regrow yellow in 5 s (48) | regrow burst | Tack 0-0-1+ | Sniper 0-2-0 | Ninja 1-0-0 | Spike |
| 20 | 6 black (66) | explosion-immune | Bomb 0-0-2 | Sniper | Ninja | Spike |
| 22 | 16 white in 8 s (176) | freeze-immune | Ice 2-0-0 | Sniper | Ninja | Spike |
| **24** | 1 **camo** green + 20 blue (43) | **first camo**; R33 20 camo red + 13 camo yellow; R36 20 camo regrow green | Dart 0-0-2 | Sniper 0-1-0 | Ninja / Wizard 0-0-2 | Spike / Village 0-2-0 |
| 25 | 25 regrow yellow, 10 purple (210) | purple: no energy/plasma/fire | Dart, Boomerang | Sniper | Ninja (not Wizard bolts) | Spike |
| **28** | 6 **lead** (138); R30 9; R37 15; R38 14 | **first lead** | Bomb; Boomerang 0-0-2 | Sniper 1-0-0 | Alchemist; Wizard 0-1-0 | Spike 2-0-0 |
| 38 | 2 ceramic (1,157); R43 7 ceramic in 9 s; R46 6 fortified ceramic | first ceramic | Boomerang 2-0-2 / 3-0-2 | Sniper 2-0-0 | Ninja 2-0-x + Alch 2-0-0 | Spike |
| **40** | **1 MOAB** (616) | 200 HP + 4 ceramics | **Bomb 0-3-0** | **Sniper 3-0-0** or 2x 2-0-0 | Super 0-0-0; Alch 0-2-0 | Spike 0-2-0; Engineer 0-2-0 |
| 45 | 4 fortified lead + 10 camo purple + 180 pink (2,289) | fortified lead (4 HP), camo purple | Bomb 2-0-x | Sniper 1-1-0 | Alch + Ninja | Spike 2-0-0 |
| 50 | 2 MOAB, 20 ceramic, 8 fortified lead (3,540) | 2 MOABs | 2x Mauler | Sniper 3-0-0 | Alch 2-2-0 | Spike |
| 51 | 15 camo ceramic, 10 regrow rainbow (2,030) | camo ceramic | Dart 0-2-4 | Sniper 3-1-0 | Ninja 4-0-x | Village 0-2-0 |
| **59** | 50 **camo lead**, 30 ceramic incl. 10 regrow (4,270) | camo + lead together | Dart 4-0-2 | **Sniper 1-1-0+** | Wizard 0-2-2; Ninja 0-0-3 | Spike 2-0-0 |
| **60** | **1 BFB** (3,164) | 700 HP + 4 MOAB inside | Bomb 0-4-0 (750 ability) | Sniper 4-2-0 | Ninja 2-0-4 Sticky | Spike 2-3-0 |
| 62 | 250 purple, 5 MOAB, 2 fortified MOAB, 15 camo regrow rainbow (8,247) | purple swarm + fortified blimps | Boomerang / Bomb | Sniper | Alch 4-2-0 (+15 vs fortified) | Spike |
| **63** | 75 lead + 122 ceramic in 3 clumps (14,413) | **first ceramic wall** | Boomerang 3-0-2; Tack 4-2-0 | Sniper 3-2-0 x2 | Ninja 4-0-2 + Alch 4-2-0; Super 3-0-2 | Spike 3-2-0 |
| 64 | 6 MOAB + 3 fortified MOAB in 9.5 s (6,264) | 2,400 blimp HP burst | 2x Mauler; Assassin | Maim | Sticky | SHREDR |
| 65 | 100 zebra, 70 rainbow, 50 ceramic, 3 MOAB, 2 BFB (18,966) | mixed wall | Boomerang 3-0-2 | Sniper 3-2-0 | Ninja 4-0-2 | Spike |
| 67 | 13 fortified camo regrow ceramic + 8 MOAB (6,410) | camo + regrow + fortified | Dart 4-0-2 | Sniper 3-2-0 | Ninja + Alch | Village 0-2-0 |
| 69 | 40 fortified lead, 40 regrow black, 50 ceramic (6,680) | bombs fail (black) | Boomerang 0-0-2+ | Sniper 1-x-x | Alch | Spike 2-0-0 |
| 70 | 120 camo regrow white, 200 rainbow, 4 MOAB (13,184) | camo + freeze-immune swarm | Dart 0-2-4 | Sniper 0-2-x | Ninja 4-0-2 | Village 0-2-0 |
| 74 | 50 ceramic, 25 fortified camo regrow ceramic, 60 fortified ceramic, 1 BFB (18,054) | **ceramic wall 2** (82 s) | Tack 4-2-0 | Sniper 3-2-0 | Super 3-0-2 | Spike 3-2-0 |
| 75 | 7 BFB, 3 fortified MOAB, 28 lead in 22.6 s (25,402) | 6,100 blimp HP | 2x Assassin | Maim x2 | Sticky x2 | SHREDR |
| **76** | 60 regrow ceramic in 1.8 s (6,240) | instant regrow ceramic burst | Tack 4-2-0 | Sniper 3-2-0 | Druid 0-2-0 | **Village 0-1-0 / Engineer 0-3-0** |
| 77 | 11 MOAB + 5 BFB (22,596) | 5,700 blimp HP | Assassin | Maim | Sticky | SHREDR |
| **78** | 150 rainbow, 75 ceramic, 80 purple, 72 camo ceramic, 1 BFB (26,382, 90 s) | purple + camo ceramic | Boomerang 3-0-2 | Sniper 3-2-0 | Ninja 4-0-2 (not Sun Avatar for purple) | Village 0-2-0 / 0-3-0 |
| 79 | 500 regrow rainbow, 4 BFB, 2 fortified BFB (45,804) | highest RBE before 80 | Tack 4-2-0 | Sniper 4-2-0 | Sun Avatar | Village 0-1-0 |
| **80** | **1 ZOMG** (16,656) | 4,000 HP at ~5.1 u/s, then 4 BFB, 16 MOAB, 64 ceramics | 2x Assassin | 2x Maim | 2-3 Sticky; Sun Avatar | SHREDR at track end |

## Impoppable / CHIMPS (rounds 6-100)

Everything in the Hard table from R17 onwards still applies (1 life, so build a round
earlier). The extra checkpoints are:

| By | Round contents (RBE) | Danger | Primary | Military | Magic | Support |
|---|---|---|---|---|---|---|
| 6 | 4 green, 15 red, 15 blue (57) | $650 start, 1 life, no farms in CHIMPS | Dart | Sniper | Ninja | - |
| 81 | 17 BFB (44,506) | ramping starts; super ceramics (60 HP) | Assassin x2 | Maim x2 | Sticky x2 | SHREDR |
| 83 | 120 super ceramics (40 fortified, 40 regrow) + 30 MOAB (25,080) | 60/120-HP ceramics | Tack 4-2-0 | Sniper 4-2-0 (+50 ceramic) | Sun Avatar | Spike 3-2-0 |
| 85-88 | 2 ZOMG; 4 ZOMG; 2 ZOMG + 8 BFB + 18 MOAB | multiple ZOMGs | Assassin | Maim | Sticky / Sun Avatar | SHREDR |
| 89 | 20 fortified MOAB + 8 fortified BFB (64,384) | fortified blimps | - | Maim | Alch 4-2-0 (+15 fortified) | SHREDR |
| **90** | 50 fortified camo regrow lead + **3 DDT** (2,756) | **first DDT**: camo + lead + black, 480 HP, ~90 u/s | Boomerang 0-4-2 + Radar | **Sniper 4-2-0** | **Ninja 0-2-4**; Sun Avatar 3-0-2 | **Village 2-3-0 MIB**; Spike 2-3-0 |
| 91 | 100 fortified super ceramic (120 HP) + 20 BFB (71,160) | fortified ceramic wall | Tack 4-2-0 | Sniper 4-2-0 | Sun Avatar | Spike 3-2-0 |
| 92 | 50 fortified MOAB + 4 ZOMG (117,408) | blimp HP | Assassin | Maim | Sticky | SHREDR |
| 93 | 10 fortified BFB + 6 DDT (62,936) | DDTs behind cover | - | Maim | Sticky 0-2-4 | MIB |
| 94 | 25 BFB + 6 ZOMG in 15 s (178,112) | dense blimps | Assassin | Maim | Sun Avatar | Spike Storm |
| **95** | 500 camo regrow purple, 250 fortified camo regrow lead, 50 fortified MOAB, **30 DDT** (80,860) | camo purple (Sun Avatar can't hit purple without MIB) + 30 DDT | - | Sniper 4-2-0 x2 | Ninja 4-0-2 / 0-2-4 | **Village 2-3-0 MIB** |
| 96 | 30 BFB + 40 fortified MOAB + 6 ZOMG (238,952) | sustained blimp DPS | Assassin | Maim | Sun Avatar | SHREDR |
| 97 | 2 fortified ZOMG, 10,720 HP each (69,984) | first fortified ZOMG | - | Maim | Sticky | SHREDR |
| **98** | 8 ZOMG + 30 fortified BFB in 30 s (327,456; ~100,600 top-layer HP) | **hardest round** | Assassin x2 | Maim x2+ | 2-3 buffed Sun Avatars + Sticky | SHREDR / Spike Storm |
| 99 | 60 MOAB + 9 fortified DDT (1,104 HP each) | fast fortified DDTs | - | Sniper 4-2-0 | Ninja 0-2-4 | MIB + Spike 2-3-0 |
| **100** | **1 BAD**: 28,000 HP, 67,200 RBE | no Maim stun; children 2 ZOMG + 3 DDT | Bomb 0-5-0 (T5) | Sniper 5-2-0 (T5) | 2-3 Sun Avatars, 4+ Sticky | Spike 2-0-5 (T5); Spike 0-4-0 Storm |

## ABR (Hard, rounds 3-80) critical rounds

| By | Round contents (RBE) | Danger | Primary | Military | Magic | Support |
|---|---|---|---|---|---|---|
| 3 | 6 blue, 5 regrow blue, 15 red (37) | regrow at R3 | Dart | Sniper | Ninja | - |
| **5** | 12 **camo** red + 1 camo regrow red (52); R7 15 camo blue; R16 20 camo green | **camo from R5** | Dart 0-0-2 | Sniper 0-1-0 | **Ninja** | Spike |
| 7 | 2 black (90) | explosion-immune | Bomb 0-0-2 | Sniper | Ninja | Spike |
| **10** | 2 **lead** (210); R23 4; R28 6 regrow lead | lead from R10 | Bomb | Sniper 1-0-0 | Alchemist | Spike 2-0-0 |
| 15 | 3 purple (216); R22 16 purple | purple | Dart / Boomerang | Sniper | Ninja | Spike |
| **24** | 1 **camo lead** (23); R30 9 camo lead | camo lead | Dart 4-0-2 | **Sniper 1-1-0** | Wizard 0-2-2; Ninja 0-0-3 | Spike 2-0-0 |
| 27 | 250 camo red/blue/green/yellow (535) | camo rush | Dart 0-2-2 | Sniper 0-1-x | Ninja 2-0-1 | Village 0-2-0 |
| 32 | 3 ceramic, 5 rainbow, 10 purple (657) | first ceramic | Boomerang 2-0-2 | Sniper 2-1-0 | Ninja 2-0-1 | Spike |
| **40** | **1 fortified MOAB** (856) | 400 HP + 4 fortified ceramics: 2x standard R40 | **2x Bomb 0-3-0** | **Sniper 3-1-0** | Alch 0-2-0 (+15 vs fortified) + Ninja | Spike 0-2-0 |
| 43 | 2 MOAB + 10 rainbow in 9.3 s (1,702) | 2 MOABs | Mauler | Sniper 3-x-x | Alch | Spike |
| 46 | 8 fortified ceramic in 7 s (912) | 20-HP shells | Boomerang 3-0-2 | Sniper 3-1-0 | Ninja + Alch | Spike |
| 50-53 | 2 fortified MOAB + 4 MOAB (R50); 28 camo fortified ceramic (R51); 3 fortified MOAB + 120 camo pink (R53) | camo + fortified | Mauler x2 | Sniper 3-2-0 | Alch 2-2-0 + Ninja 4-0-x | Village 0-2-0 |
| **54** | **BFB** + MOAB + 35 regrow black (4,165) | BFB 6 rounds early | Bomb 0-4-0 | Sniper 4-2-0 | Sticky | SHREDR |
| 59 | 50 camo regrow lead + 20 camo fortified ceramic (4,605) | camo lead mass | Dart 4-0-2 | Sniper 3-2-0 | Ninja 0-0-3 / Wizard 0-2-2 | Spike 2-0-0 |
| **60** | 1 **fortified BFB** (4,824) | 1,400 HP: Assassin no longer one-shots | 2x Assassin | Maim | Sticky | SHREDR |
| 62-65 | 250 purple + blimps (R62 13,748); ceramic wall with 40 camo ceramics (R63 14,820); 6 fortified MOAB + 2 BFB in 9.5 s (R64); R65 21,050 | purple, camo ceramic, blimp burst | Boomerang 3-0-2; Assassin | Sniper 3-2-0 / 4-2-0 | Ninja 4-0-2 + Alch 4-2-0 | Village 0-2-0 |
| 73-77 | fortified MOAB/BFB waves (16-34k RBE); R76 10 BFB in 10 s | fortified blimp DPS | Assassin x2 | Maim x2 | Sticky x2; Sun Avatar | SHREDR |
| **79** | 500 camo rainbow + 4 fortified BFB + **ZOMG** (59,452) | hardest ABR round: camo AoE + 9,600 blimp HP | Assassin | Maim x2 | Sun Avatar + Sticky | Village 0-2-0 |
| **80** | **2 ZOMG** (33,312) | 8,000 top-layer HP | 2x Assassin | 2x Maim | Sticky x3 | SHREDR |

ABR rounds 81-100 (DDT R88, BAD R99, Fortified BAD R100) are freeplay in standard play. They
are in the JSON for completeness.
