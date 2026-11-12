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
    python tools/optimize_builds.py --chimps --maps "Alpine Run" --nice   # CHIMPS (see CHIMPS_RUNS)
    python tools/optimize_builds.py --calibrate          # model vs the bot's logged games
    python tools/optimize_builds.py --check FILE.yaml    # re-evaluate a written plan
    python tools/optimize_builds.py --answer FILE.yaml   # add the threat answers coverage misses
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
SPOTS_PER_KIND = 8       # best spots shown per tower kind (diverse: no two overlapping)
SPOTS_RESERVE = 40       # ... and how far down the ranking free_spot() may look when those are taken
# Towers of one kind a plan may place. Until 2026-11-03 a kind had only its
# SPOTS_PER_KIND spots, which also capped its copies; once free_spot looked
# further (SPOTS_RESERVE), the greedy bought what was cheapest per leak: Dark
# Dungeons Deflation (2026-11-11) opened with 34 bare $175 Skywardens, spent
# all $40,000 on 54 towers and leaked from round 34 (worst margin 0.06),
# while the plan written on 2026-10-22 (8 Skywardens) still held at 1.78.
MAX_PER_KIND = SPOTS_PER_KIND
SPOT_STRIDE = 2          # grid cells between candidate spots (the grid is 160 x 108)
MAX_PLACE_TIERS = 3      # a new tower may come with up to this many tiers at once
MAX_UPGRADE_STEP = 5     # an upgrade action buys up to this many tiers of one path at once
NEVER_KINDS = {"mortar", "dartling"}   # aimed by hand: they do nothing for the bot (dps_model)
# ... and towers the bot cannot pick up: it places by hotkey, and Desperado,
# Mermonkey and Skywarden have none bound by default (docs/backlog.md)
NEVER_KINDS |= {k for k, t in T.TOWERS.items() if not t.get("hotkey")}
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

# --- CHIMPS (--chimps) -----------------------------------------------------------
# CHIMPS is kept out of DEFAULT_RUNS: 95 rounds from $650 make a run far
# longer than the other modes'. --chimps runs these maps: the beginner maps
# where chimps_ninja_sun won Impoppable (logs/results.jsonl, 2026-11), so a
# map-specific CHIMPS plan gets proven where the hand-written one already holds.
CHIMPS_MAPS = ["Alpine Run", "Park Path", "Hedge", "End Of The Road", "Winter Park", "Carved",
               "Candy Falls", "Frozen Over"]
CHIMPS_RUNS = [(m, "chimps") for m in CHIMPS_MAPS]

# Known damage-model errors (backlog: village Primary buffs, Glaive Lord and
# Master Bomber counted map-wide; fixed in a parallel change to
# btd6bot/dps_model.py). Until that lands, CHIMPS plans - one leak loses the
# game - must not lean on them: model_doubt() rejects these tiers there.
CHIMPS_MODEL_DOUBTS = {
    "boomerang": (0, 5),   # Glaive Lord (5-x-x): its orbiting glaives counted map-wide
    "ninja": (2, 5),       # Master Bomber (x-x-5): its stun bombs counted map-wide
}
VILLAGE_PRIMARY_PATH = (0, 3)   # Primary Training+ (3-x-x): its buffs reach non-Primary towers too
MODEL_DOUBT_MODES = {"chimps"}


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
    from btd6bot.boosts import double_cash_applies, fast_track_wanted
    rules = D.mode_rules(mode)
    mr = S.MODE_RULES.get(mode, {})
    econ = Economy(mode=mode, family=S.PRICE_FAMILY.get(mode, "medium"),
                   start_round=int(mr.get("start_round") or rules["start_round"] or 1),
                   end_round=int(mr.get("end_round") or rules["end_round"] or 60),
                   start_cash=float(rules["start_cash"]), cash_mult=float(rules["cash"]))
    boosts = boosts or {}
    # the runner switches the toggle off in boosts.FAST_TRACK_OFF_MODES, so
    # those games are planned from the mode's own first round
    if boosts.get("fast_track") and fast_track_wanted(mode) and mode not in ("chimps", "deflation"):
        econ.start_round, econ.start_cash = fast_track_start(econ, double_cash_applies(boosts, mode))
    elif mode == "deflation" and boosts.get("double_cash"):
        # logged: Deflation games on the account start with $40,400, double the $20,000
        econ.start_cash *= 2.0
    if double_cash_applies(boosts, mode):
        econ.cash_mult *= 2.0
    return econ


def hero_tiers_at(hero, map_name, mode, account, placed_round, rnd):
    """The hero Tower's tiers in round `rnd`: (level, optimistic level) -
    the level it is rated at (hero_level_at) and the level the bot's
    ability planner may already assume (abilities.HERO_XP_OPTIMISM), which
    decides whether it presses anything (Evaluator.pressed)."""
    from btd6bot.abilities import HERO_XP_OPTIMISM, estimate_hero_level
    return (hero_level_at(hero, map_name, mode, account, placed_round, rnd),
            estimate_hero_level(hero, placed_round, rnd, HERO_XP_OPTIMISM))


def hero_level_at(hero, map_name, mode, account, placed_round, rnd):
    """The level the bot's estimate gives `hero` in round `rnd`, placed in
    `placed_round` (abilities.estimate_hero_level, with the map's and the
    account's Monkey Knowledge XP bonuses; none of the knowledge in modes
    that switch it off: CHIMPS). The same estimate the live forecast uses
    (forecast.RoundForecast.hero_level)."""
    from btd6bot import strategy as S
    from btd6bot.abilities import estimate_hero_level, hero_xp_multiplier
    knowledge = () if (S.MODE_RULES.get(mode) or {}).get("no_mk") else tuple(
        getattr(account, "mk_unlocked", ()) or ())
    return estimate_hero_level(hero, placed_round, rnd, hero_xp_multiplier(map_name, knowledge))


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

def _main_checkout():
    """The main checkout this tree belongs to (itself outside a git worktree)."""
    import subprocess
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        return Path(common).parent
    except (OSError, subprocess.CalledProcessError):
        return ROOT


def load_account():
    """The current account (data/current_account.txt), or None.

    In a git worktree the live account file is read from the main checkout.
    None when that account's file is missing there too: AccountState.load would hand back an empty
    account - no towers unlocked but the Dart Monkey, no upgrades - and every
    plan would be a row of bare darts."""
    try:
        from btd6bot.account import AccountState
        from btd6bot.identity import account_path
        uid = (ROOT / "data" / "current_account.txt").read_text(encoding="utf-8").strip()
        path = account_path(uid)
        if not Path(path).exists():
            # a git worktree: the live account file is in the main checkout
            path = _main_checkout() / "data" / "accounts" / f"{uid}.json"
        if not Path(path).exists():
            log.warning("account %s: %s not found - planning for a fully unlocked account", uid, path)
            return None
        return AccountState.load(path)
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


# --learned: plan on the map's learned file (data/maps/<map>.npz), so the
# spots the live game refused are left out as the bot itself leaves them out.
# Off by default: a worktree's copy of that file may be stale.
USE_LEARNED = False
# --panes: also plan on ground under cycling panes (Covered Garden), open
# one round in four (see MapSetup.pane_spots). Off by default.
USE_PANES = False


