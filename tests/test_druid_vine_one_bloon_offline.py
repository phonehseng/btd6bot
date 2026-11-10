"""A Druid of the Jungle's vine grabs one bloon, not a crowd.

The game makes the druid map-wide at x-3-x, and its JungleVine attack fires
a projectile with 9,999,999 pierce, 9,999,999 damage and a 4-unit radius,
plus a CollideOnlyWithTargetModel: it collides with the one bloon it was
sent at and nothing else. The export leaves that behaviour uninterpreted
(attacks.json "other"), so the damage model read the vine as a 4-unit blast
and gave it `1 + packing x 24` bloons a shot. Against round 63's ceramic
bursts (40 ceramics spawned in 0.2 s, three times) that was ~6 whole
ceramics per vine, and two druids carried Bazaar Half Cash's round-63
rating: the live board of the third loss (2026-11-10 11:29, loss case
20261110_114329_Bazaar_half_cash) rated 1.98 (1.27 without either druid)
and lost all 100 lives in seconds, the defeat screen counting 104 lives of
yellows. With the vine on its one target the same board rates under 1.

The board is the one the journal logged at round 63's start.
Run: python tests/test_druid_vine_one_bloon_offline.py (also collectable by pytest).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import simulate_threats as SIM              # noqa: E402
from btd6bot import dps_model as D          # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

# (tid, kind, tiers, x, y): the journal's round-63 board (hero left out)
BAZAAR_HALF_CASH_R63_LOSS = [
    ("sni1", "sniper", (4, 2, 0), 0.7615, 0.4361), ("sub1", "sub", (2, 0, 4), 0.3981, 0.3339),
    ("sni2", "sniper", (3, 2, 0), 0.1095, 0.4872), ("sub2", "sub", (4, 2, 0), 0.4409, 0.3339),
    ("dr1", "druid", (1, 3, 0), 0.6974, 0.828), ("dr2", "druid", (1, 3, 0), 0.1363, 0.828),
    ("sni3", "sniper", (1, 2, 0), 0.7401, 0.5043), ("sub3", "sub", (4, 2, 0), 0.3981, 0.7087),
    ("sni4", "sniper", (1, 2, 0), 0.1042, 0.5469), ("sub4", "sub", (2, 3, 0), 0.4302, 0.2743),
    ("sub5", "sub", (2, 0, 4), 0.3981, 0.2317), ("sub6", "sub", (4, 2, 0), 0.4622, 0.2317),
]


def _vine():
    return next(s for s in D.profile("druid", (1, 3, 0)).sources if s.name == "JungleVine>Collidable")


def test_vine_meets_only_its_target():
    vine = _vine()
    assert vine.placement == "global" and vine.reach == 0.0, vine
    lay = D.layer("Ceramic")
    for rho in (0.01, 0.5, 5.0):          # lone bloons ... a packed burst
        assert abs(D._hit_rate(vine, lay, rho, None) - 1.0 / 2.6) < 1e-9, rho


def test_one_thorn_patch_per_vine():
    """The thorn patch is spawned where the vine touched: once per vine."""
    thorns = [s for s in D.profile("druid", (1, 3, 0)).sources if s.name == "JungleVine>Projectile"]
    assert len(thorns) == 1 and abs(thorns[0].shots - 1.0 / 2.6) < 1e-9, thorns


def test_bazaar_half_cash_round_63_loss_board_leaks():
    m = SIM.map_model("Bazaar", learned=True)
    fc = RoundForecast("Bazaar", "half_cash", m.sight, (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    assert fc._ready()
    towers = [SimpleNamespace(tid=t, kind=k, tiers=c, x=x, y=y) for t, k, c, x, y in BAZAAR_HALF_CASH_R63_LOSS]
    margin = D.round_margin(fc.stations(towers), "half_cash", 63, fc.track)
    assert margin < 1.0, f"the board that lost round 63 rated {margin:.2f}"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
