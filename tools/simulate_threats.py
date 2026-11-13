"""Play a strategy's build order offline against the round calendar.

No game is involved: a fake game charges the real prices of the mode's
difficulty (btd6bot/towers.py), income is the game's own per-round cash
(data/rounds.json: pops + end-of-round bonus, at base rates - Double Cash,
farms and hero/MK discounts are left out, so the result is pessimistic), and
every spot is accepted (on a real map with learned=True: every spot the live
game has not refused). Between rounds the strategy.Executor ticks as it does
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

from btd6bot import clicktime as CT  # noqa: E402
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
    """A game that charges the mode's real prices and accepts every spot -
    except, given a map model that learned them (map_model(learned=True)),
    the spots the live game refused (see place)."""

    def __init__(self, family, hero="quincy", model=None):
        self.family = family
        self.hero = hero
        self.model = model
        self.cash = 0.0
        self.towers = {}
        self.fail_reason = None
        self.locked_seen = None
        self.refused_spots = []
        self.click_refusals = 0
        self.bought = []          # (round, text)
        self.round = None
        self.s = type("Screen", (), {"width": 1920})()
        # the seconds of clicking spent (simulate(click_budget=...)): each
        # purchase costs what clicktime.seconds says it does live - a tier
        # bought from the panel the executor kept open (hold_panel) costs a
        # chained tier, any other a whole upgrade and a pass of the match loop
        self.clock = 0.0
        self.hold_panel = None
        self._open = None          # tid whose panel is open (held from the last tier)

    def price(self, kind):
        return T.hero_cost(self.hero, self.family) if kind == "hero" else T.tower_cost(kind, self.family)

    def place(self, tid, kind, fx, fy, check_valid=True, more_spots=()):
        """Place at the first of (fx, fy) and more_spots that the map does not
        refuse, as Game.place goes through them while holding the tower; the
        refused ones are listed in refused_spots for the executor to learn.

        Lotus Island CHIMPS (2026-11-05, loss case 20261105_171203): the
        game refused the build's spots for b1, the MIB village, the
        alchemist and b3; the village went to the north end of the map and
        b3 after it, and round 95 was lost at a rated 0.4 while the replay,
        which put every tower on its planned spot, rated it 2.5."""
        self.refused_spots = []
        self.click_refusals = 0
        cost = self.price(kind)
        if cost > self.cash:
            self.fail_reason = "cash"
            return None
        for sx, sy in [(fx, fy), *more_spots]:
            if not self._refused(kind, sx, sy):
                break
            self.refused_spots.append((sx, sy))
        else:
            self.click_refusals = len(self.refused_spots)
            self.fail_reason = "spot"
            return None
        self.click_refusals = len(self.refused_spots)
        fx, fy = sx, sy
        self.cash -= cost
        self.clock += CT.seconds(None, 1, [])
        self._open = None
        p = Placed(tid, kind, fx, fy, spent=cost)
        self.towers[tid] = p
        self.bought.append((self.round, f"place {tid} ({kind})"))
        return p

    def _refused(self, kind, fx, fy):
        """Did the live game refuse a `kind` tower centred here (the model's
        learned refused layer, MapModel.refused)? An amphibious tower is
        refused where both surfaces are, as Executor._learn_blocked records
        its refusals; a big tower also where its own layer says so
        (placement.refusal_layer)."""
        if self.model is None or not getattr(self.model, "refused", None):
            return False
        from btd6bot.placement import refusal_layer
        if kind == "hero":
            cls = T.HEROES.get(self.hero, {}).get("placement") or "land"
        else:
            cls = T.TOWERS.get(kind, {}).get("placement") or "land"
        cx, cy = (int(round(v)) for v in self.model.frac_to_cell(fx, fy))
        surfaces = ("land", "water") if cls == "land_or_water" else (cls,)
        hero = self.hero if kind == "hero" else None
        masks = [self.model.refused_mask(sf) | self.model.refused_mask(refusal_layer(sf, kind, hero))
                 for sf in surfaces]
        h, w = masks[0].shape
        return 0 <= cx < w and 0 <= cy < h and all(m[cy, cx] for m in masks)

    def upgrade(self, p, path, max_wait=0.0, allow_xp_unlock=True):
        if p.kind == "hero":
            return False
        cost = T.upgrade_cost(p.kind, path, p.tiers[path - 1] + 1, self.family)
        if cost > self.cash:
            self.fail_reason = "cash"
            self.last_price = cost
            return False
        self.cash -= cost
        held = self.hold_panel == p.tid
        self.clock += CT.CHAINED_S if (held and self._open == p.tid) else CT.seconds(None, 0, [1])
        self._open = p.tid if held else None
        p.tiers[path - 1] += 1
        p.spent += cost
        self.bought.append((self.round, f"upgrade {p.tid} -> {p.crosspath}"))
        return True

    def release_panel(self):
        self.hold_panel = self._open = None

    def remove_obstacle(self, fx, fy, cost, name=""):
        """Removable obstacles only exist on a real map (simulate(real_map=True));
        the removal is paid like any purchase, at the map file's price."""
        if cost > self.cash:
            self.fail_reason = "cash"
            return False
        self.cash -= cost
        self.bought.append((self.round, f"remove {name or 'obstacle'}"))
        return True

    def target(self, p, mode):
        return True

    def sell(self, p):
        self.towers.pop(p.tid, None)
        return True

    def targeted_ability(self, key, p):
        """A `do: ability` step's press (Blood Sacrifice): the tower is gone,
        as live once the game took it (Game.targeted_ability)."""
        self.towers.pop(p.tid, None)
        self.bought.append((self.round, f"sacrifice {p.tid} ({p.kind} {p.crosspath})"))
        return "done"

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


