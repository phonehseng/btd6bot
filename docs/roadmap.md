# Roadmap

Project checklist. Tick an item (`- [x]`) when it is done and verified in
real games. The "btd6-progress" dashboard pane reads this file to show
overall completion, so keep the format: `## Section` headings and `- [ ]` /
`- [x]` items.

The owner's goal (2026-10-22): run unattended until the bot reliably wins
everything, warming up from easy to hard: every Easy-family medal on every
map, then the Medium family, then Hard, its sub-modes and CHIMPS on hard
maps. Never lose, never replay a beaten map/mode.

## Medal goals (warm-up order)
- [ ] Every Easy-family medal on every map (Easy, Primary Only, Deflation)
- [ ] Every Medium-family medal (Medium, Military Only, Apopalypse, Reverse)
- [ ] Hard on every map
- [ ] Hard sub-modes: Magic Only, Double HP, Half Cash, ABR, Impoppable
- [ ] CHIMPS on advanced and expert maps
- [ ] 24-hour unattended run without a loss

## Playing a game
- [x] Window capture and guarded input (never sends Esc)
- [x] HUD reading: cash, lives, round
- [x] Menu navigation with purchase guards
- [x] Strategy plans (YAML, roles instead of coordinates)
- [x] Full defence before the first round, incl. Fast Track starting cash
- [x] Defeat must be confirmed by the lives counter (no false quits)
- [x] Purchases count only with proof (no phantom towers or tiers)
- [x] Threat checks: camo, lead, purple, DDT answered before they arrive
- [x] Banana farms: bananas collected, Marketplace first
- [x] Sniper Elite Defender + radar village plan (works on any map)
- [x] Glaive Lord boomerang plan
- [x] Damage towers must reach the route (45% of the best spot); ones reaching under 25% are sold
- [ ] Towers that pop nothing in 6 rounds are sold (pop counter, two reads)
- [ ] Villages and alchemists placed beside the towers they buff, never alone
- [x] Round forecast: the damage model rates every round as it starts
- [ ] Abilities in a crisis: before panic buys on a leak, early in forecast crisis rounds
- [ ] Win Hard reliably on most maps
- [ ] CHIMPS strategies and wins

## Maps
- [x] Exact map geometry read from the game files (91 maps)
- [x] Height correction for the tilted camera
- [x] New and updated maps picked up automatically
- [x] Sandbox track learning as fallback
- [x] Map fit: how much of each track every tower can reach
- [ ] Line-of-sight aware tower spots
- [x] Dynamic map mechanics: moving parts, sometimes-blocking windows, removable obstacles
- [x] Raised platforms placeable (the highest area decides, as in the game)
- [ ] Buy removable obstacles when the freed space is worth it
- [ ] Blocked spots that reach far more track are probed; the game's answer is learned
- [ ] Researched map builds with exact spots won in real games
- [ ] Optimizer builds (margin 2.0 on every round) won in real games; more maps optimized

## Account and planning
- [x] Account detection and full sync (towers, upgrades)
- [x] Medal sweep of every mode, category unlock bars (co-op medals kept)
- [x] Planner: warm-up order, Monkey Money and XP per hour
- [x] Never replay a beaten map/mode
- [x] Monkey Knowledge auto-spend
- [x] Hero selection (strategy's hero equipped from the HEROES screen)
- [x] Paragon focus: XP to towers closest to their paragon (weighs 3x)
- [x] A solo XP build for every tower (water towers on water maps)
- [ ] Every paragon unlocked
- [x] Double Cash / Fast Track read and used in win chances
- [x] Loss circuit breaker: Easy-family medals after repeated losses
- [x] Collection events: crates collected, reward cards turned
- [x] Mode intro boxes closed after loading (Deflation, ...)
- [x] Check Monkey Knowledge and achievements only when the "!" badge shows

## Game knowledge
- [x] Round compositions
- [x] Tower XP mechanics
- [x] Bloon properties knowledge base
- [x] Map geometry, round sets and achievements read from the game files
- [x] Tower and bloon stats decoded from the game model

## Running unattended
- [x] Supervisor, watchdog and scheduled task
- [x] Offline gate (ALLOW_ONLINE file for development)
- [x] Status overlay and progress pane
- [x] Rolling recording and daily highlight videos
- [x] Sped-up full-run videos (every CHIMPS game, daily Hard-family games)
- [x] Dev log: voiceover script, progression arc and before/after video
- [x] Hourly caretaker: health, loss diagnosis, development
- [ ] A recorded CHIMPS win
