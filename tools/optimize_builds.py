"""Choose the cheapest safe tower builds and spots for a map and mode, from the game's own numbers.

Why
---
The hand-written and generated strategies place towers by role and hope
the defence holds; the bot lost games on maps where it did not (Luminous
Cove, Castle Revenge, Dark Path, ...). This tool builds a plan with the
analytic evaluator btd6bot/dps_model.py instead: every purchase is the one
that makes the coming rounds safe for the least money, at a spot chosen
from the map's geometry, and money that safety does not need goes into the
tower whose XP is worth most (tower XP is split by cash invested; towers
still short of their paragon or upgrades are worth more).

What it does, per map and mode
------------------------------
1. Economy (see `Economy`): the mode's start round and cash and the game's
   own income per round (data/rounds.json) at base rates - no Double Cash,
   no Fast Track - which is the hardest case: with the account's boosts the
   same plan has at least as much money at every round, so it is at least
   as safe (proof in docs/optimizer.md).
2. Candidate spots per tower kind (see `MapSetup`): cells where the tower
   may stand (btd6bot.placement.valid_spots on the map's geometry), ranked by
   how much bloon route lies inside the tower's range (line of sight counted).
3. Greedy build order (see `optimize`), round by round:
     * before round r, while some round r..r+LOOKAHEAD would leak at the
       required safety margin, buy the affordable action (place a tower at
       its best free spot, possibly with its first tiers; or one/two tiers
       of an upgrade) that removes the most leaked bloon health per dollar;
       actions on the XP target count up to XP_PREFERENCE times more;
     * once the next SURPLUS_WINDOW rounds are all safe, spend what is left
       on the XP target (the action that adds most margin per dollar);
     * then the round is played and its cash comes in.
   "Safe at margin M" means the round pops without a leak with every tower
   at 1/M of its modelled strength (dps_model.round_margin).
4. Output: strategies/optimized/<map id>_<mode>.yaml in the strategy format,
   with exact spots as {"at": [fx, fy]} (screen fractions of the 1920x1200
   window) next to the usual `segment`, and comments with the numbers:
   round bought, cost, which round it secures, the margin per round, the
   predicted game length and XP per hour.

Calibration (`--calibrate`)
---------------------------
Replays the bot's own logged games (logs/bot.log: every placement with its
screen position, every upgrade, lives at every round) through the
evaluator and compares its margins with the lives really lost. The table it
prints is how SAFETY_MARGIN below was chosen; docs/optimizer.md has the
numbers.

Usage
-----
    python tools/optimize_builds.py                      # the default maps x modes (see DEFAULT_RUNS)
    python tools/optimize_builds.py "Dark Path" hard     # one map / mode
    python tools/optimize_builds.py "Dark Path" hard --target ninja
    python tools/optimize_builds.py --calibrate          # model vs the bot's logged games
    python tools/optimize_builds.py --check FILE.yaml    # re-evaluate a written plan
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402
from btd6bot import towers as T  # noqa: E402

log = logging.getLogger("optimize_builds")

OUT_DIR = ROOT / "strategies" / "optimized"
LOG_FILE = ROOT / "logs" / "bot.log"
RESULTS_FILE = ROOT / "logs" / "results.jsonl"

# --- the safety bar ------------------------------------------------------------
# Every round must still pop without a leak with all towers at 1/SAFETY_MARGIN
# of their modelled strength. Chosen from --calibrate on the bot's 2,104
# logged rounds (logs/bot.log, 2026-10-21/22): of the rounds the model rated
# below 1.0, 5.4% lost lives; 1.0-2.0: 1.0%; 2.0 and above: 0.5% (6 of
# 1,229, four of them on Logs); 6.0 and above: none. See docs/optimizer.md.
SAFETY_MARGIN = 2.0

# --- search settings (assumptions, see docs/optimizer.md) ---------------------
LOOKAHEAD = 3            # rounds ahead that must be safe before the next round starts
SURPLUS_WINDOW = 8       # rounds ahead that must be safe before money goes to XP instead
XP_PREFERENCE = 2.0      # an action on the XP target may be this much less cost-efficient
SPOTS_PER_KIND = 8       # best spots kept per tower kind (diverse: no two overlapping)
SPOT_STRIDE = 2          # grid cells between candidate spots (the grid is 160 x 108)
MAX_PLACE_TIERS = 3      # a new tower may come with up to this many tiers at once
MAX_UPGRADE_STEP = 5     # an upgrade action buys up to this many tiers of one path at once
NEVER_KINDS = {"mortar", "dartling"}   # aimed by hand: they do nothing for the bot (dps_model)
INCOME_KINDS = {"farm"}  # banana farms: only as an XP target (their cash is not modelled)
SHORTLIST = 16           # actions simulated per purchase (the rest are ranked out by a quick yardstick)
SHORTLIST_TARGET = 4     # ... plus this many more on the XP target
PROXY_PACKING = 0.05     # bloons per world unit assumed by the yardstick (a typical stream)

# --- maps and modes produced by default -----------------------------------------
# The maps the bot lost on (logs/results.jsonl "defeat", 2026-10-22) with the
# mode lost in, plus the Easy/Medium-family modes the planner is working through.
LOST = {
    "Luminous Cove": ["hard"], "Castle Revenge": ["hard"], "Dark Path": ["hard"], "Last Resort": ["hard"],
    "Pat's Pond": ["hard"], "Party Parade": ["hard"], "Enchanted Glade": ["hard"], "Covered Garden": ["hard"],
    "Ancient Portal": ["medium", "deflation"], "Bloonarius Prime": ["deflation"],
}
FAMILY_MODES = ["easy", "primary_only", "deflation", "medium", "military_only", "reverse"]
DEFAULT_RUNS = [(m, mode) for m, modes in LOST.items() for mode in dict.fromkeys(modes + FAMILY_MODES)]


# ===========================================================================
# Economy: what cash a mode gives, round by round
# ===========================================================================

@dataclass
class Economy:
    """Cash of one mode at base rates.

    start_round / end_round / start_cash: from the mode's Mod assets (attacks.json
    "modes": StartingRound, EndRound, StartingCash); income(r): data/rounds.json
    "cash" of round r (pops + end-of-round bonus, as the game pays them) times
    the mode's cash multiplier (Half Cash 0.5, Deflation 0)."""
    mode: str
    family: str           # price family for btd6bot.towers prices
    start_round: int
    end_round: int
    start_cash: float
    cash_mult: float

    def income(self, rnd):
        rd = ((D._json(str(D.ROUNDS_FILE)).get("abr" if self.mode == "abr" else "standard") or {})
              .get(str(rnd)) or {})
        return float(rd.get("cash") or 0.0) * self.cash_mult