_MAP_MODELS = {}


def map_model(map_name, learned=False):
    """A MapModel filled from the map's own game geometry (data/map_geometry,
    as mapfit does live), or None when the map has none.

    learned: start from the map's learned file (data/maps, maplearn.DATA)
    so the spots the live game refused (MapModel.refused) are refused here
    too - the executor then picks the spots it picks live, and a CashGame
    given this model refuses the same clicks.

    With it the executor chooses spots on the real ground, and the blimp check
    measures each tower's reach as the track cells inside its range
    (strategy.Executor._reach_fn) instead of OpenModel's 2.5 x range, so the
    simulated ratio sees short tracks, long tracks and towers that only cover
    one lane. Built once per map: applying the geometry takes ~0.1 s."""
    key = (map_name, learned)
    if key not in _MAP_MODELS:
        from btd6bot import mapgeom
        from btd6bot.layout import LAYOUTS
        from btd6bot.maplearn import MapModel
        geom = mapgeom.load(map_name)
        model = None
        if geom is not None:
            playfield = LAYOUTS["16:10"]["playfield"]
            base = MapModel.load(map_name, playfield) if learned else MapModel(map_name, playfield)
            model = mapgeom.apply(base, geom)
        _MAP_MODELS[key] = model
    return _MAP_MODELS[key]


def full_account():
    from btd6bot.account import AccountState
    a = AccountState()
    a.unlocked_towers = set(T.TOWERS)
    a.unlocked_heroes = set(T.HEROES)
    a.unlocked_upgrades = {k: [5, 5, 5] for k in T.TOWERS}
    return a


