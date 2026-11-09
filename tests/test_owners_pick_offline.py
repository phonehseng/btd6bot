"""The NEXT file names the next game (Runner.owners_pick): "Map / mode
[/ strategy]", played once ahead of the planner. Written so the owner can
send the bot into a CHIMPS run on a chosen map (2026-11-05) and watch it.
CHIMPS needs the map's Impoppable medal, and a one-life pick under its bar
needs "!force" (more in test_chimps_planner_offline.py).
Offline: a temporary NEXT file and a full account.
Run: python tests/test_owners_pick_offline.py"""
import logging
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import runner as R               # noqa: E402
from btd6bot.strategy import load_all         # noqa: E402

logging.getLogger("runner").setLevel(logging.CRITICAL)


def pick(line):
    """owners_pick for a NEXT file holding `line` (None: no file)."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "NEXT"
        if line is not None:
            f.write_text(line, encoding="utf-8")
        bot = R.Bot.__new__(R.Bot)
        bot.account = F.full_account()
        bot.account.medals = {"Alpine Run": {"impoppable": True}}   # unlocks its CHIMPS
        bot.strats = load_all()
        with mock.patch.object(R, "NEXT_FILE", f):
            plan = bot.owners_pick(R.planner_specs(bot.strats, bot.account))
            left = f.exists()
    return plan, left


def test_a_chimps_pick_becomes_a_plan_with_the_best_chimps_strategy():
    plan, left = pick("Alpine Run / chimps !force")
    assert plan is not None and not left
    assert (plan.map, plan.mode_key, plan.mode, plan.difficulty) == ("Alpine Run", "chimps", "chimps", "hard")
    # the map's own CHIMPS build (strategies/maps, 2026-11-05) beats the general one
    assert plan.strategy_id == "alpinerun_chimps", plan.strategy_id
    assert plan.phase == "OWNER"


def test_a_named_strategy_is_used():
    plan, _ = pick("alpine run / chimps / chimps_ninja_sun !force")
    assert plan.strategy_id == "chimps_ninja_sun"


def test_bad_lines_are_dropped_and_not_retried():
    for line in ("Alpine Run", "Nowhere / chimps", "Alpine Run / nosuchmode", "Alpine Run / chimps / nosuchstrat"):
        plan, left = pick(line)
        assert plan is None and not left, line


def test_a_beaten_pick_is_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "NEXT"
        f.write_text("Alpine Run / chimps", encoding="utf-8")
        bot = R.Bot.__new__(R.Bot)
        bot.account = F.full_account()
        bot.account.has_medal = lambda m, mode: True
        bot.strats = load_all()
        with mock.patch.object(R, "NEXT_FILE", f):
            assert bot.owners_pick(R.planner_specs(bot.strats, bot.account)) is None


def test_a_beaten_map_takes_an_achievement_build():
    """Achievement replays are allowed (owner, 2026-11-07): Logs Hard is
    beaten, but ach_kali_maaaaaaaa is played there (2026-11-09 14:34 the
    NEXT line was refused as "already beaten"). A general build still is not."""
    for line, want in (("Logs / hard / ach_kali_maaaaaaaa !force", "ach_kali_maaaaaaaa"),
                       ("Logs / hard / hard_ninja_alch_sun", None)):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "NEXT"
            f.write_text(line, encoding="utf-8")
            bot = R.Bot.__new__(R.Bot)
            bot.account = F.full_account()
            bot.account.has_medal = lambda m, mode: True
            bot.strats = load_all()
            with mock.patch.object(R, "NEXT_FILE", f):
                plan = bot.owners_pick(R.planner_specs(bot.strats, bot.account))
        if want is None:
            assert plan is None, line
        else:
            assert plan is not None and plan.strategy_id == want and not plan.first_time, line


def test_no_file_means_the_planner_decides():
    assert pick(None) == (None, False)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
