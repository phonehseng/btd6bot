"""Check a build for Apopalypse: can the board it stands at each round hold
every round the game could send there, with no pause between rounds?

Why
---
Apopalypse rounds are random (btd6bot/apopalypse.py: the game's own group
pool, budget and scores), so the damage model's usual check - one standard
round at a time (dps_model.round_margin) - has nothing to rate, and
tools/simulate_threats.py skips the mode. The bot had never won it: the
general plan apopalypse_ninja_sniper lost on Polyphemus (2026-10-27, round 52)
and Infernal (2026-11-05, round 45), and docs/map_strategies/beginner.md
left the mode out of the Beginner map builds until a random-round check
existed. This is that check, kept conservative on purpose.

The check
---------
1. The board. The build is played the executor's way
   (tools/simulate_threats.simulate: plan ticks, the match loop's surplus
   spending, buying during the round) on the map's real ground with the spots
   the live game refused there refused too (map_model(learned=True)), on the
   account's economy: Fast Track's round-15 start and Double Cash
   (optimize_builds.economy), and each round paid what it pays in a poor
   game (by each round, the cash of the poorest INCOME_QUANTILE of
   INCOME_GAMES games drawn as the game draws them, apopalypse.round_cash):
   Apopalypse pays far less than Medium's rounds ($39,300 over rounds 1-60
   against Medium's $54,500, before Double Cash). The towers standing when
   each round starts, where they stand, are that round's board.
2. The rounds. For round r the board is rated (dps_model, strict reading:
   snipers see only what their sight lets them, Advanced Intel subs and aces
   reach only their own circle) against a window of two rounds laid end to
   end - round r, then round r + 1 starting the moment r has spawned its last
   bloon, as the game sends them - so bloons the board has not finished when
   the next round arrives are still there with it:
     * the worst windows: each round built by apopalypse.worst_round - the
       round the game sends when its shuffle puts the hardest groups first
       and the budget is the largest (x1.5): every hard group that fits,
       then the rest of the budget the same way - for two meanings of
       "hardest" (HARDNESS): the board's margin against the group alone
       (one big group it can barely pop), and the load the group puts on
       the board per point of budget (1 / margin alone / score: many
       mid-sized groups that fill the budget). Both rounds of the window
       are built so; the worse window counts;
     * SAMPLES random windows drawn as the game draws them, as a cross-check
       of the constructed one.
   The gate is the worst of both at every round from the start to round 60
   (the win): GATE_MARGIN (2.0, the house safety margin: the board would hold
   at half strength) or more.
3. Drift. The same with every tower DRIFT_UNITS further from the villages
   and alchemists that buff it (the CHIMPS builds' fifth replay,
   docs/map_strategies/beginner.md): a spot the game shifts a little must
   not take a buff away.

The clicking. Live, a round passes every 3-4 s and a purchase takes about
one of them (btd6bot/clicktime.py), so a bank can pile up that the clicks
never spend (Mesa, 2026-11-09: $7.7k-$17.4k idle from round 44). By
default the board is bought as fast as the cash allows; --click-budget S
gives each round after the start S seconds of clicking, each purchase
costing what it costs live, and --old-clicks buys as the bot did before
clicktime.py (one tier a tick, in plan order) for comparing the two.

Not modelled (on the safe side unless noted): the hero, abilities, Monkey
Knowledge; the end-of-round bonus is assumed paid every round although the
game pays it only once a round is fully popped (a board that holds at 2.0
pops its rounds); the window covers one overlap (a board that falls behind
two rounds in a row is already failing the gate).

Usage
-----
    python tools/apopalypse_check.py strategies/maps/parkpath_apopalypse.yaml
    python tools/apopalypse_check.py <file> --map "Park Path" --maps-dir <dir with the live data/maps>

In a git worktree, --maps-dir should point at the live checkout's data/maps
(read-only): the refused spots there are the ones the game really refuses.
"""
from __future__ import annotations

import argparse
import logging
import math
import random
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import apopalypse as A        # noqa: E402
from btd6bot import dps_model as D         # noqa: E402
from btd6bot import strategy as S          # noqa: E402

