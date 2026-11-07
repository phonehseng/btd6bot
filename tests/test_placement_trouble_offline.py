"""Maps where the bot could not build its defence are trusted less (no game needed).

Tricky Tracks, 2026-11-02/03: Easy failed twice with "no defence could be
placed" (errors, not losses, so the planner learned nothing), then was played
at p=0.98 in safe mode: two snipers and the hero went down, every later spot
was refused, a sniper step was given up, and the game was lost at round 27.
Every other mode on the map still looked just as safe.

Covers:
  * note_placement_trouble lowers the prior of every mode on the map (for
    general builds and builds allowed on several maps) under the safe-mode
    bar; other maps keep theirs;
  * the record survives a save/load and a win on the map clears it;
  * the runner notes "no defence" errors and lost games with a step given
    up after refused spots, not wins-with-refusals, losses with an outside
    cause, or steps given up after 0 refused spots (no legal spot in reach
    on the bot's own map data: the build, not the ground);
  * the map's own build (strategies/maps) is not doubted for it, except on
    moving ground (Geared, Sanctuary).
Run: python tests/test_placement_trouble_offline.py"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import planner  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402
from btd6bot.runner import Bot  # noqa: E402

MAP, OTHER = "Tricky Tracks", "Monkey Meadow"


MODES = ("easy", "medium", "hard")
# a general build and one made for Tricky Tracks, both declared near-certain
SPECS = [planner.StrategySpec(id=sid, towers={"dart": (0, 0, 0)}, modes=frozenset(MODES),
                              base_success={m: 0.98 for m in MODES}, maps=maps)
         for sid, maps in (("t_general", None), ("t_special", frozenset({MAP, OTHER})))]


def priors(account, map_name):
    """{mode: best prior of the two test builds} on ``map_name``."""
    return {mode: max(planner.prior_win_probability(account, s, map_name, mode) for s in SPECS)
            for mode in MODES}


def test_prior_drops_on_every_mode():
    a = AccountState()
    before = priors(a, MAP)
    other_before = priors(a, OTHER)
    assert a.note_placement_trouble(MAP) == 1
    after = priors(a, MAP)
    for mode, p in after.items():
        assert p <= before[mode] * planner.MAP_LOSS_FACTOR + 1e-9, (mode, before[mode], p)
        assert p < 0.85, (mode, p)
    assert priors(a, OTHER) == other_before


def test_persist_and_clear():
    a = AccountState()
    a.note_placement_trouble(MAP)
    a.note_placement_trouble(MAP)
    with tempfile.TemporaryDirectory() as d:
        b = AccountState.load(a.save(Path(d) / "acct.json"))
    assert b.placement_trouble == {MAP: 2}
    b.note_map_won(MAP)
    assert b.placement_trouble == {}


def test_runner_rules():
    """Bot._note_placement on a stand-in bot (no screen, no game)."""
    saved = []
    acct = AccountState()
    acct.save = lambda *a, **k: saved.append(1)
    bot = SimpleNamespace(account=acct)
    plan = SimpleNamespace(map=MAP)
    note = lambda res: Bot._note_placement(bot, plan, res)  # noqa: E731
    note({"outcome": "victory", "steps_given_up": 3})       # refusals in a win: fine
    assert acct.placement_trouble == {}
    note({"outcome": "defeat", "steps_given_up": 0})        # an ordinary loss
    assert acct.placement_trouble == {}
    note({"outcome": "defeat", "steps_given_up": 1, "outside_cause": "game crash"})
    assert acct.placement_trouble == {}
    note({"outcome": "defeat", "steps_given_up": 2, "steps_refused": 0})   # no spot in reach: the build
    assert acct.placement_trouble == {}
    note({"outcome": "no defence"})
    note({"outcome": "defeat", "steps_given_up": 1, "steps_refused": 1})
    assert acct.placement_trouble == {MAP: 2}
    note({"outcome": "victory"})
    assert acct.placement_trouble == {} and len(saved) == 3   # the first win saved nothing


def test_own_map_build_keeps_its_prior():
    """Peninsula's own Deflation build is not doubted for the trouble
    general builds ran into there; Geared's own build still is (its gears
    turn, so the refusals learned there say little about any spot)."""
    for map_name, doubted in (("Peninsula", False), ("Geared", True)):
        own = planner.StrategySpec(id="t_own", towers={"dart": (0, 0, 0)}, modes=frozenset(MODES),
                                   base_success={m: 0.9 for m in MODES}, maps=frozenset({map_name}))
        a = AccountState()
        before = planner.prior_win_probability(a, own, map_name, "medium")
        a.note_placement_trouble(map_name)
        a.note_placement_trouble(map_name)
        after = planner.prior_win_probability(a, own, map_name, "medium")
        assert (after < before) == doubted, (map_name, before, after)
        assert planner.trouble_applies(SPECS[0], map_name)   # a general build always is


if __name__ == "__main__":
    test_own_map_build_keeps_its_prior()
    test_prior_drops_on_every_mode()
    test_persist_and_clear()
    test_runner_rules()
    print("placement trouble: OK")