def economy(mode, boosts=None):
    """The mode's economy; with the account's boosts ({"double_cash": bool,
    "fast_track": bool}, as btd6bot.boosts reads them) when given:
    Fast Track moves the start (fast_track_start) and Double Cash doubles
    every income where it pays (boosts.double_cash_applies)."""
    from btd6bot import strategy as S
    from btd6bot.boosts import double_cash_applies
    rules = D.mode_rules(mode)
    mr = S.MODE_RULES.get(mode, {})
    econ = Economy(mode=mode, family=S.PRICE_FAMILY.get(mode, "medium"),
                   start_round=int(mr.get("start_round") or rules["start_round"] or 1),
                   end_round=int(mr.get("end_round") or rules["end_round"] or 60),
                   start_cash=float(rules["start_cash"]), cash_mult=float(rules["cash"]))
    boosts = boosts or {}
    if boosts.get("fast_track") and mode not in ("chimps", "deflation"):
        econ.start_round, econ.start_cash = fast_track_start(econ, double_cash_applies(boosts, mode))
    elif mode == "deflation" and boosts.get("double_cash"):
        # logged: Deflation games on the account start with $40,400, double the $20,000
        econ.start_cash *= 2.0
    if double_cash_applies(boosts, mode):
        econ.cash_mult *= 2.0
    return econ


def fast_track_start(econ, double_cash=True):
    """(round, cash) a Fast Track game starts with. The game skips the
    first quarter of the mode's rounds: start = start_round - 1 +
    end_round // 4 matches every logged game (Easy round 10, Hard round 22;
    logs/bot.log 2026-10-21/22). Cash: the skipped rounds' income on top of
    the start cash (doubled with Double Cash), less 10% to stay on the safe
    side (logged with Double Cash: Hard $9,700 against $9,922 by this sum)."""
    start = econ.start_round - 1 + econ.end_round // 4
    skipped = sum(econ.income(r) for r in range(econ.start_round, start))
    return start, 0.9 * (2.0 if double_cash else 1.0) * (econ.start_cash + skipped)


def seconds_per_round(mode):
    """Real seconds one round takes the bot (fast-forward, buying, popups),
    the median over its logged wins in this mode (logs/results.jsonl), else
    over all wins; 12 s when nothing is logged."""
    rows = []
    try:
        for line in RESULTS_FILE.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("outcome") == "victory" and r.get("minutes"):
                rows.append(r)
    except (OSError, ValueError):
        pass

    def per_round(r):
        if r["mode"] not in D.MODE_MODS:
            return None
        # the logged games ran with the account's Fast Track
        start = economy(r["mode"], {"fast_track": True}).start_round
        n = max(1, int(r["round"]) - start + 1)
        return r["minutes"] * 60.0 / n

    same = [x for x in (per_round(r) for r in rows if r["mode"] == mode) if x]
    every = [x for x in (per_round(r) for r in rows) if x]
    return statistics.median(same or every) if (same or every) else 12.0


# ===========================================================================
# The account: what is unlocked and whose XP is worth most
# ===========================================================================

def load_account():
    """The current account (data/current_account.txt), or None."""
    try:
        from btd6bot.account import AccountState
        from btd6bot.identity import account_path
        uid = (ROOT / "data" / "current_account.txt").read_text(encoding="utf-8").strip()
        return AccountState.load(account_path(uid))
    except Exception:
        return None


def xp_weights(account):
    """{tower kind: value of one XP point to the account}, 0.1 .. 1.

    A tower still needs XP for its locked upgrades and, if it has one, its
    paragon (data/tower_xp.json prices). As in the planner's paragon_status,
    a tower one Hard game (or less) from everything it needs counts fully
    and one ten games away 10% of that: weight = 0.5 + 0.5 x closeness.
    Towers that have everything get 0.1 (their XP has no known use,
    docs/tower_xp.md). Without account data every tower counts fully."""
    if account is None:
        return {k: 1.0 for k in T.TOWERS}
    weights = {k: 0.1 for k in T.TOWERS}
    try:
        from btd6bot.planner import DEFAULT_CONFIG, load_tower_xp_prices
        prices = load_tower_xp_prices(DEFAULT_CONFIG.tower_xp_path)
        reach = DEFAULT_CONFIG.paragon_reach_xp
    except Exception as e:
        log.warning("tower XP prices unavailable (%s): every tower weighted fully", e)
        return {k: 1.0 for k in T.TOWERS}
    for kind, price in prices.items():
        have = (account.unlocked_upgrades or {}).get(kind) or [0, 0, 0]
        locked = sum(xp for path, tiers in enumerate(price.upgrade_xp)
                     for tier, xp in enumerate(tiers, start=1) if tier > have[path])
        paragon = 0 if (price.paragon is None or (account.paragons or {}).get(kind)) else price.paragon_xp
        needed = max(0.0, locked + paragon - float((account.tower_xp or {}).get(kind) or 0.0))
        if needed > 0:
            weights[kind] = 0.5 + 0.5 * min(1.0, reach / needed)
    return weights


def unlocked_tiers(account, kind):
    """Highest tier per path the account may buy (5-5-5 without account data)."""
    if account is None:
        return (5, 5, 5)
    have = (account.unlocked_upgrades or {}).get(kind)
    if kind not in (account.unlocked_towers or T.TOWERS):
        return None
    return tuple(have) if have else (0, 0, 0)


# ===========================================================================
# Map: spots and line of sight
# ===========================================================================

@dataclass
class Spot:
    cell: tuple          # (column, row) of the MapModel grid
    x: float             # world position of a tower standing there
    z: float
    h: float             # height of the ground it stands on
    fx: float            # screen fractions of the 1920x1200 window
    fy: float
    score: float         # covered route length (world units, all routes summed)


