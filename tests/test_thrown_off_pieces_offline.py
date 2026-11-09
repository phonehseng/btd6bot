"""Shrapnel and frags hit only the bloons around the one their carrier struck.

A sniper's Shrapnel Shot and a bomb's Frag Bombs throw pieces off the bloon
the bullet or bomb struck, and the pieces fly away from it. The damage model
used to give each piece `1 + packing x reach` bloons to meet, the same as a
dart fired at a target, so every piece counted at least one hit even on a
lone bloon. A 2-2-0 sniper's bullet came with five Shrapnel hits: six pink
pops a shot instead of one. On spread-out rounds that made sniper boards
look several times stronger than they were:

  * Sanctuary Military Only (2026-11-09 10:21, solo_sniper, picked as SAFE
    at p=0.94): five snipers stood at round 38 and lost all 65 lives left;
    the model rated that board 1.41 (and 1.15 at round 36, which cost 85
    lives);
  * Sanctuary Medium (2026-11-08 21:27): two 3-2-0 snipers rated 2.1-2.8 at
    round 38 and lost every life;
  * Ship Capture Half Cash (2026-11-09 01:35): bombs with Frag Bombs and a
    1-2-0 sniper rated 1.87 at round 38 and lost 22 lives there.

The pieces now meet `packing x reach` bloons (the others near the struck
spot), plus the children the carrier's hit left on the spot when it popped
the struck layer. Blasts centred on the spot (a bomb's Explosion) still take
in the struck bloon. Winning sniper boards stay rated safe.

The boards are the ones the bot logged (logs/bot.log, logs/journal).
Run: python tests/test_thrown_off_pieces_offline.py (also collectable by pytest).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

# (tid, kind, tiers, x, y) as logged; heroes are not modelled and left out.
SANCTUARY_MILITARY_LOSS = [      # 2026-11-09 10:27, round 38
    ("a1", "sniper", (2, 2, 0), 0.382, 0.249), ("a2", "sniper", (4, 2, 0), 0.414, 0.913),
    ("b1", "sniper", (1, 0, 2), 0.377, 0.930), ("sniper1", "sniper", (0, 0, 0), 0.259, 0.819),
    ("sniper2", "sniper", (0, 0, 0), 0.371, 0.138),
]
SANCTUARY_MEDIUM_LOSS = [        # 2026-11-08 21:38, round 38
    ("s2", "sniper", (3, 2, 0), 0.403, 0.871), ("s1", "sniper", (3, 2, 0), 0.409, 0.215),
]
SHIP_CAPTURE_LOSS = [            # 2026-11-09 01:40, rounds 37-39
    ("snp1", "sniper", (1, 2, 0), 0.409, 0.189), ("bmb1", "bomb", (0, 3, 2), 0.462, 0.666),
    ("bmb2", "bomb", (0, 2, 2), 0.414, 0.675), ("bmb5", "bomb", (3, 0, 2), 0.355, 0.709),
    ("bmb3", "bomb", (0, 2, 2), 0.612, 0.700), ("bmb4", "bomb", (0, 2, 3), 0.227, 0.726),
    ("desperado1", "desperado", (0, 2, 0), 0.574, 0.496), ("mer1", "mermonkey", (2, 0, 0), 0.500, 0.700),
]
# Won: Mushroom Grotto Military Only, solo_sniper (2026-11-05 10:43), board at round 38.
MUSHROOM_GROTTO_MILITARY_WIN = [
    ("a1", "sniper", (3, 2, 0), 0.3233, 0.4702), ("a2", "sniper", (3, 2, 0), 0.318, 0.5298),
    ("b1", "sniper", (2, 0, 3), 0.5638, 0.5894), ("sniper1", "sniper", (3, 2, 0), 0.318, 0.5894),
    ("sniper2", "sniper", (3, 2, 0), 0.5638, 0.4276),
]
# Won: Party Parade Military Only, military_heli_sniper (2026-11-05 10:17), board at round 38.
PARTY_PARADE_MILITARY_WIN = [
    ("s1", "sniper", (3, 2, 0), 0.5691, 0.5213), ("s2", "sniper", (2, 2, 0), 0.2699, 0.4787),
    ("h1", "heli", (3, 0, 2), 0.318, 0.5554), ("sniper1", "sniper", (3, 2, 0), 0.5958, 0.4872),
    ("h2", "heli", (3, 0, 2), 0.6386, 0.2061), ("sniper2", "sniper", (2, 2, 0), 0.5958, 0.5554),
    ("sniper3", "sniper", (1, 2, 0), 0.2966, 0.4446), ("sniper4", "sniper", (1, 0, 0), 0.5638, 0.5809),
]


def _margins(map_name, mode, board, rounds):
    fc = RoundForecast(map_name, mode)
    assert fc._ready(), f"no damage model for {map_name}"
    stations = fc.stations([SimpleNamespace(tid=t, kind=k, tiers=c, x=x, y=y) for t, k, c, x, y in board])
    return {r: D.round_margin(stations, mode, r, fc.track) for r in rounds}


def _source(kind, tiers, name):
    return next(s for s in D.profile(kind, tiers).sources if s.name.endswith(name))


def test_pieces_thrown_off_a_struck_bloon_are_marked():
    assert _source("sniper", (2, 2, 0), "Shrapnel").off_struck
    assert not _source("sniper", (2, 2, 0), "Projectile").off_struck
    assert _source("bomb", (0, 0, 2), "Frag").off_struck
    assert not _source("bomb", (0, 0, 2), "Explosion").off_struck, "a blast on the spot takes in the struck bloon"


def test_shrapnel_misses_a_lone_bloon_and_still_works_a_crowd():
    shrapnel = _source("sniper", (2, 2, 0), "Shrapnel")
    pink = D.layer("Pink")
    assert D._hit_rate(shrapnel, pink, 1e-4, None) < 0.01 * shrapnel.shots, "nothing beside a lone bloon"
    crowd = 3.0 / shrapnel.reach        # three other bloons along each piece's sweep
    assert abs(D._hit_rate(shrapnel, pink, crowd, None) - shrapnel.shots * shrapnel.pierce) < 1e-9


def test_pieces_still_meet_the_children_a_bullet_leaves_on_the_spot():
    shrapnel = _source("sniper", (2, 2, 0), "Shrapnel")     # bullet: 7 damage
    lone = 1e-4
    assert D._hit_rate(shrapnel, D.layer("Lead"), lone, None) > 0.9 * shrapnel.shots, "greens left by the bullet"
    assert D._hit_rate(shrapnel, D.layer("Pink"), lone, None) < 0.01 * shrapnel.shots, "the bullet pops it all"
    assert D._hit_rate(shrapnel, D.layer("Ceramic"), lone, None) < 0.01 * shrapnel.shots, "7 does not pop a ceramic"
    frag = _source("bomb", (0, 0, 2), "Frag")                # the bomb itself does no damage
    assert D._hit_rate(frag, D.layer("Zebra"), lone, None) < 0.01 * frag.shots


def test_sanctuary_military_only_round_38_board_is_rated_a_loss():
    m = _margins("Sanctuary", "military_only", SANCTUARY_MILITARY_LOSS, (36, 38))
    assert m[38] < 1.0, m           # was 1.41, now 0.51; the game lost its last 65 lives
    assert m[36] < 1.0, m           # was 1.15, now 0.51; the game lost 85 lives


def test_sanctuary_medium_two_sniper_board_is_rated_a_loss():
    m = _margins("Sanctuary", "medium", SANCTUARY_MEDIUM_LOSS, (38,))
    assert m[38] < 1.0, m           # was 2.1 offline (2.8 live), now 0.55; lost every life


def test_ship_capture_frag_board_is_no_longer_rated_comfortable():
    m = _margins("Ship Capture", "half_cash", SHIP_CAPTURE_LOSS, (38,))
    assert m[38] < 1.3, m           # was 1.87, now 1.08; lost 22 lives that round


def test_winning_sniper_boards_stay_safe():
    m = _margins("Mushroom Grotto", "military_only", MUSHROOM_GROTTO_MILITARY_WIN, (36, 37, 38, 39, 40))
    assert min(m.values()) > 1.5, m         # was 3.0-6.5; now 2.1-4.0 (R39 2.09)
    m = _margins("Party Parade", "military_only", PARTY_PARADE_MILITARY_WIN, (36, 37, 38, 39, 40))
    assert min(m.values()) > 1.5, m         # was 3.4-7.8; now 2.9-7.4


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
