"""magic_obyn_ninja_wizard: the round-40 MOAB answer and the map exclusions.

On 2026-11-08 the build lost six Magic Monkeys Only games at round 40, the
first MOAB (Ravine, Muddy Puddles, Spillway, Bloody Puddles, Dark Dungeons,
Midnight Mansion), and Water Park at round 63 although the file excluded it.
In every round-40 loss n2 stood at 2-0-3 (Flash Bomb): the Sticky Bomb
(2-0-4) came late in the plan and the `moab` answer named the Flash Bomb the
build already had. And the Water Park exclusion sat at the top level of the
file, where the runner never reads it (it takes the planner block's).

Checked here, without the game:
  * the build's `moab` answer is a ninja Sticky Bomb, and the plan buys it
    straight after the Flash Bomb, before the Necromancer and Bloonjitsu;
  * no strategy file keeps `excluded_maps` at the top level, and the
    planner spec the runner builds for this build excludes Water Park and
    the multi-lane maps it cannot cover.
Run: python tests/test_magic_only_r40_offline.py (also collectable by pytest)."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import strategy as S  # noqa: E402

BUILD = "magic_obyn_ninja_wizard"
LEFT_OUT = {"Water Park", "Muddy Puddles", "Bloody Puddles", "Dark Dungeons", "Midnight Mansion"}


def _tiers(text):
    return tuple(int(t) for t in text.split("-"))


def test_moab_answer_is_the_sticky_bomb():
    strat = S.load_all()[BUILD]
    upgrade = next(st for st in strat["answers"]["moab"] if st["do"] == "upgrade")
    assert upgrade["id"] == "n2" and _tiers(upgrade["to"])[2] >= 4, upgrade   # 0-0-4 Sticky Bomb


def test_sticky_bomb_comes_right_after_the_flash_bomb():
    plan = S.load_all()[BUILD]["plan"]
    keys = [(st.get("id"), st.get("to")) for st in plan]
    flash, sticky = keys.index(("n2", "2-0-3")), keys.index(("n2", "2-0-4"))
    assert sticky == flash + 1, keys
    assert sticky < keys.index(("w1", "0-2-4")) and sticky < keys.index(("n1", "4-0-2"))


def test_no_strategy_keeps_excluded_maps_at_the_top_level():
    for path in (ROOT / "strategies").rglob("*.yaml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        assert "excluded_maps" not in doc, f"{path.name}: excluded_maps belongs in the planner block"


def test_runner_spec_excludes_the_maps():
    sys.path.insert(0, str(ROOT / "tools"))
    import simulate_threats as SIM
    from btd6bot import runner
    from btd6bot.planner import canonical_map
    strats = S.load_all()
    specs = {sp.id: sp for sp in runner.planner_specs({BUILD: strats[BUILD]}, SIM.full_account())}
    got = set(specs[BUILD].excluded_maps)
    assert {canonical_map(m) for m in LEFT_OUT} <= got, got


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