class MapSetup:
    """Geometry of one map for one mode: the evaluator's Track, the bot's
    MapModel grids (placement, line of sight) and candidate spots per kind."""

    def __init__(self, map_name, mode):
        from btd6bot import layout as L
        from btd6bot import mapgeom as G
        from btd6bot.maplearn import MapModel
        self.map_name = map_name
        self.track = D.Track(map_name, reverse=(mode == "reverse"))
        self.model = MapModel(map_name, L.LAYOUTS["16:10"]["playfield"])
        G.apply(self.model, self.track.geom)
        self._spots = {}

    # -- line of sight ---------------------------------------------------------
    def sight(self, x, z, pts, samples=12):
        """Visible mask of world points pts (N x 3) from a tower at (x, z):
        no sight-blocking cell of the MapModel on the straight line between."""
        grid = self.model.sight
        if grid is None or not grid.any():
            return np.ones(len(pts), bool)
        t = np.linspace(0.1, 0.9, samples)[:, None]
        px = x + (pts[:, 0][None, :] - x) * t
        pz = z + (pts[:, 1][None, :] - z) * t
        ph = pts[:, 2][None, :] * t
        flat = np.stack([px.ravel(), pz.ravel(), ph.ravel()], axis=1)
        cells = np.rint(self.track.proj.to_cells(flat)).astype(int)
        h, w = grid.shape
        cells[:, 0] = np.clip(cells[:, 0], 0, w - 1)
        cells[:, 1] = np.clip(cells[:, 1], 0, h - 1)
        blocked = grid[cells[:, 1], cells[:, 0]].reshape(samples, -1).any(axis=0)
        return ~blocked

    def sight_for(self, kind):
        from btd6bot import placement as P
        return self.sight if kind != "hero" and P.needs_sight(kind) else None

    # -- spots -----------------------------------------------------------------
    def cell_spot(self, cell):
        fx, fy = self.model.cell_to_frac(*cell)
        x, z, h = self.track.frac_to_world(fx, fy)
        return Spot(cell=tuple(cell), x=x, z=z, h=h, fx=fx, fy=fy, score=0.0)

    def spots(self, kind):
        """The best SPOTS_PER_KIND spots for a kind, best first, no two of
        them overlapping (so later towers of the kind have room)."""
        if kind in self._spots:
            return self._spots[kind]
        from btd6bot import placement as P
        ok = P.valid_spots(self.model, kind)
        out = []
        if ok is not None and ok.any():
            rows, cols = np.nonzero(ok)
            keep = (rows % SPOT_STRIDE == 0) & (cols % SPOT_STRIDE == 0)
            rows, cols = rows[keep], cols[keep]
            prof = D.profile(kind, (0, 0, 0))
            radius = None if (prof is None or prof.is_global) else max(prof.range, 1.0)
            sight = self.sight_for(kind)
            scored = []
            for r, c in zip(rows, cols):
                sp = self.cell_spot((int(c), int(r)))
                if radius is None:
                    sp.score = 0.0
                else:
                    zones = self.track.zones(sp.x, sp.z, radius, sight=sight)
                    sp.score = sum(z.length for z in zones if z)
                    if sp.score <= 0:
                        continue
                scored.append(sp)
            # global towers: keep them off the good spots (lowest score first)
            scored.sort(key=lambda s: s.score, reverse=radius is not None)
            gap = 2.0 * P.footprint_radius(kind) / P.units_per_cell(self.model)
            for sp in scored:
                if all((sp.cell[0] - o.cell[0]) ** 2 + (sp.cell[1] - o.cell[1]) ** 2 >= gap * gap for o in out):
                    out.append(sp)
                if len(out) >= SPOTS_PER_KIND:
                    break
        self._spots[kind] = out
        return out

    def free_spot(self, kind, towers):
        """The best spot of a kind whose footprint does not overlap a placed tower."""
        from btd6bot import placement as P
        upc = P.units_per_cell(self.model)
        r = P.footprint_radius(kind) / upc
        for sp in self.spots(kind):
            if all((sp.cell[0] - t.spot.cell[0]) ** 2 + (sp.cell[1] - t.spot.cell[1]) ** 2
                   >= (r + P.footprint_radius(t.kind) / upc) ** 2 for t in towers):
                return sp
        return None


# ===========================================================================
# Builds, actions and their evaluation
# ===========================================================================

@dataclass
class Tower:
    tid: str
    kind: str
    spot: Spot
    tiers: tuple
    spent: float = 0.0


@dataclass
class Action:
    """Place a tower (tid None) or upgrade one, to `tiers`, for `cost`."""
    kind: str
    tiers: tuple
    cost: float
    tid: str | None = None
    spot: Spot | None = None


def legal(tiers):
    """At most two paths used, at most one of them above tier 2."""
    return sum(t > 0 for t in tiers) <= 2 and sum(t > 2 for t in tiers) <= 1


def upgrade_cost(kind, tiers_from, tiers_to, family):
    cost = 0.0
    for path in range(3):
        for tier in range(tiers_from[path] + 1, tiers_to[path] + 1):
            cost += T.upgrade_cost(kind, path + 1, tier, family)
    return cost


class Evaluator:
    """Runs dps_model on builds, with the stations of unchanged towers cached."""

    def __init__(self, setup, mode):
        self.setup = setup
        self.mode = mode
        self._stations = {}

    def station_of(self, tower, towers):
        """The station of one tower standing among `towers` (None when it
        does no damage or reaches no track). It depends only on the tower
        and the supporters on the map (villages), so it is cached by
        (kind, crosspath, cell, supporters)."""
        if tower.kind == "hero":
            return None
        supporters = tuple(sorted((t.kind, t.tiers, t.spot.cell) for t in towers if t.kind != "hero"
                                  and (D.profile(t.kind, t.tiers) is not None and D.profile(t.kind, t.tiers).buffs)))
        key = (tower.kind, tower.tiers, tower.spot.cell, supporters or None)
        st = self._stations.get(key)
        if st is None:
            placed = [D.Placed(t.tid, t.kind, t.tiers, t.spot.x, t.spot.z) for t in towers if t.kind != "hero"]
            me = D.Placed(tower.tid, tower.kind, tower.tiers, tower.spot.x, tower.spot.z)
            st = D.station_for(me, placed, self.setup.track, sight=self.setup.sight) or False
            self._stations[key] = st
        return st or None

    def stations(self, towers):
        """Stations for the towers (support buffs between them included)."""
        return [st for st in (self.station_of(t, towers) for t in towers) if st is not None]

    def results(self, towers, rounds, margin=SAFETY_MARGIN):
        """{round: RoundResult} with every tower at 1/margin strength."""
        st = self.stations(towers)
        return {r: D.simulate_round(st, self.mode, r, self.setup.track, strength=1.0 / margin) for r in rounds}

    def leak(self, towers, rounds, margin=SAFETY_MARGIN):
        """{round: leaked health} with every tower at 1/margin strength."""
        return {r: res.leaked_rbe for r, res in self.results(towers, rounds, margin).items()}

    def capacity(self, station, bloon_id):
        """Health a station can take off one bloon id's outer layer while
        such a bloon crosses its zone (best route): a quick yardstick used to
        shortlist actions before simulating them."""
        if station is None:
            return 0.0
        rates = getattr(station, "_full_rates", None)
        if rates is None:
            station.strength = 1.0
            rates = station._full_rates = D._Rates(station)
        lay = D.layer(bloon_id)
        best = 0.0
        for route, zone in enumerate(station.zones):
            if zone is None:
                continue
            r = rates.get(bloon_id, 1.0, PROXY_PACKING, route)
            if r is not None:
                best = max(best, r[0] * zone.length / lay.speed)
        return best

    def margins(self, towers, rounds):
        st = self.stations(towers)
        return {r: D.round_margin(st, self.mode, r, self.setup.track) for r in rounds}

    def end_times(self, towers, rounds):
        st = self.stations(towers)
        return {r: D.simulate_round(st, self.mode, r, self.setup.track).end_time for r in rounds}


# ===========================================================================
# The greedy optimizer
# ===========================================================================

@dataclass
class Step:
    rnd: int              # bought before this round
    action: Action
    tid: str
    why: str
    cash_after: float


@dataclass
class Plan:
    map_name: str
    mode: str
    target: str | None
    hero: str
    steps: list = field(default_factory=list)
    towers: list = field(default_factory=list)
    unsafe: list = field(default_factory=list)     # rounds it could not make safe in time
    margins: dict = field(default_factory=dict)
    spent_by_kind: dict = field(default_factory=dict)
    share_by_round: dict = field(default_factory=dict)
    seconds: float = 0.0
    econ: Economy | None = None
    boosts: dict = field(default_factory=dict)


