"""With one life, reinforcing judges purchases on the first round of the
look-ahead that ends the game, however far off, and reaches the tier 5s that
hold it.

Pat's Pond Impoppable (2026-11-12 23:33-00:00, chimps_sub_druid_water; loss
case 20261113_000355_PatsPond_impoppable): from round 81 the damage model
rated round 90 - three fortified camo DDTs - at 0.06-0.07, and about $98k
came in before it. Three things kept that cash from round 90 (backlog 110):

1. the blimp check bought and held for the blimp rounds before it, which the
   model rated as held (Executor._ramp_yields_to_lost_round,
   tests/test_ramp_yields_to_lost_round_offline.py);
2. reinforce._look looked for a game-ending round only ENDING_LOOKAHEAD = 3
   rounds ahead, so at rounds 81, 83 and 86 it judged purchases on rounds 87,
   92 and 94 - with one life it now judges on the first round of the whole
   look-ahead that ends the game, and saves for it from the cash and the
   income until then (save_target, game_ending);
3. options() offers one tier at a time and at most MAX_OPTIONS of them: the
   bare ans_blimps_boomerang's MOAB Domination ($65,790, round 90 -> 1.6)
   was never offered, with a big bank the trimmed list dropped the $25,800
   Crossbow Master, and the purchases were ranked by lives saved at half
   strength, mostly in round 88, which the board holds at full strength
   (heli -> 4-0-0, "0.07 -> 0.07"). Now the tier 5s the standing towers grow
   into are offered (growth_options) and, when the judged round ends a
   one-life game, ranked by what they do to that round (holding_pick,
   best_holder).

Rated on the lost game's own board at the start of round 88 (the board of
tests/test_ramp_yields_to_lost_round_offline.py). Slow: a few minutes.
Run: python tests/test_reinforce_lost_round_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from btd6bot import reinforce as R                      # noqa: E402
import test_ramp_yields_to_lost_round_offline as CASE   # noqa: E402  (the round-88 board)

END = 100
DDT_ROUND = CASE.DDT_ROUND        # 90


def _look(cash, rnd=CASE.RND, one_life=True):
    """best() on the case's board with `cash` at round `rnd`, without the
    look's time budget (the live budget only spreads the same ratings over
    several passes: tests/test_reinforce_budget_offline.py)."""
    ex = CASE._setup(one_life=one_life)
    ex.g.cash, ex.g.round = cash, rnd
    saved = R.LOOK_BUDGET_S
    R.LOOK_BUDGET_S = 1e9
    try:
        return R.best(ex, ex._forecast(), cash, rnd, END, lives=1)
    finally:
        R.LOOK_BUDGET_S = saved


def test_round_88_buys_for_the_round_that_ends_the_game():
    """The live look at round 88 with $35,965 bought the heli's 4-0-0 for
    round 88's blimps, "0.07 -> 0.07" for round 90. Now the purchase is
    judged on round 90 alone: a Crossbow Master (a dart to 0-2-5) lifts it
    to about 0.45, and nothing the cash buys does more."""
    if not CASE._ready():
        return
    status, found = _look(CASE.CASH)
    assert status == "buy", status
    option, worst, before, after = found
    assert worst == DDT_ROUND, worst
    assert "heli" not in option.what, option.what
    assert after >= 0.4 > before, (option.what, before, after)
    print(f"round 88, ${CASE.CASH}: {option.what} - round 90 {before:.2f} -> {after:.2f}")


def test_a_bank_that_pays_the_moab_domination_buys_it():
    """With $66,000 at round 88 the live look ended in a Sky Shredder (0.07).
    The bare boomerang's MOAB Domination ($65,790) holds round 90 and round
    93's DDTs too, so it comes before the cheaper Glaive Lord, which holds
    round 90 alone (best_holder)."""
    if not CASE._ready():
        return
    status, found = _look(66_000)
    assert status == "buy", status
    option, worst, before, after = found
    assert worst == DDT_ROUND and after >= 1.0, (worst, after)
    assert option.goal == {"do": "upgrade", "id": "ans_blimps_boomerang", "to": "0-2-5"}, option
    print(f"round 88, $66000: {option.what} - round 90 {before:.2f} -> {after:.2f}")


def test_from_round_81_the_look_saves_for_round_90():
    """Round 90 is nine rounds ahead of round 81, past ENDING_LOOKAHEAD. With
    one life the look judges on it anyway, finds nothing $35,802 buys that
    holds it, and saves for a tier 5 that does."""
    if not CASE._ready():
        return
    status, found = _look(35_802, rnd=81)
    assert status == "save", (status, found and found[0].what)
    option, worst, before, lifted = found
    assert worst == DDT_ROUND and lifted >= 1.0 and option.cost > 35_802, (option.what, worst, lifted)
    assert option.goal and "5" in option.goal["to"], option
    print(f"round 81, $35802: saving for {option.what} (${option.cost:.0f}) - round 90 -> {lifted:.2f}")


def test_with_lives_to_spare_the_far_round_waits_for_its_turn():
    """Without one life a round nine rounds off is left to the saving rules
    as before: the look at round 81 does not judge on round 90."""
    if not CASE._ready():
        return
    status, found = _look(35_802, rnd=81, one_life=False)
    assert not found or found[1] != DDT_ROUND, (status, found[0].what, found[1])


def test_growth_options_reach_a_bare_towers_tier_5():
    """options() offers a bare tower one tier at a time; growth_options
    offers its tier 5s, each costed at the whole path and carrying it as the
    goal - the Domination only once the budget pays all of it."""
    if not CASE._ready():
        return
    ex = CASE._setup()
    goal = {"do": "upgrade", "id": "ans_blimps_boomerang", "to": "0-2-5"}
    assert all(o.goal != goal for o in R.options(ex, 66_000, weak=DDT_ROUND))
    grown = [o for o in R.growth_options(ex, 66_000) if o.goal == goal]
    assert len(grown) == 1 and 65_000 < grown[0].cost <= 66_000, grown
    assert grown[0].step == {"do": "upgrade", "id": "ans_blimps_boomerang", "to": "0-0-1"}, grown[0].step
    assert all(o.goal != goal for o in R.growth_options(ex, 60_000))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
