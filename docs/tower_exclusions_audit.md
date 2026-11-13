# Tower and hero exclusions audit (2026-11-12)

Read-only audit of everything that keeps a tower kind, a crosspath or a hero
from being considered when builds are made, or that biases against it. The
code was read on `main`, which already has damage-model phase 2: abilities,
heroes, sprays and pierce refresh are credited. Status effects are still
off (`STATUS_RATING = False`, `btd6bot/dps_model.py:2581`).

Live account: SFYOSHHYV, level 153 (`data/accounts/SFYOSHHYV.json`).
- **Towers:** all 26 kinds are unlocked.
- **Heroes:** all 18 are owned. The selected hero is `obyn`.
- **Locked tiers:**
  - mortar x-x-1 and higher (path 3 is at 0);
  - dartling x-5-x;
  - super x-x-4 and higher;
  - mermonkey: every tier 5;
  - skywarden 5-x-x, x-4-x and x-x-4 and higher;
  - village 5-x-x.
- **Not a factor on this account:** unlock-order code such as
  `planner.TOWER_UNLOCK_PRIORITY` (`btd6bot/planner.py:384`),
  `STRATEGY_NEEDS` (`:425`) and the `GIFT_BOX_TOWERS` level-up filter
  (`:738`, `btd6bot/match.py:2018`).

## 1. Usage counts

**Strategy counts.** These cover every YAML under `strategies/`, 504 files
in all:

| Folder | Files |
|---|---|
| top level | 21 |
| `generated` | 26 |
| `maps` | 247 |
| `optimized` | 185 |
| `achievements` | 25 |

- "Files" counts the files that place the kind in any section.
- "Place steps" counts `do: place` steps per section.

**Live counts.** These come from the 425 `tower XP this game` lines in
`logs/bot.log*` (2026-11-07 22:04 to 2026-11-12 08:55).
- "Live games with XP" counts the games in which the kind earned XP.
- "Led" counts the games where it earned the most XP of any kind.

### Towers

| Tower | Category | Files (top/gen/maps/opt/ach) | Files total | Files with it in `plan` | Place steps plan / fill / answers / panic | Live games with XP | Led | Live XP |
|---|---|---|---|---|---|---|---|---|
| dart | primary | 5/25/58/45/7 | 140 | 111 | 384 / 19 / 52 / 11 | 279 | 14 | 2,906,054 |
| boomerang | primary | 4/9/49/20/4 | 86 | 76 | 136 / 18 / 22 / 7 | 43 | 14 | 443,933 |
| bomb | primary | 4/26/92/87/3 | 212 | 181 | 434 / 62 / 118 / 2 | 110 | 5 | 743,048 |
| tack | primary | 3/2/35/42/6 | 88 | 76 | 154 / 24 / 11 / 9 | 27 | 5 | 185,199 |
| ice | primary | 0/4/7/40/0 | 51 | 41 | 100 / 33 / 6 / 0 | 10 | 3 | 70,878 |
| glue | primary | 2/1/4/3/6 | 16 | 15 | 26 / 2 / 2 / 0 | 8 | 0 | 19,093 |
| desperado | primary | 0/1/49/127/0 | 177 | 162 | 607 / 108 / 3 / 19 | 16 | 0 | 83,367 |
| sniper | military | 9/7/194/95/5 | 310 | 291 | 1112 / 89 / 129 / 88 | 235 | 81 | 5,510,873 |
| sub | military | 3/1/93/71/2 | 170 | 164 | 435 / 51 / 35 / 15 | 29 | 20 | 792,328 |
| buccaneer | military | 0/1/105/52/5 | 163 | 160 | 454 / 17 / 66 / 1 | 37 | 22 | 2,267,934 |
| ace | military | 1/25/87/52/0 | 165 | 138 | 328 / 20 / 42 / 2 | 122 | 3 | 1,379,135 |
| heli | military | 4/5/52/11/4 | 76 | 58 | 138 / 21 / 25 / 3 | 98 | 61 | 3,288,389 |
| **mortar** | military | 0/1/0/0/1 | **2** | 2 | 5 / 1 / 0 / 1 | 3 | 0 | 26,188 |
| **dartling** | military | 0/1/1/0/2 | **4** | 4 | 7 / 1 / 0 / 0 | 3 | 0 | 45,281 |
| wizard | magic | 1/2/15/8/1 | 27 | 27 | 45 / 8 / 5 / 4 | 32 | 5 | 479,760 |
| super | magic | 9/1/19/9/10 | 48 | 41 | 56 / 17 / 16 / 1 | 129 | 17 | 2,942,784 |
| ninja | magic | 10/26/42/10/8 | 96 | 71 | 194 / 27 / 49 / 37 | 286 | 151 | 7,693,335 |
| alchemist | magic | 14/1/38/25/10 | 88 | 85 | 133 / 13 / 31 / 2 | 268 | 6 | 2,122,380 |
| druid | magic | 3/1/51/14/0 | 69 | 66 | 173 / 15 / 7 / 5 | 50 | 5 | 720,291 |
| mermonkey | magic | 0/1/27/83/0 | 111 | 110 | 257 / 5 / 3 / 0 | 17 | 0 | 240,919 |
| skywarden | magic | 0/1/25/121/0 | 147 | 147 | 979 / 34 / 3 / 17 | 9 | 0 | 15,843 |
| farm | support | 1/1/0/0/1 | 3 | 3 | 8 / 1 / 0 / 0 | 0 | 0 | 0 |
| spike | support | 11/26/37/10/9 | 93 | 89 | 119 / 29 / 55 / 46 | 115 | 10 | 1,424,914 |
| village | support | 13/4/51/0/12 | 80 | 79 | 96 / 2 / 6 / 0 | 197 | 3 | 2,005,487 |
| **engineer** | support | 0/1/1/6/1 | **9** | 9 | 14 / 2 / 2 / 0 | 5 | 0 | 31,787 |
| **beast_handler** | support | 0/1/0/3/1 | **5** | 5 | 14 / 1 / 2 / 0 | 2 | 0 | 23,990 |

