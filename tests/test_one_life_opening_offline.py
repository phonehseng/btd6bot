"""Offline: one-life games (CHIMPS) and their first rounds.

* A one-life game never starts with a single non-hero tower
  (match.Match._lone_opener): Winter Park CHIMPS (2026-11-05) began round 6
  with one $430 buccaneer, the plan's $280 tack unaffordable, and a red got
  through 12 seconds in.
* An untested build in a one-life mode is priced by how the account's
  builds did in their first game there (planner.first_game_factor): CHIMPS
  builds won 1 of their first 5, each priced 0.82-0.85 untested.

Run: python tests/test_one_life_opening_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import match as M  # noqa: E402
from btd6bot import planner as P  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402
from btd6bot.strategy import rules  # noqa: E402


def _match(mode, kinds):
    """A Match with only the pieces _lone_opener reads: the mode's rules and
    the towers placed so far."""
    m = M.Match.__new__(M.Match)
    m.ex = N(rules=rules(mode))
    m.g = N(towers={f"t{i}": N(kind=k) for i, k in enumerate(kinds)})
    return m


def test_chimps_with_one_tower_wants_a_second():
    assert rules("chimps").get("one_life")
    assert _match("chimps", ["buccaneer"])._lone_opener()
    assert _match("chimps", ["hero", "buccaneer"])._lone_opener()      # the hero does not count


def test_two_towers_or_lives_to_spare_are_left_alone():
    assert not _match("chimps", ["buccaneer", "tack"])._lone_opener()
    assert not _match("chimps", [])._lone_opener()      # nothing down: _place_starter's own case
    assert not _match("hard", ["buccaneer"])._lone_opener()


def _priced_match(mode, kinds, forbidden=()):
    """_match plus what _opener_reserve reads: the opener kinds, which of
    them the game allows, and the Hard price table (CHIMPS is priced as Hard)."""
    from btd6bot import towers as T
    from btd6bot.strategy import Executor
    m = _match(mode, kinds)
    m.ex.CHEAP_OPENERS = Executor.CHEAP_OPENERS
    m.ex.kind_allowed = lambda k: k not in forbidden
    m.g.price = lambda k: T.price(T.TOWERS[k]["cost"], "hard")
    return m


def test_one_life_plan_keeps_back_a_second_towers_price():
    """Alpine Run CHIMPS (2026-11-06): the plan took the $650 start to $15
    with one tack, and the lone tack leaked in round 6. While one tower
    stands, the cheapest opener's price is kept back from the plan."""
    from btd6bot import towers as T
    m = _priced_match("chimps", ["tack"])
    dart = T.price(T.TOWERS["dart"]["cost"], "hard")
    assert m._opener_reserve() == dart
    # the cheapest kind the game still allows sets the reserve
    m = _priced_match("chimps", ["tack"], forbidden=("dart",))
    allowed = [T.price(T.TOWERS[k]["cost"], "hard") for k in m.ex.CHEAP_OPENERS if k != "dart"]
    assert m._opener_reserve() == min(allowed)


def test_no_reserve_with_lives_to_spare_or_two_towers():
    assert _priced_match("hard", ["tack"])._opener_reserve() == 0
    assert _priced_match("chimps", ["tack", "dart"])._opener_reserve() == 0
    assert _priced_match("chimps", ["hero"])._opener_reserve() == 0   # the first tower is not held back


def test_build_without_starter_keeps_the_entrance_openers():
    m = _priced_match("chimps", ["buccaneer"])
    m.ex.strat = {"id": "x"}
    steps = m._starter_steps()
    assert [s["kind"] for s in steps] == list(m.ex.CHEAP_OPENERS)
    assert all(s["segment"] == [0.05, 0.45] and "at" not in s for s in steps)


