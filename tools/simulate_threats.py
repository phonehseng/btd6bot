"""Play a strategy's build order offline against the round calendar.

No game is involved: a fake game charges the real prices of the mode's
difficulty (btd6bot/towers.py), income is the game's own per-round cash
(data/rounds.json: pops + end-of-round bonus, at base rates - Double Cash,
farms and hero/MK discounts are left out, so the result is pessimistic), and
every spot is accepted. Between rounds the strategy.Executor ticks as it does
live; at the start of each round the simulator records whether the defence
can pop every bloon signature the round brings (threats.py) and, on blimp
rounds, the rough blimp damage ratio.

What it shows: whether the threat checks get every answer bought in time
with the money a mode really gives, which answers the executor had to buy
on top of the plan, and how far each plan gets by each round.

Usage:
    python tools/simulate_threats.py                     # every general strategy x its modes
    python tools/simulate_threats.py hard_ninja_alch_sun hard
    python tools/simulate_threats.py --map "Dark Castle" chimps_ninja_sun chimps
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import strategy as S  # noqa: E402
from btd6bot import threats as TH  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.game import Placed  # noqa: E402

# Starting cash per mode (data/rounds.json difficulty_notes; Half Cash halves it,
# Deflation gives $20,000 and nothing after).
START_CASH = {"half_cash": 325, "deflation": 20000}
DEFAULT_START_CASH = 650
SETUP_TICKS = 80     # plan steps the setup may buy before the first round


class CashGame:
    """A game that accepts every spot and charges the mode's real prices."""

    def __init__(self, family, hero="quincy"):
        self.family = family
        self.hero = hero
        self.cash = 0.0
        self.towers = {}
        self.fail_reason = None
        self.locked_seen = None
        self.refused_spots = []
        self.bought = []          # (round, text)
        self.round = None
        self.s = type("Screen", (), {"width": 1920})()

    def price(self, kind):
        return T.hero_cost(self.hero, self.family) if kind == "hero" else T.tower_cost(kind, self.family)

    def place(self, tid, kind, fx, fy, check_valid=True, more_spots=()):
        cost = self.price(kind)
        if cost > self.cash:
            self.fail_reason = "cash"
            return None
        self.cash -= cost
        p = Placed(tid, kind, fx, fy, spent=cost)
        self.towers[tid] = p
        self.bought.append((self.round, f"place {tid} ({kind})"))
        return p

    def upgrade(self, p, path, max_wait=0.0, allow_xp_unlock=True):
        if p.kind == "hero":
            return False
        cost = T.upgrade_cost(p.kind, path, p.tiers[path - 1] + 1, self.family)
        if cost > self.cash:
            self.fail_reason = "cash"
            self.last_price = cost
            return False
        self.cash -= cost
        p.tiers[path - 1] += 1
        p.spent += cost
        self.bought.append((self.round, f"upgrade {p.tid} -> {p.crosspath}"))
        return True

    def target(self, p, mode):
        return True

    def sell(self, p):
        self.towers.pop(p.tid, None)
        return True

    def select(self, p):
        return True

    def deselect(self, p):
        pass


