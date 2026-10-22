# Backlog

Items marked **[live]** need the game, so the bot has to be paused for them; only a developer session that stops the supervisor should do those. Items marked **[offline]** can be done safely while the bot runs: edit code, then use `tools/restart_after_game.ps1` to load it between games.

## Next
0. **[live]** Level 30+: the Gift Box unlocks Dartling, Beast Handler, Mermonkey, Desperado and Skywarden by pops. When the account reaches 30, calibrate the Gift Box screen and point it at the next locked tower (Dartling first: strong and placement-free). Hotkeys for Desperado (O), Mermonkey (P) and Skywarden (;), which have none by default, were bound on 2026-10-22 (Settings -> Hotkeys; leaving the page asks "Save Hotkey Changes?" - Save, or they are lost).
1. **[live]** Tower-choice carousel sometimes fails to center the target. At level 16 the bot wanted Ninja and got Druid. `logs/bot.log` now records each step (`carousel step N: centre=...`) and `logs/carousel.png`; work out the step direction from those.
2. **[live]** Calibrate `meta.select_hero` (Gwendolin is unlocked) and wire it into `runner.select_hero`. Check every `# VERIFY LIVE:` note in `btd6bot/meta.py`.
3. **[live]** At level 30, calibrate `meta.buy_monkey_knowledge`, then call it from the runner after games when `account.mk_points > 0`.
5. **[offline]** `tests/test_planner.py::test_long_run_reaches_everything` fails; investigate it.
6. **[offline]** Planner: use the observed `minutes` per map/mode (`account.map_stats`) instead of estimates, to maximize Hard wins per hour.
9. **[offline]** Look at each loss in `logs/bot.log` (`outcome': 'defeat'`), work out which threat leaked, and strengthen that strategy's `answers:` section.

## Done
- Autonomous loop: menus → planner → search → play → record. Supervisor and caretaker are in place.
- Map medals are read from the search-result card (`btd6bot/medals.py`); the save file is adopted, and already-earned first-time medals are skipped. The black/Impoppable medal colour is still to be verified live.
- Hero/tower ability planner (`btd6bot/abilities.py`): estimated hero level, MOAB-round saving, emergency use on leaks.
- Water scan (`scanner.scan_water`) runs when the chosen strategy uses water towers.
- Account identity: User ID read from Settings; per-account state and achievements files; full upgrade sync from the Monkeys menu on a new account or daily; re-checked every 6 games or on an implausible level.
