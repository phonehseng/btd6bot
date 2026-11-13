"""Lost Crevasse CHIMPS: the guide build opens with the towers that held live.

Why
---
The guide (OneEyedDeacon) opens with Sauda alone at round 6. The bot lost
round 6 that way twice on 2026-11-13: at 07:27 with her inside the left
loop (case 20261113_073019_LostCrevasse_chimps, 22 pops) and at 11:11 at
the guide's own top middle, one cell lower than asked because the game
refused the cell (case 20261113_111449_LostCrevasse_chimps, 23 pops). Each
time reds walked past her on the side she was not striking.

The bot's own older build had held this map's first rounds in six games
with a boat in the lake and a dart at round 6, a desperado at 7 and a sky
warden at 8 (tools/opening_rule.PROVEN, journal 20261107_181331). The
guide build now opens with those towers on those cells and follows the
guide from Sauda on. The opening costs cash the guide never spent, so the
guide's late glue is left out to keep the last step inside round 100.

Checked here:
  * the guide's Sauda opening is listed as lost (opening_rule.GUIDE_LOST);
  * the build's opening meets the opening rule as a live-proven one;
  * the plan places the proven towers first, in that game's order, and
    Sauda right after them;
  * the whole plan is still bought by round 100.

Run: python tests/test_lostcrevasse_chimps_proven_opening_offline.py (no game)."""
import logging
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import opening_rule as OR  # noqa: E402
import test_chimps_builds_offline as TC  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)

MAP = "Lost Crevasse"
BUILD = ROOT / "strategies" / "maps" / "lostcrevasse_chimps_guide.yaml"
LAST_ROUND = 100


def _build():
    return yaml.safe_load(BUILD.read_text(encoding="utf-8"))


def _proven():
    """The live-proven Lost Crevasse opening of tools/opening_rule."""
    return next(p for p in OR.PROVEN if p.map == MAP)


def test_the_guides_sauda_opening_is_listed_as_lost():
    assert MAP in OR.GUIDE_LOST
    ok, why = OR.matches_guide(_build())
    assert not ok, why


def test_the_opening_is_the_live_proven_one():
    source, why = OR.opening_source(_build())
    assert source == "proven", (source, why)


def test_sauda_comes_after_the_proven_towers():
    d = _build()
    places = [st["kind"] for st in d["plan"] if st["do"] == "place"]
    proven_kinds = []
    for tower in _proven().towers:
        if tower.kind not in proven_kinds:
            proven_kinds.append(tower.kind)
    assert places[:len(proven_kinds)] == proven_kinds, places
    assert places[len(proven_kinds)] == "hero", places
    assert not d.get("hero_opens"), "the hero no longer holds the opening alone"


def test_the_plan_is_bought_by_the_last_round():
    timeline = TC.plan_timeline(_build(), "chimps")
    assert timeline[-1][2] <= LAST_ROUND, timeline[-1]


if __name__ == "__main__":
    import inspect
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as exc:
                fails += 1
                print("FAIL", name, exc)
    sys.exit(1 if fails else 0)
