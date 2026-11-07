"""Safe mode lets open Beginner medals go first (CHIMPS with the map's own build).

The owner's order since 2026-11-05: black borders map tier by tier, Beginner
maps first. Safe mode (the loss circuit breaker) plays only games at
p >= CONFIDENT_P, while an untested map build is capped just under it, so the
Beginner CHIMPS builds would have waited behind every confident game on
every map. The owner chose (2026-11-05 15:30) to let them go first; nothing
else in safe mode changes.
Run: python tests/test_beginner_before_safe_mode_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import runner as R               # noqa: E402
from btd6bot import planner as P               # noqa: E402
from btd6bot.planner import CATEGORY_EASE     # noqa: E402
from btd6bot.strategy import load_all         # noqa: E402

BEGINNER, ADVANCED = CATEGORY_EASE["beginner"], CATEGORY_EASE["advanced"]


def first(cands, benched=()):
    return R.beginner_before_safe_mode(cands, lambda m, mode: (m, mode) in benched)


def specs():
    return {s.id: s for s in R.planner_specs(load_all(), F.full_account())}


def cand(s, map_name, mode="chimps", ease=BEGINNER, ok=True, tier="HS", p=0.84):
    return NS(s=s, map=map_name, mode=mode, ease=ease, ok=ok, tier=tier, p=p)


def test_an_open_beginner_medal_clearing_its_bar_goes_first():
    """2026-11-06: the Beginner maps without a black border lack Apopalypse
    too. A general build clearing its own bar goes first; one under it, or a
    harder map's medal, does not."""
    apop = specs()["apopalypse_ninja_sniper"]
    cands = [cand(apop, "Park Path", mode="apopalypse", p=0.80),
             cand(apop, "Park Path", mode="apopalypse", ok=False, tier=None, p=0.5),
             cand(apop, "Cargo", mode="apopalypse", ease=ADVANCED, p=0.80)]
    assert first(cands) == [cands[0]]


def test_only_beginner_chimps_with_the_maps_own_build_go_first():
    sp = specs()
    own, general = sp["endoftheroad_chimps"], sp["chimps_ninja_sun"]
    cands = [cand(own, "End Of The Road"),
             cand(general, "End Of The Road"),                   # not made for the map
             cand(own, "End Of The Road", ok=False, tier=None),  # under its bar
             cand(own, "End Of The Road", ease=ADVANCED)]       # not a Beginner map
    picked = first(cands)
    assert picked == [cands[0]], picked


def test_a_benched_map_is_not_let_through():
    own = specs()["endoftheroad_chimps"]
    assert first([cand(own, "End Of The Road")], benched={("End Of The Road", "chimps")}) == []



def test_beginner_chimps_map_builds_are_not_scaled_by_first_games():
    """The caretaker's first-game factor (2 of 5 CHIMPS first games won)
    scales every untested one-life build; the owner's Beginner CHIMPS map
    builds keep their own gate, every other build is still scaled.

    Park Path's build is the example: its gate (base_success 0.85) clears
    the CHIMPS bar. End Of The Road's was the example until 5e7180f held it
    back to 0.5 (the replay's cash gap), which is under the bar by design."""
    acc = F.full_account()
    acc.history = [{"strategy": f"b{i}", "mode": "chimps", "won": i < 1, "t": f"2026-11-05T1{i}"}
                   for i in range(5)]
    sp = specs()
    own, general = sp["parkpath_chimps"], sp["chimps_ninja_sun"]
    assert P.owner_first_build(acc, own, "Park Path")
    assert not P.owner_first_build(acc, general, "Park Path")
    assert not P.owner_first_build(acc, own, "Cargo"), "a harder map is not put first"
    assert P.first_game_factor(acc, general, "chimps") < 1.0, "the general build is still doubted"
    assert P.win_probability(acc, own, "Park Path", "chimps")[0] >= P.p_threshold("chimps")