class MapSetup:
    reserve = True   # free_spot may look past the best SPOTS_PER_KIND spots (see there)
    """Geometry of one map for one mode: the evaluator's Track, the bot's
    MapModel grids (placement, line of sight) and candidate spots per kind."""

    def __init__(self, map_name, mode):
        from btd6bot import layout as L
        from btd6bot import mapgeom as G
        from btd6bot.maplearn import MapModel
        self.map_name = map_name
        self.track = D.Track(map_name, reverse=(mode == "reverse"))
        playfield = L.LAYOUTS["16:10"]["playfield"]
        self.model = MapModel.load(map_name, playfield) if USE_LEARNED else MapModel(map_name, playfield)
        G.apply(self.model, self.track.geom)
        self._spots = {}

    # -- line of sight ---------------------------------------------------------
    def sight(self, x, z, pts):
        """Visible mask of world points pts (N x 3) from a tower at (x, z):
        no sight-blocking cell of the MapModel on the straight line between
        (dps_model.sight_test, shared with the live forecast).

        The blockers' heights and the ground's go in as well, as the live
        forecast passes them (match.py): a tower on raised ground sees over
        blockers no higher than it. Without them every tower on Sunken
        Columns' column tops counted as blind behind the columns it stands
        on: the best dart spot of the map "saw" 18 units of a 640-unit
        route, the entrance row where four live games had opened saw none,
        and tools/pin_spots.py pinned the Impoppable build's first towers,
        two subs, down in a pool, where the walls do hide the route - round
        6 took the one life twice (cases 20261112_012149 and
        20261112_093331)."""
        if not hasattr(self, "_sight"):
            heights = (getattr(self.model, "sight_height", None), getattr(self.model, "ground_height", None))
            self._sight = D.sight_test(self.model.sight, self.track, heights=heights)
        if self._sight is None:
            return np.ones(len(pts), bool)
        return self._sight(x, z, pts)

    def sight_for(self, kind):
        from btd6bot import placement as P
        return self.sight if kind != "hero" and P.needs_sight(kind) else None

    # -- spots -----------------------------------------------------------------
    def cell_spot(self, cell):
        fx, fy = self.model.cell_to_frac(*cell)
        x, z, h = self.track.frac_to_world(fx, fy)
        return Spot(cell=tuple(cell), x=x, z=z, h=h, fx=fx, fy=fy, score=0.0)

    def pane_spots(self, kind):
        """Cells open to `kind` only while their pane is open (Covered
        Garden's glass, mapgeom.pane_open): the union over one cycle of the
        rounds. The executor places and upgrades a tower there only in its
        pane's rounds (Executor._pane_shut, _reachable), so a plan using them
        must be re-checked with that timing; the optimizer itself buys as
        soon as the cash allows."""
        from btd6bot import mapgeom as G
        from btd6bot import placement as P
        grids = G.grids_for(self.model)
        if not grids or not grids.get("panes"):
            return np.zeros(self.model.heat.shape, bool)
        base = P.valid_spots(self.model, kind)
        n = max(len(masks) for _, masks in grids["panes"])
        out = np.zeros(base.shape, bool)
        for rnd in range(1, n + 1):
            out |= P.valid_spots(self.model, kind, now_round=rnd)
        return out & ~base

    def spots(self, kind):
        """The best SPOTS_PER_KIND spots for a kind, best first, no two of
        them overlapping (so later towers of the kind have room)."""
        return self.ranked_spots(kind)[:SPOTS_PER_KIND]

    def ranked_spots(self, kind):
        """Every spot of a kind that reaches the track, best first, no two
        of them overlapping. spots() shows the best few; free_spot() walks
        on down this list when those are taken by other kinds."""
        if kind in self._spots:
            return self._spots[kind]
        from btd6bot import placement as P
        ok = P.valid_spots(self.model, kind)
        if USE_PANES and ok is not None:
            ok = ok | self.pane_spots(kind)
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
                if len(out) >= SPOTS_RESERVE:
                    break
        self._spots[kind] = out
        return out

    def hero_spot(self, hero, towers):
        """The spot the hero is rated at: of the cells the hero may stand on
        (placement.valid_spots for "hero"), the one whose circle of the
        hero's range covers the most track and whose footprint overlaps no
        placed tower; any free cell for a map-wide hero (Psi). None when
        there is no room. The executor places a hero with no "at" by its own
        rules; this is the model's stand-in for that spot when a plan does
        not say (replay_plan)."""
        from btd6bot import placement as P
        key = ("hero", hero)
        if key not in self._spots:
            ok = P.valid_spots(self.model, "hero", hero)
            prof = D.profile(D.hero_kind(hero), (1,))
            radius = None if (prof is None or prof.is_global) else max(prof.range, 1.0)
            scored = []
            if ok is not None and ok.any():
                rows, cols = np.nonzero(ok)
                keep = (rows % SPOT_STRIDE == 0) & (cols % SPOT_STRIDE == 0)
                for r, c in zip(rows[keep], cols[keep]):
                    sp = self.cell_spot((int(c), int(r)))
                    if radius is not None:
                        sp.score = sum(z.length for z in self.track.zones(sp.x, sp.z, radius) if z)
                        if sp.score <= 0:
                            continue
                    scored.append(sp)
            scored.sort(key=lambda sp: sp.score, reverse=True)
            self._spots[key] = scored[:SPOTS_RESERVE]
        upc = P.units_per_cell(self.model)
        r = P.footprint_radius("hero", hero) / upc
        for sp in self._spots[key]:
            if all((sp.cell[0] - t.spot.cell[0]) ** 2 + (sp.cell[1] - t.spot.cell[1]) ** 2
                   >= (r + P.footprint_radius(t.kind if t.kind != "hero" else "dart") / upc) ** 2
                   for t in towers):
                return sp
        return None

    def free_spot(self, kind, towers):
        """The best spot of a kind whose footprint does not overlap a placed tower.

        All the kinds' best spots crowd the same stretch of track, so once a
        dozen towers stand there the first SPOTS_PER_KIND spots of every
        other kind can be taken. The search goes on down the ranked list
        then: before 2026-11-03 it stopped, and on Cargo Magic Only no Druid,
        Alchemist, Wizard or Ninja could be placed after round 13 - the only
        Lead answer left was a $7,560 Super Monkey, so rounds 28-45 were
        rated 0.06 and the mode looked unwinnable (backlog 13).

        With ``reserve`` False only the SPOTS_PER_KIND best spots are used,
        as before: the cheap towers the greedy then buys at the farther spots
        can cost more than they bring (optimize tries both)."""
        from btd6bot import placement as P
        upc = P.units_per_cell(self.model)
        r = P.footprint_radius(kind) / upc
        for sp in (self.ranked_spots(kind) if self.reserve else self.spots(kind)):
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


def threat_names():
    """The threat names strategy.coverage checks (strategy.THREATS)."""
    from btd6bot import strategy as S
    return {t for _r, t in S.THREATS}


def legal(tiers):
    """At most two paths used, at most one of them above tier 2."""
    return sum(t > 0 for t in tiers) <= 2 and sum(t > 2 for t in tiers) <= 1


