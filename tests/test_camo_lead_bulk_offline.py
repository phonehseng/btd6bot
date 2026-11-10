"""The strong-camo threat for camo leads is dated by the first round that
sends them in bulk, not by the first camo lead.

ABR's first camo lead comes alone on round 24; dated there, every ABR
opening (Fast Track from round 22) bought a Radar Scanner village for it.
Pat's Pond and Bloody Puddles ABR (2026-11-10) spent $3.7-4.3k of a $5k
opening on it and lost rounds 30 and 23.
Run: python tests/test_camo_lead_bulk_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import strategy as S  # noqa: E402


def test_abr_camo_leads_in_bulk_come_on_round_30():
    assert S._ABR["camo_lead"] == 30
    assert S.ABR_SHIFT["camo_lead"] == 30


def test_standard_camo_leads_stay_on_round_59():
    assert S._STD["camo_lead"] == 59
    assert (59, "camo_lead") in S.THREATS


def test_a_lone_camo_lead_is_not_bulk():
    rounds = {"24": {"groups": [{"bloon": "Lead", "count": 1, "camo": True}]},
              "30": {"groups": [{"bloon": "Lead", "count": 9, "camo": True},
                                {"bloon": "Red", "count": 40, "camo": True}]}}
    assert S._first_bulk_camo_lead(rounds) == 30
    assert S._first_bulk_camo_lead({"1": {"groups": []}}) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