def simulate(strat, mode, map_name="Monkey Meadow", water=False, ticks=10, account=None, scenario=None,
             real_map=False, learned=False, income=None, boards=None, click_budget=None):
    """Run one game offline. scenario: {"start_round", "start_cash",
    "income_multiplier"} to play an optimized build as it was planned (Fast
    Track start, Double Cash income: its `optimizer.scenario`); default the
    mode's own start and income. real_map: place on the map's own geometry
    (map_model) rather than the open field, where the map has geometry;
    learned (with real_map): with the spots the live game refused on it
    refused here too (map_model(learned=True)).
    income: rnd -> cash the round pays at base rates, instead of the round
    calendar's (Apopalypse's random rounds: tools/apopalypse_check.py);
    boards: a dict filled with {round: {tid: (kind, tiers, fx, fy)}}, the
    towers standing when each round starts.
    click_budget: seconds of clicking each round allows after the first
    (Apopalypse: about one round's length), each purchase costing what it
    costs live (CashGame.clock, clicktime.seconds); None: as many purchases
    as `ticks` allows, however long they would take. The round is paid
    first and the board it starts with is the one rated - its purchases are
    made while it plays, as under continuous sends.
    Returns a dict:
    gaps      [(round, need, what is missing)] signatures the defence could not
              pop at the start of a round that brings them
    ramp      [(round, ratio)] blimp damage ratio at the start of blimp rounds
    answers   [(round, text)] purchases of towers the plan does not list
    build     {tid: crosspath} at the end
    placed    {tid: (kind, tiers, fx, fy)} at the end: where each tower stands
    spent     total cash spent"""
    rules = S.rules(mode)
    fam = S.PRICE_FAMILY.get(mode, "hard")
    hero = strat.get("hero") or "quincy"
    income_fn = income
    real = map_model(map_name, learned) if real_map else None
    g = CashGame(fam, hero, real)
    g.cash = START_CASH.get(mode, DEFAULT_START_CASH)
    model = real or OpenModel(map_name, water)
    ex = S.Executor(g, model, strat, mode, account or full_account())
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
    # maps with long path phases (Erosion): as the live match does
    # (Match._repaint_for_round), new towers need ground only until the
    # phase ends, and the towers on ground the map destroys are forgotten
    phase_geom = None
    if real is not None:
        try:
            from btd6bot import mapgeom
            geom = mapgeom.load(map_name)
            if geom and mapgeom.phase_end(geom, start) is not None:
                phase_geom = geom
        except Exception:
            phase_geom = None
    ground_seen = None
    for rnd in range(start, end + 1):
        g.round = rnd
        if phase_geom is not None:
            horizon = mapgeom.phase_end(phase_geom, rnd)
            if horizon != getattr(ex, "ground_horizon", None):
                ex.ground_horizon = horizon
                ex.track_changed()
            lost = mapgeom.lost_ground(model, phase_geom, ground_seen, rnd)
            if lost is not None:
                ex.ground_lost(lost)
            ground_seen = rnd
        if click_budget and rnd > start:
            # continuous sends: the round starts with the board as it stands,
            # pays as it plays, and the bot buys while it does - as far as
            # the seconds go
            if boards is not None:
                boards[rnd] = {p.tid: (p.kind, tuple(p.tiers), p.x, p.y) for p in g.towers.values()}
            income = (TH.round_cash(set_name, rnd) if income_fn is None else income_fn(rnd)) * mult
            g.cash += income
            total_in += income
            g.clock = 0.0
            for _ in range(50):           # (a purchase that costs no clicking cannot loop forever)
                if g.clock >= click_budget:
                    break
                if not ex.tick(g.cash, rnd) and not (g.cash > 800 and ex.surplus(g.cash, rnd)):
                    break
            continue
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
        if boards is not None:
            boards[rnd] = {p.tid: (p.kind, tuple(p.tiers), p.x, p.y) for p in g.towers.values()}
        for sig in TH.round_signatures(set_name, rnd):
            ok, how = ex._covers(sig)
            if not ok:
                out["gaps"].append((rnd, TH.sig_name(sig), how))
        load = TH.round_blimp_load(set_name, rnd, double_hp=bool(rules.get("tough_moabs")))
        if load:
            out["ramp"].append((rnd, round(ex.blimp_ratio(load), 2)))
        income = (TH.round_cash(set_name, rnd) if income_fn is None else income_fn(rnd)) * mult
        g.cash += income                  # the round is played and paid
        total_in += income
        for _ in range(ticks // 2):       # buying during the round
            if not ex.tick(g.cash, rnd):
                break
    out["answers"] = [(r, t) for r, t in g.bought if t.split()[1].startswith("ans_")]
    out["surplus"] = [(r, t) for r, t in g.bought
                      if t.split()[1] not in plan_ids and not t.split()[1].startswith(("ans_", "hero"))]
    out["build"] = {p.tid: "-".join(map(str, p.tiers)) for p in g.towers.values()}
    out["placed"] = {p.tid: (p.kind, tuple(p.tiers), p.x, p.y) for p in g.towers.values()}
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
                continue    # random rounds: no calendar here (tools/apopalypse_check.py rates them)
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
