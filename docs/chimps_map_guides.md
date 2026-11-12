# CHIMPS map guides: the 55 maps without a black border

What players use to beat CHIMPS on every map the main account (SFYOSHHYV) has
not beaten on CHIMPS: 18 Intermediate, 24 Advanced and 13 Expert maps.
Researched 2026-11-12 (game v57.x). This is the seed for rebuilding the bot's
CHIMPS builds the way the Beginner maps and Cracked were won: by following a
proven guide step by step with `plan_first`.

The open maps come from `data/accounts/SFYOSHHYV.json`, `medals[<map>]["chimps"] == False`.
The tiers come from `btd6bot/account.py`.

## How it was researched

- **bloon.games** (`https://bloon.games/how-to-beat-chimps-on-<map>/`). The
  pages were fetched raw and the guide text extracted. Only 11 of the 55 have
  written steps: Balance, Lost Crevasse, Luminous Cove, Polyphemus, Spillway,
  Dark Path, Sunset Gulch, Mushroom Grotto, Infernal, Flooded Valley and
  Glacial Trail. The other pages hold one "BTD6 Master" video, and its
  description has no tower list. Nine maps have no CHIMPS page at all:
  Party Parade, Muddy Puddles, #Ouch, Quad, Workshop, Bloody Puddles, Ravine,
  Dark Dungeons and Tricky Tracks.
- **YouTube.** The top 10 results for "<map> chimps btd6" on each map, with
  their full descriptions. This turned out to be the richest source:
  OneEyedDeacon, BeatbloonsBob, ApexZ ("Full Auto Start"), G-Horizon,
  Yoboi3li, retrogaming fun, CrimsonPlanet, HyperF3, BTD6 BluePrint, metaldevil
  and others write the whole build, round by round, in the description or a
  pinned comment.
- **Wikis.** The strategy sections of bloonswiki and fandom, read through
  their MediaWiki API.
- **Reddit and Steam.** Reddit refused scripted fetches, so only search
  snippets (and one mirror of the CHIMPS difficulty chart) were used. Steam
  had almost nothing map-specific.
- **Earlier project research.** `docs/map_strategies.md` and
  `docs/map_strategies/*.md`, for track geometry, sight blockers, removables
  and the bot's model gaps. The headers of the lost builds
  `strategies/maps/{lostcrevasse,moonlanding,rake,springspring,sulfursprings}_chimps.yaml`
  say what went wrong.

**Confidence labels on each strategy:**

| Label | Meaning |
|---|---|
| verified-written-steps | A written round-by-round list (description, pinned comment or page) was read. |
| video-description | The tower list was read in a description but not every round. |
| wiki / snippet-only | Second-hand. |
| UNVERIFIED / inferred | Not stated by any source, so treat it as a hypothesis. |

The YouTube watch pages started to rate-limit (HTTP 429 or a captcha) partway
through, so a few descriptions named in the sections were never read. Each of
those is flagged where it appears.

## Account constraints (checked against `unlocked_upgrades`)

Tier caps are written [top, middle, bottom]. Every other tower has 5-5-5.

| Tower | Cap | Effect on the guides |
|---|---|---|
| Mortar | 5-5-0 | No bottom path at all. That rules out bloon.games' Spillway (3-0-2 and Blooncineration 2-0-5), bloon.games' Glacial Trail (Signal Flare 0-2-3) and ApexZ's Muddy Puddles (0-2-4). |
| Monkey Village | 4-5-5 | No Primary Expertise. It appears in bloon.games' Balance and Luminous Cove guides, OneEyedDeacon's Bloody Puddles and Workshop (v48) guides, and others. Stop at Primary Mentoring 4-2-0, which loses the Mega Ballista finisher. |
| Mermonkey | 4-4-4 | No tier 5 (Lord of the Abyss, Popseidon, Final Harmonic). That rules out bloon.games' Flooded Valley as written, the Pat's Pond, X Factor and Quad LotA guides, the Luminous Cove "Axis of Mermonkey", and others. |
| Dartling | 5-4-5 | No M.A.D. |
| Super Monkey | 5-5-3 | No tier 4-5 bottom path. |
| Skywarden | 4-3-3 | No tier 5. |

**Heroes owned:** Brickell, Adora, Benjamin, Churchill, Corvus, Dan D'monke,
Etienne, Ezili, Geraldo, Gwendolin, Obyn, Pat Fusty, Psi, Quincy, Rosalia,
Sauda, Silas and Striker Jones. Every hero the recommended guides use is
owned.

## Bot limits that the per-map "Bot notes" check against

CHIMPS rules: no selling, no income, no Monkey Knowledge, no powers, and the
game starts on round 6 with $650.

**What the bot can do:**

- Set targeting priorities, including a heli's Pursuit or Lock in Place and
  an ace's Centered Path, as a one-time setting.
- Buy removable obstacles.
- Press an ability on a given round.

**What it cannot do:**

- Place on a ship deck or a Carrier Flagship deck.
- Aim. This covers a mortar target, a Spike Factory or Perma-Spike "Set
  Target", Wall of Trees, Mega Mine, and a dartling's cursor.
- Time an ability to the moment a MOAB or BAD is on screen. This covers
  First Strike, Pre-Emptive Strike timing and Rosalia's blimp-break timing.
- Move a hero during a game.

Guides that rely on any of these are flagged per map.

## Patterns across the 55 maps

1. **Map-wide towers really are required on many maps.** Ground towers do
   not see enough of the track there.
   - Sniper armies ("Axis of Havoc": 0-2-5 Elite Defender, 0-5-2 Elite
     Sniper, 5-2-0 Cripple MOAB, several 0-3-2, with a 5-2-0 Permanent Brew
     alchemist and a 2-0-2 village): Geared, X Factor, Mesa, Cargo, Castle
     Revenge, Erosion, Sunset Gulch, Sunken Columns, Mushroom Grotto, Last
     Resort, Quad, Bloody Puddles, Quiet Street and Moon Landing.
   - Water towers that see the whole track (Carrier Flagship, Advanced Intel
     subs): Luminous Cove, Sulfur Springs, Haunted, Firing Range, Spring
     Spring, Peninsula, Flooded Valley, Muddy Puddles and #Ouch.
   - Aircraft: Ace 2-0-5 Flying Fortress with Rosalia on Water Park, Bazaar,
     Covered Garden and Bloonarius Prime, and a heli on Encrypted, Chutes,
     Another Brick and Infernal.
   - Spirit of the Forest (x-5-0 druid) is a core piece on Lost Crevasse,
     Sunken Columns, Ascent, Ship Capture and Luminous Cove.
   - Perma-Spike at the exit is the late-game insurance on Polyphemus, Dark
     Path, Sunset Gulch, Mushroom Grotto, Last Resort, Rake, Workshop,
     Erosion, Glacial Trail, Sanctuary and Ancient Portal.
2. **The written guides that fit the bot best come from a few creators.**
   OneEyedDeacon (Sauda/Psi/Etienne sniper and Tack Zone builds, no
   abilities, v50-v54), BeatbloonsBob, ApexZ ("Full Auto Start"), G-Horizon
   and retrogaming fun (Churchill). Their descriptions give exact rounds and
   crosspaths, the format that won Cracked.
3. **Some balance changes may have outdated older guides.** OneEyedDeacon
   notes that Elite Defender (0-2-5) was nerfed around v54, and that the
   Bomb Blitz nerf killed his Bomb Axis guides. One comment claims
   middle-path snipers lost lead popping in 57.1 (UNVERIFIED). Prefer v54+
   guides wherever a sniper build is used.
4. **Gaps in the bot's own map model block some guide spots.**
   - Spillway: the centre barrel.
   - Sunken Columns: the raised ground.
   - Balance: the central plots.
   - Encrypted: the crypt interior and the $250 pads.
   - Flooded Valley: the Silas ice.
   - Midnight Mansion: the drawer spot.
   - Geared: Psi on the moving gears.

   These maps need the placement data fixed before their guides can be
   followed.
5. **No bot-friendly written guide was found for five maps:** #Ouch, Quad,
   Bloody Puddles, Party Parade and Midnight Mansion. Every written list
   there leans on timed abilities or shop items. Videos titled "no abilities
   / no micro" exist (Doreo, BTD Flagship, sYnce), but they would have to be
   watched and written up by hand.


## Intermediate maps