**What the tower counts show:**
- **Present in files but absent live.** Desperado, Mermonkey and Skywarden
  are common in the map and optimized files. Live they lead no game and earn
  little XP: those builds sit in medals that are already won or not reached
  yet.
- **Live play is narrow.** Ninja, sniper and heli lead 293 of the 425 games.
- **Effectively never built:** mortar, dartling, beast handler, engineer,
  glue and farm.

### Heroes

There are 18 heroes. A file's hero is its `hero:`, or else
`required_hero`, or else the first entry of `planner.heroes`.
- **Live counts** use the hero last logged as equipped (`heroes: hero X
  equipped`) before each game's XP line.
- **Unattributed games:** 9 games came before the first equip line in the
  logs.

| Hero | Files (top/gen/maps/opt/ach) | Files total | Live games |
|---|---|---|---|
| quincy | 8/26/89/80/9 | 212 | 92 |
| obyn | 12/0/36/86/7 | 141 | 298 |
| admiral_brickell | 0/0/47/9/1 | 57 | 9 |
| etienne | 1/0/37/10/0 | 48 | 10 |
| sauda | 0/0/18/0/0 | 18 | 2 |
| psi | 0/0/15/0/0 | 15 | 3 |
| ezili | 0/0/4/0/0 | 4 | 1 |
| pat_fusty | 0/0/0/0/2 | 2 | 0 |
| benjamin | 0/0/0/0/1 | 1 | 0 |
| adora | 0/0/0/0/1 | 1 | 1 |
| dan_dmonke | 0/0/1/0/0 | 1 | 0 |
| **gwendolin** | 0 | 0 | 0 |
| **striker_jones** | 0 | 0 | 0 |
| **rosalia** | 0 | 0 | 0 |
| **churchill** | 0 | 0 | 0 |
| **geraldo** | 0 | 0 | 0 |
| **corvus** | 0 | 0 | 0 |
| **silas** | 0 | 0 | 0 |

**What the hero counts show:**
- Quincy and Obyn hold 353 of 504 files and 390 of 425 live games.
- Seven heroes appear nowhere.
- Every other hero comes only from hand-written map research
  (`strategies/maps`) or one achievement plan.

