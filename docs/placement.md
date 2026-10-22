# Placement knowledge (BTD6 v57, Oct 2026)

`data/placement.json` holds the placement facts a track-mask placer can use:

- `towers`: 26 towers and 18 heroes.
- `maps`: all 88 single-player maps, keyed exactly like `account.MAPS`.
- `line_of_sight`: the line-of-sight (LOS) rules.
- `rules`: 20 heuristics that can be computed from the learned map model.

`conventions` in the file defines every field.

## Sources

Every page was fetched through `r.jina.ai` on 2026-10-21. The Fandom "Height" page was CAPTCHA-blocked.

- **bloonswiki `Line_of_sight` page:** the general rules.
- **Every bloonswiki tower page:** the stat tables. These give display range, footprint radius, targeting options, and an
  `Ignores blockers` filter on each attack and projectile. That filter is the most reliable LOS source found.
- **All 88 bloonswiki map pages:** the infobox (entrances, exits, water) plus the description and strategy sections.
- **Hero pages:** mostly prose. Hero ranges are therefore less certain and are marked `?`.

Anything not confirmed is marked `?` in the JSON.

## Line of sight: key facts

How LOS works:

- **Three kinds of blocker:** walls and objects, removables, and **higher terrain**.
  - A tower cannot see bloons on ground higher than itself.
  - It can see lower ground.
  - Low-ground traps: the Ravine river, Sunken Columns depressions, Mesa's valley, Quarry's lower layers, and Glacial Trail's water.
- **When LOS is checked:** targeting is checked when an attack starts. Most LOS projectiles die on a blocker.
- **The game draws the blocked area.**
  - A selected or ghost tower shows the blocked part of its range in red (black with High Contrast).
  - A Sniper ghost shades blocked areas across the whole map.
  - This is the cheapest way for the bot to learn a per-cell LOS mask (see "Using it" below).

**Ignore LOS completely:**

- Towers:
  - Ace and Heli (both fly).
  - Mortar (lobbed shots).
  - Alchemist (potions).
  - Spike Factory: it drops spikes behind blockers, but its range must still reach the track.
  - Beast Handler's base staff attack.
- Heroes:
  - Obyn (spirit wolf).
  - Ezili.
  - Adora.
  - Psi (global).
  - Corvus's spirit.
  - Etienne's drones, but only inside his 55 range.
- Farm and Village have no attack, so LOS does not apply to them.

**Ignore LOS only with an upgrade:**

- Wizard:
  - Guided Magic (1-x-x).
  - Phoenix (x-4-x).
  - Necromancer zombies (x-x-4).
- Sub Ballistic Missile (x-3-x) and Pre-emptive Strike. The sub's normal darts, including through Advanced Intel, still need LOS.
- Boomerang:
  - The MOAB Press heavy Kylie (x-x-4).
  - Glaive Ricochet (3-x-x): glaives pass through walls, but targeting still needs LOS.
- Druid: Heart of Thunder lightning and Superstorm.
- Skywarden Thundering Arc (x-2-x) and up, which also unlocks Set Target.
- Buccaneer Aircraft Carrier planes (4-x-x).
- The Super Monkey X-ray Ultra Monkey Knowledge.
- Beast Handler Giganotosaurus and the flying birds.
- Brickell's mines.
- Gwendolin's Cocktail.
- Silas can attack inside an Ice Monkey's range.

**Need LOS:**

- Dart, boomerang (base), bomb, tack, glue, desperado, druid thorns, mermonkey, wizard (base), super, ninja (caltrops too), engineer, buccaneer guns.
- Bomb: the projectile needs LOS, but its explosion ignores blockers.
- Ice: needs a visible target to trigger; the blast itself ignores blockers.
- Sniper: global range, but every shot needs a clear line.
- Dartling: shots are destroyed by blockers.
- Quincy, Gwendolin, Striker Jones, Pat Fusty, Silas (own targeting), and probably Churchill, Sauda, Geraldo, Rosalia and Dan.
- Benjamin's Trojan has infinite range but cannot see through walls.

**Slightly elevated LOS** (sees over some low objects):

- Tack tier 4+.
- Ice Cryo Cannon line.
- Bionic Boomerang (x-3-x).
- Grandmaster Ninja (5-x-x).
- Super Laser Blasts (1-x-x) and up.

**Immunity zones are not LOS.** Under these, bloons are immune to every attack, including LOS-ignoring ones:

- Quad trusses.
- Dark Castle entrance trees.
- The KartsNDarts tunnel (non-MOABs only).
- The X Factor central barrack.

Two related cases behave differently:

- Under the Logs logs, bloons can still be hit by LOS-ignoring towers.
- In Mushroom Grotto's darkness, nothing can target bloons, but projectiles still hit.

## Aiming (`aiming` field)