def test_build_names_its_starter_spot_and_kind():
    """Sulfur Springs CHIMPS (2026-11-07 18:43): the starter dart, refused at
    its entrance spot, went to (0.473, 0.871) and the game was lost in round
    9. A build's `starter: {kind, at}` is tried first at its spot (Executor's
    `at` fallback moves it a few cells when refused); the entrance openers
    stay behind it."""
    from btd6bot import towers as T
    m = _priced_match("chimps", ["buccaneer"])
    m.ex.strat = {"starter": {"kind": "tack", "at": [0.3, 0.13]}}
    steps = m._starter_steps()
    assert steps[0] == {"do": "place", "id": "starter", "kind": "tack", "role": "dps", "at": [0.3, 0.13]}
    assert [s["kind"] for s in steps[1:]] == [k for k in m.ex.CHEAP_OPENERS if k != "tack"]
    # the plan keeps back the named starter's price, not the cheapest opener's
    assert m._opener_reserve() == T.price(T.TOWERS["tack"]["cost"], "hard")
    # a kind the game forbids is ignored: back to the entrance openers
    m = _priced_match("chimps", ["buccaneer"], forbidden=("tack",))
    m.ex.strat = {"starter": {"kind": "tack", "at": [0.3, 0.13]}}
    assert "tack" not in [s["kind"] for s in m._starter_steps()]
    assert m._opener_reserve() == T.price(T.TOWERS["dart"]["cost"], "hard")


def test_build_can_opt_out_of_the_starter():
    """Sulfur Springs CHIMPS (2026-11-07 18:43, 19:57): the recordings show
    the starter dart never threw a dart from either spot, and round 9 was
    lost with the boat $10 short of Double Shot. `starter: none`: a lone
    opener stays alone and the plan keeps nothing back for a second tower."""
    m = _priced_match("chimps", ["buccaneer"])
    m.ex.strat = {"starter": "none"}
    assert not m._lone_opener()
    assert m._opener_reserve() == 0
    # without the opt-out the same board still wants its second tower
    m.ex.strat = {"id": "x"}
    assert m._lone_opener()


def test_validate_checks_the_starter_field():
    from btd6bot.strategy import validate
    base = {"id": "x", "modes": ["chimps"], "plan": [{"do": "place", "id": "b1", "kind": "buccaneer"}]}
    assert validate(dict(base, starter="none")) == []
    assert validate(dict(base, starter="nothing"))
    assert validate(dict(base, starter={"kind": "dart", "at": [0.2, 0.4]})) == []
    assert validate(dict(base, starter={"kind": "dart"})) == []
    assert validate(dict(base, starter={"kind": "laser", "at": [0.2, 0.4]}))
    assert validate(dict(base, starter={"kind": "dart", "at": [0.2]}))
    assert validate(dict(base, starter={"kind": "dart", "at": [0.2, 0.4], "x": 1}))


def _spec(mode):
    return next(x for x in P.EXAMPLE_STRATEGIES if mode in x.modes)


def test_first_games_lost_doubt_untested_builds_in_one_life_modes():
    acc = AccountState()
    acc.apply_level(60)
    s = _spec("chimps")
    assert P.first_game_factor(acc, s, "chimps") == 1.0          # no record: 4/4
    clean = P.prior_win_probability(acc, s, "Monkey Meadow", "chimps")
    # four other builds lost their first CHIMPS game, one won
    for i in range(4):
        acc.record_result("Logs", "chimps", f"build_{i}", False, round_reached=40)
    acc.record_result("Logs", "chimps", "build_ok", True, round_reached=100)
    # second games of the same build do not count again
    acc.record_result("Logs", "chimps", "build_0", True, round_reached=100)
    k = P.FIRST_GAME_PRIOR_GAMES
    f = P.first_game_factor(acc, s, "chimps")
    assert abs(f - (1 + k) / (5 + k)) < 1e-9, f
    doubted = P.prior_win_probability(acc, s, "Monkey Meadow", "chimps")
    assert abs(doubted - min(0.98, max(0.01, clean * f))) < 1e-9, (clean, f, doubted)


def test_played_builds_and_modes_with_lives_keep_their_prior():
    acc = AccountState()
    acc.apply_level(60)
    for i in range(4):
        acc.record_result("Logs", "chimps", f"build_{i}", False, round_reached=40)
        acc.record_result("Logs", "hard", f"build_{i}", False, round_reached=40)
    s = _spec("chimps")
    acc.record_result("Logs", "chimps", s.id, False, round_reached=50)
    assert P.first_game_factor(acc, s, "chimps") == 1.0     # its own record decides now
    assert P.first_game_factor(acc, _spec("hard"), "hard") == 1.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
