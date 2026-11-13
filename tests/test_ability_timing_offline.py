"""Abilities count only the uses sure to land on a bloon (dps_model.ABILITY_TIMING).

Case 20261112_202137 (Muddy Puddles Impoppable, 2026-11-12 20:09, build at
8f34eed): the game was lost at round 40, its one MOAB, at a blimp ratio of
0.29. The damage model had rated the round 1.18, 0.59 of it without the
abilities: the centre tack's Blade Maelstrom (2-4-0, bought in round 39 for
this round: blades for 3 s every 20 s) counted as a share of blades on the
MOAB however short its pass. The bot presses it on cooldown, not when the
MOAB comes, and the MOAB is in the tack's reach for about 8 s: no use is
sure to meet it.

The board below is the journal's (logs/journal/20261112_200934_MuddyPuddles
_impoppable.jsonl, the "round" event of round 40): towers at the start of
the round, exact spots, placement rounds for Etienne's level. Round 40 must
rate under 1 live (status effects off) and offline, and gain nothing from
the Maelstrom; the rounds the board held must still rate as held.

Run: python tests/test_ability_timing_offline.py"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import simulate_threats as SIM              # noqa: E402
from btd6bot import dps_model as D          # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

MAP, MODE, HERO = "Muddy Puddles", "impoppable", "etienne"
KNOWLEDGE = ("Monkey Education",)            # the main account's hero-XP knowledge, as the bot rates it

# (tid, kind, tiers, x, y, placement round), as the journal logs them
MUDDY_40 = [
    ("des501", "desperado", "0-1-0", 0.2485, 0.7257, 6), ("bea502", "beast_handler", "0-0-0", 0.318, 0.845, 6),
    ("sky503", "skywarden", "1-0-1", 0.5905, 0.6406, 6), ("sky504", "skywarden", "2-0-1", 0.2592, 0.385, 6),
    ("sky505", "skywarden", "2-0-0", 0.2271, 0.6235, 6), ("sky506", "skywarden", "1-0-0", 0.5798, 0.5894, 6),
    ("bonus_dart", "dart", "0-0-3", 0.5477, 0.2402, 6), ("des507", "desperado", "0-0-0", 0.6012, 0.7257, 7),
    ("sky508", "skywarden", "2-0-1", 0.2592, 0.4531, 8), ("sky509", "skywarden", "2-0-1", 0.4409, 0.385, 9),
    ("sky510", "skywarden", "2-0-0", 0.2164, 0.6917, 9), ("sky511", "skywarden", "2-0-1", 0.2164, 0.5724, 10),
    ("tac512", "tack", "2-4-0", 0.5157, 0.6406, 11), ("wiz513", "wizard", "1-2-0", 0.6225, 0.828, 12),
    ("des514", "desperado", "0-0-0", 0.6012, 0.5213, 13), ("sub515", "sub", "2-3-0", 0.6332, 0.4361, 14),
    ("eng516", "engineer", "0-0-0", 0.2592, 0.845, 15), ("buc517", "buccaneer", "2-0-1", 0.4035, 0.6406, 18),
    ("eng518", "engineer", "0-0-0", 0.5531, 0.6917, 18), ("tac519", "tack", "2-3-0", 0.1523, 0.6406, 19),
    ("mer520", "mermonkey", "0-0-0", 0.6867, 0.615, 20), ("a1", "alchemist", "0-0-0", 0.5531, 0.5554, 23),
    ("buc521", "buccaneer", "0-3-2", 0.3981, 0.5639, 25), ("bom522", "bomb", "0-1-3", 0.2164, 0.1806, 26),
    ("boo523", "boomerang", "0-0-0", 0.3019, 0.3509, 30), ("eng524", "engineer", "0-0-0", 0.5691, 0.1806, 31),
    ("hero", "hero", "0-0-0", 0.5157, 0.845, 32), ("ace_carry1", "ace", "0-0-0", 0.1256, 0.845, 34),
    ("nin501", "ninja", "0-0-0", 0.3019, 0.4702, 37), ("buc502", "buccaneer", "0-0-1", 0.3554, 0.6576, 38)]


def _towers(board):
    return [SimpleNamespace(tid=t, kind=k, tiers=tuple(int(c) for c in tiers.split("-")), x=x, y=y, placed_round=p)
            for t, k, tiers, x, y, p in board]


def _margin(board, rnd, status=True):
    """The board's margin for `rnd`, rated as the match loop rates it (the
    learned map's sight, Etienne at the bot's level estimate), with status
    effects on or off; a fresh forecast, so no memo carries over."""
    m = SIM.map_model(MAP, learned=True)
    saved = D.STATUS_RATING
    D.STATUS_RATING = status
    try:
        fc = RoundForecast(MAP, MODE, m.sight, (getattr(m, "sight_height", None), getattr(m, "ground_height", None)),
                           hero=HERO, knowledge=KNOWLEDGE)
        assert fc._ready()
        return (fc.margins(_towers(board), [rnd]) or {}).get(rnd)
    finally:
        D.STATUS_RATING = saved


def test_no_maelstrom_use_is_sure_to_meet_one_moab():
    """Blade Maelstrom (3 s in 20, pressed on cooldown) and a window of
    under 20 s: floor((window + 3) / 20) = 0 uses sure to land; a window
    of 40 s gets 2 of the 2.15 the uptime credits."""
    landed, expected = D._uses_landed(20.0, 3.0, (6.5, 14.6), "on_cooldown")      # round 40's MOAB at the tack
    assert landed == 0.0 and math.isclose(expected, (14.6 - 6.5 + 3.0) / 20.0)
    landed, expected = D._uses_landed(20.0, 3.0, (0.0, 40.0), "on_cooldown")
    assert landed == 2.0 and math.isclose(expected, 43.0 / 20.0)


def test_moab_ability_pressed_at_the_blimps():
    """MOAB Eliminator (every 10 s, pressed 6 game seconds into a MOAB
    round): one MOAB in the tower's reach from 4 s to 16 s meets the press
    whenever between 6 s and 10 s it comes."""
    assert D._uses_landed(10.0, 0.0, (4.0, 16.0), "moab")[0] == 1.0
    assert D._uses_landed(10.0, 0.0, (0.0, 5.0), "moab")[0] == 0.0     # gone before the first press


def test_sabotage_only_in_slow_rounds_and_first_strike_after_the_blimps():
    """Bloon Sabotage is pressed only in the hand-picked slow rounds
    (abilities.ROUND_START, is_slow_round): none lands in round 91, the
    leaked Bloonarius Prime round its uptime helped lift over 1.0. First
    Strike waits for the first blimp to be 2 s on the track."""
    assert D._uses_landed(60.0, 15.0, (24.0, 98.0), "slow", {"slow": False})[0] == 0.0
    assert D._uses_landed(60.0, 15.0, (24.0, 98.0), "slow", {"slow": True})[0] == 1.0
    assert D._uses_landed(60.0, 0.0, (30.0, 40.0), "strike", {"blimp_s": 30.0})[0] == 0.0  # cooldown may run
    assert D._uses_landed(60.0, 0.0, (30.0, 95.0), "strike", {"blimp_s": 30.0})[0] == 1.0
    assert D._uses_landed(60.0, 0.0, (30.0, 95.0), "strike", {"blimp_s": None})[0] == 0.0
    from btd6bot.abilities import BLIMP_TARGETED, ROUND_START
    names = D._tower_ability_names()
    assert names[("ninja", "Sabotage")] in ROUND_START
    assert names[("sub", "First Strike Capability")] in BLIMP_TARGETED


def test_buffed_copy_and_plain_copy_add_up():
    """A buffed copy at share s keeps f of its shots; the plain copy beside
    it (1 - s of the shots) takes back the rest, 1 - s f of them in all:
    with no use sure to land (f = 0, a 5 s pass and Call to Arms every
    45 s) the tower fires every shot unbuffed, none lost."""
    st = SimpleNamespace(windows=((0.0, 5.0), (), {}))
    share = 1.0 / 3.0
    on = SimpleNamespace(timed=((45.0, 15.0, share, "on", "on_cooldown"),))
    off = SimpleNamespace(timed=((45.0, 15.0, share, "off", "on_cooldown"),))
    f_on, f_off = D._timing_factor(on, st, stay=5.0), D._timing_factor(off, st, stay=5.0)
    assert f_on == 0.0 and math.isclose((1.0 - share) * f_off, 1.0)


def test_round_40_rates_under_one_live_and_offline():
    for status in (False, True):
        margin = _margin(MUDDY_40, 40, status)
        assert margin is not None and margin < 1.0, (status, margin)


def test_the_maelstrom_adds_nothing_to_round_40():
    """With the timing rule the board rates round 40 as it does without
    the ability; at its uptime the ability changed the rating."""
    timed = _margin(MUDDY_40, 40)
    D.ABILITY_RATING = False
    try:
        D.profile.cache_clear()
        D._own_attack_hits.cache_clear()
        plain = _margin(MUDDY_40, 40)
    finally:
        D.ABILITY_RATING = True
        D.profile.cache_clear()
        D._own_attack_hits.cache_clear()
    assert math.isclose(timed, plain, rel_tol=1e-6), (timed, plain)


def test_held_rounds_of_the_board_still_hold():
    """Rounds 35-39 held with the board one or two towers short of round
    40's (journal margins 1.45-3.36); the round-40 board rates them over 1."""
    for rnd in (36, 38, 39):
        margin = _margin(MUDDY_40, rnd)
        assert margin is not None and margin >= 1.0, (rnd, margin)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
