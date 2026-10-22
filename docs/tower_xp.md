# Tower XP in BTD6: rules for XP grinding

Research date: 2026-10-21. Basis: bloonswiki.com (Blooncyclopedia), which documents game versions up to about v57. The machine-readable version is `data/tower_xp.json`.
Anything marked **?** is not confirmed by a reliable source.

## 1. XP per round

XP is awarded **once, at the end of each completed round**. The amount is fixed for that round number and does **not** depend on pops, damage or lives.
Player XP, tower XP and hero XP all start from the same base amount.

```
base(r) = 20r + 20             r <= 20
        = 40(r-20) + 420       21 <= r <= 50
        = 90(r-50) + 1620      r > 50          (assumed linear past 140 ?)

cumulative(1..r) = 10r^2 + 30r                 r <= 20
                 = 20r^2 - 360r + 3800         21..50
                 = 45r^2 - 2835r + 65050       r > 50

tower_xp_round = base(r) * map_mult * (1.08 if Monkey Education) * freeplay_mult(r)
```

| r | 1 | 10 | 20 | 21 | 30 | 40 | 50 | 51 | 60 | 80 | 100 | 120 | 140 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base XP | 40 | 220 | 420 | 460 | 820 | 1220 | 1620 | 1710 | 2520 | 4320 | 6120 | 7920 | 9720 |

The full list for rounds 1 to 140 is in `tower_xp.json` under `xp_per_round`.

Note: the wiki sentence "XP is based on the round's RBE, 30% after round 71" describes **BTD5** only, not BTD6. The raw wikitext confirms this.

## 2. How the XP is split between towers

- At each round end, the round's tower XP is split **between tower types in proportion to the cash currently invested** in them (purchase price plus upgrades) for all towers on the map.
- Each type's share goes into that type's **single account-wide XP pool**, which pays for its upgrade unlocks.
- Example: $19,000 of Ninjas and $1,000 of Darts gives 95% to Ninja and 5% to Dart.

```
xp_to_type[T] = tower_xp_round * invested[T] / sum(invested over all non-hero towers)
```

Consequences:

- **Heroes are ignored** in the split. Hero XP is a separate stream, and placing a hero does not dilute tower XP.
- An **unupgraded tower vs a tier-5**: there is no flat per-tower amount. A tier-5 earns more only because more cash is in it. **Only the ratio matters.** A single $200 target tower with no other non-hero towers on the map gets 100% of the round's tower XP.
- **Tower count is irrelevant.** Many cheap towers are no better than one expensive tower of the same type.
- **Sold towers earn nothing**, because they have no invested cash at round end. A tower placed mid-round counts if it is still there at round end.
- Unknown **?**:
  - whether "invested" means price paid (after difficulty scaling and discounts), sell value, or base price;
  - how free Insta Monkeys, Paragons and sub-towers count.

  None of this matters when only the target type is on the map.
- Co-op: XP is split first between players by invested-cash ratio, then by type within each player.

