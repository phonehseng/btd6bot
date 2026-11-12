# Damage model fix plan (2026-11-12)

This plan comes from four audits of how the damage model scores every tower and hero. Each was checked against the BTD6 wiki for version 57.4:

- `docs/model_audit_primary.md`
- `docs/model_audit_military.md`
- `docs/model_audit_magic.md`
- `docs/model_audit_support_heroes.md`

The owner's background research is in `docs/tower_research_2026-11.md`.

**What the audits agree on.** The exported numbers are right: rates, pierce, damage, immunities and bonuses. The ratings go wrong in how `dps_model.py` combines them:

- it credits too much where attacks are alternatives or don't reach;
- it credits nothing for heroes, abilities, status effects and aimed towers.

The 2.0 safety bar and `model_ceiling.json` were fitted on the current, wrong model. After each phase:

1. Re-fit them: margin against outcome, from `logs/results.jsonl` and the journals' round snapshots.
2. Re-rate every strategy (`tools/optimize_builds.py --check`).

Never ship a phase without that re-fit.

## Phase 1: over-credits (makes ratings honest; ships first)

1. **Bomber Ace bombs on the whole map** (military #1). Read the export's `over_track_only`: the bombs fall only while the plane is over the track. 2-3-0 aces and Ground Zero are over-rated 3-10×.
2. **Overflow averaging** in `_Rates._compute` (magic #1). One huge hit plus many small hits are averaged, so every small hit acts like an instakill. Druid of the Jungle reads about 6 bloons/s; the real figure is about 0.4.
3. **Alternatives counted as if all fire** (military #4, primary #6):
   - sub airburst darts counted both on hit and on miss;
   - Buccaneer rear shots;
   - Spectre / Flying Fortress alternation;
   - Recursive Cluster;
   - submerged subs still credited with darts;
   - frag pierce cost.
4. **Per-attack range, not the tower's largest** (primary #4): Glaive Lord's orbit (radius 30) and the Desperado pistol.
5. **Acidic Mixture Dip treated as permanent** (magic). It lasts 10 shots per throw, one throw every 10 s, unless the Alchemist has Permanent Brew.
6. **Spiked Mines** explode twice instead of once, and are allowed to pop black and DDT (support).

## Phase 2: missing value (lets the planner choose the towers the owner uses)

7. **Heroes in the rating**, at their estimated level by round, behind a switch (support #1).
   - Etienne's level-8 camo: also fix the sub-tower buff read.
   - Obyn's Druid buffs.
   - Psi needs an instakill source.
   - Corvus must stay out until his spells are modelled.
   - Fix the hero constants: Corvus/Silas XP ratios swapped, about 14 cooldowns, Ezili's and Rosalia's ability levels.
8. **Abilities credited by uptime**, since the bot fires them on cooldown:
   - MOAB Eliminator, about 4× its blimp damage;
   - Super/Blade Maelstrom;
   - Call to Arms (+42%) and Homeland Defense;
   - Turbo/Perma Charge;
   - First Strike;
   - Ball of Light;
   - Glue Strike/Storm, Snowstorm, Absolute Zero.
9. **Status effects as time added on the track** (primary #1, military #3):
   - stuns: Maim MOAB keeps a MOAB stunned all the time, Bloon Crush, Flash Bomb;
   - slows: glue, ice, Bloon Sabotage;
   - knockback: Monarch of Storms, MOAB Press;
   - debuffs: Cripple MOAB (+5 damage from every source), Embrittlement (+1), Super Brittle (+4).
10. **Aimed sprays read as all-around fire** (magic #2, primary #6): Sun Avatar, Bloonjitsu/Grandmaster, Druid thorns, Triple Shot, the Desperado shotgun. The export must carry the spray angle.
11. **Pierce refresh on lingering projectiles**: Wall of Fire (10 hits credited, the game gives up to about 300), the Jungle bramble (up to 15× too low) and Carpet of Spikes.
12. **Mechanics missing from the export entirely:**
    - Spirit of the Forest's whole-track vines;
    - Prince of Darkness graveyard scaling;
    - Wizard Lord Phoenix;
    - Shimmer/Archmage camo stripping;
    - Bloon Master Alchemist;
    - the Sub Commander aura (×2 damage);
    - the Carrier Flagship attack-speed buff;
    - Pre-emptive Strike;
    - the Comanche mini-helis;
    - Ice Shards and Icicles;
    - The Blazing Sun's fire.
13. **Druid of the Jungle vine:** digest time on ceramics and leads (about 4.1 s and 3.35 s, against the base 2.6 s).
14. **Mortar and Dartling at a fixed aim point.** Credit the round's track around one aim point, and have the bot set that point. No code sets a Mortar target today, and a Dartling's default aim needs one in-game look to confirm.
15. **Economy:** Benjamin's income ($90 to $5,000 a round), farms and Village discounts are ignored by the optimizer.

## Phase 3: builds

After phases 1-2 and their re-fit, regenerate the general and map builds. They should then be able to pick, on merit:

- a Druid of the Jungle opening (1-3-0 with a camo village, or with Obyn) carrying rounds 1-39;
- Spirit of the Forest and Monarch of Storms late;
- Spectre with Centered Path;
- Glaive Lord with a camo village;
- Etienne for map-wide camo;
- Benjamin in Impoppable;
- Mortar and Dartling at fixed aim points;
- Adora placed at the track's edge, once Ball of Light is fired on heavy rounds.