**Solo-build results** (`logs/results.jsonl`, all time):
- `solo_dartling`: won 16, lost 9 (23 of the 25 games were Deflation).
- `solo_mortar`: won 1, lost 2.
- Both builds carry a sniper and spike defence, so these results do not show
  what the dartling or mortar itself did.

## 2. Exclusions and biases, ranked by how much they narrow the choice

"Holds?" says whether the reason is still valid now that phase 2 is on
`main`.

### 1. No code ever compares heroes on merit

This is the widest exclusion: about 12 of 18 heroes are never chosen.

- **`tools/gen_builds.py:95`:** `HERO = "quincy"` is written into all 26 solo
  builds.
  - *Why:* "owned by every account and placed on land: the bot never lacks
    him". Commit aa5ac99, 2026-10-22.
  - *Holds?* No. The live account owns all 18 heroes, and `hero_for`
    already falls back when a hero is not owned.
- **`tools/optimize_builds.py:1336-1338`:** the hero is
  `account.selected_hero or "quincy"`. The `Optimizer` default is `"quincy"`
  (`:733`), and `--check` / `--answer` use `plan.get("hero") or "quincy"`
  (`:1434`, `:1449`, `:1536`, `:1671`).
  - *Effect:* every optimized build gets whatever hero happened to be equipped
    when the tool ran: obyn 86, quincy 80. That hero is then played live,
    which keeps it selected, so the choice feeds itself.
  - *Why:* no comment. The hero was simply never a search dimension.
  - *Holds?* No. The model now rates heroes by level (`HERO_RATING = True`,
    `dps_model.py:1124`) and their abilities (`ABILITY_RATING`, `:1226`), so
    each owned hero could be rated in turn.
- **`btd6bot/strategy.py:1026`:** `HERO_FALLBACK = ["obyn",
  "striker_jones", "gwendolin", "quincy"]`.
- **`btd6bot/planner.py:503`:** `HERO_PRIORITY` is the same list.
  - *Why:* the free heroes of a fresh account, in a hand order. Commit
    2b756bf, 2026-10-21.
  - *Holds?* Only as a last resort for an account that owns nothing else.
    It is still used whenever a strategy names no hero
    (`planner._pick_hero`, `:1029`).
- **Nowhere:** no hero sweep exists, and no `hero` field is ever searched.
  The 15/18/37/47 uses of Psi, Sauda, Etienne and Brickell all come from
  hand research written into `strategies/maps`.

### 2. The map-build tower lists are baked into 247 files

These rules were applied by scratch scripts and are not in repo code. They
are documented in `docs/map_strategies/*.md` and in the file headers:

- **`docs/map_strategies/advanced_a.md:31-34`** and the headers of 39 files
  in `strategies/maps/` (for example `anotherbrick_easy.yaml:14`): "no Heli,
  Mortar, Dartling or Beast Handler".
  - The stated reason for leaving out Heli is that
    `strategy.TARGET_MODES` has no "pursuit". **That reason is stale.**
    `Executor._aim` (`strategy.py:6992-7024`, commit d674992, 2026-10-23)
    sets Lock in Place and then Pursuit by itself.
- **`docs/map_strategies/intermediate_a.md:30-31`:** "no mortar/dartling;
  no skywarden, mermonkey, beast handler, engineer, ice or glue as damage".
- **`docs/map_strategies/expert.md:20`** and **`beginner.md:524`:** no
  mortar or dartling.
- **`docs/research_strategies.md:49-50`:** "No Mortar, Dartling or Ace". This
  rule shaped the 21 top-level hand strategies.
  - The Ace part never held: by default the Ace flies its own circle and
    needs no aim. `docs/tower_research_2026-11.md:317` already flags this.
- **Holds?**
  - Mortar: still holds (see item 4).
  - Dartling: partly holds (see item 4).
  - Heli, Ace, Beast Handler, Engineer, Ice and Glue: no longer hold.
    - The executor operates all six.
    - The Ice/Glue/Engineer-as-damage exclusion was a model gap. It closes
      once status effects are on (item 6).