class Optimizer:
    """One greedy optimization of one map, mode and XP target (see run())."""

    def __init__(self, map_name, mode, target=None, account=None, hero="quincy", boosts=None):
        self.map_name, self.mode, self.target = map_name, mode, target
        self.account = account
        self.boosts = dict(boosts or {})
        self.econ = economy(mode, self.boosts)
        self.setup = MapSetup(map_name, mode)
        self.ev = Evaluator(self.setup, mode)
        self.hero = hero
        self.weights = xp_weights(account)
        self.kinds = self._kinds()

    def _kinds(self):
        """Tower kinds this mode and account allow and the model can use."""
        from btd6bot import strategy as S
        only = S.MODE_TOWER_FILTER.get(self.mode)
        out = []
        for kind, info in T.TOWERS.items():
            if kind in NEVER_KINDS or (kind in INCOME_KINDS and kind != self.target):
                continue
            if only and info.get("category") != only:
                continue
            if unlocked_tiers(self.account, kind) is None:
                continue
            if D.profile(kind, (0, 0, 0)) is None or not self.setup.spots(kind):
                continue
            out.append(kind)
        return out

    # -- candidate actions -------------------------------------------------------
    def actions(self, towers, cash):
        fam = self.econ.family
        out = []
        for kind in self.kinds:
            cap = unlocked_tiers(self.account, kind)
            spot = self.setup.free_spot(kind, towers)
            if spot is None:
                continue
            base = T.tower_cost(kind, fam)
            if base > cash:
                continue
            for tiers in _bundles(cap, MAX_PLACE_TIERS):
                cost = base + upgrade_cost(kind, (0, 0, 0), tiers, fam)
                if cost <= cash and D.profile(kind, tiers) is not None:
                    out.append(Action(kind=kind, tiers=tiers, cost=cost, spot=spot))
        for t in towers:
            if t.kind == "hero":
                continue
            cap = unlocked_tiers(self.account, t.kind)
            for path in range(3):
                for step in range(1, MAX_UPGRADE_STEP + 1):
                    new = list(t.tiers)
                    new[path] += step
                    new = tuple(new)
                    if new[path] > cap[path] or not legal(new) or D.profile(t.kind, new) is None:
                        break
                    cost = upgrade_cost(t.kind, t.tiers, new, fam)
                    if cost > cash:
                        break
                    out.append(Action(kind=t.kind, tiers=new, cost=cost, tid=t.tid))
        return out

    @staticmethod
    def apply(towers, action, tid):
        """New tower list with the action done (towers are not changed in place)."""
        if action.tid is None:
            return towers + [Tower(tid, action.kind, action.spot, action.tiers, action.cost)]
        return [Tower(t.tid, t.kind, t.spot, action.tiers, t.spent + action.cost) if t.tid == action.tid else t
                for t in towers]

    def preference(self, action):
        """How much more an action is worth for XP: the target's full
        XP_PREFERENCE, other towers whose XP the account still needs part of it."""
        if action.kind == self.target:
            return XP_PREFERENCE
        return 1.0 + (XP_PREFERENCE - 1.0) * 0.5 * (self.weights.get(action.kind, 0.1) >= 0.5)

    # -- the search ---------------------------------------------------------------
    def run(self):
        t0 = time.time()
        econ = self.econ
        plan = Plan(self.map_name, self.mode, self.target, self.hero, econ=econ, boosts=self.boosts)
        towers, cash, n = [], econ.start_cash, 0
        hero_cost = T.hero_cost(self.hero, econ.family)
        hero_placed = False
        last = econ.end_round
        # without income (Deflation) every round is paid from the start cash:
        # plan for all of them at once
        no_income = econ.cash_mult == 0
        for rnd in range(econ.start_round, last + 1):
            # 1. safety for the next LOOKAHEAD rounds
            window = list(range(rnd, last + 1 if no_income else min(last, rnd + LOOKAHEAD) + 1))
            towers, cash, n = self._make_safe(plan, towers, cash, n, rnd, window, must=True)
            # the hero once the first tower stands and it is affordable (its
            # damage is not modelled: it only adds safety)
            if not hero_placed and towers and cash >= hero_cost:
                cash -= hero_cost
                hero_placed = True
                plan.steps.append(Step(rnd, Action("hero", (0, 0, 0), hero_cost), "hero",
                                       "hero: not counted by the model (extra safety)", cash))
            # 2. further rounds: buy ahead while affordable
            ahead = window if no_income else list(range(rnd, min(last, rnd + SURPLUS_WINDOW) + 1))
            towers, cash, n = self._make_safe(plan, towers, cash, n, rnd, ahead, must=False)
            # 3. surplus to the XP target, if everything ahead is safe
            if self.target and not any(v > 0 for v in self.ev.leak(towers, ahead).values()):
                towers, cash, n = self._spend_surplus(plan, towers, cash, n, rnd, ahead)
            plan.share_by_round[rnd] = _shares(towers)
            cash += econ.income(rnd)
        plan.towers = towers
        rounds = list(range(econ.start_round, last + 1))
        plan.margins = self._timeline_margins(plan, rounds)
        plan.unsafe = [r for r, m in plan.margins.items() if m < SAFETY_MARGIN]
        for t in towers:
            plan.spent_by_kind[t.kind] = plan.spent_by_kind.get(t.kind, 0.0) + t.spent
        plan.seconds = time.time() - t0
        return plan

    def _make_safe(self, plan, towers, cash, n, rnd, window, must):
        """Buy the best leak-per-dollar actions until the window is safe.

        Actions are scored on every round of the window that leaks (nearer
        rounds weigh more). The best action may cost more than the cash in
        hand but less than what comes in before the first leaking round:
        then nothing is bought now and the money is saved for it - unless
        the round about to start leaks (must), when the best affordable
        action is bought anyway."""
        while True:
            leaks = self.ev.leak(towers, window)
            bad = {r: v for r, v in leaks.items() if v > 0}
            if not bad:
                return towers, cash, n
            first = min(bad)
            budget = cash + sum(self.econ.income(r) for r in range(rnd, first))
            base = sum(v / (1 + (r - rnd)) for r, v in bad.items())
            best = best_now = None
            best_score = best_now_score = 0.0
            for a in self.shortlist(towers, self.actions(towers, budget), bad, rnd):
                after = self.ev.leak(self.apply(towers, a, "trial"), list(bad))
                gain = base - sum(v / (1 + (r - rnd)) for r, v in after.items())
                if gain <= 1e-6:
                    continue
                score = gain / max(a.cost, 1.0) * self.preference(a)
                if score > best_score:
                    best, best_score = a, score
                if a.cost <= cash and score > best_now_score:
                    best_now, best_now_score = a, score
            if best is not None and best.cost > cash:
                if not (must and first == rnd and best_now is not None):
                    return towers, cash, n          # save for it
                best = best_now
            if best is None:
                return towers, cash, n
            n, tid = self._tid(best, n)
            towers = self.apply(towers, best, tid)
            cash -= best.cost
            plan.steps.append(Step(rnd, best, tid, f"secures round {first}" if first == rnd
                                   else f"ahead of round {first}", cash))

    def shortlist(self, towers, actions, bad, rnd):
        """The actions worth simulating: a quick yardstick (Evaluator.capacity:
        health the new or upgraded tower adds against the bloons that leak,
        capped at each bloon's total health) per dollar picks the best
        SHORTLIST of them, plus the best few on the XP target."""
        if len(actions) <= SHORTLIST:
            return actions
        leaked = {}
        for r, res in self.ev.results(towers, list(bad)).items():
            for bid, n in res.leaked.items():
                leaked[bid] = leaked.get(bid, 0.0) + n / (1 + (r - rnd))
        scored = []
        for a in actions:
            trial = self.apply(towers, a, "trial")
            new = next(t for t in trial if t.tid == (a.tid or "trial"))
            old = next((t for t in towers if t.tid == a.tid), None)
            st_new = self.ev.station_of(new, trial)
            st_old = self.ev.station_of(old, towers) if old else None
            value = 0.0
            for bid, n in leaked.items():
                gain = self.ev.capacity(st_new, bid) - self.ev.capacity(st_old, bid)
                value += n * min(D.rbe(bid), max(0.0, gain))
            scored.append((value / max(a.cost, 1.0) * self.preference(a), a))
        scored.sort(key=lambda va: -va[0])
        keep = [a for v, a in scored[:SHORTLIST] if v > 0]
        keep += [a for v, a in scored[SHORTLIST:] if a.kind == self.target and v > 0][:SHORTLIST_TARGET]
        return keep or [a for _, a in scored[:SHORTLIST]]

    def _spend_surplus(self, plan, towers, cash, n, rnd, window):
        """Money no round needs goes into the XP target: the target action
        that adds most margin to the hardest of the coming rounds per dollar."""
        while True:
            options = [a for a in self.actions(towers, cash) if a.kind == self.target]
            if not options:
                return towers, cash, n
            hardest = min(window, key=lambda r: self._quick_margin(towers, r))
            now = self._quick_margin(towers, hardest)
            best = max(options, key=lambda a: (self._quick_margin(self.apply(towers, a, "trial"), hardest) - now)
                       / max(a.cost, 1.0))
            n, tid = self._tid(best, n)
            towers = self.apply(towers, best, tid)
            cash -= best.cost
            plan.steps.append(Step(rnd, best, tid, "XP: surplus into the target tower", cash))

    def _quick_margin(self, towers, rnd):
        return D.round_margin(self.ev.stations(towers), self.mode, rnd, self.setup.track, iterations=5)

    def _tid(self, action, n):
        if action.tid is not None:
            return n, action.tid
        return n + 1, f"{action.kind[:3]}{n + 1}"

    def _timeline_margins(self, plan, rounds):
        """Margin of every round with the towers standing when it starts."""
        out = {}
        towers = []
        by_round = {}
        for s in plan.steps:
            by_round.setdefault(s.rnd, []).append(s)
        for r in rounds:
            for s in by_round.get(r, []):
                if s.action.kind != "hero":
                    towers = self.apply(towers, s.action, s.tid)
            out[r] = round(D.round_margin(self.ev.stations(towers), self.mode, r, self.setup.track), 2)
        return out


