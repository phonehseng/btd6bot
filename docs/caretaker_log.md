# Caretaker log

## 2026-10-21 18:25
- Found no supervisor or bot running: bot.log stopped at 16:46 ("first visit to Logs: scanning placement") and supervisor.log logged no exit, so the whole process tree was killed from outside (no crash event, no traceback). BTD6 was still running.
- Restarted the supervisor at 18:13. At the same moment another session installed the `BTD6Bot` scheduled task (`tools/install_task.ps1`), which started a second supervisor. Killed mine within a minute (it had only reached the main menu); the scheduled-task instance (24 h) is now the only bot running.
- Since 15:57: 3 RESULT lines, 3 wins and 0 losses, 0 lives lost. Player level L19. Logs/Easy was in progress at round 30 with 200 lives; the placement scan finished (704 points, 48% placeable).
- Seen: cash OCR misread for rounds 2-17 on Logs (e.g. 3117, 8297, 7337, apparently an extra leading digit). Reads were sane from round 18. Watch this; it can make the bot try purchases it can't afford.
- No development this run: another session had uncommitted edits in runner.py, run_forever.ps1 and README.md, so I left the code alone. Suggestion: run_forever.ps1 should refuse a second instance (named mutex), because the caretaker and the scheduled task can race.

## 2026-10-22 16:30
- Bot status: scheduled task BTD6Bot is Ready (not running); the last supervisor exit was code 3 (owner stop) at 16:07, logged by bot.log as "stopped by the user (Ctrl+Alt+F8 or STOP file)". logs/dev_active.txt was touched at 16:11 and planner.py/strategy.py have uncommitted edits, so a developer session is working and the stop is theirs. Not restarted, no code changes this run. BTD6 is still open; the recorder is running. Safe mode: off (streak 0, trips 0).
- Since the 10-21 18:25 entry: 59 games, 45 wins, 13 defeats, 1 abandoned. 12 of the defeats came from the medium/hard tiers between 01:11 and 05:17 (Ancient Portal, Logs x2, Tree Stump medium; Luminous Cove, Pat's Pond, Dark Path, Last Resort, Enchanted Glade, Party Parade, Castle Revenge, Covered Garden hard), the other two were Deflation with solo_spike (Bloonarius Prime r49, Ancient Portal r54). From 13:00 the bot was back on Easy-family medals and won 20 of 22.
- Stopped game: Water Park / easy with solo_tack. Lives fell 200 -> 7 by round 36. Evidence in bot.log: ~30 land spots "not placeable", ten tack spots "refused the click" in a row on round 29, and from 16:05 every tack (tack2..tack11, b2) was "corrected" to 0-1-2 from one identical panel read ([(None,None),('cash',190),('cash',385)]) while cash stayed 1390 - the upgrade panel was most likely not the selected tower's (selection not landing on this water map), so no upgrades were bought for two rounds. Worth a look by the active developer: the "really X-Y-Z - corrected" path should not accept a panel whose prices are identical for every tower, and solo_tack needs land-spot coverage checked for water maps.
- supervisor.log is still locked by a stale handle (every supervisor line since 10-21 16:34 goes to supervisor.fallback.log only); harmless but hides the live log from a plain tail.

## 2026-10-22 16:30 (second run, same minute)
- A second caretaker run fired alongside the 16:30 entry above; it found the same state and did nothing more: BTD6Bot task Ready, last exit code 3 at 16:07 (owner/developer stop), no bot process, BTD6 open, recorder running, safe mode off. logs/dev_active.txt was rewritten at 16:26, so the developer session is still active: no restart, no code edits.
- Noted for the developer: the stale `tail -F` processes from 10-21 evening sessions (seven of them, still alive) are what hold logs/supervisor.log open; ending them should let the supervisor write its main log again.
- The Water Park / easy near-loss (solo_tack, 200 -> 7 lives) still has no RESULT line, so it is not counted in results.jsonl; its diagnosis is left with the active developer as above.

## 2026-10-23 14:58
- Bot status: running (bot.py run pid 31544, recorder up, BTD6 open); state.txt fresh (14:55, Off The Coast easy r39, 200 lives); no tracebacks. Scheduled task shows Ready while the bot runs, so it was started outside the task; left alone. Safe mode ON (tripped 14:18, streak 5 of 16 wins needed, trips 2).
- Since the 10-22 16:30 entry the double_hp tier was entered in earnest: 28 games on 10-23 between 07:52 and 14:18 with ~6 defeats (Spice Islands magic_only r39, Ancient Portal r27, Balance r38, Dark Path r40, Castle Revenge r60, Encrypted r40) and the rest wins. After the 14:18 Encrypted loss the breaker fired and the bot is back on Easy-family medals: 5 wins, 0 losses since.
- Diagnosed Encrypted double_hp (ninja/alchemist build, 100 lives gone from round ~40 in about 3 minutes): bot.log shows "threat moab: nothing applicable to buy - not holding the plan for it" at round ~40, i.e. the build had no MOAB-class damage at the double-HP blimp wave. Same family as the other double_hp strategy deaths; the strategy double_hp_sniper_sun needs an earlier MOAB answer (heli/ace/bomb upgrades) before the round-40 blimp check, and the loss rate for this tier (about 1 in 5) is too high for 'never lose'. No code edits this run (no safe small fix; left for the next developer run).

## 2026-10-23 15:00
- Bot status: bot.py run (pid 31544) and the recorder are running and BTD6 is open; the BTD6Bot task reads "Ready" but the supervisor process (pid 33204) is alive, so nothing was restarted. bot.log is current (Off The Coast / easy, round 39, 200 lives). logs/dev_active.txt is from 00:51, so no developer is active. Safe mode: ON (streak 5, trips 2, last trip 14:18) and it is correctly running Easy-family medals; the last 5 games were all wins.
- Since the 10-22 16:30 entry: 115 games, 96 wins, 19 defeats. By mode: hard-tier sniper/sun/avatar plans (Pat's Pond, Party Parade, Covered Garden, Last Resort, Bloonarius Prime), magic_only x4 with magic_obyn_ninja_wizard, double_hp x5 (Ancient Portal, Balance, Dark Path, Castle Revenge, Encrypted), plus Water Park easy solo_tack, Ravine easy opt_ravine_easy (r18, 168 lives lost) and Quarry deflation solo_bomb.
- Diagnosed from bot.log (Encrypted double_hp, 13:46): the defence rating fell to 0.18-0.28 by rounds 36-40 with only ninjas, a village and a few snipers; 15 and 38 lives went in single rounds and many ninja/spike spots were "invalid for". double_hp_sniper_sun gets too little damage into rounds 35-40 on these maps. Several results show lives_lost 0 with a defeat (Dark Path r40, Cracked r76, Bloonarius Prime, Enchanted Glade): worth checking whether the defeat logic is mislabelling the game or the lives counter is misread.
- No code changes this run (time went on the health check); the 12h bench and safe mode contain the damage. Next developer pass should take the Ravine easy loss first (an easy-tier loss is the most serious), then the lives_lost 0 defeats.

## 2026-10-23 15:40
- Bot status: found DOWN. The supervisor and bot.py were gone, BTD6 was open but not in front, and bot.log showed "paused: BTD6 is not the foreground window" from 15:00 (Off The Coast easy, round 32, 200 lives) onward, so about 40 minutes of play were lost and that game has no RESULT line. Restarted with `schtasks /run /tn BTD6Bot`, brought the BTD6 window forward; the bot reached the main menu and started Another Brick / easy (military_heli_sniper).
- Wins/losses since the 15:00 entry: none recorded (last result 14:56, Off The Coast easy, a win). Safe mode ON (streak 6 of 16, trips 2). No developer active (dev_active.txt from 00:51).
- Likely cause: something took focus from BTD6 at 15:00 (the overlay.py process is still running) and the supervisor died later; not diagnosed further. No code edits this run; open items remain the Ravine easy loss, the lives_lost 0 defeats and the double_hp MOAB answer.

## 2026-10-23 16:20
- Bot status: healthy. BTD6Bot task Running, bot.py run (pid 34444) and the recorder are up, BTD6 open; state.txt is 5 seconds old (High Finance / easy, round 32, 200 lives). No tracebacks or loops in the last 300 log lines; supervisor restarts are the normal exit-code-4 code reloads.
- Since the 15:40 entry: 6 wins, 0 defeats (results.jsonl). Safe mode ON (streak 12, trips 2) and running Easy-family medals as intended.
- Only warnings seen: "giving up on step" for heli/sniper placements with 0 refused spots on the current map (a new map's spot list is empty for those steps). No code edits this run; open items unchanged (Ravine easy loss, lives_lost 0 defeats, double_hp MOAB answer).

## 2026-10-27 18:35
- Bot status: healthy at last check (task Running, bot.py + recorder up, BTD6 open, state fresh). Safe mode ON (streak 8, trips 2); no developer active.
- Diagnosed the Sunset Gulch easy loss (r18, 162 lives): ~107 learned refused spots (3x3 patches) were treated as walls in placement.valid_spots' footprint check, leaving 0 legal cells for hero/sniper/heli, so only one sniper was placed. Fixed: refused cells are removed after the footprint check (sniper spots 0 -> 1,024 on the saved model); regression test added; check.py ALL OK.
- 27 older loss folders still say "status: new" (mostly Hard/double_hp/magic_only strategy deaths already noted above); not worked through this run. Open: why ~100 refusals accumulate per map; double_hp MOAB answer.

## 2026-10-27 18:57
- Bot status: running (task Running, bot.py + recorder up, BTD6 open). Found it paused because OneDrive had taken the foreground; brought BTD6 back to the front and it resumed. Safe mode ON (streak 1/64 after the win below, trips 4); no developer active.
- Since the 18:35 entry: 1 win (Another Brick military_only, medal earned). Two earlier Another Brick military_only defeats (17:39 and 18:12, rainbow rush at round 51) never reached results.jsonl: the bot ignored the defeat card for ~25 min each time because the lives counter behind it read "1", and the watchdog restart landed on the defeat screen.
- Fixed and committed: the defeat card ("Bloons Leaked", or Defeat with Restart/Review Map) now counts as proof of a defeat, and 15 defeat reads in a row count whatever the lives say; only one false_defeat picture per false alarm (2,273 had piled up in logs/).
- Diagnosed the 8 Medium losses of today (Covered Garden, X Factor, Enchanted Glade, Sunset Gulch, Castle Revenge, Ship Capture, Mushroom Grotto, Last Resort): placement starvation (fixed in eb9514e, which came after them) plus too little blimp damage at the round-40 MOAB. Diagnosis written, folders marked handled; backlog item 8 added for the blimp check. 50 older folders still say "status: new"; Polyphemus apopalypse (17:32) not worked through yet.

## 2026-10-27 19:30
- Bot status: found paused - BTD6 had closed at 19:07:58 mid-game (Pat's Pond medium, no crash dialog or event-log entry). Started it through Steam; after a code reload the bot reached the menus, won Pat's Pond medium (19:21) and is playing Pat's Pond reverse. Task Running, bot.py + recorder up. Safe mode ON (streak 1, trips 4); no developer active.
- Since the 18:57 entry: 3 wins (Off The Coast reverse, Another Brick reverse, Pat's Pond medium), 1 defeat (Peninsula medium r42, water_sub_alch). The Peninsula case folder was missing, so it was filed with `python -m btd6bot.losses`.
- Polyphemus apopalypse (17:21, r52): the lives crop started on the heart's bonus-lives ring and OCR read 86 as 286 for 30 rounds, so no leak was seen. Fixed in e3c6f82 (crop starts at x 0.064, regression test with real HUD frames; impossible reads on 400 stills go from 12 to 2). check.py ALL OK.
- Peninsula medium: too little MOAB damage at r40-42. Reinforce bought zero-gain sub upgrades, and path-1 prices that read blank by mistake closed the plan's real upgrades. Diagnosed but not fixed yet: backlog items 10-12 (blank path-1 prices, reinforce saving for the worst round, Apopalypse cash piling up). Both folders are marked handled.

## 2026-10-27 20:20
- Bot status: OFF on purpose. At 19:33 it was stopped from the HUD, BTD6 was closed, and at 19:38 bot_off.ps1 wrote STOP (exit code 3, owner stop; commit 1217741 adds the OFF/ON buttons). Not restarted, STOP left in place; BTD6 not running. Safe mode ON (streak 2, trips 4); no developer active.
- Since the 19:30 entry: no finished games (Pat's Pond reverse was a win at 19:29; the next game was cut off by the stop).
- Bazaar Medium (06:16, r56, $33k unspent): the placement starvation already fixed in eb9514e. Diagnosis written, folder marked handled; 48 older folders still say "status: new".
- Backlog item 10 fixed: a blank upgrade price is now read again with the cursor moved off the panel and 0.4 s to settle, so a hover tooltip right after a click no longer closes a path for the game (regression test in tests/test_purchase_proof_offline.py).

## 2026-10-27 21:45
- Bot status: still OFF on purpose (STOP from bot_off.ps1 at 19:38, exit code 3; HOLD from the HUD stop). Not restarted; BTD6 not running. Safe mode ON (streak 2, trips 4); no developer active.
- Since the 20:20 entry: no games played (0 wins, 0 losses).
- Diagnosed the three newest open losses (2026-10-27 early morning). Glacial Trail Easy and Spillway Deflation: placement starvation (0 refused spots, cash unspent), already fixed in eb9514e. Dark Dungeons Primary Only (solo_bomb): the damage model rated round 11 at 0.06 and the optimizer's best build only 0.68, but the planner never asked it.
- Fixed in cd7ff76: each optimized build's worst_margin now counts as a map/mode ceiling, so map/modes under 1.5 are capped at p 0.5 until a win. On the record they went 19-19, against 74/87 at 2.0 or more; 60 of 185 optimized map/modes are now capped. check.py ALL OK. 45 older folders still say "status: new".

## 2026-11-02 20:45
- Bot status: back ON. STOP is gone and BTD6 was started at 20:24 by the owner's live session. The first bot process gave up on the loading screen ("too many consecutive failures", exit 0); the supervisor restarted it at 20:29 and it reached the main menu. It then waited 7 min for the app window covering the game; the caretaker brought BTD6 forward at 20:37 and it resumed (syncing account SFYOSHHYV, reading upgrade trees). Safe mode ON (streak 2, trips 4).
- Since the 2026-10-27 21:45 entry: no finished games (0 wins, 0 losses).
- Losses: 14 open case folders on map/modes with a model ceiling under 1.5 were diagnosed as one group: the planner played games the damage model rated unwinnable, now capped by cd7ff76 (each folder's ceiling re-checked today; 6 also show the placement starvation fixed in eb9514e). Marked handled; 28 older folders still say "status: new".
- Not committed: the 2026-10-28 working-tree change to btd6bot/reinforce.py (trim() keeps the dearest options; under margin 1 the purchase saving the most lives wins), with its test and backlog item 13. tests/test_reinforce_offline.py passes, but tools/check.py did not finish within this run (over 12 min while the bot runs), so next run: run check.py and commit it if ALL OK. The bot already runs this code because it reloads from disk.

## 2026-11-02 21:54
- Bot status: running (BTD6Bot task Running, bot.py run since 20:29, recorder up, BTD6 responding); state.txt fresh (Sulfur Springs Deflation, round 32, 200 lives). No tracebacks or loops in bot.log. Safe mode ON (streak 7, trips 4).
- Since the 20:45 entry: 5 wins, 0 losses (Spice Islands Primary Only + Deflation, Quiet Street Primary Only + Deflation, Sulfur Springs Primary Only). No new loss folders.
- Committed the pending reinforce change (5dada26: the option list keeps the dearest purchases too; under margin 1 the most lives saved wins) after a full check.py ALL OK.
- Fixed why check.py could not finish in a run (6af2640): test_base_success_is_conservative reloaded every strategy per tower and mode (over 10 min alone); it loads once now.
- Next run: 28 old folders still "status: new", newest first: Ravine Easy (solo_buccaneer, round 28, 118 lives lost) and Spillway Deflation (round 50, report says 0 lives lost - check whether the defeat or the lives count was misread).

## 2026-11-02 22:40
- Bot status: running again (BTD6Bot task Running, bot.py run since 20:29, reloaded 22:28; playing Pat's Pond Military Only, round 45, no lives lost). From 21:44 to 22:28 it was stuck: five games in a row refused with "no defence could be placed", the last three waiting 10 min each for a code fix. Safe mode ON (tripped again by the loss; 0/64 wins to leave, trips 4).
- Since the 21:54 entry: 3 wins (Sunken Columns Easy, Dark Path Primary Only, Cargo Primary Only), 1 loss (Dark Path Deflation, round 35, solo_dartling).
- Stuck cause, fixed in af14398: seasonal scenery next to the cash counter. Tricky Tracks' Halloween graffiti read as '$3.700-00元', and Encrypted's falling leaves added a phantom digit. Every read was rejected and the bot never buys on unknown cash. The cash parser now cuts trailing junk, accepts a padded read only when it repeats a clean one, and cash_stable no longer ends on a bad frame; all 52 recorded frames read correctly.
- Loss diagnosed (diagnosis.md, handled): general Deflation build too weak (rated 0.48 for round 40 once fully bought, $115 left), while the planner trusted the optimized build's 2.04 ceiling. Code fix not done yet: backlog item 14 (rate the build before Play in no-income modes and leave the game instead of losing; planner uses the optimized build or the build's own rating). Next run: do item 14. The 28 old folders still say "status: new".

## 2026-11-02 23:52
- Bot status: running (BTD6Bot task Running, bot.py run since 22:28, recorder up, BTD6 responding); playing Castle Revenge Military Only. No tracebacks or loops. Safe mode ON (streak 7, trips 4).
- Since the 22:40 entry: 8 wins (Dark Path and X Factor Medium/Reverse/Military Only, Castle Revenge Medium/Reverse), 1 loss (Sunset Gulch Medium, round 53).
- Backlog item 14 done (ae96a28): Deflation builds are rated over rounds 31-40 before Play and left (benched 24 h, not a defeat) under 0.8 - calibrated on 26 logged Deflation games, it catches 5 of 7 losses for 1 of 19 wins; general builds capped at p=0.76 in no-income modes.
- Sunset Gulch loss diagnosed and handled (6647c72): 10 false hero-click refusals were learned as bad ground; the map's refused layer had grown to 2,444 of 4,326 legal cells, leaving one sniper and $54,839 unspendable. Refused-click runs that place nothing are no longer learned; Sunset Gulch's layer reset. Other maps look poisoned too: backlog item 15.
- Next run: backlog item 15 (clean refused layers), then the 28 old "status: new" folders.

## 2026-11-03 00:35
- Bot status: running (BTD6Bot task Running, bot.py run since 00:16, recorder up, BTD6 responding); playing Ship Capture Military Only, round 49, no lives lost. Safe mode ON (3/64 wins to leave, trips 4).
- Since the 23:52 entry: 2 wins in results.jsonl (Castle Revenge Military Only, Ship Capture Reverse), 0 losses. Ship Capture Medium also ended on a Victory screen, but the bot was silent from 00:06 to 00:16 (after "upgrade sniper6 ... not bought" x3) and the watchdog killed it; the restarted bot found the Victory screen and logged it as a win. The cause of the silence is unknown: logs\stacks.txt had already been overwritten by the new bot.
- run_forever.ps1 now copies stacks.txt to logs\hang_stacks_<time>_<hung|loop>.txt before the watchdog kills the bot (newest 5 kept). It takes effect the next time the supervisor itself restarts (it was not restarted, so the game in progress was not interrupted).
- Backlog item 15 done: each map forgets, once on load, learned refusals inside buckets where a tower really stood (e.g. Polyphemus 397 cells, Frozen Over 265, Spice Islands 126), and every placed tower clears the refusals under it. Offline test tests/test_refusal_cleanup_offline.py.
- Next run: if a hang_stacks file shows up, diagnose it; then the 28 old "status: new" loss folders (newest: Ravine Easy, Spillway Deflation).

## 2026-11-03 01:47
- Bot status: running (BTD6Bot task Running, bot.py run since 00:25, recorder up, BTD6 responding); playing Enchanted Glade Military Only, round 48, no lives lost. Safe mode ON (streak 2, trips 4). No hang_stacks file yet.
- Since the 00:35 entry: 6 wins (Underground Medium/Reverse/Military Only, Peninsula Medium and Military Only, Enchanted Glade Medium), 3 losses (Party Parade Medium r40, Geared Medium r40, Peninsula Reverse r50) - all three diagnosed and handled.
- Geared (1894329): the round reader froze at 23 while the game ran to 40 - placement ticks of 10-15 s let the game move on >2 rounds between reads and only identical reads were counted. match.RoundVotes now accepts readings the elapsed time explains. Test tests/test_round_votes_offline.py.
- Peninsula Reverse (d225f14): OCR reads "$2,200" as "#2,200", so every sniper's path 1 was closed and $51,030 sat unspent; game.looks_like_price accepts it. This is also the root cause of backlog item 10. Test tests/test_price_text_offline.py.
- Party Parade: round-40 MOAB with a weak general build (backlog item 8, no code change). New backlog item 16: follow towers carried by Geared's gears.
- Next run: watch bot.log for "shows no price although its tiers" becoming rare (item 10); backlog item 16 or 8; then the 28 old "status: new" folders.

## 2026-11-03 02:59
- Bot status: running (BTD6Bot task Running, bot.py run since 01:41 with reloads, recorder up, BTD6 responding); playing Dark Castle Military Only, round 56, no lives lost. Safe mode ON (streak 1, trips 4).
- Since the 01:47 entry: 6 wins (Enchanted Glade Military Only/Reverse, Cargo Medium/Military Only/Reverse, Dark Castle Medium), 4 losses (Spillway, High Finance, Cornfield, Sanctuary Medium) - all diagnosed and handled.
- Spillway (01bc6af): OCR reads "$500" as "学500" at full resolution; str.isalnum() accepts the glyph, so the price looked blank and sub paths closed. Second root cause of backlog item 10 (~80 blank reads/hour after the '#' fix).
- High Finance / Cornfield (2aed24b): mapfit gave global-range towers full coverage without checking room; now counts towers that fit (High Finance heli/ace/mortar 0, Cornfield ace 1/3). All 88 maps re-measured.
- ddc7271: safe mode now plays only p >= 0.85 games and idles otherwise (the three p 0.78-0.84 safe-mode games all lost). Sanctuary: platforms carry towers (backlog 16). 28 old (Oct 22-24) loss folders triaged: 7 superseded by later wins, 21 grouped by cause.
- Next run: if the bot idles ("safe mode plays only games with p >= 0.85"), raise confidence with better builds rather than lowering the bar; check the "shows no price" hourly count fell; backlog 11 (reinforce while saving) and 16.

## 2026-11-03 03:40
- Bot status: running (BTD6Bot task Running, bot.py run since 02:50, recorder up, BTD6 responding) but idle since 03:06: "safe mode plays only games with p >= 0.85 and none is left". Safe mode ON (streak 3/64, trips 4).
- Since the 02:59 entry: 1 win (Dark Castle Reverse, 0 lives lost), 0 losses. No new loss folders.
- Cause of the idling: the only p >= 0.85 games left were benched, not unplayable. Lotus Island Military Only/Reverse (p 0.98) are padlocked in the game although the card and medal sweep show its Medium medal (probably a co-op guest medal), so they failed to start, were benched 2 h and came back first again. 4771aa5: a mode that stays on mode select after three clicks is noted as locked for 7 days (with its siblings and the chain below it) and mode_unlocked() skips it. Test tests/test_locked_modes_offline.py.
- Tricky Tracks Easy fails with "no defence could be placed" and no placement line at all (108 valid spots offline, no "unspent" warning -> probably the cash read is None on that map). The error now logs the cash read and plan note; its 6 h bench ends ~03:45, so the next run should read that error.
- Next run: after Lotus is locked out, the safe-mode pool is nearly empty (Peninsula Reverse benched until ~13:00). Safe mode needs 64 wins in a row to end and has almost nothing to play, so it is effectively a deadlock: consider letting safe mode end after a clean idle period, or offer Easy-family games at p >= 0.85 with better builds. Also "level reads 38 but notes say 137" fires after every game (~4 s each).

## 2026-11-03 04:40
- Bot status: running (BTD6Bot task Running, bot.py run reloaded 04:31 with the new code, recorder up, BTD6 responding) but idle: safe mode (0/64, trips 4) has no p >= 0.85 game left. No loops, no tracebacks.
- Since the 03:40 entry: 0 wins, 1 loss - Tricky Tracks Easy (round 27, p=0.98 n=0), handled. Lotus Island Military Only/Reverse were noted locked for 7 days as designed.
- Tricky Tracks (61fa7bb): the game refused every spot after hero + 2 snipers (heli/tack/sniper streaks, a step given up, $5,885 unspent) and cash read None; the map had already failed twice with "no defence could be placed", which taught the planner nothing. New AccountState.placement_trouble per map (no-defence errors + losses with a given-up step, cleared by a win) scales every mode's prior there by 0.7 per event. Tricky Tracks set to 3 and all modes benched 48 h. Real cause (refused valid spots, cash OCR) is backlog 17.
- b3bb0a6: safe mode's "a clean day resets the doubling" never happened while safe mode stayed on (trips 4 from late Oct -> 64 wins). Now every day without a trip or defeat forgives one trip: 32 from ~2026-11-04 03:56 if no game is lost.
- Next run: backlog 17 (Tricky Tracks overlay + cash OCR on frames/game_002.jpg); the safe-mode pool is still nearly empty - raising confidence with better Easy-family builds is the way to get games.

## 2026-11-03 05:35
- Bot status: running (BTD6Bot task Running, bot.py run since 04:31, recorder up, BTD6 responding), idle by design: safe mode (0/64, trips 4) has no p >= 0.85 game left (top: Peninsula Reverse 0.86, benched until ~13:00; Spillway Medium 0.849). No loops, no tracebacks, no PAUSE/STOP.
- Since the 04:40 entry: 0 wins, 0 losses. No new loss folders (all handled).
- Backlog 8 calibrated instead of changed blind: new tools/ramp_calibration.py pairs the logged round-40 blimp check with each game's outcome. Medium family lost 10 of 24 games rated under 1x but only 6 of 115 at 1x+ (Hard family 24% vs 12%), so the check is already a good loss predictor; the next step is to rate the round-40 ratio offline per (strategy, map) and feed it to the planner's p, which could lift the strong open Medium medals over the safe-mode bar.
- Next run: that planner change (backlog 8), or backlog 17 (Tricky Tracks). Safe-mode forgiveness starts ~2026-11-04 03:56 if nothing is lost.

## 2026-11-03 06:28
- Bot status: running (BTD6Bot task Running, bot.py run since 04:31, recorder up, BTD6 responding), idle by design: safe mode (0/64, trips 4) has no p >= 0.85 game left. No loops, no tracebacks, no PAUSE/STOP.
- Since the 05:35 entry: 0 wins, 0 losses. No new loss folders.
- Backlog 17, cash part: on the Tricky Tracks stills the graffiti right of the cash was read as extra digits ('$2,873' -> '$2-87300', '$3.0260'), so cash was None at most round starts. hud.trim_to_digits re-reads a failed crop cut where the white digits end, and a dash before three last digits counts as the comma: correct reads 4 -> 11 of the first 17 frames. Test in tests/test_cash_offline.py.
- Next run: Tricky Tracks refused spots (rest of backlog 17), or backlog 8 (rate builds' round-40 ratio offline to lift strong Medium medals over the safe-mode bar). "level reads 38 but notes say 137" still fires every 30-min idle check.

## 2026-11-03 07:45
- Bot status: running (BTD6Bot task Running, bot.py run since 06:20, recorder up, BTD6 responding), idle by design: safe mode (0/64, trips 4) has no p >= 0.85 game left (top: Peninsula Reverse 0.862 benched, Spillway Medium 0.849). No loops, no tracebacks, no PAUSE/STOP.
- Since the 06:28 entry: 0 wins, 0 losses. No new loss folders.
- Backlog 8: tested whether the offline simulator's round-40 blimp ratio could lift the strong open Medium builds over the bar. New `ramp_calibration.py --offline` says no: it does not predict losses (Easy 2x+ lost 15% vs 7% at 0.5-1x; Hard no better; only Medium trends). Planner unchanged; the estimate needs each map's real track reach first.
- Next run: simulate with the map's track reach (mapgeom) and recheck, or backlog 17 (Tricky Tracks refused spots). Safe-mode forgiveness from ~2026-11-04 03:56.

## 2026-11-03 08:30
- Bot status: running (BTD6Bot task Running, bot.py run since 06:20, recorder up, BTD6 responding), idle by design: safe mode (0/64, trips 4) has no p >= 0.85 game left. No loops, no tracebacks, no PAUSE/STOP.
- Since the 07:45 entry: 0 wins, 0 losses. No new loss folders.
- "level reads 38 but notes say 137" (every 30-min idle check): the account is level 138 and the badge's leading "1" spans x 0.089-0.099, so the old OCR box (from x 0.095) cut it in half. runner.read_level now reads (0.083-0.13); on recorded menu frames it reads 138 at 0.99 confidence. The notes should adopt 138 at the next check.
- Next run: confirm the warning is gone in bot.log; then backlog 17 (Tricky Tracks refused spots) or simulate with mapgeom track reach (backlog 8). Safe-mode forgiveness from ~2026-11-04 03:56.

## 2026-11-03 09:35
- Bot status: running (BTD6Bot task Running, bot.py run since 08:19, recorder up, BTD6 responding), idle by design: safe mode (0/64, trips 4) has no p >= 0.85 game left. No loops, no tracebacks, no PAUSE/STOP. The "level reads 38" warning is gone: the bot now reads L138.
- Since the 08:30 entry: 0 wins, 0 losses. No new loss folders.
- Backlog 17 (Tricky Tracks refused spots), checked offline: the map geometry fits the screen exactly, and 37 of the 48 refused spots are on the brick platforms at the same distance from the rails as the two snipers that were placed. So the ground data is not the cause; after the second sniper every click was refused everywhere. Item changed to a live check (overlay saved as dev media). The first heli spot was on a track the grid forbids - which code path picked it is still open.
- Next run: backlog 8 (simulate with the map's track reach) or 11/12 (reinforce spends while the plan saves). tools/check.py takes ~6 min now: run it with a bounded wait. Safe-mode forgiveness from ~2026-11-04 03:56.

## 2026-11-03 10:45
- Bot status: running (BTD6Bot task Running, bot.py run since 08:19, recorder up, BTD6 responding), idle by design: safe mode (0/64, trips 4) has no p >= 0.85 game left. No loops, no tracebacks, no PAUSE/STOP.
- Since the 09:35 entry: 0 wins, 0 losses. No new loss folders.
- Backlog 12 done: in Apopalypse (continuous sends) a plan step blocked by refused spots or an upgrade click with no effect is now set aside after one attempt and the plan goes on; a set-aside placement carries its later upgrades with it (also fixes Deflation dropping them). Polyphemus 2026-10-27 had idled from $2k to $15k on such steps. Offline tests added; check.py ALL OK.
- Next run: why surplus() bought nothing in that Polyphemus minute; backlog 11 (reinforce spends while the plan saves) or 8. Safe-mode forgiveness from ~2026-11-04 03:56.

## 2026-11-03 11:30
- Bot status: running (BTD6Bot task Running, bot.py run since 10:19, recorder up, BTD6 responding), idle by design: safe mode (0/64, trips 4) has no p >= 0.85 game left. No loops, no tracebacks, no PAUSE/STOP.
- Since the 10:45 entry: 0 wins, 0 losses. No new loss folders.
- Backlog 5 and 6 were stale: `test_long_run_reaches_everything` passes (449 simulated games, 44 Hard medals, 18% losses) and the planner already learns per-map minutes from `map_stats`. Both moved to Done.
- Next run: backlog 11 (reinforce spends while the plan saves for a step after the weakest round) or 8. Safe-mode forgiveness from ~2026-11-04 03:56.

## 2026-11-03 12:28
- Bot status: running (BTD6Bot task Running, bot.py run since 10:19, recorder up, BTD6 responding), idle by design: safe mode (0/64, trips 4) has no p >= 0.85 game left. No loops, no tracebacks, no PAUSE/STOP.
- Since the 11:30 entry: 0 wins, 0 losses. No new loss folders.
- Backlog 11, Cornfield part: replayed the Cornfield Medium loss offline. Reinforce did run, but had nothing it was allowed to buy: no tower fitted, the big tiers cost $32-42k, and the sniper's 4-2-0 ($450, weakest round 0.71 -> 0.87) was past the plan's crosspath. Reinforcing may now take a side path up to tier 2 once the leading path is past 2 (Executor._side_path_ok), and reinforce logs when it finds nothing or a purchase fails (both were silent). Test added; check.py ALL OK.
- Next run: backlog 11 rest (spend while the plan saves for a step landing after the weakest round) or 8. Safe-mode forgiveness from ~2026-11-04 03:56.

## 2026-11-03 13:35
- Bot status: running (BTD6Bot task Running, bot.py run since 12:21, recorder up, BTD6 responding), idle by design: safe mode (0/64, trips 4) has no p >= 0.85 game left. No loops, no tracebacks, no PAUSE/STOP.
- Since the 12:28 entry: 0 wins, 0 losses. No new loss folders.
- Backlog 11, Peninsula part: when the weakest round leaks even at full strength and nothing affordable lifts it over 1, reinforce now saves for the cheapest dearer purchase that does (up to 3x the cash, round 2+ away) and surplus() leaves that cash alone ("reinforce: saving for ..."). The "plan saves past the weakest round" case was already covered (reinforce ignores the plan's wait). Tests added; check.py ALL OK.
- Next run: backlog 8 (simulate with the map's track reach) or 16 (Geared rotating tower positions). Safe-mode forgiveness from ~2026-11-04 03:56.

## 2026-11-03 14:36
- Bot status: running (BTD6Bot task Running, bot.py run since 13:19, BTD6 responding), idle by design since 13:58: safe mode (1/64, trips 4) has no p >= 0.85 game left. No loops, no tracebacks, no PAUSE/STOP.
- Since the 13:35 entry: 1 win (Peninsula Reverse, peninsula_medium, 0 lives lost), 0 losses. No new loss folders.
- Backlog 16, gear part: towers on Geared's gears are now followed round - `btd6bot/carried.py` turns each remembered click spot by the gear's angle (45/108 deg, from the map's RotateAreaAction data) whenever the round counter advances, so selections stop failing and towers are no longer "forgotten" and re-bought. Test `tests/test_carried_offline.py`; check.py ALL OK. Sanctuary's moving platforms still open.
- Next run: backlog 8 (simulate with the map's track reach) or Sanctuary platforms (16 rest). Safe-mode forgiveness from ~2026-11-04 03:56.

## 2026-11-03 15:45
- Bot status: running (BTD6Bot task Running, bot.py run since 14:22, recorder up, BTD6 responding). It was PAUSED 14:22-15:18: a Steam "Refresh Sign In" window had taken the foreground. The caretaker brought BTD6 back to the front (not signed in to Steam; if the window keeps coming back, the owner may need to sign in). Since then idle by design: safe mode (1/64, trips 4) has no p >= 0.85 game left. No loops, no tracebacks, no PAUSE/STOP.
- Since the 14:36 entry: 0 wins, 0 losses. No new loss folders.
- Backlog 8: `tools/simulate_threats.py` can now play a build on the map's own geometry (`simulate(..., real_map=True)`, `map_model`), so the blimp check measures reach from real track cells instead of 2.5 x range; `ramp_calibration --offline --real-map` pairs per (strategy, mode, map). Easy and Medium show a trend (Medium 0.5-1x 32% lost vs 2x+ 9%), Hard still none, so the planner was not changed. Test `tests/test_simulate_real_map_offline.py`; check.py ALL OK.
- Next run: Medium-family p penalty for real-map ratio under 1x (backlog 8), or Sanctuary platforms (16 rest). Safe-mode forgiveness from ~2026-11-04 03:56.

## 2026-11-03 16:35
- Bot status: running (BTD6Bot task Running, bot.py run, recorder up, BTD6 responding), playing again since 16:01 (safe mode plays the normal medal order instead of idling, commit 93a2a66); now Infernal Double HP. No loops, no tracebacks, no PAUSE/STOP. Safe mode on (trips 4).
- Since the 15:45 entry: 2 wins (KartsNDarts Double HP, Chutes Double HP, 0 lives lost), 0 losses. No new loss folders.
- Roadmap "villages and alchemists beside the towers they buff": a buffer step with a researched `at` spot but no standing `near` towers ignored that spot (Castle Revenge Hard, Covered Garden Hard, Dark Castle). `_buff_spots` now tries the `at` spot first when it buffs at least one damage tower; tests in `tests/test_spot_relaxing_offline.py`; all 61 check steps OK (run in parallel - check.py one by one now takes over 10 minutes). Roadmap item ticked.
- Next run: Medium-family p penalty for real-map ratio under 1x (backlog 8), or Sanctuary platforms (16 rest).

## 2026-11-03 17:47
- Bot status: running again (task Running, bot restarted 17:20, recorder up); now Quad Magic Only, round 77, 100 lives. Safe mode on (trips 4), "no confident game left", so it plays the normal medal order. **Owner: the bot logged that BTD6's Auto Start looks ON (Glacial Trail, 17:34). Please turn it off in the game's settings: with it on, the bot cannot hold a round to buy.**
- Since 16:35: 1 win (Underground Double HP), 4 losses: Infernal DHP r79, Cargo DHP r75 (missed by the bot, added to results.jsonl by hand), Cargo DHP r63 (picked again straight after the restart because the r75 loss was never recorded), Glacial Trail Medium r25.
- Stuck at 17:02-17:20: Cargo was lost while the bot was buying. It kept clicking on the DEFEAT card for 35 s (no Continue was bought), a click hit Home, and it then clicked the Legends page 430+ times. I stopped bot.py and the supervisor restarted it. Fix in 8fbe2f3: no clicks without the match HUD (Game.screen_ok), the defeat card is believed at any lives count, the Legends page is a named screen left by the back arrow, and unknown screens try the back arrow.
- Same commit, reinforce: no saving for a later round when earlier rounds already cost the lives left (Cargo saved $30k and lost), and in a crisis it buys the biggest margin gain when nothing passes the half-strength test (Infernal sat on $77k). New tests; all check steps pass.
- Glacial Trail: the ice-freeze mechanic is not modelled (backlog 18). Next run: watch the Double HP games for the new reinforce behaviour; backlog 18 or 8.

## 2026-11-03 18:27
- Bot status: running (task Running, bot.py restarted 18:13 by a code reload, recorder up, BTD6 responding); now opening Frozen Over. No loops, tracebacks, PAUSE or STOP. Safe mode on (trips 4), playing the normal medal order.
- Since 17:47: 4 wins (Quad Magic Only, Lost Crevasse ABR, Hedge ABR, End Of The Road ABR, 0 lives lost), 0 losses. No new loss folders.
- Backlog 18 (average part): the damage model now counts Glacial Trail's ice - every round there is rated at 80% of the build's strength (`dps_model.TOWER_FREEZE`, commit eda9c75), so the forecast and reinforce see the gap that lost the Medium game at round 25. Per-tower freeze phase still open.
- A developer session committed unfinished-game settling / blind crisis spending / sell-and-avoid (19e038f) while this run was checking; its test helper in `tests/test_useless_towers_offline.py` lacked the map model and failed - fixed in 913b431 (that commit's message describes the whole feature but it holds only the helper fix). All 64 check steps pass.
- Owner: please still check BTD6's Auto Start setting (logged ON at 17:34).

## 2026-11-03 19:33
- Bot status: running (task Running, bot.py up since 18:26, recorder up, BTD6 responding); Candy Falls ABR at round 80, 100 lives. No tracebacks, loops, PAUSE or STOP; no Auto Start warning since 17:34. Safe mode on (trips 4), playing the normal medal order.
- Since 18:27: 4 wins (Frozen Over, Carved, Winter Park, Skates ABR - and Candy Falls finishing), 0 losses, 0 lives lost. No new loss folders.
- Fixed (c06d9e9): village-discounted upgrade prices matched no price-table tier, so a bought tier was judged by cash (hidden by ABR income), the hotkey bought a second tier and the bot lost count (Skates: opener dart really 4-2-0, believed 0-0-0/2-0-0; source of most remaining "shows no price" lines and "could not select opener"). Prices now name a tier within the game data's deepest discount (15%). Tests added; all check steps pass.
- Backlog 18 (Glacial Trail per-tower freeze phase) left open: the freeze offset is not in the game-data copies, and guessing it would be hardcoding. Next run: watch "is really ... corrected" lines on village builds; backlog 8 or 13.

## 2026-11-03 20:50
- Bot status: running (task Running, bot.py up since 19:32, recorder up, BTD6 responding); Spring Spring ABR at round 25, 100 lives. No tracebacks, loops, PAUSE or STOP; no Auto Start warning. Safe mode on (trips 4, 12/64 wins to leave), playing the normal medal order.
- Since 19:33: 5 wins (Candy Falls, Polyphemus, Quarry, Quiet Street, Adora's Temple ABR, 0 lives lost), 0 losses. No new loss folders. Quarry had 10 sniper clicks refused in a row (logged as "more likely the game than the ground"); the game was still won.
- Backlog 13 (e577175): the build optimizer rated every Magic Only round from 22 unsafe because each tower kind only had its 8 best spots, all on the same stretch of track - after 13 Skywardens/Mermonkeys, no Druid/Alchemist/Wizard/Ninja could be placed, so Lead had no cheap answer. free_spot now looks further down the ranking; the Lead rounds on Cargo went from 0.06 to 0.24-1.4. Test added; check.py ALL OK. No optimized plans regenerated - the plan is still not safe enough to use as a ceiling (greedy opening, rounds 59/78). Next run: find what rounds 59/78 lack, or backlog 8.

## 2026-11-03 21:35
- Bot status: running (task Running, bot.py up since 19:32, recorder up, BTD6 responding); opening Rake ABR. No tracebacks, loops, PAUSE or STOP; no Auto Start warning. Safe mode on (trips 4), playing the normal medal order.
- Since 20:50: 4 wins (Spring Spring, Moon Landing, Downstream, Streambed ABR), 0 losses. No new loss folders.
- Spring Spring was a near-loss: 90 lives lost at round 79. Cause: the map reader turns a path's CurvedLineNodes child into one Bezier arc, so the bot's track crosses the islands instead of looping round them; reinforce bought 7 ninjas and 2 supers by that track and sold five unused ("not a single pop"). Same reader bug moves the track on 24 maps.
- Fix written and tested (Spring Spring/Infernal/Quad renders now match the game) but NOT applied: it makes hand-picked spots on Infernal, Quad, Sanctuary and Geared illegal (Geared's hero loses every legal cell). Reverted; patch + test saved in ~/.btd6bot_cache/pending/curved_child_paths/, steps in backlog item 19. Next run: finish item 19.

## 2026-11-03 22:32
- Bot status: OFF by the owner - STOP file present, supervisor's last line is exit code 3 at 21:30 (stopped while opening Rake ABR); task Ready, no bot.py or recorder, BTD6 not running. Left off as the owner set it; not restarted, STOP untouched.
- Since 21:35: no games finished (0 wins, 0 losses). No new loss folders. Safe mode on (trips 4, 17/64 wins to leave), normal medal order.
- Backlog 19 done (757aa6d): track paths with a CurvedLineNodes child are read as splines (geometry v8) - Spring Spring's island loops, Infernal's figure-eight, and Geared's track now goes round the gear instead of across it. Spots moved for the new lanes; Geared builds use Ezili at the gear hub (no Quincy cell stays in reach as the gear turns); Sanctuary Medium swaps two druids for snipers. check.py ALL OK.
- New backlog 20: Psi's reach reads as 0.0, not global (no legal cell on moving ground). Next run (once the owner turns the bot back on): watch the first Spring Spring / Infernal / Geared / Sanctuary games on the new tracks for refused or useless placements.
