# BTD6 achievements: what the bot can get

Data: `data/achievements.json` (162 entries: the 156 of the Steam list plus 6
Legends DLC). Plans for restricted-win achievements:
`strategies/achievements/ach_*.yaml` (21 files).
Sources: the Steam achievement list for app 960090 (names, descriptions, hidden
flags, global unlock %), bloonswiki "Achievements (BTD6)" and the individual
achievement pages, which give the exact rules and wiki strategies. Researched
2026-10-21, game v57; re-checked 2026-11-07 (Steam still lists 156; bloonswiki
and the fandom wiki refused automated reads that day, so the rules below are
the 2026-10-21 research). Status: the main account's (SFYOSHHYV, level 150)
in-game scan of 2026-11-06 22:10 (`data/accounts/SFYOSHHYV.achievements.json`).

Names and descriptions follow the in-game text (bloonswiki). Where Steam
spells a name differently, the entry has a `steam_name` field (5 cases, e.g.
"Me Did A Job On DDT", "Master of Life"). The JSON also has `requirement`
(the exact rule where the text is vague or hidden), `reward`, `strategy`
(YAML id), `steam_api_id`, `steam_unlock_pct` and `dlc`.

## Where the main account stands (scan 2026-11-06)

| | count |
|---|---|
| catalog entries | 162 |
| read COMPLETE | 57 (59 cards; 2 OCR'd too badly to match a name) |
| read in progress | 41 (18 above 0 %, 23 at 0 %) |
| read "unknown" | 2 (Lookin fab, Season Starts) |
| not read | 62 |

The game sorts the list by completion: in-progress cards first (highest %
first, down to 0 %), COMPLETE cards last. Every 0 % card was read, so a card
the scan did not read is almost certainly a COMPLETE card near the bottom
(the scan stops after two pages with no new card). The planner still treats
an unread card as "unknown" (it may add value to a first-time medal), but it
never *replays* a map for one (see below).

## Why the bot never played an achievement build (fixed 2026-11-07)

`logs/bot.log` had no NEXT line with an `ach_*` build in weeks: the picks
were forced CHIMPS (NEXT file), last-resort medals, and "achievement:
Thrifty" / "achievement: Survivor" notes on normal medals. Three causes:

1. **Stale scan.** `PlannerConfig.achievements_state_path` was
   `data/achievements_state.json`, a scan from 2026-10-21. Since accounts
   got their own files the bot saves its scans to
   `data/accounts/<id>.achievements.json` (`identity.load_for` moves
   `achievements.STATE` there), so the planner used month-old data: it
   credited wins to Thrifty (complete) and saw none of the new progress.
   Now the default is `planner.ACCOUNT_SCAN`, resolved by
   `planner.account_scan_path()` to the current account's file (from
   `data/current_account.txt`, which `identity.load_for` writes).