def _bundles(cap, max_tiers):
    """Crosspaths a new tower may be bought at directly: total tiers <=
    max_tiers, legal, within the account's unlocked tiers."""
    out = []
    for a in range(min(cap[0], max_tiers) + 1):
        for b in range(min(cap[1], max_tiers) + 1):
            for c in range(min(cap[2], max_tiers) + 1):
                t = (a, b, c)
                if sum(t) <= max_tiers and legal(t):
                    out.append(t)
    return out


def _shares(towers):
    """{kind: share of the non-hero cash invested} (what tower XP follows)."""
    total = sum(t.spent for t in towers if t.kind != "hero")
    out = {}
    for t in towers:
        if t.kind != "hero" and total > 0:
            out[t.kind] = out.get(t.kind, 0.0) + t.spent / total
    return out


# ===========================================================================
# XP per hour
# ===========================================================================

def xp_report(plan, weights):
    """Predicted tower XP of one game as planned (from the plan's start
    round), the target's share, its value-weighted XP and XP per hour."""
    from btd6bot.account import MAPS, GAME_MAP_CATEGORIES
    tx = D._json(str(ROOT / "data" / "tower_xp.json"))
    per_round = {int(k): float(v) for k, v in (tx.get("xp_per_round") or {}).items()}
    cat = GAME_MAP_CATEGORIES.get(plan.map_name) or MAPS.get(plan.map_name) or "beginner"
    mult = float((tx.get("map_difficulty_multipliers") or {}).get(cat, 1.0))
    econ = plan.econ or economy(plan.mode)
    start = econ.start_round
    rounds = range(start, econ.end_round + 1)
    xp = sum(per_round.get(r, 0.0) for r in rounds) * mult
    value = 0.0
    target_xp = 0.0
    for r in rounds:
        shares = plan.share_by_round.get(r) or {}
        value += per_round.get(r, 0.0) * mult * sum(weights.get(k, 0.1) * s for k, s in shares.items())
        target_xp += per_round.get(r, 0.0) * mult * shares.get(plan.target, 0.0)
    minutes = len(rounds) * seconds_per_round(plan.mode) / 60.0
    return {"game_xp": round(xp), "target_xp": round(target_xp), "valued_xp": round(value),
            "minutes": round(minutes, 1), "target_xp_per_hour": round(target_xp / minutes * 60) if minutes else 0,
            "valued_xp_per_hour": round(value / minutes * 60) if minutes else 0, "start_round": start}


# ===========================================================================
# Writing the plan
# ===========================================================================

def map_id(map_name):
    from btd6bot.mapgeom import map_id_for
    return map_id_for(map_name) or re.sub(r"\W+", "", map_name.lower())


def _segment(setup, tower):
    """Progress range [a, b] of the route stretch a tower covers (for the
    executor's role/segment spot picking, the fallback to the exact spot)."""
    prof = D.profile(tower.kind, tower.tiers)
    if prof is None or prof.is_global:
        return None
    zones = setup.track.zones(tower.spot.x, tower.spot.z, prof.range, sight=setup.sight_for(tower.kind))
    best = max(((z, p) for z, p in zip(zones, setup.track.paths) if z), key=lambda zp: zp[0].length, default=None)
    if best is None:
        return None
    z, p = best
    a = z.entry / p["length"]
    b = min(1.0, (z.entry + max(z.length, 1.0) * 1.6) / p["length"])
    return [round(a, 2), round(b, 2)]


