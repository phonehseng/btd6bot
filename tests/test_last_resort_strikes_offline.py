"""A last-resort pick is skipped after three losses on the same map/mode
with no win (planner.struck_out, LAST_RESORT_STRIKES).

2026-11-08/09: Apopalypse lost Firing Range four times and Dark Path,
Castle Revenge and Sunken Columns three times each, as last resorts, before
each was excluded by hand. Run: python tests/test_last_resort_strikes_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import planner  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402


def _game(acc, map_name, mode, strategy, won):
    acc.history.append({"t": "2026-11-09T11:00:00", "map": map_name, "mode": mode,
                        "strategy": strategy, "won": won})


def test_three_losses_without_a_win_strike_out():
    acc = AccountState()
    for _ in range(2):
        _game(acc, "Firing Range", "apopalypse", "apopalypse_ninja_sniper", False)
    assert not planner.struck_out(acc, "apopalypse_ninja_sniper", "Firing Range", "apopalypse")
    _game(acc, "Firing Range", "apopalypse", "apopalypse_ninja_sniper", False)
    assert planner.struck_out(acc, "apopalypse_ninja_sniper", "Firing Range", "apopalypse")
    assert planner.build_map_record(acc, "apopalypse_ninja_sniper", "Firing Range", "apopalypse") == (0, 3)


def test_a_win_or_another_build_or_mode_is_not_struck():
    acc = AccountState()
    for _ in range(3):
        _game(acc, "Firing Range", "apopalypse", "apopalypse_ninja_sniper", False)
    assert not planner.struck_out(acc, "hard_ninja_alch_sun", "Firing Range", "apopalypse")
    assert not planner.struck_out(acc, "apopalypse_ninja_sniper", "Firing Range", "half_cash")
    assert not planner.struck_out(acc, "apopalypse_ninja_sniper", "Ravine", "apopalypse")
    _game(acc, "Firing Range", "apopalypse", "apopalypse_ninja_sniper", True)
    assert not planner.struck_out(acc, "apopalypse_ninja_sniper", "Firing Range", "apopalypse")


def test_a_map_mode_every_build_lost_is_played_last():
    """Dark Dungeons Military Only, 2026-11-04..09: five losses by four builds,
    none of them struck out on its own."""
    acc = AccountState()
    for sid in ("military_heli_sniper", "military_heli_sniper", "solo_sniper", "solo_ace"):
        _game(acc, "Dark Dungeons", "military_only", sid, False)
    assert not planner.struck_out(acc, "solo_heli", "Dark Dungeons", "military_only")
    assert planner.map_mode_record(acc, "Dark Dungeons", "military_only") == (0, 4)
    assert planner.map_struck_out(acc, "Dark Dungeons", "military_only")
    assert not planner.map_struck_out(acc, "Dark Dungeons", "magic_only")
    _game(acc, "Dark Dungeons", "military_only", "solo_heli", True)
    assert not planner.map_struck_out(acc, "Dark Dungeons", "military_only")


def test_the_untrimmed_stats_count_when_the_history_has_rolled_over():
    """Ravine Magic Only, 2026-11-10: three losses in strategy_stats but only
    two left in the 500-game history - the stats decide."""
    acc = AccountState()
    acc.strategy_stats["Ravine|magic_only|magic_obyn_ninja_wizard"] = {"wins": 0, "losses": 3, "games": 3}
    for _ in range(2):
        _game(acc, "Ravine", "magic_only", "magic_obyn_ninja_wizard", False)
    assert planner.struck_out(acc, "magic_obyn_ninja_wizard", "Ravine", "magic_only")


def test_a_hopeless_map_mode_is_not_a_last_resort():
    """A ceiling under HOPELESS_CEILING plus three losses across builds:
    skipped (Last Resort Primary Only, ceiling 0.09, 2026-11-10). Two losses,
    or a ceiling at or above it, or a medal on record: still played."""
    from unittest import mock
    acc = AccountState()
    acc.strategy_stats["Last Resort|primary_only|solo_bomb"] = {"wins": 0, "losses": 2, "games": 2}
    with mock.patch.object(planner, "model_ceiling", lambda m, mode: 0.09):
        assert not planner.hopeless(acc, "Last Resort", "primary_only")
        acc.strategy_stats["Last Resort|primary_only|primary_core"] = {"wins": 0, "losses": 1, "games": 1}
        acc._map_mode_losses = None
        assert planner.hopeless(acc, "Last Resort", "primary_only")
    with mock.patch.object(planner, "model_ceiling", lambda m, mode: 1.41):
        assert not planner.hopeless(acc, "Last Resort", "primary_only")


if __name__ == "__main__":
    test_a_hopeless_map_mode_is_not_a_last_resort()
    test_the_untrimmed_stats_count_when_the_history_has_rolled_over()
    test_three_losses_without_a_win_strike_out()
    test_a_win_or_another_build_or_mode_is_not_struck()
    test_a_map_mode_every_build_lost_is_played_last()
    print("ok")
