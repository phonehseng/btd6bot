# Bloons: what each one is, what pops it, and when it comes

The bot must never lose to a bloon it cannot pop. This page explains the knowledge
behind that rule and how the bot uses it.

The knowledge lives in three places:

| File | What it holds | Source |
|---|---|---|
| `data/bloons.json` | Per bloon: layer HP, children, properties, speed, RBE, first rounds | Facts entered by hand; checked against the game model (0 disagreements on 17 bloons) |
| `data/counters.json` | Damage types; per tower and crosspath, the damage type of each attack, camo access and auras; a derived table of counters | Hand facts as a fallback. The game model is used first. |
| `data/game_data/round_sets.json` | Every round of every round set | The game's own files (`gamedata.py`) |

The game model is `btd6bot/gamemodel.py` with `data/game_model/*`, decoded from the
game's `sim_model`. For every tower crosspath it says whether some attack pops lead,
black, white or purple. It also says whether the tower detects camo, strips camo,
lends camo (Radar Scanner) or lends every damage type (MIB).

Where the game model has an answer, it decides. `counters.json` adds what the model
cannot say:

- whether one attack gets past several immunities at once (zebra, DDT);
- whether an attack can hurt MOAB-class bloons (an Ice Monkey's freeze cannot);
- which attacks lie on the track (spikes);
- the Alchemist's Acidic Mixture Dip (a buff).

`python tools/build_bloon_kb.py` derives the RBE, immunities, signatures, first rounds
and the counters table. It also writes the cross-checks. `--check` fails when the
derived parts are out of date. `tests/test_threats_offline.py` runs that check.

## The nature of each bloon

Data from `data/bloons.json`. Speed is relative to a red bloon (25 units/s). HP is
per layer.

| Bloon | Layer HP | Fortified HP | Children | Properties | Immune to (damage types) | RBE (fortified) | Speed (x red) | First sent (std / ABR) |
|---|---|---|---|---|---|---|---|---|
| red | 1 | - | - | - | - | 1 | 1.0 | 1 / 2 |
| blue | 1 | - | 1x red | - | - | 2 | 1.4 | 3 / 1 |
| green | 1 | - | 1x blue | - | - | 3 | 1.8 | 6 / 5 |
| yellow | 1 | - | 1x green | - | - | 4 | 3.2 | 11 / 8 |
| pink | 1 | - | 1x yellow | - | - | 5 | 3.5 | 15 / 12 |
| black | 1 | - | 2x pink | black | explosion | 11 | 1.8 | 20 / 7 |
| white | 1 | - | 2x pink | white | cold (freeze) | 11 | 2.0 | 22 / 14 |
| purple | 1 | - | 2x pink | purple | fire, energy, plasma | 11 | 3.0 | 25 / 15 |
| lead | 1 | 4 | 2x black | lead | sharp, cold, energy | 23 (26) | 1.0 | 28 / 10 |
| zebra | 1 | - | 1x black, 1x white | black + white | explosion, cold | 23 | 1.8 | 26 / 26 |
| rainbow | 1 | - | 2x zebra | - | - | 47 | 2.2 | 35 / 26 |
| ceramic | 10 (60 super) | 20 (120) | 2x rainbow | - | - | 104 (114) | 2.5 | 38 / 32 |
| MOAB | 200 | 400 | 4x ceramic | blimp | - | 616 (856) | 1.0 | 40 / 40 |
| BFB | 700 | 1,400 | 4x MOAB | blimp | - | 3,164 (4,824) | 0.25 | 60 / 54 |
| ZOMG | 4,000 | 8,000 | 4x BFB | blimp | - | 16,656 (27,296) | 0.18 | 80 / 79 |
| DDT | 400 | 800 | 4x ceramic (camo, regrow) | blimp, camo, lead, black | sharp, cold, energy, explosion | 816 (1,256) | 2.64 | 90 / 88 |
| BAD | 20,000 | 40,000 | 2x ZOMG, 3x DDT | blimp | - | 55,760 (98,360) | 0.18 | 100 / 99 |

### Modifiers

- **Camo.** Only towers with camo detection target the bloon. Damage that lies on the
  track (spikes) still hits it. A decamo (Counter-Espionage, Shimmer, Signal Flare,
  Submerge and Support, Cleansing Foam) strips camo for good. Children inherit camo,
  so a camo lead pops into camo blacks.
- **Regrow.** The bloon regrows lost layers over time, up to its original type. This
  is not an immunity: it needs damage density. Grow Blocker (Village 0-1-0) and Heart
  of Oak (Druid 0-2-0) stop it. Children inherit regrow.
- **Fortified.** Lead, ceramic and blimp layers get double HP (fortified lead: 4). A
  fortified blimp drops fortified children. A fortified ceramic or lead drops normal
  children.
- **Freeplay (R81+).** Blimp HP and speed ramp up by 2% per round (x1.40 at R100).
  Ceramics become 60-HP super ceramics. Non-blimp bloons drop only one child.
- **Double HP MOABs.** Every blimp layer has twice the HP.
- **Status.** White and zebra cannot be frozen. MOAB-class bloons cannot be frozen and
  shrug off most knockback. A BAD is immune to most stuns, slows and shrinking (Maim
  MOAB does not stun it).

### Damage types

| Damage type | Cannot pop | Examples |
|---|---|---|
| normal | - | Juggernaut, Full Metal Jacket, Flash/Sticky Bomb |
| sharp | lead, frozen | darts, tacks, shurikens, spikes, bullets |
| explosion | black | bombs, shells, missiles, pineapples |
| fire | purple | Hot Shots, Ring of Fire, Wall of Fire |
| cold | white, lead | the Ice Monkey's freeze |
| energy | lead, purple | Wizard bolts, Laser Blasts |
| plasma | purple | Plasma Blasts, Sun Avatar, Tech Terror |
| acid | - | Alchemist potions |

### Signatures: why "can pop" is about one attack

A bloon's **signature** is the set of properties that one attack must get past to pop
it. The bot reasons in signatures (`btd6bot/threats.py`):

- A **camo lead** is {camo, lead}. It needs one tower that both sees camo and does
  non-sharp damage. A Ninja (camo, sharp) next to a Bomb Shooter (lead, no camo)
  covers camo and lead separately, but the camo lead walks through.
- A **lead** pops into two **blacks**. Bombs alone pop the lead and then leak its
  children.
- A **ceramic** releases rainbows, then zebras {black, white}, then blacks and whites.
  Bombs plus Ice cannot pop a zebra.
- A **DDT** is {blimp, camo, lead, black}. A MOAB Assassin cannot hurt it
  (explosions). A Maim MOAB sniper without Night Vision Goggles cannot target it. A
  decamo is not trusted against DDTs, so the popper needs real detection or a radar
  village.
- A **BAD** carries three DDTs.

## What counters what, at which crosspath

Derived table: `counters.json` → `counters`. The game model is used where it has an
answer. Each entry is the minimal crosspath at which a tower handles the signature
alone. Two support towers widen this:

- A **Radar Scanner** village (0-2-0) in range lends camo detection.
- A **Monkey Intelligence Bureau** (0-3-0) lends every damage type.

The rows below list the towers the bot can buy and aim. The full table, which also
covers gift-box towers, is in the JSON.

- **Camo detection**
  - Ninja: from 0-0-0 (native).
  - Sniper 0-1-0 (Night Vision Goggles).
  - Dart 0-0-2 (Enhanced Eyesight).
  - Wizard 0-0-2 (Monkey Sense).
  - Super 0-0-2 (Ultravision).
  - Heli 0-2-0 (IFR).
  - Ace 0-2-0 (Spy Plane).
  - Buccaneer 0-0-2 (Crow's Nest).
  - Ice 2-0-0 (Cold Snap).
  - Mortar 0-0-1.
  - Dartling 0-1-0.
  - Sub 4-0-0. Sub 3-x-x only strips camo.
  - Boomerang 5-0-0 (Glaive Lord).
  - Druid 4-0-0.
  - Spikes hit camo on the track without detection.
  - Support: Village 0-2-0 Radar Scanner, for every tower in range.
- **Lead**
  - Pops lead from tier 0: Bomb, Mortar, Alchemist.
  - Druid 1-0-0.
  - Sniper 1-0-0 (Full Metal Jacket).
  - Boomerang 0-0-2 (Red Hot Rangs).
  - Wizard 0-1-0 (Fireball).
  - Ace 0-1-0.
  - Ice 2-0-0.
  - Sub 0-2-0.
  - Buccaneer 0-2-0.
  - Super 2-0-0.
  - Spike 2-0-0.
  - Tack 3-0-0.
  - Ninja 0-0-3 (Flash Bomb).
  - Heli 3-0-0 or 0-0-3.
  - Dart 4-0-0 (Juggernaut).
  - Support:
    - Village 0-3-0 MIB, for every tower in range.
    - Alchemist 2-0-0 Acidic Mixture Dip, for the towers it buffs.
- **Black (explosion-immune)**
  - Every non-explosive tower.
  - Bombs need 0-0-2 (Frag Bombs; the game model says this ends at 0-0-3).
  - Mortars need 0-0-2 (Burny Stuff), 0-3-0 or 4-0-0.
- **White (freeze-immune)**
  - Everything but the Ice Monkey.
  - The Ice Monkey needs 3-0-0. Cold Snap (2-0-0) does not pop white.
- **Zebra (black + white in one attack)**
  - Any non-explosive, non-cold tower.
  - Bomb 0-0-2.
  - Mortar 0-0-2.
  - Ice 3-0-0.
- **Purple (no energy, fire or plasma)**
  - Most base towers.
  - Cannot pop purple:
    - Tack 3-x-x and up (fire).
    - Super Monkey with top path 1 or more (laser or plasma), or 0-4-x (Tech Terror).
    - Wizard below 0-1-0.
  - Can pop purple:
    - Red Hot Rangs.
    - Wizard 0-1-0 and up.
- **Camo lead**
  - Sniper 1-1-0, the cheapest.
  - Ninja 0-0-3.
  - Spike 2-0-0.
  - Super 2-0-2.
  - Wizard 0-1-2.
  - Dart 4-0-2.
  - Ice 2-0-0.
  - Mortar 0-0-1.
  - Boomerang 5-0-0.
  - Any lead popper next to a Radar Scanner.
  - Any tower next to an MIB.
- **DDT**
  - Sniper 1-1-0, the cheapest.
  - Ninja 0-0-3: Sticky Bomb 2-0-4 is the strong one.
  - Spike 2-0-0.
  - Super 2-0-2.
  - Dart 4-0-2.
  - Boomerang 5-0-2.
  - Wizard 0-2-2.
  - Heli 5-2-0.
  - With a Radar Scanner nearby:
    - Sniper 1-0-0.
    - Boomerang 0-0-2.
    - Tack 3-0-0.
    - Super 2-0-0.
    - Alchemist 0-0-0.
  - Bombs only work inside an MIB.

Heroes are never counted: what they can pop changes with their level.

### Facts the game model corrected

`counters.json` → `crosscheck` lists every crosspath where the hand facts alone
disagree with the game.

Hand facts were wrong, and the bot now follows the game:
- Frag Bombs lose black-popping at 0-0-3 (Cluster Bombs).
- Cold Snap (Ice 2-0-0) does not pop white.
- Tech Terror (Super 0-4-x) does not pop purple.

Hand facts were too cautious:
- Red Hot Rangs pops purple. It is not fire.
- Druid Heart of Thunder pops lead (from 1-0-0).
- Wizard Fireball pops purple.
- Sub 3-x-x does strip camo.
- Mortar 0-0-1 and Dartling 0-1-0 detect camo.
- Glaive Lord (Boomerang 5-x-x) detects camo.

`data/rounds.json`'s answer lists had these errors, now fixed in `strategy.ANSWERS`:
- Sniper camo is at 0-1-0, not 0-2-0.
- The Alchemist pops lead from 0-0-0.
- The Sub's own camo detection comes at 4-x-x.

Camo and lead answers in `strategy.ANSWERS` are now read from
`gamemodel.answers()` at import.

## When each threat comes (from the game's rounds)

First round each signature is needed, inside each mode's round window. Derived by
`tools/build_bloon_kb.py` into `bloons.json` → `threat_rounds`. Children are
included: a camo ceramic needs camo + zebra.

| Mode (rounds) | camo | lead | black | white | zebra | purple | camo+lead | camo+black | camo+white | camo+zebra | camo+purple | blimp | DDT |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Easy (1-40) | 24 | 28 | 20 | 22 | 26 | 25 | - | - | 37 | - | - | 40 | - |
| Medium (1-60) | 24 | 28 | 20 | 22 | 26 | 25 | 59 | 42 | 37 | 42 | 45 | 40 | - |
| Hard and its sub-modes (3-80) | 24 | 28 | 20 | 22 | 26 | 25 | 59 | 42 | 37 | 42 | 45 | 40 | - |
| Impoppable / CHIMPS (6-100) | 24 | 28 | 20 | 22 | 26 | 25 | 59 | 42 | 37 | 42 | 45 | 40 | 90 |
| ABR (3-80) | **5** | **10** | 7 | 14 | 26 | 15 | **24** | 24 | 31 | 39 | 45 | 40 | - |
| Deflation (31-60) | 33 | 37 | 31 | 31 | 31 | 32 | 59 | 42 | 37 | 42 | 45 | 40 | - |

- No DDT or BAD appears in any game that ends at round 80. Standard DDTs come at
  R90, 93, 95 and 99 (fortified), then the BAD at R100. ABR has DDTs from R88.
- Strength rounds stay on the older calendar (`strategy.THREATS`):
  - ceramic: 38
  - MOAB: 40
  - BFB: 60
  - ZOMG: 80
  - the R63 rush
  - camo ceramic: 51
  - fortified MOAB: 62 (ABR 40)

## What the bot does with it

The `strategy.Executor` runs two kinds of checks.

### 1. Property threats (`_property_due`)

- **Calendar.** Every signature the mode's round set brings, at every round it
  appears (not only the first).
- **When a threat is due.** A threat becomes due ahead of its next round. The lead
  time is long enough for the income of the rounds in between (`data/rounds.json`
  cash, with a 25% margin; Double Cash and farms are not counted) to pay for the
  cheapest answer:
  - at least 3 rounds ahead;
  - at least 5 rounds ahead with one life (Impoppable/CHIMPS);
  - at most 10 rounds ahead.
- **Latch.** A due threat stays due until it is covered. Cash saved for it is never
  spent by `surplus()`.
- **What it buys, in order:**
  1. The plan's next steps, if they cover the threat for at most 1.5x (or +$300) the
     cheapest option. While a round is still to spare, the plan just carries on.
  2. The strategy's own `answers:` for the threat, under the same price rule.
  3. The cheapest option (`_options`):
     - an upgrade of a placed tower (never off its plan path; never past what the
       account has unlocked or what turned out locked);
     - or a new tower the mode, the strategy's constraints, the tower caps and the
       account allow;
     - never income upgrades in CHIMPS;
     - never Mortar or Dartling (they must be aimed);
     - never a water tower on a map without water.
- **Log lines:**
  - `threat camo (round 24): covered by n1 (ninja 2-0-1: sharp; camo: detect (innate))`
  - `threat lead arrives round 28 and the defence cannot pop it (...) - cheapest answer new bomb 0-0-0 ($405)`
  - `threat lead (round 28): bought place bomb - cheapest answer ...`
  - `threat lead (round 28): answered - covered by ...`

### 2. Strength threats and the blimp ramp

- Strength threats use the older tier tables (ANSWERS) with the strategy's answers.
- A DDT-tier tower only counts if it can itself hurt DDTs.
- **Blimp ramp.** Before each blimp round (`_ramp_due`), the bot estimates the blimp
  damage the defence deals in reach. It compares that with the round's blimp HP
  (children, fortified, Double HP and freeplay ramp included). For each tower:
  - damage per second comes from `counters.json` → `blimp_dps` (rough estimates);
  - time in reach comes from the map model's track cells inside the tower's range,
    or the whole crossing for map-wide towers.
- **When the ramp falls short:**
  - the strategy's answer for that blimp class runs first;
  - otherwise the plan carries on;
  - extra blimp damage is bought only when the plan is used up, or when the round is
    next and the estimate is under 0.4x.

### Between rounds (`Executor.hold_round`, called from `match.py`)

Play waits when the coming round brings a bloon nothing can pop and its answer is
affordable right now. It never waits more than 30 s per round, so a failing purchase
cannot stall a game.

### Offline check

`tools/simulate_threats.py` plays every strategy's build order through every mode it
lists. It uses the real prices and the game's own per-round income, and records any
round whose bloons the defence could not pop on arrival. All 57 strategy/mode pairs (2026-10-22)
have 0 gaps (`tests/test_threats_offline.py` enforces this).

## Needs live verification

- **Track reach.** The map model's track cells → world units conversion assumes one
  lane. Multi-lane maps under-count reach.
- **The `blimp_dps` numbers** are order-of-magnitude estimates. Watch the
  `blimp check round N` lines against real outcomes and tune them.
- **The Alchemist's lead dip** is counted for towers inside its range. In the game,
  the buff is thrown at towers one at a time.
- **Decamo position is not modelled.** A Counter-Espionage ninja near the exit does
  not reveal camos for towers upstream.
- **`hold_round` assumes** the HUD shows the coming round, or the one just played,
  between rounds. Both are checked.