2. **Never-replay rule.** Every achievement build is pinned to one map and
   mode (Unsung Monkeys: Logs Easy), and on this account all of those are
   beaten. `planner._candidates` dropped beaten pairs before scoring, so an
   achievement build could never be a candidate. Now an achievement build
   may replay its own map/mode (planner tier **ACH**) when all of this
   holds (`planner._replay_allowed`):
   - the scan read its card **in progress** (not complete, not unread);
   - its wins since that scan are fewer than
     `ceil(wins_needed x (100 - progress) / 100)` (the build's
     `constraints.wins_needed`, else the catalog's), so it stops and waits
     for the next scan (daily, or the reward claim that marks the card
     complete) instead of replaying forever;
   - its p clears the mode's own bar (no fallback bars, never LAST);
   - the build is bot-ready.
   Order: every first-time medal that clears its bar comes first (so the
   owner's black-border order is untouched), then ACH replays (surest
   first), then the last-resort LAST medals. A NEXT-file pick still beats
   everything (`runner.owners_pick`; it still refuses beaten map/modes).
   Normal strategies still never replay; safe mode's Beginner-first pass
   ignores ACH games (they earn no medal).
3. **Coverage.** `strategy.ANSWERS["moab"]` had no Spike Factory x-3-x
   (MOAB SHREDR), so the Unsung Monkeys build (2-3-0 spikes) failed
   `coverage()` for MOAB and `runner.planner_specs` dropped it. Added.

On the main account's data the planner now ranks, after the first-time
medals over their bar: `ach_unsung_monkeys` Logs Easy (p 0.93), then
`ach_freaky_friday` Logs Medium (p 0.92), then the last-resort medals.
Offline test: `tests/test_achievement_replays_offline.py`.

## Priority plan: what to go after next

Value = reward (Monkey Money, MK points, instas) per minute, single player,
on this account. "Bot" = the bot can do it with existing code.

| # | Achievement | Status | Reward | Bot? | What it needs |
|---|---|---|---|---|---|
| 1 | Unsung Monkeys | 30 % | Banana Farmer x2, 2-0-0 Farm insta | yes, now scheduled | `ach_unsung_monkeys`, 7 Logs Easy wins (~45 min) |
| 2 | Freaky Friday | 52 % | 150 MM, 0-4-0 Alchemist insta | yes, new build | `ach_freaky_friday`, ~2 Logs Medium games |
| 3 | Insta Century | 0 % | 1,000 MM, Monkey Boost x3 | owner by hand / new code | Place 100 Instas (the account has held 200 at once: Tower Keeper is done). Code: in-game Insta panel (below) |
| 4 | Instant Gratification | 0 % | 100 MM, random T5 insta | owner by hand | Place one tier-5 Insta once (1 min) |
| 5 | First Steps | 0 % | 100 MM | owner by hand | Quests menu -> "First Time Tutorial!" (~5 min) |
| 6 | Power User / Empowered / You've Got the Power | 32 % / 8 % / not read | 150 MM / 250 MM / Monkey Boost | new code | 17 / 92 more Power uses; cheap Powers bought with MM (owner now allows it). Spec below |
| 7 | Lookin fab | unknown | 500 MM | owner, once | Equip any owned hero skin on the bot's heroes; 100 wins then come from normal play |
| 8 | Sapper | 29 % | 500 MM, 1 MK point | passive | 3.55M more fortified layers. Comes from the R80+ games the bot already plays (Hard family, CHIMPS); far faster in long Easy freeplay (not supported). Best poppers: single-target non-insta damage - Elite Defender / Cripple MOAB snipers, Perma-Spike, Ninja, Sun Avatar; avoid BMA, XXXL Trap, Navarch (insta-kills), Shattering Shells / First Strike (strip or skip layers) |
| 9 | Ultimate Bloons Master | not read | 2,000 MM, 4 MK points | passive | 15 CHIMPS maps; the account record shows 15+ CHIMPS wins, so it is probably done (next scan) |
| 10 | Heavy Investment | 26 % | 100 MM, 3 Dart instas | new code | Create a Paragon with >= $401,626 extra on the slider; needs paragon purchase + slider code (also gives Big Spender/Apotheosis if open) |
| 11 | Glittering / Glorious / Magical Gold | 48 % / 9 % / 8 % | 150-250 MM + instas | passive (weekends) | Golden Bloons only on alternate weekends (Fri-Mon 08:00 UTC), R21+, not CHIMPS/Deflation. Magical Gold needs Magic Only games then: weekend gating not coded |
| 12 | Axis of Havoc | 0 % | Glue Trap x2, Camo Trap x2 | needs a build | One CHIMPS game with 5-x-x, x-5-x and x-x-5 snipers at once (~$95k of snipers at Hard prices). Appending them to a proven CHIMPS build does not fit its cash (Park Path's plan ends at R96). Needs a sniper-carry CHIMPS build checked with `tools/optimize_builds.py`. Low reward for a 35-min one-life game: last |
| 13 | Hook, Line, and Sinker | 2 % | 100 MM + 2 instas | passive-ish | 2,900 more MOAB Takedown hooks; the AbilityPlanner already fires Monkey Pirates/Pirate Lord on MOAB rounds, so add a 0-4-0 buccaneer to water builds when there is cash to spare |
| 14 | Crash of the Titans | 12 % | 300 MM, 0-0-4 Mortar insta | no | Shattering Shells (mortar 0-0-4; the account's mortar bottom path reads 0) against fortified DDTs (R90+, freeplay) |

Not worth it now / blocked: Moving House (Chinook redeploys need tower
picking), Bloon Master Populous (R200+ freeplay), 2 MegaPops (per-tower
damage readout), No Harvest (hand placement), 2TC and Josh's Constant (not
read, probably done), Snap of your fingers and Living on the Edge (need
deliberate leaks: the owner's never-lose rule; an explicit exception would
be needed), Limited Run (Trophy Store: real-money adjacent, skipped), I'll
Be Back (Monkey Money continues: forbidden). Co-op, races, bosses,
odysseys, daily challenges, contested territory, social and Legends DLC
entries are out (single-player rule / real money).

### Powers, Instas, hero skin, First Steps: built 2026-11-07, not yet run live

`menus.FORBIDDEN` is unchanged. Each routine clicks only words of its own
allow-list (`achtasks.allowed_word`: whole-word match, never real money)
and runs only while its card is wanted in the account's scan (read
"progress" or "unknown"). Daily caps per account in
`logs/achievement_tasks.json` (`achtasks`: 3,000 MM, 10 purchases, 400
clicks, 40 power uses, 30 insta uses, 4 failures per flow). Every routine
logs `achievement: ...` lines and saves a few screenshots a day of screens
no recording shows yet to `logs/achievement_captures/`.

| Module | Achievement | What it does | Calibrated from |
|---|---|---|---|
| `powers.py` | You've Got the Power, Power User, Empowered, Insta Century, Instant Gratification | Before round 1 of an Easy/Medium/Reverse (Powers also Primary/Military Only) game with p >= 0.85, never an `ach_*` build, never CHIMPS: Powers button -> up to 2 owned Powers (track ones dropped late on the track) and up to 2 Instas (lowest tier; one tier 5 while Instant Gratification is wanted) | Button position and lit/crossed-out look: recordings. The panel itself: NOT seen - read by OCR |
| `powershop.py` | Power User, Empowered | Main menu -> INSTAS + POWERS -> a cheap Power -> its MM price (10-500, no cents) -> one confirmation; only when the last game found no owned Power; real MM difference checked | Button position: recording. Shop screens: NOT seen |
| `heroskin.py` | Lookin fab | HEROES -> Obyn, then Quincy -> each skin icon with no price under it opens the skin's own page; its bottom button decides: UNLOCK FOR / a price = not owned (back arrow), SELECT / EQUIP / USE = clicked until SELECTED. A capture at every step; heroes found with no owned skin are not opened again | Live run 2026-11-07 18:06: Quincy's 2 skins priced; Obyn's 3 "New" skins also cost 2,500 MM each (the ribbon hides the price). So neither hero has an owned skin: Lookin fab needs a skin bought - an owner decision, the code never buys one |
| `quests.py` | First Steps | Look only: quest giver -> TUTORIALS tab -> logs every quest card (title, progress, GO button) and whether First Time Tutorial is listed; GO! never clicked | Live run 18:07 (capture `quests_20261107_180710.png`): the scroll monkey opens QUESTS with tabs ALL / TALES / CHALLENGES / TUTORIALS / EXPERIMENTS |

**To check live** (the first runs are the calibration; look at
`logs/achievement_captures/` and the `achievement:` lines):
1. What the Powers button opens: are Power names written on the tiles,
   and is the owned count shown as "x3"/"3" next to them? If not,
   `powers.owned_powers` finds nothing and nothing is clicked.
2. Does clicking an unowned Power in a game ask before spending? (The code
   answers any question with Cancel/No.)
3. Track Powers held like towers (red cancel X), instant ones working on
   one click; the Insta tab's word and its "a-b-c" tier labels.
4. That clicking the Powers button again closes the panel.
5. The INSTAS + POWERS screen: tab and price layout, confirmation wording.
6. The button an owned skin's page shows (no owned skin seen yet on
   Obyn or Quincy).
7. What the Quests menu's TUTORIALS tab lists.

**First Steps needs more than a look:** the First Time Tutorial is a
guided game that waits for the clicks it asks for (place a Dart Monkey
here, upgrade, press Play). The match code places towers by its own plan
with hotkeys and cannot read tutorial instructions, so a playing routine
would need: the quest's start button, an OCR reader for the tutorial
prompts with their target positions, and a click-what-it-says loop. A
5-minute job by hand.

### The original plan (kept for reference)

A Powers routine needs a narrow exception for its own buttons only:

1. **Buying** (main menu): the "INSTAS + POWERS" button (bottom row, about
   (.75, .93) per `docs/research_ui.md`) -> Powers tab -> a cheap Power
   (Road Spikes, Glue Trap, Camo Trap or Monkey Boost) -> its Monkey Money
   price button -> confirm. Never the "+" next to the Monkey Money counter
   (real-money shop) and never anything priced with cents (`menus._REAL_PRICE`).
   Read the price before clicking and cap the spend (e.g. 500 MM a day).
   Check whether "Our Powers Combined" (own 12 different Powers, 200 MM) is
   done in the next scan; if not, buy 12 different cheap ones once.
2. **Using** (in game, not CHIMPS - Powers are off there): the Powers
   button on the right-hand tower panel opens the owned Powers; click one,
   then a spot. Track Powers (Road Spikes, Glue Trap, Camo Trap, MOAB Mine)
   need a track point - `Track` already has them (the exit spot). Monkey
   Boost / Thrive / Time Stop need no target. One or two per game on a
   game the bot is sure of (p >= 0.85) is enough: 17 uses finish Power
   User, ~92 Empowered. Calibrate the panel and its hotkey (if any) from a
   screenshot first; the coordinates are not recorded yet.
3. **Instas** (Insta Century, Instant Gratification): the same in-game panel
   has an Instas tab: pick a tower, then a tier, then place it like a tower.
   Placing low-value instas early in a sure game (e.g. a 0-2-2 dart at R1)
   counts and does not change the plan. Insta Century gives 1,000 MM - the
   best reward on this list - but by hand it is only 100 placements.

