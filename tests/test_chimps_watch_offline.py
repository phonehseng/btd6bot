"""The CHIMPS watch list (Runner.watched_chimps_pick): a one-life game that
lost is tried again only once its build (or its watch line) has changed -
in between the bot plays its usual medals instead of a game the model
already expects to lose (owner, 2026-11-13).
Offline: a temporary CHIMPS_WATCH file and state file, a full account.
Run: python tests/test_chimps_watch_offline.py"""
import copy
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
LINE = "Alpine Run / chimps / alpinerun_chimps"


def _bot():
    bot = R.Bot.__new__(R.Bot)
    bot.account = F.full_account()
    bot.account.medals = {"Alpine Run": {"impoppable": True}}   # unlocks its CHIMPS
    bot.strats = load_all()
    return bot


def test_a_build_is_played_once_per_version():
    bot = _bot()
    with tempfile.TemporaryDirectory() as tmp:
        watch, state = Path(tmp) / "CHIMPS_WATCH", Path(tmp) / "tried.json"
        watch.write_text("# comment line\n" + LINE + "\n", encoding="utf-8")
        with mock.patch.object(R, "CHIMPS_WATCH_FILE", watch), mock.patch.object(R, "CHIMPS_WATCH_STATE", state):
            pick = lambda: bot.watched_chimps_pick(R.planner_specs(bot.strats, bot.account))  # noqa: E731
            plan = pick()
            assert plan is not None and plan.strategy_id == "alpinerun_chimps" and plan.mode_key == "chimps"
            assert "CHIMPS_WATCH" in plan.reason
            assert pick() is None, "the same build is not replayed after a loss"
            # the build changes (a fix landed): played again at once
            bot.strats = dict(bot.strats)
            changed = copy.deepcopy(bot.strats["alpinerun_chimps"])
            changed["description"] = str(changed.get("description", "")) + " (fixed)"
            bot.strats["alpinerun_chimps"] = changed
            assert pick() is not None
            assert pick() is None
            # an edited line (a code fix that left the build alone) also retries
            watch.write_text(LINE + "  # rev 2\n", encoding="utf-8")
            assert pick() is not None


def test_no_file_or_a_beaten_map_gives_nothing():
    bot = _bot()
    with tempfile.TemporaryDirectory() as tmp:
        watch, state = Path(tmp) / "CHIMPS_WATCH", Path(tmp) / "tried.json"
        with mock.patch.object(R, "CHIMPS_WATCH_FILE", watch), mock.patch.object(R, "CHIMPS_WATCH_STATE", state):
            assert bot.watched_chimps_pick(R.planner_specs(bot.strats, bot.account)) is None
            watch.write_text(LINE + "\n", encoding="utf-8")
            bot.account.has_medal = lambda m, mode: True
            assert bot.watched_chimps_pick(R.planner_specs(bot.strats, bot.account)) is None


def test_a_parked_build_gives_way_to_the_maps_best_build():
    """Spring Spring CHIMPS (2026-11-13 03:35, loss case
    20261113_040648_SpringSpring_chimps): the watch line named the parked
    springspring_chimps (base_success 0.05, nine round-95 losses) and the
    game was lost on round 95 again. A line naming a parked build plays the
    map's best build for the mode instead - its guide build."""
    bot = _bot()
    bot.account.mode_unlocked = lambda m, mode: True
    assert bot._parked("springspring_chimps", "chimps")
    assert not bot._parked("springspring_chimps_guide", "chimps")
    assert not bot._parked("alpinerun_chimps", "chimps")
    with tempfile.TemporaryDirectory() as tmp:
        watch, state = Path(tmp) / "CHIMPS_WATCH", Path(tmp) / "tried.json"
        watch.write_text("Spring Spring / chimps / springspring_chimps\n", encoding="utf-8")
        with mock.patch.object(R, "CHIMPS_WATCH_FILE", watch), mock.patch.object(R, "CHIMPS_WATCH_STATE", state):
            plan = bot.watched_chimps_pick(R.planner_specs(bot.strats, bot.account))
            assert plan is not None and plan.mode_key == "chimps", plan
            assert plan.strategy_id == "springspring_chimps_guide", plan.strategy_id


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