def no_income_mode(mode):
    """Does the mode forbid income (CHIMPS: no Banana Farm, no income upgrades)?"""
    from btd6bot import strategy as S
    return bool(S.MODE_RULES.get(mode, {}).get("no_income_towers"))


def income_tiers(kind, tiers):
    """Is this crosspath an income upgrade (strategy.INCOME_UPGRADES:
    Merchantman buccaneers, Bloon Trap engineers)?"""
    from btd6bot import strategy as S
    return any(k == kind and tiers[path - 1] >= tier for k, path, tier in S.INCOME_UPGRADES)


def model_doubt(kind, tiers, towers=()):
    """Why the damage model cannot be trusted with this crosspath ('' when
    it can). towers: (kind, tiers) of the towers in the tower's range - a
    village's Primary Training buffs only count when a Primary tower stands
    there. See CHIMPS_MODEL_DOUBTS."""
    doubt = CHIMPS_MODEL_DOUBTS.get(kind)
    if doubt and tiers[doubt[0]] >= doubt[1]:
        return f"{kind} {'-'.join(map(str, tiers))}: tier counted map-wide by the damage model"
    path, tier = VILLAGE_PRIMARY_PATH
    if kind == "village" and tiers[path] >= tier and \
            not any(T.TOWERS.get(k, {}).get("category") == "primary" for k, _ in towers):
        return f"village {'-'.join(map(str, tiers))}: Primary buffs with no Primary tower in range"
    return ""


def upgrade_cost(kind, tiers_from, tiers_to, family, discount=0.0):
    """Price of the tiers from tiers_from to tiers_to; `discount` (a Monkey
    Village's, economy.discount_at) comes off tiers 1-3 (economy.discounted)."""
    from btd6bot.economy import discounted
    cost = 0.0
    for path in range(3):
        for tier in range(tiers_from[path] + 1, tiers_to[path] + 1):
            cost += discounted(T.upgrade_cost(kind, path + 1, tier, family), tier, discount)
    return cost


def spot_discount(spot, towers, own=None):
    """The best Monkey Village discount at `spot` from the villages among
    `towers` (economy.discount_at); a village does not discount itself
    (`own`: the tower being priced). 0 without a spot."""
    from btd6bot.economy import discount_at
    if spot is None:
        return 0.0
    villages = [t for t in towers if t.kind == "village" and t.spot is not None and t is not own
                and t.spot is not spot]
    return discount_at(spot.x, spot.z, villages)


def place_cost(kind, tiers, family, spot, towers):
    """Price of placing `kind` at `spot` and buying `tiers` at once, with
    the discount of the villages already standing there."""
    from btd6bot.economy import discounted
    off = spot_discount(spot, towers)
    return discounted(T.tower_cost(kind, family), 0, off) + upgrade_cost(kind, (0, 0, 0), tiers, family, off)


def board_cash(mode, towers, hero=None, hero_level=None):
    """Cash the board pays per round besides the round's own cash
    (economy.board_income under the mode's rules): Benjamin's Cyber Cash at
    `hero_level`, farms, Merchantmen. 0 in CHIMPS and Deflation."""
    from btd6bot import strategy as S
    from btd6bot.economy import board_income
    return board_income(towers, S.MODE_RULES.get(mode, {}), hero, hero_level)


class Evaluator:
    """Runs dps_model on builds, with the stations of unchanged towers cached.

    hero: the plan's hero id. Its Tower has kind "hero" and tiers (level,),
    the level it has in the round being rated (hero_level); it is rated as
    the model's tower "hero:<id>" (dps_model.HERO_RATING), so its own
    attacks count and its buffs (Obyn's Druid pierce, camo and range,
    Etienne's map-wide camo) reach the towers it covers."""

    def __init__(self, setup, mode, hero=None):
        self.setup = setup
        self.mode = mode
        self.hero = hero
        self._stations = {}

    def model_kind(self, t):
        """(kind, tiers) of a Tower as the damage model knows it, or None for
        a hero that is not rated (none named, or heroes switched off)."""
        if t.kind == "hero":
            if not self.hero or not D.HERO_RATING or not t.tiers:
                return None
            return D.hero_kind(self.hero), tuple(t.tiers[:1])
        return t.kind, t.tiers

    def placed(self, t):
        """The dps_model.Placed of a Tower, or None (model_kind)."""
        mk = self.model_kind(t)
        return None if mk is None else D.Placed(t.tid, mk[0], mk[1], t.spot.x, t.spot.z)

    def pressed(self, towers):
        """Does the bot press abilities with this board's hero? Yes: with
        Adora the planner holds only the keys Blood Sacrifice may sit on
        and presses the rest (abilities.presses_blind, AbilityPlanner.
        unsafe_keys). Kept as a method so the station cache keys on it."""
        from btd6bot.abilities import presses_blind
        hero = next((t for t in towers if t.kind == "hero"), None)
        if hero is None or not self.hero:
            return True
        return presses_blind(self.hero, None, None)

    def station_of(self, tower, towers):
        """The station of one tower standing among `towers` (None when it
        does no damage or reaches no track). It depends only on the tower
        and the supporters on the map (villages, a buffing hero), and on
        whether the bot presses abilities with this hero (pressed), so it is
        cached by (kind, crosspath, cell, supporters, pressed)."""
        me = self.placed(tower)
        if me is None:
            return None
        pressed = self.pressed(towers)
        board = [b for b in (self.placed(t) for t in towers) if b is not None]
        supporters = tuple(sorted((b.kind, b.tiers, t.spot.cell) for b, t in
                                  ((self.placed(t), t) for t in towers) if b is not None
                                  and (D.profile(b.kind, b.tiers) is not None and D.profile(b.kind, b.tiers).buffs)))
        key = (me.kind, me.tiers, tower.spot.cell, supporters or None, pressed)
        st = self._stations.get(key)
        if st is None:
            st = D.station_for(me, board, self.setup.track, sight=self.setup.sight, pressed=pressed) or False
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
    board_cash: float = 0.0          # cash the board paid besides the rounds' own (Optimizer.board_income)


