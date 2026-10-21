# BTD6 (v57, PC) UI flows for a screen bot: research notes

Sources: web research done 2026-10-21, plus the bot's own live captures in `docs/screens/` (960x600, 16:10).
Coordinates are fractions of the game frame (x, y), measured from our 960x600 captures unless they say otherwise.
Fractions taken from other bots were measured on 16:9 frames: `btd6-ahk` used 1920x1080 and `btd6farmer` used normalized 16:9. They are approximate on our 16:10 frame, so use them as search regions, not blind clicks.
Tags: **[OBS]** seen in our own screenshots. **[SRC]** has a web or code source. **[UNV]** is unverified, inferred, or from memory, so confirm it live.

Bot code consulted (these are good template and flow references):
- linus-jansson/btd6farmer: `src/Bot.py`, `src/static.py` (normalized button table) https://github.com/linus-jansson/btd6farmer
- piweiblen/BloonsPlayer: `src/player.py`, image folders `buttons/`, `edge cases/`, `heroes/` https://github.com/piweiblen/BloonsPlayer
- m00rex/btd6-ahk: `main.ahk`, `img/states/*` (`home`, `map_selection`, `in_game`, `level_up`, `victory`, `victory_menu`, `defeat`, `overwrite`, `collect`, `event`) https://github.com/m00rex/btd6-ahk

The fandom and bloonswiki sites block direct fetches (403/402). The bloonswiki pages cited below were read through the `r.jina.ai/<url>` reader proxy.

---

## 0. Screens already captured (layout reference)

| Screen | Key elements (x, y) |
|---|---|
| Main menu (`after_home.jpg`) [OBS] | Bottom row: MONKEYS (.13,.93), HEROES (.25,.93), Legends (.37,.93), PLAY (.50,.92), PLAY SOCIAL (.63,.93), INSTAS + POWERS (.75,.93), KNOWLEDGE (.87,.93). Top-left: profile (.04,.06), level star plus XP bar "1,830/4,250" (.11-.30,.05), envelope/inbox with "!" (.34,.05). Top-right: Monkey Money "$175" with a "+" (.97,.05); the "+" opens the real-money shop, so the bot must not click it. Left column: settings gear (.045,.19), quests/achievements with "!" (.06,.29), shop "SOLD" (.05,.40), trophy/event icon (.05,.53), exit (.03,.92). Scene props: black coffin (.27,.60), TV (.14,.55), red gift box (.60,.57), witch monkey (.77,.55), monkey holding a scroll with a green arrow (.40,.60). "New" ribbons over Heroes, Legends and Instas. |
| Map select (`search.jpg`, `search2.jpg`) [OBS] | Back (.04,.05). Search toggle (.045,.15). Search box "Search..." (.52,.04). Red X to clear search (.325,.04). Candy icon (.68,.04), which is the Halloween collection-event item and probably a bonus-map filter [UNV]. FRIENDS (.96,.06). Page arrows (.10,.40) and (.90,.40). 3x2 map grid, card centres (.255,.30) (.50,.30) (.745,.30) (.255,.59) (.50,.59) (.745,.59) with map name above each card. Page dots (.5,.77). CHANGE HERO with hero portrait (.06,.93). A locked map shows a padlock on its thumbnail (Dark Castle). |
| Level up (`levelup.jpg`) [OBS] | Dark purple star background, star with level number and a "LEVEL UP!" ribbon at the centre (.5,.45). Monkey mascot bottom-left. No button: click anywhere or press Space/Esc to continue. |
| Tower choice (`levelup2.jpg`) [OBS] | Banner "PRIMARY MONKEYS" (it changes with the category), subtitle "CHOOSE A MONKEY TO UNLOCK". Horizontal carousel of towers with the selected one in the centre (.5,.45). Name (.5,.79), description (.5,.85), green UNLOCK (.5,.94). Clicking a side tower rotates the carousel. [SRC] says levels that unlock a non-hero tower offer "a choice of which tower to unlock from one of the four main tower categories" (bloonswiki Bloons TD 6 page, search snippet). |
| Upgrade tree (`upgrade_tree.jpg`) [OBS] | See section 3. |
| Victory card (`victory.jpg`) [OBS] | "VICTORY" ribbon, player card with accolade (for example "MASTER BUILDER / 16 Towers Placed"), stats list, level/XP strip, green **Next** (.50,.84). |
| Victory rewards (`victory2.jpg`) [OBS] | "Congratulations! You completed this track on: Easy", "REWARDS:" row (candy event item ×1, Monkey Money 75). Buttons: **Home** (.36,.78), **Review Map** (.50,.78), **Freeplay** (.64,.78). |