def plan_yaml(plan, setup, weights, xp):
    """The plan as strategy YAML text (with explanatory comments)."""
    econ = plan.econ or economy(plan.mode)
    worst = min(plan.margins.values()) if plan.margins else 0.0
    weak = sorted(plan.margins.items(), key=lambda kv: kv[1])[:5]
    total = sum(plan.spent_by_kind.values()) or 1.0
    on = [b.replace("_", " ") for b, v in sorted(plan.boosts.items()) if v]
    lines = [
        "# OPTIMIZED by tools/optimize_builds.py from the game's own numbers - do not edit by hand:",
        "# change the optimizer or its data and run it again (see docs/optimizer.md).",
        "#",
        f"# {plan.map_name}, {plan.mode}: planned for rounds {econ.start_round}-{econ.end_round}, starting with "
        f"${econ.start_cash:,.0f} and the game's own income x{econ.cash_mult:g} "
        f"({'account boosts: ' + ', '.join(on) if on else 'no boosts'}). More money at every round only makes",
        "# it safer; with less (an account without these boosts) it is not proven safe - run with --base for that.",
        f"# Safety: every round pops without a leak with all towers at 1/{SAFETY_MARGIN:g} of their modelled",
        f"# strength (dps_model), except: {', '.join(str(r) for r in plan.unsafe) or 'none'}.",
        f"# Lowest margins: {', '.join(f'R{r} {m:.2f}' for r, m in weak)} (worst {worst:.2f}).",
        "# Cash by tower kind at the end: " + ", ".join(
            f"{k} ${v:,.0f} ({v / total:.0%})" for k, v in sorted(plan.spent_by_kind.items(), key=lambda kv: -kv[1])),
        f"# XP: XP target {plan.target or 'none'}; the game gives {xp['game_xp']:,} tower XP in about "
        f"{xp['minutes']} min, {xp['target_xp']:,} of it to the target",
        f"# ({xp['target_xp_per_hour']:,}/h); weighted by what each tower's XP is worth to the account: "
        f"{xp['valued_xp_per_hour']:,}/h.",
        "# Spots: `at` is the exact spot (screen fractions of the 1920x1200 window) the model evaluated;",
        "# `segment` the covered stretch of track, for the executor's own spot picking until `at` is wired.",
        "# The hero's damage is not modelled (extra safety).",
        f"id: opt_{map_id(plan.map_name)}_{plan.mode}",
        f"map: {plan.map_name}",
        f"modes: [{plan.mode}]",
    ]
    if plan.target:
        lines.append(f"xp_target: {plan.target}")
    lines.append(f"hero: {plan.hero}")
    final = {}
    for t in plan.towers:
        if t.kind != "hero":
            final[t.kind] = [max(a, b) for a, b in zip(final.get(t.kind, [0, 0, 0]), t.tiers)]
    lines += [
        "planner:",
        f"  maps: [{plan.map_name}]",
        "  towers: {" + ", ".join(f"{k}: [{', '.join(map(str, v))}]" for k, v in final.items()) + "}",
        "optimizer:",
        f"  scenario: {{start_round: {econ.start_round}, start_cash: {econ.start_cash:.0f}, "
        f"income_multiplier: {econ.cash_mult:g}, boosts: [{', '.join(on)}]}}",
        f"  safety_margin: {SAFETY_MARGIN}",
        f"  worst_margin: {worst:.2f}",
        f"  unsafe_rounds: [{', '.join(str(r) for r in plan.unsafe)}]",
        f"  minutes: {xp['minutes']}",
        f"  target_xp_per_hour: {xp['target_xp_per_hour']}",
        f"  valued_xp_per_hour: {xp['valued_xp_per_hour']}",
        "plan:",
    ]
    towers_now = {}
    for s in plan.steps:
        a = s.action
        if a.kind == "hero":
            lines.append(f"  - {{do: place, id: hero, kind: hero, role: dps}}   # R{s.rnd}: ${a.cost:,.0f}; {s.why}")
            continue
        cross = "-".join(map(str, a.tiers))
        note = f"R{s.rnd}: ${a.cost:,.0f}, {s.why}; cash left ${s.cash_after:,.0f}"
        if a.tid is None or s.tid not in towers_now:
            tower = Tower(s.tid, a.kind, a.spot, a.tiers, a.cost)
            towers_now[s.tid] = tower
            seg = _segment(setup, tower)
            seg_text = f", segment: [{seg[0]}, {seg[1]}]" if seg else ""
            lines.append(f"  - {{do: place, id: {s.tid}, kind: {a.kind}, role: dps{seg_text}, "
                         f"at: [{a.spot.fx:.3f}, {a.spot.fy:.3f}]}}   # {note}")
            if any(a.tiers):
                lines.append(f"  - {{do: upgrade, id: {s.tid}, to: {cross}}}")
            if strong_targeting(a.kind, a.tiers):
                lines.append(f"  - {{do: target, id: {s.tid}, mode: strong}}   # single-target: MOAB-class first "
                             "(as modelled)")
        else:
            lines.append(f"  - {{do: upgrade, id: {s.tid}, to: {cross}}}   # {note}")
    if plan.target:
        lines += [
            "fill:",
            f"  - {{do: upgrade, kind: {plan.target}, to: {_fill_cross(plan)}}}   # surplus: the target's own path",
            f"  - {{do: place, kind: {plan.target}, role: dps, max: 10}}",
        ]
    return "\n".join(lines) + "\n"


def strong_targeting(kind, tiers):
    """Single-target towers (sniper bullets) are modelled with "strong"
    targeting (dps_model Station.strong), so their plan step sets it."""
    prof = D.profile(kind, tiers)
    return bool(prof and any(s.reach == 0.0 for s in prof.sources))


def _fill_cross(plan):
    """The target's most-bought crosspath (where surplus cash should go)."""
    best = None
    for t in plan.towers:
        if t.kind == plan.target and (best is None or sum(t.tiers) > sum(best)):
            best = t.tiers
    return "-".join(map(str, best or (0, 0, 0)))


def write_plan(text, map_name, mode):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{map_id(map_name)}_{mode}.yaml"
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path


# ===========================================================================
# Running it: one map/mode, choosing the XP target
# ===========================================================================

def target_candidates(map_name, mode, weights, account, limit=3):
    """XP targets worth trying: towers whose XP is worth most (ties: the one
    whose best spot covers most route), that the mode allows and that can
    deal damage on this map."""
    from btd6bot import strategy as S
    only = S.MODE_TOWER_FILTER.get(mode)
    setup = MapSetup(map_name, mode)

    def fit(kind):
        prof = D.profile(kind, (0, 0, 0))
        if prof is not None and prof.is_global:
            return math.inf
        spots = setup.spots(kind) if kind in T.TOWERS else []
        return spots[0].score if spots else 0.0

    kinds = []
    for kind, w in sorted(weights.items(), key=lambda kv: (-round(kv[1], 2), -fit(kv[0]))):
        info = T.TOWERS.get(kind) or {}
        if kind in NEVER_KINDS or kind in INCOME_KINDS or (only and info.get("category") != only):
            continue
        if unlocked_tiers(account, kind) is None:
            continue
        prof = D.profile(kind, (0, 0, 0))
        if prof is None or not prof.sources or fit(kind) <= 0:
            continue
        kinds.append(kind)
    return kinds[:limit]


def optimize(map_name, mode, target=None, account=None, write=True, candidates=3, base=False):
    """Best plan for a map/mode: one optimization per XP target candidate
    (or the given target), keeping the safe plan with the most value-weighted
    XP per hour (else the one with the fewest unsafe rounds).
    base: plan without the account's boosts (Fast Track, Double Cash)."""
    weights = xp_weights(account)
    boosts = {} if base or account is None else dict(getattr(account, "boosts", {}) or {})
    hero = (getattr(account, "selected_hero", None) or "quincy") if account else "quincy"
    if hero not in T.HEROES:
        hero = "quincy"
    targets = [target] if target else target_candidates(map_name, mode, weights, account, candidates) or [None]
    best = None
    for tgt in targets:
        opt = Optimizer(map_name, mode, target=tgt, account=account, hero=hero, boosts=boosts)
        plan = opt.run()
        xp = xp_report(plan, weights)
        key = (len(plan.unsafe) == 0, -len(plan.unsafe), xp["valued_xp_per_hour"])
        log.info("%s %s target %s: unsafe %s, worst margin %.2f, valued XP/h %s (%.0f s)", map_name, mode, tgt,
                 plan.unsafe, min(plan.margins.values()), xp["valued_xp_per_hour"], plan.seconds)
        if best is None or key > best[0]:
            best = (key, plan, opt.setup, xp)
    _, plan, setup, xp = best
    text = plan_yaml(plan, setup, weights, xp)
    path = write_plan(text, map_name, mode) if write else None
    return plan, xp, path