class Optimizer:
    """One greedy optimization of one map, mode and XP target (see run())."""

    def __init__(self, map_name, mode, target=None, account=None, hero="quincy", boosts=None, reserve=True):
        self.map_name, self.mode, self.target = map_name, mode, target
        self.reserve = reserve
        self.account = account
        self.boosts = dict(boosts or {})
        self.econ = economy(mode, self.boosts)
        self.setup = MapSetup(map_name, mode)
        self.setup.reserve = reserve
        self.hero = hero
        self.ev = Evaluator(self.setup, mode, hero)
        self.weights = xp_weights(account)
        self.kinds = self._kinds()
        self.hero_at = None       # the round the hero was bought (run), for its income

    def board_income(self, towers, rnd):
        """Cash the board pays at the end of round `rnd` besides the
        round's own (board_cash), with the hero at its estimated level
        (hero_level_at) once it is bought."""
        level = (hero_level_at(self.hero, self.map_name, self.mode, self.account, self.hero_at, rnd)
                 if self.hero_at is not None else None)
        return board_cash(self.mode, towers, self.hero if self.hero_at is not None else None, level)

    def round_cash(self, towers, rnd):
        """All the cash round `rnd` brings: the mode's (Economy.income) and
        the board's (board_income)."""
        return self.econ.income(rnd) + self.board_income(towers, rnd)

    def _kinds(self):
        """Tower kinds this mode and account allow and the model can use."""
        from btd6bot import strategy as S
        only = S.MODE_TOWER_FILTER.get(self.mode)
        no_income = no_income_mode(self.mode)
        out = []
        for kind, info in T.TOWERS.items():
            if kind in NEVER_KINDS:
                continue
            # income towers: only as the XP target, and never where the
            # mode forbids income (CHIMPS locks the Banana Farm), whatever the target
            if kind in INCOME_KINDS and (kind != self.target or no_income):
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
    def allowed(self, kind, tiers, spot, towers):
        """May the plan buy this crosspath at this spot? Not an income
        upgrade where the mode forbids income, and (MODEL_DOUBT_MODES) not a
        tier the damage model is known to overrate (model_doubt)."""
        if no_income_mode(self.mode) and income_tiers(kind, tiers):
            return False
        if self.mode in MODEL_DOUBT_MODES:
            near = []
            if kind == "village":   # only a village's doubt depends on its neighbours
                prof = D.profile(kind, tiers)
                reach = prof.range if prof is not None else 0.0
                near = [(t.kind, t.tiers) for t in towers if t.kind != "hero" and t.spot is not spot
                        and (t.spot.x - spot.x) ** 2 + (t.spot.z - spot.z) ** 2 <= reach * reach]
            if model_doubt(kind, tiers, near):
                return False
        return True

    def room_for(self, kind, towers):
        """May one more tower of ``kind`` be placed (MAX_PER_KIND)?"""
        return sum(t.kind == kind for t in towers) < MAX_PER_KIND

    def actions(self, towers, cash):
        fam = self.econ.family
        out = []
        for kind in self.kinds:
            cap = unlocked_tiers(self.account, kind)
            if not self.room_for(kind, towers):
                continue
            spot = self.setup.free_spot(kind, towers)
            if spot is None:
                continue
            if place_cost(kind, (0, 0, 0), fam, spot, towers) > cash:
                continue
            for tiers in _bundles(cap, MAX_PLACE_TIERS):
                cost = place_cost(kind, tiers, fam, spot, towers)
                if cost <= cash and D.profile(kind, tiers) is not None and self.allowed(kind, tiers, spot, towers):
                    out.append(Action(kind=kind, tiers=tiers, cost=cost, spot=spot))
        for t in towers:
            if t.kind == "hero":
                continue
            off = spot_discount(t.spot, towers, own=t)
            cap = unlocked_tiers(self.account, t.kind)
            for path in range(3):
                for step in range(1, MAX_UPGRADE_STEP + 1):
                    new = list(t.tiers)
                    new[path] += step
                    new = tuple(new)
                    if new[path] > cap[path] or not legal(new) or D.profile(t.kind, new) is None:
                        break
                    cost = upgrade_cost(t.kind, t.tiers, new, fam, off)
                    if cost > cash:
                        break
                    if not self.allowed(t.kind, new, t.spot, towers):
                        break    # higher tiers of this path stay out too
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
        hero_round = None
        self.hero_at = None
        last = econ.end_round
        # without income (Deflation) every round is paid from the start cash:
        # plan for all of them at once
        no_income = econ.cash_mult == 0
        for rnd in range(econ.start_round, last + 1):
            if hero_round is not None:
                # the hero's level in this round: the window is rated with it
                # (the lowest of the window - it only grows)
                towers = self._level_hero(towers, hero_round, rnd)
            # 1. safety for the next LOOKAHEAD rounds
            window = list(range(rnd, last + 1 if no_income else min(last, rnd + LOOKAHEAD) + 1))
            towers, cash, n = self._make_safe(plan, towers, cash, n, rnd, window, must=True)
            # the hero once the first tower stands and it is affordable,
            # rated at its estimated level by round (dps_model.HERO_RATING)
            if not hero_placed and towers and cash >= hero_cost:
                cash -= hero_cost
                hero_placed = True
                self.hero_at = rnd
                spot = self.setup.hero_spot(self.hero, towers) if D.HERO_RATING else None
                if spot is not None:
                    hero_round = rnd
                    towers = self._level_hero(towers + [Tower("hero", "hero", spot, (1,), hero_cost)], rnd, rnd)
                    why = "hero: rated at its estimated level"
                else:
                    why = "hero: not counted by the model (extra safety)"
                plan.steps.append(Step(rnd, Action("hero", (0, 0, 0), hero_cost, spot=spot), "hero", why, cash))
            # 1b. the threats of the window that the build has no answer for
            # (strategy.coverage: the runner will not play a build without one)
            towers, cash, n = self._answer_threats(plan, towers, cash, n, rnd, window)
            # 2. further rounds: buy ahead while affordable
            ahead = window if no_income else list(range(rnd, min(last, rnd + SURPLUS_WINDOW) + 1))
            towers, cash, n = self._make_safe(plan, towers, cash, n, rnd, ahead, must=False)
            # 3. surplus to the XP target, if everything ahead is safe
            if self.target and not any(v > 0 for v in self.ev.leak(towers, ahead).values()):
                towers, cash, n = self._spend_surplus(plan, towers, cash, n, rnd, ahead)
            plan.share_by_round[rnd] = _shares(towers)
            board = self.board_income(towers, rnd)
            plan.board_cash += board
            cash += econ.income(rnd) + board
        plan.towers = towers
        rounds = list(range(econ.start_round, last + 1))
        plan.margins = self._timeline_margins(plan, rounds)
        plan.unsafe = [r for r, m in plan.margins.items() if m < SAFETY_MARGIN]
        for t in towers:
            plan.spent_by_kind[t.kind] = plan.spent_by_kind.get(t.kind, 0.0) + t.spent
        plan.seconds = time.time() - t0
        return plan

    def _level_hero(self, towers, placed_round, rnd):
        """towers with the hero's Tower at its level in round `rnd`
        (hero_level_at); unchanged without a hero."""
        out = []
        for t in towers:
            if t.kind == "hero":
                t = Tower(t.tid, t.kind, t.spot,
                          hero_tiers_at(self.hero, self.map_name, self.mode, self.account, placed_round, rnd), t.spent)
            out.append(t)
        return out

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
            budget = cash + sum(self.round_cash(towers, r) for r in range(rnd, first))
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

    def as_strategy(self, plan):
        """The plan so far as a strategy dict, as strategy.coverage reads one."""
        steps = []
        for st in plan.steps:
            a = st.action
            if a.kind == "hero":
                continue
            if a.tid is None:
                steps.append({"do": "place", "id": st.tid, "kind": a.kind})
            steps.append({"do": "upgrade", "id": st.tid, "to": "-".join(map(str, a.tiers))})
        return {"id": f"opt_{map_id(self.map_name)}_{self.mode}", "map": self.map_name,
                "modes": [self.mode], "plan": steps}

    def missing_threats(self, plan, last_round):
        """Threats (strategy.THREATS) due by ``last_round`` in this mode that
        the plan's build does not answer by strategy.coverage's rules.
        plan: a Plan, or a strategy dict (a written plan file)."""
        from btd6bot import strategy as S
        strat = plan if isinstance(plan, dict) else self.as_strategy(plan)
        ok, missing = S.coverage(strat, self.mode, self.account)
        if ok:
            return []
        shift = S.rules(self.mode).get("threat_shift", {})
        due = {t for r, t in S.THREATS if shift.get(t, r) <= last_round}
        return [t for t in missing if t in due and t in S.ANSWERS]

    def answer_actions(self, towers, threat, cash):
        """Affordable actions that make the build answer ``threat`` by one of
        strategy.ANSWERS[threat] (kind, path, tier): upgrading a standing
        tower of that kind to the tier, or placing a new one with it."""
        from btd6bot import strategy as S
        fam = self.econ.family
        out = []
        for kind, path, tier in S.ANSWERS[threat]:
            if kind not in self.kinds:
                continue
            cap = unlocked_tiers(self.account, kind)
            if path and cap[path - 1] < tier:
                continue
            for t in [t for t in towers if t.kind == kind]:
                new = list(t.tiers)
                if path:
                    new[path - 1] = max(new[path - 1], tier)
                new = tuple(new)
                if new == t.tiers:
                    continue
                cost = upgrade_cost(kind, t.tiers, new, fam, spot_discount(t.spot, towers, own=t))
                if (legal(new) and D.profile(kind, new) is not None and cost <= cash
                        and self.allowed(kind, new, t.spot, towers)):
                    out.append(Action(kind=kind, tiers=new, cost=cost, tid=t.tid))
            spot = self.setup.free_spot(kind, towers) if self.room_for(kind, towers) else None
            if spot is None:
                continue
            tiers = tuple(tier if path and i == path - 1 else 0 for i in range(3))
            cost = place_cost(kind, tiers, fam, spot, towers)
            if cost <= cash and D.profile(kind, tiers) is not None and self.allowed(kind, tiers, spot, towers):
                out.append(Action(kind=kind, tiers=tiers, cost=cost, spot=spot))
        return out

    def _answer_threats(self, plan, towers, cash, n, rnd, window):
        """Buy the cheapest answer to every threat of the coming ``window``
        that the build cannot answer (missing_threats).

        The damage model may rate a round safe without one - Dark Dungeons
        and Quad Deflation (2026-10) held every BFB round at margin 2.0 with
        lower-tier towers - but strategy.coverage, which the runner checks
        before it plays any build, would then drop the build, and the open
        medals it was made for stayed without a playable build. Buying the
        answer makes the plan pass that check as it is; the margins are
        measured afterwards with the answer standing (run)."""
        for _ in range(len(threat_names())):
            missing = self.missing_threats(plan, max(window))
            if not missing:
                break
            threat = missing[0]
            options = self.answer_actions(towers, threat, cash)
            if not options:
                break          # not affordable yet: tried again next round
            best = min(options, key=lambda a: (a.cost, -self.preference(a)))
            n, tid = self._tid(best, n)
            towers = self.apply(towers, best, tid)
            cash -= best.cost
            plan.steps.append(Step(rnd, best, tid, f"answers {threat} (strategy.coverage)", cash))
        return towers, cash, n

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
        hero_round = None
        for s in plan.steps:
            by_round.setdefault(s.rnd, []).append(s)
        for r in rounds:
            for s in by_round.get(r, []):
                if s.action.kind != "hero":
                    towers = self.apply(towers, s.action, s.tid)
                elif s.action.spot is not None:
                    hero_round = r
                    towers = towers + [Tower("hero", "hero", s.action.spot, (1,), s.action.cost)]
            if hero_round is not None:
                towers = self._level_hero(towers, hero_round, r)
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
        f"# Cash the board paid besides the rounds' own (hero income, farms; economy.board_income): "
        f"${plan.board_cash:,.0f}.",
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
        f"map: {json.dumps(plan.map_name)}",   # quoted: "#Ouch" would start a YAML comment
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
        f"  maps: [{json.dumps(plan.map_name)}]",
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
            at = f", at: [{a.spot.fx:.3f}, {a.spot.fy:.3f}]" if a.spot is not None else ""
            lines.append(f"  - {{do: place, id: hero, kind: hero, role: dps{at}}}   # R{s.rnd}: ${a.cost:,.0f}; {s.why}")
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