MODE = "apopalypse"
GATE_MARGIN = 2.0          # optimize_builds.SAFETY_MARGIN, the house bar
SAMPLES = 24               # random windows per round (the cross-check)
INCOME_GAMES = 400         # games drawn for the income curve
INCOME_QUANTILE = 0.10     # the board is bought with a poor game's cash
WINDOW = 2                 # rounds rated together: r, then r + 1 end to end
DRIFT_UNITS = 5.0          # world units every tower moves away from its supporters
ACCOUNT_BOOSTS = {"double_cash": True, "fast_track": True}   # the main account (docs: btd6-main-account-buffs)
SUPPORT_KINDS = ("village", "alchemist")
HARDNESS = ("alone", "load")   # the two orderings the worst windows are built with (see the docstring)


@lru_cache(maxsize=None)
def _poor_game_curve():
    """{round: cash paid by the end of that round} of a poor game: at each
    round, the INCOME_QUANTILE of INCOME_GAMES games drawn as the game draws
    them (rounds 1-61, pops + end-of-round bonus at base rates). Over rounds
    1-60 such a game pays $39,300 (the median game $41,800); with the $650
    start, bloons.fandom.com's Apopalypse_(BTD6) gives $36,859 to $46,919
    for the whole game, and the same draws average 41.5 MOABs a game, as it
    says (checked 2026-11-06, 1,500 games)."""
    rng = random.Random(2026)
    games = []
    for _ in range(INCOME_GAMES):
        total, row = 0.0, {}
        for r in range(1, A.END_ROUND + WINDOW):
            total += A.round_cash(r, A.random_round(r, rng))
            row[r] = total
        games.append(row)
    k = int(INCOME_QUANTILE * (INCOME_GAMES - 1))
    return {r: sorted(g[r] for g in games)[k] for r in games[0]}


def low_income(rnd):
    """Base-rate cash of round rnd in a poor game (_poor_game_curve): what
    the board is bought with."""
    curve = _poor_game_curve()
    return max(0.0, curve.get(rnd, 0.0) - curve.get(rnd - 1, 0.0))


def scenario(boosts=None):
    """Start round, start cash and income multiplier of the account's games."""
    import optimize_builds as O
    econ = O.economy(MODE, ACCOUNT_BOOSTS if boosts is None else boosts)
    econ.end_round = A.END_ROUND
    return {"start_round": econ.start_round, "start_cash": econ.start_cash, "income_multiplier": econ.cash_mult}


def use_maps_dir(maps_dir):
    """Read the learned map files (refused spots) from a copy of maps_dir:
    maplearn reads data/maps of this checkout by default, and the live files
    belong to the running bot (copied, never opened in place)."""
    from btd6bot import maplearn
    import simulate_threats as SIM
    tmp = Path(tempfile.mkdtemp(prefix="apop_maps_"))
    for f in Path(maps_dir).glob("*.npz"):
        shutil.copy2(f, tmp / f.name)
    maplearn.DATA = tmp
    SIM._MAP_MODELS.clear()
    return tmp


def boards(strat, map_name, boosts=None, learned=True, click_budget=None):
    """Play the build the executor's way; ({round: board}, simulate's result).
    A board is {tid: (kind, tiers, fx, fy)} at the start of the round.
    click_budget: seconds of clicking per round after the start (simulate's
    click model), or None for as many purchases as the cash allows."""
    import simulate_threats as SIM
    out = {}
    res = SIM.simulate(strat, MODE, map_name, real_map=True, learned=learned, scenario=scenario(boosts),
                       income=low_income, boards=out, click_budget=click_budget)
    return {r: b for r, b in out.items() if r <= A.END_ROUND}, res


