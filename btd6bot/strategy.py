"""Map-independent strategies and the executor that plays them.

A strategy is a YAML build plan (strategies/*.yaml). Steps name *roles*, not
coordinates; the executor turns roles into spots using the learned map model:

  role: dps      maximise covered track (optionally within a progress segment)
  role: support  stand within reach of the towers listed in `near`
  role: exit     cover the last part of the track (spike factories, cleanup)
  role: far      away from the track (banana farms)

Plan steps run in order as cash allows. `fill` steps repeat afterwards to spend
surplus cash; `panic` runs whenever lives drop during a round.
"""
import logging
import math
import time
from pathlib import Path

import numpy as np
import yaml

from . import towers as T

log = logging.getLogger("strategy")
STRAT_DIR = Path(__file__).resolve().parents[1] / "strategies"

MODE_FAMILY = {
    "easy": "easy", "primary_only": "easy", "deflation": "easy",
    "medium": "medium", "military_only": "medium", "apopalypse": "medium", "reverse": "medium",
    "hard": "hard", "magic_only": "hard", "double_hp": "hard", "half_cash": "hard", "abr": "hard",
    "impoppable": "impoppable", "chimps": "impoppable",
}
MODE_TOWER_FILTER = {
    "primary_only": "primary", "military_only": "military", "magic_only": "magic",
}

# Rounds where a new kind of threat first shows up (standard rounds). The
# executor makes sure an answer is *already built* a couple of rounds earlier:
# DDTs in particular are too fast to answer after they appear.
THREATS = [
    (22, "camo"), (26, "lead"), (36, "ceramic"), (38, "moab"),
    (58, "bfb"), (62, "rush"), (78, "zomg"), (88, "ddt"), (98, "bad"),
]
# What counts as an answer: (tower, path, min tier) - any one is enough.
ANSWERS = {
    "camo": [("dart", 3, 2), ("sniper", 2, 2), ("ninja", 0, 0), ("heli", 0, 0), ("wizard", 3, 3),
             ("sub", 3, 0), ("village", 2, 2), ("druid", 0, 0), ("mortar", 0, 0), ("ace", 0, 0),
             ("engineer", 3, 3), ("spike", 0, 0), ("alchemist", 0, 0)],
    "lead": [("tack", 1, 3), ("bomb", 0, 0), ("boomerang", 3, 2), ("sniper", 1, 1), ("alchemist", 1, 1),
             ("wizard", 2, 2), ("heli", 0, 0), ("mortar", 0, 0), ("ace", 0, 0), ("glue", 1, 1),
             ("dart", 1, 4), ("ninja", 3, 2), ("spike", 0, 0), ("super", 1, 1)],
    "ceramic": [("tack", 1, 3), ("boomerang", 1, 3), ("bomb", 2, 2), ("sniper", 1, 2), ("dart", 3, 3),
                ("heli", 1, 2), ("ninja", 1, 3), ("super", 0, 0), ("spike", 0, 0), ("druid", 1, 3)],
    "moab": [("bomb", 2, 3), ("boomerang", 1, 4), ("tack", 1, 4), ("sniper", 1, 3), ("heli", 1, 3),
             ("dart", 3, 4), ("ninja", 3, 3), ("super", 0, 0), ("spike", 3, 3), ("druid", 2, 4),
             ("wizard", 2, 4), ("ace", 0, 0), ("sub", 3, 3), ("buccaneer", 2, 4)],
    "bfb": [("bomb", 2, 4), ("sniper", 1, 4), ("heli", 1, 4), ("boomerang", 1, 4), ("dart", 3, 4),
            ("super", 1, 3), ("ninja", 3, 4), ("spike", 3, 4), ("druid", 2, 4), ("tack", 1, 4)],
    "rush": [("tack", 1, 4), ("bomb", 3, 3), ("ninja", 1, 4), ("super", 0, 0), ("wizard", 2, 3),
             ("dartling", 0, 0), ("boomerang", 1, 3), ("ice", 3, 3)],
    "zomg": [("bomb", 2, 4), ("sniper", 1, 4), ("super", 1, 3), ("heli", 1, 4), ("spike", 3, 4),
             ("boomerang", 1, 5), ("druid", 2, 4), ("ninja", 3, 4)],
    "ddt": [("sniper", 2, 4), ("bomb", 2, 4), ("heli", 1, 4), ("super", 1, 3), ("spike", 3, 4),
            ("ninja", 3, 4), ("boomerang", 1, 4), ("dart", 3, 4)],
    "bad": [("super", 1, 4), ("bomb", 2, 5), ("sniper", 1, 5), ("ninja", 3, 5), ("spike", 3, 5)],
}
# camo-requiring threats also need camo on the answering tower (or village MIB)
NEEDS_CAMO = {"ddt"}