---

## 1. Heroes

**Unlock levels and Monkey Money prices.** Sources: [bloonswiki Level table](https://www.bloonswiki.com/Level) via jina, and [switchbladegaming 2026 hero list](https://www.switchbladegaming.com/bloons-td-6/best-heroes-and-strategy-2026/).

| Hero | Becomes available at player level | Monkey Money price |
|---|---|---|
| Quincy | start (tutorial) | free |
| Gwendolin | 14 | **free unlock** at level 14 |
| Captain Churchill | 15 | 2,500 |
| Benjamin | 15 | 3,000 |
| Pat Fusty | 15 | 3,000 |
| Striker Jones | 21 | **free unlock** at level 21 |
| Ezili | 25 | 3,000 |
| Adora, Sauda, Etienne, Rosalia, Silas | 25 | 5,000 each |
| Obyn Greenfoot | 28 | **free unlock** at level 28. Level 28 can only be bypassed with a paid pack; ignore that. |
| Admiral Brickell, Psi | 35 | 5,000 |
| Geraldo, Corvus | 35 | 7,000 |
| Dan D'Monke | ? | 7,000 [UNV] |

In-game placement costs on Medium: Quincy $540, Gwendolin $725, Striker $700, Obyn $650, Churchill $2,000, Benjamin $1,200. Gwendolin is $615 on Easy and $870 on Impoppable. The Hero Favors knowledge takes 10% off.

**Heroes screen.** Open it from main menu HEROES (.25,.93) or from CHANGE HERO.
- Layout [SRC btd6farmer `static.py`, 2023 layout]: left-side grid of hero portraits, 3 columns at x≈.04/.12/.20, rows at y≈.16/.37/.58/.79/.93. With 19+ heroes the grid now scrolls [UNV]. Click a portrait, then the **Select** button (btd6farmer `CONFIRM_HERO` ≈(.59,.57)), then press **Esc** or the back arrow to leave.
- BloonsPlayer does the same thing: it clicks the hero portrait template, waits up to 2 s for the `select` template, clicks it, then presses Escape.
- Hero portrait templates differ per skin. BloonsPlayer keeps `<hero> 1..3.png` for each hero.
- [UNV] A hero that is owned but not selected shows a green "Select" button. The current hero probably shows "Selected" or no button. An unowned hero that is purchasable shows a price button with a Monkey Money icon, which opens a confirm dialog. A hero not yet available shows a lock with "Unlocks at level N". Skins appear as a row of small portraits. Before clicking anything, OCR the button text and click it only if it reads "Select".
- **Change Hero** flow [OBS button and SRC BloonsPlayer]: CHANGE HERO sits bottom-left (.06,.93) on the map-select screen. BloonsPlayer also uses it from the difficulty screen (its "inner" hero menu, used when the difficulty button is visible). It opens the same hero picker: click the portrait, click Select, press Esc, and the bot is back on map select or difficulty with the new portrait shown. The selected hero is global, not per map.

---

## 2. Monkey Knowledge (MK)

Rules [SRC: bloonswiki MK pages via jina, basicallyaverage.com/monkey-knowledge-btd6, gamerant]:
- MK unlocks at **level 30**. Level 30 itself gives 1 MK point, and every later level gives 1 point **except levels 33 and 36, which give 200 Monkey Money instead**. Achievements can also award points.
- Six trees, opened from the main menu KNOWLEDGE button (.87,.93): **Primary, Military, Magic, Support, Heroes, Powers**.
- A node needs its connected parent node(s). Whether a node with two parents needs one or both is **[UNV]**, so the bot should read the node's locked or available state rather than assume.
- Tier gates: tier 3 and above need N points already invested in *that tree*. Gates seen: Primary T3=5, T4=8, T5=10, T6=10; Military T3=4, T4=8, T5=8, T6=14, T7=14; Support T3=3, T4=3, T5=8, T6=14; Heroes T3=3, T4=3, T5=8, T6=8; Magic T5=8, T6=8. The Magic T3/T4 and Powers numbers are uncertain.
- Monkey Money cost, paid only the first time: T1-3 free, **T4 250, T5 500, T6/T7 1,000**. A respec costs **2,000 MM** and refunds points; Monkey Money already paid is kept, so re-buying a node later costs only the point.
- MK can be toggled off. It never applies in **CHIMPS**.
- The purchase UI (click node, info panel, "Unlock"-style button) is **[UNV]**. Template-match it live.

Current tree layout ([bloonswiki Template:BTD6 mk nav](https://www.bloonswiki.com/Template:BTD6_mk_nav)):
- **Primary**: T1 Fast Tack Attacks, Increased Lifespan, Extra Dart Pops / T2 Poppy Blades, Hard Tacks, Fast Glue, Fraggy Frags, Cheap 'Rangs, Crossbow Reach / T3 Big Inferno, Icy Chill, More Splatty Glue, Budget Clusters, Recurring 'Rangs, Extra Bounce, 4 and 4, Force vs Force / T4 So... Cold..., Aviation Grade Glue, Mega Mauler, Hard Press, Master Double Cross / T5 Big Cryo Blast, Hypothermia, Cheaper Solution, Violent Impact, Bionic Augmentation, Long Turbo, Come On Everybody! / T6 Bonus Glue Gunner, **More Cash**, **Bonus Monkey!**
- **Military**: T1 Naval Upgrades, Airforce Upgrades, **Elite Military Training**, Emergency Unlock / T2 Big Bunch, Accelerated Aerodarts, Ceramic Shock / T3 Breaking Ballistic, Faster Takedowns, Targeted Pineapples, Rapid Razors, Extra Burny Stuff, Cheaper Maiming, Gorgon Storm / T4 Quad Burst, Trade Agreements, Gun Coolant, Paint Stripper, Cross the Streams / T5 Flanking Maneuvers, Wingmonkey, Aeronautic Subsidy, Charged Chinooks, Budget Battery, Master Defender / T6 Sub Admiral, Military Conscription, Advanced Logistics, Door Gunner / T7 **Big Bloon Sabotage**
- **Magic**: T1 SUPER Range, Lingering Magic, Magic Tricks / T2 Cheaper Doubles, Heavy Knockback, Hot Magic, Speedy Brewing, **Mo' Monkey Money** / T3 Diversion Tactics, Strike Down the False, Warm Oak, Flame Jet, Strong Tonic / T4 X-ray Ultra, Cold Front, Arcane Impale, Acid Stability / T5 Deadly Tranquility, There Can Be Only One, Vine Rupture / T6 Tiny Tornadoes, Mana Shield
- **Support**: T1 Flat Pack Buildings, One More Spike / T2 Insider Trades, More Valuable Bananas, First Last Line of Defense / T3 Bigger Banks, Farm Subsidy, Vigilant Sentries, **Monkey Education** / T4 Backroom Deals, Inland Revenue Streams, Thicker Foams, Very Shreddy, To ARMS! / T5 Better Sell Deals, Healthy Bananas, Big Traps, Hi-Value Mines, Veteran Monkey Training, Global Ability Cooldowns / T6 Bank Deposits, Paragon of Power
- **Heroes**: T1 Heroic Reach, More 'Splody, Ability Discipline / T2 Heroic Velocity, Scholarships / T3 Quick Hands, **Self Taught Heroes**, Ability Mastery / T4 Hero Favors / T5 Empowered Heroes, Big Bloon Blueprints / T6 Monkeys Together Strong, Weak Point
- **Powers**: T1 Bigger Camo Trap, Just One More, Cheaper Lakes / T2 Mauling MOAB Mines, Longer Time Stop, Budget Pontoons / T3 Supersize Glue Trap, Longer Boosts, Powerful Monkey Storm / T4 Ambush Tech, Pre-game Prep, Fit Farmers / T5 Budget Cash Drops, Supa-Thrive / T6 Grand Prix Spree

Verified chains (bloonswiki per-node pages):
- **Mo' Monkey Money** (+10% Monkey Money from wins with MK enabled, rounded down; also applies to Daily Challenges): Magic Tricks → Speedy Brewing → Mo' Monkey Money. All free, 3 points total.
- **Monkey Education** (+8% XP for towers and heroes): Support T3, free, needs 3 points invested in Support. Its parent node is [UNV]: the wiki lists none, so it is probably a T2 Support node.
- Support economy: Flat Pack Buildings → More Valuable Bananas → **Farm Subsidy** (first Banana Farm $100 cheaper) → Inland Revenue Streams (250). Flat Pack Buildings → Insider Trades → Bigger Banks.
- **Self Taught Heroes** (+10% hero XP): More 'Splody → Scholarships (hero levels 10% cheaper to buy) → Self Taught Heroes (T3, 3 invested). Heroic Reach → Heroic Velocity → Quick Hands. **Hero Favors** (heroes 10% cheaper) needs both Quick Hands and Self Taught Heroes and costs 250 MM.
- **More Cash** (+$200 starting cash; +$100 on Half Cash; Deflation starts with $20,200; not in CHIMPS): Extra Dart Pops → Crossbow Reach → 4 and 4 (5 invested) → Master Double Cross (8 invested, 250) → Come On Everybody! (10 invested, 500) → **Bonus Monkey!** (free Dart Monkey at the start of each game; 10 invested, 1,000) → **More Cash** (10 invested, 1,000; the wiki also lists Bonus Glue Gunner as a parent). That is 10 Primary points and 2,750 MM.
- **Elite Military Training**: Military T1, free. Gamerant says it gives a one-time 1,000 XP to each military tower and then +5% XP [UNV numbers].
- **Big Bloon Sabotage** (-10% MOAB-class health, bosses excluded; T7, 14 invested, 1,000) needs Sub Admiral **and** Master Defender:
  - Sub Admiral (T6, 14 invested, 1,000) ← Flanking Maneuvers (500) ← Quad Burst (250, ← Breaking Ballistic ← Naval Upgrades) **and** Trade Agreements (250, ← Faster Takedowns ← Big Bunch ← Naval Upgrades).
  - Master Defender (500) ← Cheaper Maiming ← Ceramic Shock ← Elite Military Training.
  - Total is about 14 Military points and roughly 3,500 MM.

### Recommended MK purchase order for a farming bot (Easy/Standard runs, Monkey Money and XP focus)
1. Magic Tricks → Speedy Brewing → **Mo' Monkey Money** (points 1-3, free).
2. Flat Pack Buildings → More Valuable Bananas → **Monkey Education** (points 4-6, free; add Insider Trades if Monkey Education's parent is Insider Trades).
3. **Elite Military Training** (point 7, free; one-time XP for military towers).
4. More 'Splody → Scholarships → **Self Taught Heroes** (points 8-10, free; hero XP).
5. Primary toward **More Cash**: Extra Dart Pops, Crossbow Reach, Fast Tack Attacks, Increased Lifespan, Hard Tacks/Fast Glue (fillers to reach 5), 4 and 4, filler, Master Double Cross (250), filler to reach 10, Come On Everybody! (500), **Bonus Monkey!** (1,000), **More Cash** (1,000). Bonus Monkey! is a free Dart Monkey every game, which is useful for an Easy bot.
6. Farm Subsidy (only if the strategies use farms), then Heroic Reach → Heroic Velocity → Quick Hands → **Hero Favors** (250).
7. Late game: the **Big Bloon Sabotage** chain, Better Sell Deals (Support T5, 500), Pre-game Prep (Powers T4).

Alternatives with no web consensus: mobilegamemaster ranks More Cash and Bonus Monkey first, and basicallyaverage puts Mo' Monkey Money first. For a Monkey Money farmer, Mo' Monkey Money comes first because it is cheap and its gain compounds.

---

## 3. Monkeys-menu upgrade tree

- Seen in `upgrade_tree.jpg` [OBS]:
  - Back arrow (.04,.05). Header shows the tower name ("TACK SHOOTER") and "XP: 704" with an orange "+" (.70,.04), with yellow **prev/next arrows** at (.20,.06) and (.80,.06). The arrows cycle through towers.
  - Description line (.5,.10).
  - A 3x5 grid of upgrade icons, one row per path, with names under each icon. Owned icons are green, available ones are grey-green, and locked tier 5 icons are stone faces. A lightning badge marks paragon or power-related tiers.
  - Left panel: the selected upgrade's name and art, a green **"UNLOCK FOR: 550 XP"** button (.14,.41), and "Ingame cost 190".
  - Bottom-right: **"UNLOCK ALL / Applies to this Monkey only."** (.90,.57). This is a **real-money purchase and the bot must never click it.** Treat the "+" next to XP as unsafe too: it opens an XP or Monkey Money purchase/transfer dialog [UNV].
- How to reach it:
  - From the main menu: MONKEYS (.13,.93) → tower grid grouped by category (Primary/Military/Magic/Support) → click a tower → this screen [UNV for the grid layout].
  - In game: the green **UPGRADES** button at the top of the tower panel (.93,.08), seen in `victory.jpg`, opens the same screen [UNV that it is pixel-identical, but the header, grid and Unlock button style match].
- Switching towers: the top arrows cycle through all towers in menu order, wrapping across categories [UNV for wrap]. Read the header name with OCR after each click.
- XP is earned per tower at the end of each round, by the towers placed. Monkey Education and Elite Military Training boost it. An "UNLOCK FOR" button is greyed or unaffordable when XP is too low [UNV].

---

## 4. Level-up popups

- Order [OBS and SRC]: the round ends, the game pauses, and **"LEVEL UP!"** appears with the level number. Click or press Space to continue, then the reward screens appear. The level-up can fire mid-game, and in btd6-ahk's README it is the #1 cause of a stuck bot.
- What each bot does:
  - btd6farmer clicks screen centre (.5,.5) three times on `levelup` or `instamonkey`, and once on `monkey_knowledge`.
  - BloonsPlayer clicks the `LEVEL UP` template, waits up to 10 s for a `monkey knowledge` popup and clicks it, then presses Space twice.
  - Avoid the Space approach mid-game: Space also starts rounds and toggles fast-forward.
- Rewards by level ([bloonswiki Level](https://www.bloonswiki.com/Level)):
  - Levels 2-6: choose a Primary tower. Levels 7-12: choose a Military tower (Dartling excluded). Levels 15-17 and 19-20: Magic tower. Levels 22-24 and 26: Support tower (Beast Handler excluded). Each of these shows the "<CATEGORY> MONKEYS / CHOOSE A MONKEY TO UNLOCK" carousel with an UNLOCK button.
  - Hero unlocks: **14 Gwendolin**, **21 Striker Jones**, **28 Obyn Greenfoot** (free). Hero shop availability: 15 (Churchill, Benjamin, Pat), 25 (Ezili, Adora, Sauda, Etienne, Rosalia, Silas), 35 (Brickell, Psi, Geraldo, Corvus). Hero-unlock reward screen text is [UNV], so dismiss it by clicking the centre or the green button if one is present.
  - Monkey Money: 50 at levels 13, 18, 25, 27, 29, and 200 at 33 and 36.
  - Level 20: Events. Level 30: **Monkey Knowledge** (first point, plus a "Monkey Knowledge unlocked" popup), Contested Territory, Boss Rush, **Gift Box**. Level 50: Map Editor. Levels 10/20/30/50 add quest slots and Martian Games.
- **Gift Box** (red box on the main menu, works from level 30): Dartling, Beast Handler and Mermonkey need 3M pops each; Desperado and Skywarden need 3.5M each. When a tower is ready, the box "shines and bounces". Opening an upgrade screen for that tower then shows "You have unlocked this tower! Collect it from the Gift Box on the Main Menu!" Click the box to play the unlock animation. ([bloonswiki Gift Box](https://www.bloonswiki.com/Gift_Box))
- Other in-game popups:
  - Insta Monkey reward when round 100 is beaten.
  - Achievement and quest toasts, which are non-blocking [UNV].

---

## 5. End of game

**Victory** [OBS and SRC]:
1. The "VICTORY" stats card appears, with **Next** at (.50,.84). btd6farmer's `VICTORY_CONTINUE` (.50,.84) matches.
2. The rewards panel appears with "Congratulations! You completed this track on: <Difficulty>" and a "REWARDS:" row. The row shows the collection-event item and count during events, Monkey Money, and an Insta Monkey or trophies where they apply.
   - Buttons: **Home** (.36,.78), **Review Map** (.50,.78), **Freeplay** (.64,.78). btd6farmer has `VICTORY_HOME` (.367,.781) and `FREEPLAY` (.629,.772).
3. **Home** leads to a loading screen. btd6farmer treats it as loading while more than half the pixels are black.
4. If a collection event is active, btd6-ahk and BloonsPlayer next detect a **"collect"** state, the event screen with a **Collect** button:
   - btd6farmer `EASTER_COLLECTION` (.50,.63).
   - Then the crate opens and shows 2-3 (up to 5) Insta Monkey cards in a row at y≈.50. btd6farmer has 5 x-slots: .34, .42, .50, .58, .66. btd6-ahk uses 1080p x-values .356, .467, .620. Click each card to reveal it.
   - Then **Continue** (.50,.86-.92), then back on the event screen, then **back arrow** top-left (.04,.06) or the event's Play button to leave.
   - BloonsPlayer loops clicking `cont`, `reward`, `insta-monkey` and the coloured `insta monkey` templates until `back` is clicked.
   - Whether this screen opens automatically after Home or from a menu icon is [UNV]. Handle it as a state that can appear at any time.
   - Crate tiers ([bloonswiki Collection Event](https://www.bloonswiki.com/Collection_Event_(BTD6))): Wooden (20 items), Bronze (30), Silver (40), Gold (50), Diamond (70). The tier rises with lifetime items collected in the event (100/250/450/1,000).
   - Featured Instas can be pre-selected (btd6-ahk `img/featured/*`).
- Monkey Money observed: 75 for Monkey Meadow (Beginner) on Easy [OBS]. Repeat clears of the same map and difficulty pay **20%** of the first reward [SRC bloonswiki]. The exact table is [UNV].

**Defeat** [SRC btd6farmer coordinates and BloonsPlayer templates; labels UNV]:
- The "DEFEAT" banner appears with a row of buttons at y≈.75.
- Normal modes have 4 buttons: **Home** (.29), **Restart** (.43), then probably **Review Map** (.57) and a green **Continue** (.71). Continue costs Monkey Money, about 100-500 and rising with round; the first continue ever is free since v23. Continue is the paid option, so the bot must never click it.
- **CHIMPS and Deflation** have no Continue, so the row has 3 buttons: Home (.36), Restart (.50), and a third at (.64), probably Review Map or "Retry Last Round" [UNV].
- In CHIMPS, Continue is replaced by **"Retry Last Round"**. Using it, or exiting mid-game, gives the red rather than black CHIMPS medal. Deflation has no continues.
- **Restart** opens a confirm dialog: **OK** on the right ≈(.59,.67), Cancel on the left [SRC btd6farmer `RESTART_CONFIRM`].
- To restart after a victory, btd6farmer does: Next → Freeplay → Esc → Esc (opens the pause menu) → Restart (.55,.76) → confirm (.59,.67).
- The pause menu's Home is at ≈(.44,.79) [SRC `QUIT_HOME`].

**Existing save, "Overwrite"** [SRC: fandom Known Bugs says choosing difficulty and mode "will ask the player if you want to overwrite the player's saved game"; btd6-ahk `states/overwrite.png` and `buttons/ok_overwrite.png`; BloonsPlayer `edge cases/overwrite`]:
- Each map has one save. After you click Difficulty and then Mode, a confirm dialog appears with **OK** on the right ≈(.59,.68) [SRC btd6farmer `OVERWRITE_SAVE`] and Cancel on the left.
- The **exact wording is [UNV]**. Match on OCR "overwrite" or "save", or on the dialog template.
- btd6-ahk clicks OK only when its config allows it, and otherwise stops so the save is kept.

---

## 6. Main-menu popups on login

The wiki and web sources barely document these, so everything below is [UNV] except where marked.
- **Daily reward chest**: a treasure chest in the main menu scene, collectable once per UTC day. Missing a day does not reset the streak. There are 50 reward days that loop: day 1 is 50 MM, day 2 a Cash Drop, day 3 a T1 Insta, and so on [SRC bloonswiki Daily Reward].
  - btd6-ahk looks for `buttons/chest` in a small box at 1080p (563-588, 639-664) ≈ (.30,.60), clicks it, waits 3 s, then clicks `close_chest` at about (.30,.36).
  - In our Halloween capture the object at (.27,.60) is a **black coffin**, which is very likely the seasonal skin of the chest [UNV].
  - Clicking it shows the reward. Close with the button or X, or press Esc.
- **News / What's New**: after an update, a news panel or video can open. Close it with the X top-right, or press Esc. The **TV** prop (.14,.55) is likely the news/videos entry point [UNV].
- **Event popups** (Race, Boss, Odyssey, Contested Territory, collection-event intro): a modal with an event banner and an X or "OK". Esc usually closes it.
- **Collection event**: the event icon on the main menu or left column, and the map-select candy icon. Handle the Collect and crates flow as in section 5.
- **Inbox/envelope** (.34,.05) with "!": gifts or compensation. Optional; the bot can ignore it.
- **Quests** "!" (.06,.29) and **Trophy Store** (left column): optional; the bot can ignore them.
- **Rate prompt**: on PC/Steam it is unlikely or rare. If it appears, close it with "Later", "No" or the X.
- **Level-up** can also appear on the main menu.
- **Gift Box ready**: the box bounces. This is optional and does not block the menu.
- Generic dismiss strategy, used by every reference bot: try **Esc**. If the screen did not change, click a detected X, OK, Continue or Back template. Never click anything showing a currency price, "$", "UNLOCK ALL", "Buy" or the "+" next to Monkey Money.

---

## 7. Map-select medals and the bonus sticker

- Each map card has **4 large medal slots under the thumbnail = Easy, Medium, Hard, Impoppable** [SRC Steam: "4th slot is where the medals for Impoppable and CHIMPs go"]. A small CHIMPS medal attaches to the 4th: **red** for a normal clear, **black** for a clear in one session without exiting or using Retry Last Round [SRC bloonswiki Medal].
- An empty slot is a flat tan medal silhouette [OBS]. A filled slot is a coloured medal. Our Monkey Meadow Easy medal is blue-centred with an orange ribbon [OBS].
- Small star pips under and between the slots [OBS] are most likely per-mode completion marks [UNV]: Easy has Standard, Primary Only and Deflation; Medium has Standard, Military Only, Apopalypse and Reverse; Hard has Standard, Magic Monkeys Only, Double HP MOABs, Half Cash and Alternate Bloons Rounds; Impoppable and CHIMPS are on the 4th slot. Tan pips mean not done; coloured pips mean done.
- **Border colour** of the card: Bronze when all Easy modes are done, Silver when all Easy and Medium are done, Gold when all through Hard plus Impoppable and CHIMPS are done, Black when all are done and CHIMPS is black. A second medal row exists for co-op [SRC Steam threads and bloonswiki Map].
- Reading completion: sample the 4 slot centres. Under our 960x600 Monkey Meadow card, slots are at (.18,.41), (.23,.41), (.28,.41), (.33,.41). Tan or brown means empty; a saturated colour means earned.
- **Bonus reward sticker**: during a collection event, one random map per difficulty tier shows a **"BONUS REWARDS"** icon on its thumbnail. It pays far more event items, for example Expert Easy gives 12 instead of 4. The sticker moves after you finish that map and every 8 hours [SRC bloonswiki Collection Event]. The candy button by the search bar probably filters to these maps [UNV].
- Mode unlocks (singleplayer):
  - Primary Only → Deflation.
  - Military Only → Apopalypse. Reverse needs Medium Standard [UNV].
  - Hard Standard → Magic Only and Double HP MOABs. Double HP MOABs → Half Cash. Alternate Bloons Rounds → Impoppable → CHIMPS.

---

## 8. Special-mode start popups

| Mode | Popup text and buttons | Rules |
|---|---|---|
| **Apopalypse** (Medium) | A rules screen with its own **Play** button. BloonsPlayer waits until `apop play` stops moving, then clicks it. Description: "Ever increasing Bloon waves, no breaks at the end of each round." | Rounds run back to back. Only one Space is needed to start; btd6farmer presses Esc after loading. |
| **Deflation** (Easy) | An info dialog with an **OK** button at about (.50,.70) [SRC btd6farmer `OK_MIDDLE`, BloonsPlayer waits for `buttons ok`]. "Start at round 31 with 20,000 cash, but you can't earn any more." | Rounds 31-60. No income, no continues. Selling still refunds. |
| **Half Cash** (Hard) | Dialog with OK [SRC btd6farmer handles it with Esc]. "Half starting cash, end of round cash, and all income generation. ALERT: also half from Cash Drop and Continue!" | |
| **Impoppable** | Dialog with OK [SRC BloonsPlayer/btd6farmer]. Text [UNV]. | Starts at round 6, ends at 100. Higher prices. |
| **CHIMPS** (Hard) | Dialog with OK, centre ≈(.50,.68) [SRC btd6farmer `CONFIRM_CHIMPS`]. "The true test of a BTD master. No Continues, Hearts lost, Income, Monkey Knowledge, Powers or Selling." | Rounds 6-100. One life. No MK. Retry Last Round instead of Continue. |
| **Sandbox** | Dialog with OK [SRC]. | |
| Primary Only, Military Only, Magic Only, Reverse, Double HP MOABs, Alternate Bloons Rounds, Standard | No popup expected [UNV]. Neither reference bot handles one. | |

All three reference bots dismiss these with **OK or Esc** after the loading screen ends, then press Space to start, and Space again for fast-forward. A dialog showing a Monkey Money cost (Continue, hero boost, power purchase) must never be confirmed.

---

### Open items to verify live
1. Exact overwrite dialog text and button labels.
2. Defeat button labels and their order on the 16:10 frame.
3. Heroes screen layout in v57: Select/Selected text, scroll, purchase-confirm dialog.
4. Whether the collection crate screen opens automatically after Home.
5. Monkey Education's parent node, and whether MK nodes with two parents need one or both.
6. What the star pips under the medals mean.
7. Which main-menu props are the daily chest (coffin?) and the news TV.