### Lost Crevasse (Intermediate)
**Map traits / what it requires:** Two entrances (fandom lists 2, bloonswiki lists 3 with a boss path). Both paths run at the same time and cross the long middle diagonal in opposite directions, so the middle is the crowd-control zone (bloonswiki). The ice slows bloons. Ice crystals block placement and sight on the upper right. A sniper right of the small crystal above the crystal column sees both sides with little blockage (bloonswiki). The lake on the lower right touches both lanes after they split. No removables. Bloonswiki says v57.0 nerfed the map to "an average Intermediate"; before that, guides called it harder than most Advanced maps. Nothing is strictly required, but a global sniper with sight of both lane ends shows up in every written guide. Recommended: Sauda (the entrance chokepoint and overlapping lanes give her near-double damage), Super Glue and snipers.
**Strategy 1 - Sauda + Tack Zone + Spirit of the Forest, no abilities / no micro** (source: https://www.youtube.com/watch?v=yjRUMBRZOss ; OneEyedDeacon; v53.2, about 7 months old; confidence: verified-written-steps (video description))
- Hero: Sauda, top middle, "as high as possible".
- Core towers: Tack 2-0-5 (Tack Zone), Druid 1-5-0 (Spirit of the Forest), Sniper 0-2-2, Village1 4-0-2, Village2 0-3-2, Alchemist 4-2-0, Ice 5-2-0 (Icicle Impale), Glue 0-2-5 (Super Glue, Strong then First).
- Purchase order: R6 Sauda; R8 Tack1 0-0-0 right of Sauda; R10 Sniper1 0-0-0 next to the crystal; R12 Druid1 0-0-0 behind Sauda; R13 Druid 0-1-0; R15 0-2-0; R19 0-3-0; R20 1-3-0; R22 Sniper 0-0-1; R23 0-1-1; R25 0-1-2; R27 0-2-2; R32 Village1 0-0-2 (left, behind the druid); R36 Village2 0-0-2 (right); R37 Tack 2-0-3; R39 Tack 2-0-4; R40 Village1 2-0-2; R43 Alch1 3-2-0; R45 Village2 0-2-2; R46 Village1 3-0-2; R48 Ice1 4-1-0 left of Sauda; R49 Alch 4-2-0; R51 Druid 1-4-0; R63 Tack 2-0-5; R65 Glue1 0-1-3 on Strong, double-discounted, next to the druid; R66 Glue 0-2-3; R68 Glue 0-2-4; R83 Druid 1-5-0; R92 Ice 5-2-0; R97 Glue 0-2-5, targeting First; R99 Village2 0-3-2 + Village1 4-0-2.
- Key placements: Sauda at top middle, high up. Tack to her right, ice to her left, druid behind her. Sniper next to the crystal. Two villages (left/right) covering the cluster.
- Abilities used: none (title: "NO ABILITIES and NO MICRO").
- Account conflicts / substitutes: none. Village top path stops at 4 (Primary Mentoring), which is within the cap. Ice 5-2-0 and Glue 0-2-5 are unlocked.
**Strategy 2 - Sauda + Elite Defender / Elite Sniper / Perma-Brew (Axis of Havoc)** (source: https://www.youtube.com/watch?v=AjYKwKvdNV4 ; OneEyedDeacon; v50.0, from before the v57 nerf; confidence: verified-written-steps)
- Hero: Sauda, top middle.
- Core: Sniper1 0-2-5 Elite Defender; Sniper2 0-5-2 Elite Sniper; Alch1 5-2-0 Permanent Brew; Druid 1-3-0; Village 2-0-2; Sniper3 5-2-0 Cripple MOAB; Snipers 4-6 0-3-2; Glue 0-2-3.
- Order: R6 Sauda; R9 Sniper1 on Strong, high, next to the crystal, seeing the end of both tracks; R11 Sniper2 on Strong under it; R12 Druid1 left of Sauda; R14/15/19 Druid 0-1-0/0-2-0/0-3-0; R21 1-3-0; R28 Village1 0-0-2; R29-31 Sniper1 0-0-1 -> 0-0-2 -> 0-1-2; R32 0-2-2 on First; R36 0-2-3; R40 0-2-4; R42 Sniper2 0-3-2 on First; R44 Alch1 3-0-0; R46 4-0-0; R48 Village 2-0-2; R50 Sniper2 0-4-2; R57 0-5-2 on First; R81 Alch 5-2-0 ("during round, sword charge for safety"); R85 Sniper1 0-2-5; R86 Sniper3 3-2-0 on Strong top right of the alch; R89 4-2-0; R90/92/93 Snipers 4/5/6 at 0-3-2; R94 Glue 0-1-3 on Strong; R95 0-2-3; R100 Sniper3 5-2-0.
- Abilities: Sauda's Sword Charge on R81 is optional ("for safety").
- Conflicts: none.
**Strategy 3 - bloon.games written list (Sauda, Elite Defender, Prince of Darkness, Spirit of the Forest)** (source: https://bloon.games/how-to-beat-chimps-on-lost-crevasse/ , video 0NCRHYPxqo0 by BTD6 Master; about 1 year old (v50-era); confidence: verified-written-steps, order only, no rounds)
- Order: Sauda; Sniper1; Sniper2 on Strong 1-0-0; Village 0-0-2; Sniper1 0-2-2 -> 0-2-3 -> 0-2-4; Village 2-0-2 + Wizard 2-0-4; Sniper1 0-2-5; Wizard 2-0-5 (Prince of Darkness); Druid 2-4-0 -> 2-5-0; Sniper2 4-2-0; 3x Alch 4-2-0; 2x Wizard 4-0-2.
- No conflicts. The project's lostcrevasse_chimps.yaml header costs this list at about $208k at Hard prices against $178,909 earned by R100, so it is too expensive as written.
**Bot notes:** Strategy 1 needs no abilities, no aiming and no selling, and every tower stands on land around Sauda. It is the best fit for the bot. It also opens with Sauda alone at R6. The yaml header found Sauda's best cell reaches only 9% of the track, so check the opening against the guide's "top middle as high as possible" cell. Strategy 2's Sword Charge is optional. The bot's own Carrier Flagship build lost R95 several times (lostcrevasse_chimps.yaml Status), so switching to a guide build is justified. Targeting changes needed: Sniper1 Strong -> First, Glue Strong -> First.

### Luminous Cove (Intermediate)
**Map traits / what it requires:** Two lanes that alternate by round. Odd rounds enter top-left and run clockwise round the central heart pond. Even rounds enter top-right and run anticlockwise. The raised pre-waterfall track near both entrances is hidden from most towers. The heart pond is the only spot that reaches both lanes. Land is only the bottom strip, and every land spot reaches one lane only (the bot's land plan lost R49 on Hard). The Mermonkey secret needs tier-5 Mermonkeys and is not doable on this account. Effectively REQUIRED: water towers in the heart pond and/or a map-wide tower. Bloonswiki ranks Carrier Flagship first (ignores line of sight and buffs water towers about 17%), with Admiral Brickell. Heli also gets around the blockers.
**Strategy 1 - Brickell + Carrier Flagship + Crossbow Master + Spirit of the Forest** (source: https://www.youtube.com/watch?v=O65H67unAwA ; metaldevil; v45.3; confidence: video-description (written rounds, transcribed in docs/map_strategies.md))
- Hero: Admiral Brickell (R12).
- Core: Buccaneer 5-2-0 (Carrier Flagship), Dart 2-0-5 (Crossbow Master), Village 4-2-0, Druid 1-5-0, Alch 4-2-0, Glue 0-2-4, Sniper 4-0-2, Ice 4-0-2.
- Order: R6 Dart "closer to the darker bottom path" + Buccaneer; R7 Bucc 1-0-0; R12 Brickell; R13 Bucc 2-0-0; R14-18 Dart to 0-0-3; R19 Dart 2-0-3; R23 Bucc 2-2-0; R29 Dart 2-0-4; R35 Bucc 3-2-0, then Glue "as high into the corner as possible" (used as a marker); before R40 Village 1-2-0 next to the glue covering the dart; R40 Village 2-2-0; R48 Bucc 4-2-0 + Druid 1-3-0; R49 Druid 1-4-0; R71 Druid 1-5-0; R81 Bucc 5-2-0; R85 Dart 2-0-5; R88 Alch 4-2-0 next to the boat; R91 Glue 0-2-3; R94 Sniper 4-0-2 Strong; R95 Village 4-2-0; R96 Glue 0-2-4; R97 Ice 4-0-2.
- Abilities: R98-100 Brickell Mega Mine placed by hand near the top-right pool / BAD. This is targeted micro.
- Conflicts: none (Village 4-2-0 is within the cap).
**Strategy 2 - bloon.games Obyn ninja land build** (source: https://bloon.games/how-to-beat-chimps-on-luminous-cove/ , video fzoVygeCjno by BTD6 Master; about 1 year old; confidence: verified-written-steps but LOW reliability: the text looks machine-written and has no positions)
- Order: Ninja 1-0-1 -> R12 Obyn -> Ninja 3-0-2 -> 4-0-2; Village 0-0-2; before R40 Alch 4-2-0 next to the ninja; Village 2-0-2; Druid 2-4-0 -> 2-5-0; Spike 2-5-0 (Carpet of Spikes); Village 5-0-2 (Primary Expertise) for the Mega Ballista.
- Conflict: Primary Expertise is LOCKED. Cap the village at 4-0-2. That loses the Ballista, which this list uses as its late-game finisher. This is a land build, which the bot's geometry says covers one lane per spot. Not recommended.
**Other evidence (snippet-only):** Brickbrock subs-only black border, v44.1 (https://www.youtube.com/watch?v=SomxhKhswRg). "Fleet of Destroyers" black border, v44.1 (https://www.youtube.com/watch?v=oWvfmmF-6Dw). "Axis of Mermonkey" black border (https://www.youtube.com/watch?v=z883nQUiLcc), which uses tier-5 Mermonkeys, LOCKED on this account. A "53K spare cash" guide (https://www.youtube.com/watch?v=D49e5X89tUw) whose snippet says: without Mermonkey, buy the Sub on R25. RowdyAirplane92: "Icicle Impale makes a huge difference." Hbomb (8WMDOBXc73k): generic Silas + Icicle strategy (Silas is owned, so this is usable; no written steps). BTD6 Index cheapest LTC: Carrier Flagship 5-0-2 + Brickell.
**Bot notes:** Strategy 1 needs only boat/pond water spots and land around the dart. The only micro is Brickell's Mega Mine on R98-100. Pressing it blindly drops it at a default spot, which is UNVERIFIED as sufficient. No selling. This is the best fit for the bot. The Flagship deck is not used.

### Ancient Portal (Intermediate)
**Map traits / what it requires:** One entrance. The track spirals clockwise into a portal and then takes the right lane by default. The left (walled, "swirly", 24.42 RBS) lane is used only after clicking the free Realign Portal device, which has a 10 s cooldown. Two hero pedestals buff heroes (camo/MIB, +range/damage). Totems charged by 15,000 pops near the top portal blast the screen when clicked. There is a pond. Bloonswiki (v54.0): "middle-of-the-road", single lane, many bends. It recommends Pop and Awe (mortar 0-5-0; aiming needed), Perma-Spike, and Overdrive / Tack Zone at the bends. Fandom: undead bloons and Sauda's charge misbehave on the right lane. Nothing is strictly required; most comps work.
**Strategy 1 - BeatbloonsBob "No RNG": Quincy, Sub, WLP, Bloon Solver, Perma-Spike** (source: https://www.youtube.com/watch?v=RtSL6RUWAO4 ; BeatbloonsBob; about 9 months old (~v54-55); confidence: verified-written-steps, order only, no rounds)
- Hero: Quincy.
- Order: Sub 2-0-1; Alch 2-0-0 (Strong); Sub 2-0-3; Alch 3-0-1; Sub 2-0-4; Wizard 4-2-0; Village 2-0-0; Glue 4-2-0; Village 3-2-0; Glue 5-2-0 (Bloon Solver); Wizard 5-2-0 (Wizard Lord Phoenix); Village 4-2-0; Alch 4-0-1; Spike 2-0-5 (Perma-Spike) on Smart.
- Placements: not given. The sub must be in the pond. The bot geometry says the pond covers about 51% of the right lane, so keep the default right lane.
- Abilities: none listed. WLP's Phoenix ability is optional.
- Rounds inferred: Sub 2-0-4 by about R40 (MOAB) and Perma-Spike last (by R95) - inferred.
- Conflicts: none (Village 4-2-0 is within the cap).
**Strategy 2 - SnartFarts no ability / no micro (Obyn, Ninja, SotF, Popseidon, Flagship)** (source: https://www.youtube.com/watch?v=QbIVmJ2EPKU ; SnartFarts; v52.2; confidence: verified-written-steps, order only)
- Order: Ninja; Ninja 2-0-1; Obyn; Ninja 3-0-1; Alch; Alch 3-2-0; Ninja 4-0-1; Alch 4-2-0; Druid; Druid 1-4-0; Mermonkey; Mermonkey 0-4-2; Druid 1-5-0; Mermonkey 0-5-2 (Popseidon); Village; Village 2-3-0; Buccaneer; Buccaneer 5-2-0.
- Conflict: Mermonkey 0-5-2 is LOCKED (cap [4,4,4]). Stopping at 0-4-2 loses Popseidon, the guide's main late-game damage. Substitute: put the money into the Flagship earlier and/or a Perma-Spike as in Strategy 1 (inferred).
**Strategy 3 - BlueCliff Hard (reference, not CHIMPS)** (source: https://www.youtube.com/watch?v=-QdOnx826eA): Quincy; Ninja 4-0-2 by R33; Alch 4-0-1; Boomerang 5-0-2 (Glaive Lord) R65; Village 5-2-0 R79. Primary Expertise is LOCKED here, so cap the village at 4-2-0. Hard only.
**Bot notes:** Strategy 1 needs no abilities or aiming and all its upgrades are within the caps, so it is the best fit. Leave the portal unrealigned (default right lane) unless the plan puts short-range towers in the ruins. Totem clicks are optional. Put Quincy on a hero pedestal for its buffs (wiki). Spike on Smart is a one-time setting.

### Sulfur Springs (Intermediate)
**Map traits / what it requires:** One long lane (37.25 RBS) that loops round a central hot spring. Bloonswiki (v56.3): "by consensus the easiest Intermediate". The land sits on cliffs, and three low rocks make good bounce spots. The springs fill the inner loop, and the bot found that every land cell reaches at most about 14% of the track. Recommended: Ultra-Juggernaut on the low rocks (wall bounces); five Destroyers in the central spring with camo + Stronger Stimulant -> Permanent Brew; Admiral Brickell. No removables. Nothing is strictly required, but water (central spring) or wall-bouncing towers are what work.
**Strategy 1 - HyperF3 v56: Obyn, Wizard Lord Phoenix + Carrier Flagship** (source: https://www.youtube.com/watch?v=vm5zTKXFyAc ; HyperF3; v56, 2 months old; confidence: verified-written-steps, order only, ended with $44,689 spare)
- Hero: Obyn (placed second).
- Order: Wizard; Obyn; Wizard 2-0-0; Buccaneer; Wizard 2-0-2; Bucc 2-0-2; Wizard 3-0-2; Bucc 3-0-2; Bucc 4-0-2; Wizard 4-0-2; Wizard 5-0-2 (Wizard Lord Phoenix); Bucc 5-0-2 (Carrier Flagship); Glue; Glue 0-2-5 (Super Glue); Alch; Alch 4-2-0. The author says the alchemist "probably isn't even necessary".
- Rounds inferred: Bucc 3-0-2 Destroyer before R40; Flagship around R60-80; Super Glue before R95 - all inferred.
- Abilities: none mentioned.
- Conflicts: none.
**Strategy 2 - Axis of Sub, "mostly AFK"** (source: https://www.youtube.com/watch?v=7Dpd8wjn3Fw ; Gold-Games SK; about 2 years old (v41-42); confidence: snippet-only). The description says a "sun/sub commander carries until 80, but falls off vs super ceramics, and by that time we have pre emptive". So: Sub Commander (sub 2-0-5) to R80, then Pre-emptive Strike (sub 0-5-x). No written steps.
**Strategy 3 - wiki Destroyer fleet** (https://www.bloonswiki.com/Sulfur_Springs ; wiki, v56.3): 5 Destroyers (3-x-x) in the central spring with camo + Alch 4-2-0 -> 5-2-0 Permanent Brew; Brickell. No round list.
**Bot notes:** The project's sulfursprings_chimps.yaml (generic Flagship recipe, boat in the west pool) lost R95 repeatedly. Strategy 1 is a recent written build, has no abilities, and puts its boat where the source does (in the springs; check the spot is legal). It is the best fit. The bot has no Flagship deck to use and the guide does not need one. WLP has no aiming. Obyn is owned.

### Water Park (Intermediate)
**Map traits / what it requires:** Two lanes alternate every round. Odd rounds take the lazy river (17.8 RBS, bloons 10% slower). Even rounds take the waterslide (24.8 RBS). The slide is a sight blocker. Water towers can only go in the bottom pool, which has 3 floaties for land towers and does not reach the slide lane. Space is limited. Bloonswiki calls it "one of the most challenging Intermediate maps". Heli excels. Short-range towers belong on the pink slide, from where they shoot down straight lines of both paths. Recommended: Comanche Commander (heli 0-0-5) and MOAB Domination (boomerang 0-0-5 on the slide). Wiki tip: a 0-1-1 -> 0-2-2 Boomerang on the bottom centre of the slide carries the early game. Effectively REQUIRED: something that covers both alternating lanes, in practice global aircraft (ace or heli) or slide-placed towers.
**Strategy 1 - Rosalia + Flying Fortress** (source: https://www.youtube.com/watch?v=dYsOxUMQV_g ; OneEyedDeacon; v49.3; confidence: verified-written-steps)
- Hero: Rosalia (R16, workshop next to the slide, "put on circle").
- Core: Boomerang 0-2-2, Dart 0-0-0, Sniper 0-2-2, Ace 2-0-5 (Flying Fortress), Alch 3-2-0, Village 2-2-0.
- Order: R6 Dart1 on the edge of the slide + Boomerang1 next to it; R7 Boom 0-0-1; R8 0-0-2; R9 0-1-2; R11 0-2-2; R12 Sniper1 on Strong, left side of the slide's bottom circle; R16 Rosalia; R18 Sniper 0-0-1; R20 0-0-2; R21 0-1-2; R23 0-2-2 on First; R30 Village1 0-0-2; R32 Ace1 0-0-1 next to Rosalia; R33 Ace 0-0-2 "center path on bottom middle"; R35 Rosalia scatter missile on rainbows + Ace 0-0-3 during the round; R36 Ace 1-0-3; R37 2-0-3; R38 Alch1 2-0-0; R39 3-0-0; R41 Village 2-0-0 above the alch [sic: the guide already bought 0-0-2 at R30]; R42 2-2-0; R43 Alch 3-2-0; R55 Ace 2-0-4 (Spectre); R85 Kinetic Charge + jetpack + scatter missile once they break open; R87 same; R88 Ace 2-0-5.
- Abilities: Rosalia's scatter missile (R35), Kinetic Charge / jetpack / scatter missile (R85, R87), each timed for when the blimps "break open".
- Conflicts: none. The village line is inconsistent in the text (0-0-2 at R30, then 2-0-0/2-2-0); read it as 2-2-0 in the end (inferred).
**Other sources (video-only):** Punji "Waterpark Chimps Guide in 60 Seconds" (87k views, about 3 years old, https://www.youtube.com/watch?v=yQ_SCS7sMxY). Culture "No abilities/Micro" (https://www.youtube.com/watch?v=r0DP8BMp6aE, 7 months old). Tadomika (ZEYL9gm5ZXk). wellordering (Pxor5NgbBZI) also uses Rosalia. I could not read the steps of any of them.
**Bot notes:** The ace's Centered Path needs a hand-placed centre ("bottom middle"), which is aiming. The bot must use the default circle path or a fixed preset; UNVERIFIED whether that suffices. Rosalia's abilities are timed to blimp breaks on R85/R87; pressing them blindly at round start would fire early. The ace 2-0-5 itself does not need the abilities on R88+. Strategy 1 is the only written one and still the best available. Alternative for the bot (wiki, inferred): Comanche Commander (heli 0-0-5, Pursuit/default) replacing the ace avoids aiming. Do not rely on the pool alone: it misses the slide lane.

### Polyphemus (Intermediate)
**Map traits / what it requires:** Two lanes run at the same time (21.94 RBS each) and interweave on the C-shaped island. They travel once round the eye. The eye (pond) gives towers inside it a 15% discount, +17.6% attack speed and camo detection. It closes at the end of every round ending in 5 and disables its towers (the only map feature that disables rather than sells). Reopening costs $0 on R6-15 and rises $500 every 10 rounds, so keeping it open through R80 costs $14,000 and through R100 about $22,500 (fandom; bloonswiki says $26,000). Walls/trees are removable ($500 each, 8 on bloonswiki). Fandom: do not put an Arctic Wind on the pond. Recommended: Carrier Flagship 5-2-0 in the eye + Brickell; Giant Condor (Beast Handler) drags blimps. Land above and below the eye covers the loop best. Nothing is strictly required.
**Strategy 1 - bloon.games: Obyn, Monarch of Storms + Elite Defender + Perma-Spike** (source: https://bloon.games/how-to-beat-chimps-on-polyphemus/ , video PZ-FQyXy8Lo (BTD6 Master); v~45-48; confidence: verified-written-steps, order only)
- Hero: Obyn Greenfoot (boosts the druid).
- Core: Druid 5-0-2 (Monarch of Storms), Sniper 0-2-5 (Elite Defender), Village 2-0-2, Alch 4-2-0, Spike 2-0-5 (Perma-Spike).
- Order: Druid; Sniper; Obyn; Village 0-0-2; Sniper 0-2-2 -> 0-2-3; before R40 Sniper 0-2-4 + Village 2-0-2; Alch 4-2-0 next to the sniper; Sniper 0-2-5; Druid 4-0-2 (Ball Lightning), then save; Druid 5-0-2; before R96 Spike 2-0-5.
- Placements: not given, except the alch next to the sniper.
- Abilities: Obyn's abilities are optional ("to get through the early rounds faster", i.e. speed).
- Conflicts: none.
**Other sources (snippet-only, no steps read):** "All Three Tier-5 Tack Shooters" black border, v36.1 (https://www.youtube.com/watch?v=J2EHq88A2Zg). Polyphemus CHIMPS "Safe & Easy", v36.1 (https://www.youtube.com/watch?v=9QPymnrKt7o). An Obyn walkthrough (https://www.youtube.com/watch?v=pdiDKSC9QYU). ZoozieBloons CHIMPS (named in project docs). BTD6 Index records were not checked here.
**Bot notes:** The bloon.games build has no aiming, no abilities and no selling. It does not say whether towers go in the eye. If the bot puts them on land (above/below the eye), the eye mechanic is avoided entirely. That is safest for the bot, which may not reliably reopen the eye after rounds 15, 25, ... (towers in a closed eye are disabled, not lost). Keep the Perma-Spike on an exit that both lanes share, or note it covers one exit only (both lanes run at once). The two simultaneous lanes are the coverage risk.

### Covered Garden (Intermediate)
**Map traits / what it requires:** One lane (about 19.8 RBS). Three of the four garden quarters are under glass at any time. The open quarter rotates clockwise each round: BL on R1, then TL R2, TR R3, BR R4, BL R5, TL R6 (TL is open on rounds ≡ 2 mod 4). Under glass you cannot place or upgrade, but attacks and abilities still work, and the glass does not block sight. Global towers (heli, Centered Path, mortar/dartling targeting) work freely. Outside the garden there are only narrow left and right strips. Recommended: Corvus at the front (farms mana, can Spirit Walk), Geraldo outside the garden, Comanche Commander outside the garden. Effectively REQUIRED: pane-timed upgrades or global towers on the open strips.
**Strategy 1 - Rosalia + Flying Fortress** (source: https://www.youtube.com/watch?v=u0-X2o8hfQQ ; OneEyedDeacon; v50.0; confidence: verified-written-steps)
- Hero: Rosalia (R13, in front over the entrance track, then "move to bend").
- Core: Desperado x2 0-0-0, Druid 1-3-0, Sniper 0-2-2 (bench), Village 2-2-0, Ace 2-0-5, Alch 3-2-0.
- Order: R6 Desperado1 next to the fountain + Desperado2 bottom-left of the fountain seeing the start of the track; R9 Druid1 in front (under the track); R13 Rosalia; R14 Druid 0-1-0; R18 Sniper1 0-1-0 on the bench, Strong; R21 scatter missile; R22 Druid 0-3-0; R26 Sniper 0-2-1 on First; R27 Druid 1-3-0; R30 Sniper 0-2-2; R32 Village1 above Rosalia; R33 Ace1 above Village1; R34 Ace 0-0-1; R35 0-0-2 "center path on top right"; R37 0-0-3; R38 2-0-3; R40 Alch1 3-0-0 above the ace; R42 Village 0-2-0; R43 Alch 3-2-0; R44 Village 2-2-0; R56 Ace 2-0-4; R88 Ace 2-0-5 during the round.
- Placements: the garden towers (desperados, bench sniper) are all bought on TL-open rounds (6, 18, 26, 30), consistent with the pane cycle. Druid, Rosalia, village, ace and alch are on the left strip outside the garden.
- Abilities: Rosalia scatter missile R21. Moving Rosalia to the bend on R13 is micro.
- Conflicts: none.
**Strategy 2 - Tadomika Elite Defender "special placement to ignore the obstacles"** (https://www.youtube.com/watch?v=Hlr18_Sz-vk ; 8 months old; confidence: snippet-only). Etienne no-ability (metaldevil, v49.3, https://www.youtube.com/watch?v=2Vwl5NnG_kA) and Quincy (Cosmos, https://www.youtube.com/watch?v=7E_PmzhAesU) runs exist with no written steps. BTD6 Index LTCs: Monarch of Storms 5-0-2 + Geraldo / + Blazing Sun.
**Bot notes:** Strategy 1 already times garden purchases to TL rounds, so the bot's pane-aware executor can follow it. The issues are the ace's Centered Path ("top right"), which is aiming (use the default path; UNVERIFIED), and the Rosalia move/scatter missile (pressing blindly on R21 is probably fine). The bot's earlier coveredgarden attempts ran out of strip spots; this build uses only 4 strip towers + Rosalia. Best available fit.

### Quiet Street (Intermediate)
**Map traits / what it requires:** Non-MOAB bloons enter from both ends of the sidewalks (top and bottom) and leave by the other side. MOAB-class bloons use only the road from bottom to top. That makes the early and mid game hard and the late game simpler (bloonswiki). Cars ($250 x5) and frozen ponds ($500 x2) are removable; there is no water until a pond is bought. Cars and walls block sight. The main defence should focus on the top side (fandom). Recommended: Corvus; Bloon Exclusion Zone (dartling 2-0-5, on the far right, with Stronger Stimulant + Acidic Mixture Dips); Carpet of Spikes 2-5-0 (outer-ring spikes hit MOABs without being eaten by ceramics; "eliminates all concerns for Round 100"). Heroes like Obyn, Ezili, Adora and Etienne can shoot over the wall to both lanes. Nothing is strictly required, but long-range towers are needed for the two-sided sidewalks.
**Strategy 1 - Maxalph no hero, no abilities (sniper wall)** (source: https://www.youtube.com/watch?v=lwkCrJI-7DE ; Maxalph; about 4 years old (~v29-31, OLD; balance has changed since); confidence: verified-written-steps)
- Hero: none.
- Core: about 7 snipers (0-5-2, 4-2-0, 0-4-2/0-3-2 several), Tack 5-0-2 (Inferno Ring), Alch 4-0-1 x2 + 4-2-0, Village 2-0-2 + 4-2-0, Spike 3-2-0, Glue 0-2-3.
- Order: R6 +1 Dart, +1 Sniper (Strong); R8, R10, R11 +1 Sniper each (Strong); R16 Tack 2-0-2; R18 Tack 3-0-2; R22 Sniper A 0-2-1; R24 0-2-2; R27 Sniper B 1-2-0; R35 Sniper A 0-3-2; R38 Alch 3-0-0 + Sniper B 2-2-0; R40 Sniper C 0-2-2 (First); R43 Village 2-0-2; R48 Sniper A 0-4-2; R49 Sniper B 3-2-0; R50 Sniper D 0-3-2 + Sniper E 0-2-2 (First); R58 Sniper A 0-5-2; R63 Alch 4-0-1 + Spike 3-2-0; R65 Tack 4-0-2; R72 Sniper B 4-2-0 + a sniper 0-3-2; R85 Tack 5-0-2; R89 Village2 4-2-0; R91 Alch2 4-2-0; R94 Alch3 4-0-1 + a sniper 0-4-2; R96 another sniper 0-4-2; R97 Glue 0-2-3 (Strong).
- Placements: not given.
- Abilities: none.
- Conflicts: none (Village 4-2-0 is OK). Adding Quincy (owned) is a likely improvement (Febh's no-micro Quincy run, https://www.youtube.com/watch?v=_1gssI4uYnA, video-only).
**Strategy 2 - wiki BEZ / Carpet of Spikes / Corvus** (https://www.bloonswiki.com/Quiet_Street ; confidence: wiki, no round list): Corvus early -> Dartling 2-0-4 (BADS) saved up to 2-0-5 BEZ on the far right + Alch 4-2-0 + 4 Acidic Mixture Dip alchs; Spike 2-5-0 Carpet of Spikes for DDTs/R100. Dartling 2-0-5 is within the cap ([5,4,5]). BEZ "attack in all directions" needs no aiming once it is BADS/BEZ (per fandom).
**Bot notes:** Strategy 1 is fully passive (no hero, no abilities, Strong/First targeting only), but it is old. Snipers are global, which suits the two-sided lanes. Pick sniper cells with sight of both sidewalks and the road (cars block sight; buying cars at $250 is possible). Strategy 2 needs no aiming either, but has no written order. Recommended: Strategy 1 with Quincy added at R6, plus the wiki's Carpet of Spikes 2-5-0 as a late safety net (inferred).

### Bloonarius Prime (Intermediate)
**Map traits / what it requires:** Lanes alternate. On prime rounds (2, 3, 5, 7, 11, ... 83, 89, 97) bloons take the short right "prime" lane (17.4 RBS, awkward layout). All other rounds take the long left "composite" lane round the lake (21.5 RBS). The rock/tree column in the middle blocks sight. Few spots cover both lanes. Bloonswiki (v57.4): "among the most difficult Intermediate maps". The prime lane never gets DDTs or purples before R101, so only the composite lane needs DDT/BAD answers. Recommended: Corvus at the entrance, Geraldo (shop refresh at R95), Heli Pilot (unlimited range on alternating lanes); fandom also suggests Golden Eagle + Gyrfalcons and Smart Spikes. Effectively REQUIRED: global aircraft (heli/ace) or snipers with sight of both lanes; a single exit spike fails (the bot lost Deflation at R49).
**Strategy 1 - Rosalia + Flying Fortress** (source: https://www.youtube.com/watch?v=mLpg86Zc7Rs ; OneEyedDeacon; v49.3; confidence: verified-written-steps)
- Hero: Rosalia (R14, on top, leaving room for a village above).
- Core: Dart x3 0-0-0, Sub 0-0-0, Sniper 0-2-2, Druid 1-3-0, Village 2-2-2 (0-0-2 then 2-2-0 as written), Ace 2-0-5, Alch 3-2-0.
- Order: R6 Dart1 on Strong (left top intersection) + Dart2 between the tracks at the bottom; R7 Sub1 on the right splitting the two halves of the right lane; R8 Dart3 at the bottom-left intersection; R10 Sniper1 Strong at the bottom; R14 Rosalia; R16 Druid1 on the right; R17 0-1-0; R19 move Rosalia right; R20 move left + swap to grenade; R21 scatter missile at start; R22 Druid 0-3-0 (during round); R24 Sniper 0-1-0; R25 Druid 1-3-0; R27 Sniper 0-1-1; R28 0-1-2; R29 0-2-2 on First; R35 Village1 0-0-2; R36 Ace1 0-0-2; R38 0-0-3; R39 2-0-3; R40 jetpack + scatter missile; R42 Village 0-2-0 (as written); R43 2-2-0; R44 Alch 3-0-0; R45 3-2-0; R56 Ace 2-0-4; R89 Ace 2-0-5.
- Abilities: Rosalia moves (R14, R19, R20), grenade swap, scatter missile R21, jetpack + scatter R40.
- Conflicts: none.
**Strategy 2 - MaxMonki: Obyn, "no abilities or other micro"** (https://www.youtube.com/watch?v=zK3Q3JzP8k4 ; about 1 year old, "Works in 2026"; confidence: snippet-only, video-only steps): "You need Obyn and a couple monkeys." No tower list readable.
**Strategy 3 - BlueCliff Hard (reference)** (https://www.youtube.com/watch?v=oIiUcr4qJAw): Quincy, Ninja 4-0-2 R33, Alch 4-0-1 x2, Boomerang 2-0-4 R39, Ace 2-0-3 R48 -> 2-0-4 R61, Village 2-2-0, Sniper 4-0-2 R74. Hard only, not CHIMPS. The ace is Spectre-path.
**Bot notes:** Strategy 1 leans on Rosalia micro: moving her between lanes on R19-20 matches the alternating lanes. The bot can press abilities on a round, but cannot drag/move Rosalia. UNVERIFIED whether her default position covers both lanes. The ace's default path (no Centered Path given here) is fine. The bot's previous build should mirror the ace + sniper core; R40 abilities can be pressed blindly at round start. For a no-micro alternative, the MaxMonki Obyn video would need watching. The wiki's Comanche/heli on Pursuit is the aiming-free global option.


Research note (applies to all maps): extra web research this session added little. bloonswiki returned 403, fandom /Strategies subpages returned 402, the breezewiki mirror was bot-blocked, and YouTube rate-limited (429 / Google "sorry" page) every description fetch. Reddit and Steam searches found no map-specific CHIMPS threads for these maps. Almost everything below therefore comes from the pre-gathered bundle (bloon.games, YouTube descriptions, wiki text) plus the project docs and lost-build headers. Upgrade names given next to crosspaths are my own reading of the crosspath; where I was unsure I left the name out. Anything not in a source is marked "inferred" or "UNVERIFIED".

---

### Balance (Intermediate)
**Map traits / what it requires:** Bloons enter from 2 entrances (left and right edge) and split into 8 sub-paths. All of them wind around one big central loop, then leave by 2 exits. Hedges block sight and leave only small plots. There is water (a bottom pond) and no removables. The centre of the loop is the key spot: tack, Sauda, ice, alchemist and mortar targeted on the loop all gain greatly (bloonswiki). No map-wide tower is required, because the central loop lets short-range towers see every lane. **Bot problem:** the project doc (docs/map_strategies/intermediate_a.md, Balance) says "most central plots are refused in the live model (gap 6); only the right entrance is modelled (gap 3)". Every proven CHIMPS strategy below puts its core tower in the centre, so the bot must be able to place there first.

**Strategy 1 - Lazy Inferno Ring + Super Brittle (5 stops)** (source: https://www.youtube.com/watch?v=apOdpf5OR7M, BTD6 BluePrint, ~2 months old (v5x era); confidence: video-description, written round steps)
- Hero: Sauda (top middle), placed R6.
- Core towers: Tack Shooter 5-0-2 (Inferno Ring), Ice Monkey 5-2-0 (Super Brittle), Alchemist 4-2-0 (Stronger Stimulant).
- Purchase order: R6 Sauda (top middle) -> R15 Tack 3-0-2 (top middle) -> R37 Tack 4-0-2 (Ring of Fire) + Ice 4-2-0 (Embrittlement, middle) -> R66 Tack 5-0-2 -> R90 Ice 5-2-0 + Alchemist 4-2-0 -> R100 win. The author says these are the *latest* safe rounds; buying earlier is fine.
- Key placements: Sauda and the tack at the top middle of the central loop; the ice in the middle; the alchemist next to the tack (it buffs the tack late).
- Abilities used: none ("no abilities").
- Account conflicts / substitutes: none (ice 5-2-0, alchemist 4-2-0 and tack 5-0-2 are all unlocked).

**Strategy 2 - bloon.games written: Inferno Ring + Prince of Darkness + village** (source: https://bloon.games/how-to-beat-chimps-on-balance/ with video https://www.youtube.com/watch?v=3rTODcd3KDA, BTD6 Master, ~1 year old; confidence: verified-written-steps)
- Hero: Sauda (upper middle); abilities optional for early speed.
- Core towers: Tack 5-0-2, Wizard 2-0-5 (Prince of Darkness), Village 5-2-0 (Primary Expertise).
- Order: Tack in the centre, quickly to 3-0-2 -> R28 Tack 4-0-2 -> before R40 Wizard 2-0-4 (Necromancer) -> R45 Village 4-2-0 (camo + buff for the tack) -> R72 Tack 5-0-2 -> R82 Wizard 2-0-5 -> R89 Village 5-2-0.
- Abilities: none needed.
- Account conflicts: **Village 5-2-0 (Primary Expertise) is LOCKED** (village top path caps at 4). Substitute: stop at Village 4-2-0, then add Strategy 1's Ice 5-2-0 and/or Alchemist 4-2-0 with the money saved (inferred).

**Strategy 3 - BeatbloonsBob "World's Easiest Balance CHIMPS"** (source: https://www.youtube.com/watch?v=wWIBqJ4bTOA, ~8 months old; confidence: video-description, ordered steps, no round numbers)
- Hero: Sauda.
- Order: Sub 2-0-1 -> Boomerang 3-0-2 -> Sub 2-0-4 -> Boomerang 4-0-2 -> Alchemist 3-2-0 ("Strong" targeting) -> Wizard 0-2-4 -> Buccaneer 5-2-0 (Carrier Flagship) -> Boomerang 5-0-2 (Glaive Lord) -> Wizard 0-2-5 (Prince of Darkness). Optional: Spike Factory 2-0-5 (Perma-Spike) at the exit "for safety".
- Account conflicts: none. Nothing is placed on the Flagship deck.

**Bot notes:** All three strategies are no-ability and need no aiming. The only one-time settings are Alchemist "Strong" and Spike Factory targeting. Strategy 1 is the best fit for the bot: only 4 towers, 5 stops, no locked tiers, and written rounds. The blocker is placement: the tack (and Sauda) must sit at the top middle of the central loop, which the live model currently refuses. Fix the refused-plot data for Balance before trying. Strategy 2 needs the Primary Expertise substitution.

---

### Encrypted (Intermediate)
**Map traits / what it requires:** One entrance that splits at once into 2 lanes with 2 exits (half the bloons take each). A walled crypt sits in the middle. Its interior is small but has "by far the best coverage of the track" (bloonswiki). The walls block line of sight and make projectiles bounce, which favours Ultra-Juggernaut, Glaive bounces and Arctic Knight's Ice Jet. Four $250 grave pads open class-restricted spots (the Military altar water takes military towers only). Grass outside the crypt sees only 8-10% of an exit; a sniper on the bottom grass sees about 44% of each lane (project doc). **Bot problem:** the project doc says "the walled middle and the four $250 class pads are closed to the bot". Every proven strategy uses the crypt interior or a heli. Without the crypt, map-wide damage (heli, sniper, Flagship planes, Prince of Darkness, which collects graves through walls) is effectively required.

**Strategy 1 - Sauda + Ultra-Juggernaut + Prince of Darkness in the crypt** (sources: bloonswiki Encrypted recommended towers (in bundle); https://bloons.fandom.com/wiki/Encrypted tips; confidence: wiki, no round steps)
- Hero: Sauda in the crypt centre, with Berserker Brew and Relentless Glue support (wiki). Ezili or Corvus are the wiki's alternatives for Prince of Darkness.
- Core towers: Dart 5-x-x Ultra-Juggernaut inside the crypt (walls make the balls re-hit; pair with Berserker Brew); Wizard x-x-5 Prince of Darkness (graveyard fills through the wall; zombies spawn inside and clean up DDTs and super ceramics; also a decamo option); Carrier Flagship for map-wide blimp damage; Arctic Knight (Mermonkey 4-x-x, Ice Jet ability bounces in the crypt); a Radar Scanner village on the altar so the altar towers get camo (fandom).
- Round timings: none in the sources (UNVERIFIED).
- Account conflicts: Wiki's "The Final Harmonic" (Mermonkey bottom tier 5) is **LOCKED** (Mermonkey caps at 4). Arctic Knight (4-x-x) is fine; its Ice Jet is an ability.

**Strategy 2 - Heli as main DPS with Sauda + dart opening** (source: https://www.youtube.com/watch?v=3RHVoFwgyLY, Gold-Games SK, ~3 years old; confidence: video-description, towers only)
- Hero: Sauda. Early game is Sauda + Dart while saving up for the heli; Sauda's ability was timed on R14 ("close to being rng").
- The description gives no crosspaths. Related title from search: "Encrypted Safe and Easy CHIMPS Black Border Guide | Apache Prime + Archmage" (https://www.youtube.com/watch?v=4RW_ZXxYX6g; snippet-only), which says rounds 41-46 need no player action.
- Account conflicts: none known.

**Other evidence (snippet-only):** wellordering's Encrypted video (https://www.youtube.com/watch?v=fayqBSMWdrI, 5k views) says "You can make early game much easier by adding 2 Subs" (towers otherwise unknown). ebylxn won with "Glord" (Glaive Lord) at 77k spare (https://www.youtube.com/watch?v=4F22rDI7DzE). Ethan Reid's "easiest" guide is no-micro, no-RNG (https://www.youtube.com/watch?v=bo4tXL27eW4, v21 era, towers unknown).

**Bot notes:** No written round-by-round guide was found. The bloon.games page is video-only, and YouTube descriptions could not be fetched beyond the bundle. The bot's current placement data closes the crypt, and that kills Strategy 1. Options:
- (a) Make the crypt interior placeable, then use Strategy 1 (no aiming; only Arctic Knight / Sauda abilities, which are optional).
- (b) Use map-wide damage: an Apache Prime / Pursuit heli (one-time "Pursuit" targeting from top-path tier 2, or Lock Place; inferred) plus a Wizard 5-x-x Archmage, per the 4RW_ZXxYX6g title. The project's Medium build already uses Pursuit helis and snipers here.

Prince of Darkness works through walls, so it suits a bot that cannot place inside. Flag Sauda's ability timing as micro (R14 in the heli guide).

---

### Bazaar (Intermediate)
**Map traits / what it requires:** Two lanes that **alternate by round** (top left-to-right, bottom right-to-left). They are short (~23 RBS) and S-bend through the middle. Market stalls block sight; four palm trees cost $500 each to remove. Land is scarce, and per the project doc no heli pad fits. A canal by the bridge reaches both lanes' middle stretches. The middle strip sees both lanes. Map-wide and lane-swapping towers shine: Corvus, Carrier Flagship + Brickell, Prince of Darkness 1-0-5, Comanche Commander + Glue Storm (bloonswiki). Wiki rates Bazaar "among the most difficult Intermediate maps". Mortars can reliably target the starts of the tracks (fandom).

**Strategy 1 - Rosalia + Flying Fortress (OneEyedDeacon)** (source: https://www.youtube.com/watch?v=nyw0_VLPl38, OneEyedDeacon, v49.3, ~1 year old, 10k views; confidence: verified-written-steps)
- Hero: Rosalia (R14, on the left).
- Core towers: 3 darts, a boomerang, Druid 1-3-0, Sniper 0-2-2, Village 2-2-0, Ace 2-0-5 (Flying Fortress), Alchemist 3-2-0.
- Exact order:
  - Opening: R6 Dart 0-0-0 (right) + Dart 0-0-0 on Strong (middle) + Dart 0-0-0 (left) -> R8 Boomerang 0-0-0 on Strong, left of dart2 -> R11 Druid 0-0-0 right of dart2 -> R14 Rosalia (left) -> R15 Druid 0-1-0 -> R17 Sniper 0-0-0 "lined up with top row" -> R18 Sniper 0-1-0 -> R20 Sniper 0-2-0 -> R22 Scatter Missile (Rosalia ability) at round start -> R25 Scatter Missile for the purples -> R26 Druid 0-3-0 -> R27 Druid 1-3-0 -> R28 Sniper 0-2-1 -> R29 Sniper 0-2-2.
  - Mid game: R36 Village 0-2-0 -> R40 Ace 2-0-3 + both Rosalia abilities -> R42 Alchemist 3-0-0 -> R43 Alchemist 3-2-0 -> R45 Village 2-2-0 -> R56 Ace 2-0-4 (Spectre) -> R88 Ace 2-0-5 (Flying Fortress) -> win.
- Abilities used: Rosalia's Scatter Missile on R22 and R25, both abilities on R40.
- Account conflicts: none (Ace 2-0-5 and Village 2-2-0 are unlocked; Rosalia is owned).

**Strategy 2 - Carrier Flagship + Brickell** (source: bloonswiki Bazaar recommended towers; confidence: wiki, no steps)
- Brickell instead of Corvus: Mega Mines, plus Naval Tactics, which gives the front darts DDT-popping power. The Flagship "can sweep through every round up until the late 80s". The canal is the water spot.
- Late wincon: Prince of Darkness 1-0-5 (spawn point can follow the active lane) or Comanche + Glue Storm (wiki).
- Account conflicts: none for Flagship. Comanche is fine on the account, but the project doc says no heli pad fits.

**Other sources (no steps):** Alatreon "updated for v48" (https://www.youtube.com/watch?v=hU8K-K7lk5I). metaldevil "EASY CHIMPS on Bazaar with Etienne (v56.3)" (https://www.youtube.com/watch?v=ed6xO4Frw-c) is the newest-version proof, but its towers are unknown.

**Bot notes:**
- Strategy 1 is the best fit: written per-round steps, an owned hero, no locked tiers.
- Abilities: Rosalia's must be pressed at the start of R22, R25 and R40. Pressing blind at round start matches the guide's intent ("at start").
- Targeting: two darts and the boomerang are set to "Strong" (a one-time setting). The ace stays on default targeting; the guide mentions no setting. Ace 2-0-x unlocks Centered Path, but the guide does not say to use it.
- Placement: the darts are packed in the middle strip, and the sniper "lined up with top row". The bot's Medium notes say the live game refuses most grass, so check the ace footprint fits.

---

### Spring Spring (Intermediate)
**Map traits / what it requires:** Two simultaneous lanes from the same entrance to the same exit, looping around the big island and two back islands. Over 40% of each lane is off screen. There are no removables, and the sight blockers are non-intrusive. Towers do best at the right end of the large island and in the water at the exit, where both lanes meet. Wiki recommends: map-wide blimp damage (Aircraft Carrier / Flagship) to stagger blimps; Perma-Spike at the bottom-right of the island just above the exit, on "Smart" (with Berserker Brew + Jungle Drums), to stop exit leaks; Glaive Lord at the back. Boss bloons take the top path (fandom).

**Prior bot result:** the bot's Flagship recipe (springspring_chimps.yaml) lost R9 in the opening, then twice at R95 (camo regrow purples/leads + 30 camo DDTs + fortified MOABs) with the model rating 0.51-0.82. So a Flagship + Quincy + Glaive Lord + Cripple MOAB build is not enough here. Every real guide below adds a stall/exit tower (Perma-Spike, Super Brittle ice, Pre-emptive Strike sub, glue).

**Strategy 1 - CrimsonPlanet: Etienne + Flagship + Arctic Knight + Pre-emptive Strike + Super Brittle** (source: https://www.youtube.com/watch?v=8oRUiaBFsHY, CrimsonPlanet, v53.2, ~7 months old; confidence: video-description, ordered steps without round numbers, "No Micro & Abilities")
- Hero: Etienne (shares camo detection via his drone).
- Order: Sub 0-0-0 -> Mermonkey 0-0-0 -> Etienne -> Buccaneer 3-2-0 (Destroyer) -> Mermonkey 4-0-1 (Abyssal Warrior; Arctic Knight would be 0-4-1 - which the guide means is unverified) -> Buccaneer 5-2-0 (Carrier Flagship) -> Sub 0-5-0 (Pre-emptive Strike, passive missiles at each blimp spawn) -> Ice 5-2-0 (Super Brittle) -> Village 2-3-0 (MIB).
- Optional: Alchemist 0-3-0, Mermonkey 5-0-1, Glue 0-5-0 or 0-2-4.
- Abilities: none. Arctic Knight's and Pre-emptive Strike's abilities are not used, per the title.
- Account conflicts: optional Mermonkey 5-0-1 (Popseidon) is **LOCKED**; skip it (it is optional). Everything else is unlocked.

**Strategy 2 - BloonBeast: Buccaneer 4-2-0 into Perma-Spike, Etienne, glue + ice** (source: https://www.youtube.com/watch?v=q2qD9oYfOjw, BloonBeast, ~1 year old, "no abilities, 62K cash spare"; confidence: video-description, towers only)
- Hero: Etienne ("shared camo detection").
- Core: Buccaneer 4-2-0 (Aircraft Carrier) for a strong early/mid game and an easy save into Perma-Spike (Spike Factory x-x-5; the usual crosspath is 2-0-5, inferred). Glue and Ice "maximize the round durations to make full use of Perma spikes" for the end-game stall. Exact crosspaths/rounds: UNVERIFIED.
- Account conflicts: none expected.

**Strategy 3 - NamelessBandicoot: Churchill + Bloon Solver + Master Bomber + Perma-Spike** (source: https://www.youtube.com/watch?v=yklSfE_zpIo, ~1 year old; confidence: video-description)
- Churchill; Glue 5-x-x (Bloon Solver, over 1 million pops); Bomb x-5-x? (Master Bomber, crosspath not given); Perma-Spike; a camo village (get it earlier than the author did); an alchemist for the glue and Churchill.
- Account conflicts: none.

**Bot notes:**
- Strategy 1 suits the bot: no abilities, no aiming. Pre-emptive Strike fires passively, so no ability timing is needed. Every tower is unlocked and nothing goes on a deck.
- The bot's own failures were the opening (R9) and R95. Strategy 1's early game is Sub + Mermonkey + Etienne + Destroyer, not Quincy plus one boat. Its R95 answer is Pre-emptive Strike + Super Brittle + MIB.
- Perma-Spike (Strategy 2) needs one setting, "Smart", at the wiki spot above the exit. This is the classic leak-stopper and fits the owner's point about stall/exit towers.

---

### Moon Landing (Intermediate)
**Map traits / what it requires:** One long lane (~40 RBS, 1,110-1,242 units) that loops through three walled craters. There is no water and no removables. The crater walls block line of sight for most land towers. Aliensrock: "REALLY bad for anything that isn't mortar or heli pilot". The fandom tips say:
- mortars work without micro because the craters keep bloons in place;
- the alchemist works as a starter thanks to thick loops;
- Archmage ignores the crater walls, and with range buffs it can see into all craters from the middle.

**Effectively required:** map-wide or wall-ignoring damage (sniper on the high ground / Elite Defender, Archmage, heli, mortar).

**Prior bot result:** lost R7 twice (moonlanding_chimps.yaml) with 3-dart and 2-desperado openings, the second by ONE red. The darts covered 13% of the track. The proven guides open with darts too but add a Sniper on high ground immediately (BeatbloonsBob) or a Wizard + Obyn (Mtx).

**Strategy 1 - BeatbloonsBob: Obyn + Elite Defender + PoD + Archmage** (source: https://www.youtube.com/watch?v=cSmSH9JAgBQ, ~9 months old, "No abilities or micro", $50k spare; confidence: video-description, ordered steps without rounds)
- Hero: Obyn (4th purchase).
- Order: Dart 0-0-0 ("Close" targeting) -> Sniper 0-0-0 "as high as you can where I place it" -> Dart 0-0-0 -> Dart1 0-1-0 -> Dart2 0-1-0 -> Obyn -> Sniper 0-2-2 -> Heli 3-0-2 -> Sniper 0-2-4 -> Village 2-2-0 -> Sniper 0-2-5 (Elite Defender) -> Wizard 0-2-5 (Prince of Darkness; "same targetting location as me") -> Wizard 5-2-0 (Archmage) -> Alchemist 4-0-1. Optional: Spike Factory 2-0-5 at the end.
- Abilities: none.
- Account conflicts: none.

**Strategy 2 - Mtx: Archmage + Ultra-Juggernaut + Perma-Spike + Icicle Impale** (source: https://www.youtube.com/watch?v=TrPkZWsBzOg, Mtx, 13 days old (current version); confidence: video-description, chapters only)
- Hero: Obyn.
- Final core: Wizard 5-2-0 Archmage, Dart 5-0-2 Ultra-Juggernaut, Spike Factory 2-0-5 Perma-Spike, Ice 0-2-5 Icicle Impale, Village 2-3-0.
- Chapter order: three-Dart opening -> Wizard and Obyn -> Spike-o-pult and early upgrades -> Spike Factory -> R40 + Arcane Spike (Wizard 4-x-x) -> Ultra-Juggernaut -> R63 -> Archmage + Village -> Deadly Spikes + targeting -> Perma-Spike -> Ice -> Icicle Impale, R98 -> R100.
- Mentions "spike targeting" (a one-time setting; which setting is UNVERIFIED).
- Account conflicts: none.

**Other sources:** Kronk33 mortar strategy (https://www.youtube.com/watch?v=ifDmX_cpiF0, no steps). H2K Zeus "three Wizards" (https://www.youtube.com/watch?v=1Uwh8f7FGks, ~3 years old). Yars v19.2 (works on 27.x) with brambles once, no Wall of Trees (https://www.youtube.com/watch?v=AtEHtaPWYnU; old). Aliensrock Apache Prime (very old).

**Bot notes:**
- Strategy 1 is the best fit: no abilities, every tier unlocked, and the sniper is map-wide.
- Opening: the bot's own loss shows the darts alone are marginal. Follow Bob's order exactly: the sniper is the 2nd tower, at the highest point, and the darts take Sharp Shots early.
- Heli 3-0-2: the bot needs a fixed heli mode. "Lock Place" over a crater is a one-time setting; follow-touch is not usable. Mark which mode Bob used as UNVERIFIED.
- PoD "same targeting location": UNVERIFIED which priority.
- Avoid mortar strategies unless the bot can set a mortar target once.
- Required map-wide pieces: Elite Defender sniper and Archmage.

---

### Haunted (Intermediate)
**Map traits / what it requires:** Two simultaneous, overlapping lanes with separate entrances and a short track (~21 RBS). You cannot see leaks easily. Two trees can be removed ($500 each). Wiki ranks it "among the more difficult Intermediate maps". The central pond lets water towers hit both sides: Destroyers / Flagship + Stronger Stimulant -> Perma-Brew; Brickell (+1 pierce for water towers, Naval Tactics, Mega Mines); Bloontonium Reactor sub in the centre for decamo. The bottom bends still allow land strategies. Effectively required: water towers in the central pond (strongly favoured, not strictly required).

**Strategy 1 - BeatbloonsBob: Sauda + sub + Flagship + Bloon Solver + Archmage** (source: https://www.youtube.com/watch?v=LJuBp-nHYno, ~8 months old, "No abilities or micro"; confidence: video-description, ordered steps without rounds)
- Hero: Sauda (3rd purchase).
- Order: Dart 0-0-0 ("Strong") -> Sub 0-0-0 -> Sub 0-0-1 -> Sauda -> Sub 2-0-2 -> Buccaneer 2-2-0 ("Strong") -> Sub 2-0-4 (Armor Piercing Darts) -> Buccaneer 3-2-0 -> Dart 0-0-3 -> second Dart 0-0-3 on the left side -> Buccaneer 4-2-0 -> Village 2-2-0 **before round 59** -> Mermonkey 4-2-0 -> Buccaneer 5-2-0 (Flagship) -> Village 4-2-0 -> Alchemist 4-0-1 -> Glue 5-2-0 (Bloon Solver) -> Wizard 4-2-0 -> Wizard 5-2-0 (Archmage) -> Glue 0-2-4 (Relentless Glue, "Strong").
- Abilities: none. The Mermonkey 4-2-0 ability is not used per the title.
- Account conflicts: none (Mermonkey 4-2-0 is within cap; Village 4-2-0 is the cap).

**Strategy 2 - Perma-Brew water (wellordering / wiki)** (sources: https://www.youtube.com/watch?v=yBm4OdmYpZk, wellordering, ~1 year old ("I love Perma-Brew"); bloonswiki Haunted; confidence: snippet-only + wiki)
- Brickell; several Destroyers (wiki: 5, or one upgraded to Flagship) in the pond with camo; Alchemist 4-x-x Stronger Stimulant -> 5-x-x Permanent Brew; a Bloontonium Reactor sub in the centre for decamo; Brickell's abilities.
- Rounds: UNVERIFIED.
- Account conflicts: none.

**Other:** FonceXx no-hero guide (https://www.youtube.com/watch?v=ERU_KkdWaXU, steps unknown).

**Bot notes:**
- Strategy 1 is fully written, ability-free and unlocked. The one settings are "Strong" targeting on the dart, the buccaneer and the second glue.
- The pond spot must reach both lanes. The bot cannot see leaks on this map visually either (overlapping lanes), so rely on its lives counter.
- Strategy 2 relies on Brickell abilities (Mega Mines / Naval Tactics); blind pressing on blimp rounds is acceptable but weaker.

---

### Firing Range (Intermediate)
**Map traits / what it requires:** Two simultaneous lanes that partly interweave and cross. A fence and the central watchtower/outpost (removable, $1,000) keep ground towers off the early track; ground towers see under 10% of a lane before removal. Removing the outpost opens good centre spots, and there are good water spots. A sniper on the bottom grass sees ~84% of both lanes (project doc). Wiki picks: Destroyer (camo + Berserker Brew; Grape Shot crosspath) and Pop and Awe mortar, with Striker Jones and Relentless Glue, plus extra BAD defence. Fandom: early CHIMPS works with a dart on the platform and a tack on the other platform, or a sub. Effectively required: water towers or the outpost removal (TVS BLOONS beat it with "nothing behind fence", using the water spot).

**Strategy 1 - BeatbloonsBob: Psi + sub + Flagship + Super Brittle + Tack Zone** (source: https://www.youtube.com/watch?v=_PM_WfS-nOc, ~8 months old, $60k spare; confidence: video-description, ordered steps without rounds)
- Hero: Psi (3rd purchase).
- Order: Sub 0-0-0 -> Dart 0-0-0 ("Strong") -> Sub 1-0-1 -> Psi -> Sub 2-0-2 -> Buccaneer 2-2-0 -> Buccaneer 3-2-0 -> Sub 2-0-4 -> Village 2-2-0 -> Buccaneer 5-2-0 (Flagship) -> Village 4-2-0 -> Ice 5-2-0 (Super Brittle) -> Tack 2-0-5 (The Tack Zone) -> GG.
- Abilities: none listed.
- Account conflicts: none (Psi owned).

**Strategy 2 - Askaii: Etienne + ninja + alchemist + Flagship + Archmage + PoD + Elite Defender** (sources: https://www.youtube.com/watch?v=X5ltn0IGc0I and unedited https://www.youtube.com/watch?v=5uits3JYAOo, Askaii, ~5 years old (v2x era, likely still valid; older); confidence: video-description, ordered steps, "no ability")
- Hero: Etienne.
- Order: Dart 0-0-0 x2 -> Ninja 2-0-1 -> Etienne -> Alchemist 2-0-0 ("Strong") -> Ninja 4-0-2 -> Alchemist 4-2-0 -> Buccaneer 3-2-0 -> Village 2-0-0 -> Village 0-0-0 -> Buccaneer 4-2-0 -> **remove the obstacle** (outpost, $1,000) -> Wizard 4-0-1 -> Buccaneer 5-2-0 -> Wizard 5-0-1 (Archmage) -> Wizard 0-2-5 (Prince of Darkness) -> Sniper 0-2-5 (Elite Defender).
- Account conflicts: none.

**Bot notes:**
- Strategy 1 is the simplest: 13 steps, no abilities, no removable, all unlocked, Psi owned.
- Strategy 2 needs the $1,000 outpost bought (the bot can do this) and is older.
- Avoid the wiki's Pop and Awe: it needs a mortar target, which only works if set once; flag it.
- Psi has a targeting/ability set (Psychic Blast etc.); Bob lists no abilities, so leave it passive.

---

### Chutes (Intermediate)
**Map traits / what it requires:** Two very short lanes (~16 RBS, ~460-500 units) that **alternate every round** and cross in an X at the bottom middle. Two statues block sight ($350 each to remove). Each pool reaches one lane only. A ground tower in the X sees ~16% of each lane, while a sniper on the top strip sees ~85% of both (project doc). Wiki: "easily harder than some Advanced maps". Few useful corners (tack is weak). Wiki/fandom recommend:
- Comanche Commander (Heli 0-0-5) + Glue Storm + Geraldo (Sharpening Stone; shop refresh on R95 in CHIMPS);
- Carrier Flagship + Brickell;
- Heli Pilots in general, since only one lane is active per round;
- Sauda "is able to start" CHIMPS here.

**Effectively required:** map-wide / lane-following damage (heli, Flagship, sniper).

**Strategy 1 - Comanche Commander + Glue Storm + Geraldo** (source: bloonswiki Chutes recommended towers (bundle); confidence: wiki, no rounds)
- Hero: Geraldo (Sharpening Stone on the Comanche; Gerry's Fire mid-game; Pet Rabbit; Genie Bottle after the R95 shop refresh).
- Core: Heli 0-0-5 Comanche Commander (MOAB Shove stalls blimps); Glue x-4-x Glue Storm (ability: +2 damage to glued bloons, de-leads DDTs, so no MIB is needed).
- Round timings: none in sources (UNVERIFIED).
- Account conflicts: none (Geraldo owned).

**Strategy 2 - Carrier Flagship + Brickell** (source: bloonswiki Chutes; confidence: wiki, no rounds)
- The Flagship "sweeps the mid-game with little issue" and saves cash for other wincons. Brickell's Naval Tactics and Mega Mines "both aid greatly".
- Caveat: each pool reaches one lane only (project doc), so the boat covers one lane per round unless the planes do the work (inferred).

**Other video sources (no steps fetched; YouTube blocked):**
- Dabloon: Sub Commander + Pat Fusty (https://www.youtube.com/watch?v=nEZDe_qFnvg, ~6 years old); he says the common strategy is "Obyn and Wizard Monkey".
- H2K Zeus: Druids (https://www.youtube.com/watch?v=kJDmLc-UVAQ, v34).
- wellordering's 12k-view guide (https://www.youtube.com/watch?v=PCjGRrAAir4), which he says also wins Covered Garden, Water Park, Bazaar and Geared.
- KILOFINITRIX "no micro, one ability" (https://www.youtube.com/watch?v=glyMPWap7b0).
- Search snippets of other videos mention Sauda placed on the bottom intersection at R6, Sauda's ability on R96, and Village 4-2-0 on R99-100 (snippet-only, video IDs not pinned).
- "Easy Chutes Chimps (Guide in Description)" https://www.youtube.com/watch?v=xIq0cgJh4nk has a written guide that I could not fetch (429). **Fetch it when YouTube unblocks.**

**Bot notes:**
- No written round-by-round guide was retrieved. Next step: fetch xIq0cgJh4nk or PCjGRrAAir4.
- Comanche + Glue Storm relies on the Glue Storm ability (blind pressing on blimp/DDT rounds is plausible). Comanche's own ability (Comanche Commander's mini-comanches) is also a press.
- The heli must use "Lock Place" over the X or "Pursuit" (Heli 2-x-x only, so not on a 0-0-5 Comanche). Comanche 0-0-5 has no Pursuit, so it needs Lock Place at the X; this is inferred and needs checking.
- The bot's Hard build (Apache Prime with Pursuit + snipers) is the closest proven-by-bot shape.
- Geraldo's shop items need manual buying/placing (micro); flag it.

---

### Rake (Intermediate)
**Map traits / what it requires:**
- Lanes: two simultaneous, short lanes (~16 RBS each) that cross in the middle. Over 40% of each is off screen, and the crossing confuses tower targeting (bloonswiki).
- Removable: a $1,000 statue/rock; clearing it opens a good spot.
- Best spots: the centre, just below the centre, the cleared rock spot, and the pool (upper left), which sees the top stretches of both lanes.
- Wiki picks: Perma-Spike set to "Smart", slightly top-left of the centre of the enclosed space bottom-left of the rock, covering both exits (with Berserker Brew + Jungle Drums); Glaive Lord at the centre.

**Prior bot result:** lost R6-R7 twice with darts/Quincy, then the desperado opening held but R40 was lost: the Destroyer popped the MOAB and its ceramics ran out of the bottom exit (rake_chimps.yaml). Every proven guide below adds early exit/ceramic cleanup (spikes, a tack, MOAR Glaives) before the Flagship.

**Strategy 1 - SnartFarts: Brickell + desperados + Flagship + Glaive Lord + Super Brittle** (source: https://www.youtube.com/watch?v=971hSEdzXDk, SnartFarts, v52.2, ~9 months old, "No ability No micro"; confidence: video-description, ordered steps)
- Hero: Admiral Brickell (step 4).
- Order: 2 Desperados -> Buccaneer -> Buccaneer 2-2-0 -> Brickell -> Desperado 3-2-0 -> Buccaneer 3-2-0 -> Boomerang -> Boomerang 4-0-2 (MOAR Glaives) -> Village -> Village 2-2-0 (Radar Scanner first) -> Buccaneer 5-2-0 (Flagship) -> Village 4-2-0 -> Boomerang 5-0-2 (Glaive Lord) -> Ice -> Ice 5-2-0 -> Village 5-2-0.
- Account conflicts: **Village 5-2-0 LOCKED**; stop at 4-2-0 (the last step; spend the money elsewhere, e.g. Strategy 2's Perma-Spike).

**Strategy 2 - BeatbloonsBob: Sauda + Tack Zone + Perma-Spike + Glaive Lord + Super Brittle** (source: https://www.youtube.com/watch?v=yIlrhysKjPg, ~4 months old; confidence: video-description, ordered steps, one round anchor)
- Hero: Sauda (3rd purchase).
- Order: 2 Desperados -> Tack 0-0-2 -> Sauda -> Spike Factory 0-0-2 ("same targeting as me") -> Spike 2-0-3 **before round 28** -> Alchemist 3-2-0 next to the spike factory (placed so it doesn't cover the Desperado) -> Ice 0-0-0 -> Boomerang 4-0-2 -> Tack 1-0-4 (Overdrive) -> Tack 2-0-4 -> Ice 4-2-0 -> Tack 2-0-5 (The Tack Zone) -> Village 4-2-0 -> Alchemist 4-0-1 below the ice -> first Alchemist 4-2-0 -> Boomerang 5-0-2 (Glaive Lord) -> Spike 2-0-5 (Perma-Spike) -> Ice 5-2-0.
- Account conflicts: none.

**Other:** Ethan Reid, Sun Avatar + Avatar of Wrath (https://www.youtube.com/watch?v=eTwCP7HrA4A, ~6 years old). H2K Zeus, Grandmaster Ninja (https://www.youtube.com/watch?v=q7Db_0yA5BQ, v34).

**Bot notes:**
- Both written guides open with 2 Desperados (the bot's own opening that held).
- Strategy 2 is fully unlocked. Its spike targeting is unknown ("same targeting as me"; the wiki suggests "Smart"), so set "Smart" once (inferred).
- Strategy 1 is closest to the bot's existing Flagship build but adds Brickell, Desperado 3-2-0 and MOAR Glaives before the Flagship. That is the missing R40 ceramic cleanup.
- The project's yaml notes the pool-to-village distance problem (village 41 units from the boat; Bigger Radius needed).
- Neither guide uses abilities or the statue.
- Strategy 2 is preferred for a bot with no water-buff issues. The Perma-Spike at the exits is the leak insurance this map needs.


## Advanced maps

### Off The Coast (Advanced)
**Map traits / what it requires:** One long single lane (19.3-22 RBS) that starts AND ends in the sea; beach (land) only covers the middle arch, water covers the whole lower half (left bay near entrance, right bay near exit). Shipwreck in the middle: only three small land pieces (left piece, crow's nest/crane, right piece); crane and two top-corner cliffs block line of sight a little. No removables. Wiki (bloonswiki): "one of the easiest Advanced maps"; difficulty is the lack of compact loops and the entrance/exit being in water far apart, so homing/global/water towers do best. Recommended by bloonswiki: Comanche Defense/Commander (heli 2-0-x, single lane), Carrier Flagship (global planes + water buff). Fandom tip: Perma-Spike works but needs an Arctic Wind (ice x-x-4? "artic wind") to sit near the exit, or sacrifice track length.
Effectively REQUIRED: none strictly, but every written CHIMPS guide relies on water (subs/buccaneer) and/or global towers (Heli, crow's-nest Sniper); ground-only comps see little track.

**Strategy 1 - Quincy Subs -> Heli (Apache Prime) + Prince of Darkness, no ability activations** (source: https://www.youtube.com/watch?v=hV74wqAusLI ; BTD6 Fenix; ~5 years old (v22-24 era) - every tower used has only been buffed since, still valid but old; confidence: verified-written-steps (video description))
- Hero: Quincy
- Core towers: Sub 2-0-3, Sniper 1-0-0 (crow's nest, Strong), Heli 5-0-2 (Apache Prime), Alchemist 4-2-0 (+ second Alch 4-2-0 and 0-3-1 at R97-98), Village 2-2-0, Wizard 0-2-5 (Prince of Darkness), Dart 0-2-5 (Crossbow Master), Spike Factory 3-2-0.
- Purchase order (verbatim from source):
  - R6 Dart Monkey + Monkey Sub; R8 Sub 0-0-1; R11 Quincy; R14 Sub 2-0-1; R18 Sub 2-0-2; R23 Sub 2-0-3
  - R25 Sniper on Strong; R26 Sniper 1-0-0; R31 Heli; R32 Heli 2-0-0; R35 Heli 3-0-0; R36 Heli 3-0-2
  - R37 Alchemist; R38 Alch 3-0-0; R39 Alch 3-2-0; R40 (optional Quincy lvl-3 ability)
  - R41 Village 0-2-0; R42 Village 2-2-0; R45 Alch 4-2-0; R47 Wizard; R49 Wizard 0-2-4; R59 Heli 4-0-2
  - R75 Wizard 0-2-5; R76/R78/R85/R87 optional Quincy abilities "for safety"; R88 Heli 5-0-2
  - R91 Dart 0-2-4; R96 Dart 0-2-5; R97 Alc 4-2-0 (second alchemist - inferred, since the first is already 4-2-0); R98 Spike Factory 3-2-0 + Alc 0-3-1; R99/R100 optional Quincy abilities
- Key placements in words: sub at the water's edge near the last bend (docs/map_strategies.md, fandom trivia); sniper on the crow's nest (sees the whole track); heli/alch/village/wizard on the beach (inferred, not stated).
- Abilities used: none required ("You don't have to activate any ability's ... just an option").
- Account conflicts / substitutes: none (all tiers available; Quincy owned).
**Strategy 2 - Buccaneer Carrier Flagship + Sub + Ace + support (CurlyFrys tower list)** (source: https://www.youtube.com/watch?v=rVR3aH1S1FQ ; CurlyFrys; ~9 months old (~v52-53); confidence: video-description (final upgrades only, no rounds))
- Hero: Quincy
- Core towers (final crosspaths): Buccaneer 5-2-0, Sub 4-0-2, Village 2-3-0, Ice 0-3-2, Druid 1-4-0, Dart 0-0-0, Ace 5-0-1, Alchemist 4-0-1.
- Purchase order: not given (watch video). Inferred only: dart + sub opener, buccaneer line toward 5-2-0 (Flagship) around R60-70.
- Abilities: not stated (UNVERIFIED; watch video). Druid 1-4-0 is Jungle's Bounty, whose cash income CHIMPS disables - its role here is unclear (UNVERIFIED).
- Account conflicts: none. Bot cannot place towers on the Flagship deck - this list does not need it.
**Strategy 3 - Sauda/ Apache Prime + Spectre + Glue (OneEyedDeacon)** (source: https://www.youtube.com/watch?v=WnYzI5d781A ; OneEyedDeacon livestream ~1y; confidence: snippet-only: "Apache Prime + Spectre + Glue Gunner works well. Just had to throw in a couple Sauda abilities, get Jungle Drums early, and added three MOAB Assassins for the BAD")
- Hero: Sauda (abilities used). Core: Heli 5-x-x Apache Prime, Ace 0-2-4+ Spectre, Glue, Village 2-0-2 (Jungle Drums), 3x Bomb 0-2-4 (MOAB Assassin) for the BAD. No rounds given.
- Other evidence: BTD6 Index 2TC Pre-Emptive Strike (Sub 2-5-0) + Geraldo; Brickbrock "Off The Coast CHIMPS with only Subs" (https://www.youtube.com/watch?v=knjvV4kTJzY, v~30s) and "Fleet of Destroyers" (https://www.youtube.com/watch?v=4qGF6Nfw0bY, v33.3); Rydeon Etienne + Flagship + Sky Shredder + Sub Commander (https://www.youtube.com/watch?v=7qQI4Ycdo2U, uses spike storm R99 + all abilities R100).
**Bot notes:** Strategy 1 suits the bot best: written rounds, no abilities, no micro, no selling, no aiming. Heli default (Follow Touch?) - set Heli to Pursuit (one-time targeting) - inferred, source does not say; sniper on Strong. Placement of the sub matters (water's edge near last bend) and the crow's-nest sniper spot must be legal in the bot model (docs say crane slightly blocks LOS). Bot's existing 'chimps' hints already follow Fenix. Flag: R97 "Alc 420" duplicates R45 - treat as a second alchemist.

### Cornfield (Advanced)
**Map traits / what it requires:** Longest Advanced map, single lane (24.2 path length). Very little free land at start: only the small dirt plot in the middle (inner U, track progress ~0.42-0.72) plus thin strips; 13 corn patches ($350-$1,500, total ~$9,300) block placement AND line of sight until bought (cheapest: $350 middle far-left / middle far-right). Small gaps between plots let some shots through (sniper through the scarecrow-plot gap). "No Harvest" achievement = win without removing corn; 4 secret pixel spots (2nd bend medium, 5th bend medium hard, 6th bend small sub-pixel, above 3rd small). bloonswiki: "usually seen as one of the easiest Advanced maps"; Ultra-Juggernaut balls bounce off corn and re-hit. Bloon Solver puddles, Glaive ricochet, seeking shuriken and Carpet of Spikes ignore the corn.
Effectively REQUIRED: none - but a dense core in the middle plot (or bought corn) is needed; snipers/supers are poor (corn blocks sight, no room).

**Strategy 1 - BeatbloonsBob No-Harvest Ultra-Juggernaut + Glaive Lord + Solver + Carpet of Spikes** (source: https://www.youtube.com/watch?v=f_J04Y_M5c4 ; BeatbloonsBob; ~8 months old (~v52-53); confidence: video-description (written order, NO round numbers))
- Hero: Sauda
- Core towers: Dart 5-0-2 (Ultra-Juggernaut), Boomerang 5-0-2 (Glaive Lord), Boomerang 2-0-4 (MOAB Press), Village 4-2-0, Glue 5-2-0 (Bloon Solver), Spike 2-5-0 (Carpet of Spikes), extra Dart 0-0-0 Strong.
- Purchase order (verbatim order; rounds inferred in docs only): Sauda -> 0-0-0 Dart on bottom of map (Strong) -> 3-0-1 Dart -> middle Dart to 4-0-2 -> 0-0-0 Village (as low as you can) -> 4-0-2 Boomerang -> 2-0-4 Boomerang (Strong, as low and left as you can) -> middle Dart 5-0-2 -> Village 4-2-0 -> Boomerang to 5-0-2 -> 5-2-0 Glue (as low as you can) -> 2-5-0 Spike Factory. "That's all you need!"
- Key placements: everything in the free middle plot; first Dart "on bottom of map" = a hidden/no-harvest spot (bot may put it in the plot).
- Abilities used: none listed (Carpet of Spikes ability exists; author does not mention using it - presumably unneeded/UNVERIFIED).
- Account conflicts: none (Village 4-2-0 allowed).
**Strategy 2 - BlueCliff-style Ninja/Alch/Solver core (Hard build, adapted) / buy corn** (source: https://www.youtube.com/watch?v=qcnDjtGW6DU ; BlueCliff Hard no MK, ~v33-35; confidence: video-description, HARD not CHIMPS - CHIMPS use is inferred)
- Hero: Quincy. Core: Ninja 4-0-2, Alchemist 4-0-1, Village 5-2-0 (CONFLICT: Primary Expertise locked -> stop at 4-2-0), Glue 5-2-0. Rounds (Hard, starting R3): R3 Ninja, Dart; R7 Quincy; R9-18 Ninja to 3-0-2; R25 Alch 2-0-0; R26 3-0-0; R34 Ninja 4-0-2; R37 Alch 4-0-1; R39 Village 2-0-0; R49 Village 4-0-0 + Glue 4-2-0; R61 Glue 5-2-0 (+ remove $700 corn below the plot); R63 Village 4-2-0; R77 Village 5-2-0 (locked).
- Not proven on CHIMPS past R80 - only use as a fallback skeleton.
**Strategy 3 - unescaped Sauda/Quincy + Spirit of the Forest + Perma-Spike (No Harvest)** (source: https://www.youtube.com/watch?v=HMfHgEdJv_k ; unescaped; v33.3 (old; author recommends Sauda over Quincy); confidence: video-description (written summary))
- Purchase order: R6 Quincy or Sauda top left; R8 Sniper Strong; R10 Wizard next to hero; R12 Druid Strong below hero; R16 Spike bottom right; then Druid 0-3-0 -> 1-3-0, Wizard 0-3-2, Spike 2-0-2 Smart; R38 Spike 2-0-3; R41 2-0-4; R58 2-0-5; R62 Druid 1-4-0; R76/R78 hero ability on ceramic waves; R79 Druid 1-5-0; then Sniper 4-2-0, Glue 0-0-3 Strong -> 0-2-3, Alch 1-3-0 Strong next to MOAB glue, Alch 4-0-0 for the Spike, Bomb 2-4-0 Strong; R96 Bomb 2-5-0; R97/R100 "keep using Bomb ability" (MOAB Eliminator) on fortified ZOMGs / BAD.
- Abilities: needed (R76/78 hero, R97/R100 MOAB Eliminator spam) - bot presses blindly, risky.
- Other proven: OneEyedDeacon "Axis of Bomb" No Harvest (https://www.youtube.com/watch?v=EGaW9O4dfSE, v49.3, Striker Jones, bombs 0-2-5/5-2-0/1-5-0, village 5-2-0 at R99 = LOCKED, MOAB Eliminator spam R100; Bomb Blitz was later nerfed (OED note on Underground) - likely weaker now, inferred); OneEyedDeacon v53.2 (https://www.youtube.com/watch?v=6XQgSHPXHaE) Benjamin + Tack 2-0-4 + Perma-Spike 2-0-5 + Alch 4-2-0 + Dart 4-0-2, but uses Alch 1-0-5 (Total Transformation, ability) R88 and Benjamin ability R98; HyperF3 v56 (https://www.youtube.com/watch?v=q2JUXF2I_S8) Quincy + Desperado 5-2-0 + Wizard 5-0-2 + Bomb 2-0-5 + Skywarden 3-1-0 + Boomerang 2-0-4 BUT Village 5-0-0/5-2-0 = LOCKED (Primary Expertise) and author admits relying on Bomb Blitz passive at R98.
**Bot notes:** The bot does not need No Harvest - it can buy cheap corn ($350 patches) for room, which removes the hardest constraint. Strategy 1 is the cleanest (no abilities, no aiming, final tiers all in caps) but has no round numbers - the bot must schedule by affordability. Secret no-harvest spots are pixel-precise and probably illegal in the bot's placement model; put the "bottom" dart in the plot or a bought corn plot instead. Avoid strategies using Village 5-x-x (HyperF3, OED bomb axis). Solver/Juggernaut/Carpet need no targeting changes beyond 2-0-4 boomerang on Strong.

### Underground (Advanced)
**Map traits / what it requires:** Two SHORT simultaneous lanes (12.9 / 13.2) that both loop through a central ring and cross at its left and right edges (opposing curved paths). Cave walls block sight only slightly ("non-intrusive"); no water, no removables. bloonswiki: near-average Advanced difficulty because many spots in/above/below the ring cover both lanes; stall towers (Relentless Glue / Solver) are especially valuable on short lanes; recommended Sauda, Glaive Lord, Carpet of Spikes, Bloon Solver, Prince of Darkness.
Effectively REQUIRED: none - most comps work if centred in/around the ring; stall (glue) strongly recommended.

**Strategy 1 - retrogaming fun Churchill + Glue/Village/Alch/Sniper, no abilities, no mid-round actions** (source: https://www.youtube.com/watch?v=eXTI3EzbFgc ; retrogaming fun; tested on v50; confidence: verified-written-steps)
- Hero: Captain Churchill
- Core towers: 2x Desperado 0-0-0, Dart 0-3-2, 2x Sniper (one -> 5-2-0, one -> 1-1-0/4-2-0), 2x Village (3-0-2 and 4-2-0/0-2-2 - see note), 2x Glue (5-2-0 Solver + 4-2-0), Alchemist 4-2-0 (+ second Alch 4-0-0), Wizard 5-2-0 (Archmage).
- Purchase order (verbatim): R6 2x Desperado 0-0-0; R9 Dart 0-2-0; R11 Dart 0-3-0; R13 Sniper 0-0-0 Strong; R15 new Sniper 0-0-0 Strong; R16 Dart 0-3-2; R17 top Sniper 1-0-0; R19 bottom Sniper 1-0-0; R27 Churchill top right; R30 Village 0-0-0; R33 Village 0-0-2 + top Sniper 1-1-0; R36 new Village 0-0-2 (covers Churchill); R39 village into 3-0-2 + Glue 2-1-0; R40 Alchemist 3-0-0; R42 village into 0-2-2; R43 Glue 3-1-0; R44 Glue 3-2-0; R46 new Glue 3-2-0 "under double discount"; R49 left Glue 4-2-0; R51 right Glue 4-2-0; R59 Wizard 4-2-0 (retarget Wall of Fire); R60 Alchemist 4-2-0; R62 village into 4-2-0; R76 left Glue 5-2-0; R85 Wizard 5-2-0; R88 bottom Sniper 4-2-0; R97 bottom Sniper 5-2-0; R98 Alchemist 4-0-0 (new); R99 Sniper 4-2-0 (author did 4-1-0 by mistake).
- Village note (from docs): text says village1 302 then 022 then 420 - impossible on one tower; follow intent: one village ends 3-0-2 / 4-0-2, the other 0-2-2 -> 4-2-0 (inferred).
- Key placements: Desperados inside the ring left and right; snipers top/bottom; Churchill top right; glues inside both villages' range ("double discount").
- Abilities: none. Wizard "retarget Wall of Fire" = aiming (skip; default WoF goes to nearest track).
- Account conflicts: none (Village 4-2-0 allowed; Churchill owned).
**Strategy 2 - OneEyedDeacon Bomb Axis (Striker Jones)** (source: https://www.youtube.com/watch?v=h0GpxS2xX_w ; OED v49.3; confidence: verified-written-steps BUT author says it was "obsoleted by the bomb blitz nerf" (https://www.youtube.com/watch?v=qgB5zf-TXwY description) - DO NOT USE as-is)
- R6 3x Dart, R8 4th dart, R11 Striker, darts 0-3-2, bomb1 0-2-4 -> 0-2-5 (R58), alch 3-2-0, village 4-2-0, bomb2 0-3-1 -> 1-4-0 (R86) -> 0-5-1 (R95), bomb3 3-2-0 -> 5-2-0 (R85); R100 MOAB Eliminator spam.
**Strategy 3 - OneEyedDeacon PMFC + Geraldo (abilities + micro)** (source: https://www.youtube.com/watch?v=qgB5zf-TXwY ; OED v53.2; confidence: verified-written-steps) - Geraldo, Boomerang 0-5-2 (Perma Charge), Spike, Sniper 4-0-2, Village 4-2-0, many Geraldo items (turrets, glue, genie, rejuve, bunny), ability timing nearly every round from R40. Unsuitable for the bot.
- Other evidence: Zeroprince (Obyn, PermaBrew, Druid spam, https://www.youtube.com/watch?v=3X1O6xFm-s8, video only); JMisc Elite Defender + Elite Sniper + Gwen (https://www.youtube.com/watch?v=-vDmAZE8qnA, video only); BTD6 Index 2TC Perma Charge + Geraldo.
**Bot notes:** Strategy 1 is ideal: designed for "no abilities, no mid-round actions", only targeting changes (Strong), one cosmetic Wall-of-Fire retarget to skip. Watch the Village wording ambiguity. Two lanes at once - bot needs placement in/around the ring legal in its model (docs: inner ring ellipse x 0.30-0.55, y 0.40-0.60).

### High Finance (Advanced)
**Map traits / what it requires:** Two lanes that ALTERNATE by round (odd rounds the long S lane 27.6, even rounds the short U lane 15.6 - incl. R40 MOAB). Only free land: the four small corners of the central park + a pond (water) touching both lanes. 15 removable building lots ($350-$1,500, total ~$12,550) add space; buildings/construction fences block line of sight; only $1,500 lots fit a Heli/Farm. bloonswiki: average difficulty; Heli Pilots solid (single-lane alternating); recommended Carrier Flagship 5-2-0 + Brickell (Naval Tactics, Mega Mines), Bloon Solver on the $750 lower-middle building, Comanche Commander with Geraldo. Fandom: Apache Prime not impeded by LOS; 0-2-5 Perma-Spike fits bottom-right of green path on Close; Dart 3+-x-x Spike-o-Pult in the alley between the two rightmost buildings.
Effectively REQUIRED: none strictly; water Buccaneer in the pond and/or a global Heli are the common carries because buildings block sight.

**Strategy 1 - unescaped Quincy: Pirate Lord + Spike + Inferno Ring + Glue Storm** (source: https://www.youtube.com/watch?v=YSHTM5sTkqU ; unescaped; v34.3 "updated for v44.1"; confidence: verified-written-steps (from docs/map_strategies.md), ability-heavy)
- Hero: Quincy
- Core: Buccaneer 2-5-0 (Pirate Lord) in lower pond, Spike 4-0-2 (Smart), Alch 4-2-0 x2, Village 4-2-0, Tack 5-2-0 (Inferno Ring) Strong, Glue 0-5-2 (Glue Storm), Ice 4-2-0.
- Order: R6 Quincy; R7 Dart Strong; R10 Buccaneer (lower pond); R12 Bucc 0-1-0; R15 Quincy Rapid Shot on pinks; R17 Spike Factory; R19 Spike 0-0-2 Smart; R20 Bucc 1-1-0; R21 2-1-0; R26 2-2-0; R27 2-3-0; then Spike 3-0-2; R39 Bucc 2-4-0; R40 Rapid Shot on the MOAB; R42 Alch 3-0-0; R43 Village; R44 0-2-0; R45 2-2-0; then Spike 4-0-2, Alch 4-2-0; R60-R87 hook BFBs/ZOMGs with Pirate Lord ability; R70 Bucc 2-5-0; Tack 3-0-0; R74 Tack 4-2-0; R87 Tack 5-2-0 Strong; second Alch 4-2-0; Village 4-2-0; Glue 0-4-2; R95 Glue Strike; R96 Glue 0-5-2; R100 Ice 4-2-0.
- Abilities: MANY and timed (hooks on specific blimps, Glue Strike/Storm). Account conflicts: none.
**Strategy 2 - Carrier Flagship + Sky Shredder + Bloon Solver (Etienne)** (sources: Brickbrock https://www.youtube.com/watch?v=dI_Sh-pJjiM (v~22, "Carrier Flagship + Sky Shredder combo ... great for this map because of all the buildings blocking"), wellordering "Prince of Darkness - Sky Shredder" (https://www.youtube.com/watch?v=w53Z25TUIrQ, pre-v45), bloonswiki recommendations; confidence: video-description + wiki, NO written rounds)
- Hero: Etienne (Brickbrock; camo for all towers) - Brickell is the wiki's pick for Flagship.
- Core: Buccaneer 5-2-0 in the pond, Ace 5-0-x (Sky Shredder), Glue 5-2-0 Solver on top-centre of the $750 lower-middle building (wiki). Rounds: UNVERIFIED (watch video).
**Strategy 3 - BlueCliff Hard skeleton (no buildings)** (source: https://www.youtube.com/watch?v=C5QklAgqeGQ ; ~v30; HARD, sells towers; confidence: video-description) - Ninja 3-0-2 -> Bucc 3-2-0 -> Alch 4-0-1 -> Village 2-2-0 -> Bucc 4-2-0 -> 5-2-0 (R59, after SELLING ninja) -> Boomerang 5-0-2; CHIMPS use inferred only.
- Other CHIMPS evidence: sYnce Sauda + Ray of Doom (Dartling 5-x-x top, allowed; v55.2, https://www.youtube.com/watch?v=9G6DQGSBA94, video only - RoD needs no aim but dartling default follows cursor -> set to locked/target? flag); G00SE Archmage + Popseidon (v46.3, https://www.youtube.com/watch?v=Ud32kDtLoYY - Popseidon = Mermonkey T5, LOCKED); Lazynomicro Psi + Bloon Exclusion Zone (dartling 0-0-5, allowed; https://www.youtube.com/watch?v=QEFcrDeU00Y, "R84 got close", no steps); Kaka Cake no abilities v29 (52k left, https://www.youtube.com/watch?v=NGTcd8hG7is, video only); BTD Flagship no abilities/no micro v44.1/v46.2 (https://www.youtube.com/watch?v=ApMdx8BTe0M, https://www.youtube.com/watch?v=cGzgVMeeuRc, video only); BTD6 Index 2TC Bounty Hunter + Popseidon.
**Bot notes:** No modern no-ability written guide was found; best bot candidate is a Flagship-from-the-pond plan (Strategy 2 towers) with BlueCliff's early Ninja/Buccaneer timing, Bloon Solver on the $750 building (bot can buy removables) - but this composite is INFERRED, needs simulation. Strategy 1 requires timed hooks/Glue Strike - bad for blind ability presses. Dartling (RoD/BEZ) needs aim mode: avoid unless "Lock in place"/target setting is supported. Bot cannot place towers on the Flagship deck (none needed). Alternating lanes: park corners and pond see both lanes.

### Another Brick (Advanced)
**Map traits / what it requires:** One single lane (19.6) shaped like a U lying on its side: down from the top, right along the upper half, U-turn at far right, back left along the lower half, out at the bottom. A brick WALL (line-of-sight blocker) runs between the two horizontal halves and down the left side, so most ground towers see only one half; the land right of the U-turn sees both. Two ponds (top-right sees only top half; bottom-left sees the exit stretch). Two brick pallets ($1,000 each) on the left free space but towers there are wall-blocked (only global towers useful). bloonswiki: "one of the easiest Advanced maps"; counter the wall with towers that see over it: Aircraft Carrier/Flagship (+Brickell), Guided Magic wizards / Prince of Darkness (graveyard over walls), Perma-Spike near the exit with Jungle Drums + 3-0-1 Berserker Brew.
Effectively REQUIRED: a wall-ignoring damage source (Heli, Flagship, PoD/guided wizard, or Perma-Spike at the exit). Ground-only splash sees half the track.

**Strategy 1 - Fynn Sauda + Ninja + Heli + PoD + MOAB Press + Perma-Spike, no abilities, no RNG** (source: https://www.youtube.com/watch?v=a6PNBW8MGtE ; Fynn BTD6; v27.3 (OLD, ~5y; towers mostly buffed since, still plausible); confidence: verified-written-steps)
- Hero: Sauda
- Core: Ninja 4-0-2, Alch 0-0-3 (+ Alch 4-2-0, Alch 3-0-0), Village 3-0-2, Heli 4-0-2, Wizard 2-0-5 (PoD), Glue 0-1-3 Strong, 3x Boomerang 2-0-4 Strong, Spike 0-2-5 (Perma-Spike) Smart, Mortar 0-0-4.
- Order (verbatim): R6 Sauda; R9 Ninja; R10 0-0-1; R12 1-0-1; R13 2-0-1; R17 3-0-1; R19 3-0-2; R24 Alch1 0-0-2; R27 Alch1 0-0-3; R34 Ninja 4-0-2; R37 Village1 2-0-0; R39 Heli 1-0-0; R40 Heli 2-0-0; R41 Village 2-0-2; R44 Heli 3-0-2; R55 Heli 4-0-2; R57 Alch2 4-2-0; R60-62 Wizard 0-0-4 -> 2-0-4; R77 Wizard 2-0-5; R79 Village 3-0-2; R80-82 Glue 0-1-3 (strong) + 3x Boomerang 2-0-4 (strong); R85 Spike 0-0-4 (smart) + Alch 3-0-0; R94 Spike 0-0-5 -> 0-2-5; R96 optional Ninja 0-0-4 (not needed); R97 Mortar 0-0-3; R98 Mortar 0-0-4; R100 optional abilities.
- Abilities: none required. Account conflicts: Mortar 0-0-3/0-0-4 = bottom-path mortar is LOCKED (and needs aiming). Substitute (inferred): spend that ~$9k on more 2-0-4 boomerangs / Glue 0-2-4 / Spike 2-5-0 or more 2-0-4 MOAB Press; or skip (source said R100 abilities "for safety").
**Strategy 2 - Archmage (Bloons mind / Chewie)** (sources: https://www.youtube.com/watch?v=GJbsdCb_XTI Bloons mind v55.1 "Archmage, no micro, no RNG"; https://www.youtube.com/watch?v=pLdXtc3USrg Chewie v34 Archmage LCC <$90k; confidence: video-description, no rounds) - Wizard 5-x-x Archmage (guided magic sees over walls). Rounds UNVERIFIED.
**Strategy 3 - Apache Prime + Spectre + Glue (OneEyedDeacon)** (source: https://www.youtube.com/watch?v=PJchPnaM71A ; OED ~1y; confidence: snippet-only "So easy that my Apache Prime + Spectre + Glue Gunner strat worked") - Heli 5-x-x, Ace 0-2-4/0-2-5 (Spectre), Glue; hero likely Sauda (as on his Off The Coast run; UNVERIFIED).
- Other evidence: fandom CHIMPS Sauda + Apache Prime + Perma-Spike (docs); BTD Flagship "all T5 Helis no abilities/no micro" v44.1 (https://www.youtube.com/watch?v=_HvZV1bq8Bo); Cosmos Quincy no abilities (https://www.youtube.com/watch?v=MM1PxQ_ePro); Omen Super Brittle + Blazing Sun Desperado (https://www.youtube.com/watch?v=OZsr0EvEEGg); BTD6 Index 2TC Perma Charge + Geraldo.
**Bot notes:** Strategy 1 is the only written one; drop the locked mortar. Heli: set to Pursuit (inferred - Fynn does not state; Pursuit/Lock settings are one-time). Spike on Smart, glue/boomerangs on Strong. Perma-Spike must be near the exit (bottom pond side) - Spike Factory needs land beside the exit stretch. Pallets need not be bought.

### Peninsula (Advanced)
**Map traits / what it requires:** Short single lane (14.2) around a big central MOUNTAIN that blocks line of sight; >80% water. Land: the mountaintop (high ground; a sniper there sees everything, short-range towers reach nothing) and one small plot at the bottom bend (only real land DPS spot, 2-3 small towers). Three seaweed rocks ($500 each): top-right island (near exit; Perma-Spike spot), left of the peninsula (land next to first third; Etienne/Orca spot), bottom-left island (far; ice spot). bloonswiki: above-average Advanced difficulty; recommended Carrier Flagship + Brickell, Perma-Spike on the top-right island with 3-0-1 brew, Orca (Beast Handler).
Effectively REQUIRED: water towers (subs/buccaneer) or mountaintop global towers (sniper/heli); land is too scarce for a ground comp.

**Strategy 1 - 0Python Brickell sub spam, no micro / no abilities** (source: https://www.youtube.com/watch?v=bkeuo0q7XbY ; 0Python BTD6; ~10 months (~v52); confidence: verified-written-steps)
- Hero: Admiral Brickell
- Core: Subs 2-0-4 (x ~11), one Sub 2-0-5 (Sub Commander), Sub 2-4-0 (First Strike), Buccaneer 0-3-2 + Buccaneer 0-0-2, 2x Dart 4-2-0, Alch 3-2-0, Ice 4-1-0, Village 2-3-0, Mermonkey 4-0-2.
- Order (verbatim): Dart R7 (sub placed first, implied R6); R9 sub 0-0-1; R11 sub 1-0-1; R14 Brickell (mid-round); R19 sub 1-0-2; R22 Bucc 0-0-2; R27 Bucc 0-2-2; R29 sub(1) 2-0-3; R36 sub 2-0-4; R39 Alch 3-2-0; R40 Bucc 0-3-2; R44 new sub(2) 2-0-4; R49 sub(3) 2-0-4; R50 sub(4) 2-0-4; R62 2 darts 4-2-0; R70 bottom-left sub 2-0-5; R71 Bucc 0-0-2 right of the T5 sub; R72-R81 4x 2-0-4 subs (8 total); R83 Ice 4-1-0; R84 Village 2-3-0; R90-R93 2x 2-0-4 subs; R94 Sub 2-4-0; R96-R100 Merm 4-0-2 + keep spamming 2-0-4 subs; R100 First Strike "for safety".
- Abilities: none needed; risky rounds 14, 63, 99, 100; First Strike on the last BAD layer recommended ("2 out of my 4 test runs ... needed ability").
- Account conflicts: none (Mermonkey 4-0-2 within 4-4-4 cap).
**Strategy 2 - retrogaming fun Etienne + Snipers + Heli + Perma-Spike, no abilities** (source: https://www.youtube.com/watch?v=_QrcbP0y2Fw ; retrogaming fun; v51; confidence: verified-written-steps)
- Hero: Etienne (left seaweed island bought R18)
- Order (verbatim): R6 3x Dart (targets last, first, first; first dart position important or lose R9); R8 left Dart 0-2-0; R10 Sniper Strong; R12 Dart 0-3-0; R13 Dart 1-3-0; R18 unlock first island + Etienne; R19 new Sniper Strong; R20 first sniper 1-0-0; R23 1-2-0; R26 Alchemist Strong; R30 Heli "lock in place"; R34 Village 0-0-1; R35 Heli 1-0-0; R36 Village 0-0-2 + Heli 2-0-1; R37 Heli 2-0-2 + Sniper 0-1-0; R38 Sniper 2-2-0 (other sniper target first); R40 Heli 2-0-3 + Ice; R42 Sniper 2-3-0; R44 new Alch 3-0-0; R45 Sniper 0-2-2; R49 Sniper 2-4-0 First; R50 Village 2-0-2; R56 Sniper 2-5-0 First; R58 Alch 4-0-0; R82 Alch 5-0-0; R83 Sniper 0-2-4; R87 Sniper 0-2-5; R91 unlock last island + Spike 0-0-4 "retarget"; R97 Spike 1-0-5; R98 Spike 2-0-5.
- Flags: Heli "lock in place" (one-time setting at its pad); Spike "retarget" = targeting priority (UNVERIFIED which); Sniper 0-2-5 Elite Defender was nerfed after v51 (OED v54.1 notes "025 elite defender got nerfed") - weaker now.
**Strategy 3 - OneEyedDeacon Rosalia + Flying Fortress** (source: https://www.youtube.com/watch?v=w_2iqqkna8M ; OED v49.3; confidence: verified-written-steps) - Ace 2-0-5 + Rosalia, ability timings (jetpack + scatter missile, kinetic charge) and moving Rosalia / switching her targeting most rounds R52-R87, ace centred path placement. Unsuitable for the bot.
- Other evidence: Dabloon MOAB Maulers + ice to freeze water (https://www.youtube.com/watch?v=rIqbq1lhO8o, v~20); Commander Ryu Silas ice (https://www.youtube.com/watch?v=J62_tKFlxkk, v55); GirlKizzer Perma-Spike + Brickell v56 (https://www.youtube.com/watch?v=mxt7jQCfTcc); BTD6 Index heroless 3TC Flagship 5-0-2 + SotF 2-5-0 + Carpet of Spikes.
**Bot notes:** Strategy 1 best: water-only, no aiming, no micro, Brickell owned. Bot just presses First Strike on cooldown from R94 (blind) - acceptable but the source wants it on the last BAD layer; consider keeping ability unused until R100 if the bot can. Mid-round Brickell R14 -> bot buys when affordable. Placement precision matters (sub spots near exit side / entrance / below bottom bend per docs). Strategy 2 needs Heli lock-in-place and has the Edef nerf issue.

### Pat's Pond (Advanced)
**Map traits / what it requires:** Two simultaneous lanes (13.8 / 14.4) circle a big pond in opposite directions; each junction is one lane's entrance and the other's exit (overlapping entrances/exits make leaks hard to see). Lanes are far apart in the middle, so global towers (Heli Pursuit, Advanced Intel subs) chase back and forth. Four $500 removables (2 rocks in the water, 2 trees; LOS blockers). bloonswiki: cram short-range towers at the left or right junction (right preferred: BAD exits there); recommended Sauda, Super Glue (stall), Carpet of Spikes, Glaive Lord.
Effectively REQUIRED: none - a junction cluster (plus stall) is the key; avoid heli.

**Strategy 1 - retrogaming fun Desperado/Subs/Churchill/Glue Solver, no abilities, no mid-round actions** (source: https://www.youtube.com/watch?v=CPBKQYUTSsU ; retrogaming fun; tested v50; confidence: verified-written-steps)
- Hero: Captain Churchill
- Core: 2x Desperado 0-1-0, Sub 2-0-2 x2, Sniper 4-2-0, Village 4-0-2 + Village 0-2-2 + Village 0-0-1, Glue 5-2-0, Alch 4-2-0, Wizard 5-2-0, Spike 2-0-5, Alch 0-3-1.
- Order (verbatim): R6 2x Desperado; R9 Sub; R11 sub 0-0-1; R12 Sniper Strong; R14 new Sub as top right as possible; R18 top sub 0-0-2; R20 bottom sub 0-0-1; R24 right Desperado 0-1-0; R28 Churchill + Sniper 1-0-0; R30 top sub 2-0-2; R33 left Desperado 0-1-0; R35 Village 0-0-2; R36 Alchemist + bottom sub 2-0-1; R37 bottom sub 2-0-2; R38 remove two islands ($500 rocks x2); R40 Village 0-0-1 (covers Churchill) + Alch 3-0-0; R42 right village 0-0-2, left village 2-0-2; R43 Alch 3-2-0; R46 left village 4-0-2 + Glue 3-1-0; R50 Glue 4-2-0 + Alch 4-2-0; R51 village 0-2-2; R60 Wizard 4-2-0 (re-target Wall of Fire); R74 Glue 5-2-0; R84 Wizard 5-2-0; R85 Spike 2-0-4 (re-target); R95 Spike 2-0-5; R97 Sniper 4-2-0 target last; R98 Alch 0-3-1 Strong.
- Abilities: none. Aiming: Wall of Fire retarget and Spike "re-target" (skip / leave default; inferred targeting change for spike).
- Account conflicts: none (Village 4-0-2 OK).
**Strategy 2 - OneEyedDeacon Obyn + 8 Druids** (source: https://www.youtube.com/watch?v=dydRUL5zKw0 ; OED v50.1; confidence: verified-written-steps)
- Hero: Obyn. Order: R6 Sub (right) + Dart (under left track); R8 Druid1; R11 Obyn; R13 Druid1 0-1-0; R14 spam brambles; R15 Druid2 next to sub; R16 Druid1 0-2-0; R20 0-3-0; R22 1-3-0; R23 Dart 0-0-2 camo priority; R24 0-2-2; R26-28 Druids 3-5; R29 Alch; R31 Dart 0-3-2; R33 Village; R37 Village 0-2-0; R38 Druid2 2-0-0; R39 3-0-0; R40 Druids 6-8 + bramble MOAB; R41-57 druids to 0-0-3 -> 0-0-4 -> 0-1-4 one by one; R49 Village 2-2-0; R51 Alch 3-2-0; R53 4-2-0; R75 trees, refresh for last BFB; R79 one druid 0-1-5 during round; R83 Village 2-3-0; R84 Druid1 1-4-0; R95 1-5-0; R97 Sub 0-4-0 + First Strike 2nd ZOMG; R99 Glue 0-2-4 Strong; R100 First Strike.
- Abilities: brambles spam, Wall of Trees (aimed), First Strike timing. Poor for bot.
- Other: Mathgodpi Druid/Obyn/Dart -> Sniper -> Tack Zone + Perma Brew, no abilities, no water (https://www.youtube.com/watch?v=2yR4YlL-tYg, no rounds); sYnce Striker + Perma-Spike + Lord of the Abyss (Mermonkey T5 = LOCKED); wellordering Lord of the Abyss (LOCKED); Doreo Glaive Lord v43.3; unescaped v45.3 (written guide only in pinned comment).
**Bot notes:** Strategy 1 is made for "no abilities, no mid-round actions" - best for the bot; buy both $500 water rocks at R38 (bot can). Skip WoF/spike retargets. Avoid Lord of the Abyss guides (locked). Churchill targeting default fine.

### Cargo (Advanced)
**Map traits / what it requires:** Short main bloon road (13.9). Parked trucks in the middle block line of sight until R39, when they drive off and open a MOAB-ONLY lane (11.7, one of the shortest) that crosses the road; from then most rounds run both lanes. After R39 two $500 trucks become removable. Water all around. bloonswiki: hard mid-game (bloon and MOAB lanes split attention); place early towers right of the MOAB lane; late core below the MOAB lane's first bend; recommended Corvus, Glaive Lord. Fandom: slows (glue, MOAB Shove, Cripple MOAB) are strong; global towers (sniper, heli, mortar, Advanced Intel sub) can switch lanes; R63 is brutal.
Effectively REQUIRED: global damage that covers the MOAB-only lane - Snipers are used by every written CHIMPS build.

**Strategy 1 - OneEyedDeacon Sauda + Axis of Havoc snipers + Prince of Darkness, no abilities, no micro** (source: https://www.youtube.com/watch?v=9OiV2P_YvCA ; OED v49.3; confidence: verified-written-steps)
- Hero: Sauda
- Core: Sniper1 0-2-5 (Elite Defender), Sniper2 0-5-2 (Elite Sniper), Sniper3 5-2-0 (Cripple MOAB), Alch 4-2-0 x2, Village 3-0-2, Wizard 0-2-5 (PoD), Boomerang 2-0-4, Glue 0-2-4, Engineer 0-3-1, 2x Tack 2-0-4.
- Order (verbatim): R6 Sauda top right corner; R8 Boomerang left of Sauda (top-left as possible); R10 Sniper1 Strong across barriers; R12 0-0-1; R14 0-0-2; R15 0-1-2; R17 0-2-2 on first; R18 Boomerang 0-0-1; R19 0-0-2; R29 Sniper1 0-2-3; R37 0-2-4; R40 Village1 2-0-2; R42 Wizard1 0-0-3; R44 0-0-4; R45 0-2-4; R47 Alch1 3-2-0 for sniper1; R60 Wizard 0-2-5; R63 Alch1 4-2-0; R65 Sniper2 0-3-2; R71 0-4-2; R78 0-5-2 on first; R79 Sniper3 3-2-0 Strong; R80 4-2-0; R90 5-2-0; R95 Sniper1 0-2-5; R96 Alch2 4-2-0 for sniper3; R97 Village 3-0-2; R98 Glue1 0-2-4 Strong (low, in village range); R99 Engineer 0-3-1 next to glue, foam aimed in front of MOAB lane; R100 Tack1 2-0-4 under sniper3 + Boomerang1 2-0-4 Strong + Tack3 2-0-4 under wizard1 (1-0-4 if not in discount range).
- Abilities: none. Aiming: Engineer foam target (R99) - skip or leave default.
- Account conflicts: none. Note Elite Defender 0-2-5 nerf after v49.3 (OED) - here it is bought only at R95, minor impact (inferred).
**Strategy 2 - Mathgodpi Striker Jones + Subs -> Sub Commander + Perma Brew + Elite Defender/Elite Sniper, no abilities** (source: https://www.youtube.com/watch?v=hzVxMvuAEOI ; Mathgodpi ~1y; confidence: video-description summary, no rounds) - "Start with 3 dart monkeys, a sub, and Striker Jones ... Alch buff for your sub is needed for round 40. Then upgrade it to stronger stim, get a village, another sub, then save up for sub commander and perma brew ... get elite defender and elite sniper".
**Strategy 3 - Alex Sauda + Sniper + Druid + SotF (order list)** (source: https://www.youtube.com/watch?v=dBnllg4LwxE ; ~2y; confidence: video-description, no rounds) - Sauda; Sniper Strong; Druid 1-3-0; Sniper -> First, 0-2-4; Alch 4-0-1; Village Jungle Drums; Elite Defender; Radar Scanner village; Spirit of the Forest; MIB + Glue 0-2-5; "two first strikers" (abilities) + Spike 2-4-0.
- Other: wellordering SotF (https://www.youtube.com/watch?v=nJz5jC33pX4), Omen Bloon Solver (https://www.youtube.com/watch?v=bMtRZOTgVEc), sYnce Rosalia + Flying Fortress (v55.2), Doreo Obyn v43.2, BTD6 Index LCC/2TC with Perma Charge + Geraldo.
**Bot notes:** Strategy 1 is fully written, no abilities; sniper targeting changes (Strong -> First) are one-time settings. Model gap (docs): the bot's geometry treats trucks as permanent sight blockers and the MOAB lane as hidden - dock snipers are global so unaffected, but the bot's damage model will under-rate the MOAB-lane coverage; trust the guide. Skip engineer foam aiming.

### Spillway (Advanced)
**Map traits / what it requires:** FOUR simultaneous lanes (22-23.6 each) from the four corners into a central loop where every lane circles ~1.75 times before leaving; four $2,000 inflatable walls (valves) block sight from the side pools to the loop. A metal barrel in the exact centre fits one small tower (Ninja start). Water in the side pools. bloonswiki: not particularly difficult - bloons linger in the middle; recommended Pop and Awe 2-5-0 mortar + Striker Jones + Relentless Glue, Archmage 5-2-0 (guided magic, middle crosspath), Carrier Flagship (deck towers see over walls), The Biggest One. Fandom: 0-0-0 Ninja on the barrel can start CHIMPS alone.
Effectively REQUIRED: the barrel Ninja (or other centre/wall-ignoring damage: guided Wizard, Mortar, Ace, Energizer Sub, Flagship); ground towers outside the walls only see the straight entry lanes.

**Strategy 1 - OneEyedDeacon Psi L20 + barrel Ninja + Mortar 2-3-0 + Ace + Energizer + Wizards** (source: https://www.youtube.com/watch?v=KW-50Pa14jU ; OED v49.3; confidence: verified-written-steps)
- Hero: Psi
- Core: Ninja 2-0-2 (barrel), Mortar 2-3-0, Ace 2-0-3 (Neva-Miss), Alch 3-0-0 + Alch 4-2-0, Sub 5-0-0 (Energizer), Village 2-0-0, Wizard 2-0-5 (PoD) + Wizard 5-2-0 (Archmage), Sub 0-4-0 (First Strike), Spike 1-4-0.
- Order (verbatim): R6 Ninja1; R7 0-0-1; R9 1-0-1; R11 2-0-1; R15 Psi; R17 Ninja 2-0-2; R20 Mortar1; R22 0-1-0; R23 0-2-0; R27 0-3-0; R28 1-3-0; R30 2-3-0; R32 Ace1; R33 0-0-1; R34 0-0-2; R37 0-0-3; R38 2-0-3; R39 Alch1 2-0-0 under ace; R40 3-0-0; R41 Sub1 2-0-0; R42 3-0-0; R44 4-0-0; R59 5-0-0; R60 Village 2-0-0 under Psi near water; R61 Wizard1 0-0-2; R63 2-0-3; R64 2-0-4; R77 Psi on strong; R79 Wizard1 2-0-5; R80 Wizard2 3-2-0 Strong under wizard1, WoF in middle; R82 4-2-0; R92 5-2-0 during round; R93 "300 alch1" (likely new Alch2 3-0-0 between the wizards - source then says 320 alch2); R94 Alch2 3-2-0; R95 4-2-0; R96 "030 sub1"; R97 "040 sub1" (a 5-0-0 sub cannot become 0-3-0 -> must be a NEW sub 0-3-0 -> 0-4-0, inferred); R98 Psi scream when ZOMGs reach the middle; R99 Spike 1-4-0; R100 First Strike + Spike Storm + scream.
- Abilities: R98/R100 timed (Psi Psychic Blast, First Strike, Spike Storm). Aiming: Mortar target must be the centre loop (one-time aim at placement; inferred); WoF "in middle" (aim).
- Account conflicts: none (Mortar 2-3-0 within 5-5-0).
**Strategy 2 - retrogaming fun Etienne + barrel Ninja + Archmage + Mermonkey, no abilities** (source: https://www.youtube.com/watch?v=WVzGzQM5RPA ; retrogaming fun v49; confidence: verified-written-steps (per docs/map_strategies.md))
- Order: R6 Ninja on barrel; R7 Sniper Strong; R11 Etienne; R13 Wizard 1-0-0; R15 2-0-0; R19 2-2-0 (relocate WoF into loop); R21 Sniper 1-0-0; R22 1-1-0; R27 Village; R32 Village 0-0-2 + Wizard 3-2-0; R35 Sniper 2-1-0; R37 Village 2-0-2; R40 buy LEFT wall ($2,000) + Mermonkey 3-2-0 + Etienne First; R44 Merm 4-2-0; R50 Wizard 4-2-0; R63 Mermonkey 5-2-0 (LOCKED: Mermonkey T5) ; R80 Wizard 5-2-0 (Archmage); R83 Spike 2-4-0; R95 Spike 2-5-0; R98 Mortar 0-0-4 aimed at loop (LOCKED: bottom-path mortar); R99 Sniper 4-2-0.
- Account conflicts: Mermonkey 5-2-0 locked (cap 4-4-4) -> stop at 4-2-0; Mortar 0-0-4 locked -> substitute (docs suggest 1-4-0 spike / First Strike sub; or Mortar 2-3-0+ aimed at loop, inferred).
**Strategy 3 - bloon.games Striker Jones + Ninja + two Mortars (TBO + Blooncineration)** (source: https://bloon.games/how-to-beat-chimps-on-spillway/ ; confidence: wiki-style written steps, no version) - Ninja 1-0-1 -> 2-0-4 -> 2-0-5 (R97) on barrel; Striker; Mortar1 3-0-2 -> 4-0-2 (R47) -> 5-0-2 (R74) aimed at centre; Mortar2 2-0-3 -> 2-0-4 (R51) -> 2-0-5 (R85). CONFLICT: Mortar bottom path locked (x-x-1+ impossible) -> both mortars unbuildable as written. Substitute (inferred, matches bloonswiki Pop and Awe recommendation): Mortar 5-2-0/4-2-0 (TBO with middle crosspath) and Mortar 2-5-0 (Pop and Awe) aimed at centre with Striker.
- Other: wellordering Ezili + MIB + Sabo (https://www.youtube.com/watch?v=oR0o8os2bL0); Culture no abilities (https://www.youtube.com/watch?v=mZkDZKsurNw); Re-Bloonator "4 towers" (https://www.youtube.com/watch?v=2n12dfsnfGY); Adora + Flagship deck build (docs; deck placement - bot cannot); BTD6 Index heroless Blooncineration + Apache Prime.
**Bot notes:** All strategies need the CENTRE BARREL Ninja - docs say the barrel has no legal cell in the bot model: must be hard-coded. Mortars need a one-time aim at the loop centre (bot: only if its default target or a one-time aim works). Strategy 2 (no abilities) is closest to bot-friendly once T5 Mermonkey and bottom mortar are replaced; Strategy 1 needs ability timing at R98/R100. Walls cost $2,000 - bot can buy.

### Geared (Advanced)
**Map traits / what it requires:** Single lane (13.9) over two rotating gears: the big gear turns 45 deg every round (8-round cycle), the small 108 deg (10-round cycle); towers ride the gears, so finite-range towers are carried away from the track. No water, no removables, NO line-of-sight blockers. bloonswiki: early game is the hardest part; Snipers are usually the only affordable early option (unaffected by rotation); later Comanche, Spectre, Heli tier-5s; Corvus/Rosalia good. Fandom: multiple sniper + dart early is effective; Dark Knight/Spike Storm ability ignore rotation.
Effectively REQUIRED: Snipers (global) early - every written CHIMPS guide spams 3-7 snipers; later Heli/Ace or more snipers.

**Strategy 1 - retrogaming fun Geraldo + snipers + heli + Perma Brew, no abilities, no mid-round actions** (source: https://www.youtube.com/watch?v=31FN4VAul_Q ; retrogaming fun; tested v50; confidence: verified-written-steps)
- Hero: Geraldo (shop items used: turret, glue, nails, See Invisibility potion, sharpening stone)
- Order (verbatim): R6 Boomerang Strong + Dart ("the only precise positions"); R7 Boomerang target last; R8 new Dart last; R9 new Boomerang Strong; R10 new Dart last; R11 Sniper Strong; R13 new Sniper Strong; R15 new Sniper + boomerang Strong; R18 Geraldo Strong; R19 sniper 1-0-0; R21 turret target last; R22 glue; R24 sniper 1-2-0; R27 Gerry's glue + nails as far as possible; R28 sniper first; R29 Heli "fixed place" (lock); R31 heli 1-0-0; R32 2-0-0; R33 sniper 0-1-0; R36 glue + nails; R37 Village 0-0-2 + heli 2-0-2; R38 sniper 2-2-0; R39 glue; R40 heli 2-0-3; R42 sniper 2-3-0 first; R43 sniper 0-2-2; R45 Alch 3-0-0 closest to 2-3-0 sniper + glue; R47 Alch 4-0-0; R48 sniper 0-3-2; R49 village 2-0-2; R51 sniper 2-4-0; R59 sniper 2-5-0 first; R82 Alch 5-0-0; R84 sniper 0-2-4; R89 sniper 0-2-5; R90 invisibility potion on heli; R93 new Sniper 4-2-0 + invisibility potion on 0-2-5 and 2-5-0 snipers + stone on 0-2-5 sniper; R98/R99 glue; R99 sniper 5-2-0.
- Abilities: none; but Geraldo item placement/targeting on towers each few rounds. Heli lock-in-place one-time.
- Account conflicts: none. 0-2-5 Elite Defender was nerfed after v50 (OED v54.1) - weaker now.
**Strategy 2 - OneEyedDeacon UPDATED Geraldo + Axis of Havoc (v54.1, no abilities, no micro)** (source: https://www.youtube.com/watch?v=x66sSCIgVe0 ; OED v54.1 (post-Edef-nerf); confidence: verified-written-steps)
- Order: R6 Dart + Sniper1 Strong at 11 o'clock, TURN ON AUTOSTART (reason not stated); R8 Sniper2 Strong; R10 Sniper3 Strong; R12 Sniper4 FIRST; R15 Geraldo front; R16 spike(nails) back; R18 turret front; R19 Druid1 0-1-0; R21 glue front; R24 spike back; R25 glue front; R26 Druid 0-3-0; R27 1-3-0; R28-30 Sniper4 0-1-0 -> 0-2-0 -> 0-2-1; R31-33 Sniper2 1-0-0 -> 1-0-2; R37 1-0-3; R40 1-0-4; R42 "camo druid1" (Geraldo potion, inferred); R43 glue + Village1 0-0-2; R44 Village2 0-0-2; R46 Village2 2-0-2; R47 Sniper4 0-3-2 + glue; R48 Sniper2 2-0-4 First; R49 Alch 3-2-0 for sniper4; R50 Village1 0-2-2; R53 Sniper4 0-4-2; R62 Sniper2 2-0-5; R70 Sniper4 0-5-2 First; R73 Druid 1-4-0; R80 10x mines (Geraldo item, UNVERIFIED name); R84 Druid 1-5-0; R85 Alch 4-2-0 + Sniper3 3-2-0; R88 4-2-0; R90/92/93/98 all spikes (nails); R97 Sniper3 5-2-0; R98-99 genie bottles; R100 4x blade trap.
- Abilities: none, but very item-heavy (Geraldo shop).
**Strategy 3 - G-Horizon Psi + 7 snipers + Druid + Perma Brew (v53, no abilities/micro)** (source: https://www.youtube.com/watch?v=6QOiPh3CY1w ; G-Horizon v53; confidence: video-description chapter list (rounds given))
- Order: R6 Dart + Sniper1 Strong (Auto Start ON, R7 OFF); R8/R10/R12/R13/R15 Snipers 2-6 Strong; R19 Psi Strong; R21 Druid + Sniper1 First; R22 Druid 0-1-0; R27 0-3-0; R28 1-3-0; R30 Sniper1 0-2-0; R32 0-2-2; R36 0-2-3; R40 0-2-4; R44 Village 2-0-2; R46 Alch 3-2-0; R53 Sniper1 0-2-5; R55 Alch 4-2-0; R80 Alch 5-2-0; R81 Sniper2 0-3-2 First; R82 0-4-2; R85 0-5-2 First; R90-96 Snipers 3-6 to 0-2-4 First; R97 Sniper7 2-0-4 Strong.
- No items, no abilities, no aiming - but carry is 0-2-5 Elite Defender at R53, which OED says was nerfed (v54.x); OED switched to 2-0-5. Substitute (inferred): make Sniper1 2-0-4 -> 2-0-5 instead of 0-2-4 -> 0-2-5 (needs a camo source: druid/village 0-2-x).
- Other: Hbomb/Chom Chom (https://www.youtube.com/watch?v=olxHJYGSsY4), Dabloon (https://www.youtube.com/watch?v=bi2t_Xd_W4E), sYnce Rosalia + Flying Fortress v55.2, Commander Ryu Rosalia + Apache Prime v56, BTD Flagship v53.2 no abilities (https://www.youtube.com/watch?v=3UBDubycS2M).
**Bot notes:** Strategy 3 is the most bot-friendly (only placements, upgrades, targeting) - but apply the 2-0-5 Edef substitution and note the docs: Psi has range None in the bot's HEROES table, so the placement check refuses Psi on moving ground (model bug to fix or swap hero, e.g. Quincy which fits the one steady cell). Strategies 1-2 need Geraldo item purchases/placement (shop UI) - only if the bot supports Geraldo items. Auto Start toggle in sources is optional. Heli "fixed place" = Lock in place one-time setting.

### Mesa (Advanced)
**Map traits / what it requires:** Two simultaneous lanes (top 14.5, bottom 11.1 - bottom is shorter and leaks first; R40/60/80/100 MOABs come on the top lane per fandom) separated by sight-blocking rock walls / elevation. Only the strip top-right of centre reaches both lanes (with confusing targeting); the large top-left plateau is high ground where snipers/supports see the map; a rock island inside the bottom lane's loop is the best bottom-lane spot. Three $500 hoodoo rocks (become LOS-free high ground). bloonswiki: "one of the most difficult Advanced maps"; recommended Perma-Spike (reaches both exits, Smart), Corvus, Giant Condor (move blimps to top lane), Symphonic Resonance.
Effectively REQUIRED: Snipers on the plateau (global; Axis of Havoc) or Perma-Spike - ground towers see one lane.

**Strategy 1 - OneEyedDeacon Etienne + Axis of Havoc snipers + Glaive Lord, no abilities, no micro** (source: https://www.youtube.com/watch?v=CVxEdZq3I2c ; OED v54.1 (post-Edef-nerf rework); confidence: verified-written-steps)
- Hero: Etienne
- Core: Sniper1 0-5-2 (Elite Sniper), Sniper2 2-0-5 (Elite Defender), Sniper3 5-2-0 (Cripple MOAB), Boomerang 5-0-2 (Glaive Lord), Village 4-0-2, Alch 4-2-0, Glue 0-2-4, 3x Dart.
- Order (verbatim): R6 Dart1 Strong (left) + Dart2 "splitting tracks, range border touches wheel" + Dart3 Strong hugging the bottom cliff; R8 Sniper1 during round, as high as possible on platform (leave on first); R10 Sniper2 Strong during round, left of sniper1; R14 Etienne in front of dart2; R15 Boomerang1 behind dart2; R16 1-0-0; R17 2-0-0; R19 3-0-0; R20 3-0-1; R21 3-0-2; R22 Sniper2 1-0-0; R24 1-0-1; R26 1-0-2; R27 Sniper1 0-1-0; R28 0-2-0; R29 0-2-1; R30 0-2-2; R35 Boomerang 4-0-2; R36 Sniper2 2-0-2; R39 2-0-3; R42 2-0-4 on first; R44 Village1 0-0-2; R46 Sniper1 0-3-2; R47 Alch1 3-0-0; R48 Village 2-0-2; R49 3-0-2; R51 Sniper1 0-4-2; R60 Sniper2 2-0-5; R63 Alch1 4-2-0; R71 Sniper1 0-5-2 on first; R83 Boomerang 5-0-2; R84 Sniper3 3-2-0 Strong; R85 4-2-0; R86 Village 4-0-2; R87 Glue1 0-2-3 Strong in front of Etienne; R89 0-2-4; R97 Sniper3 5-2-0.
- Abilities: none. Account conflicts: none.
**Strategy 2 - OneEyedDeacon Obyn + Axis of Havoc + druid (v50.0)** (source: https://www.youtube.com/watch?v=cz7PaKRVwyM ; OED v50.0; confidence: verified-written-steps; author: "Previous guide apparently has issues due to the 025 sniper nerf") - Obyn brambles spam, Wall of Trees refreshed R63-R99, Sniper1 0-2-5 R49, right barrier removed R93 ($500). Superseded by Strategy 1.
**Strategy 3 - Perma-Spike based (older)** (sources: H2K Zeus v34 Perma-Spike (https://www.youtube.com/watch?v=ZFfMDy49m90), Dabloon Ultra-Juggernaut 70k left (https://www.youtube.com/watch?v=f4BhItKNqz4, ~6y), sYnce Psi + Spectre + Monarch of Storms v54.3 (https://www.youtube.com/watch?v=vYoEyINu9gI), Lazynomicro (https://www.youtube.com/watch?v=7bHbY8hpriU); confidence: video-only, no rounds).
**Bot notes:** Strategy 1 is ideal (post-nerf, no abilities, no aiming). Mid-round placements R8/R10 -> bot buys as soon as affordable. Docs: the bot's sight grid ignores the rock island height and rates the bottom lane invisible from every legal ground spot - snipers are global so this mostly matters for the darts/boomerang strip; the damage model will under-rate, trust the guide. Placement precision of Dart2 ("splitting tracks") and Sniper1 (as high as possible) matters.

### X Factor (Advanced)
**Map traits / what it requires:** Four entrances/exits; two lanes active each round and the spawn side rotates every round (alternating + simultaneous); bloons cross the middle through tunnels where they are invulnerable (~31-44% of each path hidden) and move erratically through corner mini-loops. $2,000 central military stack removable (central platform). bloonswiki: "generally seen as the hardest Advanced map"; global towers suffer from 2 lanes, short-range towers miss half the map; recommended Psi (hits anywhere, stuns), Snipers (early pivot, Maim MOAB), Carpet of Spikes (DDTs, BAD).
Effectively REQUIRED: Snipers (global) - every modern written guide is sniper-based; Psi strongly recommended.

**Strategy 1 - OneEyedDeacon Sauda + Axis of Havoc + PoD, no abilities, no micro (v54.1)** (source: https://www.youtube.com/watch?v=IRdVGDWzArY ; OED v54.1 (post-nerf); confidence: verified-written-steps)
- Hero: Sauda
- Core: Sniper1 2-0-5 (Elite Defender), Sniper2 0-5-2 (Elite Sniper), Sniper3 5-2-0, Druid 1-3-0, Village 4-2-0, Alch 4-2-0 x2, Wizard 2-0-5 (PoD), Glue 0-2-4, Tack 2-0-4, 2x Dart.
- Order (verbatim): R6 Dart1 right (top-left as possible in corner) + Dart2 left (2nd circle, bottom as possible, range touches small wood plank); R7 Sniper1 Strong; R9 Sniper2 Strong; R12 Sauda above middle, top-left as possible on platform; R14 Druid1 below middle; R15 0-1-0; R17 0-2-0; R21 0-3-0; R22 1-3-0; R23 Sniper2 0-1-0; R25 0-1-1; R27 0-1-2; R28 0-2-2 on first; R29 Sniper1 1-0-0; R30 1-0-1; R31 1-0-2; R36 1-0-3; R37 2-0-3; R41 2-0-4 on first; R42 Sniper2 0-3-2; R46 Village1 2-2-0; R49 Alch1 3-2-0 for sniper2; R51 Sniper2 0-4-2; R58 0-5-2 on first; R68 Sniper1 2-0-5; R71 Alch1 4-2-0; R73 Sniper3 3-2-0 Strong; R76 4-2-0; R79 Wizard1 2-0-4; R85 2-0-5; R86 Alch2 4-2-0 for wizard1; R87 Village 3-2-0; R88 4-2-0; R90 Glue1 0-1-3 Strong; R98 Sniper3 5-2-0; R99 Glue 0-2-4; R100 Tack1 2-0-4.
- Abilities: none. Account conflicts: none (Village 4-2-0 OK).
**Strategy 2 - G-Horizon Psi + 7 snipers + Druid + Perma Brew (v53.2)** (source: https://www.youtube.com/watch?v=cbqYU4k5f0o ; G-Horizon v53.2; confidence: video-description chapter list)
- Order: R6 2x Desperado; R8 Sniper1 Strong (mid-round); R10 Sniper2 Strong (mid-round); R12/R14/R15 Snipers 3-5 Strong; R19 Psi Strong; R21 Druid; R27 Druid 0-3-0; R28 1-3-0; R32 Sniper1 0-2-2 First; R36 0-2-3; R40 0-2-4; R44 Village 2-0-2; R46 Alch 3-2-0; R53 Sniper1 0-2-5; R55 Alch 4-2-0; R80 Alch 5-2-0; R81 Sniper2 0-3-2 First; R83 0-4-2; R85 0-5-2 First; R88-96 Snipers 3-6 to 0-2-4 First; R97 Sniper7 2-0-4 Strong.
- Flag: relies on 0-2-5 Elite Defender (nerfed per OED v54.1) - substitute 2-0-5 path (inferred).
**Strategy 3 - OneEyedDeacon Obyn + Axis of Havoc (v49.3)** (source: https://www.youtube.com/watch?v=Kf_J-Dfmp-s ; confidence: verified-written-steps) - needs R8 targeting micro, bramble spam, Wall of Trees R83/84/99; superseded by Strategy 1.
- Other: Doreo Obyn + 2 Savatars + Perma Brew v48.2 (https://www.youtube.com/watch?v=VQzGI2T3sYk), wellordering (abilities R76/R78), sYnce Psi + Spectre + Carpet of Spikes v54.3, sYnce Striker + Lord of the Abyss (LOCKED Mermonkey T5), MaxMonki Psi (ability R96/R98).
**Bot notes:** Strategy 1 is ideal (post-nerf, no abilities, no micro, only targeting changes). Dart placements are precise ("range border touches small wood plank"); Sauda placement "top-left on platform above middle". Bot model: invulnerable tunnel parts are flagged; snipers cover all. Desperado (G-Horizon) needs one per right-side corner (R6 spawns right corners).


### Sunken Columns (Advanced)
**Map traits / what it requires:** Two simultaneous lanes (18.8 RBS each) that cross twice (top and bottom crossing). The two hexagonal middle columns are sunken: towers there have their sight blocked by the track walls except through narrow gaps. All guides build on the raised outer land, mostly the top column (spawn camp, covers both entrances and the top crossing) plus the bottom/left corners. Water: two ponds inside the depressions ($1,000 each to fill in; rarely bought, still sight-blocked). Effectively REQUIRED: something that covers both lanes from the raised spots. In practice that is snipers (global, from the raised land only) and/or a 1-5-0 Spirit of the Forest (vines along the whole track). The bot model marks the raised outer land as unplaceable (known model gap), so every guide spot is currently illegal for the bot.
**Strategy 1 - Sauda + Spirit of the Forest + Axis of Havoc snipers, no abilities, no micro** (source: https://www.youtube.com/watch?v=_GHS1QFoyUY ; OneEyedDeacon; v54.2, ~6 months old; confidence: video-description, full round list)
- Hero: Sauda (R11, "on bottom").
- Core towers: Dart x4 0-0-0 (top column); Druid 1-3-0 -> 1-5-0 Spirit of the Forest; Village x2 (2-0-2 and 0-2-2); Sniper1 2-0-5 (Strong -> First at R49), Sniper2 0-5-2 (First), Sniper3 5-2-0 (Strong); Alchemist 4-2-0 for Sniper2; Glue 0-2-3 (Strong).
- Purchase order: R6 Dart1, Dart2, Dart3 0-0-0 on top; R8 Dart4 next to the middle dart; R11 Sauda on bottom; R13 Druid1 next to Sauda; R14 Druid 0-1-0; R15 0-2-0; R20 0-3-0; R21 1-3-0; R28 Village1 0-0-2; R33 Village2 0-0-2; R34 Sniper1 on Strong, left of the villages; R35 Sniper1 1-0-1; R36 2-0-1; R37 Sniper2 0-2-0 on First; R38 Sniper1 2-0-2; R39 2-0-3; R40 Village1 (right) 2-0-2; R42 Sniper2 0-3-2; R44 Village2 0-2-2; R46 Alch1 3-2-0 for Sniper2; R49 Sniper1 2-0-4 on First; R51 Sniper2 0-4-2; R59 Sniper2 0-5-2 on First; R68 Sniper1 2-0-5; R71 Alch1 4-2-0; R73 Druid 1-4-0; R84 Druid 1-5-0; R85 Sniper3 3-2-0 on Strong; R87 Sniper3 4-2-0; R89 Glue1 0-2-3 on Strong; R97 Sniper3 5-2-0.
- Key placements: darts on the top column. Sauda and the druid at the bottom. Villages and snipers grouped (sniper1 "left of villages").
- Abilities used: none.
- Account conflicts / substitutes: none (village 2-0-2/0-2-2, alch 4-2-0, sniper tier 5s are all within caps; Sauda owned).
**Strategy 2 - Old (v32.2) CHIMPS table: Etienne + druids + 4-0-0 Ace + wizards + spike line** (source: https://bloons.fandom.com/wiki/C.H.I.M.P.S./Strategies ; fandom wiki; v32.2 (2022) - balance has changed a lot since; confidence: wiki (order only))
- Hero: Etienne (Psi as an alternative).
- Core towers: Dart, Sniper 1-2-0, 2 Druids (one 1-3-0), Ace 4-0-0 for R40, 2x Wizard 0-2-4 near the entrance, Spike Factory 0-2-4 -> 5-0-1? (listed as "Sky Shredder 5-0-1"), Perma-Spike, Glue 2-0-4, Ice 5-2-0 Super Brittle, Alchemist, Village 2-0-0.
- Purchase order: start Dart, Sniper; 2nd Dart, Druid, Etienne; 2nd Druid, Druid1 1-3-0, Sniper 1-2-0; R40 Ace 4-0-0; mid: 2x Wizard 0-2-4, Spike 0-2-4 (alched), Alch for the Ace, Village 2-0-0; late: Sky Shredder (Ace 5-0-1), Perma-Spike, Glue 2-0-4, Super Brittle; Etienne/Psi abilities on R78/R80/R98.
- Abilities used: hero abilities on R78/80/98.
- Account conflicts / substitutes: none. Ace 4-0-0 Ground Zero is an ability (needs aiming-free press only; OK).
Other proven runs with no written steps: Omen "Perma Spike makes Sunken Columns CHIMPS easy" (https://www.youtube.com/watch?v=MNrN78EcAX4); Junky yard Gwendolin + Inferno Ring, "no micro" (https://www.youtube.com/watch?v=B6EsDJum5Jo); Fynn Sauda + snipers + Tack Zone + Perma-Spike + Carrier Flagship (https://www.youtube.com/watch?v=VQebEc-GpNg). Wiki recommends Sauda, Glaive Lord near a crossing, and Super Glue (0-0-5) to hold bloons in the crossings.
**Bot notes:** Strategy 1 needs no abilities, no aiming and no selling. It is the best fit, but only after the bot model can place towers on the raised outer land (top column, bottom column, bottom-left corner); today only the sunken middle is legal and it sees almost nothing. The damage model must also credit Spirit of the Forest vines over the whole track and snipers only from raised spots. The R40 Ace in Strategy 2 relies on default circle flight (fine) but is an old-version plan.

### Midnight Mansion (Advanced)
**Map traits / what it requires:** Two simultaneous lanes share the top floor, then go down opposite staircases to a central exit. About 55% of each lane is hidden or covered track. Magic fire walls swap every 2 rounds and block line of sight: top-middle and bottom-middle lines on rounds 1+4n/2+4n, the staircases on 3+4n/4n. Very little land: no Heli or Banana Farm fits, and Village, Super, Ace and Spike Factory fit only on the two drawers ($250 each, removable). Towers on the drawers ignore the fire walls (fandom). Effectively REQUIRED: a crowd-damage chokehold on the shared top floor (top-left or top-right corner), which is where Sauda's Sword Charge double-hits. Also a drawer must be bought for any Village. Global towers are not a must; every guide uses the top-floor bends.
**Strategy 1 - Sauda + Overdrive -> Tack Zone + Super Brittle + Icicle Impale** (source: https://www.youtube.com/watch?v=KVlfBvOU0F0 ; NamelessBandicoot; ~11 months old (v50-52 era); confidence: video-description (order only, few round numbers))
- Hero: Sauda.
- Core towers: Tack 2-0-4 Overdrive -> 2-0-5 Tack Zone; Village (on a drawer) + Alchemist for the Overdrive; Ice 2-0-4 -> 2-0-5 Icicle Impale; a second Ice 5-x-x Super Brittle; Glue 4-0-2 by R92 (alternative: a Spirit of the Forest druid inside village range).
- Purchase order: early Sauda + towers (not written); upgrade Village and Alchemist "for the overdrive" first; R37 Sauda ability for the camo whites; then Ice 2-0-4 "for later"; then Tack Zone, Super Brittle and Icicle Impale in succession; Glue 4-0-2 by R92; R92-100 turn off auto-start and buy upgrades before each round; R100 Sauda level-10 ability after the BAD pops. With the druid variant the tier-5 order is tack - druid - impale - brittle.
- Key placements: top-floor corner chokehold (wiki: Sauda best top-left or top-right); village on a drawer; druid variant must be in village range.
- Abilities used: Sauda R37 (camo whites); "be ready to use abilities for accidental leaks" on R92-100; Sauda level 10 on R100.
- Account conflicts / substitutes: none.
**Strategy 2 - Etienne / Sauda Solver-style (wellordering updated guide)** (source: https://www.youtube.com/watch?v=rOM6jI0VuYA ; wellordering; ~1 year old; confidence: snippet-only (the description only says: follow the video; with the old Sauda version, place Sauda on R18 instead of Etienne; "you'll need a 0-3-2 Dart!"))
- Hero: Etienne (or Sauda on R18).
- Core towers: not written beyond a 0-3-2 Dart (Crossbow Master line). UNVERIFIED.
- Abilities used: unknown.
**Strategy 3 - Doreo "EASY" Bloon Solver + Icicle Impale** (source: https://www.youtube.com/watch?v=TC_QN-SJ2VI ; Doreo; v43.3; confidence: snippet-only ("solver impale op, glord impale might be better"))
- Core towers: Glue 5-2-0 Bloon Solver + Ice 0-2-5 Icicle Impale (Glaive Lord as an alternative). Order and hero not in the text.
Corroborating sources: Steam thread https://steamcommunity.com/app/960090/discussions/0/4200239074420214057/ (a player cleared with Sauda + MOAB Eliminator + Tack Zone + Bloon Solver + several x-3-x Wizards + 2-3-0 Village, "before recent changes"; another failed at R98 with Sub Commander/Pre-emptive and Carrier/Sky Shredder; Pat fits only on the bookshelves). Other videos without steps: sYnce Obyn + Permanent Brew + Avatar of Wrath, v55.2 (https://www.youtube.com/watch?v=y0aFQcrR0uU); Mate_DLX v56 (https://www.youtube.com/watch?v=tAAo4Zf6U3E). BTD6 Index LTC: Monarch of Storms 5-0-2 + Geraldo; heroless Elite Defender + Archmage + Monarch of Storms (snipers on the drawers work).
**Bot notes:** No written round-by-round CHIMPS list exists, so all round numbers are inferred. The bot must buy a $250 drawer before any Village. Sauda abilities are pressed blindly: R37 on cooldown is fine, but "use abilities for accidental leaks" is reactive micro. Super Brittle, Impale and Tack Zone need no aiming. Leaks are mostly from bloons "colliding" on the shared floor (NamelessBandicoot), so stalling (glue) matters. Model gap: the shared top floor has no track cells in the model, so top-corner spots read about 0 reach, and the swapping fire walls are modelled as always on. Best bot fit: Strategy 1 (no aiming, no selling), with the bot's own round timing.

### Erosion (Advanced)
**Map traits / what it requires:** Six lanes, one active at a time. The active lane moves after R17, R35, R53, R71 and R89, and that ice melts: towers on it sink with no refund in CHIMPS (Pat Fusty, Ice, Mermonkey and towers on Arctic Wind ice survive). Lane lengths 7.2/9.0/11.7/10.9/7.8/4.3, so the R90+ lane is tiny. Only the top-right glacier is permanent: no Heli (blocked), one farm, about 3 villages in game (1 in the bot model). There is permanent water bottom-left for an early Sub. Effectively REQUIRED: map-wide damage from the glacier. Every written CHIMPS guide is a sniper core plus Psi, with Perma-Spike or Carpet of Spikes on the short final lane.
**Strategy 1 - Psi + Axis of Havoc snipers + Perma-Spike, no abilities, no micro** (source: https://www.youtube.com/watch?v=KOT6M9kcoUE ; OneEyedDeacon; v50.0; confidence: video-description, full round list)
- Hero: Psi (R20, "on ice ledge on strong").
- Core towers: Dart 0-0-0; Sub 1-0-2 (early); Sniper1 0-2-5 Elite Defender; Sniper2 0-5-2 (First); Sniper3 3-2-0; Sniper4 5-2-0; Alch1 4-2-0 (snipers), Alch2 4-2-0 (spike); Village 2-2-0; Spike 2-0-5 Perma-Spike; Glue 0-2-4.
- Purchase order: R6 Dart1 + Sub1; R8 Sub 0-0-1 (during round); R9 1-0-1; R11 Sniper1; R15 Sub 1-0-2 (during round); R20 Psi on the ice ledge, Strong; R21 Sniper2 under Sniper1; R23 Sniper3 under Sniper2, Strong; R24 Sniper3 1-0-0; R26 Sniper1 0-0-1; R27 0-0-2; R28 0-1-2; R29 0-2-2; R35 0-2-3; R38 0-2-4 (during round); R42 Sniper2 0-3-2; R45 Alch1 3-2-0 next to snipers 1+2; R47 Village1 2-0-0 next to Alch1 "as low as possible"; R50 Sniper2 0-4-2; R57 Sniper2 0-5-2 ON FIRST; R59 Alch1 4-2-0; R61 Sniper3 3-2-0; R64 Spike1 1-0-3 "as low as possible, targeting 2nd to last lane"; R66 Spike 1-0-4; R80 Spike 2-0-5; R82 Alch2 4-2-0 for the spike; R84 Sniper4 4-2-0; R88 "target spikes to top track exit"; R94 Sniper4 5-2-0 asap; R95 Glue1 0-1-3 on Strong; R97 Sniper1 0-2-5; R98 Glue 0-2-4 (during round); R99 Village 2-2-0.
- Key placements: everything on the permanent top-right glacier, kept low; Sub in the permanent bottom-left water.
- Abilities used: none.
- Account conflicts / substitutes: none.
**Strategy 2 - Psi + Elite Defender + Druid + Perma-Spike, no abilities/micro** (source: https://www.youtube.com/watch?v=No3NYnNZV1c ; G-Horizon; Update 53; confidence: video-description (chapter list with rounds))
- Hero: Psi (R19; Strong at R40).
- Core towers: Dart, Sub 1-0-2, Sniper 0-2-5, Druid 1-3-0, Village1 3-0-2, Village2 0-2-2, Alch 4-2-0, Engineer 5-0-2 Ultraboost, Ice1 0-3-1, Ice2 5-2-0 Super Brittle, Glue 0-2-4, Spike 2-0-5 (Smart).
- Purchase order: R6 Dart + Sub at [450,890] (1080p); R9 Sub 1-0-1; R14 1-0-2; R19 Psi; R20 Sniper; R27 Druid 0-3-0 (mid-round); R28 Druid 1-3-0; R30 Sniper 0-2-0; R32 0-2-2; R36 0-2-3; R40 Psi to Strong, Sniper 0-2-4; R44 Village1 2-0-2; R47 Alch 3-2-0; R53 Sniper 0-2-5; R55 Alch 4-2-0; R76 Village2 0-0-2, Ice1, Engineer 4-0-2; R77 Engineer 5-0-2 (mid-round); R78 Village2 0-2-2 (mid-round); R79 Ice1 0-3-0; R88 Ice2 5-2-0, Village1 3-0-2, Ice1 0-3-1; R92 Glue 0-2-4 Strong; R92-99 Spike 2-0-5 on Smart.
- Abilities used: none. "No RNG if you place on the listed rounds."
- Account conflicts / substitutes: none. Engineer 5-0-2 and a second village may not fit in the bot's glacier model; treat them as optional.
**Strategy 3 - Rosalia + Flying Fortress (OneEyedDeacon v49.3)** (source: https://www.youtube.com/watch?v=G5AX8dvEoKE ; confidence: video-description) - Sub 2-0-2, Ninja, Sniper 1-1-0, Ace 2-0-5 from R32 (0-0-2 "center path on bottom right exit"), Alch 3-2-0, Village 2-2-0, Spike 2-0-5 Smart. Needs many timed Rosalia jetpack/scatter missile/kinetic charge presses and Rosalia retargeting each round from R76 on, plus an Ace "Centered Path" set at a map point. NOT bot-suitable. Also: viby v44 Geraldo (https://www.youtube.com/watch?v=ZdjN2C_Sg0Y) uses many Geraldo shop items (pickles, totems, fires), so NOT bot-suitable.
**Bot notes:** Strategy 1 needs two Spike Factory set-target aims ("2nd to last lane" at R64, "top track exit" at R88). That is a one-time Set Target per change, so it is only OK if the bot can place a target point; otherwise use Strategy 2's spike on Smart. Strategy 2 needs no aiming and no abilities, but "mid-round" buys at R27/R77/R78 and a pixel-exact sub spot. Never place non-amphibious towers on ice that melts before they pay off; the early Dart/Sub are deliberately sacrificed. Best bot fit: Strategy 2 timings with Strategy 1's sniper core (both Psi). Required: global snipers on the glacier.

### Dark Path (Advanced)
**Map traits / what it requires:** Single lane (18.9 RBS) through a sunken gully. Rock walls block line of sight almost everywhere. Two raised rock stacks and a high central platform see over the walls (good for short-range towers and global towers). Buyable cave walls are 4 tiers per cave, $250/$500/$1,000/$1,000 (2 per tier). The central loops suit Mortar and wall-ricochet towers (Juggernaut). One exit, so Perma-Spike "guarantees victory" (wiki). The bot lost Hard at R25 because its ground spots saw nothing. Effectively REQUIRED: towers that ignore walls or use them (Heli/Ace/Etienne drones/snipers on high ground, Ultra-Juggernaut ricochet) plus Perma-Spike at the exit.
**Strategy 1 - "Lazy CHIMPS": Etienne + Ultra-Juggernaut + Blazing Sun + Super Brittle + Tack Zone, 8 stops, no abilities** (source: https://www.youtube.com/watch?v=eyIX-967nps ; BTD6 BluePrint; ~2 months old (v56-57); confidence: video-description, full list)
- Hero: Etienne (R12).
- Core towers: Desperado 5-2-0; Skywarden 2-0-0; Dart 5-2-0 Ultra-Juggernaut; Ice 5-2-0 Super Brittle; Tack 2-0-5 Tack Zone; Village 3-0-0. Note: the title says "Blazing Sun" but the written list has no Super Monkey; the written list is what is listed here.
- Purchase order: R6 Desperado + Skywarden, Desperado Strong; R9 Dart, Skywarden Strong; R12 Etienne; R19 Dart 3-2-0; R28 Dart 4-2-0; R37 Desperado 3-2-0, Ice 3-2-0; R57 Dart 5-2-0, Desperado 4-2-0, Ice 4-2-0, Skywarden 2-0-0; R85 Desperado 5-2-0, Ice 5-2-0, Tack 2-0-5, Village 3-0-0. These are the LATEST safe buy rounds; buying earlier is fine.
- Key placements: keep the walls (the Juggernaut ricochets off them); Ultra-Jugg on low ground.
- Abilities used: none. Spare cash at the end: $63k.
- Account conflicts / substitutes: Skywarden 2-0-0 is within the [4,3,3] cap. Village 3-0-0 is fine. None.
**Strategy 2 - SnartFarts: Quincy + Ninja + Alch + Village + Apache Prime + Perma-Spike** (source: https://www.youtube.com/watch?v=4AAtx2p1bwE ; SnartFarts; v52.2; confidence: video-description (order, no rounds))
- Hero: Quincy.
- Core towers: Ninja 4-0-2; Alch 4-2-0 x2; Village 2-3-0; Heli 5-0-2 Apache Prime; Spike 0-2-5.
- Purchase order: Quincy; Ninja; Ninja 3-0-2; Alch; Alch 3-2-0; Ninja 4-0-2; Alch 4-2-0; Village; Village 1-0-0; Heli; Heli 3-0-2; Village 2-2-0; Heli 5-0-2; Village 2-3-0; Spike; Spike 0-2-4; Alch2; Alch2 4-2-0; Spike 0-2-5.
- Key placements: everything in the open exit pocket (bottom-left).
- Abilities used: none listed. Account conflicts: none. (wellordering notes "Apache Prime is not" strong, while Perma-Spike is.)
**Strategy 3 - bloon.games: Obyn + Elite Defender + Superstorm + Perma-Spike** (source: https://bloon.games/how-to-beat-chimps-on-dark-path/ ; bloon.games / BTD6 Master; 2024 (v44-45); confidence: verified-written-steps (no round numbers except R40/R83/R95))
- Hero: Obyn. Core: Engineer + Dart start; Sniper 0-2-5; Village 1-0-2 -> 2-0-2 (after removing the two lower wall layers); Alch 3-2-0; Druid 4-0-2 -> 5-0-2 at R83; Spike 2-0-5 before R95.
- Order: Engineer + Dart; Sniper; Obyn ("use abilities whenever"); Sniper 0-2-2; remove the two lower wall layers, Village 1-0-2; Sniper 0-2-3; before R40 Sniper 0-2-4 then Village 2-0-2; Alch 3-2-0 next to the sniper; Sniper 0-2-5; Druid 4-0-2; R83 Druid 5-0-2; before R95 Spike 2-0-5.
- Account conflicts: none.
**Bot notes:** Strategy 1 is the best fit: 8 buy stops, no abilities, no aiming, no selling, all within account caps, current version. Desperado and Skywarden targeting are simple priority settings. Strategy 2's heli defaults to Follow Touch, so the bot must set Pursuit (unlocked at 2-x-x) or Lock in Place; then it is fine. Strategy 3 needs the bot to buy wall removables (it can). Model gap: high-ground stacks are rated blind, and the Juggernaut wall ricochet is likely under-rated by the damage model.

### Castle Revenge (Advanced)
**Map traits / what it requires:** Four entrances (2 wheel, 2 water/MOAB) merge into a top and a bottom lane that run at the same time to 2 exits on the left. Bloons are invulnerable while climbing the wheels. Castle walls block sight and projectiles, and no ground spot lets a short-range tower reach both lanes. The raised central platform sees the whole track. A $500 pressure valve knocks back non-MOAB bloons for 15 s (75 s cooldown) and blocks Perma-Spike-style exit placement. Wiki consensus: one of the 3 hardest Advanced maps. Effectively REQUIRED: global towers (snipers) or a fully mirrored defence per lane. Wiki extras: Carpet of Spikes (covers both lanes) and Giant Condor (needs the drop-off set by hand). Bot lost Hard at R46 because one lane leaked.
**Strategy 1 - Psi + Axis of Havoc snipers (back of map)** (source: https://www.youtube.com/watch?v=XUfUa1MSU9g ; OneEyedDeacon; v50.0; confidence: video-description, full round list)
- Hero: Psi (R19, "in front", Strong).
- Core towers: Dart x4 0-0-0 (top/middle/bottom), Dart3 3-2-0; Sub 0-0-0; Sniper1 0-2-5 (First), Sniper2 0-5-2 (First), Sniper3 5-2-0 (Strong), Snipers 4-6 0-3-2; Village 2-0-2; Alch 5-2-0; R100: 3x Tack 0-0-3 (Tack Sprayer).
- Purchase order: R6 Dart1 top + Dart2 middle + Dart3 bottom; R8 Sub1; R9 Dart4 (during round); R11 Sniper1 Strong ("as far back as possible"); R13 Sniper2 Strong; R14 Sniper3 Strong; R19 Psi (or during R18); R20 Dart3 0-2-0; R21 2-2-0; R22 3-2-0; R23 Sniper1 0-1-0; R25 0-2-0 on First; R27 Sniper3 1-0-0; R28 Sniper1 0-2-1; R29 0-2-2; R35 0-2-3; R39 0-2-4; R49 0-2-5 (during round); R50 Village 2-0-2; R52 Sniper2 0-3-2 ON FIRST; R54 Alch1 3-2-0 for snipers 1+2; R59 Sniper2 0-4-2; R60 Alch1 4-2-0; R81 Psi stun when the first 4-6 BFBs are on the track; R82 Alch1 5-2-0 (during round), maybe stun; R83 stun MOABs; R84 Sniper3 3-2-0; R85 4-2-0; R89 "052 sniper1 ON FIRST" (as written; it must be Sniper2 0-5-2); R91/92/93 Snipers 4/5/6 0-3-2; R95 Psi stun when the 4th DDT arrives; R99 Sniper3 5-2-0; R100 3x Tack Sprayer.
- Key placements: snipers in the back; Psi in front.
- Abilities used: Psi stun R81-83 and R95 (timed).
- Account conflicts / substitutes: none.
**Strategy 2 - Sauda + mirrored darts/tack/wizards + Mermonkeys + First Strike** (source: https://www.youtube.com/watch?v=JfjH7gMVRGw ; OneEyedDeacon; v53.1; confidence: video-description, full round list)
- Hero: Sauda (R12, bottom).
- Core: Dart1 4-0-2 (top), Dart3 4-0-2 (bottom); Tack 2-0-4 (top); Village x2 3-0-2; Wizard1 1-0-5 Prince of Darkness, Wizard2 0-3-2; Ice 4-1-0 (top); Glue 0-2-4 (Strong); Sub 2-5-0; Mermonkey x3 0-4-1; Alch x2 3-2-0; Sniper 1-0-0.
- Order: R6 3 darts (top lined with the track, middle, bottom); R8 Sub; R9 Dart4; R12 Sauda bottom; R14 Sniper Strong; R15 1-0-0; R16-19 Dart1 1-0-0 -> 2-0-0 -> 2-0-2 -> 3-0-2; R22-23 Dart3 3-0-0 -> 3-0-2; R29 Dart1 4-0-2; R30 Tack 0-0-2 top (far left); R31-33 1-0-2, 1-0-3, 2-0-3; R37 2-0-4; R40 Alch1 3-0-0 for the tack; R41 Dart3 4-0-2; R42 Village1 0-0-2 top; R43 Alch1 3-2-0; R45 Village2 0-0-2 bottom; R46 Wizard1 1-0-3 (middle); R48 1-0-4; R49 Wizard2 0-2-2 bottom; R50 0-3-2; R51 both villages 3-0-2; R55 Ice 4-1-0 top; R57 Glue 0-0-3 Strong; R59 Alch2 3-2-0 for Wizard1; R75 Wizard1 1-0-5; R76 Sub 2-3-0; R80 Sub 2-4-0; R82 Glue 0-2-4; R84 Mermonkey1 0-4-1; R94 Sub 2-5-0; R96 Mermonkey2 0-4-1; R98 Mermonkey3 0-4-1.
- Abilities: Sauda Leaping Sword R15/R22/R35, Sword Charge R65/R73; First Strike R80/85/88/97/100; Mermonkey ability on ZOMGs R85-R100 (up to 3x per round). Heavy, timed.
- Account conflicts: Mermonkey 0-4-1 is within the [4,4,4] cap. None.
**Strategy 3 - Gwendolin + Axis of Havoc (v49.3)** (source: https://www.youtube.com/watch?v=lkrli1pCqCk ; OneEyedDeacon; confidence: video-description) - the same sniper core, but it uses Gwen Cocktail/Firestorm on about 10 rounds. The author says Strategy 1 is more consistent.
Others without steps: SnartFarts Psi + Elite Defender + 3 helis + Ace 2-0-4 "centered path" (micro, https://www.youtube.com/watch?v=ATtcAJt_G4s); sYnce Striker + The Biggest One, v55.2; sYnce Etienne + Popseidon; Chom Chom Mermonkey combo (74k spare); Junxi Lin Elite Sniper + Primary Expertise (Primary Expertise is LOCKED on this account).
**Bot notes:** Strategy 1 is the best fit: snipers are global, there is no aiming, and the only abilities are Psi's stun (Psychic Blast, aimless global). Blind presses on R81-83/R95 are close to what the guide does, but timing "when the 4th DDT arrives" is not reproducible, so expect risk at R95. Strategy 2 is ability-heavy (Mermonkey and First Strike several times a round), so it is NOT bot-suitable. Bot must place snipers where they see both lanes (ground snipers see about 80% of their own lane and about 30% of the other; the raised platform sees all). Tack Sprayers at R100 are cheap filler.

### Last Resort (Advanced)
**Map traits / what it requires:** Single entrance and exit, with 4 alternating routes in a 4-round cycle: big loop (+80% speed), medium (+40%), small (+25%), straight (+15%). R63/R99 use the small loop, R78/R98 the medium, and R40/R76/R100 the straight. Only the top lane is used every round. Snow and snowmen platforms block sight; land is short. The $1,000 frozen pond opens one water spot. Single exit, so Perma-Spike "as far right as possible on the top section, Smart, with Jungle Drums + Berserker Brew" (wiki). Effectively REQUIRED: exit protection (Perma-Spike) plus towers on the top lane or global towers (snipers). Bot lost Hard at R24 on a small-loop round.
**Strategy 1 - Quincy + Axis of Havoc snipers + Perma-Spike, no abilities, no micro** (source: https://www.youtube.com/watch?v=7fpYt6w9ziE ; OneEyedDeacon; v49.3; confidence: video-description, full round list (from project docs))
- Hero: Quincy (R6, "in middle of pole").
- Core: Sniper1 5-2-0 (Strong), Sniper2 0-2-5, Sniper3 0-5-2 (First); Spike 2-0-5 (Smart, far right); Alch1 4-2-0 (Sniper3), Alch2 4-2-0 (spike); Village 2-2-0; Glue 0-2-4 (Strong).
- Order: R6 Quincy; R8 Sniper1 Strong, right of Quincy; R13 Spike as far right as possible; R16 Spike 0-0-2 Smart; R19 1-0-2; R20 Sniper1 1-0-0; R26 Spike 1-0-3; R35 1-0-4; R36 Sniper1 2-0-0; R37 2-2-0; R39 3-2-0; R40 Glue 0-0-0 left of Quincy, Strong; R42 Village 2-0-0 left of the glue; R43 Sniper2 0-2-1 left of the village; R44 0-2-2; R46 0-2-3; R49 0-2-4; R50 Sniper3 0-3-2; R51 Alch1 3-2-0 for Sniper3; R52 4-2-0; R57 Sniper3 0-4-2; R59 Alch2 3-2-0 for the spike; R63 Sniper1 4-2-0; R64 Alch2 4-2-0; R80 Spike 2-0-5; R84 Sniper3 0-5-2 First; R94 Sniper1 5-2-0 (during round); R97 Sniper2 0-2-5; R98 Glue 0-1-3 -> 0-1-4 -> 0-2-4 Strong; R99 Village 2-2-0.
- Abilities: none. Account conflicts: none.
**Strategy 2 - FroStee Mate: Quincy + Glaive Lord + Perma-Spike + Spike Storm + Carpet, no micro, no abilities** (source: https://www.youtube.com/watch?v=VQd2aoDI_70 ; FroStee Mate; v46; 37k views; confidence: video-description (upgrade names by round))
- Hero: Quincy.
- Order (names as written): R6 Quincy; R8 Sniper (Strong); R9 Dart; R10 Boomerang; R15 Spike Factory, R18 Smart Spikes (Smart), R21 Bigger Stacks; R22 Full Metal Jacket (sniper); R27 Long Life Spikes, R35 Deadly Spikes; R36 Glaives + Red Hot Rangs, R37 Ricochet; R39 Alchemist Berserker Brew; R42 Village Radar Scanner; R45 MOAR Glaives; R46 Jungle Drums; R50 Wizard Dragon's Breath w/ Monkey Sense, Alchemist, Tack Overdrive w/ Even Faster Shooting; R51 Berserker Brew + Perishing Potions; R62 Stronger Stimulant + Perishing Potions; R75 Glaive Lord, Primary Training; R84 Perma-Spike; R88 Spike Storm + White Hot Spikes; R99 Carpet of Spikes.
- Inferred crosspaths: Boomerang 5-0-2, Spike1 1-0-5 (Perma), Wizard 3-0-2, Tack 2-0-4, Alchs 4-2-0/3-2-0, Village 3-2-0, Spike2 2-4-0 -> 2-5-0 (inferred).
- Abilities: none ("no micro no abilities"). Spike Storm's ability is not needed. Account conflicts: none.
**Strategy 3 - SnartFarts: Quincy + Ninja 2-0-5 + Wizard Lord Phoenix + Perma-Spike** (source: https://www.youtube.com/watch?v=RUf6olKIK0k ; v52.2; confidence: video-description (order only)) - Quincy "slightly left to the pole"; Dart; Ninja 2-0-2; Spike 0-0-2 Smart; Wizard 0-2-0 before R28; Spike 0-2-4 (as written); Alch 3-2-0; Wizard 0-2-4; Ninja 2-0-4; Alch 4-2-0; Dart 4-0-2; Village 2-0-0; Wizard 0-2-5; Spike 0-2-5 (as written); Ninja 2-0-5; Dart 5-0-2; Village "0-2-3" (probably 2-3-0). The Spike crosspaths are probably 2-0-5 written wrongly (UNVERIFIED).
Others: G-Horizon Silas + Engineer + ice army + Tack 2-0-5 + Spike 2-0-5, no abilities (https://www.youtube.com/watch?v=ZMNP7TvNo4U, round list in the bundle: R14 Silas, R22 Spike 0-0-2 Smart, R43 Ice x2, R50-51 Ice 4-1-0/3-1-0, R75 Ice 2-0-5, R81 Ice 5-1-0, R86 Tack 2-0-5, R96 Spike 2-0-5). wellordering: Carrier Flagship + Super Brittle. LastResort v56.2: Silas + Golden Justice. Napalm: Monarch of Storms.
**Bot notes:** Strategy 1 is the best fit: no abilities, no aiming, Perma-Spike on Smart, snipers global, current-ish (v49.3). Placement words matter: Quincy at the lamp post in the small loop. The model marks the small-loop interior unplaceable (model gap); test about (0.65,0.20). The bot must hold the fast small-loop and straight rounds: R63 (small), R76 (straight), R98-100. The frozen pond ($1,000) is optional; none of the top 3 guides needs it. Strategy 2 is a good second (all ground towers, no abilities).

### Enchanted Glade (Advanced)
**Map traits / what it requires:** Two alternating lanes (odd rounds bottom-left 14.2, even rounds top-right 16.8). They share the wavy stretch below the centre and the climb to one exit under the cherry tree. Trees block sight. The best ground is the bottom-centre island right below the shared stretch. The only water is the ring round the bottom-right island, far from the track (fine for Carrier Flagship planes or Sub Advanced Intel, not for direct fire). Effectively REQUIRED: crowd damage at the bottom-centre/below-centre (R63 = 122 ceramics on the bottom-left lane) or global towers. Perma-Spike at the shared exit is "integral to nearly all strategies" (wiki). Bot lost Hard at R63 (its spikes stood on an island with no track in range).
**Strategy 1 - FroStee Mate: Sauda + Druid of the Jungle + Sub + Bloon Solver + Spike Storm/Carpet + Icicle Impale, no micro** (source: https://www.youtube.com/watch?v=P5X5umWqjwA ; FroStee Mate; v47.0; 12.8k views; confidence: video-description (upgrade names by round))
- Hero: Sauda (R6).
- Order: R6 Sauda; R8 Boomerang; R10 Sub; R12 Druid; R19 Druid of the Jungle (0-3-0); R20 Hard Thorns (1-3-0); R32 Sub Triple Guns + Advanced Intel (2-0-3), Dart Monkey; R36 Armor Piercing Darts (Sub 2-0-4); R40 Alchemist Berserker Brew (3-0-0); R42 Village Radar Scanner (0-2-0); R47 Primary Mentoring (Village 4-2-0); R48 Glue Bloon Dissolver + Glue Splatter (3-2-0); R50 Bloon Liquifier (4-2-0); R63 Bloon Solver (5-2-0); R70 Spike Factory Spike Storm (0-4-0); R71 White Hot Spikes (2-4-0); R85 Carpet of Spikes (2-5-0); R87 Ice Icicles + Deep Freeze (0-2-4); R96 Icicle Impale (0-2-5). Crosspaths in brackets are inferred from the upgrade names.
- Abilities: none ("No Micro"). Spike Storm and Carpet have abilities but they are not needed.
- Account conflicts: Village 4-2-0 Primary Mentoring is within the cap. None.
**Strategy 2 - SnartFarts: Quincy + Carrier Flagship + Ninja 2-0-5 + Spirit of the Forest** (source: https://www.youtube.com/watch?v=MEHLrD12TMk ; v52.2; confidence: video-description (order only))
- Order: Quincy; Buccaneer; Bucc 2-2-0; Ninja; Ninja 2-0-2; Bucc 3-2-0; Ninja 2-0-3; Village; Village 2-0-0; Bucc 4-2-0; Village 2-2-0; Bucc 5-2-0 Carrier Flagship; Druid; Druid 1-5-0; Village 2-3-0; Ninja 2-0-5; Glue (Strong); Glue 0-2-4.
- Abilities: none listed. Account conflicts: none. Carrier Flagship deck placement is NOT used. Note (wellordering): Carrier Flagship was nerfed later but is "still amazing".
**Strategy 3 - CrimsonPlanet: Obyn + Wizard 5-0-2 + Heli 5-0-2 + Druid 1-3-0, no micro** (source: https://www.youtube.com/watch?v=50CsJ1u4_xw ; v52.2; confidence: video-description (order only)) - Dart; Mermonkey 1-0-0; Obyn; Druid 1-1-0; Wizard 3-0-2; Druid 1-3-0; Mermonkey 4-0-0; R40 Obyn ability; Wizard 4-0-2; Heli 4-0-2; Village 0-2-0; Wizard 5-0-2 Archmage; Village 2-3-0; Heli 5-0-2; Sub 0-4-0; optional Glue 0-2-4; R100 Sub ability (First Strike) recommended. Mermonkey 4-0-0 is within the cap.
Others: unescaped "braindead" Rosalia + Spectre + Permanent Brew -> Flying Fortress (https://www.youtube.com/watch?v=28MiiPGtBb8, steps only in a pinned comment, not retrieved); wiki: Druid of the Jungle -> Neva-Miss -> Spectre (2-2-0 village + Berserker Brew) -> Flying Fortress on R87-88 with Rosalia, using the Lots More Darts crosspath. sYnce Quincy + Perma-Spike + Lord of the Abyss (Mermonkey tier 5 is LOCKED on this account).
**Bot notes:** Strategy 1 is the best fit: Sauda, no abilities, no aiming, all ground towers on the bottom-centre/below-centre land, and the R63 Bloon Solver timing is exactly the bot's past failure point. Strategy 2 is also fine: the Carrier Flagship only needs to sit in the water ring (no deck use), and the Druid SotF gives map-wide vines. Strategy 3 heli defaults to Follow Touch, so the bot must set Pursuit; the Obyn R40 and Sub R100 presses are blind-pressable. Ace/Spectre lines (wiki) need a centred path or Neva-Miss (Neva-Miss is a default-fine upgrade, 2-x-x). Required map-wide tower: none if the bottom-centre is used; else a Carrier/Spectre/SotF.

### Sunset Gulch (Advanced)
**Map traits / what it requires:** Winding Bloon path (19.5) plus, from R39/40, a straight MOAB-only rail lane (10.5) whose exit sits under the right-hand shop panel. Blimps must die before about x 0.85. The two lanes share the bridge segment. The top rock fits a Spike Factory and the bottom rock an XL tower. No water. Effectively REQUIRED: something that hits the MOAB rail hard (snipers are global; Desert Phantom/Golden Justice along the straight; Perma-Spike set at the lane intersection). The bot already won Hard here.
**Strategy 1 - Sauda + Axis of Havoc + Permanent Brew, no abilities, no micro** (source: https://www.youtube.com/watch?v=uZcfkclocAs ; OneEyedDeacon; v53.1; confidence: video-description, full round list)
- Hero: Sauda (R6, "in back, as top left as possible").
- Core: Sniper1 4-2-0 -> 5-2-0 (First), Sniper2 0-2-4 -> 0-2-5 (First), Sniper3 0-5-2 (First), Snipers 4-6 0-3-2; Alch 5-0-0 Permanent Brew; Village 2-0-2.
- Order: R6 Sauda; R9 Sniper1 Strong "in back between two planks"; R11 Sniper1 1-0-0; R12 Sniper2 Strong; R14 Sniper2 0-0-1; R16 0-0-2; R17 0-1-2; R19 0-2-2 on First; R28 0-2-3; R36 0-2-4; R39 Village1 0-0-2 lined up with the plank right of the track; R40 Alch1 3-0-0 for Sniper2; R42 Alch1 4-0-0; R44 Village 2-0-2; R45 Sniper3 0-2-0; R46 0-3-2; R50 0-4-2; R56 0-5-2 on First; R57 Sniper1 2-0-0; R58 3-0-0; R59 3-2-0 on First; R63 4-2-0; R83 Alch1 5-0-0 (during round); R88 "025 sniper1" (as written; = Sniper2 0-2-5); R89 Sniper4 0-3-2; R92 Sniper5 + Sniper6 0-3-2; R99 Sniper1 5-2-0.
- Abilities: none. Account conflicts: none.
**Strategy 2 - bloon.games: Obyn + Elite Defender + Superstorm + Perma-Spike** (source: https://bloon.games/how-to-beat-chimps-on-sunset-gulch/ ; bloon.games / BTD6 Master; confidence: verified-written-steps (anchors R40/R83/R95 only))
- Order: Engineer at the entrance (Last); Dart at the exit; Obyn; Druid + Sniper; Sniper 0-2-2; Village 0-0-2; Sniper 0-2-3; before R40 Sniper 0-2-4; Village 2-0-2; Alch 3-2-0 next to the sniper; Sniper 0-2-5; Druid 4-0-2; R83 Druid 5-0-2; before R95 Spike 2-0-5.
- Abilities: "no micro" (Obyn abilities optional). Account conflicts: none.
**Strategy 3 - Striker + Bomb Axis (OneEyedDeacon v49.3)** (source: https://www.youtube.com/watch?v=y1PU-nNaKQE ; confidence: video-description) - R6 3 darts; R9 Sniper 0-2-2 (First by R19); R12 Striker top-right on the left curve; R20-33 Bomb1 0-2-4; R37-38 Alch 3-2-0; R40-45 Village 4-2-0 (+ Concussive Shell ability R40); R46 Bomb2 1-3-0 Strong; R58 Bomb1 0-2-5; R59-61 Bomb3 4-2-0; R64 Bomb2 1-4-0; R85 Bomb3 5-2-0; R95 Bomb2 1-5-0; R99 Village 5-2-0 + Bomb2 2-5-0; R100 MOAB Elim ability + Artillery Command + "spam elim". CONFLICT: Village 5-2-0 Primary Expertise is LOCKED (keep 4-2-0); timed abilities; the author notes Bomb Blitz was later nerfed. Not recommended.
Others: FroStee Mate Desperado "no micro no abilities" (one button press on R98, https://www.youtube.com/watch?v=YLydn1f2aYI, no steps); sYnce Quincy + Perma-Spike + Lord of the Abyss (Mermonkey 5 LOCKED).
**Bot notes:** Strategy 1 is the best fit (snipers only, no abilities, no aiming). "Sauda in back" = north of the rail (top-left cliff). Strategy 2 is equally simple and its Perma-Spike covers the rail exit; Perma-Spike on Smart (wiki suggests a Set Target at the intersection, which needs aiming). Bot already beat Hard with Obyn/magic.

### Party Parade (Advanced)
**Map traits / what it requires:** Two separate short lanes (11.3 each) run at the same time either side of a wide hedge wall that blocks placement AND sight. Snipers see only their own side, and Pursuit helis get stuck flying between lanes. No water, no removables. Rated near casual Expert (wiki). Effectively REQUIRED: either a fully mirrored build (one of each per lane) or map-wide towers that ignore the wall: Psi, Prince of Darkness (with village/Etienne range buff), Spirit of the Forest, Carpet of Spikes, Monkey Ace in any path except Wingmonkey (wiki). The bot lost Hard at R57 because it stacked one lane.
**Strategy 1 - Sauda + Tack Zone, mirrored (OneEyedDeacon)** (source: https://www.youtube.com/watch?v=FgmIs2s7cL0 ; OneEyedDeacon; v53.0; confidence: video-description, full round list)
- Hero: Sauda (R12, right; target switched Close/First on several rounds).
- Core: Desperado x2 0-0-0; Dart x2; Tack 2-0-5 Tack Zone (left); Sniper x2 1-x-0; Spike1 4-2-0 (left), Spike2 4-2-0 (right), Spike3 2-4-0 Spike Storm (left); Village x2 3-0-2; Alch1 4-2-0, Alch3 3-0-0; Wizard 0-3-2; Ice x2 4-1-0; Glue x2 0-2-4 (Strong), Glue3 2-4-0 Glue Strike; Boomerang x6 0-2-4 MOAB Press (Strong); Engineer x2 0-3-1.
- Order: R6 Desperado1 + Desperado2; R8 Dart right; R9 Dart left; R12 Sauda right; R13 Tack left; R15 Sniper1 left Strong; R16 Sniper2 right Strong; R20 Spike1 left; R22-23 snipers 1-0-0; R24 Tack 1-0-2; R26 2-0-2; R27 2-0-3; R30 Spike2 right; R36 Tack 2-0-4; R38 Village1 1-0-2 left; R39 Spike1 1-0-0; R40 Alch1 3-0-0; R41 Sniper1 1-1-0; R44 Village2 1-0-2 right + Wizard 0-2-0 next to Sauda; R46 Wizard 0-3-0; R47 Village1 2-0-2; R48 Spike1 1-2-0; R49 3-2-0; R50 Alch2 3-0-0 for Spike1 + Spike2 3-0-0; R51 Wizard 0-3-2 + Ice1 2-0-0 -> 3-0-0; R53 Alch3 3-0-0 for Spike2; R55 Spike2 3-2-0; R56 Ice1 4-1-0 + Village2 2-0-2; R58-59 Alch1 4-0-0 -> 4-2-0; R60 Village1 3-0-2; R62 Ice2 4-1-0 right; R64 Glue1 0-0-3 right; R65 Village2 3-0-2; R67 Glue2 0-0-3 left; R74 Spike2 4-2-0; R80 Tack 2-0-5; R83 Spike1 4-2-0; R84 Glue1 0-2-4; R85 Glue2 0-2-4; R86/R89 Boomerang 0-2-4 x2 right; R90 Engineer 0-3-1 left; R91 Engineer 0-3-1 right; R93/R94 Boomerang 0-2-4 x2 left; R95 Glue3 2-3-0 right; R96 Spike3 2-3-0 left; R97 Boomerang 0-2-4 x2 right; R99 Spike3 2-4-0 + Glue3 2-4-0; R100 Glue Strike when the BAD is in Tack Zone range, then Spike Storm.
- Abilities: Leaping Sword R36/R40/R43/R50; Sword Charge R60(optional)/R75/R78/R98; Glue Strike + Spike Storm R100 (timed). Sauda target swaps R36/37/43/44.
- Account conflicts: none (Village 3-0-2 OK).
**Strategy 2 - Silas + Icicles spam + Carpet of Spikes** (source: https://www.youtube.com/watch?v=RcmAOifd91w ; sYnce; v55.2; confidence: snippet-only (title only; no steps)). Hero Silas (owned); Ice 0-x-4 Icicles towers in numbers + Spike 2-5-0 Carpet (covers both lanes). Order UNVERIFIED.
**Strategy 3 - no-ability videos without written steps:** FroStee Mate "NO MICRO, NO ABILITIES" v53.0 (https://www.youtube.com/watch?v=qky5Q-E0dxs); Doreo "EASIEST ... No Abilities/Micro" v53.0 (https://www.youtube.com/watch?v=BhpXTTWP5WI, 33.7k views); Vadim X Rosalia "without any RNG"; Chom Chom Bomb Blitz and Plasma Monkey Fan Club; Kaka Cake Striker + bomb spam. Towers and orders are UNVERIFIED (descriptions empty).
Mirrored templates from other modes (project docs, BeatbloonsBob Double HP/Impoppable v53): one Mermonkey per lane -> 4-2-0, Sauda, Wizard 0-2-2 x2, Sniper 0-2-4/0-2-5 per side, Spike 1-0-4 Smart per exit, Boomerang 2-0-4 Strong, Village 4-2-0, Ace 2-0-3 (covers both lanes). Mermonkey 4-2-0 is within the cap. BTD6 Index LTC: Golden Justice + Avenger + Pop and Awe 2-5-0 + Geraldo (owned; note Pop and Awe is Mortar 0-5-0 line, within the mortar cap).
**Bot notes:** Strategy 1 is the only full written CHIMPS list, but it uses about 12 timed abilities (Sauda Leaping Sword/Sword Charge, Glue Strike and Spike Storm "when the BAD is in range") and several Sauda target swaps. The swaps are settable; the timed abilities are not reliable when pressed blindly. Glue Strike and Spike Storm are aimless globals, so a blind press at R100 start may still work. The author also notes the top-path ice was bugged vs the R100 BAD. Strongly consider the wiki's map-wide picks (Spike 2-5-0 Carpet, Druid 1-5-0 SotF, Wizard 0-0-5 PoD with a range buff, Ace Neva-Miss 2-x-x) plus a mirrored base; the Hard/Double HP mirrored builds already have this shape. RULE: never buy a second tower for one lane before its mirror. Best bot fit: Strategy 1 without the optional abilities, adding a second Carpet/Perma per lane as insurance (inferred).

### Mushroom Grotto (Advanced)
**Map traits / what it requires:** Two simultaneous lanes (18.6/18.8) loop twice through the centre. Darkness: towers can be placed only on lit ground and can target only lit zones. At the start only a small centre circle is lit. Removables: 4 small mushrooms ($250 each) light the corners, and the big centre mushroom ($400, only after all 4) enlarges every zone. Guides buy them all by R25-36. Mortars and Dartlings fire without a target (wiki); Carpet of Spikes is concentrated if nothing is lit. Effectively REQUIRED: buy the mushrooms (~$1,400) before relying on global snipers or a village. Early game must be done from the lit centre.
**Strategy 1 - Sauda + Mermonkeys/darts -> Axis of Havoc + Glaive Lord, no abilities** (source: https://www.youtube.com/watch?v=hO9LkFVka6M ; OneEyedDeacon; v54.0; confidence: video-description, full round list)
- Hero: Sauda (R12, Close, above mermonkey2).
- Core: Mermonkey x2 0-0-0; Dart x2 0-3-0; Tack 0-0-0; Sniper1 2-0-5 (First), Sniper2 0-5-2 (First), Sniper3 5-2-0 (Strong); Boomerang 5-0-2 Glaive Lord; Village 3-2-0; Alch 4-2-0; Glue x2 0-2-4/0-2-3 (Strong).
- Order: R6 Mermonkey1 + Mermonkey2; R8 Dart1 bottom-left; R9 Dart2 top-right; R12 Sauda Close above mermonkey2; R13 Dart1 0-1-0; R14 Sniper1 Strong; R15 Tack top-left; R16 Dart2 0-2-0; R17 Dart1 0-2-0; R19 Dart2 0-3-0; R21 Dart1 0-3-0; R22 Sniper1 0-0-1; R24 0-0-2; R26 1-0-2; R27 Sniper2 First; R28 0-2-0; R30 0-2-1; R31 0-2-2; R32 Boomerang; R33 2-0-0; R34 2-0-2; R35 3-0-2; R36 buy 4 outer mushrooms + the middle one; R39 Sniper1 1-0-3; R40 2-0-3; R42 Village 0-2-0; R44 2-2-0; R46 Boomerang 4-0-2; R48 Sniper2 0-3-2; R49 Sniper1 2-0-4 First; R50 Alch 3-0-0 for Sniper2; R54 Sniper2 0-4-2; R63 Sniper1 2-0-5; R64 Village 3-2-0; R66 Alch 4-2-0; R81 Boomerang 5-0-2; R82 Sniper3 3-2-0 Strong; R84 4-2-0; R86 Sniper2 0-5-2 First; R89 Glue1 0-2-3 Strong right; R97 Sniper3 5-2-0; R99 Glue1 0-2-4 + Glue2 0-2-3 Strong left.
- Abilities: none. Account conflicts: none.
**Strategy 2 - bloon.games: Obyn + 2 Druids (Monarch of Storms) + Elite Defender + Perma-Spike** (source: https://bloon.games/how-to-beat-chimps-on-mushroom-grotto/ ; confidence: verified-written-steps (no round numbers))
- Order: Mermonkey x2; Dart x2; Obyn (abilities "for safer rounds", optional); Druid x2; Sniper 0-2-2 (middle path first); light the mushrooms, centre last; Sniper 0-2-3 -> 0-2-4; Alch 4-2-0 next to the sniper; Village 2-0-2 and Druid1 4-0-2; Druid2 4-0-2; Sniper 0-2-5; Druid1 5-0-2; Spike 2-0-4 -> 2-0-5.
- Account conflicts: none.
**Strategy 3 - G-Horizon: Psi + Tack blade shooters + Dart + Mermonkey Lord of the Abyss + Spike 2-5-0, no abilities/micro** (source: https://www.youtube.com/watch?v=eU_eTtiYX_o ; ~7 months old (v54-55); confidence: video-description with rounds and 1080p pixel spots) - R6 Tack1 [961,652], Tack2 [756,462]; R7 Dart Strong [962,766]; R10-14 Tack1 1-2-0 -> 1-3-0 -> 2-3-0; R17-19 Tack2 0-3-0 -> 2-3-0; R23 Psi Strong; R25 mushrooms TL+BR; R28 Sniper 1-0-0 Strong + mushrooms TR+BL; R30 centre mushroom; R33 Dart 3-0-2 First; R36 4-0-2; R40 Spike 1-3-0; R43 Mer 3-0-2; R46 4-0-2; R58 Mer 5-0-2; R60 Alch 3-2-0; R61 Spike 2-3-0; R82 Spike 2-5-0 (mid-round); R84 Village 3-0-2; R85 Glue 0-2-4 Strong; R90 Boomerang 0-2-4 x2 Strong; R92 Alch 4-2-0. CONFLICT: Mermonkey 5-0-2 Lord of the Abyss is LOCKED (cap 4); stopping at Mer 4-0-2 Abyssal Warrior leaves a gap (UNVERIFIED whether Carpet covers it).
Others: retrogaming fun Sauda + darts + boomerangs + Super 3-2-0 + Wizard 5-2-0 + Bomb 2-0-4 + Village 4-2-0, no abilities, no mid-round actions, v54 (written; full list in the bundle; it has a "retarget wall of fire" step that needs aiming); Doreo Superstorm no abilities/micro (no steps); HyperF3 v56 (Obyn + Desperado + Wizard + Glue Storm/Solver). BTD6 Index LTC: Monarch of Storms + The Blazing Sun.
**Bot notes:** The bot must buy all 5 mushrooms (4x $250, then $400) around R25-36; until then towers must stand in the lit centre and globals only hit lit zones (the model does not model darkness, so it over-rates snipers early). Strategy 1 is the best fit: no abilities, no aiming, no selling, all caps OK, and the mushrooms are bought in one stop at R36. Strategy 2 is also clean.

### Ascent (Advanced)
**Map traits / what it requires:** Two long simultaneous lanes (20.8 and 29.5); few sight blockers (pointed rocks, an elevated rock pool). The big central island lies inside both lanes. Ponds: top centre, by the right-hand exits, and bottom-left by the entrances. Heli Pursuit "may get confused" by the two lanes (wiki). One of the easiest Advanced maps: most comps work. Wiki tips: Perma-Spike on the middle platform at the bottom right hits both paths near the end (and fits in village range); a submerged Sub 3-0-1 at the start decamos all bloons. Effectively REQUIRED: none.
**Strategy 1 - CrimsonPlanet: Obyn + Wizard 4-0-2 + 2 Subs + Druid 2-5-0 + Heli 2-0-5, no micro & abilities** (source: https://www.youtube.com/watch?v=KEmm-iPaHl0 ; CrimsonPlanet; v56.0; confidence: video-description (order only, no rounds))
- Hero: Obyn.
- Order: Wizard 0-0-0; 2x Sub 0-0-0; Obyn; Wizard 3-0-2; Druid 1-3-0; Heli 2-0-3; Wizard 4-0-2; Druid 2-5-0 Spirit of the Forest; Village 2-3-0; Heli 2-0-5. Optional: Sub 2-5-0 instead of the Heli 2-0-5, Alch 0-3-0, Mermonkey 4-0-0, Glue 0-5-0 or 0-2-4.
- Key placements: wizard/druid/village on the central island (project docs); subs in the top pond.
- Abilities: none. Account conflicts: none (Mermonkey 4-0-0 OK).
**Strategy 2 - HyperF3: Obyn + Subs + Ninja + Poplust druids + Avatar of Wrath + Perma-Spike** (source: https://www.youtube.com/watch?v=TZg8hFFquZA ; HyperF3; v56; confidence: video-description (order only, from project docs))
- Order: Sub; Dart; Sub 0-0-1; Obyn; Ninja; Sub 0-0-2; Ninja 0-0-1; Druid; Druid 1-3-0; Spike Factory 0-0-2 -> 2-0-4; Village; 6x Druids; Druid 0-1-4; Village 2-2-0; 5x Druids 0-1-4; Glue -> 0-1-3; Druid 0-1-5 Avatar of Wrath; Village 2-3-0; Spike 2-0-5; Alch 4-2-0; Glue 0-2-4. $26,463 left at the end.
- Abilities: none listed. Account conflicts: none.
**Strategy 3 - sYnce: Rosalia + Flying Fortress** (source: https://www.youtube.com/watch?v=_dZ9AVBZ7w0 ; v56.0; confidence: snippet-only) - "free black border with no micro, no RNG and ability for free 99" (one Rosalia ability on R99). Ace 5-x-x; crosspath not in the text (wiki on Enchanted Glade suggests Lots More Darts 5-2-0; UNVERIFIED here). Order UNVERIFIED.
Others: BTD6 Fenix "No Abilities" (10.5k views, no text); MaxMonki Quincy "no micro or abilities" (no text); Hbomb Silas + Skywardens; N00BMaster477 Axis of Havoc instead of Skywarden. BTD6 Index LTC: MOAB Domination + Geraldo; heroless Spirit of the Forest 1-5-0 + M.A.D 1-5-0; cheapest Blazing Sun 5-0-2 + Geraldo.
**Bot notes:** Strategy 1 heli: the default is Follow Touch, so the bot must set Pursuit (2-x-x) or Lock in Place. Pursuit may wobble between the two lanes (wiki); Strategy 1 offers Sub 2-5-0 as the replacement (Pre-emptive Strike fires automatically; its First Strike ability is optional). Strategy 2 needs no heli and no abilities but has many towers (12 druids). Neither has round numbers, so the bot schedules by cash (inferred). Both use Obyn and a Spirit of the Forest or Avatar druid line, which the damage model should credit along both long lanes. The project model rates Aces near zero here (model gap).

### Ship Capture (Advanced)
**Map traits / what it requires:** Four short plank lanes (8.2-10.6) under a central ship, converging into 2 lanes that meet near the central grate/hatch. Rounds board from one side at a time (wiki table: Left 5-9, 15-19, 25-29, 35-39, 50-54, ...; Right 1-4, 10-14, 20-24, ...; Both 45-49, 60-64, 75-79, 90-94). The $1,000 hatch turns the grate into water; it can only be removed with nothing on it. Crow's nest (up to 5 small towers) and a quarterdeck. Effectively REQUIRED: none strictly. Stalling and exit protection matter: Perma-Spike with a Set Target between the two main lanes (wiki), plus Abyssal Warrior/Lord of the Abyss from central water if the hatch is removed.
**Strategy 1 - Obyn + Desperados + Skywardens + Spirit of the Forest + Perma-Spike + 3 MOAB Press, no abilities** (source: https://dq7reimagined.com/btd6/ship-capture-chimps/ ; "Player Atlas" web write-up; v57.0, page updated 2026-10-13; confidence: verified-written-steps (relative placements; the page warns v57.1 changed Skywarden interactions))
- Hero: Obyn (R12, beneath the Skywardens).
- Core: Desperado x2 (upper one 4-2-0 Strong); Skywarden x2 0-0-0; Druid1 1-5-0 SotF; Druid2 (Heart of Thunder -> Druid of the Storm + Druidic Reach, i.e. 2-0-1 inferred); Spike 2-0-5; Mermonkey 4-x-x Abyssal Warrior (Echosense crosspath); Village (discount upgrades, then Jungle Drums); Glue 0-2-4 (Strong); Boomerang x3 x-x-4 MOAB Press (Strong); Alch 3-0-1.
- Order: R6 2 Desperados on the central grate (upper, then just below); R8 Skywarden below the lower Desperado; R9 Skywarden2 right of it; R12 Obyn; R14 Druid left of Obyn; R18 Spike above the druid; R20 Spike 0-0-2, Set Target near the bottom of the grate between the two exit routes; R25 Spike 1-0-2; R26 Mermonkey beside the druid, Druid Hard Thorns; R32 Village above the spike (discount upgrades); R35 Druid of the Jungle; R36 Spike 1-0-3; R39 1-0-4; R40 Village Jungle Drums (after the round); R43 Druid2 Heart of Thunder; R44 Druid of the Storm + Druidic Reach; R47 Druid1 1-4-0; R50 Desperado 4-2-0 Strong; R54 Mermonkey Abyssal Warrior; R75-76 Druid1 1-5-0; R77-84 Spike 2-0-4 -> 2-0-5; R85 Glue 0-0-4 Strong; R86 Glue 0-2-4; R88 Boomerang x-x-4 Strong; R92 Alch 3-0-1 by the spike; R94 two more MOAB Press.
- Abilities: none. Spend about $138k.
- Account conflicts: Skywarden 0-0-0 is fine; Mermonkey 4-x-x is fine (the cap is 4). Village path unclear ("discount" = bottom path, then Jungle Drums 2-0-x); inferred 2-0-2, within the cap.
**Strategy 2 - Etienne + Carrier Flagship + Pirate Lord + Pre-emptive Strike (hatch removed)** (source: https://www.youtube.com/watch?v=MmIHEDOuMwI ; 신사알파카; v57.0; confidence: snippet-only (hero and tier 5s only)). Needs the $1,000 hatch removed first, then Buccaneer 5-2-0 Carrier, Buccaneer 0-0-5 Pirate Lord (its ability needs timing), Sub 2-5-0. Order UNVERIFIED.
**Strategy 3 - Silas + Carpet of Spikes** (source: https://www.youtube.com/watch?v=GkC3sViEC3w ; sYnce; v57.0; confidence: snippet-only). The description implies Ice Coldchain/Frozen Verdict/Winter's Mercy ice lines with Silas and a Spike 2-5-0. Order UNVERIFIED.
Others: FroStee Mate "NO Micro, NO Effort, SIMPLE" v57.0 (https://www.youtube.com/watch?v=eFdwyp0yfXw; no text, YouTube fetch blocked); BTD6 Fenix "No Abilities" (9.7k views, no text); Lazynomicro "Upper Deck" (Captain BEZ = Benjamin? UNVERIFIED); Hbomb Obyn + Druids + Permabrew; Zeroprince Jones + Primary Expertise + MOAB Maulers (Primary Expertise LOCKED). BTD6 Index heroless LTC: Final Harmonic + Pop and Awe 0-5-2 + Bloon Solver.
**Bot notes:** Strategy 1 is the best fit: no abilities, no deck placement, all within caps, current version. One aim is needed: the Spike Factory Set Target "near the bottom of the grate, between the two exit routes" (R20, one-time). If the bot cannot set a target point, use Smart (the guide says avoid Normal); the risk is UNVERIFIED. Do NOT place anything on the hatch if a water plan is wanted later. Carrier Flagship strategies don't need deck placement, but they need the hatch removed before placing on it.


## Expert maps

### Muddy Puddles (Expert)
**Map traits / what it requires:** 4 parallel vertical lanes (top entrance -> bottom exit, ~9.7-11 RBS each) that ALTERNATE by round, one lane per round (fandom formula since v9.0: lane 1 = r%6==1; lane 2 = r%6 in {2,0}; lane 3 = r%6 in {3,5}; lane 4 = r%6==4). Lanes 2+3 get 2/3 of all rounds; R40 MOAB lane 4, R60/R78/R80/R98 lane 2, R63/R95/R99 lane 3, R100 BAD lane 4. No line-of-sight blockers, no removables, water ponds between lanes (middle pond between lanes 2 and 3, right pond left of lane 4). Early game is the hard part (alternating far-apart lanes, precise placement). Effectively REQUIRED: towers that reach every lane - Advanced Intel subs (2-x-x) in a pond, snipers, Psi (global), Heli/Ace, Carrier Flagship. Local-range towers only work for lanes 2-3 (wiki: focus local setups there, mind R100 on lane 4). Wiki (v56.3) says the late game is no longer "True Expert"; Corvus, Rosalia, Comanche Commander, subs, Beast Handler recommended. Sources: https://www.bloonswiki.com/Muddy_Puddles , https://bloons.fandom.com/wiki/Muddy_Puddles/Strategies

**Strategy 1 - Boat/sniper start, Psi, Advanced-Intel sub army -> Sub Commander + Pre-Emptive Strike** (source: https://www.youtube.com/watch?v=gJLFvkHiOBk ; G-Horizon, "Easy Guide (1 Ability, No Micro)", uploaded 2026-02-28 (~v55); confidence: video-description, written steps)
- Hero: Psi (placed R27, set Strong at R40).
- Core towers: Buccaneer 5-0-2 (Carrier Flagship, middle pond), Sniper 1-0-1, Sub2 2-0-5 (Sub Commander), Sub3 2-0-4, Sub4 2-5-0 (Pre-Emptive Strike), Desperados x4 0-1-0, Alchemist 3-2-0, Village 2-0-2, Boomerang 0-0-0; optional Glue 0-2-4.
- Purchase order: R6 Boat on Strong in the middle pond (author pixel [624,674] @1080p); R7 Sniper; R8 Sniper Strong; R9 Sub1 (right pond, [1249,420]); R10 Boomerang on Last, bought MID-ROUND; R12 Desperado1 Strong ([623,507]), Boat to First; R14 Sub2 1-0-0; R16 Sub2 2-0-0; R18 Sub2 2-0-1 (mid-round); R22 2-0-2; R24 Desperado1 0-1-0; R27 Psi; R28 Sniper 1-0-1; R32 Sub2 2-0-3; R36 Sub2 2-0-4; R40 Sub3 2-0-2, Alch 3-0-0, Desperado2 0-1-0, Psi Strong; R42 Desperado3 0-1-0; R45 Village 2-0-2; R47 Sub4 2-3-0, Alch 3-2-0; R48 Sub3 2-0-3, Boat 0-0-2; R60 Sub2 2-0-5; R63 Sub3 2-0-4, Desperado4 0-1-0; R82 Sub4 2-5-0; then Boat 5-0-2 ASAP; (author note) Glue 0-2-4 above the sub for R98; R100 Pre-Emptive/First Strike ability once the BAD passes the middle of the track.
- Key placements: boat in the middle pond (covers lanes 2+3), subs in ponds with Advanced Intel for global reach, desperados between lanes; Psi anywhere (global).
- Abilities used: one (2-5-0 First Strike on R100 BAD).
- Account conflicts / substitutes: none (Psi owned, sub 2-5-0 / boat 5-0-2 unlocked). Author warns rounds < 15 can leak by RNG due to boomerang timing.

**Strategy 2 - Quincy dart/sub start, Advanced-Intel sub army, Sub Commander + Pre-Emptive Strike ("Full Auto Start")** (source: https://www.youtube.com/watch?v=oX9ceTu_E30 ; ApexZ, 2026-08-09; confidence: video-description, written steps, no placements given)
- Hero: Quincy (R6, Strong then First after yellows).
- Core towers: Dart x5, Sub2 2-0-5, Sub3 2-0-4, 3 more 2-0-4 subs, Sub4 2-5-0, Snipers x2 (1-0-0), Druid 1-3-0, Alch 4-2-0 x2, Village 2-0-2, Mortar 0-2-4 (R94).
- Purchase order: R6 Quincy; R7 Dart1; R9 Sub1; R10 Dart2 (Last), Sub1 Strong, Dart3; R11 Dart2/Sub1 to First; R12 Quincy L3 Rapid Shot; R13 Sniper1 Strong; R14 Sub2, Rapid Shot; R15 Sniper2; R16 Dart4; R17 Sub2 1-0-0; R18 Rapid Shot; R19 Sub2 2-0-0; R21 2-0-1; R22 Sniper1 1-0-0; R26 Sub2 2-0-2; R27 Druid 0-1-0; R31 Druid 0-3-0; R32 Druid 1-3-0, Dart4 0-0-2; R34 Sub2 2-0-3; R37 2-0-4; R38 Alch1 2-0-0; R40 Alch1 3-2-0; R41 Village 1-0-2; R45 Alch1 4-2-0; R46 Sub3 2-0-0; R47 Sub4 2-2-0; R50 Sub3 2-0-2; R59 Sub2 2-0-5; R61-62 Sub3 2-0-4, Dart5 0-0-2; R63 Sub4 2-3-0; R65 Village 2-0-2; R67 Alch2 4-2-0; R67-75 three more 2-0-4 subs; R82 Sub4 2-4-0; R89 Sub4 2-5-0; R93/R97/R100 First Strike; R94 Mortar 0-2-4 retargeted each round to the next spawn; R98 Quincy L10 Storm of Arrows.
- Abilities used: Quincy L3 (R12/14/18), L10 (R98), First Strike (R93/97/100).
- Account conflicts / substitutes: Mortar 0-2-4 needs MIDDLE+BOTTOM path - bottom-path mortar is LOCKED on this account (cap 5-5-0). Substitute: skip it (it is a late add-on) or use Glue 0-2-4 as G-Horizon suggests (inferred).

**Strategy 3 - 3 darts + 5 snipers, Psi, Dartling, Sub Commander + Pre-Emptive** (source: https://www.youtube.com/watch?v=ESzoqCI83nY ; unescaped, v39.2, 2023-11; confidence: video-description; old) - heavy micro (sniper targeting swapped 4-10 times per round R6-R10) and a MANUALLY AIMED Dartling R18-R27; NOT bot-suitable, listed only as evidence that Psi + Sub Commander + Pre-Emptive Strike is the standard late game.

Other evidence (video-only): sYnce v56.3 Dan D'Monke + Perma-brew + Elite Defender (https://www.youtube.com/watch?v=EOOJOk2lYX8); Doreo v49.2 "All 3 Tier 5s" (https://www.youtube.com/watch?v=sm6Loacb1Tc); BTD6 Index "Easy R19 Airburst (ft. Skywardens)" start (https://www.youtube.com/watch?v=t6Hk0nI6SBs).

**Bot notes:** Strategy 1 is best for the bot: no micro, one ability, no aiming, all unlocks owned. Risks: R6 boat and R12 desperado need near-exact spots (author gives 1080p pixels - convert to screen fractions); R10 boomerang is bought mid-round (bot must buy during R10 or accept RNG); R18 sub upgrade mid-round. The single ability (2-5-0 on R100) should fire when the BAD is mid-lane on lane 4 - a blind press at round start may waste it; delay ~8-10 s after the BAD spawns (inferred). Strategy 2 relies on many timed Quincy abilities and a re-aimed mortar each round (impossible for the bot, and the mortar path is locked). Lane-aware placement matters: anything with local range should sit between lanes 2 and 3.


### #Ouch (Expert)
**Map traits / what it requires:** 4 very short lanes (2 vertical ~8.0 RBS, 2 horizontal ~10.2 RBS) ALL active every round, crossing around a central square pond (the only water; holds ~9 boats / 13 subs). Pond can be drained for $1,000 only while no water tower is on it (turns the centre into land reaching all 4 lanes). No LOS blockers. Wiki (v57.4): True Expert; water strategies (Destroyer + Permanent Brew), Grandmaster Ninja + 20 Shinobi after draining, Lord of the Abyss, Symphonic Resonance (covers all 4 lanes from the pond), Admiral Brickell recommended. Effectively REQUIRED: a centre setup that reaches all 4 lanes - either water towers in the pond (Advanced Intel subs, boats/Pirate Lord/Destroyers, Mermonkey Symphonic Resonance) or drain + Grandmaster Ninja/Shinobi; sniper (global) for R28/R30 leads and R40 (fandom: 3-0-2 sniper + low-tier glue/ice beats R40). Steam/reddit snippets: Perma-Spike is weak here (4 exits). Sources: https://www.bloonswiki.com/Ouch (fetched via API), https://bloons.fandom.com/wiki/Ouch/Strategies

**Strategy 1 - Brickell water comp: Advanced-Intel subs, Aircraft Carrier/Flagship + Pirate Lord, Glue Storm, First Strike** (source: https://www.youtube.com/watch?v=ZAEURMORvUc ; OneEyedDeacon "How to SPEEDRUN #Ouch Chimps", v51.2, 2025-11; confidence: verified-written-steps)
- Hero: Admiral Brickell (R14, in the middle/pond).
- Core towers: Dart 0-0-2, Sub1 4-0-2 (Reactor), Sub2 2-0-2 -> 0-4-0 First Strike (note: guide writes "030 sub2"/"040 sub2" late on a 2-0-2 sub; as written), Sniper 1-1-0, Boat1 5-2-0 (Carrier Flagship), Boat2 2-5-0 (Pirate Lord), Boat3 4-2-0, Village 4-2-0, Alch 4-2-0, Mermonkey 4-0-1, Glue 0-5-2 (Glue Storm), Ninja 0-4-0 (Sabotage).
- Purchase order (exact): R6 dart1 + sub1; R8 sub2 left; R9 sub2 Strong; R10 sniper1 top right Strong, sub2 First; R14 Brickell middle; R15 sub2 0-0-1 mid-round; R18 Naval Tactics; R20 sub2 0-0-2; R21 1-0-2; R22 2-0-2 (mid-round); R24 sniper1 0-1-0; R25 boat1 above Brickell; R27 boat1 0-1-0; R28 sniper1 1-1-0; R29 dart1 0-0-2; R31 boat1 2-1-0; R35 boat1 3-1-0; R37 boat1 3-2-0; R38 boat2 0-2-0; R39 boat2 2-3-0; R41-42 village1 0-2-0; R48 boat1 4-2-0; R50 boat2 2-4-0, village1 2-2-0; R53 alch1 4-2-0; R54-57 mermonkey1 2-0-1 -> 3-0-1 -> 4-0-1; R73 boat1 5-2-0; R82 boat2 2-5-0; R83 village1 4-2-0; R84-91 glue1 0-3-2 -> 0-4-2 -> 0-5-2; R93 boat3 3-1-0 next to boat1; R95 boat3 4-2-0; R96 ninja1 0-4-0; R97 sub1 4-0-2; R98 sub2 0-3-0; R99 sub2 0-4-0; R100 Naval Tactics + First Strike.
- Abilities used: MANY - Brickell Naval Tactics (~20 rounds), Mega Mine (R64-R99), Monkey Pirates/Pirate Lord hook on specific MOABs (R50-R98), Glue Storm R91-R99, Sabotage R99, First Strike R100.
- Account conflicts / substitutes: Mermonkey 4-0-1 OK (cap 4-4-4). Glue 0-5-2 OK. None locked.

**Strategy 2 - Drain the pond: Geraldo + Grandmaster Ninja with 20 Shinobi** (sources: https://www.youtube.com/watch?v=_0ON6rQ7Fd0 (OneEyedDeacon, Desperado start, v50.0, 2025-09) and https://www.youtube.com/watch?v=UvU1PYOKxg4 (dart start, v49.2); wiki + fandom name this the classic black-border strategy; confidence: verified-written-steps)
- Hero: Geraldo (R13).
- Core towers: Desperados 0-0-0 x2 (or 5 darts), Engineer 0-0-0, Sniper 1-0-1, Ninja1 5-0-2 (Grandmaster), 20 x Ninja 0-3-0/0-3-1 (Shinobi), Alch 3-2-0, Villages 3-0-2 + 0-3-2, Glue 0-1-4, Ice 5-2-0.
- Purchase order (v50.0): R6 Desperado1 bottom of middle platform + Desperado2 right platform; R8 Desperado2 Strong; R10 engineer1; R13 Geraldo; R14-21 Geraldo spikes/turrets on exits; R19-20 sniper1 1-0-0 Strong; R26 REMOVE WATER ($1,000) + Gerry glue; R27-33 ninja1 in the middle 0-0-1 -> 3-0-2; R34 sniper1 1-0-1; R37 ninja1 4-0-2 (mid-round); R39-41 village1 0-0-2; R40 Gerry's Fire + Maelstrom item; R42/44 alch1 3-0-0 -> 3-2-0; R45 village2 0-0-2; R46 village1 2-0-2; R48-R70 Shinobi ninjas (0-3-0/0-3-1) one or two per round to 20; R84 ninja1 5-0-2; R85 village2 0-3-2; R86-92 glue1 0-1-3 -> 0-1-4 on Strong; R93 ice1 4-1-0; R94 village1 3-0-2; R99 ice1 5-2-0; R100 Maelstrom items + spikes on exits.
- Abilities used: no tower abilities, but Geraldo SHOP ITEMS every few rounds (spikes/turrets/glue/blade trap/maelstrom placed on the track, Pickles, Gerry's Fire on a tower, camo potions, genies, idols).
- Account conflicts / substitutes: none. Bot limit: needs Geraldo item purchase AND on-track placement - currently unsupported (inferred).

**Strategy 3 - Etienne, ninjas/sniper, Aircraft Carrier... (unescaped "Amphibious Ice", v49.3)** (source: https://www.youtube.com/watch?v=esGFeab-kzI pinned comment; confidence: written steps in pinned comment) - Etienne, 2x Ninja 3-0-2, Sniper 4-0-2/3-0-2, Wizard 5-0-2, Boomerang 5-0-2, Ice 2-4-0, Glue 0-2-4, Subs 2-3-0/2-4-0, Ninjas 0-4-0 x2; uses Drones/UCAV, Ice freeze, Sabotage and First Strike ~40 times with precise timing. Not bot-suitable as written.

Video-only no-ability options worth transcribing: Doreo "NEW Easiest #OUCH ... (No Abilities/Micro/Geraldo)" v49.2 (https://www.youtube.com/watch?v=SveJAh69Ttc ; author note mentions "moar spam" - UNVERIFIED which tower, likely MOAR Glaives boomerangs); Sleeping Axolotl "No Micro, No abilities" v44 (https://www.youtube.com/watch?v=6c2MOyykPFM) is Geraldo-item based; sYnce v56.3 Brickell + Perma-brew + Destroyer spam (https://www.youtube.com/watch?v=5W5D4Hm458I); BTD Flagship v53.2 "No Abilities/No Micro" (https://www.youtube.com/watch?v=UuH9mz4MJpU ; a commenter's notes: Churchill + ~10 Mermonkeys 0-3-2/3-0-1 Abyssal Warrior + Lord of the Abyss + Carpet of Spikes 2-5-0, Glue 2-3-0/Relentless, Ice Embrittlement) - Lord of the Abyss (Mermonkey 5-x-x) is LOCKED on this account.

**Bot notes:** No written strategy is fully bot-friendly. Strategy 1 needs ~60 timed ability presses (Naval Tactics, Mega Mine - possibly needs a target spot, UNVERIFIED - and hooks on specific blimps); blind per-round presses would be weaker but most of these abilities auto-target (hook = strongest blimp in range; Naval Tactics/Glue Storm/Sabotage are global/no aim). Strategy 2 needs the pond drained ($1,000 removable at R26 - bot can do) but depends on Geraldo items placed on the track (bot can't). Recommended path: transcribe the Doreo v49.2 no-ability/no-Geraldo video (or the sYnce Brickell Destroyer + Perma-brew video) into steps; meanwhile Strategy 1 is the best available written, all-unlocked, aim-free comp. Do NOT drain the pond in any water strategy. Mermonkey tier 5 (Lord of the Abyss) is locked - avoid guides that need it.


### Dark Castle (Expert)
**Map traits / what it requires:** 4 entrances on the left (each under a removable tree pack, $1,000 each; bloons are IMMUNE under trees) merging into ONE short exit through the castle door; top lane is always first each round (fandom: remove top trees first). River with water spots next to the merged track. Short (9-10 RBS without trees). Wiki: second-easiest Expert map; convergent exit makes Perma-Spike, Avatar of Wrath/Poplust druids, villages, bomb/cluster splash very strong. Snipers' sight is partly blocked by castle walls/trees. Pre-Emptive Strike passive needs the trees removed. Required map-wide tower: none - most comps work; a spike factory/druid at the exit is the standard safety. Sources: https://www.bloonswiki.com/Dark_Castle , https://bloons.fandom.com/wiki/Dark_Castle

**Strategy 1 - Obyn + 7 druids (Poplust x6 -> Avatar of Wrath) + Permanent Brew, no abilities** (source: https://www.youtube.com/watch?v=YUR_SIL0trE ; Yoboi3li, "Safe Black Border Guide (No Abilities, No Micro)", 2026-08-22 (~v57); confidence: video-description, written steps; placements only on video)
- Hero: Obyn (R10, "pretty far left").
- Core towers: Sub 0-0-0, Skywarden 0-0-0, Boomerang 0-0-0, Sniper 0-2-1, 6 druids 0-1-4 (Poplust) -> one 0-1-5 (Avatar of Wrath), Druid 4-0-2, Alch 5-0-1 (Permanent Brew), Village 2-0-2.
- Purchase order (all AFTER the round; autostart off): R6 Sub + Skywarden; R7 Boomerang; R10 Obyn; R13 Sniper Strong; R15 2 druids; R20 Sniper 0-2-1 (author: 1-2-0 may be better) on First; R27 Village 0-0-2; R30 druids 0-1-1; R31 druid 1-0-1; R33 2-0-1; R35 3-0-1; R37 more 0-1-1 druids to 7 total + Alch 0-0-0; R39 Alch 3-0-1; R44 3-0-1 druid -> 4-0-2; R48 two Poplusts 0-1-4; R49 third Poplust; R50 Village 2-0-2, Alch 4-0-1; R51-78 nothing; after R78 Alch 5-0-1 (Perma Brew); R81 remaining 3 druids -> Poplust; R94 centre Poplust -> Avatar of Wrath (0-1-5).
- Key placements: druid cluster inside Obyn's range near the merge/exit, alch + village touching the druids.
- Abilities used: none. Removables: none bought.
- Account conflicts / substitutes: Skywarden 0-0-0 fine (cap 4-3-3). Alch 5-0-1 fine. None.

**Strategy 2 - Obyn, 3 subs + Perma-Spike + Poplust druids ("Full Auto Start")** (source: https://www.youtube.com/watch?v=3UlaQFG9c-c ; ApexZ, 2026-07-01; confidence: video-description)
- Hero: Obyn (R13).
- Purchase order: R6 Dart + Sub1; R8 Sub2; R10 Sub3; R13 Obyn; R17 Spike Factory; R19 Spike 0-0-2 on Close; R24 0-0-3; R27 1-0-3; R28 2-0-3; R36 2-0-4; R38-55 6x Druid 0-1-4 + 1x Druid 4-0-2 in Obyn's range; R57 Alch 4-0-1; R61 Village 2-0-0; R79 Spike 2-0-5 (Perma-Spike); R80 Ice 0-2-4; R85 Village 2-3-0; R92 Ice 0-2-5 (Super Brittle); R96 Sub1 2-4-0; R99 Sub3 2-4-0; R100 sub (First Strike) abilities on the BAD.
- Abilities used: Obyn L10 "from level 10 onward" (optional), First Strike R100.
- Account conflicts: none.

**Strategy 3 - Quincy, Sub 2-0-4 + Alch, Sun Avatar 3-0-2, Perma-Spike 0-2-5, MOAB Press boomerangs** (source: https://www.youtube.com/watch?v=oePssmHJDTc ; BlueCliff, 2023-04-30 (~v36); confidence: verified-written-steps, older) - R6 Dart (bottom mid) + Sub, Dart (top mid) both Strong; R9-R23 Sub 0-0-1 -> 2-0-3; R11 Quincy; R27 Alch (mid) 2-0-0 Strong; R32 3-0-1; R35 Spactory 0-0-2 Smart; R37 Alch 4-0-1; R39 remove TOP trees, Dart (top left) 0-0-2; R42 Sub 2-0-4; R45 Village 2-0-0; R48-62 Super 0-0-2 -> 2-0-2 -> 3-0-2; R65 Spactory 0-2-4; R79 0-2-5; R82 Alch (right) 4-0-1; R84 Sniper 4-2-0 Strong; R85 remove all trees; R86 Village 4-0-0; R88-96 five Boomerangs 2-0-4 Strong; R92 Glue 0-2-4 Strong. Uses Quincy L3/L10 on R40, R60, R76, R78, R80, R98, R100.

Other: BeatbloonsBob (https://www.youtube.com/watch?v=W0naQh_vc7E , 2026-02, order only, no rounds): 2 Desperados, Dart 0-3-1/0-3-2, Mermonkey 4-2-0, Silas, Spike 2-0-2 Smart -> 3-0-2 -> 4-0-2 -> second Spike 2-5-0, Village 4-2-0, Ice 2-0-5 + Ice 5-2-0 - no abilities except optional R22. sYnce v57.4 Silas + Super Brittle + Perma-spike (video-only, https://www.youtube.com/watch?v=-Otux9Y5_k8).

**Bot notes:** Strategy 1 is ideal: zero abilities, zero micro, all purchases between rounds, druids are local towers near the merge (no aiming), all unlocks owned. Druid Poplust stack must be placed tightly together (Poplust buffs nearby Poplusts) inside Obyn's range; get placement spots from the video. Strategy 2 adds Perma-Spike insurance and only needs one end-game First Strike press (blind press on R100 is acceptable after the BAD enters). Tree removal is optional (BlueCliff R39/R85), not needed for Strategy 1.


### Quad (Expert)
**Map traits / what it requires:** 4 entrances/exits, ALL active every round, each path crossing the diamond-shaped garden around a central pond (paths 11.3-12.3 RBS; exits sit at the same truss as another entrance, so tracks overlap and leaks are hard to see). 4 removable trusses ($1,500 each) block LOS and make bloons IMMUNE underneath (Pre-Emptive passive, Pre-Game Prep, Spirit of the Forest do nothing there); fandom: remove left+right trusses for a First Strike + Reactor double-shot on R100. Two killzones: bottom-left edge (bottom+right entrances) and top-right edge (top+left entrances). Wiki: True Expert, third hardest map; separate defences for top and bottom halves. Effectively REQUIRED: global/very-long-range damage (snipers: Elite Defender/Elite Sniper/Maim, Prince of Darkness, Advanced-Intel subs early) and/or two killzone clusters with Spiked Balls/Mines (wiki: turns Quad into a two-lane map). Giant Condor, Glaive Lord, Sauda also recommended. Sources: https://www.bloonswiki.com/Quad , https://bloons.fandom.com/wiki/Quad/Strategies

**Strategy 1 - Psi + sniper army (Elite Defender 2-0-5, Elite Sniper 0-5-2, Maim/Cripple 5-2-0) + Prince of Darkness** (source: https://www.youtube.com/watch?v=Q2IEAOx5pVo ; OneEyedDeacon "Quad Chimps ft. Axis of Havoc", v54.2, 2026-04; confidence: verified-written-steps)
- Hero: Psi (R14, Strong, bottom-left of desperado1).
- Core towers: Desperado x2 0-0-0, Dart x2, Sub1 2-0-2, Sniper1 2-0-5 (Elite Defender), Sniper2 0-5-2 (Elite Sniper), Sniper3 5-2-0 (Cripple MOAB), Druid 2-3-0, Villages 0-2-2 + 2-0-2, Alch 4-0-0 + Alch 3-2-0, Wizard 1-0-5 (Prince of Darkness), Glue 0-2-4, Ice 2-4-0, Tack 1-0-4.
- Purchase order (exact): R6 desperado1 left + desperado2 right (middle, range border touching the barrier); R9 sniper1 Strong right of bottom bush; R10 dart1 top; R15 dart2; R16 sub1 top of pond, Strong; R17 1-0-0; R19 2-0-0 First; R21 2-0-1; R22 sniper1 1-0-0; R24 sniper2 First; R27 sub1 2-0-2 (mid-round); R28-30 sniper2 0-0-1 -> 0-1-1 -> 0-2-1; R32 druid1 bottom next to sniper1 0-1-0; R33 1-2-0; R35 1-3-0; R36 2-3-0 (Strong; R37 First); R37-40 sniper1 1-0-2 -> 2-0-2 -> 2-0-3; R42 village1 0-0-2; R44 village2 0-0-2; R45 village1 0-2-2; R46 sniper2 0-3-2; R47 village2 2-0-2; R49 alch1 3-0-0 (sniper2); R50 sniper1 2-0-4 First; R54 sniper2 0-4-2; R61 0-5-2 First; R71 sniper1 2-0-5; R73 alch1 4-0-0; R75 sniper3 3-2-0 Strong; R78 4-2-0; R79 wizard1 0-0-4 bottom-left of pond; R80 1-0-4 + alch2 3-2-0; R86 wizard1 1-0-5; R88-90 glue1 0-1-3 -> 0-2-3 -> 0-2-4 Strong; R97 sniper3 First; R98 sniper3 5-2-0, wizard Strong, sniper1+3 on Elite; R99 ice1 2-4-0; R100 tack1 1-0-4 top.
- Abilities used: Psi stun/scream ~20 times (R21-R100, timed on specific blimps), Ice (Snowstorm) R99/R100.
- Account conflicts / substitutes: none (Psi owned, sniper/wizard tier 5 unlocked).

**Strategy 2 - Sauda + Spiked Balls killzones, Overdrive + Tack Zone** (source: https://www.youtube.com/watch?v=OHXfTttu-IU ; sYnce, v37.3, 2023-06; confidence: verified-written-steps, OLD - Overdrive/Tack Zone/Spiked Balls nerfed since; wiki still recommends Sauda + Spiked Balls/Mines) - R6 3 darts; R8 sub Strong; R9-27 sub 1-0-0 -> 2-0-2; R12 Sauda on Close; R13/R17 snipers; R22-41 wizard 0-1-0 -> 0-3-2; R29/R32 spike factories bottom-left and top-right -> 3-2-0; per side: Village 2-0-2 -> 4-0-2, 4 alch buffs on the Spiked Balls, Ice 4-1-0, 2x Ice 0-2-3 (R75), 2x Tack 2-0-4; R83 Tack Zone; R84/R87 Alch 3-2-0 for two Overdrives; 2x Glue 0-1-3 per side; R94-96 Boomerangs 0-2-4/2-0-4; R95 Ninja 0-4-0; R100 Sub 0-4-0. Many Sauda Leaping Sword / Sword Charge and Sabotage timings.

**Strategy 3 - Churchill + desperado/dart start, 10 Mermonkeys, Carpet of Spikes ("Full Auto Start")** (source: https://www.youtube.com/watch?v=6R0hyblW2_A ; ApexZ, 2026-05-26; confidence: video-description) - R6 2 Desperados; R8 2 Darts; R10 Sniper Strong; R11-16 darts 0-3-0; R19 2 more darts; R27 Churchill, Sniper 1-0-0; R30 darts 0-3-2; R31-34 Druid 0-3-0; R36-41 two Villages 1-0-2; R40 Alch 3-0-0; R41-47 10 Mermonkeys 0-0-2 in the pond; R49 centre Mermonkey 3-0-2 -> 4-0-2; R52 3 Mermonkeys 0-3-2; R53-60 Spike 0-4-0; R78-81 Spike 2-5-0; "until R89" Mermonkey 4-0-2 -> **5-0-2 (Lord of the Abyss)**; R90-96 Village 4-0-2, Glues 0-2-3/0-2-4, Bomb 0-4-2, Druid 3-0-2, Glue 2-3-0; R99 Village 0-3-0. CONFLICT: Mermonkey tier 5 is LOCKED (cap 4-4-4) - substitute: keep 4-0-2 Abyssal Warrior + extra 0-3-2 mermonkeys (UNVERIFIED that it holds R95-R100).

Video-only no-ability options: Doreo "No Abilities/Micro/Geraldo" v51.2 (https://www.youtube.com/watch?v=w8_WEpX7sJg) and v46.3 (https://www.youtube.com/watch?v=OAAyTLp7VF4 , "crack zone"); BTD Flagship v53.2 "No Abilities / No Micro" (https://www.youtube.com/watch?v=fim4ZOG1ghc ; commenter: do NOT use an ability on R40; another got Josh's Constant with it); sYnce v55.1 Etienne + Perma-brew + Elite Defender (https://www.youtube.com/watch?v=LaUcinhdHRY), v57.2 Sauda + Perma-spike (https://www.youtube.com/watch?v=FDJ8bFirLKc).

**Bot notes:** Strategy 1 is the best fit: snipers are global (no LOS issue except trusses) and need only targeting changes (Strong/First/Elite), all unlocks owned. Its risk is the Psi ability timing - blind presses each round are weaker; consider leaving Psi's abilities on "press when blimps present" (inferred). Desperado R6 placement is precise ("range border touching the barrier"). Truss removal ($1,500 x4) is optional in Strategy 1 (not used). Strategy 2 is ability-heavy and outdated; Strategy 3 needs locked Lord of the Abyss. Best long-term: transcribe the Doreo/BTD Flagship no-ability videos.


### Workshop (Expert)
**Map traits / what it requires:** Single exit; bloons ride a conveyor at +50% speed; from R40 MOAB-class drop down a chute onto a short separate blimp path (MOAB path ~6.7 RBS, 3rd shortest blimp track in the game). Sight blockers (tables/machines). Paid gizmos: Reverse Motor (cancels conveyor speed 30 s) and Track Extensions (4 loops for 20 s); first use of each is FREE, then 50*((r-1)//10+1)+50*uses / 100*((r-1)//15+1)+150*uses. Early CHIMPS needs 3-4 precisely placed darts. Effectively REQUIRED: Spike Factory at the exit (Spiked Balls/Mines mid, Perma-Spike late) - wiki and every guide; Sauda + Super Glue/stun recommended. Sources: https://www.bloonswiki.com/Workshop_(BTD6) , https://bloons.fandom.com/wiki/Workshop_(BTD6)/Strategies

**Strategy 1 - Sauda, Druid of the Jungle, Perma-Spike 2-0-5 + Spiked Mines 4-2-0, Super Maelstrom tack, no abilities** (source: https://www.youtube.com/watch?v=e2jZofvcaNQ ; OneEyedDeacon "Easiest Workshop Chimps w/ NO ABILITIES", v53.2, 2026-02; confidence: verified-written-steps)
- Hero: Sauda (R17).
- Core towers: Darts x4 0-0-0, Druid 1-3-0, Spike1 2-0-5, Spike2 4-2-0, Village1 2-0-2, Village2 4-0-2 (Primary Mentoring), Alch1 4-2-0, Alch2 4-2-0, Tack 2-0-5 (Super Maelstrom), Glue 0-2-4, Ice 5-2-0 (Super Brittle).
- Purchase order (exact): R6 dart1 on Last (left, next to the desk) + dart2 Strong ("hair aligned with line") + dart3 next to dart2; R8 dart4 Strong next to dart1; R10 druid1 under the track next to the hammer by the bottom machine; R14 spike1 bottom-right (exit); R17 Sauda; R18 spike1 0-0-1; R19 0-0-2 (author: manual targeting); R22 1-0-2; R23-29 druid1 0-1-0 -> 1-1-0 -> 1-2-0 -> 1-3-0; R32 village1 for spike1; R35 village1 0-0-2; R36 spike1 1-0-3; R37-38 alch1 2-0-0 -> 3-0-0; R41 spike1 1-0-4; R43-44 alch1 4-0-0 -> 4-2-0; R46 village1 2-0-2; R48-49 spike2 3-0-0 -> 3-2-0; R50-51 village2 3-0-2 -> 4-0-2; R52-54 tack1 2-0-3 -> 2-0-4; R59 spike2 4-2-0; R62 glue1 0-0-3 Strong; R79 spike1 2-0-5; R80 ice1 4-1-0; R81 alch2 4-0-0 for tack1; R85 tack1 2-0-5; R86 alch2 4-2-0; R88 glue1 0-2-4; R97 ice1 5-2-0.
- Abilities used: none; no gizmos.
- Account conflicts / substitutes: Village 4-0-2 is Primary Mentoring (allowed, cap 4 top). None.

**Strategy 2 - same comp, "Full Auto Start"** (source: https://www.youtube.com/watch?v=J5pN-jskVLo ; ApexZ, ~2026-08; confidence: video-description) - R6 Dart1 Last, Dart2 Strong, Dart3 First; R7 Dart4 Strong; R10 Druid + Track Extension when the last blue wave enters; R14 Spike1; R16 Sauda; R17-18 Spike1 0-0-2 targeting "end of the track"; R22 1-0-2; R24-29 Druid 1-3-0; R32-33 Village1 0-0-2; R35 Spike1 1-0-3; R37 Alch1 3-0-0; R42 4-2-0; R44 Village1 2-0-2; R45-58 Spike2 1-0-0 -> 3-1-0 -> 3-2-0 -> 4-2-0; R49-50 Village2 3-0-2 -> 4-0-2; R51-53 Tack 2-0-3 -> 2-0-4; R61 Glue 0-1-3; R62 Spike1 2-0-4; R78 2-0-5; R80 Ice 4-2-0 + Alch2 4-2-0; R86 Tack 2-0-5, Glue 0-2-3; R88 Glue 0-2-4; R96 Ice 5-2-0; R100 Track Extension + Reverse Motor gizmos.

**Strategy 3 - Striker Jones, Spike 4-0-2, MOAB Eliminator/Assassin bombs** (source: https://www.youtube.com/watch?v=99F5bY86yLU ; OneEyedDeacon v48.2, 2025-06; confidence: verified-written-steps) - same 4-dart + druid start, Striker R17, Spike1 0-0-2 Close -> 1-0-2 -> 3-0-2 -> 4-0-2, Bomb1 0-2-4 -> 0-2-5 -> 1-5-0 (MOAB Eliminator), Bombs 1-3-0/1-4-0, Alch 3-0-1 x2, Villages 2-0-2 + 4-2-0 -> 5-2-0 (R99 "520 village1" = PRIMARY EXPERTISE - LOCKED on this account), Glue 0-2-5; uses Concussive Shell, Eliminator and Artillery Command abilities R40/R98/R100.

Others (video-only): Doreo "No Abilities/Micro/Machines" v46.3 (https://www.youtube.com/watch?v=_sKXWHuxy1w ; commenter on v51.0: fails R9-10 unless an extra Druid is added); sYnce v57.4 Silas + Super Brittle + Perma-spike, "no micro, no ability, no gizmos" (https://www.youtube.com/watch?v=yTBomDfRmiM); FroStee Mate v49.3 no micro/no abilities (https://www.youtube.com/watch?v=FFaoQC-tsFA).

**Bot notes:** Strategy 1 fits the bot almost perfectly (no abilities, no gizmos). Hard parts: R6-R8 dart placements are pixel-precise (get spots from the video or the fandom/unescaped 1080p pixels); R19 spike "manual targeting" - use Close/Smart instead (bot can't aim; inferred safe because the factory sits at the exit). Avoid Strategy 3 (Primary Expertise locked, ability-heavy). Gizmos (free first use) could be added on R40 as insurance if the bot can click them - optional.


### Bloody Puddles (Expert)
**Map traits / what it requires:** 5 short vertical lanes (~9.1-10.2 RBS); every round spawns from TWO far-apart entrances whose pair rotates (fandom: R1+4k lane1 top + lane5 bottom; R2+4k lane2 top + lane4 bottom; R3+4k lane3 top+bottom; R4+4k lane2 top + lane4 bottom); MOAB-class on R40/60/80/100 from the bottom of path 2; bosses top of middle path. Intrusive LOS blockers; removable jeep: $1,000 (a Chinook crashes onto it = MORE blocking) then $500 to clear jeep+chinook+rocks. Several ponds. Wiki: hardest map in the game; early game needs precise placement + luck. Effectively REQUIRED: global/long-range towers - Advanced-Intel/Airburst subs ("basically essential" early), snipers (Elite Sniper/Elite Defender/Maim), Psi; Giant Condor helps. CHIMPS start: 2 Desperados (wiki: much less precise than the pixel-perfect dart+sub start). Sources: https://www.bloonswiki.com/Bloody_Puddles , https://bloons.fandom.com/wiki/Bloody_Puddles/Strategies

**Strategy 1 - Striker Jones, desperados + 4 snipers + Airburst sub, MOAB Assassin bomb spam** (sources: https://www.youtube.com/watch?v=kRpOZgXz1Eo (OneEyedDeacon v53.2, 2026-03) and identical https://www.youtube.com/watch?v=PoilgyLevgQ (ApexZ "Full Auto Start", 2026-07); confidence: verified-written-steps)
- Hero: Striker Jones (R29, right of the rocks).
- Core towers: Desperados x2 0-0-0, Darts x2, Snipers x4 (1-0-0/1-1-0), Sub1 2-0-3, Ninja 0-0-0, Bombs 0-2-4 x2, ~15 Bombs 2-4-0 (MOAB Assassin), Bomb 4-2-0 x2, Alch 3-0-1 + 3-2-0 x2, Village 5-2-0 (R79), Glue 0-2-4 x2.
- Purchase order: R6 desperado1 under 2nd puddle top-left + desperado2 right of 4th lane; R7-11 desperado2 Strong/First swaps; R8 dart1; R9 dart2; R10 sniper1 Strong (mid-round); R13-15 snipers 2-4 Strong; R17 sub1 1-0-0; R19 2-0-0; R21 2-0-1 (+ sniper2 Close->First micro); R22 sniper1 1-0-0 mid-round; R23 sniper4 0-1-0; R27 sub1 2-0-2; R29 Striker; R32 sub1 2-0-3; R33 ninja1; R34-36 bomb1 0-0-1 -> 0-2-3; R36 sniper4 1-1-0; R37 sniper2 1-0-0; R40 alch1 3-0-1; R42-48 village1 0-2-0 -> 4-2-0; R46 bomb1 0-2-4; R49-50 bomb2 0-2-4; R51-52 alch2/3 3-2-0; R54-62 bombs 3-5 1-3-0 -> 1-4-0; R64-66 bomb6 3-2-0 -> 4-2-0; R79 village1 5-2-0 + all bombs to 2-4-0; R80 bomb7 4-2-0; R81-85 glues 0-2-3 -> 0-2-4 Strong; R83-R99 bombs 8-19 2-4-0; R93 remove barriers (jeep).
- Abilities used: MANY - Concussive Shell and MOAB Assassin abilities (2x-12x) on specific blimps R31-R100, Striker L10/L20.
- Account conflicts / substitutes: R79 Village 5-2-0 = PRIMARY EXPERTISE - LOCKED (cap 4-5-5). Substitute: stay at 4-2-0 (inferred; loses the R79+ discount/ballista).

**Strategy 2 - Quincy, Airburst subs, Elite Sniper + Elite Defender + Maim sniper army** (source: https://www.youtube.com/watch?v=oCsimreEU1k ; Spiffy BTD, v30.1, 2022-03; confidence: verified-written-steps, OLD)
- Hero: Quincy (R14).
- Purchase order: R6 dart (Last) + sub; R7 dart Strong; R9 sub; R10 sniper Strong mid-round; R11 dart; R15 sniper; R17 top-left sub 1-0-0, dart bottom right; R19 2-0-0; R21 2-0-1; R22 dart; R23/R25 snipers 1-0-0; R27 sub 2-0-2; R31 2-0-3; R33 dart 0-0-2; R35 druid 0-3-0; R39 village 0-0-2 + alch 3-0-0 (only the 2-0-3 sub in range); R40 2x glue 1-1-0; R42 2nd village 0-0-2, first 2-0-2; then in order: sniper 0-3-2, alch 3-0-1, top-middle sniper 4-0-0, sniper 0-4-2; R63 0-5-2 First; then sniper 4-2-0, alch 4-0-1, sniper 2-0-5 First, alch 4-2-0, 2x 0-3-2 snipers, another alch 4-2-0, 2x 0-3-2 snipers, village 0-3-2, 2x glue 0-1-3 Strong, 3x boomerang 2-0-4 Strong, ice 4-1-0, village 3-0-2, ninja 0-4-0, sub 0-4-0, tack 2-0-3; R96 Maim on First; R99 Sabotage; R100 Quincy abilities + First Strike.
- Abilities used: Quincy Rapid Shot ~6x early, Storm of Arrows R63/R100, Sabotage R99, First Strike R100.
- Account conflicts: none. CAUTION (YouTube comment on Doreo's guide, UNVERIFIED): "as of update 57.1, middle path sniper lost its lead popping" - the many 0-3-2 snipers may now need lead help (Alch acid / Supply Drop shrapnel).

**Strategy 3 - unescaped desperado start + Ezili, snipers, Super Monkeys 0-3-2, Crossbow Master** (source: https://www.youtube.com/watch?v=JHRqzDkIRsQ pinned comment; v49.1, 2025-06; confidence: written steps in pinned comment) - "no micro, no perfect placements" start: R6 2 desperados; R7 desperado R Strong; R8 dart L; R9 dart R Strong; R10 sniper mid-round; R12-15 snipers 2-4 Strong; R17-27 sub 1-0-0 -> 2-0-2; R28 Ezili Strong + 3 snipers First; R35 sniper 0-3-2; R36-38 Alch 3-0-0; R37-42 Glues 1-1-0; R42-65 Villages 2-0-2/3-0-2, Super Monkeys 0-3-2 x2; R59-63 Ice 3-1-0; R71 Ninja 0-4-0; R81 Dart 0-2-5 Crossbow Master; R84-98 Boomerangs 0-2-4 x4; R89-96 Bombs 4-1-0; R90/93 Engineers 0-3-0 (foam, "retarget both foams" = aiming). Uses ~25 Hex/Sabotage presses.

Video-only no-ability option: Doreo "NEW EASIEST ... (No Abilities/Micro)" v49.0 (https://www.youtube.com/watch?v=rvkuXLSqdPs ; desperado start, apparently Gwendolin since a commenter mentions Firestorm; 57.1 fix per commenter: set Supply Drop airdrop to shrapnel at R52, collect it on R59, Firestorm on R93). sYnce v56.3 Psi + Elite Defender + Perma-brew "New EASIEST" (https://www.youtube.com/watch?v=35WVq5CzBKI).

**Bot notes:** Hardest map for the bot. Every written guide uses many timed abilities and mid-round targeting micro on R7-R26 (desperado/sniper Strong<->First swaps). Strategy 1 abilities (MOAB Assassin missile, Concussive Shell) auto-target, so blind presses on blimp rounds are partially OK, but its R79 Primary Expertise is locked. Strategy 2 (snipers + Advanced-Intel subs) is the most bot-like comp (global towers, targeting only) but is old (v30) - verify vs 57.1 sniper changes. Best plan: transcribe Doreo v49.0 or sYnce v56.3 (Psi/Elite Defender/Perma-brew) videos; use the wiki 2-desperado start. Jeep removal: buy both steps together ($1,000 + $500) or not at all (step 1 alone adds a crashed Chinook that blocks more sight).


### Infernal (Expert)
**Map traits / what it requires:** 2 long lanes (~19.3-19.5 RBS, ~22 RBS per fandom) ALTERNATING by round (odd = top lane, even = bottom). Very scarce land: small islands/pillars (top-left island, two middle pillars inside the waves that reach both lanes, bottom-right island, left/right edge half-islands) and two small ponds (top-right, bottom-left; ~3 water towers each). No LOS blockers, no removables. Wiki: generally the easiest Expert map on CHIMPS; Heli Pilots (Apache Prime / Comanche Commander), Sniper armies with Permanent Brew, BEZ dartling recommended. Fandom: Quincy start on the bottom-middle pillar is the standard (R7 is near-impossible without him; alternatives: dart + sniper, or a 0-1-1 -> 0-2-2 boomerang at the top of the bottom platform). Effectively REQUIRED: towers that reach both lanes from the few placements - heli/ace/snipers/subs with Advanced Intel; careful fitting (Alch + heli + village fit on a side island). Sources: https://www.bloonswiki.com/Infernal , https://bloons.fandom.com/wiki/Infernal/Strategies

**Strategy 1 - Quincy, subs, Apache Prime 5-0-2 + Alch 4-2-0 + Village 2-2-0, Wizard Lord Phoenix ("Full Auto Start", no abilities listed)** (source: https://www.youtube.com/watch?v=bJHJBN9QHmI ; ApexZ, 2026-08-07; confidence: video-description; written steps skip the first sub placement)
- Hero: Quincy (R6; fandom: small island in the middle of the bottom wave).
- Core towers: Dart 0-0-0, Sub 2-0-2, Alch1 4-2-0, Heli 5-0-2 (Apache Prime), Village 2-2-0, Wizard 5-0-2 (Wizard Lord Phoenix), Alch2 + Alch3 4-2-0.
- Purchase order: R6 Quincy; R7 Dart (fandom: upper middle pillar, Strong after the 2nd blue wave); [Sub placement not written - fandom/Hbomb: sub in the top-right pond ~R9]; R10 Sub 1-0-0; R13 2-0-0; R15 2-0-1; R19 2-0-2; R27 Alch 2-0-0 + Heli; R30 Heli 1-0-0; R32 2-0-0; R36 3-0-0; R37 Heli 3-0-2 + Village; R38 Village 0-2-0; R40 2-2-0; R41 Alch 3-2-0; R45 4-2-0; R54 Heli 4-0-2; R79 Heli 5-0-2; R90 Wizard 4-0-2; R94 Wizard 5-0-2; R96 Alch 4-2-0; R97 Alch 4-2-0.
- Key placements: heli pad + alch + village on one side island (fandom: place carefully; all three fit).
- Abilities used: none listed. Comments on similar Quincy guides: R37 camo can leak - place Quincy as high as possible / L3 ability on R37 as insurance.
- Account conflicts: none.

**Strategy 2 - Quincy, Apache Prime, Prince of Darkness 2-0-5, Maim MOAB, MOAB Press, First Strike** (source: https://bloon.games/how-to-beat-chimps-on-infernal/ (written steps; video https://www.youtube.com/watch?v=Xwf0pPeGroU); confidence: verified-written-steps, version not stated)
- Hero: Quincy (rock at bottom centre).
- Order: Quincy; Dart upper rock; Sub upper-right water, Sniper lower-right rock (Strong), Sub lower-left water; Heli right rocky area 2-0-0; Sniper 1-1-0; Heli 3-0-0; Village 0-2-0 near heli; Alch 3-0-0 next to heli; Village 2-2-0; R40 Quincy ability on the MOAB; Sniper 2-2-0; Alch 4-2-0; Sniper 3-2-0; Heli 3-0-2; R57 Heli 4-0-2; Wizard upper-middle rock 0-0-4 + Alch2 3-0-0; R78 Wizard 2-0-5; Sniper 4-2-0; Glue 0-2-3 on the left rocks; 2 Boomerangs 2-0-4 above/below the glue; R95 Quincy abilities; R96 Heli 5-0-2, Sub 0-4-0 at the end; R99 spend leftovers on the upper-middle rock; R100 First Strike + Quincy ability.
- Abilities: Quincy R40/R95/R99/R100; First Strike R100.

**Strategy 3 - Quincy, Druid 1-3-0, Super 0-4-2 (Tech Terror), Apache Prime** (source: https://www.youtube.com/watch?v=2Hx219EZNN0 ; unescaped, v33.3, 2022-11; confidence: verified-written-steps, OLD) - R6 Quincy bottom rock; R7 Dart; R9 Sub; R12-18 Sub 2-0-2; R20-27 Druid 0-2-0 -> 1-3-0 First; R27 Sniper 1-1-0 Strong, Super 0-2-0; R39-41 Super 0-2-2; Village 0-2-0; Heli 3-0-2; R57 Heli 4-0-2; R80 Heli 5-0-2; Village 2-3-0; Super 0-4-2; Sniper 4-2-0; Heli 2-3-0; Sub 2-4-0; abilities R10/R40 Rapid Shot, R76/R78 Storm of Arrows, R98 Tech Terror, R100 First Strike.

Wiki alternative (no written steps): Elite Sniper 0-5-2 + Elite Defender 0-2-5 with Jungle Drums + Stronger Stimulant on the right island saving to Permanent Brew, then 0-2-4/0-3-2 sniper spam (sYnce v56.3 Corvus version: https://www.youtube.com/watch?v=p_2m1FX91f8). BEZ (Dartling bottom path tier 5, allowed by the 5-4-5 cap) with Stronger Stimulant + Overclock (ability) + MIB per wiki; dartling aiming is fine for BEZ (it does not use the cursor - inferred, verify). Video-only no-ability guides: Culture (https://www.youtube.com/watch?v=k7NJmX_byzo), n0 Skilz v52.0 (https://www.youtube.com/watch?v=1ZI8Hvi0GNQ), Hmmphington (https://www.youtube.com/watch?v=xePgJBlGkls).

**Bot notes:** Strategy 1 is the best bot fit: hero + heli are auto-targeting (Heli 3-0-x+ has Pursuit; no lock-in-place/figure-8 needed - set Pursuit once if it is not the default, inferred), no abilities, few towers. Main risk is fitting heli pad + alch + village on the tiny side island (fandom warns mistakes are catastrophic without selling) - precompute exact spots. R7 dart placement is height-sensitive (BTD6 Fenix: "too high or too low and you will die"); set the dart to Strong for R7. Optional insurance: blind Quincy L3 press on R37/R40.


### Flooded Valley (Expert)
**Map traits / what it requires:** Two simultaneous, fully overlapping lanes run along the top of a dam (one top->bottom, one bottom->top), and leaks are hard to see. The dam blocks line of sight, so land towers on the big left land hit almost nothing; the exceptions are towers with very long range on the raised rocks (Sniper), or towers that ignore line of sight (Ace, Heli, Druid of the Jungle vines, Guided Magic/Obyn). There is lots of water on the right (bends at the top and bottom, plus a middle bulge). Removable: secret flood button ($5,000), which floods the left land and sells non-amphibious towers; fandom says it is not worth it. **Water towers (Sub/Mermonkey/Buccaneer, plus Ice, which can stand on water) are effectively REQUIRED.** Fandom: "Starting with 0-0-0 Sub is necessary to beat Round 6 and Round 7 in CHIMPS". Silas's ice lets land towers (village, engineer) stand on water.

**Strategy 1 - Subs + Silas + Mermonkey + Carrier Flagship** (source: https://bloon.games/how-to-beat-chimps-on-flooded-valley/, based on BTD6 Master video https://www.youtube.com/watch?v=e7xKk8vJqN4, about 11 months old, roughly v52-53; confidence: verified-written-steps, with milestones but few exact rounds)
- Hero: Silas ("use his abilities freely" early; not required)
- Core towers: 2x Sub 0-0-0; Mermonkey 3-0-2 -> 4-0-2 Abyssal Warrior -> 5-0-2 Lord of the Abyss; Buccaneer 2-2-0 (middle first) -> 3-2-0 Destroyer -> 4-2-0 Aircraft Carrier -> 5-2-0 Carrier Flagship; Village 4-2-0; Ice 5-2-0 Super Brittle; Engineer 5-0-2 Sentry Champion; Ice 0-5-2 Absolute Zero
- Purchase order:
  - R6: Auto Start off, then 2 Subs 0-0-0 straight away. Then Silas.
  - Then a Mermonkey and a Buccaneer. Buccaneer 2-2-0 (middle first), then 3-2-0.
  - Before R36: Mermonkey 3-0-2. Before R40: Mermonkey 4-0-2 Abyssal Warrior.
  - Then Village 4-2-0, Buccaneer 4-2-0 -> 5-2-0, Mermonkey 5-0-2.
  - R85: Ice1 placed and taken to 5-2-0. Before R96: Engineer 5-0-2. Before R100: Ice2 0-5-2.
- Key placements: one Sub on the bottom bend (fandom: its range should touch the bottom entrance, Strong targeting); Sub2 at the top bend. Mermonkey, Buccaneer and Ice go in the water at the bends or the middle bulge (project geometry: bottom bend ~(0.52,0.70), top bend ~(0.49,0.16), bulge ~(0.55-0.58, 0.43-0.64)). The source does not say where the Village and Engineer go; inferred: on Silas's ice or at a land edge in range.
- Abilities used: Silas abilities early (optional). Absolute Zero's ability "freezes the screen when you need it most" (R100, timing optional).
- Account conflicts / substitutes: **Lord of the Abyss 5-0-2 is LOCKED (Mermonkey capped at 4-4-4).** Stop at 4-0-2 Abyssal Warrior. Source-backed alternatives for that late money: Carrier Flagship is the proven carry here (BTD6 Index LTC is Carrier Flagship 5-2-0 + Geraldo; Lazynomicro "Carrier Buff" v57-era video https://www.youtube.com/watch?v=1kNDM2g-DXc). Putting the saved ~$ into earlier Super Brittle/Absolute Zero, or a second Abyssal Warrior, is inferred/UNVERIFIED. Everything else fits the caps (Village 4-2-0 has no Primary Expertise; Ice and Engineer are fully unlocked).

**Strategy 2 - Brickell Sub army (Sub Commander + Ballistic Missiles + First Strike)** (source: fandom Flooded Valley/Strategies, "From the Sub Commander strategy", https://bloons.fandom.com/wiki/Flooded_Valley/Strategies; version unknown; confidence: wiki)
- Hero: Admiral Brickell
- Core towers: Subs 0-0-0 start; 3-0-0 Submerge and Support at the top and bottom bends (for the R24/R33 camos); 3-2-0 Destroyer or 2-0-4 Sub for the R40 MOAB; mid game: 2-0-5 Sub Commander plus spammed 0-3-2 Ballistic Missile subs; one sub to 0-4-x First Strike -> 0-5-x Pre-Emptive Strike by R90; a pair of 4-0-0 Bloontonium Reactors also suggested for R55-type rushes.
- Purchase order: R6 0-0-0 Sub on the bottom curve (Strong), a second Sub ASAP; Submerge and Support by R24/R33; MOAB answer by R40; Sub Commander and Ballistic Missile spam R41-R80; Pre-Emptive Strike within R90; more 0-3-2 subs after that.
- Abilities used: Brickell's abilities on R94, R96 and R98; First Strike twice on R100 (once on the BAD, once when it is about to pop).
- Account conflicts / substitutes: none (Sub and Brickell fully available).

**Strategy 3 (not for the bot) - Pat Fusty + Carrier Flagship deck + Snowstorm platform** (same fandom page, "From the flagship strategy"): 5-2-0 Carrier Flagship, 0-4-2 Snowstorm ON the flagship deck to make an ice platform, then a 4-0-2 Village, a 0-3-1 Alchemist and a 0-2-5 Prince of Darkness on the ice, and a 2-0-5 Tack Zone on the other deck. Pat's Rallying Roar on R94/96/98/99, Big Squeeze R97(-98), Snowstorm R95/R99, two First Strikes on R100. It needs deck placement and lots of ability timing, so it is unsuitable for the bot.

Other proven (video-only, no text): Doreo "double merm start", no abilities/micro, v52.1 (https://www.youtube.com/watch?v=xruveEV6vnw); G-Horizon no abilities/micro, U53 (https://www.youtube.com/watch?v=68Jbc9m1zts; project notes: 2 Mermonkey start, Silas, Destroyer, Lord of the Abyss); sYnce Obyn + Farwind Seer + Glue Storm, v57.4 (https://www.youtube.com/watch?v=W7jkDosqR38); sYnce hero-less Perma-Spike + LotA, v54.2 (LotA locked).

**Bot notes:** No aiming needed in Strategy 1. Sub/Mermonkey/Buccaneer/Ice all go on water, and **no deck placement is needed in Strategy 1** (do not put anything on the Flagship deck). The open problem is the Village 4-2-0 and Engineer 5-0-2: they are land towers, and the source does not show where they go. If the bot cannot place on Silas's ice (the project model marks it illegal), use a left-land spot inside buff/sentry range, or skip them and add a water tower (inferred). Sub placement on R6 is pixel-sensitive ("might take a couple of tries"). Do not buy the $5,000 flood. Strategy 1 with the 4-0-2 cap is the best bot fit: written order, no abilities needed. Strategy 2 depends on the timed double First Strike on R100.

### Ravine (Expert)
**Map traits / what it requires:** Two entrances take turns by round (odd rounds use the right entrance, even rounds the left; project notes) and each splits into 2, so there are 4 short lanes. Bridge walls and trees block line of sight almost everywhere. The river is too low for water towers: they attack only via Aircraft Carrier planes, First Strike, the Monkey Pirates ability, Bloontonium range, or 2-3-0 Ballistic Missile + Advanced Intel. The bottom-left area touches 3-4 lanes and is the best land. Perma-Spike is bad (its piles land on one side only; fandom). Removable/easter egg: **the sword in the stone, free, one use; tap it 24 times. Fandom: "the only possible way to beat both Round 6 and 7 on CHIMPS" is to use the sword.** Effectively REQUIRED: the sword for R6-R7, plus towers that ignore walls for the late game. Wiki lists Sky Shredder Ace, Prince of Darkness (hidden spot in the centre-left trees), Druid of the Jungle vines, and Spiked Balls/Mines at the exits; Etienne (UCAV) and Psi are noted heroes. Wiki: "by consensus the second hardest map".

**Strategy 1 - OneEyedDeacon Ezili + darts + Druids + Prince of Darkness + Spiked Balls** (source: https://www.youtube.com/watch?v=JtP8VQc5Leo, "DOMINATE Ravine Chimps", v54.1, text guide in the description; confidence: verified-written-steps)
- Hero: Ezili (placed R19, Strong, as far bottom-left as possible, right of dart2); bought to level 20 on R100.
- Core towers: Dart1 0-3-0 (first), Dart3 0-3-0, darts 4-6 and 8 0-0-0/0-1-0; Druid1 1-3-0 (Strong); Druid2 3-0-0 (Strong); Spike1 4-0-2 (left exit, Smart), Spike2 3-0-2 (right, Smart); Village1 3-2-0, Village2 2-0-0; Wizard1 2-0-5 Prince of Darkness; Alch1 3-2-0 (for wizard), Alch2 3-0-0 (for spike1); Bomb1 4-2-0, Bomb2 4-2-0; Boomerang1 0-2-5 (Strong); Ninja1 0-4-0 Sabotage.
- Purchase order (verbatim rounds): R6 three darts 0-0-0 (dart1 left on Strong; dart2 under the sword on Last; dart3 bottom middle) | R7 dart3 0-1-0, **sword when the last green comes (or mash the sword)** | R8 dart4 0-0-0 left, Strong | R9 dart5 0-0-0 Strong | R10 dart1 0-2-0 on First | R13 dart1 0-3-0 | R14 dart6 0-0-0 next to dart3 | R15 dart3 0-2-0 | R16 dart3 0-3-0 | R19 Ezili | R20 dart8 0-0-0 | R21 druid1 0-0-0 Strong, right of the right track | R22 dart8 0-1-0 | R26 spike1 0-0-0 left | R27 druid2 0-0-0 Strong at the intersection | R28 bomb1 0-0-0 | R29 druid2 1-0-0 | R31 druid2 2-0-0 | R32 spike1 0-0-2 Smart | R33 druid1 1-1-0 | R36 druid1 1-3-0 | R37 village1 0-0-0 | R38 druid2 3-0-0 | R39 village1 0-0-2 | R40 spike2 0-0-2 Smart, right behind druid2 | R41 spike1 1-0-2 | R42 wizard1 1-0-3 | R43 wizard1 2-0-3 | R46 spike1 3-0-2 | R47 wizard1 2-0-4 | R49 village1 2-0-2 | R50 spike2 3-0-2 + alch1 3-2-0 for wizard1 | R51 alch2 3-0-0 for spike1 | R52 bomb1 3-2-0 | R54 bomb2 3-2-0 right | R56 bomb2 4-2-0 | R60-R70 hex blimps (see abilities) | R72 wizard1 2-0-5 | R75 boomerang1 0-1-4 Strong | R76 boomerang1 0-2-4 | R91 boomerang1 0-2-5 | R92 village2 2-0-0 | R93 village1 3-2-0 | R95 ninja1 0-4-0, Sabotage the DDTs | R96 bomb1 4-2-0 | R97 spike1 4-0-2 | R98 hex at start | R99 Sabotage at start | R100 buy Ezili level 20, hex.
- Key placements: dart1 left, its range border through a tree; dart2 under the sword, its range through two bridge-post corners; dart3 bottom middle; village1 as high as possible, its range border touching a tree corner; spike2 on the right behind druid2. The spike1 position was not finalised by the author ("need to figure out position").
- Abilities used: the sword (R7); **Ezili Heartstopper/hex timed on many rounds** (R60, 62, 64, 66, 68 "when MOABs get to middle of bridge", 70, 72, 74, 80, 82, 85, 86, 87 "when first left ZOMG reaches middle of middle bridge", 88, 98, 100); Sabotage R95, R99; Ezili targeting switched First/Strong on R64 and R87.
- Account conflicts / substitutes: none (Village 3-2-0 max is top-3; Ezili owned).

**Strategy 2 - OneEyedDeacon Etienne + Sky Shredder** (source: https://www.youtube.com/watch?v=OpHwKwqMcOY, v50.2; also the Geraldo variant https://www.youtube.com/watch?v=i5YIBkeTklg, v51.2; confidence: video-description via prior project research summary, round numbers inferred)
- Hero: Etienne
- Core towers: darts (0-3-2 Triple Shot), Druid of the Jungle 1-3-0 (Strong), Spikes 0-0-2 Smart -> 3-0-2/4-0-2 at the left and bottom exits, Glue 1-1-0 -> 0-2-3, Village 2-0-2, Ace1 2-0-3 + Alch 3-2-0, Ace2 4-0-0 -> 5-2-0 Sky Shredder, Bombs 4-2-0, 2-0-4 MOAB Press boomerangs before R76-R80.
- Order (project summary, inferred): darts R6-R10 -> Druid + Spike + Glue R11-R20 -> Spike2 + Village R20-R30 -> Ace1 + Alch + Spikes 3-0-2 by R40 -> Ace2 4-0-0 R40-R60 -> Sky Shredder R60-R80.
- Abilities: the sword (R6/R7), Drone Swarm/UCAV, plus heli micro in the original (the project removed it for Hard).
- Account conflicts: none.

**Strategy 3 - ApexZ "Full Auto Start", Geraldo** (https://www.youtube.com/watch?v=drVwDHoVG6M; confidence: snippet-only via prior project notes: 6 darts, Geraldo items, Druid, Aces, sword). The description was not retrievable (YouTube 429/captcha). Get its written guide when possible: ApexZ routes are no-micro and auto-start, which suits the bot best.

Others (video-only): Doreo v49.3 (https://www.youtube.com/watch?v=EPvQKs6b58c), Doreo v54.2 "assassins", meaning Ninja (https://www.youtube.com/watch?v=yaSpQmvQoWg), sYnce Ezili + Desert Phantom v56.3, sYnce Silas + Icicle Impale + Bloon Solver v56.0, sYnce Obyn + Farwind Seer + Glue Storm v57.3 (https://www.youtube.com/watch?v=P4kt6LTpwHE). BTD6 Index heroless LTC: Bounty Hunter 2-4-0 + Golden Justice 2-5-0 + Elite Defender 0-2-5 + MOAB Press 0-2-4 + Bloon Crush 5-2-0 (v49.3).

**Bot notes:** The sword is mandatory: 24 taps, with the last tap timed as the last green passes (OED: "mash the sword" also works). Project notes: tap 23 times during R6 and the 24th on R7. This is a click-timing task the bot must script. Strategy 1 leans hard on Ezili hex timing (about 20 timed presses, some tied to blimp positions); blind start-of-round presses may fail R68/R87. Placements are pixel-tight ("range border through tree corner"). Spikes on Smart and Druids on Strong are targeting settings (OK). No selling, no deck. Bot pick: Strategy 1 has the only full written route, but expect ability-timing risk. Getting the ApexZ Geraldo auto-start text would likely give a lower-micro route.

### Sanctuary (Expert)
**Map traits / what it requires:** 2 entrances merge in the middle and split into 4 exits. Fandom: no line-of-sight blockers, but towers stand only on small round platforms that **move/rotate at the start of every round**, so short-range towers lose their lane. The bottom-middle platform barely moves. The statue platform has two tiny ponds (Sub/Buccaneer). Wiki: easier than the "true experts" (about Workshop level). Effectively REQUIRED: towers indifferent to platform motion: infinite range (Sniper, Desperado per recent guides, Psi), seeking (Wizard Guided Magic -> Archmage, Ninja), or **Perma-Spike on the precise bottom-middle spot with "Set Target"** (+ village + Stronger Stimulant), which "makes the late game trivial" (bloonswiki). BEZ Dartling is also wiki-recommended (bottom platform). Fandom: 2-0-5 Sub Commander is great; a Mortar aimed at the centre vines hits every bloon. Version 27.0 changed the platform start positions and broke old CHIMPS starts, so use post-v27 guides only.

**Strategy 1 - OneEyedDeacon Obyn + Desperados + Snipers + Archmage + Perma-Spike** (https://www.youtube.com/watch?v=auCq92xN0nk, v53.0; confidence: video-description NOT retrieved (429). Content from prior project research summary; rounds are inferred.)
- Hero: Obyn Greenfoot
- Core towers: 2x Desperado 0-0-0 at R6 (middle-left and middle-right platforms); Sniper(s) 1-0-2 / 0-2-2 on Strong (bottom-right platform); Wizard 2-0-2 -> 3-0-2 -> 4-0-2 -> 5-0-2 Archmage; Village 0-0-2 (camo); Spike Factory -> x-0-5 Perma-Spike + Alchemist 4-x-x Stronger Stimulant on the bottom-middle platform; Glue toward Bloon Solver (project note: "Glue 4-2-0 ... -> Bloon Solver", exact crosspath unverified).
- Order (inferred): R6 2 Desperados + Sniper; second Sniper early; Obyn; Wizard to 4-0-2 mid game; Village 0-0-2; Perma-Spike route + Alch on the bottom-middle platform; Wizard 5-0-2 by ~R70.
- Abilities: Obyn's not stated as required (UNVERIFIED).
- Account conflicts: none known (Desperado, Wizard, Spike, Glue fully unlocked).

**Strategy 2 - ApexZ "Full Auto Start", Silas** (https://www.youtube.com/watch?v=YcYjHojsqnM, ~v56; confidence: snippet-only via prior project notes: Silas, Desperados, Snipers, MOAB Press boomerang, 5 Ice Monkeys incl. Absolute Zero). The written guide was not retrievable (429). This is the auto-start/no-micro candidate, so fetch its description before building.

**Strategy 3 - Perma-Spike "no micro"** (FroStee Mate, "Return of the King! (ft. Permaspike)", https://www.youtube.com/watch?v=nLwwf5mfwlI, ~1 year old; FroStee v57.3 "NO EFFORT Simple Sanctuary ft. the (kinda) NEW tower", https://www.youtube.com/watch?v=ouxgq-tWGt4; confidence: snippet-only, titles only).
Others: Doreo v45.3 "churchill op", Churchill hero (https://www.youtube.com/watch?v=_cL1XLGn5Xk); Doreo v50.2 (https://www.youtube.com/watch?v=6jrhlnDukfY); bloon.games' video (https://www.youtube.com/watch?v=d1yK7Dl9n9Q, no written steps); sYnce Etienne + Farwind Seer + Absolute Zero / Geraldo + Axis of Havoc + Perma-brew / Adora + Desert Phantom. OED v50 Striker + Bomb Blitz (https://www.youtube.com/watch?v=NBBIRhJve8M) is outdated (Bomb Blitz was nerfed). BTD6 Index: LTC Perma Charge 0-5-2 + Wizard Lord Phoenix 1-5-0 + Geraldo (v49.3); heroless Archmage 5-0-2 + Elite Defender 0-2-5 + Base Boomer 2-0-2 + Permanent Brew 5-2-0.

**Bot notes:** The biggest issue is the **moving platforms**. Placement coordinates are valid only for the platform's position on that round, and towers ride along. The bot needs per-round platform positions (the project has them decoded) and should place long-range or seeking towers only, except on the bottom-middle platform. Perma-Spike needs **Set Target** (a one-time aim point on the central split / intersection); doable if the bot can set a target point once. Spikes keep producing there, but a moved platform may change this (UNVERIFIED). Sniper/Desperado targeting Strong is fine. A Mortar on the centre vines is a one-time aim (fandom). No deck, no selling. Best bot fit: the Perma-Spike + Snipers/Desperados + Archmage route (Strategy 1), or ApexZ's auto-start if its text can be obtained. Both avoid ability timing.

### Dark Dungeons (Expert)
**Map traits / what it requires:** Walled rooms with 4 lanes: 3 non-MOAB bloon lanes from the bottom (left, middle, right), and blimps alternating between the middle-bottom lane and a long top lane. The middle lane sits lower (a ledge), so most towers in other rooms cannot see it. A sludge pool in the bottom-right room takes water towers (Mermonkey Trance there can reach both MOAB entrances with range buffs). Removables: two free **torch spike traps** (5-damage stun spikes, 60 s cooldown each; "the only way" for most CHIMPS starts, R7 etc.; fandom says CHIMPS "mostly necessary") and the Dungeon Statue ($30k/$50k/$100k, not recommended). Towers that see over the ledge: Perma-Spike, Arcane Spike/Archmage, Spectre (weak past R80), Spirit of the Forest, Sky Shredder. The alternative is two kill-zones (Overdrives/Tack Zone + Embrittlement + MOAB Press/Glue + Primary Training). Exits: Spiked Balls (+Berserker Brew, Dragon's Breath) at the 3 exits, Smart Spikes at the left/right exits, Even Faster Production at the middle. REQUIRED: none strictly; per-room defence plus exit spikes works. Juggernauts are strong (bounces in rooms; 4-0-2 for camo/range).

**Strategy 1 - OneEyedDeacon "Arctic Knight Spam" (Sauda)** (https://www.youtube.com/watch?v=P-pNLDMPspc, v51.2; confidence: verified-written-steps)
- Hero: Sauda (R13, top right)
- Core towers: darts (dart2 0-3-0, dart1 0-3-0, dart3/4/5/7 3-0-2 -> 4-0-2 Juggernaut); Snipers 1-1-0 and 1-0-0 (Strong); Spikes: spike1 4-0-2 (target set at the intersection), spike2 3-2-0, spike3 0-0-0; Alch1 3-2-0, Alch2/Alch3 3-0-1; Tack1 2-0-4 Overdrive; Villages 2-0-2 / 3-0-2 x3; Wizard 0-3-2; Ice1 5-2-0 Super Brittle; Ice2 4-1-0; Glue1/Glue2 0-2-4 (Strong); **Mermonkeys 0-4-1 Arctic Knight x4**; Engineer 0-3-1.
- Purchase order (verbatim): R6 dart1 left, dart2 middle (as far bottom-left as possible), dart3 right | **R7 right trap** | R8 dart4 right + dart1, dart3 0-1-0 on Strong | R9 dart5 middle | R10 dart6 left on Strong | R13 Sauda top right | R14 dart2 0-2-0 | **R15 both traps for pinks** | R16 dart2 0-3-0 | R18 sniper1 Strong top left | **R21 left trap** | R22 spike1 top left | R23 sniper1 1-0-0 | R25 sniper2 Strong top right, Sauda on Close, Leaping Sword for purples | R26 sniper2 1-0-0, Sauda on First | R28 alch1 Strong middle | R30 spike2 middle | R33 spike3 top right | R34 dart1 0-3-0 | R35 tack1 1-0-2 | R36 tack1 2-0-3, both traps at start | R37 alch1 2-0-0 | R39 tack1 2-0-4, both traps for rainbows | R40 dart5 3-0-2, Leaping Sword after the MOAB breaks | R42 village1 0-0-2 top left + dart7 3-0-0 top left + sniper1 0-1-0 | R43 dart7 3-0-2, Sauda Close, both traps + Leaping Sword for ceramics | R44 dart3 3-0-2, Sauda First | R45 dart7 4-0-2, Leaping Sword | R46 dart4 4-0-2 | R47 village1 1-0-2 + spike1 0-0-2, target spikes to the intersection | R48 village1 2-0-2 | R49 village2 0-0-2 middle | R50 dart5 4-0-2 + village2 2-0-2 + spike1 2-0-2 | R51 spike1 3-0-2 | R52 alch1 3-2-0 | R55 alch2 3-0-1 for spike1 | R56 village3 2-0-2 top right | R59 wizard1 0-3-2 under Sauda | R60 village2 3-0-2 | R61 village3 3-0-2 | R63 retarget spikes next to sniper1; both traps for the first rush, Sword Charge on the third rush | R64 ice2 4-1-0 middle | R66 glue1 0-1-3 top right, Strong | R68 glue2 0-1-3 middle, Strong | R75 spike1 4-0-2, Sword Charge/Leaping Sword | R76 Sword Charge (or both traps) | R78 Sword Charge twice | R79 mermonkey1 0-4-1 | R80 mermonkey ability | R82 mermonkey2 0-4-1 top right, both abilities for fBFBs | R83 glue1 0-2-4 | R84 glue2 0-2-4 | R85 engineer1 0-3-1 top right, both mermonkey abilities | R86 spike2 3-2-0 + alch3 3-0-1 for spike2 | R87, R88, R92, R94, R96 both mermonkey abilities (for ZOMGs) | R95 ice1 5-2-0 | R97 mermonkey3 0-4-1 top right, ability | R98 2x mermonkey ability | R99 mermonkey4 0-4-1 middle | R100 all mermonkey abilities.
  (Note: "ice1 5-2-0" appears at R95 with no earlier ice1 purchase listed; ice2 is 4-1-0 at R64. Treat it as written.)
- Abilities used: torch traps (R7, 15, 21, 36, 39, 43, 63, 76); Sauda Leaping Sword / Sword Charge (R25, 40, 43, 45, 63, 75, 76, 78); Arctic Knight abilities R80-R100.
- Account conflicts: none (Mermonkey 0-4-1 is within the 4-4-4 cap; Village 3-0-2 is fine; Ice 5-2-0 is fine).

**Strategy 2 - ApexZ "Full Auto Start", Silas, no abilities, no traps** (https://www.youtube.com/watch?v=wqGrbHhDv3U, ~v55; confidence: video-description via prior project research. Placements and crosspaths are known; the round list was not re-retrieved because of the 429.)
- Hero: Silas (middle room, inside the middle lane's bend)
- Core towers: Dart1 0-3-2 (bottom-left room); Dart2 0-3-0 (bottom-middle); Dart3 right; Dart4/Dart6/Dart7 4-0-2 Juggernaut; Dart5 top-left; Sub (Strong) in the sludge pool; Glue1 2-1-0 (top-right MOAB turn), Glue2 2-0-0 (middle); Spike1 1-0-4 (left exit) + Alch1; Spike2 right exit; Spike3 1-0-4 (middle exit); Village1 (top-left corner), Village2 (low in the middle room); Ice1 4-1-0 -> 5-2-0 (top-right MOAB turn); Tack1 -> 2-0-5 Tack Zone (just above the top MOAB lane's first turn) + Alch2; Tack2 2-0-4 (middle room); Mermonkey1 3-0-1 + Mermonkey2 4-0-1 (sludge pool).
- Priorities (project summary): by R40: Dart1 0-3-2, Dart2 0-3-0, Dart4 4-0-2, spikes at all 3 exits, Alch1, Ice1 4-1-0 before the R40 MOAB. By R80: Tack Zone + Super Brittle + Juggernauts in every side room + Village/Alch buffs.
- Account conflicts: none.

**Strategy 3 - Doreo Silas "double Super Brittle", no abilities/micro** (https://www.youtube.com/watch?v=GaixgDx4--4, v50.0; confidence: snippet-only, "SILAS DOUBLE SBRIT IS SO OP"). Related: sYnce Silas + 2 Super Brittle + Coldchain spam v56.0 (https://www.youtube.com/watch?v=0nhR2EyZf5c); Chom Chom LCC Arctic Knight + Silas (https://www.youtube.com/watch?v=6PR4Jh03G4A). Other v56-57 sYnce runs: Dan D'monke + Glaive Lord, Etienne + Sentry Champion, hero-less Tack Zone (Glue Strike + Embrittlement), Obyn + Farwind Seer + Glue Storm (Farwind Seer middle path "doesn't care about" walls). BTD6 Index heroless: Triple Shot 0-3-2, Juggernaut 5-2-0, Ultra-Juggernaut, Elite Defender 0-2-5, Carpet of Spikes 2-5-0, Bomb Blitz 0-2-5 (v49.3).

**Bot notes:** Strategy 1 is ability-heavy: torch traps timed to waves (e.g. "for pinks", "for rainbows"), Sauda abilities and targeting swaps, and **Arctic Knight needs an aim point** (wiki: "can specifically point its aim ... to cover each of the rooms"; one-time target per Mermonkey, then blind presses of the ability on the listed rounds, which may work). "Target spikes to intersection" is a one-time Spike Factory target point. Fandom: torch activation "is dependent on the side of the torch pressed, timing can be crucial". **Strategy 2 (ApexZ Silas, no abilities, no traps) is the best bot fit.** It uses only targeting settings (Sub Strong) and no aiming. The open item is getting its exact round list. A sub in the sludge pool works without a deck.

### Glacial Trail (Expert)
**Map traits / what it requires:** A single long lane with two loops, ice walls (Juggernaut bounces) and little central space. **Freeze mechanic:** every tower except Ice Monkeys, Silas (and Dan per project notes) is frozen for 2 rounds every 10 rounds counted from its placement round. Project rule: placed on round r, frozen on r+9, r+10, r+19, r+20, ... Frozen villages still buff, and spike piles persist (Perma-Spike piles last 4 rounds). Wiki planning: place late-game towers on rounds ending in 2 or 4, a lead popper on a round ending in 2, and camo on a round ending in 0. After R91 any tower can be placed freely. Water is too low for subs/boats. REQUIRED: none map-wide, but freeze-immune Ice/Silas and Perma-Spike are the consensus core; Ice/Silas lack BAD damage, so a BAD killer is needed (fandom).

**Strategy 1 - G-Horizon Silas + Ice + Perma-Spike + Carpet (no abilities/micro)** (https://www.youtube.com/watch?v=Hv8M3AOfwS0, Update 53; confidence: verified-written-steps)
- Hero: Silas (R13)
- Core towers: Dart 0-0-0; Ninja 1-0-0; Ice1 3-1-0 -> 4-1-0 -> 5-2-0 Super Brittle; Ice2 0-1-3 -> 0-1-4 -> 0-2-4; Ice3 0-1-3 -> 0-1-4 -> 0-2-4; Spike1 0-0-2 (Smart) -> 2-0-3 -> 2-0-4 -> 2-0-5 Perma-Spike; Spike2 2-4-0 -> 2-5-0 Carpet of Spikes.
- Purchase order (verbatim): R6 Dart, Ninja | R9 Ninja 1-0-0 | R13 Silas | R15 Ice1 | R18 Ice2 | R22 Spike1 | R23 Spike1 0-0-2 on Smart | R28 Spike1 0-0-3 | R29 1-0-3 | R30 2-0-3 | R32 Ice3 | R37 Spike1 2-0-4 | R39 Ice1 3-1-0 | R41 Ice3 0-1-3 | R43 Ice2 0-1-3 | R46 Ice3 0-1-4 | R48 Ice2 0-1-4 | R49 Ice1 4-1-0 | R65 Spike1 2-0-5 | R80 Ice1 5-2-0, Ice2 0-2-4, Ice3 0-2-4 | R82 Spike2 2-4-0 | R95 Spike2 2-5-0.
- Variant (G-Horizon Update 52, https://www.youtube.com/watch?v=Pb5TtbZ1gtA, also written): R6 Dart, Ninja; R9 Ninja 1-0-0; R13 Silas; R15 Ice1; R16 Ice2; R22 Spike 1-0-0; R26 1-0-2 Smart; R29 1-0-3; R33 2-0-3; R38 Ice3 (listed "203", likely 2-0-3); R39 Ice3 2-0-4; R40 Ice2 0-0-3; R42 Ice1 3-0-0; R45 Ice2 0-2-4; R46 Ice1 4-2-0; R50 Spike 2-0-4; R52 Alch 3-0-1; R67 Spike 2-0-5; R79 Ice3 2-0-5; R84 Ice1 5-2-0; R92 Ice2 0-2-5.
- Key placements (project notes): Dart on the small island left/below the first loop; Ninja on the tiny spot above the track before the first loop; Silas and Ice1 on the island right of the second loop near the exit. Spike near the end of the track (inferred).
- Abilities used: none.
- Account conflicts: none (Ice and Spike fully unlocked).

**Strategy 2 - bloon.games Sauda + Ultra-Juggernaut + Perma-Spike + Sentry Champion** (https://bloon.games/how-to-beat-chimps-on-glacial-trail/, video https://www.youtube.com/watch?v=o4p_QZoHVbI, ~1 year old; confidence: verified-written-steps)
- Hero: Sauda
- Core towers: Dart 5-2-0 Ultra-Juggernaut (Strong); Engineer 5-2-0 Sentry Champion; Druid 1-3-0; **Mortar 0-2-3 Signal Flare**; Spike 2-0-5 Perma-Spike (Smart from R47); Alch 4-2-0; Glue 0-2-4 (Strong); Ice 5-1-0 Super Brittle; Sub 0-4-0 First Strike.
- Order: R8 Dart (Strong) | R14 Engineer 2-0-0 | R22 Druid 1-3-0 (middle first) | R31 Mortar aimed at the first loop | R32 Spike 2-0-3 (bottom first); then Engineer 4-2-0, Mortar 0-0-3, Dart 3-2-0, Mortar 0-2-3, Dart 4-2-0 | R47 Spike Smart + Alch 3-0-0 next to it; then Dart 5-2-0; Sauda ability R57, R60, R73; Spike 2-0-5 | R81 Glue near the entrance (Strong) -> 0-2-3; Engineer 5-2-0, Alch 4-2-0 | R87 Ice 4-1-0 | R88 Sauda ability; Glue 0-2-4; Ice 5-1-0 | R97 Sub, middle path | R99 Sub 0-4-0 | R100 First Strike "as soon as the ZOMG is on the track" (sic; R100 is the BAD).
- Account conflicts: **Mortar bottom path is LOCKED (cap [5,5,0]), so 0-0-3 Signal Flare is impossible.** Substitute: skip the Mortar or keep it 0-2-0 (no camo). Camo then comes from Engineer? (UNVERIFIED) Better: use Strategy 1. The Mortar also needs one aim point (first loop), so it is a one-time setting.

Others (video-only): FroStee Mate "Axis of FroSt" no micro/abilities, v50.1 (https://www.youtube.com/watch?v=RlCStpsSGp0); Doreo v46.3; Culture no abilities/micro (https://www.youtube.com/watch?v=7WuOdkk2wTk); sYnce Silas + Super Brittle + Popseidon v56.3 (Popseidon is Mermonkey 0-5-x, LOCKED); sYnce hero-less LotA + Perma-spike (LotA LOCKED); ApexZ Full Auto Start, same route as G-Horizon (https://www.youtube.com/watch?v=L7JnwJOokNc). BTD6 Index 2TC with Geraldo: Pop and Awe, Glaive Lord, Monarch of Storms, Perma Charge, Sentry Champion, Spirit of the Forest, Blooncineration.

**Bot notes:** The bot must model the freeze. Do not click a frozen tower for upgrades/targeting; postpone instead. Freeze timing is tied to the guide's exact placement rounds, so **place towers on exactly the listed rounds** even if cash is available earlier. In Strategy 1: Spike1 placed R22 is frozen R31-32, 41-42, ..., 91-92 (piles persist); Spike2 placed R82 is frozen R91-92; Dart/Ninja placed R6 are frozen R15-16 etc.; Silas and the Ice monkeys are never frozen. Spike Factory on Smart is a targeting setting. Spike Storm (2-4-0) has an ability, but the guide does not use it. Strategy 1 needs no abilities, no aiming, no deck: **best bot fit**. Strategy 2 needs Sauda/First Strike presses and a locked Mortar crosspath.

### Tricky Tracks (Expert)
**Map traits / what it requires:** 6 short simultaneous lanes on 3 diagonal train tracks. Bloons slow and clump at each track's middle stop point, then speed up. No water. There are high ground and sight blockers. v52.1 made bloons faster, and v53 widened the tracks, so towers can no longer sit as close. OED: "Previous guides no longer work", so prefer guides from v53 on. Removable: the train ($2,500, +$2,500 per use, long cooldown); one-shots non-MOAB bloons on a track and stuns blimps; fandom says it is only worth it around R98. Aces/Helis are poor (separated lanes). Wiki: range buffs matter (Etienne's global range buff, Deadeye, Village); Archmage with range buffs and seeking. REQUIRED: none map-wide; between-track strips plus range-buffed coverage (Etienne) is the norm.

**Strategy 1 - ApexZ "Full Auto Start", Etienne + 6 Mermonkeys** (https://www.youtube.com/watch?v=fWry_CuR6GI, "Recent Patch", about 3 months old, ~v56; confidence: verified-written-steps)
- Hero: Etienne (R15)
- Core towers: 3 Darts; Mermonkeys 1-6 (Mer1/Mer3 -> 4-0-2 Abyssal Warrior; Mer2/Mer6 0-0-2); Boomerang1 4-0-2 M.O.A.R. Glaives; Boomerang2 0-2-4 MOAB Press; Sniper 1-1-0 (Strong); Village 4-0-2; Tack 2-0-4 x5; Engineer 5-0-0 Sentry Champion; Alch1 3-0-0 (-> 4-0-2 from R89 recommended), Alch2 3-0-0 (-> 4-0-2); Ice 5-2-0; Ninja 0-4-0; Glue1 0-2-4, Glue2 2-4-0.
- Purchase order (verbatim): R6 3 Darts | R8 Mer1 | R10 Mer2 | R11 Mer3 | R12 Mer4 | R15 Etienne | R17 Boomerang1 + Mer5 | R18 Mer6 | R20 Boomerang1 0-0-1 | R21 0-0-2 | R22 2-0-2 | R25 Sniper (Strong) | R26 Sniper 1-0-0 | R27 Boomerang1 3-0-2 | R29 Drone Swarm | R30 Mer2 0-0-2 | R31 Mer3 0-0-2 and Mer1 0-0-2 | R32 Mer6 0-0-2 | R35 Boomerang1 4-0-2 | R36 Drone Swarm | R37 Boomerang2 0-2-2, Sniper 1-1-0 | R38 Boomerang2 0-2-3 | R39 Drone Swarm | R40 Boomerang2 0-2-4 "when the MOAB passes by it" | R41 Mer3 2-0-2 + Village | R42 Village 0-0-2 | R44 Mer3 3-0-2 | R45 Mer1 3-0-2 | R46 Village 2-0-2 | R47 3-0-2 | R49 4-0-2 | R50 Tack1 2-0-4 | R51 Mer3 4-0-2 | R54 Mer1 4-0-2 | R55 Engineer 3-0-0 | R56 Engineer 4-0-0 | R57 Alch1 3-0-0 | R59 Ice 3-2-0 | R60 Ice 4-2-0 | R73 UCAV when 2 BFBs appear | R75 UCAV when 3 BFBs appear | R77 Drone Swarm on multiple BFBs | R79 Engineer 5-0-0 | R81 UCAV at the end of the round | R85 Ice 5-2-0 | R86 UCAV | R87 Ninja 0-4-0 | R89 Sabotage | R90 Drone Swarm | R94 Glue1 0-2-4 + Glue2 2-4-0 | R95 Tack2 2-0-4 + Alch2 3-0-0, UCAV on the DDTs | R96 Tack3 + Tack4 2-0-4, Sabotage | R97 Tack5 2-0-4 | R98 UCAV + Glue2 Glue Strike | R99 Sabotage, Drone Swarm at the end of the round | R100 Glue Strike.
- Key placements (project notes): darts and Mermonkeys on the strips between tracks near the middle (a range-40 Mermonkey reaches 4 lanes); Mer5 above the top track, Mer6 below the bottom track; Sniper on the parked train (high ground); Ice touching the middle track at its stop point.
- Abilities used: Etienne Drone Swarm / UCAV (R29-R99, a few tied to BFB/DDT appearance), Sabotage R89/R96/R99, Glue Strike R98/R100.
- Account conflicts: none (Mermonkey 4-0-2 within cap, Village 4-0-2 = Primary Mentoring top-4 OK, Engineer 5-0-0 OK, Ice 5-2-0 OK).

**Strategy 2 - OneEyedDeacon Etienne + Wizard Archmage + Mermonkeys** (https://www.youtube.com/watch?v=XxBPMVU-P68, v53.2, written for the widened tracks; confidence: verified-written-steps)
- Hero: Etienne (R13, next to the engineer)
- Core towers: darts 1-4 (dart3 0-1-0); Engineer 0-0-0 (Close); Wizard1 5-2-0 Archmage (on Close, later First); Sniper1 4-0-2 (Strong), Sniper2 0-1-0 (First); Mermonkeys 1-6 (Mer1 0-3-2, Mer2 4-0-2, Mer3-6 0-3-2); Village 4-0-2; Ice1 5-2-0, Ice2 3-1-0 -> 4-1-0; Tack1/3/4 2-0-4; Alch 4-2-0; Glue1 0-2-4 (Strong); Boomerang1/2 0-2-4 (Strong).
- Order (verbatim, condensed): R6 dart1-3 | R7 dart3 0-1-0 | R9 engineer Close | R10 dart4 | R13 Etienne | R14 wizard1 Close | R15 1-0-0 | R17 2-0-0 | R18 Drone Swarm | R19 sniper1 Strong | R20 sniper2 First | R21 mer1 | R22 sniper1 1-0-0 | R23 Drone Swarm | R24 sniper1 1-0-1 | R26 1-0-2 | R27 Drone Swarm | R30 wizard1 3-0-0 | R31 mer2 0-0-1 | R32 mer2 2-0-1 | R33 sniper2 0-1-0 | R34 mer1 0-2-1 | R36 mer2 3-0-1, Drone Swarm | R37 wizard1 3-2-0 First, Drone Swarm | R38 sniper1 2-0-2 | R40 sniper1 3-0-2, Drone Swarm | R42 village 2-0-0 | R49 wizard1 4-2-0 | R50 village 4-0-2 | R51 mer1 0-3-2 + mer2 3-0-2 | R52 mer3 0-3-2 | R54 mer4 0-3-2 | R55 mer5 0-3-2 | R56 mer6 0-3-2 | R59 mer2 4-0-2 | R62 ice1 4-1-0 | R63 ice2 3-1-0 | R64 ice2 4-1-0 | R75/R78 Drone Swarm + UCAV (timed to BFBs) | R80 wizard1 5-2-0 | R88 ice1 5-2-0, UCAV the ZOMGs | R89 tack1 2-0-4 | R92 alch1 4-2-0 | R93 glue1 0-2-3 Strong | R94 UCAV + Drone Swarm | R95 glue1 0-2-4 + boomerang1 0-2-4 Strong | R96 tack3 2-0-4 | R97 another 2-0-4 tack (listed as tack3 again) | R98 boomerang2 0-2-4 Strong, both abilities at start | R99 sniper1 4-0-2 + village 2-0-0 (as written) | R100 tack4 2-0-4, Drone Swarm.
- Account conflicts: none.

Others (video-only): Doreo no abilities/micro, v52.1, pre-widening (https://www.youtube.com/watch?v=HB46D0Y_oG8); sYnce Etienne + Sentry Champion + Super Brittle, v55.2 (https://www.youtube.com/watch?v=GPRJh2V7JRc); sYnce Silas + Perma-charge (https://www.youtube.com/watch?v=TwHsuNXHzS8); sYnce Obyn + Farwind Seer + Glue Storm, v57.2; N00BMaster477; Chom Chom WR. BTD6 Index LTC: Golden Justice 2-5-0 + Popseidon 0-5-2 + Geraldo (v52.0). Popseidon is LOCKED (Mermonkey tier 5).

**Bot notes:** Both written routes rely on Etienne's Drone Swarm/UCAV, Sabotage and Glue Strike. Most can be blind presses at round start (ApexZ: R29/36/39/77/81/86/90/99, plus R73/75 "when 2/3 BFBs appear" and R95 "on the DDTs", which are better pressed a few seconds into the round; inferred). ApexZ R40 "upgrade Boomerang2 to 0-2-4 when the MOAB passes" means a mid-round upgrade; buying it at R40 start is fine (inferred). There is no aiming in either route. Do not use the train except as an emergency. Placements on the strips are tight after the v53 widening. **ApexZ (Strategy 1) is the best bot fit**: auto-start, no micro, every tower within account caps, simple abilities.


## Summary table

One row per map: the strategy that suits the bot best (see each map's "Bot notes"). "Required map-wide tower" is what the sources say ground towers cannot replace on that map; "-" means most comps work.

| Map | Tier | Hero | Core towers | Required map-wide tower | Source |
|---|---|---|---|---|---|
| Lost Crevasse | Intermediate | Sauda | Tack 2-0-5, Druid 1-5-0, Sniper 0-2-2, Alch 4-2-0, Ice 5-2-0, Glue 0-2-5, 2 villages | Sniper seeing both lane ends (soft) | [link](https://www.youtube.com/watch?v=yjRUMBRZOss) |
| Luminous Cove | Intermediate | Admiral Brickell | Bucc 5-2-0 (heart pond), Dart 2-0-5, Druid 1-5-0, Village 4-2-0, Alch 4-2-0, Glue 0-2-4 | Water/Carrier Flagship (map-wide) | [link](https://www.youtube.com/watch?v=O65H67unAwA) |
| Ancient Portal | Intermediate | Quincy | Sub 2-0-4 (pond), Alch 4-0-1, Wizard 5-2-0, Glue 5-2-0, Village 4-2-0, Spike 2-0-5 | - | [link](https://www.youtube.com/watch?v=RtSL6RUWAO4) |
| Sulfur Springs | Intermediate | Obyn | Wizard 5-0-2, Bucc 5-0-2 (spring), Glue 0-2-5, Alch 4-2-0 | Water in central spring (soft) | [link](https://www.youtube.com/watch?v=vm5zTKXFyAc) |
| Water Park | Intermediate | Rosalia | Boomerang 0-2-2 + Sniper 0-2-2 on slide, Ace 2-0-5, Alch 3-2-0, Village 2-2-0 | Global aircraft (ace/heli) | [link](https://www.youtube.com/watch?v=dYsOxUMQV_g) |
| Polyphemus | Intermediate | Obyn | Druid 5-0-2, Sniper 0-2-5, Alch 4-2-0, Village 2-0-2, Spike 2-0-5 | - | [link](https://bloon.games/how-to-beat-chimps-on-polyphemus/) |
| Covered Garden | Intermediate | Rosalia | Desperado x2 + Sniper 0-2-2 (TL, pane rounds), Druid 1-3-0, Ace 2-0-5, Alch 3-2-0, Village 2-2-0 (left strip) | Global/outside-garden tower (ace or heli) | [link](https://www.youtube.com/watch?v=u0-X2o8hfQQ) |
| Quiet Street | Intermediate | none (Quincy optional) | ~7 Snipers (0-5-2, 4-2-0, 0-4-2...), Tack 5-0-2, Alch 4-0-1/4-2-0, Village 2-0-2/4-2-0, Spike 3-2-0, Glue 0-2-3 | Long-range (snipers/BEZ) | [link](https://www.youtube.com/watch?v=lwkCrJI-7DE) |
| Bloonarius Prime | Intermediate | Rosalia | Dart x3, Sub, Sniper 0-2-2, Druid 1-3-0, Ace 2-0-5, Alch 3-2-0, Village 2-2-0 | Global aircraft (ace/heli) | [link](https://www.youtube.com/watch?v=mLpg86Zc7Rs) |
| Balance | Intermediate | Sauda | Tack 5-0-2 Inferno Ring (centre) + Ice 5-2-0 + Alch 4-2-0 | - (needs central loop plots) | [link](https://www.youtube.com/watch?v=apOdpf5OR7M) |
| Encrypted | Intermediate | Sauda | Heli (Apache Prime/Pursuit) + Archmage, or crypt Sauda + Ultra-Juggernaut + PoD | crypt interior or heli/PoD (walls block outside towers) | [link](https://www.youtube.com/watch?v=3RHVoFwgyLY) |
| Bazaar | Intermediate | Rosalia | 3 darts, Druid 1-3-0, Sniper 0-2-2, Village 2-2-0, Ace 2-0-5 Flying Fortress, Alch 3-2-0 | - (ace is map-wide) | [link](https://www.youtube.com/watch?v=nyw0_VLPl38) |
| Spring Spring | Intermediate | Etienne | Bucc 5-2-0 Flagship, Mermonkey 4-0-1, Sub 0-5-0, Ice 5-2-0, Village 2-3-0 (+Perma-Spike optional) | Perma-Spike/Flagship planes (exit stall + global blimp) | [link](https://www.youtube.com/watch?v=8oRUiaBFsHY) |
| Moon Landing | Intermediate | Obyn | Sniper 0-2-5 Elite Defender (high ground), Heli 3-0-2, Wizard 0-2-5 + 5-2-0 Archmage, Village 2-2-0, Alch 4-0-1 | Elite Defender sniper / Archmage (crater walls block sight) | [link](https://www.youtube.com/watch?v=cSmSH9JAgBQ) |
| Haunted | Intermediate | Sauda | Sub 2-0-4, Bucc 5-2-0 Flagship (pond), Mermonkey 4-2-0, Village 4-2-0, Glue 5-2-0 + 0-2-4, Wizard 5-2-0 Archmage, Alch 4-0-1 | - (central pond water towers strongly favoured) | [link](https://www.youtube.com/watch?v=LJuBp-nHYno) |
| Firing Range | Intermediate | Psi | Sub 2-0-4, Bucc 5-2-0 Flagship, Village 4-2-0, Ice 5-2-0, Tack 2-0-5 | - (water towers; outpost $1,000 optional) | [link](https://www.youtube.com/watch?v=_PM_WfS-nOc) |
| Chutes | Intermediate | Geraldo | Heli 0-0-5 Comanche Commander + Glue Storm (or Flagship + Brickell) | heli / map-wide (alternating short lanes) | [link](https://www.bloonswiki.com/Chutes) |
| Rake | Intermediate | Sauda | 2 Desperados, Tack 2-0-5, Spike 2-0-5 Perma-Spike, Alch 4-2-0/4-0-1, Boomer 5-0-2, Ice 5-2-0, Village 4-2-0 | Perma-Spike at exits (erratic targeting) | [link](https://www.youtube.com/watch?v=yIlrhysKjPg) |
| Off The Coast | Advanced | Quincy | Sub 2-0-3, Heli 5-0-2, Alch 4-2-0, Village 2-2-0, Wizard 0-2-5, Sniper 1-0-0, Dart 0-2-5 | water Sub + global Heli/Sniper | [link](https://www.youtube.com/watch?v=hV74wqAusLI) |
| Cornfield | Advanced | Sauda | Dart 5-0-2, Boomerang 5-0-2 + 2-0-4, Village 4-2-0, Glue 5-2-0, Spike 2-5-0 | - | [link](https://www.youtube.com/watch?v=f_J04Y_M5c4) |
| Underground | Advanced | Churchill | 2x Desperado, Dart 0-3-2, Glue 5-2-0 + 4-2-0, Village 3-0-2/4-2-0, Alch 4-2-0, Wizard 5-2-0, Sniper 5-2-0 | - | [link](https://www.youtube.com/watch?v=eXTI3EzbFgc) |
| High Finance | Advanced | Quincy (or Etienne/Brickell inferred) | Buccaneer 2-5-0/5-2-0 (pond), Spike 4-0-2, Tack 5-2-0, Alch 4-2-0, Village 4-2-0, Glue 0-5-2 | water Buccaneer / global (buildings block sight) | [link](https://www.youtube.com/watch?v=YSHTM5sTkqU) |
| Another Brick | Advanced | Sauda | Ninja 4-0-2, Heli 4-0-2, Wizard 2-0-5, Village 3-0-2, Alch 4-2-0, 3x Boomerang 2-0-4, Glue 0-1-3, Spike 0-2-5 | over-wall DPS (Heli / PoD / Perma-Spike) | [link](https://www.youtube.com/watch?v=a6PNBW8MGtE) |
| Peninsula | Advanced | Admiral Brickell | ~11x Sub 2-0-4, Sub 2-0-5, Sub 2-4-0, Bucc 0-3-2, 2x Dart 4-2-0, Alch 3-2-0, Ice 4-1-0, Village 2-3-0, Merm 4-0-2 | water Subs (mountain blocks sight) | [link](https://www.youtube.com/watch?v=bkeuo0q7XbY) |
| Pat's Pond | Advanced | Churchill | 2x Desperado, 2x Sub 2-0-2, Glue 5-2-0, Alch 4-2-0, Villages 4-0-2/0-2-2, Wizard 5-2-0, Spike 2-0-5, Sniper 4-2-0 | - | [link](https://www.youtube.com/watch?v=CPBKQYUTSsU) |
| Cargo | Advanced | Sauda | Sniper 0-2-5 + 0-5-2 + 5-2-0, Alch 4-2-0 x2, Village 3-0-2, Wizard 0-2-5, Boomerang 2-0-4, Glue 0-2-4, Tack 2-0-4 x2 | Snipers (MOAB-only lane) | [link](https://www.youtube.com/watch?v=9OiV2P_YvCA) |
| Spillway | Advanced | Etienne (or Psi) | barrel Ninja, Wizard 5-2-0 + 2-0-5, Mermonkey 4-2-0, Village 2-0-2, Sniper 4-2-0, Spike 2-5-0 | barrel Ninja + wall-ignoring (guided Wizard/Mortar/Ace) | [link](https://www.youtube.com/watch?v=WVzGzQM5RPA) |
| Geared | Advanced | Psi (Geraldo alt) | 6-7 Snipers (2-0-5/0-2-5, 0-5-2, 0-2-4s, 2-0-4), Druid 1-3-0, Village 2-0-2, Alch 5-2-0 | Snipers (rotating gears) | [link](https://www.youtube.com/watch?v=6QOiPh3CY1w) |
| Mesa | Advanced | Etienne | Sniper 0-5-2 + 2-0-5 + 5-2-0, Boomerang 5-0-2, Village 4-0-2, Alch 4-2-0, Glue 0-2-4, 3x Dart | Snipers on plateau (two LOS-split lanes) | [link](https://www.youtube.com/watch?v=CVxEdZq3I2c) |
| X Factor | Advanced | Sauda | Sniper 2-0-5 + 0-5-2 + 5-2-0, Druid 1-3-0, Village 4-2-0, Alch 4-2-0 x2, Wizard 2-0-5, Glue 0-2-4, Tack 2-0-4 | Snipers (4 rotating lanes, tunnels) | [link](https://www.youtube.com/watch?v=IRdVGDWzArY) |
| Sunken Columns | Advanced | Sauda | darts x4, Druid 1-5-0 SotF, snipers 2-0-5/0-5-2/5-2-0, villages 2-0-2+0-2-2, alch 4-2-0, glue 0-2-3 | raised-ground snipers + Spirit of the Forest (both lanes) | [link](https://www.youtube.com/watch?v=_GHS1QFoyUY) |
| Midnight Mansion | Advanced | Sauda | Tack 2-0-5 Tack Zone (top-floor corner), Ice 2-0-5 Impale + Ice 5-x-x Brittle, Village+Alch (drawer), Glue 4-0-2 | - (top-floor chokehold; drawer for village) | [link](https://www.youtube.com/watch?v=KVlfBvOU0F0) |
| Erosion | Advanced | Psi | Sub 1-0-2 early, snipers 0-2-5/0-5-2/5-2-0, alch 4-2-0, village 2-0-2, Perma-Spike 2-0-5 (Smart), glue 0-2-4 | snipers (global, glacier) + exit spike | [link](https://www.youtube.com/watch?v=KOT6M9kcoUE) |
| Dark Path | Advanced | Etienne | Desperado 5-2-0, Skywarden 2-0-0, Dart 5-2-0 Ultra-Jugg, Ice 5-2-0, Tack 2-0-5, Village 3-0-0 | - (wall-ignoring/ricochet towers; keep walls) | [link](https://www.youtube.com/watch?v=eyIX-967nps) |
| Castle Revenge | Advanced | Psi | snipers 0-2-5/0-5-2/5-2-0 + 3x 0-3-2, darts (Dart 3-2-0), village 2-0-2, alch 5-2-0 | snipers (global) - lanes cannot be shared | [link](https://www.youtube.com/watch?v=XUfUa1MSU9g) |
| Last Resort | Advanced | Quincy | snipers 5-2-0/0-2-5/0-5-2, Perma-Spike 2-0-5 Smart (far right), 2x alch 4-2-0, village 2-2-0, glue 0-2-4 | Perma-Spike (single exit) | [link](https://www.youtube.com/watch?v=7fpYt6w9ziE) |
| Enchanted Glade | Advanced | Sauda | Druid 1-3-0, Sub 2-0-4, Glue 5-2-0 Solver by R63, Village 4-2-0, Spike 2-5-0 Carpet, Ice 0-2-5 Impale, alch 3-0-0 | - (bottom-centre chokepoint) | [link](https://www.youtube.com/watch?v=P5X5umWqjwA) |
| Sunset Gulch | Advanced | Sauda | snipers 4-2-0->5-2-0, 0-2-5, 0-5-2, 3x 0-3-2; alch 5-0-0; village 2-0-2 | global (rail lane) - snipers | [link](https://www.youtube.com/watch?v=uZcfkclocAs) |
| Party Parade | Advanced | Sauda | mirrored darts/desperados/snipers; Tack 2-0-5 (left); spikes 4-2-0 x2 + 2-4-0; villages 3-0-2 x2; ice 4-1-0 x2; glue 0-2-4 x2; 6x boomerang 0-2-4 | map-wide or mirrored (Carpet/SotF/PoD/Ace) | [link](https://www.youtube.com/watch?v=FgmIs2s7cL0) |
| Mushroom Grotto | Advanced | Sauda | 2 mermonkeys + darts 0-3-0 early; snipers 2-0-5/0-5-2/5-2-0; Boomerang 5-0-2; village 3-2-0; alch 4-2-0; glue 0-2-4 | buy all 5 mushrooms (~$1,400) by R36 | [link](https://www.youtube.com/watch?v=hO9LkFVka6M) |
| Ascent | Advanced | Obyn | Wizard 4-0-2, 2 subs, Druid 2-5-0 SotF, Village 2-3-0, Heli 2-0-5 (or Sub 2-5-0) | - | [link](https://www.youtube.com/watch?v=KEmm-iPaHl0) |
| Ship Capture | Advanced | Obyn | 2 Desperado (4-2-0), 2 Skywarden, Druid 1-5-0 SotF, Spike 2-0-5 (set target), Mermonkey 4-x-x, Village, Glue 0-2-4, 3x MOAB Press, Alch 3-0-1 | - (exit Perma-Spike targeted between lanes) | [link](https://dq7reimagined.com/btd6/ship-capture-chimps/) |
| Muddy Puddles | Expert | Psi | Boat 5-0-2 (mid pond), Adv-Intel subs 2-0-5/2-0-4/2-5-0, sniper 1-0-1, desperados, Alch 3-2-0, Village 2-0-2 | Advanced Intel subs / global towers | [link](https://www.youtube.com/watch?v=gJLFvkHiOBk) |
| #Ouch | Expert | Admiral Brickell | Adv-Intel subs, Boat 5-2-0 + Pirate Lord 2-5-0, Alch 4-2-0, Village 4-2-0, Glue Storm 0-5-2, First Strike | centre pond water towers (or drain + Grandmaster Ninja) | [link](https://www.youtube.com/watch?v=ZAEURMORvUc) |
| Dark Castle | Expert | Obyn | 7 druids (6 Poplust 0-1-4 -> Avatar 0-1-5, 4-0-2), Alch 5-0-1, Village 2-0-2, sniper 0-2-1 | - | [link](https://www.youtube.com/watch?v=YUR_SIL0trE) |
| Quad | Expert | Psi | Snipers 2-0-5 + 0-5-2 + 5-2-0, Wizard 1-0-5 PoD, Druid 2-3-0, Sub 2-0-2, Villages, Alch 4-0-0/3-2-0, Glue 0-2-4 | global snipers / PoD (or spike factories at both killzones) | [link](https://www.youtube.com/watch?v=Q2IEAOx5pVo) |
| Workshop | Expert | Sauda | Spike 2-0-5 + 4-2-0 at exit, Druid 1-3-0, Tack 2-0-5, Village 2-0-2/4-0-2, Alch 4-2-0 x2, Glue 0-2-4, Ice 5-2-0 | Spike Factory at the exit | [link](https://www.youtube.com/watch?v=e2jZofvcaNQ) |
| Bloody Puddles | Expert | Quincy (or Striker Jones) | 2 desperados + snipers (0-5-2, 2-0-5, 4-x-x Maim, 0-3-2), Airburst sub 2-0-3, Alch 4-2-0/4-0-1, Villages | global snipers + Advanced-Intel/Airburst subs | [link](https://www.youtube.com/watch?v=oCsimreEU1k) |
| Infernal | Expert | Quincy | Sub 2-0-2, Heli 5-0-2 Apache Prime + Alch 4-2-0 + Village 2-2-0 (side island), Wizard 5-0-2, extra Alch 4-2-0 x2 | long-range dual-lane towers (heli/snipers) | [link](https://www.youtube.com/watch?v=bJHJBN9QHmI) |
| Flooded Valley | Expert | Silas | 2x Sub 0-0-0, Mermonkey 4-0-2 (LotA locked), Buccaneer 5-2-0 Carrier Flagship, Village 4-2-0, Ice 5-2-0 + 0-5-2, Engineer 5-0-2 | water towers (Sub/Mermonkey/Buccaneer) | [link](https://bloon.games/how-to-beat-chimps-on-flooded-valley/) |
| Ravine | Expert | Ezili | darts 0-3-0, Druid 1-3-0 + 3-0-0, Spiked Balls 3-0-2/4-0-2 (Smart), Wizard 2-0-5 PoD, Bombs 4-2-0, Boomerang 0-2-5, Ninja 0-4-0 | sword (R6-R7) + wall-ignoring DPS (Druid vines/PoD/Sky Shredder) | [link](https://www.youtube.com/watch?v=JtP8VQc5Leo) |
| Sanctuary | Expert | Obyn Greenfoot | 2x Desperado, Snipers 1-0-2/0-2-2 (Strong), Wizard 5-0-2 Archmage, Perma-Spike + Alch 4-x-x + Village 0-0-2 on bottom-middle platform | infinite-range/seeking towers + Perma-Spike (Set Target) on bottom-middle platform | [link](https://www.youtube.com/watch?v=auCq92xN0nk) |
| Dark Dungeons | Expert | Silas | darts 0-3-2/0-3-0 + 3x Juggernaut 4-0-2, Spikes 1-0-4 at 3 exits, Glue 2-1-0, Ice 5-2-0, Tack 2-0-5 + 2-0-4, Mermonkey 3-0-1/4-0-1, Alch/Village | - (per-room + exit spikes; ledge bypass optional: Perma-Spike/Archmage/Arctic Knight) | [link](https://www.youtube.com/watch?v=wqGrbHhDv3U) |
| Glacial Trail | Expert | Silas | Ice 5-2-0 + 2x Ice 0-2-4, Spike 2-0-5 Perma-Spike (Smart) + Spike 2-5-0 Carpet, Dart + Ninja 1-0-0 start | - (freeze-immune Ice/Silas strongly preferred) | [link](https://www.youtube.com/watch?v=Hv8M3AOfwS0) |
| Tricky Tracks | Expert | Etienne | 3 darts, 6 Mermonkeys (2x 4-0-2, rest 0-0-2), Boomerang 4-0-2 + 0-2-4, Village 4-0-2, 5x Tack 2-0-4, Engineer 5-0-0, Ice 5-2-0, Ninja 0-4-0, Glue 0-2-4 + 2-4-0 | - (Etienne range buff; between-track strips) | [link](https://www.youtube.com/watch?v=fWry_CuR6GI) |
