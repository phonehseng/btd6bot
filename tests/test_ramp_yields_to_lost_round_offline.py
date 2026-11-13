"""With one life, the blimp check leaves the cash alone for a blimp round the
damage model rates as held while the model rates another round ahead as lost.

Pat's Pond Impoppable (2026-11-12 23:33-00:00, chimps_sub_druid_water; loss
case 20261113_000355_PatsPond_impoppable): from round 81 on the damage model
rated round 90 - three fortified camo DDTs - at 0.06-0.07, and round 93 the
same. The blimp check read the blimp rounds before it (84, 87, 88) at
0.6-1.2x of its 2.5x one-life bar, where the model gave 1.2-1.6. So the check
bought MOAB Assassins, held the bank for a MOAB Eliminator and bought it at
round 88 ($31,200): bombs, which a DDT is immune to. In the model round 88
went 1.35 -> 1.85 and round 90 stayed at 0.07. Reinforcing, which judges
purchases on the round that ends the game and saves for one that holds it,
did not get one look in rounds 81-89; round 90's DDT took the life (defeat
screen: DDT -660). About $98k came in over those rounds; on that board a MOAB
Domination ($65,790) rates round 90 at 1.63.

The rule (Executor._ramp_yields_to_lost_round): the blimp check neither buys
nor holds for such a round. Held here on the lost game's own board at the
start of round 88 (tools/rate_board.py board_from_log, stop 23:59:40).

Run: python tests/test_ramp_yields_to_lost_round_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from btd6bot import dps_model as D                      # noqa: E402
from btd6bot import mapgeom as G                        # noqa: E402
from btd6bot import strategy as S                       # noqa: E402
from btd6bot import threats as TH                       # noqa: E402
import test_reinforce_budget_offline as SETUP           # noqa: E402  (MapModel, LAYOUTS, SIM)

MAP, MODE, BUILD = "Pat's Pond", "impoppable", "chimps_sub_druid_water"
RND, DDT_ROUND, CASH = 88, 90, 35_965
BOARD_88 = [
    ("sb1", "sub", "2-0-4", 0.628, 0.734), ("dr", "dart", "0-2-4", 0.072, 0.436),
    ("sb2", "sub", "2-0-4", 0.628, 0.232), ("hero", "hero", "0-0-0", 0.094, 0.376),
    ("a1", "alchemist", "4-2-0", 0.751, 0.751), ("dr2", "dart", "0-2-4", 0.799, 0.411),
    ("d1", "druid", "2-0-4", 0.232, 0.112), ("d2", "druid", "2-0-4", 0.19, 0.129),
    ("d3", "druid", "2-0-4", 0.072, 0.581), ("ans_blimps_ace", "ace", "4-0-0", 0.12, 0.189),
    ("v1", "village", "2-3-0", 0.099, 0.666), ("sp1", "spike", "2-0-5", 0.099, 0.811),
    ("bm1", "bomb", "2-0-3", 0.115, 0.317), ("d4", "druid", "2-0-4", 0.756, 0.624),
    ("d5", "druid", "1-0-2", 0.767, 0.376), ("d6", "druid", "0-0-0", 0.783, 0.572),
    ("bomb1", "bomb", "3-0-2", 0.553, 0.922), ("druid1", "druid", "0-3-2", 0.745, 0.317),
    ("ans_blimps_ace2", "ace", "4-0-0", 0.671, 0.896), ("a2", "alchemist", "4-2-0", 0.826, 0.445),
    ("ans_blimps_bomb", "bomb", "0-4-0", 0.051, 0.385), ("ans_blimps_super", "super", "2-3-0", 0.061, 0.3),
    ("ans_blimps_ace3", "ace", "4-0-0", 0.767, 0.845), ("ans_blimps_super2", "super", "2-0-0", 0.783, 0.692),
    ("ans_blimps_super3", "super", "0-0-0", 0.607, 0.913), ("ans_blimps_bomb2", "bomb", "0-3-0", 0.82, 0.598),
    ("ans_blimps_sniper", "sniper", "2-0-3", 0.783, 0.768), ("ans_blimps_sniper2", "sniper", "2-0-3", 0.826, 0.785),
    ("ans_blimps_bomb3", "bomb", "0-3-0", 0.826, 0.368), ("ans_blimps_sniper3", "sniper", "2-0-3", 0.826, 0.658),
    ("bomb2", "bomb", "0-3-2", 0.083, 0.743), ("dart1", "dart", "2-0-4", 0.729, 0.257),
    ("ans_blimps_heli", "heli", "3-0-0", 0.724, 0.146), ("ans_blimps_boomerang", "boomerang", "0-0-0", 0.029, 0.572),
    ("druid3", "druid", "0-0-0", 0.056, 0.794), ("druid4", "druid", "0-0-0", 0.767, 0.257),
]


def _setup(one_life=True):
    """The round-88 executor: the board standing, the plan used up (its last
    step, the Super Mines, was bought at round 83), $35,965 in hand."""
    m = G.apply(SETUP.MapModel(MAP, SETUP.LAYOUTS["16:10"]["playfield"]), G.load(MAP))
    g = SETUP.SIM.CashGame(MODE, "obyn", m)
    g.cash, g.round = CASH, RND
    ex = S.Executor(g, m, S.load_all()[BUILD], MODE, SETUP.SIM.full_account())
    for tid, kind, cross, x, y in BOARD_88:
        g.towers[tid] = SETUP.SIM.Placed(tid, kind, x, y, tiers=[int(c) for c in cross.split("-")])
    ex.purchased = len(g.towers)
    ex.idx = len(ex.plan)
    ex._init_threats()
    ex.cash_seen = CASH
    if not one_life:
        ex.rules = dict(ex.rules, one_life=False)
    return ex


def _ready():
    return D.available() and TH.available()


def _rating(ex, rnd):
    """The damage model's margin for one round on the board as it stands."""
    return ex._forecast().worst(list(ex.g.towers.values()), [rnd])[0]


