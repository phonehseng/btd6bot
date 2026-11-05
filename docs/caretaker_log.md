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

## 2026-11-04 01:47
- Bot status: running again (owner turned it on ~00:38; task Running, bot.py + recorder up, BTD6 up). From 00:43 to 01:18 the bot sat paused at the main menu because the Claude app window covered the game; the caretaker minimized it and brought BTD6 forward, and play resumed (Rake ABR, round 79 at 01:43, 100 lives). Owner: please leave the Claude window minimized or off the game after turning the bot on. No tracebacks, loops, PAUSE or STOP; no Auto Start warning.
- Since the 22:32 entry: 1 win (KartsNDarts ABR, 0 lives lost), 0 losses. No new loss folders. Safe mode still on (trips 4), normal medal order.
- Backlog 20 done (3f7fe0b): Psi's range was read as 0, so on moving ground (Geared, Sanctuary) it had no legal cell; reach_units now asks the game model's global_range flag first. Test added to tests/test_map_mechanics_offline.py.
- tools/check.py now runs its 65 steps in parallel (half the cores): ALL OK in 2.5 min instead of >10 min, which no longer fits one bounded command.
- Not committed: ~250 regenerated runtime files (data/map_fit.json + data/maps/*.npz refit to geometry v8, strategies/optimized, data/accounts) - left as the bot wrote them. Next run: watch the first Spring Spring / Infernal / Geared / Sanctuary games on the v8 tracks.

## 2026-11-04 02:30
- Bot status: running (task Running, bot.py + recorder up, BTD6 up; Spice Islands ABR round 45, 100 lives at 02:28). No tracebacks, loops, PAUSE or STOP; no new Auto Start warning (last one 2026-11-03 17:34). The bot reloaded the fixes below at 02:23 between games.
- Since 01:47: 3 wins (Balance, Sulfur Springs, Cracked ABR, 0 lives lost), 1 loss (Ancient Portal ABR, round 23, 78 lives). Safe mode on (trips 4, streak 1), normal medal order; Ancient Portal ABR benched 12 h by the bot.
- Loss diagnosed (case 20261104_015822_AncientPortal_abr, handled): the map's restore-a-bought-switch trigger counted as automatic, so the bot thought bloons use the walled left spiral and put both ninjas + the alchemist there; no bloon came. Fixed in a348100 (trigger is player-only, RULES_VERSION 2, map_fit re-measured, map_mechanics.json regenerated, test added).
- Also fixed (0c99f1a): Ninja path 1 tiers 1 and 2 both cost $380 on Hard, so a successful click looked like no effect and the hotkey bought a second tier; equal-priced tiers are now judged by the cash drop. check.py ALL OK both times.
- Next run: watch the next Ancient Portal game (after the 12 h bench) for ninjas on the top spiral / right lane.

## 2026-11-04 03:23
- Bot status: running (task Running, bot.py up since 02:35, recorder up, BTD6 responding); Haunted ABR round 79, 100 lives. No tracebacks, PAUSE or STOP.
- OWNER: BTD6's Auto Start looks ON again - the bot logged "the Play button was never idle in 39 rounds" at the end of Water Park ABR (03:11). The bot cannot hold a round to buy while it is on; please turn Auto Start off in the game's settings.
- Since 02:30: 2 wins (Spice Islands, Luminous Cove ABR), 2 losses (Bazaar ABR round 75, Water Park ABR round 61; both benched 12 h). Safe mode on (trips 4), normal medal order.
- Water Park (handled): reinforce picked an already given-up "another sniper" ~60 times in 3 min (each try skipped at once) while the defence was rated 0.06-0.15, so nothing else was bought. Fixed in 3608ff4: Executor.place_held_back, reinforce skips such placements; tests added; check.py ALL OK.
- Bazaar (handled, not fixed): no purchase left to offer from round 70 ("0 purchases tried", $3-8.7k idle), with no spot for the board's tower kinds or the plan's village/supers. Backlog 21 for the next run.

## 2026-11-04 04:26
- Bot status: running (task Running, bot.py up, recorder up, BTD6 up since 00:38); opening Dark Path. No tracebacks, loops, PAUSE or STOP.
- OWNER: BTD6's Auto Start still looks ON - logged again at 04:23 ("Play button never idle in 21 rounds"). Please turn it off in the game's settings; the bot cannot hold a round to buy while it is on.
- Since 03:23: 4 wins (Haunted, Encrypted - 86 lives lost, Chutes - 16 lost, Off The Coast, Another Brick ABR), 2 losses (Firing Range ABR round 25, X Factor ABR round 43). Safe mode on (trips 4), normal medal order.
- Firing Range (handled): the fast-track opener dart (0-0-0) on the right lane counted as full cover, so the second ninja, alchemist and village all went to the left lane of the split map; the right lane leaked 74 lives. Fixed in aac2c77: cover is weighted by the cash in each tower, and on split-path maps by how well each lane is defended (mapgeom.path_masks, Executor._lane_cover); test added; check.py ALL OK. Backlog 22 (segment with no reachable spot) filed.
- X Factor ABR (04:23): 100 lives at round 43, defeat 10 s later, rounds 22-43 in under 4 min with Auto Start on; its case folder was not written yet at 04:26 - next run: diagnose it (likely a MOAB-class leak with rounds stacking).

## 2026-11-04 05:27
- Bot status: running (task Running, bot.py + recorder up, BTD6 up since 00:38); Mushroom Grotto ABR round 28, 100 lives. No tracebacks, loops, PAUSE or STOP.
- OWNER: BTD6's Auto Start is still ON (logged again at 04:59 and 04:23). Please turn it off in the game's settings.
- Since 04:26: 2 wins (Enchanted Glade, Castle Revenge ABR), 5 losses (Dark Path ABR r75, Muddy Puddles Magic Only r40, Dark Castle ABR r40, Peninsula ABR r23, Sunset Gulch ABR r40 at 05:21 - its case folder was not written yet). Safe mode on (trips 4), normal medal order.
- Root cause found from Peninsula (handled): track_weight added the land scan's thin blocked strips as guessed track even on maps with game geometry - on most of the 91 mapped maps this phantom track was as large as the real one or larger (Dark Path 7,323 cells vs 1,474), so towers were placed to cover scenery and cover ratings were inflated. Fixed in 18c4157 (geometry paths only on mapped maps; test added; check.py ALL OK). Dark Castle, X Factor, Dark Path, Muddy Puddles diagnosed and handled; idle cash before weak rounds filed as backlog 23.
- Next run: diagnose Sunset Gulch (old code), and watch whether placements and the late-ABR losses improve now that the bot has reloaded the track fix.

## 2026-11-04 06:25
- Bot status: running (task Running, bot.py up since 05:21, recorder up, BTD6 up since 00:38); opening #Ouch. No loops, PAUSE or STOP. One handled game-loop error at 05:34 (Sanctuary ABR: no defence could be placed on its moving ground, so the bot refused to start the round - safe).
- OWNER: BTD6's Auto Start is still ON (logged again at 05:20 and 05:31). Please turn it off in the game's settings.
- Since 05:27: 2 wins (Cornfield, Underground ABR, 0 lives lost), 5 losses (Mushroom Grotto r63, Erosion r22, Ravine r40 + one abandoned, High Finance r51, Spillway r40 at 06:23 - case folder not written yet). Safe mode on (trips 4), normal medal order.
- Root cause of the "0 purchases tried with $30k+ idle" losses (High Finance, Mushroom Grotto; handled): obstacles were measured by name - High Finance's eleven "Removable"s all resolved to one strip that frees nothing - and deleted ("uncovered") obstacles were skipped, so neither map ever cleared room (36 / 165 legal ninja cells). Fixed in b1a4bd6 (by id, deleted obstacles count; test added; check.py ALL OK).
- Sunset Gulch and Ravine handled as backlog 23 (idle cash before a weak round, still open); Erosion filed as backlog 24 (only 608 cells last a long game). Next run: Spillway case, and watch the next High Finance / Mushroom Grotto games for "clearing obstacle" lines.

## 2026-11-04 07:38
- Bot status: running (task Running, bot.py up since 06:24, recorder up, BTD6 up since 00:38); Ravine Reverse round 50, 150 lives. No tracebacks, loops, PAUSE or STOP.
- OWNER: BTD6's Auto Start is still ON (logged again at 06:23 and 07:12). Please turn it off in the game's settings.
- Since 06:25: 7 wins (#Ouch Medium/Military/Reverse, Quad Medium/Military, Ravine Medium/Military), 1 loss (Quad Reverse r56). Safe mode on (trips 4), normal medal order.
- Spillway ABR (handled): round 40's MOAB was called short 3 rounds ahead, the plan's Maim MOAB was the answer, but idle spending and reinforcing ate its cash. Cash is now kept for a plan blimp step payable in time, and reinforcing respects the hold (7a3f427, test added).
- Quad Reverse (handled): $18.8k idle waiting on a $20k Apache before weak rounds (backlog 23). Safety: after both defeats the bot kept clicking on the Defeat screen (once it opened Restart, next to the Monkey-Money Continue). Failed selections now make it check the screen (9edd14e); the HUD check still passes on Defeat (backlog 25). check.py ALL OK.
## 2026-11-04 08:35
- Bot status: running (task Running, bot.py up since 07:39, recorder up, BTD6 up since 00:38); next game being set up (equipping Admiral Brickell). No tracebacks, loops, PAUSE or STOP.
- OWNER: BTD6's Auto Start is still ON (last logged 07:12). Please turn it off in the game's settings.
- Since 07:38: 5 wins (Ravine Reverse, Muddy Puddles Medium/Military/Reverse, Dark Dungeons Medium), 1 loss (Dark Dungeons Military Only r55). Safe mode on (trips 4), normal medal order.
- Fixed backlog 25's last part: the click guard passed on the Defeat card (its dimmed Play button still matched by shape). It now also wants the button lit (0e9736f, test added, check.py ALL OK).
- Dark Dungeons Military (handled; losses.py had not filed it after 5 min, filed by hand): military_heli_sniper's heli step died after 3 helis and the cash went into 15 bunched sniper 2-2-0s; round 55's ceramics leaked at the bare exit. Same build and rounds as Quad Reverse - filed as backlog 26 for the next run.

## 2026-11-04 09:50
- Bot status: running (task Running, bot.py reloaded with the fixes, recorder up, BTD6 up since 00:38); Cornfield Primary Only round 19, 200 lives. No tracebacks, loops, PAUSE or STOP.
- OWNER: BTD6's Auto Start is still ON (logged again at 09:01 on Spillway). Please turn it off in the game's settings.
- Since 08:35: 3 wins (Flooded Valley Medium, Bloody Puddles Medium/Reverse), 5 losses (Flooded Valley Military r36, Bloody Puddles Military r51, Spillway Medium r40, Geared ABR r27, Workshop Medium r36). Safe mode on (trips 4).
- The bot was IDLE from 09:07 (every game over its bar benched or lost; best p=0.74 vs 0.75). Fixed in 80f33a4: the runner now plays the surest open medal under every bar (tier LAST) rather than idling.
- Spillway Medium (handled): MOAB leaked with $7,519 banked while the plan kept retrying refused heli spots. Fixed in 77bc3bb (round before blimps: a stuck plan gives way to blimp damage; test added; check.py ALL OK). Flooded Valley grouped into backlog 26; Geared (0 legal cells) filed as backlog 27; Workshop and Bloody Puddles sudden deaths as backlog 28.

## 2026-11-04 10:25
- Bot status: running (task Running, bot.py up since 09:38, recorder up, BTD6 up since 00:38); Sulfur Springs Double HP round 74, 100 lives. No tracebacks, loops, PAUSE or STOP; no new loss cases.
- OWNER: BTD6's Auto Start is still ON (logged again at 09:50). Please turn it off in the game's settings.
- Since 09:50: 4 wins (Cornfield, Muddy Puddles, Bloody Puddles Primary Only; Sulfur Springs Magic Only), 0 losses. Safe mode on (trips 4); the bot keeps playing.
- Backlog 26 (heli-sniper on tight maps), two causes fixed in 1b919af: a stale "spot" reason from a refused heli set the next round-gated step aside, and reinforce bought s1 1-3-0, shutting out its planned 4-2-0 Maim MOAB. Tests added, check.py ALL OK. Still open: the fill's choice once the heli step dies.

## 2026-11-04 11:35
- Bot status: running (task Running, bot.py restarted 11:26, recorder and BTD6 up); Alpine Run Impoppable round ~45. Safe mode on (trips 4); the bot keeps playing (last-resort picks).
- OWNER: BTD6's Auto Start is still ON (logged in both Magic Only losses). Please turn it off in the game's settings.
- Since 10:25: 5 wins (Sulfur Springs Double HP; X Factor, Castle Revenge Primary Only; #Ouch Deflation; Alpine Run Impoppable at 11:17), 4 losses (Bloody Puddles and Workshop Magic Only; Erosion and Sunken Columns Easy Primary Only). All four cases handled.
- Erosion fixed in 705cbe1: its six paths take 18 rounds each, but all six were painted as track, so the build stood beside lanes no bloon takes before round 37. The track is now repainted for the round's path phase (test added). Sunken Columns placement (backlog 29) and the Magic Only build's missing MOAB answer (backlog 30) filed.
- Loop fixed in d4c8af3: after the Alpine Run Impoppable win, the match loop read an INSTA MONKEY! card 400 times without clicking. Restarted bot.py at 11:26, which cleared it. The restart did not credit the win ('Victory screen of an unfinished' never logged, although logs/game_in_progress.json should have held the game), so the bot is replaying Alpine Run Impoppable now. Next run: find out why _credit_unfinished_win missed it.

## 2026-11-04 12:25
- Bot status: running (task Running, bot.py up since 11:27, recorder and BTD6 up); Hedge Impoppable round 50. No tracebacks, loops, PAUSE or STOP; no new loss cases. Safe mode on (trips 4); the bot keeps playing (last-resort picks).
- OWNER: BTD6's Auto Start is still ON (logged again at 11:44 on Alpine Run). Please turn it off in the game's settings.
- Since 11:35: 3 wins, 0 losses (Alpine Run Impoppable 11:44, which replayed the 11:17 win; Off The Coast and Park Path Impoppable).
- Why the 11:17 Alpine Run win was not credited: test_between_games_offline called bot._game_done() without a temp GAME_FILE, so every check.py run deleted the live logs/game_in_progress.json. The 11:25 check ran mid-game; the restarted bot found no game to credit and replayed the map. Fixed in a3cde7d (the test uses temp files; check.py ALL OK).
- A developer session was editing runner/status/hud at 12:18 without logs/dev_active.txt (committed 6d9fb4a, the HUD level readout). I only committed the test, and skipped development this run.

## 2026-11-04 13:25
- Bot status: running (task Running, bot.py up since 12:33, recorder and BTD6 up); Carved Impoppable round 91 with $7,680. No tracebacks, loops, PAUSE or STOP; no new loss cases. Safe mode on (trips 4); the bot keeps playing.
- Since 12:25: 2 wins, 0 losses (Hedge Impoppable is now credited; End Of The Road and Frozen Over Impoppable). On Carved the damage model rated rounds 76-78 at 0.45-0.58 while the bot reinforced; check the result next run.
- Backlog 29 fixed in f7b4a33 (Sunken Columns Primary Only loss): the column tops are sight blockers typed as land, and every blocker was treated as solid. No tower could stand on them, and from the pit the columns hid the track. Raised blocker ground is now placeable, and towers there see over blockers no higher than their ground (placement + damage model, new test). Also affects Mesa, Adora's Temple, Skull Tweak, Lotus Island and Frozen Over: watch for 'invalid for' refusals on those maps' raised ground.
- OWNER: Auto Start was last logged ON at 11:44 (see the 12:25 entry).
## 2026-11-04 14:25
- Bot status: running (task Running, bot.py up since 13:29, recorder and BTD6 up); opening Polyphemus. No tracebacks, loops, PAUSE or STOP; no new loss cases. Safe mode on (trips 4, 10/64 wins to leave); the bot keeps playing.
- OWNER: BTD6's Auto Start is still ON (logged again at 13:46 on Candy Falls). Please turn it off in the game's settings.
- Since 13:25: 4 wins, 0 losses (Carved, Winter Park, Candy Falls, Lost Crevasse Impoppable, all with no lives lost).
- Lost Crevasse round 78 was rated 0.29 for ten rounds but passed easily, and reinforce spent ~$25k on supers that moved it 0.00-0.02. New tools/rate_board.py (24a033b) rebuilds a board from bot.log and rates it; --drop pinned the rating on the 72-camo-ceramic burst (the model leaves out Obyn's brambles and the alchemist's brews). Filed as backlog 31; check.py ALL OK.

## 2026-11-04 15:35
- Bot status: running (task Running, bot.py up since 13:29, recorder and BTD6 up); Adora's Temple Impoppable round 60. No tracebacks, loops, PAUSE or STOP. Safe mode on (trips 4); the bot keeps playing.
- OWNER: BTD6's Auto Start is still ON (last logged 13:46). Please turn it off in the game's settings.
- Since 14:25: 1 win, 2 losses (Quarry Impoppable won; Polyphemus and Quiet Street Impoppable lost on round 98, both chimps_ninja_sun). Both cases handled.
- Polyphemus fixed in 22f21c8: upgrade buttons near a full discount village read 17% under the price table (719 logged reads), and the tier matcher allowed only 15%, so tier drift was never corrected. A misjudged purchase closed Sun Avatar on s1 (2-0-3), and the MIB village stayed 0-0-0 in the bot's count. deepest_discount() now adds the unlisted 2% (test added, check.py ALL OK). It goes live after the current game.
- Quiet Street was a build ceiling, not drift: round 98 was rated 0.09 from round 88 on a 575-unit track, and reinforce spent on purchases worth +0.01 each. Filed as backlog 31a (Sun Avatar rating in the damage model, more MOAB damage before round 95 on short maps).

## 2026-11-04 16:23
- Bot status: running (task Running, bot.py up since 15:37, recorder and BTD6 up); Another Brick Impoppable past round 45. No tracebacks, loops, PAUSE or STOP. Safe mode on (trips 4); the bot keeps playing.
- OWNER: BTD6's Auto Start is still ON (logged again at 15:41 on Spring Spring; rounds 38-40 passed in seconds). Please turn it off in the game's settings.
- Since 15:35: 3 wins, 1 loss (Adora's Temple, KartsNDarts, Moon Landing Impoppable won with no lives lost; Spring Spring Impoppable lost on round 40, handled).
- Spring Spring fixed in 598973a: round 40's MOAB was rated 0.5x from round 37, but the plan's next step (ninja 2-0-4, no blimp damage) was not stuck, so it kept its turn and saved $5,672 while the MOAB took the only life. With one life the blimp check now looks 5 rounds ahead and buys blimp damage from two rounds before (test added, check.py ALL OK). Also seen: reinforce paid $3,000 for v1 4-0-2 rated 0.29 -> 0.29 (backlog 31a).

## 2026-11-04 17:30
- Bot status: running (task Running, bot.py up since 16:29, recorder and BTD6 up); next game starting after Rake. No tracebacks, loops, PAUSE or STOP. Safe mode on (trips 4); the bot keeps playing.
- OWNER: BTD6's Auto Start is still ON (logged again at 16:13). Please turn it off in the game's settings.
- Since 16:23: 4 wins, 0 losses (Another Brick, Downstream, Streambed, Rake Impoppable, no lives lost; Rake came through round 100 on 1 life). No new loss cases.
- Fixed in 32df810: on Rake the upgrade check bought two tiers per click four times (ninjas 0-0-1 -> 2-0-1, ninja1 2-0-1 -> 4-0-1). Ninja path 1 costs the same for tiers 1 and 2, and round income hid the cash drop, so "cash did not drop" was read as a missed click and the hotkey bought the next tier too. That reading now counts as unknown unless the button also kept a price it could have changed; a button showing any later tier proves the purchase (2 tests, check.py ALL OK). Live after the current game.

## 2026-11-04 18:35
- Bot status: running (task Running, bot.py up since 17:36, recorder and BTD6 up); opening Haunted after Encrypted. No tracebacks, loops, PAUSE or STOP. Safe mode on (trips 4); the bot keeps playing.
- OWNER: BTD6's Auto Start is still ON (logged at 17:35 Balance and 18:25 Encrypted). Please turn it off in the game's settings - with one Impoppable life the bot cannot hold rounds to buy.
- Since 17:30: 1 win, 4 losses (Cracked Impoppable won; Balance r98, Spice Islands r98, Castle Revenge r78, Encrypted r40 Impoppable lost). Balance, Spice Islands and Castle Revenge handled; Encrypted's case folder was not filed yet - next run: blimp check said 0.3x short at round 35, yet $1,920 went on four ninjas, and the ace answer was refused 20 times at rounds 38-39.
- Fixed in c16f23a: Spice Islands banked $161,626 with "0 purchases tried" from round 63 (no land spot left, every tower maxed); in a crisis reinforce now also offers tower kinds not on the board (water/air), rated at the crosspath the bank could grow them into (2 tests, check.py ALL OK). Balance and Castle Revenge filed under backlog 31a (short-track round 78-98 MOAB damage; reinforce spending +0.00 purchases while the plan's Sun Avatar waits).
## 2026-11-04 19:25
- Bot status: running (task Running, bot.py up since 18:21, recorder and BTD6 up); Chutes Impoppable round 74 on 1 life. No tracebacks, loops, PAUSE or STOP. Safe mode on (trips 4); the bot keeps playing.
- OWNER: BTD6's Auto Start is still ON (logged at 18:25 Encrypted and 18:41 Enchanted Glade). Please turn it off in the game's settings - with one Impoppable life the bot cannot hold rounds to buy.
- Since 18:35: 2 wins, 2 losses (Underground and Haunted Impoppable won, no lives lost; Haunted Half Cash r76 and Enchanted Glade Impoppable r47 lost). All three open cases (with Encrypted) handled.
- Fixed in 340eed2 (Encrypted r40): after a refused placement click the held tower's preview stuck on that spot while the cursor moved on, so 20 ace clicks hit one bad spot and no blimp damage came before the round-40 MOAB. place() now picks the tower up again after each refused click (test added).
- Fixed in 094f8de (Haunted Half Cash, Castle Revenge; backlog 31a c): reinforce no longer buys purchases that lift the weakest round under 0.01 while the plan's next step (a Sun Avatar) waits for cash. Enchanted Glade's "ninja: none in reach of the track" give-up filed as backlog 31b. check.py ALL OK; both go live after the current game.## 2026-11-04 20:55
- Bot status: running (task Running, bot.py up since 19:31, recorder and BTD6 up); opening Muddy Puddles after Workshop. No new tracebacks, loops, PAUSE or STOP. Safe mode on (trips 4): no confident game left, so the bot plays last-resort games (it never idles).
- OWNER: BTD6's Auto Start is still ON (logged again at 20:25 Workshop). Please turn it off in the game's settings.
- Since 19:25: 4 wins, 4 losses (Midnight Mansion and Mesa Easy, Sulfur Springs Impoppable, X Factor Deflation won; Chutes Impoppable r96, Midnight Mansion Primary Only r40, Muddy Puddles ABR r23, Workshop Primary Only r40 lost). The first three are handled; Workshop (0 lives counted, lost at r40) is not filed yet - next run.
- Fixed in 3fb24e6 (Muddy Puddles ABR): the planner calibrated each mode with one factor over all maps, hiding that ABR goes 9/10 on beginner maps but 0/4 on expert ones; it now calibrates per map category, so expert ABR last-resort picks drop from ~0.5-0.73 to 0.27-0.42.
- Fixed in 762f174 (Midnight Mansion Primary Only): with every cheap camo answer unplaceable, the bot froze $4,248 "saving" for a $27,625 Boomerang tier 5; an answer the income cannot pay by its round no longer holds the cash. Chutes' "saving for bad answer" during crisis rounds 94-95 filed as backlog 31c. check.py ALL OK; both go live after the current game.

## 2026-11-04 21:45
- Bot status: running (task Running, bot.py up since 20:26, recorder and BTD6 up); now: Ravine easy - round 35, $807, 200 lives. No PAUSE or STOP, no loops. Safe mode on (trips 4); last-resort games keep it playing.
- OWNER: BTD6's Auto Start is still ON (logged again at 20:32 and 20:42). Please turn it off in the game's settings.
- Since 20:55: 3 wins, 3 losses (Cornfield Deflation, Ancient Portal Double HP, Bloody Puddles Military Only won; Muddy Puddles Deflation r54, Last Resort Primary Only r20, Bloonarius Prime ABR r40 lost). Mesa Primary Only twice refused to start ("no defence could be placed", cash read 51) and is benched 6 h. All four open cases (with Workshop) are handled.
- Fixed in d73d866 (Workshop, Muddy Puddles, Last Resort): the map-ceiling cap (p 0.5 where no researched build holds) was applied before the per-category calibration, which lifted these last-resort picks back to p 0.69-0.72. The cap now holds after calibration and scales with the ceiling. The next last-resort pick is Ravine Easy (ceiling 2.99), now live.
- Bloonarius Prime ABR (round-40 rainbow/ceramic rush rated 1.00, reinforce aimed at round 47) filed as backlog 31d. check.py ALL OK.

## 2026-11-04 22:30
- Bot status: running (task Running, bot.py up since 21:23, recorder and BTD6 up); now reading upgrade trees between games after Pat's Pond Magic Only. No tracebacks, loops, PAUSE or STOP. Safe mode on (trips 4), and the bot keeps playing.
- OWNER: BTD6's Auto Start is still ON (logged again at 22:02 Party Parade). Please turn it off in the game's settings.
- Since 21:45: 3 wins, 3 losses (Lotus Island ABR, Pat's Pond Hard, Pat's Pond Magic Only won; Ravine Deflation r52, Flooded Valley Military Only r30, Party Parade Medium r31 lost). All three are handled.
- Fixed in e345f74 (Party Parade): the lane-cover grid counted the hero as the strongest tower, so Quincy in the left lane made it look defended and every bomb went right. The hero now counts at its price. Also in e345f74 (Flooded Valley): the only lead and camo popper (a 3-2-0 sniper) was sold for "no pops" one round before the leads. A tower that alone answers a bloon property is now kept.
- Fixed in c3bd57d (Ravine Deflation): calibration lifted a general build over the 0.76 no-income cap to p=0.93. The cap now holds after calibration. check.py ALL OK; all three fixes go live after the current game.

## 2026-11-04 23:25
- Bot status: running (task Running, bot.py up since 22:27, recorder and BTD6 up); now: Infernal Reverse - round 32, 150 lives. No tracebacks, loops, PAUSE or STOP; no Auto Start warning this hour. Safe mode on (trips 4), and the bot keeps playing.
- Since 22:30: 4 wins, 3 losses (Pat's Pond Double HP, High Finance Primary Only, Infernal Medium and Military Only won; Pat's Pond ABR r40, Sulfur Springs Half Cash r27, High Finance Deflation r34 lost). All three are handled.
- Fixed in 2edb32e (High Finance): the map's "BUILD FOR $1,500" lot box was not recognised (only "Remove FOR"), was left open, taken for a purchase screen, and the game ran on with $12,120 unspent. It is read now, and any leftover obstacle box is closed with its red X.
- Fixed in 2edb32e (Sulfur Springs): Fast Track starts Half Cash at round 22 with $4,420; the planner now halves the win chance of half-cash games with Fast Track on. Idea for later: switch Fast Track off on map select for Half Cash (needs a live test of the toggle).
- Pat's Pond ABR: untested build picked at p=0.71; the blimp ramp's fixed 3-round lead is filed as backlog 31d (c). check.py ALL OK.

## 2026-11-05 00:30
- Bot status: running (task Running, bot.py up since 23:21, recorder and BTD6 up); now: Cornfield Reverse. No tracebacks, loops, PAUSE or STOP. Safe mode on (trips 4), and the bot keeps playing (one last-resort pick at 23:27 rather than idling).
- OWNER: BTD6's Auto Start is still ON (auto_start: true in the 23:20 result). Please turn it off in the game's settings.
- Since 23:25: 5 wins, 2 losses (Flooded Valley Reverse, Dark Dungeons Reverse, Dark Path Deflation, Cornfield Medium and Military Only won; Infernal Reverse r47, Infernal ABR r27 lost). Both handled.
- Fixed in b0d2964 (Infernal Reverse): solo_dartling's Deflation record (13 of 18) lifted it to p=0.88 in Reverse, a mode it never played; its one income game was lost too. Calibration is now pooled per economy, and a no-income record can only lower an income mode. check.py ALL OK.
- Infernal ABR: last-resort pick (p=0.60) at a Fast Track round-22 start; dense round 27 leaked 100 lives in seconds. No code change - same Fast Track issue as backlog 31d.

## 2026-11-05 01:40
- Bot status: task Running, bot.py up since 01:24 (reload after the owner's NEXT-file commits), recorder and BTD6 up. Parked at the main menu since 01:32 by a PAUSE file reading "parked to turn off Auto Start" - the owner's doing minutes before this run, so it was left in place; the owner also played Alpine Run CHIMPS through the NEXT file. No tracebacks, loops or STOP. Safe mode on (trips 4).
- OWNER: BTD6's Auto Start was still ON at 01:00 (Bazaar) and 01:32 (Alpine Run). Please turn it off in the game's settings, then remove the PAUSE file (tools/bot_on.ps1).
- Since 00:30: 5 wins, 3 losses (Cornfield Reverse, Quad Reverse, Bazaar Medium and Military Only, Cornfield Magic Only won; Quad Deflation r54, Bazaar Reverse r51, Alpine Run CHIMPS r43 lost). Quad and Bazaar are handled; Alpine Run (the owner's pick, one life) is noted below for the next run if its case folder is not there yet.
- Fixed in 1c8488a (Bazaar Reverse): solo_bomb was played at p=0.93 on its Primary Only record although the generated solo builds had lost all six Medium-family income games; those builds now calibrate as one family per kind of game (p there 0.30). (Quad Deflation): surplus bought a $21,600 Crossbow Master between opening plan steps and the fill's bombs, snipers and spikes were never afforded; no-income openings now follow the plan and fill to the end. (Cornfield Magic Only, won anyway): ten obstacle removals were paid for and none counted because the round's income hid the price; a removal is now proved by the obstacle being gone. tools/check.py was red since d37f06d (the safe-mode test's stand-in runner lacked owners_pick) - fixed in the same commit, ALL OK.
- Alpine Run CHIMPS: reinforce bought five bare ninjas at +0.02-0.03 each while rounds 43-50 rated 0.28-0.52 and the plan's n1 4-0-2, a1 3-2-0 and village waited (backlog 31a c: the 0.01 bar lets these through); round 43 took the one life. Backlog 32 (lives reads fail while lives drain - Bazaar read 4 for 132) and 33 (why the Deflation pre-Play check keeps its ten-round horizon: 17 of 22 won games dip under 0.8 later) filed.

## 2026-11-05 02:40
- Bot status: task Running, bot.py up since 01:42, recorder and BTD6 up; the owner was at the machine 01:53-02:16 (HUD stop, another window in front), the PAUSE file is gone and the bot plays again. No tracebacks, loops or STOP. Safe mode on (trips 4, streak 1); every open medal is under its bar, so only last-resort picks at p 0.50-0.53 are left (Dark Path Double HP benched 2h at 02:01: its start was interrupted by the owner's window).
- OWNER: Auto Start: the Mushroom Grotto game (02:19-02:34, 65 rounds) raised no 'looks ON' warning, so it seems OFF now - thank you. Last ON reading 01:32.
- Since 01:40: 1 win, 1 loss (Mushroom Grotto Magic Only won r80; Glacial Trail Medium lost r16, handled).
- Fixed in 73dc950 (Glacial Trail Medium): no legal cell reached the track for any ranged tower after the dart opener (learned refusals on the few near-track cells), and pick_spots offered blind cells anyway - five towers stood 35-47 cells from the track. Such steps now get no spot, are set aside and count as placement trouble for the planner (tests/test_blind_spot_offline.py). Glacial Trail's refusal layer reset. Backlog 34: its geometry marks only 389 land cells near the track although towers have stood on the bottom-left ice; refusal layers cover 20-48% of near-track land on 25 maps and should expire. check.py ALL OK.

## 2026-11-05 03:30
- Bot status: task Running, bot.py up since 02:34, recorder and BTD6 up; now: Ancient Portal Impoppable (round 41, 1 life - a last-resort pick). No tracebacks, loops, PAUSE or STOP. Safe mode on (trips 4); every open medal is under its bar, so the planner plays last resorts at p 0.48-0.50 and loses about half of them.
- OWNER: Auto Start is ON again - `auto_start: True` at 02:40 (Mushroom Grotto) and 03:02 (Quad); the 02:40 entry's "seems OFF" was wrong. Please turn it off in the game's settings: the bot cannot hold a round to buy while it is on.
- Since 02:40: 2 wins, 3 losses (Cracked Magic Only, Ancient Portal ABR won; Mushroom Grotto Double HP r40, Quad ABR r63, Sanctuary Medium r53 lost). All three diagnosed (diagnosis.md in their case folders, reports still "new"), none fixed: another developer session merged the CHIMPS workflow branches at 03:24 (2c78454) and was running check.py during this run, so no code was edited (no dev_active.txt, but the merge speaks for itself). Next run: code the three fixes below.
- Mushroom Grotto Double HP: round 40's MOAB passed the blimp check at 1.1x (bar RAMP_OK 1.0), surplus spent the Maim MOAB sniper's cash on alch 4-2-0 and a 3-0-0 sniper, and the MOAB leaked all 100 lives at once (lives_lost 0 in the result: the HUD never showed the drop). Proposed: round_blimp_load returns the lives a leak costs (bloons.json rbe) and the executor uses a higher bar (1.4) when that is at least the mode's lives - a blimp round is pass/fail - so the plan's blimp step gets plan_hold.
- Sanctuary Medium: military_sub_sniper_water lists Sanctuary, but no sub fits its fountain basin (92 water cells, footprint 3.6 cells, deepest water cell 3.0 cells from the edge; map fit sub 0.0): all 10 sub steps given up, snipers only, $11-33k idle with "0 purchases tried". Proposed: _strategy_fits rejects a build whose water-only dps kind has map fit 0.0 (that also takes the water builds off Ship Capture - verify its fit against the stills first).
- Quad ABR: last resort p=0.50 at a Fast Track start, rounds 27-36 rated 0.26-0.30 from round 23 (80 lives lost at round 36); round 63 rated 0.44 with $17-20k idle because the $16,090 Elite Defender upgrade failed three times on an unread upgrade panel (`panel [(None, None) x3]`, 183 such lines in the log history) while the cash was kept for a $35,100 plan step that could never arrive in time. Backlog candidates: the unread panel on crowded boards, and "cash stays for plan step" only when the step is payable before the rated round.

## 2026-11-05 04:17
- Bot status: task Running, bot.py up since 03:24, recorder and BTD6 up. Found parked at the main menu by a PAUSE file from 03:39 ("investigating the Ancient Portal Impoppable loss before the CHIMPS run", written by the other developer session, which also left a NEXT.held with End Of The Road / chimps); no logs/dev_active.txt and no file edited since 03:29, so per the rules the PAUSE was removed at 04:21 and the bot played again from 04:22 (Dark Path Double HP won, now Bazaar ABR). Other session: touch logs/dev_active.txt while you work, or the hourly run lifts a PAUSE. No tracebacks, loops or STOP. Safe mode on (trips 4, streak 0).
- OWNER: Auto Start - no "looks ON" warning since 03:02; the two games since read auto_start null (undecided). Last ON reading 03:02 (Quad).
- Since 03:30: 1 win, 1 loss (Dark Path Double HP won r80; Ancient Portal Impoppable lost r94, a p=0.50 last resort). All four open cases but Sanctuary are handled.
- Fixed in 7919935 (Ancient Portal, Quad ABR): reinforce let any purchase lifting the weakest round by 0.01 spend the cash saved for a plan step - at round 88 a $30,000 Super Monkey tier worth +0.03 ate the $27,284 saved toward Perma-Spike, which the model rates +0.19 on round 94 and +0.28 on round 95; the game was lost at round 94 with $17,562 idle. A waiting plan step now keeps its claim only if income can pay it before the weak round and the model rates it at least as high as the competing purchase (the Quad case: a $35,100 Glaive Lord no income could reach held $10-20k from the Elite Defender).
- Fixed in 817e2c2 (Mushroom Grotto Double HP): the blimp check passed round 40's MOAB at 1.1x (bar 1.0) and the MOAB took all 100 lives; round_blimp_load now returns the lives a leak costs and Executor.ramp_bar wants 1.4x when that reaches the mode's lives (every MOAB round in every mode), so the plan's blimp step keeps its cash. check.py ALL OK after both.
- Backlog 35 (unread upgrade panel on crowded boards, 183 occurrences) and 36 (water builds offered where no sub fits; Sanctuary's case stays "new" with its diagnosis until the planner gate is coded next run).

## 2026-11-05 05:17
- Bot status: task Running, bot.py up since 04:35, recorder and BTD6 up; now Ascent ABR (round 34, 100 lives). No tracebacks, loops, PAUSE or STOP; NEXT.held (End Of The Road / chimps, the other session's) still sits in the folder untracked. Safe mode on (trips 4, streak 3 wins).
- OWNER: Auto Start was ON again at 04:36 (Bazaar ABR: `auto_start: true`, "the Play button was never idle in 41 rounds"); the three Ascent games since read null. Please turn it off in the game's settings.
- Since 04:17: 4 wins, 1 loss (Dark Path Double HP, Ascent Hard, Magic Only and Double HP won r80; Bazaar ABR lost r63, a p=0.50 last resort). Both open cases are handled.
- Fixed in 17615e3 (Sanctuary Medium): `planner._strategy_fits` refuses a build whose water-only tower (sub, buccaneer) has a map fit of 0.0 from both ends of the track - Sanctuary's fountain basin cannot hold a sub, so the four-sub build gave up all ten sub steps and the snipers lost round 53 with $11-33k idle. Takes the three water builds off Sanctuary and Ship Capture (its water is still to be checked against stills). tests/test_water_fit_gate_offline.py; check.py ALL OK.
- Bazaar ABR diagnosed, not fixed: from round 54 the model rated round 63 at 0.12 with $11-21k idle, but reinforce rates "another ninja" as a bare $430 tower (+0.00) while $5,800 buys a Bloonjitsu; the plan's $21,600 Sun Avatar on su1 was rated +0.00 and su1 read no pops in 17 rounds although the map model gives its cell 63% of the best reach and clear line of sight. Backlog 37 (rate "another <standing kind>" grown, as new_kind_options does) and 38 (pop counter vs map model: Ascent's opener dart also reads 0 pops for 44 rounds) filed with the evidence.
- Left alone: 38 data/maps/*.npz the bot rewrites as it learns (uncommitted), 185 untracked strategies/optimized/*.yaml from 10-22..10-27 and data/accounts/SFYOSHHYV.* - another session's; not mine to commit.

## 2026-11-05 06:40
- Bot status: task Running, bot.py reloaded at 06:28 after this run's first commit, recorder and BTD6 up; now Castle Revenge Impoppable (round 33, a p=0.5 last resort). A "stopped from the HUD" pause showed at 06:28:25 right after the reload and cleared within minutes on its own. No tracebacks, loops, PAUSE or STOP. Safe mode on (trips 4, streak 7 wins).
- OWNER: Auto Start read ON again at 06:27 (Spice Islands Impoppable: `auto_start: true`). Please turn it off in the game's settings; the bot cannot hold a round to buy while it is on.
- Since 05:17: 4 wins, 0 losses (Ascent ABR r80, Ascent Impoppable r100, Covered Garden Primary Only, Spice Islands Impoppable r100 - its first, with 8 steps given up and up to $119k idle, see below). No open loss cases.
- Fixed in 90a0d95 (backlog 37, Bazaar ABR's cause): reinforce rated "another ninja" as a bare 0-0-0 tower (+0.00) while $5,800 bought a 4-0-2; `reinforce.grow` now rates every placement, standing kinds too, at the crosspath the bank grows it into, priced at the grown tower's full cost. On the Pat's Pond test board it now picks a grown sniper ($4,375 to 0-3-2) over a single tier.
- Fixed in 730b82e (backlog 35, one cause): the game allows one of each tier 5 on the map; after sb1's Pre-emptive Strike at round 88, sb2 and sub2 asked for the same 2-0-5 for ten rounds ("MAX UPGRADES" reads as a blank panel, rec_20261105_062500.mkv at 31-37 s) with $37k-119k idle on one life. `Executor._tier5_taken` keeps a taken tier 5 out of `_next_path` and `upgrade_choices`; the 46 strategy files ask no kind for the same tier 5 twice. Still open there: reading "MAX UPGRADES" from the button itself (the words sit above the price row). check.py ALL OK after both.

## 2026-11-05 07:35
- Bot status: task Running, bot.py up since 06:37, recorder and BTD6 up; Cargo ABR just won (07:32, r80, 47 lives), the bot picks its next game. No tracebacks, loops, PAUSE or STOP; NEXT.held still untracked. Safe mode on (trips 4, streak 2). Another developer session is committing on worktree branches fix/surplus-plan-step (07:15, the surplus/plan-step cash hold) and fix/reinforce-last-buy (06:34), neither merged; this run stayed out of reinforce.py, match.py and strategy.py.
- OWNER: no new Auto Start reading since 06:27 (ON at Spice Islands Impoppable); the four games since read null. Please turn it off in the game's settings.
- Since 06:40: 3 wins, 2 losses (Spice Islands Magic Only r80, Cargo Double HP r80, Cargo ABR r80 won; Castle Revenge Impoppable lost r33 after 2 minutes, Dark Dungeons Magic Only lost r37 - both p=0.50 last resorts). Both handled (diagnosis.md in their case folders).
- Fixed in c2c4abd (Dark Dungeons): the damage model made no buff of the Alchemist's Acidic Mixture Dip (an attack whose target-only projectile carries AddAcidicMixtureToProjectileModel) and never applied the exported MIB damage_type buff, so a Ninja + Alchemist build popped no lead in its eyes: every lead round sat at the 0.06 floor from round 23, every purchase read "0.06 -> 0.06", and nothing was bought for round 37's 15 leads (3 leaked with 10 reds and 12 yellows). `dps_model._potion_buffs` + `_buffed_sources` now lift the named immunity and add the dip's bonus; the same board rates round 28 at 0.66 (was 0.35) and round 37 at 0.32 (0.08). tests/test_alch_potion_buff_offline.py.
- Fixed in a024ba1 (Castle Revenge): the two-sub water build was offered on a moat that holds one sub (sub fit 0.031, not 0.0, so the 17615e3 gate let it through); sb2 and its upgrades were given up and one 2-0-4 sub lost round 33 on one life. mapfit records "room" for water towers (FIT_VERSION 3, table refreshed in 20 s), `runner.placed_counts` tells the planner how many of each kind a plan places, and the gate refuses more water towers than the room; Castle Revenge (room 2 by geometry, but no cell for a second sub in the learned map) is also off the three water builds' map lists. check.py ALL OK after both.
- Backlog 39: Berserker Brew's numbers are not in the attack export, and reinforce is blind while the margin sits at the 1/16 floor (the plan step keeps the cash whatever a purchase would save).