class Rater:
    """Stations of boards on one map (strict reading), and margins of
    Apopalypse windows against them."""

    def __init__(self, map_name, drift=0.0):
        import optimize_builds as O
        self.setup = O.MapSetup(map_name, MODE)
        self.track = self.setup.track
        self.drift = drift
        self._stations = {}
        self._alone = {}

    def placed(self, board):
        """dps_model.Placed towers of a board (no hero), drifted if asked."""
        out = []
        for tid, (kind, tiers, fx, fy) in sorted(board.items()):
            if kind == "hero":
                continue
            x, z, _ = self.track.frac_to_world(fx, fy)
            out.append(D.Placed(tid, kind, tuple(tiers), x, z))
        return drifted(out, self.drift) if self.drift else out

    def stations(self, board):
        key = tuple(sorted(board.items()))
        if key not in self._stations:
            self._stations[key] = D.stations_for(self.placed(board), self.track, sight=self.setup.sight, strict=True)
        return self._stations[key]

    def lots(self, round_lists):
        """Lots per scenario of rounds laid end to end."""
        groups, t = [], 0.0
        for rl in round_lists:
            g, t = A.as_round_groups(rl, t)
            groups += g
        return [D.groups_lots(MODE, groups, self.track, sc) for sc in range(len(self.track.scenarios))]

    def margin(self, stations, round_lists):
        return D.lots_margin(stations, self.track, self.lots(round_lists))

    def alone(self, board, stations, group):
        """The board's margin against one group alone (cached per board)."""
        key = (tuple(sorted(board.items())), group)
        if key not in self._alone:
            self._alone[key] = self.margin(stations, [[group]])
        return self._alone[key]

    def worst_rounds(self, board, stations, rnd):
        """{hardness: the worst round at rnd for that meaning of hardest}."""
        def alone(g):
            return self.alone(board, stations, g)
        keys = {"alone": lambda g: (alone(g), -g.score),
                "load": lambda g: (-1.0 / max(alone(g), 1e-6) / max(g.score, 1e-6), alone(g))}
        return {name: A.worst_round(rnd, key) for name, key in keys.items() if name in HARDNESS}


def drifted(placed, units):
    """Every non-support tower `units` further from the supporters whose
    buffs reach it now (the sum of the directions away from them)."""
    supporters = [p for p in placed if p.kind in SUPPORT_KINDS]
    out = []
    for p in placed:
        dx = dz = 0.0
        if p.kind not in SUPPORT_KINDS:
            for s in supporters:
                prof = D.profile(s.kind, s.tiers)
                radius = max([b.get("radius") or prof.range for b in prof.buffs] or [0.0]) if prof else 0.0
                d = math.hypot(p.x - s.x, p.z - s.z)
                if 0 < d <= radius:
                    dx, dz = dx + (p.x - s.x) / d, dz + (p.z - s.z) / d
        n = math.hypot(dx, dz)
        if n > 0:
            out.append(D.Placed(p.tid, p.kind, p.tiers, p.x + units * dx / n, p.z + units * dz / n))
        else:
            out.append(p)
    return out


@dataclass
class RoundCheck:
    rnd: int
    towers: int
    worst: float                 # constructed worst window
    sampled: float               # worst of the random windows
    below: int                   # random windows under GATE_MARGIN
    hardest: list = field(default_factory=list)   # names of the worst window's first groups

    @property
    def margin(self):
        return min(self.worst, self.sampled)


def check_boards(map_name, round_boards, drift=0.0, samples=SAMPLES, seed=0, rounds=None):
    """[RoundCheck] for every round of round_boards (or `rounds`)."""
    rater = Rater(map_name, drift)
    rng = random.Random(seed)
    out = []
    for rnd in sorted(round_boards):
        if rounds is not None and rnd not in rounds:
            continue
        board = round_boards[rnd]
        st = rater.stations(board)
        window = [r for r in range(rnd, rnd + WINDOW)]
        built = [rater.worst_rounds(board, st, r) for r in window]
        worst, worst_rounds = math.inf, None
        for name in HARDNESS:
            rounds_ = [b[name] for b in built]
            m = rater.margin(st, rounds_)
            if m < worst:
                worst, worst_rounds = m, rounds_
        sampled, below = math.inf, 0
        for _ in range(samples):
            m = rater.margin(st, [A.random_round(r, rng) for r in window])
            sampled = min(sampled, m)
            below += m < GATE_MARGIN
        out.append(RoundCheck(rnd, len(board), round(worst, 2), round(sampled, 2), below,
                              [g.name for g in worst_rounds[0][:3]]))
    return out