Sources: [Tower XP](https://www.bloonswiki.com/Tower_XP), [Co-op (BTD6)](https://www.bloonswiki.com/Co-op_(BTD6)), [Sarah's BTD6 guide](https://sarahs-btd6-site.onrender.com/guides/prologue/knowledge)

## 3. Multipliers

| Factor | Multiplier | Source / confidence |
|---|---|---|
| Map: Beginner / Intermediate / Advanced / Expert | ×1.0 / ×1.1 / ×1.2 / ×1.3 (player, tower and hero XP) | [Map difficulty](https://www.bloonswiki.com/Map_difficulty) |
| Game difficulty Easy / Medium / Hard / Impoppable / CHIMPS | ×1.0 (no multiplier; harder modes only add more and later rounds) | absence of evidence **?** |
| Modes (Deflation, Apopalypse, Reverse, X-Only, ABR, Half Cash, Double HP MOABs) | ×1.0; only the round range differs | absence of evidence **?** |
| Freeplay (rounds after the win round, up to r100) | ×0.30 | [Experience](https://www.bloonswiki.com/Experience), [Freeplay](https://www.bloonswiki.com/Freeplay) (v24: 90%→70% reduction) |
| Freeplay rounds 101+ | ×0.10 (Impoppable and CHIMPS freeplay is always ×0.10) | same |
| Monkey Education (Support MK) | ×1.08 tower and hero XP | [Monkey Education](https://www.bloonswiki.com/Monkey_Education) |
| Self Taught Heroes / Monkeys Together Strong | hero XP only | [Hero](https://www.bloonswiki.com/Hero) |
| Double Cash | none (doubles all cash, so the ratio is unchanged) | **?** |
| Fast Track | skipped first 25% of rounds give no XP (Hard starts r22, Impoppable r29); no other effect **?**; not allowed in CHIMPS or Deflation | [Fast Track Mode](https://www.bloonswiki.com/Fast_Track_Mode) |
| Sandbox | 0: no rewards or stats, and heroes gain no round XP. Tower XP assumed 0 **?** | [Sandbox (BTD6)](https://www.bloonswiki.com/Sandbox_(BTD6)) |

The freeplay reduction is documented for player XP and stated generally ("XP"). Whether it also applies to **hero XP** is unclear **?**: a community hero calculator does not apply it.

### Base XP for a full game (no freeplay)

| Mode (round range) | Beginner | Intermediate | Advanced | Expert |
|---|---|---|---|---|
| Easy / Primary Only (1-40) | 21,400 | 23,540 | 25,680 | 27,820 |
| Deflation (31-60) | 45,950 | 50,545 | 55,140 | 59,735 |
| Medium / Military / Reverse / Apopalypse (1-60) | 56,950 | 62,645 | 68,340 | 74,035 |
| Hard / Magic / DHP / Half Cash / ABR (3-80) | 126,150 | 138,765 | 151,380 | 163,995 |
| Impoppable / CHIMPS (6-100) | 231,150 | 254,265 | 277,380 | 300,495 |

Freeplay add-ons on a Beginner map:

| Freeplay stretch | XP |
|---|---|
| Easy r41-100 (×0.3) | 63,045 |
| Medium r61-100 (×0.3) | 52,380 |
| Hard r81-100 (×0.3) | 31,590 |
| r101-140 (×0.1) | 31,860 |

## 4. Player XP, tower XP, hero XP, excess XP, Paragons

- **Same base amount** each round for all three. Each stream applies its own modifiers (Monkey Education applies to towers and heroes).
- Player XP is not split. Above level 155 it goes into Veteran levels, one per 20M XP.
- **Excess tower XP**: after all 15 upgrades are unlocked, XP keeps accumulating. A community report mentions a Banana Farm with 9.4M XP. That XP is what pays for the **Paragon unlock**. Beyond that, or for a type without a paragon, it has no known use **?**.
- **Paragon unlock costs tower XP only, no Monkey Money.** All 15 regular upgrades must be unlocked first, then the paragon's own XP cost below.
- **Building a paragon** in game: all three tier-5s of the type must be on the map, then you pay the cash cost (Medium prices below, scaled by difficulty). Only one of each paragon can exist at a time. In Sandbox a paragon is available only after you have built it once in a real game.
- **Paragon Degree** (1-100) comes from "power" earned by the towers it absorbs. Rules as of v57:
  - **Cash** (cap 80,000): absorbed non-T5 towers give 1 power per (cost/20,000) dollars; the slider gives 1 power per (cost × 1.05/20,000) dollars.
  - **Extra tier-5s** (cap 50,000): 6,000 each beyond the first three.
  - **Damage and income** (cap 125,000): 1 power per 180 damage, or per $45 of income, by the absorbed towers.
  - **Paragon Power Totems** (no cap): 2,000 each.
  - Required power for degree D (2 ≤ D ≤ 99): `P(D) = (50D^3 + 5025D^2 + 168324D + 843000)/600`. P(100) = 200,000. Degree 20 needs about 11k power, degree 40 about 31k.
  - Console versions still use an older formula, which includes an "upgrades" category.
  - Source: [Paragon](https://www.bloonswiki.com/Paragon)

## 5. Upgrade XP costs

Full per-upgrade data (name, Medium cash cost, XP) for all 26 towers is in `tower_xp.json` → `towers`, parsed from [List of upgrades in BTD6](https://www.bloonswiki.com/List_of_upgrades_in_BTD6).

General pattern per path, approximately:

| Tier | XP per upgrade |
|---|---|
| T1 | 100-500 (Dart T1s are free) |
| T2 | 300-1,500 |
| T3 | 2,000-3,000 |
| T4 | 7,500-16,000 |
| T5 | 22,000-50,000 |

Super Monkey costs far more (T4 35-50k, T5 85-150k), and the Beast Handler's T5s cost 90-110k. Tier-5s make up about 60-95% of a tower's total.

The table below sums each tier across the 3 paths:

| Tower | T1 | T2 | T3 | T4 | T5 | All 15 | Paragon XP | Total incl. paragon |
|---|---|---|---|---|---|---|---|---|
| Ice Monkey | 480 | 1,500 | 7,500 | 25,750 | 82,500 | 117,730 | Herald of Everfrost 750,000 | 867,730 |
| Alchemist | 425 | 1,750 | 6,750 | 28,500 | 82,000 | 119,425 | - | - |
| Dart Monkey | 0 | 300 | 6,000 | 29,000 | 87,000 | 122,300 | Apex Plasma Master 500,000 | 622,300 |
| Tack Shooter | 440 | 1,540 | 7,150 | 27,250 | 87,000 | 123,380 | Crucible of Steel and Flame 500,000 | 623,380 |
| Glue Gunner | 400 | 2,050 | 7,500 | 25,500 | 92,500 | 127,950 | - | - |
| Boomerang Monkey | 330 | 1,560 | 8,000 | 27,000 | 97,500 | 134,390 | Glaive Dominus 500,000 | 634,390 |
| Bomb Shooter | 530 | 2,250 | 8,200 | 30,000 | 97,500 | 138,480 | BOMB (Ballistic Obliteration Missile Bunker) 750,000 | 888,480 |
| Spike Factory | 470 | 1,800 | 7,000 | 35,000 | 97,000 | 141,270 | Mega Massive Munitions Factory 1,000,000 | 1,141,270 |
| Wizard Monkey | 380 | 1,800 | 7,100 | 34,000 | 100,000 | 143,280 | Magus Perfectus 1,000,000 | 1,143,280 |
| Mortar Monkey | 470 | 1,850 | 7,000 | 39,500 | 96,000 | 144,820 | - | - |
| Sniper Monkey | 450 | 2,000 | 8,750 | 31,500 | 102,500 | 145,200 | S.P.I.D.E.R. Monkey 750,000 | 895,200 |
| Engineer Monkey | 480 | 1,550 | 5,650 | 34,500 | 105,000 | 147,180 | Master Builder 750,000 | 897,180 |
| Desperado | 550 | 1,700 | 8,850 | 41,500 | 98,000 | 150,600 | - | - |
| Skywarden | 525 | 1,700 | 8,500 | 42,000 | 98,000 | 150,725 | - | - |
| Monkey Village | 560 | 4,250 | 8,500 | 47,500 | 90,000 | 150,810 | - | - |
| Druid | 410 | 1,900 | 6,200 | 37,000 | 108,000 | 153,510 | Root of all Nature 750,000 | 903,510 |
| Monkey Sub | 405 | 2,350 | 8,000 | 41,000 | 103,000 | 154,755 | Nautic Siege Core 1,000,000 | 1,154,755 |
| Monkey Buccaneer | 500 | 1,950 | 8,800 | 35,500 | 112,000 | 158,750 | Navarch of the Seas 750,000 | 908,750 |
| Monkey Ace | 440 | 1,950 | 8,200 | 42,000 | 110,000 | 162,590 | Goliath Doomship 1,000,000 | 1,162,590 |
| Ninja Monkey | 490 | 1,650 | 6,500 | 45,500 | 122,500 | 176,640 | Ascended Shadow 500,000 | 676,640 |
| Heli Pilot | 490 | 1,850 | 8,500 | 47,500 | 145,000 | 203,340 | - | - |
| Banana Farm | 600 | 2,700 | 9,700 | 60,000 | 150,000 | 223,000 | - | - |
| Dartling Gunner | 390 | 1,950 | 8,300 | 41,500 | 190,000 | 242,140 | - | - |
| Mermonkey | 460 | 1,950 | 8,300 | 41,500 | 190,000 | 242,210 | - | - |
| Beast Handler | 750 | 1,550 | 3,000 | 14,750 | 300,000 | 320,050 | - | - |
| Super Monkey | 1,350 | 5,500 | 19,500 | 132,500 | 335,000 | 493,850 | - | - |

Notes on the table:
- Towers newer than the user's game version, such as Skywarden, may not exist in their install.
- The bot can compute remaining XP by summing the locked upgrades, and can read current XP from the in-game upgrade screen.

## 6. XP-farming rules for the bot

1. **Make the target type almost 100% of non-hero invested cash at each round end.** Its share equals its cash ratio. Any other type steals XP, including Banana Farms (unless the farm is the target). A hero is free, because heroes are excluded from the split.
   - This is easiest when one tower type can solo the game, e.g. on Easy or Medium.
   - Feeding two targets: balance the cash between them.
2. **Late rounds dominate.** Round 100 is worth 153× round 1, and r61-80 alone give 69,300 base XP. Hard (126k) and CHIMPS or Impoppable (231k) give far more XP per game than Easy (21k). Choose by **XP per minute** of real time, not per game.
3. **Use Expert maps** (×1.3) when the strategy is equally safe there.
4. **Enable Monkey Education** (+8%).
5. **Freeplay is penalised** (×0.3 up to r100, then ×0.1). It is still positive: Easy r41-100 adds about 63k, more than the Easy game itself. Worth it only if the time per round is low and there is zero risk of losing. Per the project rules, never risk a loss.
6. If a non-target support tower is needed only during a round, it could be sold before the round ends to raise the target's share. This is only allowed when it cannot cause a leak.
7. Paragon grinding: after all 15 upgrades are unlocked, keep feeding the type until it reaches its paragon XP (500k-1M). That takes roughly 2-4 full CHIMPS games' worth of XP on Expert maps (about 300k each), assuming all of it goes to the target.