| tower | how it aims | bot-safe option |
|---|---|---|
| Dartling | follows the mouse cursor (Normal), or Locked, or Target Independent at x-x-4 BADS | aim once along a long straight, then Locked; or only use it from BADS |
| Mortar | a fixed reticle chosen at placement (spread 18; 8 with Increased Accuracy) | set it once on the densest bend or lane overlap (`mortar_point` rule) |
| Ace | flight pattern around the runway, about 80 radius: Circle / Infinite / Eight; Centered Path (x-x-2) circles a set point | leave Circle; pick the runway whose 80-unit circle overlaps the most track |
| Heli | Follow Touch (cursor), Lock in Place, Patrol, Pursuit (2-x-x) | buy Pursuit early; until then Lock in Place. **Never leave Follow Touch: the bot moves the mouse constantly.** The default after placement is believed to be Follow Touch (verify in game) |
| Spike | random point in range; Smart Spikes (x-x-2) adds Close / Smart / Set Target / Automatic | Smart; Set Target at an exit split |
| Skywarden | Set Target from x-2-x | optional |

## Using it in the placer

1. **Load the data.** Load `towers[id]` for the tower being placed, and `maps[name]` for the current map
   (keys match `account.MAPS`, e.g. `"#Ouch"`, `"Three Mines 'Round"`).
2. **Filter candidate cells:**
   - by `placement` (land/water mask);
   - by footprint (reserve space for `large` first; see the `cluster_reservation` rule).
3. **Score each cell** with the base `coverage` rule: track cells within `display_range`, weighted by
   `segment_preference` against each cell's learned progress. Then multiply by the geometry rule:
   - `bends` → `tack_bends` (angular coverage inside a short radius).
   - `loop_center` → `loop_center` (rays that hit track).
   - `straight` → `straight` (PCA linearity of in-range track).
   - `near_exit` → `spike_exit`.
   - `near_entrance` → restrict to progress < 0.3.
   - `passes` is a bonus for every radius tower: the count of distinct progress runs inside range.
4. **Global towers** (`range_type: global`): score by the visible fraction of the track instead of by radius
   (`global_los`). Ace, heli and mortar use `flying_any` / `mortar_point`.
5. **Support towers** (`support_radius` set: village, alchemist, obyn, etienne, rosalia, silas): score by how
   many already placed damage towers fall inside the radius (`support_radius` rule).
6. **LOS:** until the bot captures LOS masks, treat `maps[...].los_blockers` / `elevation` as a prior.
   - On heavily walled maps, prefer towers with `needs_line_of_sight: false`, or buy the LOS upgrade first.
   - Never put LOS towers on the low ground listed in `elevation`.
   - Suggested LOS learning: during the existing placement probe, hover a Sniper ghost on a few candidate cells. The red overlay
     is exactly that cell's blocked region; store it per map in the map model.
7. **Map specials** that break the static-coverage assumption:
   - Geared / Sanctuary: rotating or moving platforms.
   - Covered Garden: rotating covered quarter.
   - Erosion: land collapse at R17/35/53/71/89.
   - Glacial Trail: towers freeze 2 rounds in 10, counted per tower from its own placement round.
   - Workshop: +50% bloon speed.
   - Last Resort: loop size and speed change by round.
   - Polyphemus: the eye closes every 10 rounds.
   - Flooded Valley: land towers can't see over the dam.
   - Mushroom Grotto: darkness.
   - Skull Tweak / Spa Pits: clicking props turns on harder layouts, so **never click map props** (`dont_click_secrets`).
8. **Removables:** most removables open placement or LOS. A few are profitable (Three Mines 'Round's $435 crystal returns $870).
   The bot does not buy removables now; the costs are listed in case that changes.

## Map highlights

- **Easiest maps:** Logs, Resort, Spa Pits, Three Mines 'Round, Cubism, Four Circles, Candy Falls (beginner); Sulfur Springs,
  KartsNDarts (intermediate); Infernal and Dark Castle (expert).
- **True experts:** Bloody Puddles, Ravine, Quad, #Ouch, Dark Dungeons. Avoid them for auto-play.
- **Water-dominant maps** (`has_water` plus little land): Spice Islands, Peninsula, Luminous Cove, Flooded Valley, Lotus Island.
- **Alternating-lane maps** (score must cover every lane):
  - Water Park, Bazaar, Chutes, Luminous Cove, Enchanted Glade, High Finance, Infernal.
  - Ravine (by entrance).
  - Muddy Puddles (one lane of 4 per round).
  - Bloonarius Prime (prime rounds).
  - X Factor and Bloody Puddles (rotating spawns).
  - Ship Capture (5-round blocks).
  - Last Resort.

## Discrepancies with `btd6bot/towers.py` (not changed: .py files were off limits)

Bloonswiki values vs the current code:

| tower | value | wiki | code |
|---|---|---|---|
| Bomb | footprint | 7 | 8 |
| Ice | footprint | 6 | 7 |
| Mortar | footprint | 11 | 8 |
| Super | footprint | 11 | 9 |
| Buccaneer | footprint | 8 | 9 |
| Engineer | footprint | 7 | 6 |
| Mermonkey | footprint | 8 | 7 |
| Mermonkey | range | 28 on land / about 38 on water | 40 |
| Skywarden | footprint | 6 | 7 |
| Desperado | range | 60 | 50 |
| Desperado | footprint | 7 | 6 |
| Striker Jones | range | 55 | 50 |
| Gwendolin | range | 38 | 40 |
| Adora | range | 45 | 50 |
| Etienne | range | 55 | 60 |
| Dan D'Monke | range | 30 | 40 |
| Brickell | range | 50 | 60 |
| Churchill | acquisition range | 65 | 52 |

`docs/research_strategies.md` says Heli "needs no aiming". That is only true once it is in Pursuit or Lock in Place.