## Verified rules the descriptions don't spell out
- **Tower-category wins** (First Monkeys First, War Monkeys, Abracadabmonkey, Unsung Monkeys): count *placed towers only*; heroes and Powers are allowed (since v5.0). The Primary/Military/Magic Only modes are not required, but they enforce the rule.
- **Sapper**: 5M *Fortified layers popped individually*. Insta-kills, fort-stripping (Shattering Shells) and layer-skipping (First Strike) don't count. Long Easy freeplay is fastest.
- **Chunky Monkeys** (hidden): 10 wins on Medium or harder using only Pat Fusty, Churchill, Buccaneer, Ace, Heli, Mortar, Super, Mermonkey, Farm, Village or Spike Factory.
- **Big Bloons** (hidden): 10 games with Pat Fusty. **Golden Ticket** (hidden): the Candy Falls Oompa-Loompa click sequence. **Stubborn Strategy** (hidden): 100 wins on maps with removables without removing any. **Alchermistman and Bloonacleboy** (hidden): a Bloon Master Alchemist reaches 900k damage before R100. **Not Lacking Critical Information** (hidden): 25k crits from Sharp Shooter, Crossbow Master, Robo Monkey, Tech Terror or Anti-Bloon.
- **All for one and one for one**: Hard, at most 1 tower on screen at a time (selling and replacing is OK).
- **2TC**: only 2 towers *ever bought* in a CHIMPS win.
- **Monkey Teams** (Team Player, Team Captain, Ultimate Team-up): single player. Runs Mon 08:00 to Fri 08:00 UTC, one map per difficulty, and the 3 allowed towers change every 3 h. **Golden Bloons** appear on the alternate weekends (Fri to Mon), from R21, never in Deflation or CHIMPS.

## Restricted-win plans (`kind: game_win_constraint`)

Each YAML keeps the normal strategy schema (`id`, `hero`, `modes`,
`planner{towers, base_success}`, `plan`/`fill`/`panic` with roles
dps/support/exit/far, upgrades as `a-b-c`, `answers`). It adds
`achievement:`, `map:`, a `constraints:` block, and `notes:` for steps the
executor can't express yet.

**Wiring:** `strategy.load_all()` loads this folder (`source: achievements`) and
`readiness()` sets `bot_ready` False, with reasons, for any constraint the
executor cannot enforce. `runner.planner_specs` offers a bot-ready build only
while its achievement is not complete in the scan, and the planner plays it on
a first-time medal or as an ACH replay (see above).

| Achievement | File | Map / mode | Plan |
|---|---|---|---|
| First Monkeys First | ach_first_monkeys_first | any / primary_only, easy | primary_core: Quincy, Tack 4-0-2, Boomerang 4-0-2, Bomb 0-4-2, Dart 0-2-4, Glue 2-0-3; allowed_towers = primary |
| War Monkeys | ach_war_monkeys | any / military_only, medium | military_heli_sniper (Sniper 4-2-0, Heli 4-0-2); Tack panic replaced by Sniper/Heli |
| Abracadabmonkey | ach_abracadabmonkey | any / magic_only, hard | magic_obyn_ninja_wizard (Ninja 4-0-2 / 2-0-4, Wizard 0-2-5, Alch 4-2-0, Sun Avatar) |
| Role Reverser | ach_role_reverser | Logs / reverse | military_heli_sniper |
| Bloons Master | ach_bloons_master | Logs / chimps | chimps_ninja_sun (Ninja/Alch core, 2 Sun Avatars, villages, 2-0-5 Perma-Spike exit) |
| Unsung Monkeys | ach_unsung_monkeys | Logs / easy | Quincy R1; Engineer 1-0-0 -> 3-0-2; exit Spikes 2-0-0 (lead) -> 2-3-0 MOAB SHREDR x2+; Village 0-2-0 Radar for camo; panic = spike exit |
| Chunky Monkeys | ach_chunky_monkeys | Logs / medium, no hero | Buccaneer R1 in river ($500) -> 3-2-0 Destroyer; Mortar 0-0-3 Signal Flare (camo); Spike exit 2-3-0; Heli 4-0-2; Village 2-2-0; Super 3-0-2. Answers only use large towers |
| Big Bloons | ach_big_bloons | any / easy, primary_only, medium | primary_core with hero pat_fusty (no fallback hero) |
| Team Player, Team Captain, Ultimate Team-up | ach_team_player, ach_team_captain, ach_ultimate_team_up | Monkey Teams map / easy-hard | Dynamic: read the 3 allowed icons, then pick a strategy whose every placed kind is in that set. Hero allowed |
| All for one and one for one | ach_all_for_one_and_one_for_one | Logs (or Spa Pits) / hard, no hero | Single Buccaneer mid-river: 0-1-0 R6, 0-1-1 R7, 0-2-1 R10, 0-3-1 R14, 0-3-2 R24, 0-4-2 R30 (MOAB Takedown on MOABs), 0-5-2 R52. fill/panic empty |
| 2TC | ach_2tc | Resort / chimps, no hero | Boomerang in the smallest loop to 3-0-2, Dartling below the exit (Locked target above the entrance) 0-1-0 -> 1-3-0, Boomerang 5-0-2 Glaive Lord, Dartling 1-5-0 M.A.D |
| No Harvest | ach_no_harvest | Cornfield / chimps | Documented only (bot_feasible no): 4 hidden bend spots, Ultra-Juggernaut 5-0-2 + MOAB Glue |
| So Spiiicey Ninja Kiwi | ach_so_spiiicey_ninja_kiwi | Spice Islands / abr | abr_ninja_alch (all land); forbid Sub, Buccaneer, Brickell |
| Living on the Edge | ach_living_on_the_edge | Resort / easy, MK off | 0-0-0 Sniper R1, sold after one shot in R2; leak R2 remainder + R3-5 to reach exactly 1 life; from R6 a no-leak primary_core |
| Snap of your fingers | ach_snap_of_your_fingers | Logs / deflation, MK off | Spend exactly $10,000 (v56.3 set: Sub 4-2-0, Buccaneer 3-2-0, Tack 0-3-0, Dart 1-0-0; re-price for v57). Lose exactly 100 lives (10 camo yellows R33, all camos R36) |
| Nah, I'd Win | ach_nah_id_win | Spa Pits (Tar Pits secret) / hard, MK off | Wiki route: 3 Subs + Dart, Benjamin R13, Snipers (strong), Alchemist brews, Buccaneer 0-3-2, Village 2-0-2, Farm 2-0-3, Glues 1-1-0, Elite Defender R57, Elite Sniper R69, Maim MOAB R74. Clock positions in notes |
| Josh's Constant | ach_joshs_constant | Dark Castle / chimps | chimps_ninja_sun with the exit Spike Factory kept outside village range and bought to 2-0-5 at full price (>= $40,870) |
| 2 MegaPops | ach_2_megapops | Logs / chimps, no hero | Heli carry to 5-0-2 Apache Prime, locked in place inside a 2-3-0 MIB Village and a 4-0-0 Stronger Stimulant Alchemist, exit Glue 0-2-3, one early Dart. Every other tower combined must pop under 42,693 |
| Freaky Friday | ach_freaky_friday | Logs / medium | hard_ninja_alch_sun Medium plan plus two 2-4-0 Transforming Tonic alchemists (t1, t2); the AbilityPlanner fires the Tonic on cooldown; wins_needed 4 |

## Every achievement

Generated from `data/achievements.json` and the 2026-11-06 scan. Category: cumulative
(counts across games), single-game (one game must meet it), meta/menu (a menu action),
passive (normal farming completes it), hidden ("???" in game), or why it is out (co-op,
online, event, paid DLC). Scan: complete, a percentage, unknown, or not read (see above:
almost always complete). Bot solo: whether the bot may and could do it single-player, with
the research's difficulty. Time: rough estimate for what is left on this account.