### 3. Hand-written `ANSWERS` tier tables gate which modes a build may play

- **`btd6bot/strategy.py:144-182`** (`ANSWERS`) together with
  `coverage()` (`:510-563`, tier-table loop at `:547`).
- `btd6bot/runner.py:520` drops every mode where `coverage()` reports a
  missing strength threat: ceramic, moab, bfb, zomg, ddt, bad or rush.
  The same tables drive `Executor.has_answer` (`:4365`), the executor's own
  answer steps (`:5979`) and the optimizer's `answer_actions`
  (`tools/optimize_builds.py:980`).
- **Kinds accepted per threat:**
  - **Never accepted for any strength threat:** glue, desperado, mortar,
    alchemist, mermonkey, skywarden, engineer, beast_handler (and village,
    farm).
  - **Accepted only for the rush:** ice, dartling.
  - **Accepted only for MOAB:** ace, sub, buccaneer, wizard.
- **Effect:** a build carried by one of these kinds must also contain a
  listed kind at the listed tier, or it is dropped from that mode.
- **Why:** hand research. Commit 2b756bf, "corrected threat answers". Only
  camo and lead are refreshed from the game model (`:189-207`).
- **Holds?** No. The damage model now rates whether a build pops each round,
  per kind and crosspath, with abilities. A fixed allow-list of kinds is a
  coarser and more restrictive stand-in for that.

### 4. Mortar and Dartling are treated as doing nothing

- **`btd6bot/dps_model.py:951-952`** (`_flatten_attack` returns nothing for
  `targeting in ("point", "cursor")`) and **`:1410-1412`** (`aim_bound`).
  The documented simplification is at `:56-57`.
  - *Effect:* Mortar is rated at zero sources at every crosspath except
    0-5-x. Dartling is rated at zero except where an ability or extra attack
    exists (x-4-x, x-5-x, x-x-4, x-x-5).
- **`data/counters.json:386`** (mortar) and **`:424`** (dartling):
  `"needs_aim": true`. Commit 4eadbe8, 2026-10-22. This flag drives:
  - `gen_builds.needs_aim` (`tools/gen_builds.py:206`), which makes them
    "not carry" (`:406`), "must be aimed" (`:982`) and never helpers
    (`:688`);
  - the defence-only rule (`:1302`);
  - `strategy._answer_kinds` (`btd6bot/strategy.py:584`): never a coverage
    answer;
  - `Executor._answer_kind_ok` (`:4503-4504`): never bought as an answer.
- **`tools/optimize_builds.py:110`:** `NEVER_KINDS = {"mortar",
  "dartling"}`. Commit 627a4d3, 2026-10-22: "aimed by hand: they do nothing
  for the bot".
- **Holds?**
  - **Mortar: yes.** Its attack goes to a point set with "Set Target", and
    `Game.target` (`btd6bot/game.py:1478`) can only cycle targeting
    priorities. `TARGET_MODES` (`strategy.py:403`) says "no point targets".
    The game's default target after placing has not been verified.
  - **Dartling: only partly.** `Match._park_cursor`
    (`btd6bot/match.py:2074-2093`, PARK constants `:64-69`) rests the cursor
    on the densest stretch of track whenever the bot is idle, so a Dartling
    does fire there. The model still rates it at zero.

### 5. `counters.json` has no facts for several kinds

The hand-entered threat facts in `counters.json` have nothing for these
kinds:

| File and line | What is missing |
|---|---|
| `data/counters.json:203` | desperado: "no reliable facts - never counted" |
| `data/counters.json:560` | mermonkey: same |
| `data/counters.json:565` | skywarden: same |
| `data/counters.json:639` | beast_handler: same |
| `data/counters.json:198` | glue: "not counted as a popper" |
| `blimp_dps` table (`:642`) | no figure for dartling, ice, glue, desperado, mermonkey, skywarden, beast_handler |