# ===========================================================================
# The table of written plans (docs/optimizer.md)
# ===========================================================================

DOC_FILE = ROOT / "docs" / "optimizer.md"


def summary_table():
    """Markdown table of the plans in strategies/optimized."""
    import yaml
    rows = ["| Map | Mode | XP target | Cash by tower (top 4) | Worst margin | Rounds below "
            f"{SAFETY_MARGIN:g} | Minutes | Target XP/h | Valued XP/h |",
            "|---|---|---|---|---|---|---|---|---|"]
    share = re.compile(r"(\w+) \$[\d,]+ \((\d+%)\)")
    for path in sorted(OUT_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        d = yaml.safe_load(text)
        o = d.get("optimizer") or {}
        line = re.search(r"# Cash by tower kind at the end: (.*)", text)
        kinds = ", ".join(f"{k} {pct}" for k, pct in share.findall(line.group(1))[:4]) if line else ""
        unsafe = o.get("unsafe_rounds") or []
        rows.append(f"| {d['map']} | {d['modes'][0]} | {d.get('xp_target', '-')} | {kinds} | "
                    f"{o.get('worst_margin')} | {', '.join(map(str, unsafe)) if unsafe else 'none'} | "
                    f"{o.get('minutes')} | {o.get('target_xp_per_hour', 0):,} | {o.get('valued_xp_per_hour', 0):,} |")
    return "\n".join(rows)


def write_summary():
    """Put the table between the results markers of docs/optimizer.md."""
    text = DOC_FILE.read_text(encoding="utf-8")
    start, end = "<!-- results:start -->", "<!-- results:end -->"
    if start not in text or end not in text:
        return False
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    DOC_FILE.write_text(head + start + "\n" + summary_table() + "\n" + end + tail, encoding="utf-8")
    return True


# ===========================================================================
# Re-checking a written plan
# ===========================================================================

def replay_plan(plan, rounds=None):
    """Play a plan's steps the way the executor does - in order, each as soon
    as the cash allows - on the economy recorded in its `optimizer.scenario`,
    and return {round: margin} with the towers standing when each round
    starts. An independent check of a written file (it does not use the
    optimizer's own bookkeeping). plan: the parsed YAML dict."""
    (mode,) = plan["modes"]
    sc = (plan.get("optimizer") or {}).get("scenario") or {}
    econ = economy(mode)
    econ.start_round = int(sc.get("start_round", econ.start_round))
    econ.start_cash = float(sc.get("start_cash", econ.start_cash))
    econ.cash_mult = float(sc.get("income_multiplier", econ.cash_mult))
    setup = MapSetup(plan["map"], mode)
    ev = Evaluator(setup, mode)
    towers, cash, i = {}, econ.start_cash, 0
    steps = plan.get("plan") or []
    margins = {}
    for rnd in range(econ.start_round, econ.end_round + 1):
        while i < len(steps):
            step = steps[i]
            if step["do"] == "place" and step["kind"] == "hero":
                cost = T.hero_cost(plan.get("hero") or "quincy", econ.family)
            elif step["do"] == "place":
                cost = T.tower_cost(step["kind"], econ.family)
            elif step["do"] == "upgrade":
                t = towers[step["id"]]
                cost = upgrade_cost(t.kind, t.tiers, tuple(int(c) for c in str(step["to"]).split("-")), econ.family)
            else:
                cost = 0.0
            if cost > cash:
                break
            cash -= cost
            if step["do"] == "place" and step["kind"] != "hero":
                cell = setup.model.frac_to_cell(*step["at"])
                towers[step["id"]] = Tower(step["id"], step["kind"], setup.cell_spot(cell), (0, 0, 0), cost)
            elif step["do"] == "upgrade":
                t = towers[step["id"]]
                towers[step["id"]] = Tower(t.tid, t.kind, t.spot, tuple(int(c) for c in str(step["to"]).split("-")),
                                           t.spent + cost)
            i += 1
        if rounds is None or rnd in rounds:
            margins[rnd] = round(D.round_margin(ev.stations(list(towers.values())), mode, rnd, setup.track), 2)
        cash += econ.income(rnd)
    return margins


def check_plan(path):
    """Print a written plan's margins as replayed by replay_plan()."""
    import yaml
    plan = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    margins = replay_plan(plan)
    worst = min(margins.values()) if margins else None
    print(f"{path}: worst margin {worst} (written: {plan.get('optimizer', {}).get('worst_margin')}); "
          f"below {SAFETY_MARGIN:g}: {[r for r, m in margins.items() if m < SAFETY_MARGIN] or 'none'}")
    return margins


# ===========================================================================
# Calibration against the bot's own games
# ===========================================================================

LOG_PATTERNS = {
    "next": re.compile(r"NEXT: \[\w+\] (.+?) / (\w+) with (\S+?):"),
    "placed": re.compile(r"I game: placed (\S+) \((\w+)\) at ([\d.]+),([\d.]+)"),
    "upgraded": re.compile(r"I game: upgraded (\S+) -> (\d)-(\d)-(\d)"),
    "really": re.compile(r"W game: (\S+) is really (\d)-(\d)-(\d)"),
    "round": re.compile(r"I match: round (\d+)\s+cash (\S+)\s+lives (\S+)"),
    "result": re.compile(r"RESULT \{.*'outcome': '(\w+)', 'round': (\d+)"),
}


def logged_games(path=LOG_FILE):
    """Games in logs/bot.log: map, mode, strategy, and per round the towers
    standing when it started (screen position, crosspath) and the lives."""
    games, cur = [], None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return games
    for line in text.splitlines():
        m = LOG_PATTERNS["next"].search(line)
        if m:
            cur = {"map": m.group(1), "mode": m.group(2), "strategy": m.group(3), "towers": {}, "rounds": []}
            continue
        if cur is None:
            continue
        m = LOG_PATTERNS["placed"].search(line)
        if m:
            tid, kind, fx, fy = m.groups()
            cur["towers"][tid] = [kind, float(fx), float(fy), (0, 0, 0)]
            continue
        m = LOG_PATTERNS["upgraded"].search(line) or LOG_PATTERNS["really"].search(line)
        if m and m.group(1) in cur["towers"]:
            cur["towers"][m.group(1)][3] = tuple(int(m.group(i)) for i in (2, 3, 4))
            continue
        m = LOG_PATTERNS["round"].search(line)
        if m:
            try:
                lives = int(m.group(3))
            except ValueError:
                lives = None
            cur["rounds"].append((int(m.group(1)), lives, {k: tuple(v) for k, v in cur["towers"].items()}))
            continue
        m = LOG_PATTERNS["result"].search(line)
        if m:
            cur["outcome"], cur["last_round"] = m.group(1), int(m.group(2))
            games.append(cur)
            cur = None
    return games


CALIBRATION_RANGE = 64.0   # margins searched between 1/64 and 64


def corrected_outcomes(path=RESULTS_FILE):
    """{(map, mode, strategy, round): outcome} of results the bot corrected
    afterwards (logs/results.jsonl "note": a victory screen it missed was
    first logged as a defeat)."""
    out = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if "corrected" in str(r.get("note", "")):
                out[(r["map"], r["mode"], r["strategy"], int(r["round"]))] = r["outcome"]
    except (OSError, ValueError, KeyError):
        pass
    return out


def calibration_samples(games):
    """[(map, mode, strategy, round, lives lost, model margin)] for every
    logged round with a trustworthy lives reading (not above the mode's
    starting lives x1.2: OCR misreads like 2000) and at least one tower.
    Towers that need line of sight only count the track they can see, as
    in the optimizer."""
    from btd6bot import strategy as S
    setups, out = {}, []
    fixed = corrected_outcomes()
    for g in games:
        if g["mode"] not in D.MODE_MODS or g["mode"] == "apopalypse" or not g["rounds"]:
            continue
        key = (g["map"], g["mode"] == "reverse")
        try:
            setups.setdefault(key, MapSetup(g["map"], "reverse" if key[1] else "medium"))
        except ValueError:
            continue
        setup = setups[key]
        tr = setup.track
        for r in (g["last_round"] - 1, g["last_round"], g["last_round"] + 1):
            g["outcome"] = fixed.get((g["map"], g["mode"], g["strategy"], r), g["outcome"])
        cap = S.MODE_RULES.get(g["mode"], {}).get("lives") or 100
        rounds = g["rounds"]
        for i, (rnd, lives, snap) in enumerate(rounds):
            if lives is None or lives > cap * 1.2:
                continue
            if i + 1 < len(rounds):
                nxt_round, nxt_lives, _ = rounds[i + 1]
                if nxt_lives is None or nxt_round != rnd + 1 or nxt_lives > cap * 1.2:
                    continue
                lost = max(0, lives - nxt_lives)
            else:
                lost = lives if g.get("outcome") == "defeat" else 0
            placed = []
            for tid, (kind, fx, fy, tiers) in snap.items():
                if kind == "hero" or kind not in T.TOWERS:
                    continue
                x, z, _ = tr.frac_to_world(fx, fy)
                placed.append(D.Placed(tid, kind, tiers, x, z))
            if not placed:
                continue
            st = D.stations_for(placed, tr, sight=setup.sight)
            margin = D.round_margin(st, g["mode"], rnd, tr, lo=1 / CALIBRATION_RANGE, hi=CALIBRATION_RANGE)
            out.append((g["map"], g["mode"], g["strategy"], rnd, lost, margin))
    return out


def calibrate():
    """Print the model's margins against what happened in the logged games."""
    t0 = time.time()
    samples = calibration_samples(logged_games())
    # a margin at the bottom of the search range: even 64x stronger towers
    # leak - some bloon nobody on the map can pop (camo, lead, ...)
    structural = [s for s in samples if s[5] <= 1.0 / CALIBRATION_RANGE + 1e-9]
    graded = [s for s in samples if s[5] > 1.0 / CALIBRATION_RANGE + 1e-9]
    print(f"{len(samples)} logged rounds ({time.time() - t0:.0f} s); "
          f"{sum(1 for s in samples if s[4] > 0)} lost lives")
    print(f"model says some bloon cannot be popped at all: {len(structural)} rounds, "
          f"{sum(1 for s in structural if s[4] > 0)} of them really leaked")
    edges = [0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, math.inf]
    print("model margin   rounds  leaked  leak rate")
    for a, b in zip(edges, edges[1:]):
        sel = [s for s in graded if a <= s[5] < b]
        n = sum(1 for s in sel if s[4] > 0)
        print(f"  {a:>4} - {b:<4}  {len(sel):6d}  {n:6d}  {n / len(sel) if sel else 0:8.1%}")
    above = [s for s in graded if s[5] >= SAFETY_MARGIN]
    print(f"at or above SAFETY_MARGIN {SAFETY_MARGIN}: {len(above)} rounds, "
          f"{sum(1 for s in above if s[4] > 0)} leaked:")
    for s in sorted(above, key=lambda s: -s[4]):
        if s[4] > 0:
            print("   ", s[:5], round(s[5], 2))
    return samples


# ===========================================================================
# Command line
# ===========================================================================

def lower_priority():
    """Below-normal CPU priority, so a long run never slows the live bot
    (Windows: SetPriorityClass; elsewhere os.nice)."""
    try:
        if sys.platform == "win32":
            import ctypes
            below_normal = 0x4000          # BELOW_NORMAL_PRIORITY_CLASS
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), below_normal)
        else:
            import os
            os.nice(10)
    except Exception as e:  # priority is a courtesy: never fail the run over it
        log.warning("could not lower the priority: %s", e)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map", nargs="?")
    ap.add_argument("mode", nargs="?")
    ap.add_argument("--target", help="XP target tower (default: try the most valuable few)")
    ap.add_argument("--candidates", type=int, default=3, help="XP targets tried per map/mode")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--check", metavar="FILE", help="re-check a written plan (replayed as the executor buys)")
    ap.add_argument("--summary", action="store_true", help="rewrite the plan table in docs/optimizer.md")
    ap.add_argument("--no-account", action="store_true", help="plan for a fully unlocked account without boosts")
    ap.add_argument("--base", action="store_true", help="plan without Fast Track / Double Cash")
    ap.add_argument("--maps", help="only these maps (comma separated) of the default runs")
    ap.add_argument("--nice", action="store_true", help="run at below-normal priority (beside the live bot)")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    if a.nice:
        lower_priority()
    logging.basicConfig(level=logging.INFO if a.v else logging.WARNING, format="%(name)s: %(message)s")
    log.setLevel(logging.INFO)
    if a.calibrate:
        calibrate()
        return
    if a.check:
        check_plan(a.check)
        return
    if a.summary:
        print(summary_table() if not write_summary() else "docs/optimizer.md: plan table rewritten")
        return
    account = None if a.no_account else load_account()
    only = {m.strip() for m in a.maps.split(",")} if a.maps else None
    runs = [(a.map, a.mode)] if a.map and a.mode else [(m, mode) for m, mode in DEFAULT_RUNS
                                                      if (not a.map or m == a.map) and (not only or m in only)]
    for map_name, mode in runs:
        try:
            plan, xp, path = optimize(map_name, mode, target=a.target, account=account, candidates=a.candidates,
                                      base=a.base)
        except ValueError as e:
            print(f"{map_name} {mode}: skipped ({e})")
            continue
        worst = min(plan.margins.values()) if plan.margins else 0
        print(f"{map_name:18s} {mode:13s} target {plan.target or '-':10s} worst margin {worst:5.2f} "
              f"unsafe {plan.unsafe or '-'}  XP/h {xp['target_xp_per_hour']:>7,} "
              f"(valued {xp['valued_xp_per_hour']:,})  -> {path.relative_to(ROOT) if path else '-'}")


if __name__ == "__main__":
    main()