def test_beginner_map_builds_are_not_halved_by_the_fast_track_doubt():
    """2026-11-06: the Beginner Half Cash map builds passed every replay on
    the account's Fast Track opening and were halved to 0.45 by the general
    Fast Track doubt. A Beginner map build keeps its own gate; a general
    build in the same game is still doubted."""
    import dataclasses
    acc = F.full_account()
    acc.boosts = dict(getattr(acc, "boosts", None) or {}, fast_track=True)
    sp = specs()
    own = dataclasses.replace(sp["parkpath_chimps"], id="parkpath_half_cash_test",
                              modes=frozenset({"half_cash"}), base_success={"half_cash": 0.85})
    general = sp["hard_sniper_elite"]
    p_own = P.win_probability(acc, own, "Park Path", "half_cash")[0]
    p_general = P.win_probability(acc, general, "Park Path", "half_cash")[0]
    assert p_own >= P.p_threshold("half_cash"), p_own
    assert P.owner_first_build(acc, own, "Park Path") and not P.owner_first_build(acc, general, "Park Path")
    assert p_general < P.p_threshold("half_cash"), p_general


def test_games_before_a_builds_revision_do_not_count():
    """2026-11-06: Carved, Winter Park and Lotus Island CHIMPS each lost once
    on a version since repaired; that loss held them under the bar. With
    `planner: revised:` only the games after the repair count."""
    import dataclasses
    acc = F.full_account()
    own = specs()["carved_chimps"]
    acc.history = [{"map": "Carved", "mode": "chimps", "strategy": own.id, "won": False,
                    "t": "2026-11-05T16:12:20"}]
    acc.strategy_stats = {"Carved|chimps|" + own.id: {"wins": 0, "losses": 1, "games": 1}}
    old = dataclasses.replace(own, revised=None)
    new = dataclasses.replace(own, revised="2026-11-05T19:02")
    assert P.build_record(acc, old, "Carved", "chimps") == (0, 1)
    assert P.build_record(acc, new, "Carved", "chimps") == (0, 0)
    acc.history.append({"map": "Carved", "mode": "chimps", "strategy": own.id, "won": False,
                        "t": "2026-11-06T20:00:00"})
    assert P.build_record(acc, new, "Carved", "chimps") == (0, 1), "a loss after the repair counts"


def test_the_calibration_ignores_games_before_a_revision_too():
    """The planner scores candidates with the calibration, which read the
    aggregate record: the repaired Carved CHIMPS build rated 0.29 there and
    0.85 on its own record, so it was still never played."""
    import dataclasses
    acc = F.full_account()
    own = specs()["carved_chimps"]
    acc.history = [{"map": "Carved", "mode": "chimps", "strategy": own.id, "won": False,
                    "t": "2026-11-05T16:12:20"}]
    acc.strategy_stats = {"Carved|chimps|" + own.id: {"wins": 0, "losses": 1, "games": 1}}
    old = dataclasses.replace(own, revised=None)
    new = dataclasses.replace(own, revised="2026-11-05T19:02")
    p_old = P.win_probability(acc, old, "Carved", "chimps", calib=P._Calibration(acc, {old.id: old}))[0]
    p_new = P.win_probability(acc, new, "Carved", "chimps", calib=P._Calibration(acc, {new.id: new}))[0]
    assert p_new >= P.p_threshold("chimps") > p_old, (p_old, p_new)


def test_the_owners_xp_towers_are_focused_without_a_paragon():
    """2026-11-07, the owner: "mermonkey and sky warden need more xp". Neither
    has a paragon, so the paragon focus never steered XP to them; while they
    have locked upgrades they are focus towers at full closeness."""
    acc = F.full_account()
    for t in P.OWNER_XP_TOWERS:
        acc.unlocked_upgrades[t] = [2, 2, 0]
        acc.tower_xp[t] = 0
    focus = {g.tower: g for g in P.paragon_status(acc).focus}
    for t in P.OWNER_XP_TOWERS:
        if t in acc.unlocked_towers:
            assert t in focus and focus[t].closeness == 1.0, (t, list(focus))

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all tests passed")