def hero_cash(hero, map_name, mode, account=None, placed_round=None, end_round=None):
    """The cash `hero` pays over a game of `mode` (economy.hero_income at
    its estimated level each round, hero_level_at, under the mode's rules),
    placed in `placed_round` (default: the mode's first round) and counted
    to `end_round` (default: the mode's last). 0 for heroes without income
    and in CHIMPS / Deflation. A yardstick for comparing heroes; the plans
    themselves count it round by round (Optimizer.board_income)."""
    econ = economy(mode)
    first = placed_round or econ.start_round
    last = end_round or econ.end_round
    return sum(board_cash(mode, (), hero, hero_level_at(hero, map_name, mode, account, first, r))
               for r in range(first, last + 1))


def optimize(map_name, mode, target=None, account=None, write=True, candidates=3, base=False, heroes=None):
    """Best plan for a map/mode: one optimization per XP target candidate
    (or the given target), keeping the safe plan with the most value-weighted
    XP per hour (else the one with the fewest unsafe rounds).
    base: plan without the account's boosts (Fast Track, Double Cash).
    heroes: the heroes to try (default: the account's selected one). Each
    plan counts its hero's income (Benjamin's Cyber Cash) round by round,
    so in Impoppable and the other income modes Benjamin is weighed against
    a damage hero by the same key: safety first, then valued XP per hour,
    which his cash raises through the surplus spent on the XP target."""
    weights = xp_weights(account)
    boosts = {} if base or account is None else dict(getattr(account, "boosts", {}) or {})
    if mode == "chimps":
        # CHIMPS pays no Double Cash and has no Fast Track (economy() ignores
        # both): the written plan must not claim to need them, or the
        # planner would hold it back from an account without them (needs_boosts)
        boosts = {}
    hero = (getattr(account, "selected_hero", None) or "quincy") if account else "quincy"
    if hero not in T.HEROES:
        hero = "quincy"
    heroes = [h for h in (heroes or [hero]) if h in T.HEROES] or [hero]
    targets = [target] if target else target_candidates(map_name, mode, weights, account, candidates) or [None]
    best = None
    # each target with both spot rules (MapSetup.free_spot): every spot of a
    # kind, or only its best few - Cargo Magic Only needed the first, Dark
    # Dungeons Deflation (2026-11-11) held at 1.56 with the second and at
    # 0.55 with the first
    for hero, tgt, reserve in [(h, t, r) for h in heroes for t in targets for r in (True, False)]:
        opt = Optimizer(map_name, mode, target=tgt, account=account, hero=hero, boosts=boosts,
                        reserve=reserve)
        plan = opt.run()
        xp = xp_report(plan, weights)
        worst = min(plan.margins.values()) if plan.margins else 0.0
        key = (len(plan.unsafe) == 0, -len(plan.unsafe), worst if plan.unsafe else 0.0,
               xp["valued_xp_per_hour"])
        log.info("%s %s hero %s target %s, %s spots: unsafe %s, worst margin %.2f, valued XP/h %s, "
                 "board cash $%.0f (%.0f s)", map_name, mode, hero, tgt,
                 "all" if reserve else f"best {SPOTS_PER_KIND}", plan.unsafe,
                 worst, xp["valued_xp_per_hour"], plan.board_cash, plan.seconds)
        if best is None or key > best[0]:
            best = (key, plan, opt.setup, xp)
    _, plan, setup, xp = best
    text = plan_yaml(plan, setup, weights, xp)
    if not any(t.kind != "hero" for t in plan.towers):
        # nothing on this map/mode pops a round (Bloody Puddles Primary Only):
        # a plan with the hero alone is no build - write nothing
        log.warning("%s %s: no tower could be planned - nothing written", map_name, mode)
        write = False
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

