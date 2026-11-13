"""No general build plays Tricky Tracks' unbeaten modes.

Tricky Tracks (Advanced) is six short lanes on three diagonal tracks: a
blimp is on screen for a few seconds, mostly over one lane. Every medal won
there came from a map build (Easy, Medium, Reverse, Deflation) or a
category build (Military, Magic, Primary Only). The general builds lost all
eight games they played in the unbeaten modes, picked as last resorts at
p 0.22-0.76: ABR r63 and r40, Double HP r40 twice, Apopalypse r47 and r50,
Deflation r49 (solo_mortar; Deflation is now won with the map build). The
round-50 Apopalypse loss had the board rated 1.19 and $11,197 in hand.

Replays (2026-11-09; simulate_threats on the learned map, Fast Track and
Double Cash economy, boards rated by the live forecast with sight heights;
Apopalypse with tools/apopalypse_check.py):
  ABR         abr_ninja_alch     48 rounds under 1, worst 0.06 (r23)
              hard_sniper_elite  28 under 1, worst 0.23 (r78)
              hard_glaive_lord   35 under 1, worst 0.15 (r79)
  Double HP   hard_ninja_alch_sun 14 under 1, worst 0.38 (r51)
              hard_sniper_elite  23 under 1, worst 0.26 (r78)
  Apopalypse  apopalypse_ninja_sniper: random-round check worst 0.26 (r34),
              every round under the 2.0 gate
  ABR         military_heli_sniper 9 under 1, worst 0.56 (r78)
  Half Cash   obyn_druid_poplust 59 under 1, worst 0.06 (r24)
  Impoppable  chimps_ninja_sun   66 under 1, worst 0.13 (r98)
  Apopalypse  apopalypse_apache_spikes (added 2026-11-09): worst 0.39
              (r31-40), 0.56-0.59 in rounds 41-60 - no better than the old
              build's 0.58-0.68 there
The map's own Medium build (trickytracks_medium) was tried in these modes
too, with late steps added (Crossbow Master, Bloonjitsu ninjas, Radar
villages, Maim MOAB) and its snipers moved first for ABR's early leads. It
did better, but it still does not hold: Double HP r78 0.45-0.54 in every
variant (the 72 camo ceramics at the round's end); ABR r63 0.68 and r78/79
0.41-0.52; Half Cash 5-7 rounds under 1; Apopalypse (random-round check)
0.06 at round 19, where poor-game income does not pay for its opening. No
map build was written for those modes.

So these builds list Tricky Tracks in planner.excluded_maps. The bot does
not spend 7-15 minutes on games it has lost every time. The same check covers
any general build added later.
Run: python tests/test_trickytracks_excluded_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

MAP = "Tricky Tracks"
UNBEATEN = ("abr", "double_hp", "half_cash", "apopalypse", "impoppable")
EXCLUDED = ("abr_ninja_alch", "hard_sniper_elite", "hard_glaive_lord",
            "apopalypse_ninja_sniper", "hard_ninja_alch_sun", "double_hp_sniper_sun",
            "military_heli_sniper", "obyn_druid_poplust", "chimps_ninja_sun",
            "apopalypse_apache_spikes")


def _specs():
    """Planner specs of every strategy except the achievement plans (their
    map lists are not map names), as runner.planner_specs builds them."""
    return {sid: PL.StrategySpec.from_any(dict(s, id=sid, **(s.get("planner") or {})))
            for sid, s in S.load_all().items() if not s.get("achievement")}


def test_the_losing_builds_exclude_tricky_tracks():
    specs = _specs()
    for sid in EXCLUDED:
        assert MAP in specs[sid].excluded_maps, sid


def test_no_general_build_fits_an_unbeaten_mode():
    from btd6bot.account import AccountState
    category = AccountState().map_category(MAP)
    fits = [(sid, mode) for sid, s in _specs().items()
            if s.maps is None and not s.achievement
            for mode in UNBEATEN if PL._strategy_fits(s, MAP, category, mode)]
    assert not fits, f"general builds still offered on {MAP}: {fits}"


def test_the_map_builds_are_untouched():
    specs = _specs()
    for sid in ("trickytracks_medium", "trickytracks_deflation"):
        assert specs[sid].maps == frozenset({MAP}) and not specs[sid].excluded_maps, sid



def test_no_general_build_plays_dark_dungeons_apopalypse():
    """Dark Dungeons Apopalypse (loss case 20261113_043704): every general
    build lost there (apopalypse_apache_spikes rounds 17, 35, 39;
    apopalypse_ninja_sniper rounds 33 and 32), and tools/apopalypse_check.py
    rates the ninja/sniper build 0.06 at every round. Only the map's own
    build (darkdungeons_apopalypse) is offered there."""
    from btd6bot.account import AccountState
    m = "Dark Dungeons"
    category = AccountState().map_category(m)
    fits = sorted(sid for sid, s in _specs().items()
                  if not s.achievement and PL._strategy_fits(s, m, category, "apopalypse"))
    assert fits == ["darkdungeons_apopalypse"], fits


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