- **Effect:**
  - `gen_builds.is_carry` (`tools/gen_builds.py:404-412`) needs
    `prof.blimp > 0`, so all seven kinds above get a "support" build. That
    build is a compact defence of another carry, plus the tower itself.
  - `threats._hit` (`btd6bot/threats.py:393-395`) needs a counters attack
    for any signature with two or more properties (zebra, DDT...), so these
    kinds can never answer those.
  - The executor's blimp ramp check (`Executor.blimp_ratio`,
    `strategy.py:5058`, through `threats.blimp_capacity`) counts them as
    zero blimp damage. It then buys blimp damage of other kinds.
- **Why:** they were gift-box or new towers with no researched facts.
- **Holds?** No. The game model (`data/game_model`) has every one of them,
  and `dps_model` rates them (Desperado, Mermonkey and Skywarden have 1-9
  sources each). The model's per-crosspath blimp damage could replace the
  hand `blimp_dps` table.

### 6. Status effects are off

- **`btd6bot/dps_model.py:2581`:** `STATUS_RATING = False`. Commit 69defa0,
  2026-11-12: "off by default until they are faster".
- **Effect:**
  - Glue is rated at 0 sources at 0-0-0 and 0-3-0, so `target_candidates`
    never picks it as an XP target (`tools/optimize_builds.py:1316`).
  - Ice slows, Pat's and Psi's stuns, Mortar's Pop and Awe and Arctic Wind
    zones count for nothing.
- **Holds?** It is about to be switched on. Once it is, the
  Ice/Glue-as-damage exclusion in item 2 has no basis left.

### 7. Beast Handler's pets are missing from the model

- **`data/game_model/attacks.json`, `beast_handler`:** the pet spawners
  (`PetSpawnerAttack*`) export with 0 weapons. Only the handler's own 0-0-0
  attack has one.
  - *Effect:* `dps_model.profile` gives 1 source at 0-0-0 and 0 at every
    upgraded crosspath. The optimizer never buys a Beast Handler upgrade for
    safety. It appears only as an XP target (3 optimized files).
- **Holds?** No reason exists. This is an export gap
  (`tools/export_attacks.py`).

### 8. Hero modelling and operating gaps

All of these push the optimizer and forecast away from these heroes:

| Hero | Gap |
|---|---|
| corvus | `dps_model.profile("hero:corvus", ...)` returns **None** at every level, so the optimizer cannot rate him. His power is the spellbook, which the bot cannot use (`btd6bot/towers.py:744-746`, ability use "never"). |
| benjamin | 0 damage sources. His $250/round income is in `profile.income`, but the optimizer models no income (`INCOME_KINDS`, `tools/optimize_builds.py:114`). Rated as worthless. |
| adora | From her level 7 (Blood Sacrifice), `abilities.presses_blind` (`btd6bot/abilities.py:234-249`, `:519-525`) stops **all** ability presses, tower abilities included, for the rest of the game. `Evaluator.pressed` (`tools/optimize_builds.py:626-635`) then drops all ability credit. This holds: the hotkey order is assumed, and a wrong guess sacrifices a tower (commit 114feaa). It needs a verified key mapping. |
| striker_jones, gwendolin | Their tower buffs (bomb/mortar; fire) are not in the model: `profile.buffs` is empty. "Target Focus" is "never" (`towers.py:691`). |
| etienne | 0 sources until level 20. Drone attacks are not rated, but the UAV camo buff is. |
| geraldo | No abilities. His shop items "must be bought/placed manually" (`towers.py:742-743`), which the bot cannot do, so only his own attack counts. |
| ezili, admiral_brickell, rosalia, dan_dmonke | Sacrificial Totem, Blast Chain, Flight Boost, Transformation and Reposition are set to "never" (`towers.py:700`, `:717`, `:727`, `:753-754`). Defensible; minor. |

### 9. Generated solo builds are capped and mode-limited

- **Modes:** `gen_builds.candidate_modes` (`tools/gen_builds.py:1094-1104`)
  never tries Impoppable, CHIMPS, ABR, Half Cash or Double HP. Hard (and
  magic_only) is kept only when the build's own blimp damage passes.
  - *Result:* only ace, bomb, heli and sniper have a Hard solo build.