class OpenModel:
    """Every cell is free; towers end up next to each other (so villages reach)."""
    W, H = 100, 60

    def __init__(self, name="Monkey Meadow", water=False):
        self.name = name
        self.water = water
        self.heat = np.zeros((self.H, self.W), np.float32)

    def has_water(self):
        return self.water

    def frac_to_cell(self, x, y):
        return int(x * self.W), int(y * self.H)

    def cell_to_frac(self, cx, cy):
        return (cx + 0.5) / self.W, (cy + 0.5) / self.H

    def radius_cells(self, rng, width):
        return 8

    def score_spots(self, rc, seg, occupied, near=None, near_radius=None, placement="land",
                    extra_block=None, covered=None, valid=None):
        cover = np.ones((self.H, self.W), np.float32)
        if extra_block is not None:
            cover[extra_block] = 0
        return cover

    def best_spots(self, cover, n=12):
        idx = np.argsort(-cover, axis=None, kind="stable")[:n * 6]
        return [(int(i % self.W), int(i // self.W), float(cover.flat[i])) for i in idx
                if cover.flat[i] > 0][:n]


def full_account():
    from btd6bot.account import AccountState
    a = AccountState()
    a.unlocked_towers = set(T.TOWERS)
    a.unlocked_heroes = set(T.HEROES)
    a.unlocked_upgrades = {k: [5, 5, 5] for k in T.TOWERS}
    return a


def simulate(strat, mode, map_name="Monkey Meadow", water=False, ticks=10, account=None, scenario=None):
    """Run one game offline. scenario: {"start_round", "start_cash",
    "income_multiplier"} to play an optimized build as it was planned (Fast
    Track start, Double Cash income: its `optimizer.scenario`); default the
    mode's own start and income. Returns a dict:
    gaps      [(round, need, what is missing)] signatures the defence could not
              pop at the start of a round that brings them
    ramp      [(round, ratio)] blimp damage ratio at the start of blimp rounds
    answers   [(round, text)] purchases of towers the plan does not list
    build     {tid: crosspath} at the end
    spent     total cash spent"""
    rules = S.rules(mode)
    fam = S.PRICE_FAMILY.get(mode, "hard")
    hero = strat.get("hero") or "quincy"
    g = CashGame(fam, hero)
    g.cash = START_CASH.get(mode, DEFAULT_START_CASH)
    ex = S.Executor(g, OpenModel(map_name, water), strat, mode, account or full_account())
    set_name = TH.set_for_mode(mode)
    mult = 0.0 if rules.get("income") is False else (0.5 if rules.get("half_cash") else 1.0)
    plan_ids = {st.get("id") for _, st in S._all_steps(strat) if st.get("id")}
    out = {"gaps": [], "ramp": [], "answers": [], "build": {}, "spent": 0.0}
    start, end = rules.get("start_round", 1), rules.get("end_round", 80)
    if scenario:
        start = scenario.get("start_round", start)
        g.cash = scenario.get("start_cash", g.cash)
        mult = scenario.get("income_multiplier", mult)
    total_in = g.cash
    for rnd in range(start, end + 1):
        g.round = rnd
        # between rounds: build. Before the first Play the bot spends down
        # what it has (Match.setup), not a few steps of it: a Fast Track
        # start, and Deflation's $20,000 at round 31
        for _ in range(SETUP_TICKS if rnd == start else ticks):
            if not ex.tick(g.cash, rnd):
                break
        # the match loop spends idle cash (over $800) on surplus damage after a while
        for _ in range(2):
            if g.cash <= 800 or not ex.surplus(g.cash, rnd):
                break
        for sig in TH.round_signatures(set_name, rnd):
            ok, how = ex._covers(sig)
            if not ok:
                out["gaps"].append((rnd, TH.sig_name(sig), how))
        load = TH.round_blimp_load(set_name, rnd, double_hp=bool(rules.get("tough_moabs")))
        if load:
            out["ramp"].append((rnd, round(ex.blimp_ratio(load), 2)))
        income = TH.round_cash(set_name, rnd) * mult
        g.cash += income                  # the round is played and paid
        total_in += income
        for _ in range(ticks // 2):       # buying during the round
            if not ex.tick(g.cash, rnd):
                break
    out["answers"] = [(r, t) for r, t in g.bought if t.split()[1].startswith("ans_")]
    out["surplus"] = [(r, t) for r, t in g.bought
                      if t.split()[1] not in plan_ids and not t.split()[1].startswith(("ans_", "hero"))]
    out["build"] = {p.tid: "-".join(map(str, p.tiers)) for p in g.towers.values()}
    out["spent"] = total_in - g.cash
    out["plan_done"] = f"{ex.idx}/{len(ex.plan)}"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("strategy", nargs="?")
    ap.add_argument("mode", nargs="?")
    ap.add_argument("--map", default="Monkey Meadow")
    ap.add_argument("--water", action="store_true")
    ap.add_argument("-v", action="store_true", help="show the executor's log")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO if a.v else logging.ERROR, format="%(name)s: %(message)s")
    strats = S.load_all()
    todo = []
    for sid, s in sorted(strats.items()):
        if s.get("achievement") or not s.get("bot_ready", True):
            continue
        if a.strategy and sid != a.strategy:
            continue
        for mode in s.get("modes", []):
            if a.mode and mode != a.mode:
                continue
            if mode == "apopalypse":
                continue    # random rounds: no calendar to check against
            todo.append((sid, s, mode))
    for sid, s, mode in todo:
        r = simulate(s, mode, a.map, a.water)
        worst = min((x for _, x in r["ramp"]), default=None)
        print(f"{sid:28s} {mode:12s} plan {r['plan_done']:6s} gaps {len(r['gaps']):3d}  "
              f"min blimp ratio {worst}  answer buys {len(r['answers'])}  surplus buys {len(r['surplus'])}")
        for rnd, need, how in r["gaps"][:6]:
            print(f"      gap R{rnd}: {need} ({how})")
        for rnd, text in r["answers"][:8]:
            print(f"      answer R{rnd}: {text}")


if __name__ == "__main__":
    main()