def replay_plan(plan, rounds=None, account=None):
    """Play a plan's steps the way the executor does - in order, each as soon
    as the cash allows - on the economy recorded in its `optimizer.scenario`,
    and return {round: margin} with the towers standing when each round
    starts. An independent check of a written file (it does not use the
    optimizer's own bookkeeping). plan: the parsed YAML dict.

    On a map that freezes towers (dps_model.TOWER_FREEZE) each round is
    rated with only the towers awake in it (_awake_margin).

    The hero is rated at its estimated level in each round (hero_level_at;
    account: whose Monkey Knowledge adds hero XP - None counts none, the
    slower estimate), at the plan's "at" or, without one, at the spot
    MapSetup.hero_spot gives it."""
    (mode,) = plan["modes"]
    sc = (plan.get("optimizer") or {}).get("scenario") or {}
    econ = economy(mode)
    econ.start_round = int(sc.get("start_round", econ.start_round))
    econ.start_cash = float(sc.get("start_cash", econ.start_cash))
    econ.cash_mult = float(sc.get("income_multiplier", econ.cash_mult))
    setup = MapSetup(plan["map"], mode)
    hero = plan.get("hero") or "quincy"
    ev = Evaluator(setup, mode, hero)
    towers, cash, i = {}, econ.start_cash, 0
    placed = {}             # tower id -> the round it was bought before
    hero_bought = None      # the round the hero was bought, for its income
    steps = plan.get("plan") or []
    margins = {}
    for rnd in range(econ.start_round, econ.end_round + 1):
        if "hero" in towers:
            # the hero's level in this round (hero_level_at, as the live forecast estimates it)
            h = towers["hero"]
            towers["hero"] = Tower(h.tid, h.kind, h.spot,
                                   hero_tiers_at(hero, plan["map"], mode, account, placed["hero"], rnd), h.spent)
        while i < len(steps):
            step = steps[i]
            if step["do"] == "place" and step["kind"] == "hero":
                cost = T.hero_cost(plan.get("hero") or "quincy", econ.family)
            elif step["do"] == "place":
                spot = setup.cell_spot(setup.model.frac_to_cell(*step["at"]))
                cost = place_cost(step["kind"], (0, 0, 0), econ.family, spot, list(towers.values()))
            elif step["do"] == "upgrade":
                t = towers[step["id"]]
                cost = upgrade_cost(t.kind, t.tiers, tuple(int(c) for c in str(step["to"]).split("-")), econ.family,
                                    spot_discount(t.spot, list(towers.values()), own=t))
            else:
                cost = 0.0
            if cost > cash:
                break
            cash -= cost
            if step["do"] == "place" and step["kind"] == "hero":
                hero_bought = rnd
            if step["do"] == "place" and step["kind"] != "hero":
                towers[step["id"]] = Tower(step["id"], step["kind"], spot, (0, 0, 0), cost)
                placed[step["id"]] = rnd
            elif step["do"] == "place" and D.HERO_RATING:
                # the hero, at its planned spot or where the model would stand it
                spot = (setup.cell_spot(setup.model.frac_to_cell(*step["at"])) if step.get("at")
                        else setup.hero_spot(hero, list(towers.values())))
                if spot is not None:
                    placed["hero"] = rnd
                    towers["hero"] = Tower("hero", "hero", spot,
                                           hero_tiers_at(hero, plan["map"], mode, account, rnd, rnd), cost)
            elif step["do"] == "upgrade":
                t = towers[step["id"]]
                towers[step["id"]] = Tower(t.tid, t.kind, t.spot, tuple(int(c) for c in str(step["to"]).split("-")),
                                           t.spent + cost)
            i += 1
        if rounds is None or rnd in rounds:
            margins[rnd] = round(_awake_margin(ev, setup, plan["map"], mode, rnd, list(towers.values()), placed), 2)
        level = (hero_level_at(hero, plan["map"], mode, account, hero_bought, rnd)
                 if hero_bought is not None else None)
        cash += econ.income(rnd) + board_cash(mode, list(towers.values()),
                                              hero if hero_bought is not None else None, level)
    return margins


def _awake_margin(ev, setup, map_name, mode, rnd, towers, placed):
    """The damage model's margin for round `rnd` with the towers that are
    not frozen in it; on a map without a tower freeze simply the margin of
    all of them.

    Glacial Trail Primary Only (2026-11-11 22:55, loss case
    20261111_230017_GlacialTrail_primary_only): the written plan bought both
    tack shooters with the Fast Track cash of round 10, so both sat in ice in
    rounds 19-20 and 29-30 (dps_model.frozen_in) and those three rounds took
    all 200 lives. The file said "worst margin 2.20, unsafe rounds: none",
    because every round was rated with the whole defence at the map's
    average uptime (Track.uptime, 0.8); the live forecast, which knows each
    tower's placement round, rated round 19 at 0.06 from round 11 on.

    placed: {tower id: the round whose start board first held it}. The game
    may count a tower bought between two rounds from either of them, so the
    round is rated for both and the worse margin counts (as in
    tests/test_glacialtrail_builds_offline.py). The awake towers are rated at
    full strength - their frozen rounds are left out instead of averaged."""
    if D.tower_uptime(map_name) >= 1.0 or not towers:
        return D.round_margin(ev.stations(towers), mode, rnd, setup.track)
    saved = setup.track.uptime
    setup.track.uptime = 1.0
    try:
        return min(D.round_margin(ev.stations([t for t in towers
                                               if not D.frozen_in(map_name, placed[t.tid] - shift, rnd)]),
                                  mode, rnd, setup.track)
                   for shift in (0, 1))
    finally:
        setup.track.uptime = saved


def parse_cross(text):
    """A crosspath written "a-b-c" as a tuple of ints."""
    return tuple(int(c) for c in str(text).split("-"))