- **Priors:** `BASE_CEILING` (`:162`) caps the prior at 0.92 / 0.86 / 0.80.
  `HELPER_PENALTY` and `SUPPORT_PENALTY` (`:168-171`) lower it further.
  - The planner's paragon focus applies only above `paragon_min_p = 0.85`
    (`btd6bot/planner.py:251`). A generated Hard build therefore starts
    below the paragon bar.
  - All solo builds share one calibration family (`planner.build_family`,
    `:1496-1512`), so a weak solo build drags down every other one.
- **Helpers:** `_helper_options` (`tools/gen_builds.py:688`) excludes
  `T.GIFT_BOX_TOWERS` (dartling, beast_handler, mermonkey, desperado,
  skywarden) as answer helpers. The reason is that they "may be locked".
  - *Holds?* No for SFYOSHHYV, where all are unlocked. `usable()` already
    checks unlocks.

### 10. Stale CHIMPS model doubts

- **`tools/optimize_builds.py:143-148`:** `CHIMPS_MODEL_DOUBTS` refuses, in
  CHIMPS:
  - Glaive Lord (5-x-x boomerang);
  - Master Bomber (x-x-5 ninja);
  - village Primary Training without a Primary tower nearby (`:149`,
    `model_doubt` `:573-587`).
- **Why:** commit 2c0e5fc, 2026-11-05: these were "counted map-wide" until a
  parallel model fix.
- **Holds?** No. The fix is in:
  - per-attack reach and `own_radius`, `dps_model.py:351`, `:394`,
    `:862-863`, `:1069`, commit d2800f8;
  - the Primary Training "sets" filter, `:3096`.

### 11. Reinforcement only grows kinds already on the board

- **`btd6bot/reinforce.py:59`:** `NOT_DAMAGE = ("village", "alchemist",
  "farm")`. These are never offered as "another <kind>".
- **`btd6bot/reinforce.py:451-455`:** only kinds already standing, plus the
  plan's main kind, are offered. Other kinds come in only through
  `new_kind_options` (`:1017-1031`) in a crisis with at least $10,000 idle
  (`BLIND_SPEND_CASH`, `:63`).
- **Holds?**
  - Partly: staying with the plan's kinds is deliberate.
  - The Alchemist exclusion no longer holds. The model rates its dips and
    acid.

### 12. Small fixed lists

Each is narrow, but each fixes the choice by hand:

| File and line | List |
|---|---|
| `strategy.py:328` | `PANIC_KINDS` (tack, dart, sniper, ninja, wizard, boomerang, engineer, spike) |
| `strategy.py:1227` | `CHEAP_OPENERS`; the automatic opener is always a dart |
| `strategy.py:477-479` | `CAMO_BACKUPS` (village, dart, sniper, ninja, wizard, sub) |
| `tools/gen_builds.py:148` | `CURSOR_FIX = {"heli": (1, 2)}` |

- **`strategy.py:584`:** `_answer_kinds` also excludes all water towers
  from `coverage()`, "as the map is unknown". This biases against sub and
  buccaneer on water maps.

### 13. Dormant hotkey guards (no effect today)

- **Where:**
  - `tools/optimize_builds.py:111-113` adds towers without a hotkey to
    `NEVER_KINDS`;
  - `strategy.usable` (`:1111-1115`) and `Executor.kind_allowed`
    (`:1252-1256`) refuse them.
- **Why:** commit 2eefe59, 2026-10-22.
- **Today:** Desperado `o`, Mermonkey `p` and Skywarden `;` are bound in
  `towers.py` (`:635-637`, bound in-game 2026-10-22), so these guards
  exclude nothing.
- **Stale text:** the comment at `optimize_builds.py:111` and
  `docs/backlog.md` still say they "have none".

## 3. What to change

### Towers that must stay out, or stay limited, and why

- **Mortar:** keep it out of safety purchases until the executor can set a
  target point.
  - `Game.target` only cycles priority labels.
  - Nothing clicks "Set Target" and then a track point.
  - The damage after placement depends on a default target nobody has
    verified.
