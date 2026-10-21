# BTD6 achievements: what the bot can get

Data: `data/achievements.json` (162 entries). Plans for restricted-win achievements:
`strategies/achievements/ach_*.yaml` (20 files).
Sources: the Steam achievement list for app 960090 (names, descriptions, hidden
flags, global unlock %), bloonswiki "Achievements (BTD6)" and the individual
achievement pages, which give the exact rules and wiki strategies. Researched
2026-10-21, game v57.

Names and descriptions follow the in-game text (bloonswiki). Where Steam
spells a name differently, the entry has a `steam_name` field (5 cases, e.g.
"Me Did A Job On DDT", "Master of Life"). The JSON also has fields the task
did not ask for: `requirement` (the exact rule where the text is vague or
hidden), `reward`, `strategy` (YAML id), `steam_api_id`, `steam_unlock_pct`
and `dlc`.

## Counts

| | count |
|---|---|
| Total | 162 (156 base game, which is also the Steam list, plus 6 Legends DLC) |
| single_player | 107 |
| excluded | 55: co-op 16, odyssey 8, daily_challenge 6, boss 6, purchase (Legends DLC) 6, social/other_players 5, race 4, contested_territory 3, events/collection 1 |
| hidden (in-game "???") | 14 |

Single-player entries by kind: cumulative 43, game_stat 21,
game_win_constraint 20, progression 12, misc_ui 11.
By bot feasibility: easy 39, medium 43, hard 22, no 3. The 3 rated "no" are
No Harvest, Monkey Fan Club and I'll Be Back. 49 are `passive: true`, meaning
normal farming completes them.

Left out of the list on purpose: "Pennies from Heaven" (Legends, not
implemented), "Extreme Player" and "Heroic Stand" (text only, never
implemented).

### Verified rules the descriptions don't spell out
- **Tower-category wins** (First Monkeys First, War Monkeys, Abracadabmonkey, Unsung Monkeys): count *placed towers only*; heroes and Powers are allowed (since v5.0). The Primary/Military/Magic Only modes are not required, but they enforce the rule.
- **Sapper**: 5M *Fortified layers popped individually*. Insta-kills, fort-stripping (Shattering Shells) and layer-skipping (First Strike) don't count. Long Easy freeplay is fastest.
- **Chunky Monkeys** (hidden): 10 wins on Medium or harder using only Pat Fusty, Churchill, Buccaneer, Ace, Heli, Mortar, Super, Mermonkey, Farm, Village or Spike Factory.
- **Big Bloons** (hidden): 10 games with Pat Fusty. **Golden Ticket** (hidden): the Candy Falls Oompa-Loompa click sequence. **Stubborn Strategy** (hidden): 100 wins on maps with removables without removing any. **Alchermistman and Bloonacleboy** (hidden): a Bloon Master Alchemist reaches 900k damage before R100. **Not Lacking Critical Information** (hidden): 25k crits from Sharp Shooter, Crossbow Master, Robo Monkey, Tech Terror or Anti-Bloon.
- **All for one and one for one**: Hard, at most 1 tower on screen at a time (selling and replacing is OK).
- **2TC**: only 2 towers *ever bought* in a CHIMPS win.
- **Monkey Teams** (Team Player, Team Captain, Ultimate Team-up): single player. Runs Mon 08:00 to Fri 08:00 UTC, one map per difficulty, and the 3 allowed towers change every 3 h. **Golden Bloons** appear on the alternate weekends (Fri to Mon), from R21, never in Deflation or CHIMPS.

## Ranking: single-player, bot-feasible (value to a farming bot, then ease)

Top 15 that need deliberate action:

