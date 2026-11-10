"""No Apopalypse general build on Geared.

Geared Apopalypse (2026-11-09 22:01, apopalypse_apache_spikes, lost round
36 with 107 lives): at the round-15 start the opener dart and n1 were given
up "after 0 refused spots" - no legal cell at all - and the hero and n2,
a1 after them. Every cell on Geared that reaches the track is on one of
the turning gears, and the executor keeps every tower that is not global
range off moving ground (planner._land_towers_have_no_spot says why), so
only the helis stood. On the gears, chasing the bloons, the helis were lost
track of: h2's 3-2-0 upgrade opened h1's panel (round 17: "h2 is really
3-1-0"), h1 could not be selected at round 35 and was forgotten, and the
cash went from $1.2k to $21.8k unspent over rounds 17-36.

The planner's moving-ground gate keeps a build off Geared when the towers
that cannot stand there carry a quarter of its cost; apopalypse_apache_
spikes passed it only because its cost_share gives the helis 75%. It now
lists Geared in excluded_maps.

Checked offline: the replay on Geared's geometry places nothing but helis
(the cause), and no general Apopalypse build is planned on Geared.
Run: python tests/test_apopalypse_geared_offline.py
"""
import logging
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import planner as PL           # noqa: E402
from btd6bot import strategy as S           # noqa: E402
from btd6bot.account import AccountState    # noqa: E402
import apopalypse_check as C                # noqa: E402

MAP = "Geared"


def _specs():
    return {sid: PL.StrategySpec.from_any(dict(s, id=sid, **(s.get("planner") or {})))
            for sid, s in S.load_all().items() if not s.get("achievement")}


def test_only_helis_find_ground_on_geared():
    strat = yaml.safe_load((ROOT / "strategies" / "apopalypse_apache_spikes.yaml").read_text(encoding="utf-8"))
    _, res = C.boards(strat, MAP, learned=False, click_budget=4.0)
    kinds = {kind for kind, *_ in res["placed"].values()}
    assert kinds == {"heli"}, kinds


def test_no_general_apopalypse_build_on_geared():
    category = AccountState().map_category(MAP)
    specs = _specs()
    assert MAP in specs["apopalypse_apache_spikes"].excluded_maps
    fits = [sid for sid, s in specs.items()
            if s.maps is None and PL._strategy_fits(s, MAP, category, "apopalypse")]
    assert not fits, fits


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
            n += 1
    print(f"{n} passed")
