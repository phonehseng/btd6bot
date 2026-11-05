"""Offline: during the opening build of a no-income game (Deflation) the
surplus spender waits until the plan and its fill are exhausted; with income
it may spend between plan steps as before (match.Match._opening_surplus_ok).
Quad Deflation (2026-11-05): surplus bought a $21,600 Crossbow Master between
two plan steps and the fill's bombs, snipers and spikes were never afforded.
Run: python tests/test_opening_surplus_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import match as M  # noqa: E402
from btd6bot.strategy import PLAN_EXHAUSTED, rules  # noqa: E402


def _match(mode, waiting):
    """A Match with only the executor pieces _opening_surplus_ok reads."""
    m = M.Match.__new__(M.Match)
    m.ex = N(rules=rules(mode), waiting=waiting,
             plan_exhausted=lambda: waiting == PLAN_EXHAUSTED)
    return m


def test_no_income_opening_holds_surplus_while_steps_remain():
    assert rules("deflation").get("buy_all_upfront")
    assert not _match("deflation", "plan step 7 {...} -> wait (None)")._opening_surplus_ok()
    assert not _match("deflation", None)._opening_surplus_ok()


def test_no_income_opening_spends_the_rest_once_the_plan_is_done():
    assert _match("deflation", PLAN_EXHAUSTED)._opening_surplus_ok()


def test_income_modes_spend_between_steps_as_before():
    """A Fast Track start must become a defence before Play."""
    assert _match("hard", "plan step 3 {...} -> wait (None)")._opening_surplus_ok()
    assert _match("hard", None)._opening_surplus_ok()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