def _replayed_towers(plan, setup):
    """(towers, cash left) once every step of a written plan is bought, in
    order and as cash allows (as replay_plan buys them), by the end of its
    last round; towers as Tower records."""
    (mode,) = plan["modes"]
    sc = (plan.get("optimizer") or {}).get("scenario") or {}
    econ = economy(mode)
    econ.start_round = int(sc.get("start_round", econ.start_round))
    econ.start_cash = float(sc.get("start_cash", econ.start_cash))
    econ.cash_mult = float(sc.get("income_multiplier", econ.cash_mult))
    towers, cash = {}, econ.start_cash
    hero = plan.get("hero") or "quincy"
    hero_bought = None
    steps = list(plan.get("plan") or [])
    for rnd in range(econ.start_round, econ.end_round + 1):
        while steps:
            step = steps[0]
            spot = None
            if step["do"] == "place" and step["kind"] == "hero":
                cost = T.hero_cost(hero, econ.family)
            elif step["do"] == "place":
                spot = setup.cell_spot(setup.model.frac_to_cell(*step["at"]))
                cost = place_cost(step["kind"], (0, 0, 0), econ.family, spot, list(towers.values()))
            elif step["do"] == "upgrade":
                t = towers[step["id"]]
                cost = upgrade_cost(t.kind, t.tiers, parse_cross(step["to"]), econ.family,
                                    spot_discount(t.spot, list(towers.values()), own=t))
            else:
                cost = 0.0
            if cost > cash:
                break
            cash -= cost
            if step["do"] == "place" and step["kind"] == "hero":
                hero_bought = rnd
            if step["do"] == "place" and step["kind"] != "hero":
                towers[step["id"]] = Tower(step["id"], step["kind"], spot, (0, 0, 0), cost)
            elif step["do"] == "upgrade":
                t = towers[step["id"]]
                towers[step["id"]] = Tower(t.tid, t.kind, t.spot, parse_cross(step["to"]), t.spent + cost)
            steps.pop(0)
        if rnd < econ.end_round:
            level = (hero_level_at(hero, plan["map"], mode, None, hero_bought, rnd)
                     if hero_bought is not None else None)
            cash += econ.income(rnd) + board_cash(mode, list(towers.values()),
                                                  hero if hero_bought is not None else None, level)
    return list(towers.values()), cash


def _step_line(step, note=""):
    """One plan step as a line of the YAML flow list."""
    body = ", ".join(f"{k}: {json.dumps(v) if k == 'at' else v}" for k, v in step.items())
    return f"  - {{{body}}}" + (f"   # {note}" if note else "")


SURPLUS_NOTE = "XP: surplus into the target tower"   # Step.why of _spend_surplus purchases


def _surplus_cut(lines):
    """``lines`` without the last plan step bought as XP surplus (its
    SURPLUS_NOTE comment) - and, when that step placed a tower, without the
    later steps of that tower. None when the plan has no surplus step left."""
    idx = [i for i, ln in enumerate(lines) if ln.startswith("  - {do:") and SURPLUS_NOTE in ln]
    if not idx:
        return None
    i = idx[-1]
    m = re.search(r"do: place, id: (\w+)", lines[i])
    gone = m and m[1]
    return [ln for k, ln in enumerate(lines)
            if k != i and not (gone and k > i and re.search(rf"\bid: {gone}\b", ln))]


def _add_answers(opt, plan, lines):
    """Buy the cheapest answer to each unanswered threat with the cash the
    written plan leaves. Returns (plan lines with the new steps, missing
    after); missing is not empty when the cash ran out."""
    import yaml
    plan = yaml.safe_load("\n".join(lines))
    towers, cash = _replayed_towers(plan, opt.setup)
    end = opt.econ.end_round
    extra, n = [], 0
    for _ in range(len(threat_names())):
        missing = opt.missing_threats(plan, end)
        if not missing:
            break
        options = opt.answer_actions(towers, missing[0], cash)
        if not options:
            break
        best = min(options, key=lambda a: a.cost)
        if best.tid is None:
            n += 1
            tid = f"ans{n}"
            new = [{"do": "place", "id": tid, "kind": best.kind,
                    "at": [round(best.spot.fx, 3), round(best.spot.fy, 3)]}]
            if any(best.tiers):
                new.append({"do": "upgrade", "id": tid, "to": "-".join(map(str, best.tiers))})
        else:
            tid = best.tid
            new = [{"do": "upgrade", "id": tid, "to": "-".join(map(str, best.tiers))}]
        towers = opt.apply(towers, best, tid)
        cash -= best.cost
        plan["plan"] = list(plan.get("plan") or []) + new
        for k, st in enumerate(new):
            extra.append(_step_line(st, f"answers {missing[0]} (strategy.coverage), ${best.cost:,.0f} "
                                        "from the cash the plan leaves" if k == 0 else ""))
    cut = next((i for i, ln in enumerate(lines) if ln.startswith("fill:")), len(lines))
    return lines[:cut] + extra + lines[cut:], opt.missing_threats(plan, end)


def _shore_up(opt, plan, lines):
    """In a mode without income (all the cash is there at the start), spend
    what the written plan leaves on the optimizer's own safety purchases
    (Optimizer._make_safe) until every round holds at SAFETY_MARGIN or the
    cash runs out. Returns the plan lines with those steps added before
    `fill:`. New towers get ids the plan does not use yet."""
    towers, cash = _replayed_towers(plan, opt.setup)
    tmp = Plan(opt.map_name, opt.mode, opt.target, opt.hero)
    used = {str(st.get("id")) for st in plan.get("plan") or []}
    n = len(used) + 100
    while any(f"{k[:3]}{i}" in used for k in T.TOWERS for i in range(n + 1, n + 50)):
        n += 100
    rounds = list(range(opt.econ.start_round, opt.econ.end_round + 1))
    opt._make_safe(tmp, towers, cash, n, opt.econ.start_round, rounds, must=False)
    extra = []
    for st in tmp.steps:
        a = st.action
        note = f"{st.why}, added by --answer from the cash the plan leaves, ${a.cost:,.0f}"
        if a.tid is None:
            extra.append(_step_line({"do": "place", "id": st.tid, "kind": a.kind,
                                     "at": [round(a.spot.fx, 3), round(a.spot.fy, 3)]}, note))
            if any(a.tiers):
                extra.append(_step_line({"do": "upgrade", "id": st.tid, "to": "-".join(map(str, a.tiers))}))
        else:
            extra.append(_step_line({"do": "upgrade", "id": st.tid, "to": "-".join(map(str, a.tiers))}, note))
    cut = next((i for i, ln in enumerate(lines) if ln.startswith("fill:")), len(lines))
    return lines[:cut] + extra + lines[cut:]


