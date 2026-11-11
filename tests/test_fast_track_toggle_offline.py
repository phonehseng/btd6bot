"""Fast Track is switched off for Impoppable and back on for other modes.

Owner (2026-11-10): from the round-29 Fast Track start an Impoppable game
has eleven rounds of income to buy a whole MOAB answer; 10 of Impoppable's
45 losses came on round 40. The runner now sets the toggle per game, and the
account keeps owning the boost while it is switched off.
Run: python tests/test_fast_track_toggle_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import boosts, runner as R  # noqa: E402


def bot(on, owned=True, sticky=False):
    """A Bot whose screen shows the toggle `on`; a click flips it (unless sticky)."""
    b = R.Bot.__new__(R.Bot)
    b.account = N(boosts={"double_cash": True, "fast_track": owned}, save=lambda: None)
    state = {"on": on, "clicks": 0}

    def click(x, y):
        assert (x, y) == boosts.TOGGLES["fast_track"]
        state["clicks"] += 1
        if not sticky:
            state["on"] = not state["on"]
    b.inp = N(click=click)
    b.s = N(grab=lambda: None)
    real_read = boosts.read
    boosts.read = lambda frame: {"double_cash": True, "fast_track": state["on"]}
    return b, state, real_read


def test_off_for_impoppable_on_for_medium():
    b, state, real = bot(on=True)
    try:
        R.time.sleep, sleep = (lambda s: None), R.time.sleep
        b._set_fast_track("impoppable", {"fast_track": True})
        assert state["on"] is False and state["clicks"] == 1
        b._set_fast_track("medium", {"fast_track": False})
        assert state["on"] is True and state["clicks"] == 2
        b._set_fast_track("medium", {"fast_track": True})
        assert state["clicks"] == 2, "already right: no click"
    finally:
        boosts.read, R.time.sleep = real, sleep


def test_not_owned_or_stuck():
    b, state, real = bot(on=False, owned=False)
    try:
        R.time.sleep, sleep = (lambda s: None), R.time.sleep
        b._set_fast_track("medium", {"fast_track": False})
        assert state["clicks"] == 0, "an account without Fast Track is never clicked"
        b, state, _ = bot(on=True, sticky=True)
        b._set_fast_track("impoppable", {"fast_track": True})
        assert state["clicks"] == 2, "two tries, then the game goes on as it is"
    finally:
        boosts.read, R.time.sleep = real, sleep


def test_ownership_survives_the_toggle():
    b, state, real = bot(on=False)
    try:
        seen = b._note_boosts()
        assert seen["fast_track"] is False and b.account.boosts["fast_track"] is True
    finally:
        boosts.read = real


def test_a_build_written_for_round_3_switches_it_off():
    """abr_ninja_alch says `fast_track: false` (2-8 with Fast Track on, 2026-11-11);
    the round-22-tuned double_hp_sniper_sun keeps the toggle on in ABR."""
    from btd6bot import strategy as S
    strats = S.load_all()
    assert strats["abr_ninja_alch"].get("fast_track") is False
    assert boosts.fast_track_wanted("abr", strats["abr_ninja_alch"]) is False
    assert boosts.fast_track_wanted("abr", strats["double_hp_sniper_sun"]) is True
    assert boosts.fast_track_wanted("abr") is True
    b, state, real = bot(on=True)
    try:
        R.time.sleep, sleep = (lambda s: None), R.time.sleep
        b._set_fast_track("abr", {"fast_track": True}, strats["abr_ninja_alch"])
        assert state["on"] is False and state["clicks"] == 1
        b._set_fast_track("abr", {"fast_track": False}, strats["double_hp_sniper_sun"])
        assert state["on"] is True and state["clicks"] == 2
    finally:
        boosts.read, R.time.sleep = real, sleep


def test_impoppable_has_no_fast_track_start():
    assert boosts.fast_track_start("impoppable") is None
    assert boosts.fast_track_start("medium") == 15 and boosts.fast_track_start("hard") == 22


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
