# Roadmap

Project checklist. Tick an item (`- [x]`) when it is done and verified in
real games. The Claude Code "btd6-progress" pane reads this file to show
overall completion, so keep the format: `## Section` headings and `- [ ]` /
`- [x]` items.

## Playing a game
- [x] Window capture and guarded input (never sends Esc)
- [x] HUD reading: cash, lives, round
- [x] Menu navigation with purchase guards
- [x] Strategy plans (YAML, roles instead of coordinates)
- [x] Full defence before the first round, incl. Fast Track starting cash
- [x] Defeat must be confirmed by the lives counter (no false quits)
- [ ] Win Hard reliably on most maps
- [ ] CHIMPS strategies and wins

## Maps
- [x] Exact map geometry read from the game files (91 maps)
- [x] Height correction for the tilted camera
- [x] New and updated maps picked up automatically
- [x] Sandbox track learning as fallback
- [ ] Line-of-sight aware tower spots

## Account and planning
- [x] Account detection and full sync (towers, upgrades)
- [x] Medal sweep of every mode, category unlock bars
- [x] Planner: Hard first, Monkey Money and XP per hour
- [x] Monkey Knowledge auto-spend
- [ ] Hero selection
- [ ] Grind low-XP towers in safe games (paragons, all tiers)
- [ ] Check Monkey Knowledge and achievements only when the "!" badge shows

## Game knowledge
- [x] Round compositions
- [x] Tower XP mechanics
- [ ] Bloon properties knowledge base
- [ ] Tower and bloon stats decoded from the game model

## Running unattended
- [x] Supervisor, watchdog and scheduled task
- [x] Offline gate (ALLOW_ONLINE file for development)
- [x] Status overlay and progress pane
- [ ] 24-hour unattended run without a loss