def answer_plan(path, account=None):
    """Add to a written plan the cheapest answer (strategy.ANSWERS) to every
    threat strategy.coverage finds unanswered, and re-check the margins
    (replay_plan).

    For plans written before the optimizer bought answers itself
    (Optimizer._answer_threats): their towers held the damage model's
    rounds, but the runner would not play them. The answers are bought
    after the rest of the plan with the cash it leaves; when that is too
    little, the plan's XP-surplus steps (SURPLUS_NOTE) are given back from
    the last one until it is enough. The file is rewritten in place - the new
    steps at the end of `plan:`, the replayed worst margin and unsafe rounds
    in `optimizer:` - only when coverage then passes and the worst margin is
    no lower than before (or at least SAFETY_MARGIN). In a mode without
    income the cash still left then buys safety for the rounds under
    SAFETY_MARGIN (_shore_up).
    Returns (missing before, missing after, worst margin before, after)."""
    import yaml
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    plan = yaml.safe_load("\n".join(lines))
    (mode,) = plan["modes"]
    sc = (plan.get("optimizer") or {}).get("scenario") or {}
    boosts = {b.replace(" ", "_"): True for b in sc.get("boosts") or ()}
    opt = Optimizer(plan["map"], mode, account=account, hero=plan.get("hero") or "quincy", boosts=boosts)
    before = opt.missing_threats(plan, opt.econ.end_round)
    margins = replay_plan(plan)
    worst_before = min(margins.values()) if margins else 0.0
    if not before:
        return before, before, worst_before, worst_before
    base = lines
    while True:
        new_lines, after = _add_answers(opt, plan, base)
        if not after:
            break
        base = _surplus_cut(base)
        if base is None:
            return before, after, worst_before, worst_before
    plan = yaml.safe_load("\n".join(new_lines))
    margins = replay_plan(plan)
    if opt.econ.cash_mult == 0 and margins and min(margins.values()) < SAFETY_MARGIN:
        new_lines = _shore_up(opt, plan, new_lines)
        plan = yaml.safe_load("\n".join(new_lines))
        margins = replay_plan(plan)
    worst = min(margins.values()) if margins else 0.0
    if worst < min(worst_before, SAFETY_MARGIN):
        return before, after, worst_before, worst
    unsafe = [r for r, m in margins.items() if m < SAFETY_MARGIN]
    new_lines = [f"  worst_margin: {worst:.2f}" if ln.startswith("  worst_margin:")
                 else f"  unsafe_rounds: [{', '.join(map(str, unsafe))}]" if ln.startswith("  unsafe_rounds:")
                 else ln for ln in new_lines]
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return before, after, worst_before, worst


def check_plan(path):
    """Print a written plan's margins as replayed by replay_plan()."""
    import yaml
    plan = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    margins = replay_plan(plan)
    worst = min(margins.values()) if margins else None
    print(f"{path}: worst margin {worst} (written: {plan.get('optimizer', {}).get('worst_margin')}); "
          f"below {SAFETY_MARGIN:g}: {[r for r, m in margins.items() if m < SAFETY_MARGIN] or 'none'}")
    return margins


def restate_plan(path):
    """Rewrite a written plan's `worst_margin` and `unsafe_rounds` with what
    replay_plan() finds today, and leave its steps alone.

    For a file whose numbers come from an older damage model: the runner
    decides from these two lines whether the build may be played
    (strategy._optimized_prior), so a plan the model no longer trusts stops
    being played until the optimizer writes a better one. A dated comment
    line above `id:` says the numbers were restated. Returns (the worst
    margin written before, the worst margin now)."""
    import yaml
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    plan = yaml.safe_load("\n".join(lines))
    margins = replay_plan(plan)
    worst = min(margins.values()) if margins else 0.0
    unsafe = [r for r, m in margins.items() if m < SAFETY_MARGIN]
    before = (plan.get("optimizer") or {}).get("worst_margin")
    note = (f"# Restated {time.strftime('%Y-%m-%d')} by --restate: replayed on today's damage model the worst "
            f"margin is {worst:.2f} (was {before}).")
    out = []
    for ln in lines:
        if ln.startswith("# Restated "):
            continue                    # an earlier restatement's note
        if ln.startswith("id:"):
            out.append(note)
        if ln.startswith("  worst_margin:"):
            ln = f"  worst_margin: {worst:.2f}"
        elif ln.startswith("  unsafe_rounds:"):
            ln = f"  unsafe_rounds: [{', '.join(map(str, unsafe))}]"
        out.append(ln)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return before, worst


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
    """Idle CPU priority, so a long run never slows the live bot (Windows:
    SetPriorityClass; elsewhere os.nice). The ctypes call used before had no
    argument types and left the process at normal priority (measured
    2026-10-22, while runs beside the bot pushed the CPU to 100%)."""
    try:
        if sys.platform == "win32":
            import win32api
            import win32process
            win32process.SetPriorityClass(win32api.GetCurrentProcess(), win32process.IDLE_PRIORITY_CLASS)
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
    ap.add_argument("--restate", metavar="FILE", nargs="+",
                    help="rewrite written plans' worst margin and unsafe rounds as replayed today")
    ap.add_argument("--answer", metavar="FILE", nargs="+",
                    help="add the answers strategy.coverage misses to written plans, re-check them")
    ap.add_argument("--summary", action="store_true", help="rewrite the plan table in docs/optimizer.md")
    ap.add_argument("--no-account", action="store_true", help="plan for a fully unlocked account without boosts")
    ap.add_argument("--base", action="store_true", help="plan without Fast Track / Double Cash")
    ap.add_argument("--heroes", help="heroes to try, comma separated (default: the account's selected hero), "
                                     "e.g. quincy,benjamin for an income mode")
    ap.add_argument("--maps", help="only these maps (comma separated) of the default runs")
    ap.add_argument("--chimps", action="store_true", help="run CHIMPS on CHIMPS_MAPS instead of the default runs")
    ap.add_argument("--nice", action="store_true", help="run at below-normal priority (beside the live bot)")
    ap.add_argument("--panes", action="store_true",
                    help="also use ground under cycling panes (Covered Garden); re-check the pane timing")
    ap.add_argument("--learned", action="store_true",
                    help="leave out the spots the live game refused (data/maps/<map>.npz)")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    global USE_LEARNED, USE_PANES
    USE_LEARNED = USE_LEARNED or a.learned
    USE_PANES = USE_PANES or a.panes
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
    if a.restate:
        for f in a.restate:
            before, worst = restate_plan(f)
            print(f"{f}: worst margin {before} -> {worst:.2f} (optimizer block rewritten)")
        return
    if a.answer:
        account = None if a.no_account else load_account()
        for f in a.answer:
            before, after, worst0, worst = answer_plan(f, account)
            done = "rewritten" if before and not after and worst >= min(worst0, SAFETY_MARGIN) else "unchanged"
            print(f"{f}: unanswered {before or 'none'} -> {after or 'none'}; "
                  f"worst margin {worst0:.2f} -> {worst:.2f} ({done})")
        return
    if a.summary:
        print(summary_table() if not write_summary() else "docs/optimizer.md: plan table rewritten")
        return
    account = None if a.no_account else load_account()
    only = {m.strip() for m in a.maps.split(",")} if a.maps else None
    listed = CHIMPS_RUNS if a.chimps else DEFAULT_RUNS
    runs = [(a.map, a.mode)] if a.map and a.mode else [(m, mode) for m, mode in listed
                                                      if (not a.map or m == a.map) and (not only or m in only)]
    for map_name, mode in runs:
        try:
            plan, xp, path = optimize(map_name, mode, target=a.target, account=account, candidates=a.candidates,
                                      base=a.base, heroes=a.heroes.split(",") if a.heroes else None)
        except ValueError as e:
            print(f"{map_name} {mode}: skipped ({e})")
            continue
        worst = min(plan.margins.values()) if plan.margins else 0
        print(f"{map_name:18s} {mode:13s} target {plan.target or '-':10s} worst margin {worst:5.2f} "
              f"unsafe {plan.unsafe or '-'}  XP/h {xp['target_xp_per_hour']:>7,} "
              f"(valued {xp['valued_xp_per_hour']:,})  -> {path.relative_to(ROOT) if path else '-'}")


if __name__ == "__main__":
    main()
