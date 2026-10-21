"""Static Bloons TD 6 tower / hero / progression data for the bot (target: v57.x, Oct 2026).

Pure data plus a few tiny helpers; no external dependencies.

Sources
-------
* Base + upgrade cash costs (Medium): cyberquincy ``jsons/costs.json``
  (github.com/hemisemidemipresent/cyberquincy, auto-fetched, last updated 2026-08-30 = v56.x),
  then patched with the official v57.0 Steam patch notes
  (steamcommunity.com/app/960090/announcements):
    Glue Splatter 970->650, Glue Strike 4000->4500,
    Skywarden: Aerial Attunement 110->140, Zephyr Sense 215->175, Wind Weaver 1650->1200,
    Galesage 3300->3000, Galvanic Conduit 1800->2500, Thunder's Decree 2000->3500,
    Stormwrath Archon 35000->32000.
  v56 changes (More Tacks/Even More Tacks 150, Even Faster Shooting 220, Snowstorm 4750,
  Pirate Lord 29000) were already present in the cyberquincy data.
* Upgrade names: cyberquincy ``jsons/tower_pages.json``.
* Hero base costs: cyberquincy ``jsons/heroes.json`` (18 heroes incl. Silas v50, Dan D'Monke v55).
* Skywarden (v56): bloonswiki.com / bloons.fandom.com search snippets (Magic class, range 48,
  gift box 3.5M pops, XP for some upgrades).
* Round XP formula + map multipliers: bloonswiki "Experience" / Fandom "Experience Points".
* Difficulty multipliers / rounding: checked against several published Easy/Hard/Impoppable
  price rows (e.g. Skywarden 175/205/220/245, Galesage 2550/3000/3240/3600).

Everything not directly confirmed is marked with ``# ?``.  In particular:
* upgrade ``xp`` values are mostly per-tier *estimates* (``xp_exact`` False) - only a few
  Skywarden values were found;
* ranges, footprints, hero ranges, hero Monkey-Money prices / unlock levels and most hero
  ability cooldowns are from memory;
* PLAYER_LEVEL_XP is best effort (reading the level off-screen is more reliable).
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Difficulty pricing
# ---------------------------------------------------------------------------

DIFFICULTY_COST_MULT = {"easy": 0.85, "medium": 1.0, "hard": 1.08, "impoppable": 1.2}


def price(base: int, difficulty: str = "medium", discount: float = 0.0) -> int:
    """Price on ``difficulty`` for a Medium ``base`` cost.

    BTD6 multiplies the Medium price and rounds to the nearest $5 (half up).
    ``discount`` (0..1) is applied before rounding (village/MK discounts; approximate).
    """
    mult = DIFFICULTY_COST_MULT[difficulty.lower()]
    raw = base * mult * (1.0 - discount)
    return int(math.floor(raw / 5.0 + 0.5) * 5)


# ---------------------------------------------------------------------------
# Upgrade XP estimates
# ---------------------------------------------------------------------------

# Typical tower-XP needed to unlock an upgrade per tier (rough medians).  # ?
DEFAULT_TIER_XP = {1: 200, 2: 500, 3: 2000, 4: 8000, 5: 40000}  # ?


def _u(tier: int, name: str, cost: int, notes: str = "", xp: int | None = None) -> dict:
    return {
        "name": name,
        "tier": tier,
        "cost": cost,
        "xp": xp if xp is not None else DEFAULT_TIER_XP[tier],
        "xp_exact": xp is not None,
        "notes": notes,
    }


def _path(*ups: tuple) -> list:
    """ups: 5 tuples (name, cost, notes[, xp])."""
    assert len(ups) == 5
    return [_u(i + 1, *u) for i, u in enumerate(ups)]


def _tower(name, category, hotkey, cost, rng, placement, footprint, base_notes, paths):
    return {
        "name": name,
        "category": category,
        "hotkey": hotkey,
        "cost": cost,
        "range": rng,
        "placement": placement,
        "footprint": footprint,
        "base_notes": base_notes,
        "upgrades": paths,
    }


# ---------------------------------------------------------------------------
# Towers (Medium costs, v57)
# range: base range in game units (None = unlimited / map-wide / cursor-aimed)
# footprint: placement radius in game units  # ? (all from memory, approximate)
# ---------------------------------------------------------------------------

TOWERS: dict[str, dict] = {
    # ----------------------------- PRIMARY ---------------------------------
    "dart": _tower(
        "Dart Monkey", "primary", "q", 200, 32, "land", 6,  # footprint ?
        "sharp; no camo; can't pop lead/frozen",
        [
            _path(("Sharp Shots", 140, "+1 pierce"),
                  ("Razor Sharp Shots", 200, "+2 pierce"),
                  ("Spike-o-pult", 320, "big spiked ball"),
                  ("Juggernaut", 1800, "pops lead/frozen, ceramic dmg"),
                  ("Ultra-Juggernaut", 15000, "splitting balls, moab dmg")),
            _path(("Quick Shots", 100, "attack speed"),
                  ("Very Quick Shots", 190, "attack speed"),
                  ("Triple Shot", 450, "3 darts"),
                  ("Super Monkey Fan Club", 7200, "ability"),
                  ("Plasma Monkey Fan Club", 45000, "ability; lead")),
            _path(("Long Range Darts", 90, "range"),
                  ("Enhanced Eyesight", 200, "camo, range"),
                  ("Crossbow", 575, "dmg"),
                  ("Sharp Shooter", 2050, "crits"),
                  ("Crossbow Master", 21500, "strong single target")),
        ]),
    "boomerang": _tower(
        "Boomerang Monkey", "primary", "w", 315, 43, "land", 7,  # footprint ?
        "sharp; no camo; can't pop lead",
        [
            _path(("Improved Rangs", 200, "pierce"),
                  ("Glaives", 280, "pierce"),
                  ("Glaive Ricochet", 600, "bounces"),
                  ("M.O.A.R Glaives", 2000, "pierce/dmg"),
                  ("Glaive Lord", 32500, "orbiting glaives")),
            _path(("Faster Throwing", 175, "attack speed"),
                  ("Faster Rangs", 250, "attack speed"),
                  ("Bionic Boomerang", 1250, "fast, ceramic dmg"),
                  ("Turbo Charge", 4200, "ability"),
                  ("Perma Charge", 35000, "permanent turbo")),
            _path(("Long Range Rangs", 100, "range"),
                  ("Red Hot Rangs", 300, "lead, frozen"),
                  ("Kylie Boomerang", 1300, "straight-line"),
                  ("MOAB Press", 2700, "moab knockback, moab dmg"),
                  ("MOAB Domination", 50000, "moab dmg")),
        ]),
    "bomb": _tower(
        "Bomb Shooter", "primary", "e", 375, 40, "land", 8,  # footprint ?
        "explosion: pops lead; can't pop black/zebra; no camo",
        [
            _path(("Bigger Bombs", 250, "radius"),
                  ("Heavy Bombs", 650, "dmg, pierce"),
                  ("Really Big Bombs", 1100, "black/zebra? splash"),  # ?
                  ("Bloon Impact", 2800, "stun"),
                  ("Bloon Crush", 55000, "stun, moab dmg")),
            _path(("Faster Reload", 250, "attack speed"),
                  ("Missile Launcher", 400, "range, speed"),
                  ("MOAB Mauler", 1000, "moab dmg"),
                  ("MOAB Assassin", 3450, "ability, moab dmg"),
                  ("MOAB Eliminator", 26000, "ability, moab dmg")),
            _path(("Extra Range", 200, "range"),
                  ("Frag Bombs", 300, "frags; pops black"),
                  ("Cluster Bombs", 700, "clusters"),
                  ("Recursive Cluster", 2500, "clusters"),
                  ("Bomb Blitz", 30000, "ability on life loss")),
        ]),
    "tack": _tower(
        "Tack Shooter", "primary", "r", 260, 23, "land", 6,  # footprint ?
        "sharp; 8 tacks radial; no camo targeting but hits camo; can't pop lead",
        [
            _path(("Faster Shooting", 150, "attack speed"),
                  ("Even Faster Shooting", 220, "attack speed"),
                  ("Hot Shots", 600, "fire: lead, frozen"),
                  ("Ring of Fire", 3500, "ring of fire"),
                  ("Inferno Ring", 45500, "meteors, moab dmg")),
            _path(("Long Range Tacks", 100, "range"),
                  ("Super Range Tacks", 225, "range"),
                  ("Blade Shooter", 550, "blades"),
                  ("Blade Maelstrom", 2700, "ability"),
                  ("Super Maelstrom", 15000, "ability")),
            _path(("More Tacks", 150, "10 tacks"),
                  ("Even More Tacks", 150, "12 tacks"),
                  ("Tack Sprayer", 450, "16 tacks"),
                  ("Overdrive", 3200, "very fast"),
                  ("The Tack Zone", 20000, "many tacks")),
        ]),
    "ice": _tower(
        "Ice Monkey", "primary", "t", 400, 20, "land", 7,  # cost 400 per cyberquincy (older wikis: 500) ?
        "cold: freezes; can't pop white/zebra/lead/purple?; no camo",  # ?
        [
            _path(("Permafrost", 150, "slow"),
                  ("Cold Snap", 350, "white/zebra/lead, camo freeze"),
                  ("Ice Shards", 1500, "shards"),
                  ("Embrittlement", 2300, "brittle, camo+lead strip"),
                  ("Super Brittle", 28000, "moab dmg amp")),
            _path(("Enhanced Freeze", 200, "attack speed"),
                  ("Deep Freeze", 300, "freezes 2 layers"),
                  ("Arctic Wind", 2750, "slow aura; ice over water"),
                  ("Snowstorm", 4750, "ability, moab slow"),
                  ("Absolute Zero", 21000, "ability")),
            _path(("Larger Radius", 150, "range"),
                  ("Re-Freeze", 200, "re-freeze"),
                  ("Cryo Cannon", 1900, "long range"),
                  ("Icicles", 2750, "icicles"),
                  ("Icicle Impale", 30000, "moab dmg, slow")),
        ]),
    "glue": _tower(
        "Glue Gunner", "primary", "y", 225, 46, "land", 6,  # footprint ?
        "glue slows; no camo; glue can't affect purple?",  # ?
        [
            _path(("Glue Soak", 200, "soaks layers"),
                  ("Corrosive Glue", 300, "dot dmg"),
                  ("Bloon Dissolver", 2000, "strong dot"),
                  ("Bloon Liquefier", 5000, "strong dot"),
                  ("The Bloon Solver", 22500, "very strong dot, moab")),
            _path(("Bigger Globs", 100, "pierce"),
                  ("Glue Splatter", 650, "splash"),       # v57: 970 -> 650
                  ("Glue Hose", 1950, "very fast"),
                  ("Glue Strike", 4500, "ability, map-wide glue"),  # v57: 4000 -> 4500
                  ("Glue Storm", 16000, "ability")),
            _path(("Stickier Glue", 280, "duration"),
                  ("Stronger Glue", 400, "slow more"),
                  ("MOAB Glue", 3600, "glues moabs"),
                  ("Relentless Glue", 4000, "puddles"),
                  ("Super Glue", 24000, "stops moabs")),
        ]),
    "desperado": _tower(
        "Desperado", "primary", None, 300, 50, "land", 6,  # range ?, footprint ?
        "gift-box tower; revolver; no camo base?",  # ?
        [
            _path(("Quickdraw", 200, ""),
                  ("Standoff", 200, ""),
                  ("Big Iron", 1200, ""),
                  ("Twin Sixes", 5800, ""),
                  ("The Blazing Sun", 16500, "")),
            _path(("Eagle Eye", 150, "range?"),  # ?
                  ("Bullseye", 350, ""),
                  ("Deadeye", 3000, ""),
                  ("Bounty Hunter", 6000, "income?"),  # ?
                  ("Golden Justice", 42000, "")),
            _path(("Wanderer", 220, ""),
                  ("Nomad", 280, ""),
                  ("Enforcer", 2100, ""),
                  ("Avenger", 9500, ""),
                  ("The Desert Phantom", 31000, "")),
        ]),
    # ----------------------------- MILITARY --------------------------------
    "sniper": _tower(
        "Sniper Monkey", "military", "z", 350, None, "land", 6,  # footprint ?
        "map-wide; sharp; can't pop lead; no camo",
        [
            _path(("Full Metal Jacket", 350, "lead, 4 dmg"),
                  ("Large Calibre", 1300, "7 dmg"),
                  ("Deadly Precision", 2200, "ceramic dmg"),
                  ("Maim MOAB", 6300, "moab stun"),
                  ("Cripple MOAB", 32000, "moab stun, dmg")),
            _path(("Night Vision Goggles", 250, "camo"),
                  ("Shrapnel Shot", 450, "shrapnel"),
                  ("Bouncing Bullet", 2100, "bounces"),
                  ("Supply Drop", 7600, "ability: cash"),
                  ("Elite Sniper", 12000, "buff snipers")),
            _path(("Fast Firing", 450, "attack speed"),
                  ("Even Faster Firing", 450, "attack speed"),
                  ("Semi-Automatic", 2700, "3x speed"),
                  ("Full Auto Rifle", 4100, "very fast"),
                  ("Elite Defender", 14900, "faster on leaks")),
        ]),
    "sub": _tower(
        "Monkey Sub", "military", "x", 325, 42, "water", 7,  # footprint ?
        "water only; camo detection; sharp; can't pop lead",
        [
            _path(("Longer Range", 130, "range"),
                  ("Advanced Intel", 500, "shares tower vision"),
                  ("Submerge and Support", 700, "decamo, buffs"),
                  ("Bloontonium Reactor", 2400, "reactor dmg"),
                  ("Energizer", 28000, "ability cooldown buff")),
            _path(("Barbed Darts", 450, "pierce"),
                  ("Heat-tipped Darts", 300, "lead/frozen"),
                  ("Ballistic Missile", 1350, "missile, moab dmg"),
                  ("First Strike Capability", 13000, "ability, moab dmg"),
                  ("Pre-emptive Strike", 29000, "auto first strike")),
            _path(("Twin Guns", 450, "attack speed"),
                  ("Airburst Darts", 1000, "airburst"),
                  ("Triple Guns", 1100, "attack speed"),
                  ("Armor Piercing Darts", 2500, "lead, moab dmg"),
                  ("Sub Commander", 25000, "buff subs")),
        ]),
    "buccaneer": _tower(
        "Monkey Buccaneer", "military", "c", 400, 60, "water", 9,  # footprint ?
        "water only; sharp; can't pop lead; no camo",
        [
            _path(("Faster Shooting", 275, "attack speed"),
                  ("Double Shot", 425, "2 darts"),
                  ("Destroyer", 3350, "very fast"),
                  ("Aircraft Carrier", 8000, "planes"),
                  ("Carrier Flagship", 26000, "buffs, planes")),
            _path(("Grape Shot", 550, "grapes"),
                  ("Hot Shot", 500, "lead/frozen"),
                  ("Cannon Ship", 900, "cannon"),
                  ("Monkey Pirates", 3900, "ability: hook moab"),
                  ("Pirate Lord", 29000, "ability: hooks")),
            _path(("Long Range", 200, "range"),
                  ("Crow's Nest", 350, "camo"),
                  ("Merchantman", 2400, "income"),
                  ("Favored Trades", 5500, "income, sell value"),
                  ("Trade Empire", 23000, "income, buffs")),
        ]),
    "ace": _tower(
        "Monkey Ace", "military", "v", 800, None, "land", 8,  # footprint ?
        "flies paths over map; radial darts hit camo (no targeting needed); can't pop lead",
        [
            _path(("Rapid Fire", 450, "attack speed"),
                  ("Lots More Darts", 550, "more darts"),
                  ("Fighter Plane", 1000, "homing missiles, moab dmg"),
                  ("Operation: Dart Storm", 3300, "many darts"),
                  ("Sky Shredder", 42500, "many darts")),
            _path(("Exploding Pineapple", 200, "pineapples"),
                  ("Spy Plane", 350, "camo"),
                  ("Bomber Ace", 900, "bombs; lead"),
                  ("Ground Zero", 16000, "ability"),
                  ("Tsar Bomba", 26000, "ability, stun")),
            _path(("Sharper Darts", 500, "pierce"),
                  ("Centered Path", 550, "centered flight"),
                  ("Neva-Miss Targeting", 2550, "homing"),
                  ("Spectre", 23400, "dart/bomb spam"),
                  ("Flying Fortress", 90000, "strong all-round")),
        ]),
    "heli": _tower(
        "Heli Pilot", "military", "b", 1500, None, "land", 9,  # footprint ?
        "follows/patrols; sharp; can't pop lead; no camo",
        [
            _path(("Quad Darts", 800, "4 darts"),
                  ("Pursuit", 500, "pursuit mode"),
                  ("Razor Rotors", 1450, "rotor dmg"),
                  ("Apache Dartship", 20000, "missiles, moab dmg"),
                  ("Apache Prime", 45000, "plasma, moab dmg")),
            _path(("Bigger Jets", 300, "speed"),
                  ("IFR", 600, "camo"),
                  ("Downdraft", 3500, "blows back"),
                  ("Support Chinook", 9500, "ability: cash/lives, move towers"),
                  ("Special Poperations", 30000, "ability: marine")),
            _path(("Faster Darts", 250, "projectile speed"),
                  ("Faster Firing", 350, "attack speed"),
                  ("MOAB Shove", 3400, "moab push"),
                  ("Comanche Defense", 8500, "mini helis"),
                  ("Comanche Commander", 35000, "mini helis")),
        ]),
    "mortar": _tower(
        "Mortar Monkey", "military", "n", 600, None, "land", 8,  # footprint ?
        "targets a point; explosion hits camo; pops lead; can't pop black",
        [
            _path(("Bigger Blast", 300, "radius"),
                  ("Bloon Buster", 500, "dmg, layers"),
                  ("Shell Shock", 825, "stun"),
                  ("The Big One", 7000, "dmg"),
                  ("The Biggest One", 36000, "dmg, stun")),
            _path(("Faster Reload", 400, "attack speed"),
                  ("Rapid Reload", 500, "attack speed"),
                  ("Heavy Shells", 900, "ceramic/fortified dmg"),
                  ("Artillery Battery", 6500, "ability"),
                  ("Pop and Awe", 38000, "ability")),
            _path(("Increased Accuracy", 200, "accuracy"),
                  ("Burny Stuff", 400, "fire dot"),
                  ("Signal Flare", 1100, "decamo"),
                  ("Shattering Shells", 9500, "strip fortified/camo"),
                  ("Blooncineration", 40000, "moab burn")),
        ]),
    "dartling": _tower(
        "Dartling Gunner", "military", "m", 850, None, "land", 8,  # footprint ?
        "gift-box tower; aims at cursor (bot must aim!); hits camo; can't pop lead",
        [
            _path(("Focused Firing", 300, "accuracy"),
                  ("Laser Shock", 900, "shock; energy"),
                  ("Laser Cannon", 3000, "lead, frozen"),
                  ("Plasma Accelerator", 11750, "beam"),
                  ("Ray of Doom", 75000, "beam, moab dmg")),
            _path(("Advanced Targeting", 250, "pierce/accuracy"),
                  ("Faster Barrel Spin", 950, "attack speed"),
                  ("Hydra Rocket Pods", 4500, "rockets; lead"),
                  ("Rocket Storm", 5000, "ability"),
                  ("M.A.D", 65000, "moab dmg")),
            _path(("Faster Swivel", 150, "swivel"),
                  ("Powerful Darts", 1200, "dmg"),
                  ("Buckshot", 3000, "spread"),
                  ("Bloon Area Denial System", 12000, "self-aim"),
                  ("Bloon Exclusion Zone", 58000, "self-aim")),
        ]),
    # ------------------------------ MAGIC ----------------------------------
    "wizard": _tower(
        "Wizard Monkey", "magic", "a", 250, 40, "land", 6,  # footprint ?
        "magic: pops lead; can't pop purple; no camo",
        [
            _path(("Guided Magic", 175, "homing, see over walls"),
                  ("Arcane Blast", 450, "dmg"),
                  ("Arcane Mastery", 1450, "range, speed"),
                  ("Arcane Spike", 10000, "moab dmg"),
                  ("Archmage", 32000, "strong")),
            _path(("Fireball", 300, "fireball"),
                  ("Wall of Fire", 800, "fire wall"),
                  ("Dragon's Breath", 3300, "flamethrower"),
                  ("Summon Phoenix", 6000, "ability"),
                  ("Wizard Lord Phoenix", 50000, "permanent phoenix")),
            _path(("Intense Magic", 300, "dmg/pierce"),
                  ("Monkey Sense", 300, "camo"),
                  ("Shimmer", 1500, "decamo"),
                  ("Necromancer: Unpopped Army", 2800, "zombie bloons"),
                  ("Prince of Darkness", 26500, "zombie moabs")),
        ]),
    "super": _tower(
        "Super Monkey", "magic", "s", 2500, 50, "land", 9,  # footprint ?
        "very fast darts; sharp; can't pop lead; no camo",
        [
            _path(("Laser Blasts", 2000, "lasers; frozen"),
                  ("Plasma Blasts", 2500, "plasma; lead"),
                  ("Sun Avatar", 20000, "sun beams"),
                  ("Sun Temple", 100000, "sacrifice"),
                  ("True Sun God", 500000, "sacrifice")),
            _path(("Super Range", 1500, "range"),
                  ("Epic Range", 1900, "range"),
                  ("Robo Monkey", 7500, "two arms"),
                  ("Tech Terror", 25000, "ability"),
                  ("The Anti-Bloon", 70000, "ability")),
            _path(("Knockback", 3000, "knockback"),
                  ("Ultravision", 1200, "camo, range"),
                  ("Dark Knight", 5600, "moab dmg; purple"),
                  ("Dark Champion", 55555, "moab dmg"),
                  ("Legend of the Night", 165650, "ability")),
        ]),
    "ninja": _tower(
        "Ninja Monkey", "magic", "d", 400, 40, "land", 6,  # footprint ?
        "camo detection; sharp; can't pop lead",
        [
            _path(("Ninja Discipline", 350, "range, speed"),
                  ("Sharp Shurikens", 350, "pierce"),
                  ("Double Shot", 900, "2 shurikens"),
                  ("Bloonjitsu", 2750, "5 shurikens"),
                  ("Grandmaster Ninja", 35000, "many shurikens")),
            _path(("Distraction", 250, "knockback chance"),
                  ("Counter-Espionage", 400, "decamo"),
                  ("Shinobi Tactics", 1200, "buff ninjas"),
                  ("Bloon Sabotage", 5200, "ability: slow"),
                  ("Grand Saboteur", 22000, "ability: moab hp")),
            _path(("Seeking Shuriken", 300, "homing"),
                  ("Caltrops", 450, "caltrops"),
                  ("Flash Bomb", 2250, "stun; lead"),
                  ("Sticky Bomb", 5000, "moab dmg"),
                  ("Master Bomber", 40000, "moab dmg, stun")),
        ]),
    "alchemist": _tower(
        "Alchemist", "magic", "f", 550, 45, "land", 7,  # footprint ?
        "acid potions: pops lead; no camo",
        [
            _path(("Larger Potions", 250, "radius"),
                  ("Acidic Mixture Dip", 350, "buff: moab dmg"),
                  ("Berserker Brew", 1400, "buff towers"),
                  ("Stronger Stimulant", 2850, "buff towers"),
                  ("Permanent Brew", 48000, "permanent buff")),
            _path(("Stronger Acid", 250, "dot"),
                  ("Perishing Potions", 475, "moab dmg"),
                  ("Unstable Concoction", 2800, "moab explode"),
                  ("Transforming Tonic", 4200, "ability"),
                  ("Total Transformation", 45000, "ability")),
            _path(("Faster Throwing", 650, "attack speed"),
                  ("Acid Pool", 450, "acid pool"),
                  ("Lead to Gold", 1000, "lead -> cash"),
                  ("Rubber to Gold", 2750, "cash"),
                  ("Bloon Master Alchemist", 40000, "shrink moabs")),
        ]),
    "druid": _tower(
        "Druid", "magic", "g", 400, 35, "land", 7,  # footprint ?
        "thorns: sharp; can't pop lead; no camo",
        [
            _path(("Hard Thorns", 350, "pierce"),
                  ("Heart of Thunder", 850, "lightning; lead"),
                  ("Druid of the Storm", 1700, "tornado"),
                  ("Ball Lightning", 4500, "ball lightning"),
                  ("Monarch of Storms", 60000, "storm")),
            _path(("Thorn Swarm", 250, "more thorns"),
                  ("Heart of Oak", 350, "regrow block"),
                  ("Druid of the Jungle", 1050, "vines"),
                  ("Jungle's Bounty", 4900, "income, ability"),
                  ("Spirit of the Forest", 35000, "vines, income")),
            _path(("Druidic Reach", 100, "range"),
                  ("Heart of Vengeance", 300, "speed on leak"),
                  ("Druid of Wrath", 600, "wrath stacks"),
                  ("Poplust", 2350, "buff druids"),
                  ("Avatar of Wrath", 45000, "strong")),
        ]),
    "mermonkey": _tower(
        "Mermonkey", "magic", None, 300, 40, "land_or_water", 7,  # range ?, footprint ?
        "gift-box tower; tridents; no camo base?",  # ?
        [
            _path(("Trident Efficiency", 150, "pierce"),
                  ("Trident Swiftness", 250, "attack speed"),
                  ("Abyss Dweller", 1800, ""),
                  ("Abyssal Warrior", 4200, ""),
                  ("Lord of the Abyss", 23000, "")),
            _path(("Sharper Prongs", 200, "dmg"),
                  ("Tidal Chill", 225, "slow"),
                  ("Riptide Champion", 2000, ""),
                  ("Arctic Knight", 8000, ""),
                  ("Popseidon", 52000, "")),
            _path(("Echosense Precision", 200, "camo?"),  # ?
                  ("Echosense Network", 280, "camo share?"),  # ?
                  ("Alluring Melody", 2000, ""),
                  ("Symphonic Resonance", 7600, ""),
                  ("The Final Harmonic", 25000, "")),
        ]),
    "skywarden": _tower(
        "Skywarden", "magic", None, 205, 48, "land", 7,  # footprint ?
        "added v56; gift box (3.5M pops); arrows (sharp); no camo base?",  # ?
        [
            _path(("Aerial Attunement", 140, "range; buffs nearby towers"),   # v57: 110 -> 140
                  ("Zephyr Sense", 175, "", 550),                              # v57: 215 -> 175
                  ("Wind Weaver", 1200, "", 2750),                             # v57: 1650 -> 1200
                  ("Galesage", 3000, "disables camo in radius", 16000),       # v57: 3300 -> 3000
                  ("Farwind Seer", 19000, "dmg scales with range", 30000)),
            _path(("Storm's Pulse", 175, "energy dmg (lead?)", 175),          # ?
                  ("Thundering Arc", 275, "snipe + aoe, over walls", 650),
                  ("Galvanic Conduit", 2500, ""),                              # v57: 1800 -> 2500
                  ("Thunder's Decree", 3500, ""),                              # v57: 2000 -> 3500
                  ("Stormwrath Archon", 32000, "")),                           # v57: 35000 -> 32000
            _path(("Shatterpoint", 150, ""),
                  ("Icebore", 250, ""),
                  ("Coldchain", 1500, "freeze; synergy w/ Silas"),
                  ("Frozen Verdict", 3900, ""),
                  ("Winter's Mercy", 20000, "")),
        ]),
    # ----------------------------- SUPPORT ---------------------------------
    "farm": _tower(
        "Banana Farm", "support", "h", 1250, None, "land", 10,  # footprint ?
        "income; bananas need collecting (or Banana Salvage / EZ Collect / Monkey Bank)",
        [
            _path(("Increased Production", 500, "income"),
                  ("Greater Production", 600, "income"),
                  ("Banana Plantation", 3000, "income"),
                  ("Banana Research Facility", 19000, "income"),
                  ("Banana Central", 115000, "income")),
            _path(("Long Life Bananas", 300, ""),
                  ("Valuable Bananas", 800, "income"),
                  ("Monkey Bank", 3650, "bank: collect manually"),
                  ("IMF Loan", 7200, "ability: loan"),
                  ("Monkey-Nomics", 100000, "ability: free cash")),
            _path(("EZ Collect", 250, "auto collect radius"),
                  ("Banana Salvage", 400, "sell value"),
                  ("Marketplace", 2700, "auto-collected income"),
                  ("Central Market", 15000, "income"),
                  ("Monkey Wall Street", 70000, "income")),
        ]),
    "spike": _tower(
        "Spike Factory", "support", "j", 1000, 34, "land", 8,  # footprint ?
        "spikes on track hit camo; sharp; can't pop lead",
        [
            _path(("Bigger Stacks", 800, "pierce"),
                  ("White Hot Spikes", 600, "lead, frozen"),
                  ("Spiked Balls", 2300, "ceramic dmg"),
                  ("Spiked Mines", 9500, "mines"),
                  ("Super Mines", 125000, "huge mines")),
            _path(("Faster Production", 600, "speed"),
                  ("Even Faster Production", 800, "speed"),
                  ("MOAB SHREDR", 2500, "moab dmg"),
                  ("Spike Storm", 7000, "ability"),
                  ("Carpet of Spikes", 41000, "ability")),
            _path(("Long Reach", 150, "range"),
                  ("Smart Spikes", 400, "placement"),
                  ("Long Life Spikes", 1300, "duration"),
                  ("Deadly Spikes", 3600, "dmg"),
                  ("Perma-Spike", 30000, "permanent")),
        ]),
    "village": _tower(
        "Monkey Village", "support", "k", 1200, 40, "land", 10,  # footprint ?
        "buff aura; no attack",
        [
            _path(("Bigger Radius", 400, "radius"),
                  ("Jungle Drums", 1500, "attack speed buff"),
                  ("Primary Training", 800, "buff primary"),
                  ("Primary Mentoring", 2500, "primary discount/buff"),
                  ("Primary Expertise", 25000, "ballista")),
            _path(("Grow Blocker", 250, "regrow"),
                  ("Radar Scanner", 2000, "camo for towers"),
                  ("Monkey Intelligence Bureau", 7500, "all dmg types"),
                  ("Call to Arms", 20000, "ability"),
                  ("Homeland Defense", 40000, "ability")),
            _path(("Monkey Business", 500, "discount"),
                  ("Monkey Commerce", 500, "discount"),
                  ("Monkey Town", 10000, "cash per pop"),
                  ("Monkey City", 3000, "income"),
                  ("Monkeyopolis", 5000, "absorbs farms")),
        ]),
    "engineer": _tower(
        "Engineer Monkey", "support", "l", 350, 40, "land", 6,  # footprint ?
        "nail gun: sharp; can't pop lead; no camo",
        [
            _path(("Sentry Gun", 500, "sentries"),
                  ("Faster Engineering", 400, "sentries"),
                  ("Sprockets", 575, "attack speed"),
                  ("Sentry Expert", 2500, "special sentries"),
                  ("Sentry Champion", 32000, "sentries")),
            _path(("Larger Service Area", 250, "range"),
                  ("Deconstruction", 350, "moab/fortified dmg"),
                  ("Cleansing Foam", 900, "decamo, regrow, lead"),
                  ("Overclock", 13500, "ability: buff tower"),
                  ("Ultraboost", 72000, "ability: perma buff")),
            _path(("Oversize Nails", 450, "pierce"),
                  ("Pin", 220, "pin bloons"),
                  ("Double Gun", 450, "attack speed"),
                  ("Bloon Trap", 3600, "trap, cash"),
                  ("XXXL Trap", 45000, "moab trap")),
        ]),
    "beast_handler": _tower(
        "Beast Handler", "support", "i", 250, 20, "land", 7,  # range ?, footprint ?
        "gift-box tower; beasts in water (top)/land (mid)/air (bottom); merges beasts",
        [
            _path(("Piranha", 160, "water beast"),
                  ("Barracuda", 810, ""),
                  ("Great White", 2010, ""),
                  ("Orca", 12500, ""),
                  ("Megalodon", 45000, "moab grab")),
            _path(("Microraptor", 175, "land beast"),
                  ("Adasaurus", 830, ""),
                  ("Velociraptor", 2065, ""),
                  ("Tyrannosaurus Rex", 9500, ""),
                  ("Giganotosaurus", 60000, "")),
            _path(("Gyrfalcon", 190, "air beast"),
                  ("Horned Owl", 860, "camo?"),  # ?
                  ("Golden Eagle", 2120, ""),
                  ("Giant Condor", 9000, ""),
                  ("Pouākai", 30000, "")),
        ]),
}

# Default PC hotkey for the selected hero slot.
HERO_HOTKEY = "u"

# Default PC hotkeys for upgrading paths 1/2/3 and selling (game defaults).
UPGRADE_HOTKEYS = (",", ".", "/")  # ? ( "," "." "/" are the stock bindings)
SELL_HOTKEY = "backspace"  # ?

# ---------------------------------------------------------------------------
# Heroes (Medium costs)
# use policy for bots:
#   on_cooldown - fire whenever ready
#   moab        - fire when a MOAB-class bloon is on screen
#   save        - hold for emergencies (lives dropping / boss)
#   never       - don't auto-use (sacrifices towers, costs lives, needs targeting)
# cooldown_s values are base (no MK / no level reduction).
# ---------------------------------------------------------------------------


def _ab(level, name, cooldown_s, use):
    return {"level": level, "name": name, "cooldown_s": cooldown_s, "use": use}


def _hero(name, cost, placement, rng, unlock, abilities, notes=""):
    return {
        "name": name,
        "cost": cost,
        "placement": placement,
        "range": rng,
        "unlock": unlock,
        "abilities": abilities,
        "notes": notes,
    }


HEROES: dict[str, dict] = {
    "quincy": _hero("Quincy", 540, "land", 50, "free (starting hero)", [  # range ?
        _ab(3, "Rapid Shot", 60, "on_cooldown"),  # cd ?
        _ab(10, "Storm of Arrows", 60, "on_cooldown"),  # cd ?
    ]),
    "gwendolin": _hero("Gwendolin", 725, "land", 40, "player level ~3 or 1,500 MM", [  # ? range/unlock
        _ab(3, "Cocktail of Fire", 20, "on_cooldown"),  # cd ?
        _ab(10, "Firestorm", 60, "on_cooldown"),  # cd ?
    ]),
    "striker_jones": _hero("Striker Jones", 700, "land", 50, "player level ~5 or 1,500 MM", [  # ?
        _ab(3, "Concussive Shell", 15, "on_cooldown"),  # cd ?
        _ab(10, "Artillery Command", 60, "on_cooldown"),  # cd ?
    ], "buffs bomb/mortar; gives them camo detection"),
    "obyn": _hero("Obyn Greenfoot", 650, "land", 40, "player level ~10 or 1,500 MM", [  # ?
        _ab(3, "Brambles", 15, "on_cooldown"),  # cd ?
        _ab(10, "Wall of Trees", 90, "on_cooldown"),  # cd ?
    ], "buffs magic towers"),
    "rosalia": _hero("Rosalia", 875, "land", 40, "Monkey Money (~4,500 MM)", [  # ? names/cd
        _ab(3, "Kinetic Charge", 40, "on_cooldown"),  # ?
        _ab(10, "Reposition", None, "never"),  # ? movement ability
    ]),
    "churchill": _hero("Captain Churchill", 2000, "land", 52, "2,500 MM", [  # ? range/MM
        _ab(3, "Armor Piercing Shells", 60, "moab"),  # cd ?
        _ab(10, "MOAB Barrage", 60, "moab"),  # cd ?
    ]),
    "benjamin": _hero("Benjamin", 1200, "land", 40, "~5,000 MM", [  # ?
        _ab(3, "Biohack", 45, "on_cooldown"),  # cd ?
        _ab(10, "Syphon Funding", 60, "on_cooldown"),  # cd ?
    ], "passive income each round"),
    "pat_fusty": _hero("Pat Fusty", 800, "land", 30, "~2,000 MM", [  # ?
        _ab(3, "Rallying Roar", 45, "on_cooldown"),  # cd ?
        _ab(10, "Big Squeeze", 45, "moab"),  # cd ?
    ]),
    "ezili": _hero("Ezili", 550, "land", 52, "~2,500 MM", [  # ?
        _ab(3, "Heartstopper", 20, "on_cooldown"),  # cd ?
        _ab(7, "MOAB Hex", 30, "moab"),  # ?
        _ab(10, "Sacrificial Totem", 60, "never"),  # costs lives
    ]),
    "adora": _hero("Adora", 1000, "land", 50, "~5,000 MM", [  # ?
        _ab(3, "Long Arm of Light", 35, "on_cooldown"),  # cd ?
        _ab(7, "Blood Sacrifice", 45, "never"),  # sacrifices towers
        _ab(10, "Ball of Light", 90, "on_cooldown"),  # cd ?
    ]),
    "admiral_brickell": _hero("Admiral Brickell", 900, "water", 60, "~4,500 MM", [  # ?
        _ab(3, "Naval Tactics", 60, "on_cooldown"),  # cd ?
        _ab(10, "MEGA Mine", 90, "moab"),  # cd ?
    ], "water placement only"),
    "etienne": _hero("Etienne", 650, "land", 60, "~3,500 MM", [  # ?
        _ab(3, "Drone Swarm", 35, "on_cooldown"),  # cd ?
        _ab(10, "UCAV", 60, "on_cooldown"),  # cd ?
    ], "camo for all towers from ~L8? (Etienne zone control)"),  # ?
    "sauda": _hero("Sauda", 600, "land", 25, "~3,500 MM", [  # ?
        _ab(3, "Leaping Sword", 20, "on_cooldown"),  # cd ?
        _ab(10, "Sword Charge", 45, "on_cooldown"),  # cd ?
    ], "place right next to the track"),
    "psi": _hero("Psi", 1000, "land", None, "~3,500 MM", [  # ? (map-wide range)
        _ab(3, "Psychic Blast", 15, "on_cooldown"),  # cd ?
        _ab(10, "Psionic Scream", 60, "on_cooldown"),  # cd ?
    ]),
    "geraldo": _hero("Geraldo", 750, "land", 40, "~7,000 MM", [],  # range/MM ?
                     "no activated abilities; shop items must be bought/placed manually"),
    "corvus": _hero("Corvus", 1325, "land", 50, "~7,000 MM", [  # ?
        _ab(3, "Spellbook (mana spells)", None, "never"),
    ], "mana-based spellbook UI; not supported by simple hotkey use"),
    "silas": _hero("Silas", 850, "land", 45, "~7,000 MM", [  # range/MM ?
        _ab(3, "Frostbite", 30, "on_cooldown"),
        _ab(7, "Frozen Cascade", 60, "on_cooldown"),  # cd ?
        _ab(10, "Frozen Burial", 90, "on_cooldown"),  # cd ?
    ], "v50; buffs Ice Monkeys / Coldchain Skywardens"),
    "dan_dmonke": _hero("Dan D'Monke", 650, "land", 40, "7,000 MM", [  # range ?
        _ab(3, "Transformation", None, "never"),  # switches form
        _ab(7, "Reposition", None, "never"),       # normal form
        _ab(10, "Rabble Rouser", None, "save"),     # normal form; cd ?
    ], "v55; Masqued Macaque form has Volant Strike (L7) / Berserk Frenzy (L10)"),
}

# ---------------------------------------------------------------------------
# Player-level unlocks (v57)
# ---------------------------------------------------------------------------

PRIMARY_CHOICES = ["boomerang", "bomb", "tack", "ice", "glue"]
MILITARY_CHOICES = ["sniper", "sub", "buccaneer", "ace", "heli", "mortar"]
MAGIC_CHOICES = ["wizard", "super", "ninja", "alchemist", "druid"]
SUPPORT_CHOICES = ["farm", "spike", "village", "engineer"]
GIFT_BOX_TOWERS = ["dartling", "beast_handler", "mermonkey", "desperado", "skywarden"]

LEVEL_UNLOCKS: dict[int, dict] = {
    1: {"towers": ["dart"], "heroes": ["quincy"]},
    **{lvl: {"choose": "primary", "from": PRIMARY_CHOICES} for lvl in (2, 3, 4, 5, 6)},
    **{lvl: {"choose": "military", "from": MILITARY_CHOICES} for lvl in (7, 8, 9, 10, 11, 12)},
    **{lvl: {"choose": "magic", "from": MAGIC_CHOICES} for lvl in (15, 16, 17, 19, 20)},
    **{lvl: {"choose": "support", "from": SUPPORT_CHOICES} for lvl in (22, 23, 24, 26)},
    30: {"monkey_knowledge": True,
         "gift_boxes": GIFT_BOX_TOWERS,  # each unlocks after N pops (Skywarden 3.5M)  # ?
         "note": "MK + pop-count gift boxes for Dartling/Beast Handler/Mermonkey/Desperado/Skywarden"},
}
# Hero level unlocks (Gwendolin/Striker/Obyn) are best effort - see HEROES[*]["unlock"].  # ?

# ---------------------------------------------------------------------------
# XP
# ---------------------------------------------------------------------------

MAP_XP_MULT = {"beginner": 1.0, "intermediate": 1.1, "advanced": 1.2, "expert": 1.3}
FREEPLAY_XP_MULT = 0.3  # -70% up to round 100 (-90% after)


def XP_PER_ROUND(round_: int, map_difficulty: str = "beginner", freeplay: bool = False) -> float:
    """Player/tower XP for completing ``round_`` (confirmed piecewise formula)."""
    r = round_
    if r <= 20:
        xp = 20 * r + 20
    elif r <= 50:
        xp = 40 * (r - 20) + 420
    else:
        xp = 90 * (r - 50) + 1620
    xp *= MAP_XP_MULT.get(map_difficulty.lower(), 1.0)
    if freeplay:
        xp *= 0.3 if r <= 100 else 0.1
    return xp


def game_xp(start_round: int, end_round: int, map_difficulty: str = "beginner") -> float:
    """Total XP for clearing rounds start..end inclusive (non-freeplay)."""
    return sum(XP_PER_ROUND(r, map_difficulty) for r in range(start_round, end_round + 1))


# XP needed to go from level N to N+1 (index 0 -> level 1->2).  ALL best effort.  # ?
_LEVEL_STEP_XP = [
    180, 460, 1000, 1860, 3280, 5180, 8320, 9380, 13620, 16380,   # 1->2 .. 10->11  # ?
    14400, 16650, 14940, 16380, 17820, 19260, 20700, 16470, 17280, 18090,  # 11..20  # ?
] + [18090 + 810 * i for i in range(1, 41)]  # 21->22 .. 60->61, +810/level  # ? extrapolated

# PLAYER_LEVEL_XP[level] = cumulative XP required to *reach* that level.
PLAYER_LEVEL_XP: dict[int, int] = {1: 0}
for _i, _step in enumerate(_LEVEL_STEP_XP):
    PLAYER_LEVEL_XP[_i + 2] = PLAYER_LEVEL_XP[_i + 1] + _step
del _i, _step


def level_from_xp(total_xp: float) -> int:
    """Player level for a cumulative XP total (best effort; table above is uncertain)."""
    level = 1
    for lvl in sorted(PLAYER_LEVEL_XP):
        if total_xp >= PLAYER_LEVEL_XP[lvl]:
            level = lvl
        else:
            break
    return level


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def upgrade(tower: str, path: int, tier: int) -> dict:
    """Upgrade dict for ``tower`` path 1-3, tier 1-5."""
    return TOWERS[tower]["upgrades"][path - 1][tier - 1]


def upgrade_cost(tower: str, path: int, tier: int, difficulty: str = "medium") -> int:
    return price(upgrade(tower, path, tier)["cost"], difficulty)


def tower_cost(tower: str, difficulty: str = "medium") -> int:
    return price(TOWERS[tower]["cost"], difficulty)


def total_cost(tower: str, crosspath: str | tuple, difficulty: str = "medium") -> int:
    """Total cost to buy ``tower`` at e.g. "2-0-4" / (2, 0, 4), each step rounded separately."""
    if isinstance(crosspath, str):
        crosspath = tuple(int(c) for c in crosspath.replace("-", "").replace("_", ""))
    total = tower_cost(tower, difficulty)
    for p, tiers in enumerate(crosspath, start=1):
        for t in range(1, tiers + 1):
            total += upgrade_cost(tower, p, t, difficulty)
    return total


def hero_cost(hero: str, difficulty: str = "medium") -> int:
    return price(HEROES[hero]["cost"], difficulty)


def find_tower(name: str) -> str | None:
    """Map a display name to its id, ignoring case, spaces and punctuation
    (OCR often merges words: 'BOMBSHOOTeR')."""
    def squash(s):
        return "".join(c for c in s.lower() if c.isalnum())

    low = squash(name)
    if not low:
        return None
    for key, t in TOWERS.items():
        if squash(key) == low or squash(t["name"]) == low:
            return key
    for key, t in TOWERS.items():  # tolerate a dropped/garbled character
        n = squash(t["name"])
        if len(low) >= 6 and (low in n or n in low):
            return key
    return None


HOTKEY_TO_TOWER = {t["hotkey"]: k for k, t in TOWERS.items() if t["hotkey"]}
