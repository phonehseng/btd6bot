"""Late in a one-life game, with the plan done, idle cash goes into blimp
damage for the blimp rounds the blimp check reads short - even when the
damage model says they hold.

Water Park Impoppable (2026-11-11 02:01-02:28, chimps_sub_druid_water;
journal logs/journal/20261111_020150_WaterPark_impoppable.jsonl): plan and
fill were used up, and rounds 84-87 began with $33,782 / $40,501 / $47,132
/ $47,640. The blimp check read the blimp rounds ahead at 0.4-1.1x of the
2.5x one-life bar; the damage model rated them 2.1-3.75 and overruled the
check at round 86. At round 84 the ramp's pick, "new ace 4-0-0", carried
the id of the ace already standing (ans_blimps_ace) and answered "done"
without a click, so nothing was bought; only at rounds 86-87 did the ramp
put $41k into a sniper 5-0-0, and round 88's 8 BFBs, 18 MOABs and 2 ZOMGs
(then rounds 89-91) ended the game.

Offline on Water Park's geometry, the round-84 board from the log's
purchase lines (tools/rate_board.py board_from_log), the live game's
income between rounds. About a minute: late margins are slow.
Run: python tests/test_idle_blimp_damage_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from btd6bot import dps_model as D                      # noqa: E402
from btd6bot import threats as TH                       # noqa: E402
from test_reinforce_budget_offline import water_park_setup   # noqa: E402

RND, CASH = 84, 33_782
# what the bank grew by from the start of rounds 84, 85 and 86 to the next
# (live: start cash of the next round less the start cash plus what was spent)
INCOME = {84: 11_039, 85: 7_451, 86: 11_268}
LIVE_ROUND_87_CASH, LIVE_ROUND_87_RATIO = 47_640, 0.4
BOARD_84 = [
    ("sb1", "sub", "2-0-4", 0.676, 0.47), ("dr", "dart", "0-2-4", 0.216, 0.232),
    ("sb2", "sub", "2-0-4", 0.291, 0.896), ("hero", "hero", "0-0-0", 0.083, 0.428),
    ("druid1", "druid", "0-1-1", 0.355, 0.845), ("sub1", "sub", "0-2-1", 0.419, 0.913),
    ("dart2", "dart", "2-0-5", 0.532, 0.589), ("a1", "alchemist", "4-2-0", 0.377, 0.47),
    ("druid2", "druid", "2-0-4", 0.778, 0.649), ("druid3", "druid", "2-0-4", 0.617, 0.462),
    ("dr2", "dart", "2-0-4", 0.489, 0.589), ("ans_blimps_ace", "ace", "3-2-0", 0.355, 0.394),
    ("d3", "druid", "2-0-4", 0.745, 0.3), ("v1", "village", "2-3-0", 0.708, 0.913),
    ("bm1", "bomb", "2-0-3", 0.676, 0.836), ("sp1", "spike", "2-0-5", 0.532, 0.428),
    ("d4", "druid", "2-0-4", 0.585, 0.419), ("d5", "druid", "0-0-0", 0.473, 0.436),
    ("d6", "druid", "0-0-0", 0.19, 0.726), ("ace1", "ace", "3-1-0", 0.478, 0.351),
    ("druid5", "druid", "0-3-2", 0.82, 0.453), ("druid6", "druid", "0-3-2", 0.265, 0.462),
    ("a2", "alchemist", "4-2-0", 0.558, 0.376), ("sub2", "sub", "2-0-4", 0.665, 0.172),
    ("sub3", "sub", "2-0-4", 0.772, 0.394), ("spike1", "spike", "2-0-4", 0.088, 0.521),
    ("spike2", "spike", "2-0-3", 0.623, 0.922),
]


def _setup():
    """The round-84 executor with the plan and the fill used up (live, the
    fill's druid upgrades of d5 and d6 never went through), its forecast
    handed over as Match does."""
    ex, fc = water_park_setup(BOARD_84, RND, CASH)
    ex.forecast = fc
    ex.fill = []
    ex._init_threats()
    return ex


def test_a_second_tower_of_a_kind_gets_its_own_id():
    """The blimp check's new-ace option no longer reuses the id of the ace
    standing, so the ramp buys toward it instead of answering "done"."""
    if not D.available() or not TH.available():
        return
    ex = _setup()
    load = ex.blimp_load(RND)
    news = [o for o in ex._dps_options(load) if o["desc"].startswith("new ace")]
    assert news and all(o["steps"][0]["id"] == "ans_blimps_ace2" for o in news), news
    ex.cash_seen = CASH
    assert ex._answer_ramp(RND, load, ex.blimp_ratio(load), CASH, RND) == "bought"


def test_idle_cash_buys_blimp_damage_before_round_87_even_when_the_model_holds():
    """With the damage model overruling every blimp check (as it did for
    round 86), the ramp buys nothing; the idle cash still goes into blimp
    damage for the rounds the check reads short, before round 87."""
    if not D.available() or not TH.available():
        return
    ex = _setup()
    ex._model_holds = lambda *a, **k: True           # the model is sure every blimp round holds
    g = ex.g
    load87 = ex.blimp_load(87)
    before = ex.blimp_ratio(load87)
    for rnd in (84, 85, 86):
        g.round = rnd
        for _ in range(60):
            if not ex.tick(g.cash, rnd):
                break
        g.cash += INCOME[rnd]
    after = ex.blimp_ratio(load87)
    bought = [text for r, text in g.bought]
    assert bought, "nothing bought"
    assert g.cash < LIVE_ROUND_87_CASH / 2, (g.cash, bought)
    assert after >= 2 * LIVE_ROUND_87_RATIO and after > before + 0.3, (before, after, bought)
    print(f"round 87 starts with ${g.cash:.0f} (live ${LIVE_ROUND_87_CASH}); its blimps read "
          f"{before:.2f}x -> {after:.2f}x; {len(bought)} purchases")


def test_idle_blimp_damage_is_for_one_life_only():
    """With lives to lose the rule stays off: the blimp check and the
    model's word decide as before."""
    if not D.available() or not TH.available():
        return
    ex = _setup()
    ex.rules = {**ex.rules, "one_life": False, "lives": 100}
    assert ex._idle_blimp_damage(CASH, RND) is False
    assert not ex.g.bought


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