| Achievement | Requirement | Category | Scan 2026-11-06 | Bot solo? | Time | Method / needs |
|---|---|---|---|---|---|---|
| Impoppable | Pop 100,000,000 Bloons | cumulative, passive | complete | yes (easy) | - | Lifetime pops; accrues from every game. Hard/CHIMPS/freeplay games give the most pops per hour. |
| MOAB Assassin | Destroy 25,000 MOABs | cumulative, passive | not read | yes (easy) | passive | Lifetime MOAB kills; Hard/CHIMPS (R40+) games or freeplay accrue fastest. |
| BFB Brawler | Destroy 10,000 BFBs | cumulative, passive | not read | yes (easy) | passive | Lifetime BFB kills; play Hard (to R80) or longer modes. |
| ZOMGinator | Destroy 5,000 ZOMGs | cumulative, passive | not read | yes (easy) | passive | Lifetime ZOMG kills; ZOMGs appear from R78/R85+, so Hard/Impoppable/CHIMPS or freeplay. |
| Me Did A Job on DDT | Destroy 5,000 DDTs | cumulative, passive | not read | yes (medium) | passive | Lifetime DDT kills; DDTs from R90 (CHIMPS/Impoppable/Apopalypse) or freeplay; needs camo + lead-capable MOAB damage. |
| Sapper | Pop 5,000,000 Fortified Bloons or MOAB-Class. Avoid insta-kills and Fort stripping for best results. (Counts popped Fortified layers (incl. fortified MOAB-class and their fortified children); stripped/skipped layers do not count.) | cumulative, passive | 29% | yes (hard) | ~3.5M fortified layers left: hundreds of R100 games, or several hours of Easy freeplay | Passive. Fortified bloons come in R80+ (Hard/Impoppable/CHIMPS/ABR) and freeplay. Single-target, non-insta damage counts every layer: Elite Defender / Cripple MOAB snipers, Perma-Spike, Ninja shurikens, Sun Avatar. Avoid BMA/XXXL Trap/Navarch insta-kills and Shattering Shells / First Strike. The bot's Hard-family and CHIMPS games already feed it. |
| First Win | 1 Non-Tutorial Beginner map Win | cumulative (progression), passive | complete | yes (easy) | - | Win any non-tutorial Beginner map. |
| Grasshopper | Win on 9 different Beginner maps | cumulative (progression), passive | complete | yes (easy) | - | Win on 9 different Beginner maps (any difficulty). Medal rotation covers it. |
| Next Level | Win 1 game on an Intermediate map | cumulative (progression), passive | complete | yes (easy) | - | Win 1 game on an Intermediate map. |
| Acolyte | Win games on 5 different Intermediate maps | cumulative (progression), passive | complete | yes (easy) | - | Win on 5 different Intermediate maps. |
| Advanced Player | Win 1 game on an Advanced map | cumulative (progression), passive | complete | yes (easy) | - | Win 1 game on an Advanced map (e.g. Cornfield or Peninsula on Easy). |
| Big Monkey | Deploy a tier 4 monkey tower | single-game, passive | complete | yes (easy) | - | Buy any tier-4 upgrade. |
| Mega Monkey | Deploy a tier 5 monkey tower | single-game, passive | complete | yes (easy) | - | Buy any tier-5 upgrade. |
| Hero Time | Deploy a Hero on a non-tutorial map | single-game, passive | complete | yes (easy) | - | Place a hero on a non-tutorial map. |
| Hero Powers Activate | Use any Hero Level 3 Ability | single-game, passive | complete | yes (easy) | - | Activate any hero level-3 ability. |
| Bigger, Badder | Use any Hero Level 10 Ability | single-game, passive | complete | yes (easy) | - | Activate any hero level-10 ability. |
| Epic Hero | Level any Hero to Level 20 | single-game, passive | complete | yes (easy) | - | Get a hero to level 20 in one game: place the hero R1-3 in a Hard (R80) or longer game. |
| Monkey Avenger League | Win a game for 4 different Heroes | cumulative | complete | yes (easy) | - | Win a game with each of 4 different heroes (Quincy, Gwendolin, Striker Jones, Obyn...). Rotate the selected hero on easy wins. |
| You've Got the Power | Use Powers for the first time | cumulative | not read | yes (medium) | 1 power use | Done with Power User |
| Power User | Use Powers 25 times | cumulative | 32% | yes (medium) | 17 power uses, ~10 min once coded | Needs power use code (see plan); buy cheap Powers with MM |
| Empowered | Use Powers 100 times | cumulative | 8% | yes (medium) | 92 power uses; 1-3 per game | Same code as Power User; 1-3 cheap powers per non-CHIMPS game |
| Student | Apply your first Monkey Knowledge point | meta/menu | complete | yes (easy) | - | Apply 1 Monkey Knowledge point in the Monkey Knowledge menu. |
| Scholar | Apply 10 Monkey Knowledge points | meta/menu | complete | yes (easy) | - | Apply 10 MK points. |
| Dr. Monkey | Spend 106 Monkey Knowledge points | cumulative (progression) | complete | yes (medium) | - | Spend 106 MK points total; points come from player levels, apply them as earned. |
| First Monkeys First | Win 10 games using only Primary monkeys (Only Primary towers placed; heroes/powers allowed.) | single-game, passive | complete | yes (easy) | - | 10 wins placing only Primary towers (Dart, Boomerang, Bomb, Tack, Ice, Glue, Desperado). Heroes and Powers allowed (since v5.0); Primary Only mode not required but enforces it. Bot's primary_only farming already counts. Build: `ach_first_monkeys_first`. |
| War Monkeys | Win 10 games using only Military monkeys (Only Military towers placed; heroes/powers allowed.) | single-game, passive | complete | yes (easy) | - | 10 wins placing only Military towers (Sniper, Sub, Buccaneer, Ace, Heli, Mortar, Dartling). Military Only (Medium) enforces it. Build: `ach_war_monkeys`. |
| Abracadabmonkey | Win 10 games using only Magic monkeys (Only Magic towers placed; heroes/powers allowed.) | single-game, passive | complete | yes (easy) | - | 10 wins placing only Magic towers (Wizard, Super, Ninja, Alchemist, Druid, Mermonkey). Magic Monkeys Only (Hard) enforces it. Build: `ach_abracadabmonkey`. |
| Unsung Monkeys | Win 10 games using only Support monkeys (Only Support towers placed; heroes/powers allowed (v5.0).) | single-game | 30% | yes (medium) | 7 Easy wins, ~45 min | `ach_unsung_monkeys` (Logs Easy replay) - now scheduled |
| Inflated | Beat round 100 in Deflation mode | single-game | complete | yes (hard) | - | Deflation on Logs/Resort, then continue into freeplay and clear R100 with no income. Wiki setup: Gwendolin, 4-2-0 Aircraft Carrier (pond), 3-2-0/4-2-0 Berserker Brew Alchemist, 2-2-0 Village; 0-0-2 village discount sold after setup. Needs camo + super-ceramic handling. |
| Survivor | Beat round 100 in Apopalypse mode | single-game, passive | complete | yes (medium) | - | Win Apopalypse (Medium, rounds 1-100 continuous). Existing strategy apopalypse_ninja_sniper. |
| Indie | Win 25 games with Alternate Bloon Rounds | cumulative, passive | complete | yes (medium) | - | 25 wins in Alternate Bloons Rounds (Hard). Accrues from ABR medal runs across maps. |
| Poppable | Win 25 games on Impoppable Difficulty | cumulative, passive | complete | yes (hard) | - | 25 Impoppable wins (one life, R6-100). |
| Thrifty | Win 10 games in Half Cash mode | cumulative, passive | complete | yes (medium) | - | 10 Half Cash wins (Hard). |
| Bloonzilla! | Win 25 games against Double HP MOABs | cumulative, passive | complete | yes (medium) | - | 25 Double HP MOABs wins (Hard). |
| Role Reverser | Win a game in Reverse mode | single-game, passive | complete | yes (easy) | - | Win once in Reverse mode (Medium). Military heli/sniper plan supports reverse. Build: `ach_role_reverser`. |
| Medal Winner | Get all medals for a map | cumulative (progression), passive | not read | yes (hard) | passive | All medals on one map (every difficulty + every mode incl. CHIMPS). Pick the easiest Beginner map (Logs/Cubism/Resort) and finish its CHIMPS last. |
| Decorated Hero | Get 36 difficulty medals on Beginner maps | cumulative (progression), passive | not read | yes (easy) | passive | 36 difficulty medals on Beginner maps; medal rotation across Beginner maps covers it. |
| Red and Blue Makes... | Pop 100,000 Purple Bloons | cumulative, passive | not read | yes (easy) | passive | Pop 100k Purple bloons; accrues in Hard/CHIMPS games (purples from R50s+). Use non-magic/fire damage that can pop purples (e.g. Ninja, Bomb, Sniper). |
| Infrared | Pop 250,000 Camo Bloons | cumulative, passive | not read | yes (easy) | passive | Pop 250k Camo bloons; any game with camo detection. |
| Our Powers Combined | Collect at least 12 different Powers | meta/menu | not read | yes (easy) | ? | Own (buy or earn) 12 different Powers; buy cheap ones in the Powers shop with Monkey Money. |
| Challenger | Win 1 Daily Challenge | online (daily challenge) | not read | no | - | Daily Challenges. |
| Challenge Apprentice | Win 10 Daily Challenges | online (daily challenge) | 90% | no | - | Daily Challenges. |
| Challenge Master | Win 100 Daily Challenges | online (daily challenge) | not read | no | - | Daily Challenges. |
| Perfect Week | Complete all Daily Challenges in a week | online (daily challenge) | 100% | no | - | Daily Challenges. |
| Knowledgeable Primate | Unlock all Monkey Knowledge in one branch | cumulative (progression) | complete | yes (medium) | - | Unlock every MK in one branch (apply points into a single tree). |
| Bloons Master | Beat 1 map in CHIMPS mode | single-game, passive | complete | yes (hard) | - | Win 1 CHIMPS game (no continues, no income, no selling, no MK, no powers). Easiest Beginner map (Logs). Existing chimps_ninja_sun. Build: `ach_bloons_master`. |
| Superior Bloons Master | Beat 5 maps in CHIMPS mode | cumulative, passive | complete | yes (hard) | - | CHIMPS wins on 5 different maps. |
| Ultimate Bloons Master | Beat 15 maps in CHIMPS mode | cumulative, passive | not read | yes (hard) | passive | CHIMPS wins on 15 different maps. |
| Super BAD | Destroy 1,000 BADs | cumulative, passive | complete | yes (hard) | - | Lifetime BAD kills; one BAD per R100 game (R98+) or many in freeplay R100+. |
| Co-operation | Beat 1 map in Co-op mode | co-op | complete | no | - | Co-op only. |
| Four times the fun | Beat 1 map in 4-player Co-op mode | co-op | complete | no | - | Co-op only. |
| Triple threat | Beat 1 map in 3-player Co-op mode | co-op | complete | no | - | Co-op only. |
| Collaborate! | Have 4 Heroes on screen at once | co-op | complete | no | - | Co-op only. |
| When the going gets tough... | Win 10 games on Hard difficulty in Co-op mode | co-op | not read | no | - | Co-op only. |
| Kind Benefactor | Give 10,000 Cash in Co-op mode | co-op | complete | no | - | Co-op only. |
| Generous Benefactor | Give 50,000 Cash in Co-op mode | co-op | not read | no | - | Co-op only. |
| Monkey Contributor | Give 100,000 Cash in Co-op mode | co-op | complete | no | - | Co-op only. |
| Monkey Philanthropist | Give 1,000,000 Cash in Co-op mode | co-op | complete | no | - | Co-op only. |
| Powershare | Use 10 Powers in Co-op mode | co-op | 10% | no | - | Co-op only. |
| Power overwhelming! | Use 100 Powers in Co-op mode | co-op | not read | no | - | Co-op only. |
| Insta-defense | Use 5 Insta Monkeys in Co-op mode | co-op | 0% | no | - | Co-op only. |
| Co-op Popper | Pop 10,000,000 Bloons in Co-op mode | co-op | 96% | no | - | Co-op only. |
| Snap of your fingers | Finish a game with exactly half your starting lives and half your starting cash (End: lives == start/2 and cash == start/2.) | single-game | 0% | yes (hard) | one Deflation game | `ach_snap_of_your_fingers` - SAFETY: deliberate leaks; owner exception needed |
| Bloontona 500 | Gain entry to 500 races | online (race) | not read | no | - | Race events. |
| Rookie of the year | Complete a race in under 10 minutes | online (race) | 0% | no | - | Race events. |
| Rising star | Complete a race in under 5 minutes | online (race) | 0% | no | - | Race events. |
| Top of your game | Complete any race in under 3 minutes | online (race) | 0% | no | - | Race events. |
| The greatest challenge | Create or Play 200 challenges | online (daily challenge) | 7% | no | - | Create or play 200 challenges (daily, advanced, browser). |
| Lookin fab | Win 100 games using a skin of any Hero | cumulative, passive | unknown | yes (medium) | passive once a skin is equipped (100 wins) | Equip any owned hero skin; the bot's wins then count |
| Therpopylae | Pop 200,000 Bloons on Peninsula | cumulative | not read | yes (medium) | ? | Pop 200k bloons on Peninsula (Advanced map). ~2 Hard games or ~4-5 Medium games there; queue Peninsula for its medals. |
| Bloon Master Populous | Deal 1 billion damage with the Bloon Master Alchemist | cumulative | 0% | yes (hard) | hours of R200+ freeplay | Needs freeplay support - skip for now |
| I see you | Reveal 10,000 Bloons using Shimmer | cumulative, passive | complete | yes (easy) | - | Reveal 10k camo bloons with Shimmer (Wizard 0-0-3+). Accrues from any 0-x-3+ Wizard in camo rounds. |
| Tetrimino | Place 50 monkey towers on a map at once | single-game | complete | yes (medium) | - | 50 towers on the map at once: Easy on a big open map (End of the Road/Logs), late game place ~50 cheap 0-0-0 Darts (~$200 each). |
| All for one and one for one | Win a game with only 1 monkey tower on screen at any one time in any Hard Difficulty game (Hard difficulty; max one tower on screen at once.) | single-game | complete | yes (medium) | - | Hard, only 1 tower on screen at any time (selling+replacing allowed). Wiki: single Buccaneer on Logs or Spa Pits mid-track: 0-1-0 R6, 0-1-1 R7, 0-2-1 R10, 0-3-1 R14, 0-3-2 by R24-36, 0-4-2 Monkey Pirates R30 (use MOAB Takedown on MOABs), 0-5-2 Pirate Lord R52 then AFK. No hero placed. Build: `ach_all_for_one_and_one_for_one`. |
| Master of life | Have 1000 lives at once in a single game | single-game | complete | yes (medium) | - | Reach 1000 lives in one game (not Impoppable/CHIMPS). Easy on Logs/Resort: Druid 0-4-0 Jungle's Bounty -> 0-5-0 Spirit of the Forest, Heli 0-4-0 Support Chinook ability (lives drops), Sub 5-x-x Energizer; Benjamin lvl14+ and Healthy Bananas MK + farms help. Run into freeplay. |
| Rainbow is Magic | Pop 20,000 Rainbow Bloons with Magic Monkeys | cumulative, passive | complete | yes (easy) | - | Pop 20k Rainbow bloons with Magic towers (Wizard/Super/Ninja/Alchemist/Druid/Mermonkey). Magic Monkeys Only (Hard) has ~1,191 rainbows per game, so ~17 magic_only wins. |
| What did it cost? - Everything | Sacrifice every tower type in the game to the Temple | single-game | complete | yes (hard) | - | When upgrading a Super Monkey to Sun Temple (4-x-x), have one of every tower type in its range (incl. water towers, so a map with water in range: Logs). Easy freeplay with farming; requires all towers unlocked. |
| 2 MegaPops | Complete a game of CHIMPS with more than 2 million damage dealt by one tower | single-game | 0% | yes (hard) | one CHIMPS game | `ach_2_megapops` not bot-ready (needs per-tower damage readout) |
| A Crate Time | Open a Diamond Crate in any Collection Event | event (collection) | not read | no | - | Open a Diamond Crate in a Collection Event. |
| Axis of Havoc | Have one of each T5 sniper in one game of CHIMPS | single-game | 0% | yes (hard) | one ~35 min CHIMPS game | Needs a sniper-carry CHIMPS build that affords 5-x-x, x-5-x and x-x-5 (~$95k at Hard prices) - not written (see plan) |
| Tower Keeper | Have 200 insta monkeys in your inventory at one time | cumulative, passive | complete | yes (easy) | - | Hold 200 Insta Monkeys at once; instas come from achievements, daily chests, quests and events. Do not spend instas. |
| A year in the making | Open the Daily Chest 365 times | cumulative | not read | yes (easy) | ? | Open the Daily Chest (daily reward) 365 times; claim it once per day from the main menu. |
| Kali Maaaaaaaa | Gain 10 levels for Adora in one round | single-game | not read | yes (medium) | ? | Adora gains 10 levels in one round by Blood Sacrifice (lvl 7) of an expensive tower (Flying Fortress, Super Mines, Dartling T5). Place Adora late, level her to 7, then sacrifice. Needs Adora. |
| Adventurer | Complete an Odyssey | event (odyssey) | not read | no | - | Odysseys. |
| Seasoned Adventurer | Complete a Hard Odyssey | event (odyssey) | complete | no | - | Odysseys. |
| No Stone Left Unturned | Complete all 3 difficulties of a single Odyssey | event (odyssey) | 0% | no | - | Odysseys. |
| 12 Tasks of Monk-ules | Complete 12 different Odysseys | event (odyssey) | not read | no | - | Odysseys. |
| Modysseus Rises | Complete 50 Odysseys | event (odyssey) | not read | no | - | Odysseys. |
| Modysseus Forever | Complete 100 Odysseys | event (odyssey) | not read | no | - | Odysseys. |
| Full Speed Ahead! | Complete an Odyssey in under 1 hour | event (odyssey) | 0% | no | - | Odysseys. |
| All About That Bling | Purchase a Trophy Store item | meta/menu | complete | yes (medium) | - | Buy any item in the Trophy Store (needs Trophies, earned from events). |
| Oathbreakers | Reanimate 250,000 Bloons to fight on your side using the Necromancer Wizard | cumulative, passive | complete | yes (easy) | - | Reanimate 250k bloons with Necromancer Wizard (0-0-4) or Prince of Darkness (0-0-5). The magic strategy's 0-2-4/0-2-5 Wizard accrues it. |
| Living on the Edge | Win any non-CHIMPS/Impoppable game with only 1 life remaining (Exactly 1 life at victory; Mana Shield/MK lives must be off.) | single-game | not read | yes (hard) | one Easy game | `ach_living_on_the_edge` - SAFETY: deliberate leaks; owner exception needed |
| Freaky Friday | Use the Alchemist's Transforming Tonic abilities 100 times | cumulative | 52% | yes (medium) | 2 Medium games (~20 min) | NEW build `ach_freaky_friday` (Logs Medium replay): two 2-4-0 alchemists, the AbilityPlanner fires Transforming Tonic on cooldown. |
| Monkey Fan Club | Create or Login to your Ninja Kiwi account to cloud save your progress | meta/menu | complete | no (rule/infeasible) | - | Create/log into a Ninja Kiwi account for cloud save. Account login is a manual user action (likely already done). |
| Ready Player One? | Host and win 10 Co-op games | co-op | 20% | no | - | Co-op only. |
| Crash of the Titans | Strip the fortifications from Fortified DDTs 3000 times | cumulative | 12% | yes (hard) | long (fortified DDTs: R90+ / freeplay) | Mortar 0-0-4 Shattering Shells in late CHIMPS/ABR/freeplay; account's mortar bottom path reads 0 (locked?) |
| A La Code | Submit a Challenge to the Content Browser | online (social/content browser) | 0% | no | - | Publish a challenge to the Content Browser (public content). |
| Regifted | Pop 1,000,000 Bloons with Dartling Gunners | cumulative | complete | yes (medium) | - | Pop 1M bloons with Dartling Gunners. Use Dartling Gunners (e.g. 4-2-0 Plasma Accelerator, 2-4-0 Rocket Storm) as main DPS in Hard/freeplay games with Locked targeting (they otherwise follow the cursor); needs Dartling unlocked. |
| Coupon Crazy | Spend at least 50 Trophies in the Trophy Store | meta/menu | complete | yes (medium) | - | Spend 50 Trophies in the Trophy Store. |
| Instant Gratification | Use a Tier 5 Insta Monkey. NOTE: even after being used, Instas still count toward your collection! | meta/menu | 0% | yes (medium) | 1 min, once | Place any tier-5 Insta from the in-game Insta panel (owner by hand) |
| Insta Century | Use 100 Insta Monkeys. NOTE: even after being used, Instas still count toward your collection! | cumulative | 0% | yes (medium) | 100 insta placements | Place 1-3 spare Instas per game; needs insta-panel code or owner by hand |
| Limited Run | Purchase at least 1 new Limited Time item in the Trophy Store | meta/menu | 0% | yes (medium) | ? | Buy a new Limited Time item in the Trophy Store. |
| Tools to Darwin | Upgrade towers 20,000 times | cumulative, passive | complete | yes (easy) | - | Buy 20,000 in-game upgrades in total; accrues every game (~20-40 upgrades/game). |
| Achievement of Achievements | Collect 35 achievements | cumulative (progression), passive | not read | yes (easy) | passive | Hold 35 other achievements. |
| Hook, Line, and Sinker | Rope in 3,000 MOAB-Class Bloons using the MOAB Takedown ability | cumulative | 2% | yes (medium) | ~2,900 hooks: very long | Pirate Lord (0-5-0) MOAB Takedown on every MOAB round; AbilityPlanner already fires it on MOAB rounds - add a 0-4-0/0-5-0 buccaneer to water builds |
| Moving House | Redeploy 1,000 monkey towers using the Support Chinook | cumulative | 0% | yes (hard) | 1000 redeploys: many hours | Support Chinook redeploy needs click-targeting - skip |
| Social Butterfly | Use emotes 100 times in co-op games | co-op | complete | no | - | Co-op only. |
| So Shiny! | Pop 20 Golden Bloons | cumulative, passive | not read | yes (medium) | passive | Pop 20 Golden Bloons. Golden Bloon event runs Fri 08:00 UTC to Mon 08:00 UTC (alternates weekly with Monkey Teams); appears once per 10-round block from R21 (not in Deflation/CHIMPS/Sandbox). It jumps along the track and gains camo/lead/purple/zebra/fortified, so needs wide coverage + camo + lead. |
| Glittering Gold | Pop 100 Golden Bloons | cumulative, passive | 48% | yes (medium) | weekends only | Passive on Golden Bloon weekends (R21+, not CHIMPS/Deflation) |
| Glorious Gold | Pop 500 Golden Bloons | cumulative, passive | 9% | yes (medium) | weekends only, long | Passive on Golden Bloon weekends |
| Magical Gold | Pop 50 Golden Bloons in Magic Monkeys only mode | cumulative, passive | 8% | yes (medium) | weekends only | Magic Monkeys Only games on Golden Bloon weekends (needs weekend gating) |
| Team Player | Win 25 times with Monkey Teams (Only hero + the 3 Monkey Teams towers placed on the Monkey Teams map.) | single-game | not read | yes (medium) | ? | 25 wins with Monkey Teams: Mon 08:00-Fri 08:00 UTC one map per difficulty shows a team icon with 3 allowed towers (rotates every 3 h); win placing only the hero + those 3 towers. Bot must read the 3 icons and pick a strategy whose towers fit. Build: `ach_team_player`. |
| Team Captain | Win 50 times with Monkey Teams | single-game | not read | yes (medium) | ? | 50 Monkey Teams wins (see Team Player). Build: `ach_team_captain`. |
| Ultimate Team-up | Win 100 times with Monkey Teams | single-game | 3% | yes (medium) | ~100 Monkey Teams wins | Needs the Monkey Teams screen reader (`ach_team_*` not bot-ready) |
| What is this new Bloonery? | Defeat a Tier 1 Boss | event (boss) | complete | no | - | Boss Bloon events / Boss challenges. |
| Who's the Boss? | Defeat a Tier 5 Boss | event (boss) | not read | no | - | Boss Bloon events / Boss challenges. |
| I'm the Boss | Defeat a Tier 5 Elite Boss | event (boss) | not read | no | - | Boss Bloon events / Boss challenges. |
| Apotheosis | Upgrade to a Monkey Paragon Tower | single-game | not read | yes (medium) | ? | Upgrade any tower to its Paragon (all three T5s of that tower on the map + Paragon unlocked via tower XP). Cheapest: Dart Apex Plasma Master on Easy. |
| Like a Boss | Pop 50 Boss Bloons | event (boss) | not read | no | - | Boss Bloon events / Boss challenges. |
| Davids vs Goliath | Win a boss battle without using a Hero | event (boss) | 0% | no | - | Boss Bloon events / Boss challenges. |
| So Spiiicey Ninja Kiwi | Beat Spice Islands on Alternate Bloon Rounds with only land towers | single-game | not read | yes (hard) | ? | Win Spice Islands (Intermediate) on ABR using only land towers (no Sub/Buccaneer/Brickell; amphibious towers OK on land). Ninja/Alchemist/Village land core. Build: `ach_so_spiiicey_ninja_kiwi`. |
| No Harvest | Beat Cornfield on CHIMPS without removing any corn | single-game | 0% | no (rule/infeasible) | one CHIMPS game | Hand-placed only (`ach_no_harvest` not bot-ready) |
| Student Loans | 4 x 10^5 (Go into $400,000 of debt) | single-game | not read | yes (medium) | ? | Be $400,000 in debt: Banana Farm 0-4-0 IMF Loan ability spam (first loan $10k debt, each next +$6k with Backroom Deals); many IMF Loans on End of the Road; Geraldo rejuv potions optional. |
| Sticky Situation | Glue 500,000 Bloons | cumulative, passive | not read | yes (easy) | passive | Glue 500k bloons. Any strategy with Glue Gunners (primary_core uses 1-0-2/2-0-3 glues; 0-2-3/0-2-4 glue hose/strike glue many). |
| Big Spender | Spend 1,000,000 cash in one round | single-game | not read | yes (medium) | ? | Spend $1,000,000 in a single round: in late Easy freeplay with big income, buy a Paragon with max cash injection (also gives Apotheosis/Heavy Investment) plus upgrades in the same round. |
| The Daily Reid | Win 365 unique daily challenges | online (daily challenge) | 0% | no | - | Daily Challenges. |
| I'll Be Back | Spend 1,000 MM on Continues or Checkpoints | cumulative | not read | no (rule/infeasible) | ? | Spend 1,000 MM on continues or checkpoints. Violates the project rule 'no losses, no MM continues'. |
| Conquested Territory | Capture 5 Tiles off other players | online (contested territory) | not read | no | - | Contested Territory. |
| Stage of Empires | Capture 50 Tiles | online (contested territory) | not read | no | - | Contested Territory. |
| Territory Sampler | Capture 1 of each: Boss, Time Attack, Least Tiers and Least Cash Tiles | online (contested territory) | 0% | no | - | Contested Territory. |
| Side Quest | Complete a Quest | meta/menu | not read | yes (medium) | ? | Complete any Quest from the Quests menu. |
| Invigoration | Have 75 buffs active on your Monkeys at once | single-game | not read | yes (medium) | ? | 75 buffs active on your towers at once: many towers clustered under 2-3 Villages (Jungle Drums, MIB, Call to Arms), Alchemist brews, hero aura; may unlock in big late-game builds. |
| World League Training | Have 150,000 Beast Handler XP at once | cumulative (progression) | not read | yes (medium) | ? | Have 150,000 Beast Handler tower XP at once; use Beast Handler in farming games (expert maps x1.3 XP). |
| Life Experience | Earn 5,368,709 experience for any tower | cumulative (progression), passive | not read | yes (easy) | passive | Have 5,368,709 tower XP on one tower at once (XP beyond its unlocks, incl. Paragon). Keep farming one fully-unlocked tower. |
| Heavy Investment | Invest at least $401,626 extra when creating any Paragon | single-game | 26% | yes (medium) | 1 late Easy game (~30 min) once coded | Paragon purchase with the cash slider at >= $401,626 extra; needs paragon + slider code |
| 25 to Life | Defeat 5 unique Bosses at Tier 5 (Boss Event or Challenge Mode) | event (boss) | 0% | no | - | Boss Bloon events / Boss challenges. |
| Community Connoisseur | Win 100 different community submissions in the Content Browser. (Challenges, Odysseys, Maps) | online (social/content browser) | 0% | no | - | Win 100 different community submissions from the Content Browser. |
| First Steps | Complete the First Time Tutorial quest. | meta/menu | 0% | yes (easy) | ~5 min, once | Quests menu -> First Time Tutorial! (owner by hand, or a small menu routine) |
| Season Starts | Achieve Tier 1 in any Stage in a Social Season | online (social/content browser) | unknown | no | - | Social Season stages/stars. |
| Mid Season | Earn 7,500 Stars in any Social Season | online (social/content browser) | 0% | no | - | Social Season stages/stars. |
| Season Champion | Earn a perfect 15,000 Stars in any Social Season | online (social/content browser) | not read | no | - | Social Season stages/stars. |
| Full Strength Posse | Have a full Posse of 6 Monkeys in Frontier Legends | paid DLC (Legends) | not read | no | - | Legends DLC (Rogue/Frontier Legends) only; not counted or shown without the DLC. |
| Gon' Fishin' | Catch 30 Fish in Frontier Legends | paid DLC (Legends) | not read | no | - | Legends DLC (Rogue/Frontier Legends) only; not counted or shown without the DLC. |
| New Stuff, Same ol' Bloons | Win a game using a Sheriff weapon other than the default pistol in Frontier Legends | paid DLC (Legends) | not read | no | - | Legends DLC (Rogue/Frontier Legends) only; not counted or shown without the DLC. |
| Double Trouble | Win any number of Stages with at least 2 different heroes in Rogue Legends | paid DLC (Legends) | not read | no | - | Legends DLC (Rogue/Frontier Legends) only; not counted or shown without the DLC. |
| Marshmallow Maxing | Max out at least 1 buff in the Marshmallow XP Shop in Rogue Legends | paid DLC (Legends) | not read | no | - | Legends DLC (Rogue/Frontier Legends) only; not counted or shown without the DLC. |
| Power Creep | Obtain a total of 250 Artifacts that you use throughout your runs in Rogue Legends | paid DLC (Legends) | not read | no | - | Legends DLC (Rogue/Frontier Legends) only; not counted or shown without the DLC. |
| Big Bloons | Pat likes hugging Big Bloons even more (Complete 10 games with Pat Fusty.) | single-game, hidden | complete | yes (easy) | - | Win 10 games with Pat Fusty as hero (any mode). Needs Pat unlocked (Monkey Money). Run the normal Easy/primary plan with hero pat_fusty. Build: `ach_big_bloons`. |
| Alchermistman and Bloonacleboy | You have it set to M for mini, when it should be W for wumbo (Bloon Master Alchemist damage counter >= 900,000 before R100.) | single-game, hidden | not read | yes (medium) | ? | One Bloon Master Alchemist (Alchemist 0-0-5) deals 900,000 damage before round 100. Easy (freeplay counts) on Logs: farm, build BMA, sell other DPS when affordable, buff with Ultraboost + Homeland Defense; Perma-Spike for DDTs/BAD. |
| 2TC | Complete a game in CHIMPS Difficulty with only 2 monkey towers (Only 2 towers purchased in a CHIMPS win; sacrificed/removed towers still count.) | single-game, hidden | not read | yes (hard) | ? | CHIMPS with only 2 towers ever purchased. Wiki: Resort, Boomerang inside smallest loop 3-0-2 -> 5-0-2 Glaive Lord; Dartling below the track exit, locked target just above the track entrance, 0-1-0 -> 1-3-0 -> 1-5-0 M.A.D. No hero. Build: `ach_2tc`. |
| Bill Greates | Send $500,000 to an ally in co-op in one go | co-op, hidden | not read | no | - | Co-op only. |
| Strangely Adorable | When the planets align ever so nicely (Turn True Adora into Vengeful Adora by making a VTSG.) | single-game, hidden | complete | yes (hard) | - | Create a Vengeful True Sun God while a level-20 True Adora is in range (VTSG: MK 'There Can Be Only One' on, Anti-Bloon + Legend of the Night placed outside temple range, >$50k sacrifices in each of 4 categories for Temple and TSG). Very expensive late freeplay. |
| Josh's Constant | B-B-Beat any Expert map on CHIMPS with $40,870 or more spent on 1 Spike Factory | single-game, hidden | not read | yes (hard) | ? | Win CHIMPS on an Expert map (Dark Castle) with >= $40,870 spent on one Spike Factory: 2-0-5 or 0-2-5 Perma-Spike bought undiscounted (keep it out of village range). Build: `ach_joshs_constant`. |
| Golden Ticket | Bloompa-loompa-doompa-dee-doo! | meta/menu, hidden | not read | yes (medium) | ? | Candy Falls Easter egg: click the hidden Oompa-Loompa spots in order: 1 top-right corner, 2 house door, 3 chocolate waterfall, 4 top-left corner, 5 right side of chocolate river between middle and lower lanes, 6 bottom-right corner, 7 watermill, 8 bottom-left corner. A wrong spot or a few seconds' pause resets. Needs one-time coordinate calibration. |
| Mo Heroes, Mo Problems | Complete an Odyssey without a Hero | event (odyssey), hidden | not read | no | - | Odysseys. |
| Chunky Monkeys | I like 'em big, I like 'em chunkay (Win 10 games, Medium+, only Pat Fusty, Churchill, Buccaneer, Ace, Heli, Mortar, Super, Mermonkey, Farm, Village, Spike Factory.) | single-game, hidden | complete | yes (medium) | - | 10 wins on Medium or harder using only large-footprint towers: Buccaneer, Ace, Heli, Mortar, Super, Mermonkey, Banana Farm, Village, Spike Factory (heroes: only Pat Fusty/Churchill, or none). Medium on Logs: Buccaneer opener in the river, Mortar 0-0-3 Signal Flare (camo), Spike exit 2-3-0, Heli to 4-0-2, Super 3-0-2. Build: `ach_chunky_monkeys`. |
| Stubborn Strategy | Just because a thing can be done, does not mean that it should be done (100 wins on maps with removables, none removed.) | cumulative, passive, hidden | complete | yes (easy) | - | Win 100 games on maps that have removables without removing any. The bot never buys removables, so wins on such maps accrue it. |
| Perfect Paragon | Paragon of Paragons | single-game, hidden | not read | yes (hard) | ? | Create a degree-100 Paragon. Single player needs Geraldo's Paragon Power Totems: e.g. all dart T5s + 25 0-2-2 darts with ~16.2M pops, 19 totems, $400k+ injection, Easy on Logs/Cubism. |
| Not Lacking Critical Information | Get 25,000 Critical hits (Desperado crits do not count.) | cumulative, passive, hidden | not read | yes (easy) | passive | 25,000 critical hits from Sharp Shooter (Dart 0-x-4), Crossbow Master, Robo Monkey (Super 2-3-0), Tech Terror, Anti-Bloon. Fastest: several 2-3-0 Robo Monkeys with Jungle Drums. Primary strategies with Dart 0-2-4 accrue it passively. |
| Nah, I'd Win | Basically NAPSFRILLS'd it (Spa Pits, Tar Pits variant activated, Hard, MK off, no powers/continues.) | single-game, hidden | not read | yes (hard) | ? | Spa Pits on Hard after activating the Tar Pits secret (click rocks before R1), with MK disabled, no Powers, no continues (instas, farms, selling, lives lost OK). Wiki route uses Benjamin + Subs, Snipers, Alchemists, Buccaneer, Village by clock positions. Build: `ach_nah_id_win`. |
| They call me Cave Monkey! | Rhymes with Grug | cumulative, hidden | not read | yes (medium) | ? | Hit the Cave Monkey spot on Frozen Over with Mortar shells 50,000 times (across games; still counts after it escapes). Many 0-0-0 Mortars targeted at that spot, later Artillery Battery (0-4-0) + abilities; Striker Jones helps. Needs one calibrated target click per mortar. |