def test_the_board_reads_as_it_did_live():
    """Round 88's blimps read short in the blimp check (0.7x of 2.5x live)
    and held in the damage model (1.33 live); the model rates round 90 as
    lost (0.07 live)."""
    if not _ready():
        return
    ex = _setup()
    load = ex.blimp_load(RND)
    assert ex.blimp_ratio(load) < ex.ramp_bar(load), ex.blimp_ratio(load)
    assert _rating(ex, RND) >= 1.0, _rating(ex, RND)
    assert _rating(ex, DDT_ROUND) < ex.LIKELY_LOST, _rating(ex, DDT_ROUND)
    ramp = ex._ramp_due(RND)
    assert ramp and ramp[0] == RND, ramp and ramp[0]
    print(f"round {RND}: blimp check {ex.blimp_ratio(load):.1f}x of {ex.ramp_bar(load):.1f}x, "
          f"model {_rating(ex, RND):.2f}; round {DDT_ROUND}: model {_rating(ex, DDT_ROUND):.2f}")


def test_the_blimp_check_yields_to_the_lost_round():
    """The threat tick neither buys the MOAB Eliminator for round 88 nor
    holds cash for it: the $35,965 is left to what reinforcing finds for the
    round that ends the game."""
    if not _ready():
        return
    ex = _setup()
    assert ex._ramp_yields_to_lost_round(RND, RND)
    ex.saving_for_threat = False
    assert ex._threat_tick(CASH, RND) is None
    assert not ex.g.bought, ex.g.bought
    assert not ex.saving_for_threat and not getattr(ex, "held_cash", 0.0)


def test_with_lives_to_spare_the_blimp_check_keeps_its_turn():
    """The rule is for one-life games: with lives to spare a round rated low
    costs lives, not the game, and the blimp check goes on as before."""
    if not _ready():
        return
    ex = _setup(one_life=False)
    assert not ex._ramp_yields_to_lost_round(RND, RND)


def test_a_blimp_round_the_model_rates_weak_keeps_the_blimp_check():
    """When the damage model itself rates the blimp round under 1, both
    estimates call it short and it comes first: no yielding. Round 90 is
    such a round on this board (its DDTs are blimps)."""
    if not _ready():
        return
    ex = _setup()
    assert not ex._ramp_yields_to_lost_round(DDT_ROUND, RND)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