def load_all():
    out = {}
    for f in sorted(STRAT_DIR.glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        d.setdefault("id", f.stem)
        out[d["id"]] = d
    return out


def parse_cross(s):
    return [int(c) for c in str(s).split("-")]


def usable(strat, mode, account):
    """Can this account run this strategy in this mode? Returns (ok, why)."""
    if mode not in strat.get("modes", []):
        return False, "mode not supported"
    cat = MODE_TOWER_FILTER.get(mode)
    kinds = set()
    for st in strat.get("plan", []) + strat.get("fill", []):
        if st.get("kind") and st["kind"] != "hero":
            kinds.add(st["kind"])
    for k in kinds:
        if k not in T.TOWERS:
            return False, f"unknown tower {k}"
        if cat and T.TOWERS[k]["category"] != cat:
            return False, f"{k} not allowed in {mode}"
        if account is not None and k not in account.unlocked_towers:
            return False, f"{k} locked"
    hero = strat.get("hero")
    if mode == "chimps" and strat.get("uses_income"):
        return False, "income not allowed in CHIMPS"
    if hero and account is not None and hero not in account.unlocked_heroes:
        return False, f"hero {hero} locked"
    for kind, need in (strat.get("requires_upgrades") or {}).items():
        have = account.unlocked_upgrades.get(kind, [0, 0, 0]) if account else [5, 5, 5]
        if any(h < n for h, n in zip(have, parse_cross(need))):
            return False, f"{kind} {need} not unlocked"
    return True, "ok"


class Executor:
    def __init__(self, game, model, strat, mode, account=None):
        self.g = game
        self.m = model
        self.strat = strat
        self.mode = mode
        self.account = account
        self.plan = [dict(s) for s in strat.get("plan", [])]
        self.fill = [dict(s) for s in strat.get("fill", [])]
        self.panic_steps = [dict(s) for s in strat.get("panic", [])] or [
            {"do": "place", "kind": self._best_panic_kind(), "role": "exit"}]
        self.idx = 0
        self.counter = {}
        self.capped = set()          # (tid, path) that turned out locked
        self.failed_spots = set()
        self.panic_pending = 0
        self.unanswerable = set()
        self.last_try = 0.0
        self.no_sell = mode == "chimps"

    # -- helpers ------------------------------------------------------------
    def _best_panic_kind(self):
        for k in ("tack", "dart"):
            if self.account is None or k in self.account.unlocked_towers:
                return k
        return "dart"

    def _new_tid(self, kind):
        self.counter[kind] = self.counter.get(kind, 0) + 1
        return f"{kind}{self.counter[kind]}"

    def _range_cells(self, kind):
        if kind == "hero":
            rng = T.HEROES.get(self.g.hero, {}).get("range") or 40
        else:
            rng = T.TOWERS[kind].get("range") or 400
        return self.m.radius_cells(rng, self.g.s.width)

    def _occupied(self):
        out = []
        for p in self.g.towers.values():
            cx, cy = self.m.frac_to_cell(p.x, p.y)
            out.append((cx, cy, 3))  # footprints: ~3 cells radius each
        return out

    def pick_spot(self, kind, step):
        role = step.get("role", "dps")
        placement = "land"
        if kind != "hero" and T.TOWERS[kind]["placement"] == "water":
            placement = "water"
        rc = min(self._range_cells(kind), 60)
        seg = tuple(step.get("segment", (0.0, 1.0)))
        near, near_r = None, None
        if role == "exit":
            seg = (0.65, 1.0)
        if role == "support" and step.get("near"):
            ids = [i for i in step["near"] if i in self.g.towers]
            if ids:
                xs = [self.g.towers[i].x for i in ids]
                ys = [self.g.towers[i].y for i in ids]
                near = self.m.frac_to_cell(sum(xs) / len(xs), sum(ys) / len(ys))
                near_r = step.get("near_radius", 9)
        if role == "far":
            cover = -self.m.score_spots(rc, seg, self._occupied(), placement=placement)
            cover[cover >= 1] = -1  # still exclude blocked/occupied
        else:
            cover = self.m.score_spots(rc, seg, self._occupied(), near=near, near_radius=near_r,
                                       placement=placement)
        for cx, cy, score in self.m.best_spots(cover, n=12):
            if (kind, cx, cy) in self.failed_spots:
                continue
            return (cx, cy, score)
        return None

    def _next_path(self, p, target):
        """Cheapest next tier that moves p toward target crosspath."""
        if any(c > t for c, t in zip(p.tiers, target)):
            return None  # tower already went another way; target unreachable
        best = None
        for i in range(3):
            if p.tiers[i] >= target[i] or (p.tid, i + 1) in self.capped:
                continue
            tier = p.tiers[i] + 1
            cost = (T.upgrade_cost(p.kind, i + 1, tier, MODE_FAMILY[self.mode])
                    if p.kind != "hero" else 0)
            if best is None or cost < best[1]:
                best = (i + 1, cost)
        return best

    # -- step execution ---------------------------------------------------------
    def _resolve_targets(self, step):
        if "id" in step and step["id"] in self.g.towers:
            return [self.g.towers[step["id"]]]
        if "kind" in step:
            return [p for p in self.g.towers.values() if p.kind == step["kind"]]
        return []

    def try_step(self, step, cash, rnd):
        """Returns 'done', 'wait' or 'skip'."""
        if rnd is not None and step.get("round") and rnd < step["round"]:
            return "wait"
        do = step["do"]
        if do == "place":
            kind = step["kind"]
            if self.account and kind != "hero" and kind not in self.account.unlocked_towers:
                return "skip"
            if kind != "hero" and MODE_TOWER_FILTER.get(self.mode) and \
                    T.TOWERS[kind]["category"] != MODE_TOWER_FILTER[self.mode]:
                return "skip"
            if "max" in step and sum(p.kind == kind for p in self.g.towers.values()) >= step["max"]:
                return "skip"
            if kind == "hero" and any(p.kind == "hero" for p in self.g.towers.values()):
                return "done"
            if step.get("id") and step["id"] in self.g.towers:
                return "done"
            price = self.g.price(kind)
            if cash is not None and cash < price:
                return "wait"
            spot = self.pick_spot(kind, step)
            if spot is None:
                return "skip"
            cx, cy, _ = spot
            fx, fy = self.m.cell_to_frac(cx, cy)
            tid = step.get("id") or self._new_tid(kind)
            if self.g.place(tid, kind, fx, fy):
                if step.get("target"):
                    self.g.target(self.g.towers[tid], step["target"])
                return "done"
            self.failed_spots.add((kind, cx, cy))
            return "wait"
        if do == "upgrade":
            target = parse_cross(step["to"])
            todo = False
            for p in self._resolve_targets(step):
                nxt = self._next_path(p, target)
                if nxt is None:
                    continue
                todo = True
                path, cost = nxt
                if cash is not None and cash < cost:
                    return "wait"
                self.g.locked_seen = None
                if self.g.upgrade(p, path):
                    if self.account and p.kind != "hero":
                        self.account.note_bought(p.kind, path, p.tiers[path - 1])
                    return "wait" if self._next_path(p, target) else "done"
                # locked behind tower XP we do not have yet
                if getattr(self.g, "locked_seen", None):
                    self.capped.add((p.tid, path))
                    if self.account:
                        self.account.note_locked(*self.g.locked_seen)
                    return "wait"
                # enough cash but nothing happened: upgrade is locked
                if cash is not None and cash >= cost * 1.05:
                    self.capped.add((p.tid, path))
                    if self.account:
                        self.account.note_locked(p.kind, path, p.tiers[path - 1] + 1)
                return "wait"
            return "wait" if todo else ("done" if self._resolve_targets(step) else "skip")
        if do == "target":
            for p in self._resolve_targets(step):
                self.g.target(p, step["mode"])
            return "done"
        if do == "sell":
            if self.no_sell:
                return "skip"
            for p in self._resolve_targets(step):
                self.g.sell(p)
            return "done"
        return "skip"

    # -- threat calendar ---------------------------------------------------------
    def has_answer(self, threat):
        for p in self.g.towers.values():
            if p.kind == "hero":
                continue
            for kind, path, tier in ANSWERS.get(threat, []):
                if p.kind == kind and (path == 0 or p.tiers[path - 1] >= tier):
                    return True
        return False

    def due_threat(self, rnd, lookahead=3):
        """First upcoming threat with no answer built yet."""
        if rnd is None:
            return None
        start = self.strat.get("start_round", 1)
        for r, threat in THREATS:
            if r < start:
                continue
            # past r+1 it is no longer "early"; stop holding the plan hostage
            if r - lookahead <= rnd <= r + 1 and not self.has_answer(threat):
                return threat
        return None

    def answer_threat(self, threat, cash, rnd):
        """Run the strategy's `answers:` steps for this threat (or a generic one)."""
        steps = (self.strat.get("answers") or {}).get(threat)
        if steps is None:
            steps = self._generic_answer(threat)
        for st in steps:
            r = self.try_step(dict(st), cash, rnd)
            if r == "done":
                log.warning("threat %s: bought answer %s", threat, st)
                return True
            if r == "wait":
                return False  # saving up for it: do not spend elsewhere
        return False

    def _generic_answer(self, threat):
        """Upgrade an existing tower toward the cheapest listed answer."""
        steps = []
        for kind, path, tier in ANSWERS.get(threat, []):
            if any(p.kind == kind for p in self.g.towers.values()) and path:
                to = ["0", "0", "0"]
                to[path - 1] = str(tier)
                steps.append({"do": "upgrade", "kind": kind, "to": "-".join(to)})
        return steps[:3]

    def tick(self, cash, rnd, lives_dropped=False):
        """Do at most one action. Returns True if something was bought."""
        if lives_dropped:
            self.panic_pending = 2
        if self.panic_pending:
            for st in self.panic_steps:
                r = self.try_step(dict(st), cash, rnd)
                if r == "done":
                    self.panic_pending -= 1
                    return True
        threat = self.due_threat(rnd)
        if threat and threat not in self.unanswerable:
            if self.answer_threat(threat, cash, rnd):
                return True
            if not (self.strat.get("answers") or {}).get(threat) and not self._generic_answer(threat):
                self.unanswerable.add(threat)  # nothing we can do; don't block the plan
            else:
                return False  # hold cash for the answer
        while self.idx < len(self.plan):
            r = self.try_step(self.plan[self.idx], cash, rnd)
            if r in ("done", "skip"):
                self.idx += 1
                if r == "done":
                    return True
                continue
            return False  # waiting for cash / round
        for st in self.fill:
            if self.try_step(st, cash, rnd) == "done":
                return True
        return False

    def defended(self):
        return any(p.kind != "hero" for p in self.g.towers.values()) or \
            any(p.kind == "hero" for p in self.g.towers.values())