- **Engineer x-4-x (Overclock / Ultraboost):** the tower itself is
  operable. These abilities need a tower clicked as their target, and only
  hero abilities support that (`do: ability`, `strategy.py:384-394`).
  - The model must not credit them unless the executor presses them.
  - The Bloon Trap is income: it is already skipped where income pays
    nothing.
- **Geraldo's shop and Corvus's spellbook:** inoperable. Rate these heroes
  on their auto-attacks only.
  - Corvus first needs a model entry, since `profile` returns None.
- **Adora's abilities after level 7:** stay off until the hero ability
  hotkey order is verified on screen.

### Changes so every operable tower and hero is considered on merit

1. **Add a hero sweep.**
   - In `tools/optimize_builds.optimize` (`:1336`), run the greedy once per
     owned hero, filtered by `_hero_fits` and water placement. Keep the best
     plan.
   - Do the same in `gen_builds` (`:95`): pick the hero that rates best with
     the build, or at least skip the hard-coded `"quincy"`.
   - Turn `HERO_FALLBACK` / `HERO_PRIORITY` into a fallback only for
     accounts that own nothing else.
2. **Rebuild the map builds without the scratch-script bans.**
   - Allow Heli, Ace, Beast Handler, Engineer, Ice and Glue.
   - Drop the Heli-has-no-Pursuit reason (`advanced_a.md:31-34` and the 39
     file headers).
   - Drop the "No Ace" rule (`research_strategies.md:50`).
3. **Replace the `ANSWERS` strength tables in the mode gate**
   (`strategy.py:144-182`, `coverage` `:547`, `runner.py:520`) with a
   damage-model check.
   - Use `round_margin` over the mode's threat rounds, or derive per-crosspath
     answers from `dps_model.profile` the way camo and lead already come from
     `gamemodel.answers`.
   - Keep the tables only as a fallback when the model is missing.
4. **Fill the `counters.json` gaps from the game model.**
   - Derive blimp damage per crosspath from `dps_model` instead of the hand
     `blimp_dps` table.
   - Let `threats._hit` accept a game-model attack for multi-property
     signatures when one attack covers all of them.
   - This makes Desperado, Mermonkey, Skywarden, Ice, Glue and Beast
     Handler carries or answers on their numbers (`gen_builds.is_carry` `:404`,
     `threats.py:393`, blimp ramp).
5. **Switch `STATUS_RATING` on** (`dps_model.py:2581`) as planned. Then let
   Glue be an XP target and a safety purchase (`optimize_builds.py:1316`
   needs `prof.sources`; slows should count too).
6. **Model the Dartling at the cursor park point.**
   - The park point is `Match._park_point` (`match.py:2052-2072`).
   - Discount it for the time the cursor is busy elsewhere.
   - Then remove `dartling` from `NEVER_KINDS` (`optimize_builds.py:110`),
     from `needs_aim` in `counters.json:424`, and from the answer bans
     (`strategy.py:584`, `:4503`; `gen_builds.py:688`).
   - Adding a "Locked" target with one fixed point would make it fully
     operable.
7. **Export the Beast Handler's pets** (`tools/export_attacks.py`) so the
   model rates its upgrades.
8. **Fix the hero model gaps:**
   - a profile for Corvus's auto-attack;
   - Benjamin's income in the optimizer's economy;
   - Striker's and Gwendolin's tower buffs;
   - Etienne's drones.
9. **Remove the stale CHIMPS doubts** (`optimize_builds.py:143-149`,
   `model_doubt`), after a CHIMPS check of a Glaive Lord / Master Bomber
   plan.
10. **Generated builds** (`gen_builds.py`):
    - try Hard-family and one-life modes too;
    - drop the `GIFT_BOX_TOWERS` helper filter (`:688`);
    - reconsider `BASE_CEILING` against `paragon_min_p` (0.80 < 0.85).
11. **Reinforcement:** take `alchemist` out of `NOT_DAMAGE`
    (`reinforce.py:59`) so its buff is rated like any other option.
12. **Clean the stale text:**
    - `optimize_builds.py:111` comment;
    - `docs/backlog.md` hotkey note;
    - `dps_model.py:56-57` (once the Dartling is modelled).