def check(strat, map_name, boosts=None, samples=SAMPLES, drift=DRIFT_UNITS, learned=True, rounds=None,
          click_budget=None):
    """The whole check of one build on one map: {"plain": [RoundCheck],
    "drift": [RoundCheck], "worst": float, "passes": bool, "plan_done": str,
    "spots_off": {tid: cells}}. click_budget: see boards()."""
    round_boards, res = boards(strat, map_name, boosts, learned, click_budget)
    plain = check_boards(map_name, round_boards, 0.0, samples, rounds=rounds)
    drift_checks = check_boards(map_name, round_boards, drift, samples, seed=1, rounds=rounds) if drift else []
    worst = min(c.margin for c in plain + drift_checks)
    return {"plain": plain, "drift": drift_checks, "worst": worst, "passes": worst >= GATE_MARGIN,
            "plan_done": res["plan_done"], "placed": res["placed"], "surplus": res["surplus"],
            "spots_off": spots_off(strat, res["placed"], map_name, learned)}


def spots_off(strat, placed, map_name, learned=True):
    """{tid: cells} for plan towers that do not stand on their `at` spot (the
    game refused it, so the executor took the next cell it accepts)."""
    import simulate_threats as SIM
    model = SIM.map_model(map_name, learned)
    out = {}
    for st in strat.get("plan") or ():
        tid = st.get("id")
        if st.get("do") != "place" or not st.get("at") or tid not in placed:
            continue
        (ax, ay), (px, py) = model.frac_to_cell(*st["at"]), model.frac_to_cell(*placed[tid][2:])
        off = math.hypot(px - ax, py - ay)
        if off > 0:
            out[tid] = round(off, 1)
    return out


def report(result, out=print):
    for label in ("plain", "drift"):
        rows = result[label]
        if not rows:
            continue
        w = min(rows, key=lambda c: c.margin)
        out(f"  {label}: worst {w.margin:.2f} at round {w.rnd} (constructed {w.worst:.2f}, sampled {w.sampled:.2f};"
            f" first groups {', '.join(w.hardest)}); rounds under {GATE_MARGIN:g}: "
            f"{[c.rnd for c in rows if c.margin < GATE_MARGIN] or 'none'}")
    out(f"  plan {result['plan_done']}; towers off their spot (cells): {result.get('spots_off') or 'none'}; "
        f"worst {result['worst']:.2f} -> {'PASS' if result['passes'] else 'FAIL'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("strategy", help="a strategy file or id")
    ap.add_argument("--map", help="map name (default: the file's maps)")
    ap.add_argument("--maps-dir", help="learned map files to read (copied), e.g. the live checkout's data/maps")
    ap.add_argument("--samples", type=int, default=SAMPLES)
    ap.add_argument("--no-drift", action="store_true")
    ap.add_argument("-v", action="store_true", help="every round")
    ap.add_argument("--click-budget", type=float, metavar="SECONDS",
                    help="seconds of clicking each round allows (live: about one round, 3-4 s); "
                         "default: as many purchases as the cash pays for")
    ap.add_argument("--old-clicks", action="store_true",
                    help="buy as before clicktime.py (one tier per tick, plan order, per dollar)")
    a = ap.parse_args()
    if a.old_clicks:
        from btd6bot import clicktime
        clicktime.ENABLED = False
    logging.basicConfig(level=logging.ERROR, format="%(name)s: %(message)s")
    if a.maps_dir:
        use_maps_dir(a.maps_dir)
    strats = S.load_all()
    sid = Path(a.strategy).stem if a.strategy.endswith(".yaml") else a.strategy
    strat = strats[sid]
    maps = [a.map] if a.map else ((strat.get("planner") or {}).get("maps") or [strat.get("map")])
    for m in maps:
        print(f"{sid} on {m}:")
        r = check(strat, m, samples=a.samples, drift=0.0 if a.no_drift else DRIFT_UNITS,
                  click_budget=a.click_budget)
        if a.v:
            for c in r["plain"]:
                print(f"    R{c.rnd:3d} towers {c.towers:2d}  worst {c.worst:5.2f}  sampled {c.sampled:5.2f}"
                      f"  under-bar draws {c.below}  {c.hardest}")
        report(r)


if __name__ == "__main__":
    main()