| # | Achievement | Reward | Feasible | How (short) |
|---|---|---|---|---|
| 1 | Student | Cash Drop x2, Wizard insta | easy | Apply 1 MK point (the point also helps the bot) |
| 2 | Scholar | 100 MM, Druid insta | easy | Apply 10 MK points |
| 3 | First Monkeys First | Monkey Boost x2, 3-0-0 Dart insta | easy | 10 primary_only wins (already farmed) -> `ach_first_monkeys_first` |
| 4 | War Monkeys | MOAB Mine x3, 2-0-2 Sniper insta | easy | 10 military_only wins -> `ach_war_monkeys` |
| 5 | Abracadabmonkey | SMS x1, 0-0-3 Druid insta | easy | 10 magic_only wins. Also feeds Rainbow is Magic, I see you, Oathbreakers and Magical Gold |
| 6 | Monkey Avenger League | 100 MM | easy | Win once each with Quincy, Gwendolin, Striker Jones, +1 more hero |
| 7 | First Steps | 100 MM | easy | Quests menu: "First Time Tutorial!" |
| 8 | All for one and one for one | 1 MK point | medium | One Buccaneer on Logs to Pirate Lord -> `ach_all_for_one_and_one_for_one` |
| 9 | A year in the making | 365 MM, 1 MK point | easy | Claim the daily chest every day (365 times) |
| 10 | Survivor | 100 MM | medium | Win Apopalypse (`apopalypse_ninja_sniper`) |
| 11 | Role Reverser | 50 MM | easy | One Reverse win -> `ach_role_reverser` |
| 12 | Side Quest | 100 MM, 2 tier-2 instas | medium | Complete any quest |
| 13 | Bloons Master | 250 MM, 1 MK point | hard | One CHIMPS win on Logs -> `ach_bloons_master`. Then Superior (5 maps) and Ultimate (15 maps) give 1,000/2,000 MM and 2/4 MK points |
| 14 | Unsung Monkeys | Banana Farmer x2, farm insta | medium | Support-only Easy x10 -> `ach_unsung_monkeys` |
| 15 | Team Player | 3 tier-1 instas | medium | Monkey Teams wins (dynamic tower set) -> `ach_team_player` |

Next tier, ordered roughly by value and ease: Our Powers Combined (200 MM, but
buying the powers costs MM), Tetrimino, Therpopylae (queue Peninsula), Golden
Bloon set (So Shiny!, Glittering, Glorious, Magical Gold; weekends only),
Master of life, Student Loans, Big Spender + Heavy Investment + Apotheosis
(one late-game Paragon purchase can unlock all three), Inflated, Kali
Maaaaaaaa / Big Bloons (need Adora / Pat), Chunky Monkeys and Golden Ticket
(cosmetic only), Living on the Edge, Snap of your fingers, Nah, I'd Win, 2TC,
Josh's Constant, 2 MegaPops, Axis of Havoc, What did it cost?, Strangely
Adorable, Perfect Paragon.

Passive (49 entries, nothing to do except keep farming): pop and kill counters
(Impoppable, MOAB/BFB/ZOMG/DDT/BAD, Sapper, Infrared, Red and Blue Makes...),
map progression (First Win through Advanced Player, Decorated Hero, Medal
Winner), Big/Mega Monkey, hero ability and level feats, mode counters (Indie,
Thrifty, Bloonzilla!, Poppable, CHIMPS masters), Tools to Darwin, Sticky
Situation, Not Lacking Critical Information, Stubborn Strategy, Life
Experience, Tower Keeper, Achievement of Achievements.

Conflicts with project rules: **I'll Be Back** (spend MM on continues) is
marked infeasible. **Living on the Edge** needs deliberately undefended early
rounds, which breaks the "never start rounds undefended" rule; it needs an
explicit exception from the user.

## Restricted-win plans (`kind: game_win_constraint`)

Each YAML keeps the normal strategy schema (`id`, `hero`, `modes`,
`planner{towers, base_success}`, `plan`/`fill`/`panic` with roles
dps/support/exit/far, upgrades as `a-b-c`, `answers`). It adds
`achievement:`, `map:`, a `constraints:` block, and `notes:` for steps the
executor can't express yet.

**Wiring needed (not done, since no .py edits were allowed):**
- `strategy.load_all()` only globs `strategies/*.yaml`, so this folder is not loaded yet.
- The executor would also have to honor these constraint keys: `allowed_towers`, `place_hero: false`, `no_default_panic` (today `panic: []` falls back to a default panic tower), `no_answers`, `max_towers_on_screen` and `max_towers_purchased`.

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
