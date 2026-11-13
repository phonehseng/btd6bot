"""The rule every one-life (CHIMPS) opening must meet before a build may use it.

Why
---
On 2026-11-13 six Intermediate CHIMPS builds whose openings had been
"hardened" by an opening search (annealing on optimize_builds.replay_plan
ratings) lost in their first rounds:

  * Bazaar (case 20261113_032115, round 9): a glue was put before the
    guide's druid; 3 darts + a 0-0-0 glue met round 9's 30 greens with $305
    (the druid costs $430). The guide's 3 darts + boomerang + druid had held
    rounds 6-14 live the night before (journal 20261112_225338).
  * Lost Crevasse (20261113_032621, round 7): druid + dart rated 1.54; two
    blues got through. The guide opens with Sauda.
  * Rake (20261113_033512, round 20): the searched tack, glue, dart and
    spike took the place of the guide's tack 0-0-2 and Sauda; the bloons got
    83-96% along the route in rounds 16-20 while the model rated 1.0-2.25.
  * Water Park (20261113_041444, round 7): boomerang 0-0-1 + dart rated 1.28.
  * Moon Landing (20261113_041946, round 8): a 0-0-0 glue instead of the
    guide's second dart.
  * Sulfur Springs (20261113_042420, round 8): wizard + sniper with $345 held
    for a $430 boat; the lone boat had held to round 95 three times on
    2026-11-07.
Earlier the same night Firing Range (a lone boat rated 2.25 at round 6,
backlog 107) and Quiet Street (two darts on one side of three routes) lost
round 6 the same way.

Calibration (tools/opening_rule.py --calibrate reads the main checkout's
logs/journal; 2026-11-13 06:00): over 105
CHIMPS journals, the live margin of rounds 6-10 had an AUC of 0.66 for
held-versus-leaked (rounds 6-20: 0.74). 8 of the 15 leaked rounds 6-10 were
rated 1.0 or more (1.18, 1.18, 1.28, 1.35, 1.41, 1.54, 2.48, 2.48), while 70
of 289 held rounds were rated under 1.0 (Alpine Run held 0.34-0.51 for three
rounds, Sulfur Springs 0.36-0.72). Round 6 itself is never rated before
Play. No margin threshold separates the two: a rating alone cannot certify
an opening.

The rule
--------
The purchases a build makes through OPENING_END (round 10; pin_spots.buy_rounds
on the CHIMPS cash curve) must be one of:

  1. a live-proven opening (PROVEN): the towers, spots (within SPOT_TOL) and
     tiers of a journal's game that held rounds 6 through at least
     PROVEN_THROUGH, each bought no later than in that game (ROUND_SLACK);
  2. the guide's own opening (GUIDE): the first purchases in the guide's
     order (docs/chimps_map_guides.md), nothing else bought before them -
     unless the guide's opening has itself lost live (GUIDE_LOST);
  3. an opening the corrected model rates as holding: every round 6-10 on
     every lane (lane_margins on alternating maps) at EARLY_HOLD or more
     after the early-credit factor (corrected_margin).

The corrected model
-------------------
corrected_margin scales the model's margin of rounds 6-10 by EARLY_CREDIT
(0.6). On the journals that moves the leaked rounds rated 1.0 or more from
8 of 15 to 2 of 15 - the two left are Luminous Cove's boat at 2.48 (backlog
107: aimed pierce against a thin line), which rule 3 does not accept for an
opening with a boat in it (AIMED_PIERCE, aimed_pierce_opening) - at the price
of calling 167 of the 289 held rounds weak. That is why rules 1 and 2 come
first: the model is the last resort, and a strict one. On Water Park no
affordable opening reaches it (best 0.64): there only a live game can prove
one.

Not changed: the live forecast (btd6bot/forecast) still rates with the raw
model; its early-round crisis and hold decisions are as before.

Run: python tools/opening_rule.py [build ids]       (the source of each opening)
     python tools/opening_rule.py --calibrate        (the table above, from logs/journal)
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
import pin_spots  # noqa: E402

OPENING_END = 10        # the last round whose purchases make the opening
EARLY_CREDIT = 0.6      # rounds 6-OPENING_END: share of the model's margin the game honours
EARLY_HOLD = 1.0        # a corrected margin at least this holds
SPOT_TOL = 0.03         # a spot within this (screen fractions, both axes) is the same spot
ROUND_SLACK = 1         # buy_rounds counts whole rounds' income; the journal's round is mid-round
PROVEN_THROUGH = 20     # a proven opening held at least rounds 6 through this
# towers whose shots are aimed darts with pierce: alone they meet a thin line of
# bloons one at a time (backlog 107: Luminous Cove 2.48 and Firing Range 2.25 lost)
AIMED_PIERCE = ("buccaneer",)


@dataclass(frozen=True)
class ProvenTower:
    """One tower of a live-proven opening: its kind, spot, the round it was
    placed in and {tiers: round reached} for its upgrades."""
    kind: str
    at: tuple | None            # None: any spot (the hero; a starter dart the bot placed by itself)
    placed: int
    upgrades: tuple = ()        # ((tiers "a-b-c", round), ...)


@dataclass(frozen=True)
class Proven:
    """A live game whose opening held rounds 6 through held_through."""
    map: str
    journal: str
    held_through: int
    towers: tuple
    note: str = ""


# Openings that held live (logs/journal, read 2026-11-13). The round of each
# purchase is the journal's; a "starter" dart the bot added beside a lone
# tower is listed like any other tower (a build must buy it in its plan).
PROVEN = (
    Proven("Bazaar", "20261112_225338_Bazaar_chimps", 14, (
        ProvenTower("dart", (0.719, 0.504), 6),
        ProvenTower("dart", (0.740, 0.555), 6),
        ProvenTower("dart", (0.115, 0.487), 6),
        ProvenTower("boomerang", (0.104, 0.428), 7),
        ProvenTower("druid", (0.751, 0.470), 10),
    ), "the guide's 3 darts, boomerang and druid; lost round 15 (a later hole), not the opening"),
    Proven("Sulfur Springs", "20261107_205259_SulfurSprings_chimps", 95, (
        ProvenTower("buccaneer", (0.195, 0.411), 6, (("1-0-0", 6), ("2-0-0", 8))),
    ), "the lone boat; also 20261107_230013 and 20261108_014403 (0.195, 0.419-0.428), each to round 95"),
    Proven("Lost Crevasse", "20261107_181331_LostCrevasse_chimps", 95, (
        ProvenTower("buccaneer", (0.665, 0.709), 6),
        ProvenTower("dart", (0.190, 0.428), 6),
        ProvenTower("desperado", (0.206, 0.641), 7),
        ProvenTower("skywarden", (0.227, 0.334), 8),
        ProvenTower("buccaneer", (0.665, 0.709), 6, (("1-0-0", 10),)),
    ), "also 20261107_213840 (95), 20261108_011559 (93); the same opening without the desperado lost rounds 8 and 9"),
    Proven("Moon Landing", "20261109_000204_MoonLanding_chimps", 59, (
        ProvenTower("desperado", (0.441, 0.462), 6),
        ProvenTower("desperado", (0.633, 0.726), 6),
        ProvenTower("dart", (0.067, 0.436), 7),
        ProvenTower("dart", (0.152, 0.538), 8),
        ProvenTower("boomerang", (0.575, 0.726), 10),
    ), "also 20261108_052702 (40); 20261107_212106 lost round 7 before the round-7 dart was bought"),
    Proven("Rake", "20261107_212609_Rake_chimps", 40, (
        ProvenTower("desperado", (0.665, 0.802), 6),
        ProvenTower("desperado", (0.639, 0.402), 6),
        ProvenTower("desperado", (0.446, 0.581), 7),
        ProvenTower("boomerang", (0.542, 0.411), 9),
    )),
    Proven("Spring Spring", "20261107_222956_SpringSpring_chimps", 99, (
        ProvenTower("buccaneer", (0.751, 0.598), 6),
        ProvenTower("dart", (0.270, 0.164), 6),
        ProvenTower("tack", (0.302, 0.828), 7),
        ProvenTower("dart", (0.655, 0.334), 8),
    ), "the old springspring_chimps build, nine games to round 95-99"),
    Proven("Spring Spring", "20261112_154428_SpringSpring_chimps", 37, (
        ProvenTower("sub", (0.751, 0.572), 6),
        ProvenTower("mermonkey", (0.804, 0.572), 6),
    ), "the guide's sub and mermonkey"),
    Proven("Ancient Portal", "20261113_024226_AncientPortal_chimps", 100, (
        ProvenTower("ninja", (0.793, 0.164), 6),
        ProvenTower("dart", None, 6),       # the bot's starter, at its own choice (0.633, 0.453)
        ProvenTower("dart", (0.793, 0.726), 7),
        ProvenTower("mermonkey", (0.644, 0.624), 8),
        ProvenTower("dart", (0.558, 0.402), 10),
    ), "won"),
    Proven("Haunted", "20261113_004032_Haunted_chimps", 96, (
        ProvenTower("dart", (0.558, 0.692), 6),
        ProvenTower("sub", (0.430, 0.521), 6, (("1-0-0", 10),)),
        ProvenTower("buccaneer", (0.419, 0.658), 7, (("1-0-0", 9),)),
    ), "also 20261113_014238 (91)"),
    Proven("Haunted", "20261112_194504_Haunted_chimps", 93, (
        ProvenTower("dart", (0.558, 0.692), 6),
        ProvenTower("sub", (0.430, 0.521), 6, (("0-0-1", 8),)),
    ), "the guide's dart and sub; also 20261112_222316 (93)"),
    Proven("Firing Range", "20261113_011301_FiringRange_chimps", 95, (
        ProvenTower("sub", (0.687, 0.436), 6, (("1-0-0", 6), ("1-0-1", 7))),
    ), "also 20261112_211507 and 20261113_050944, each to round 95"),
    Proven("Firing Range", "20261112_182644_FiringRange_chimps", 95, (
        ProvenTower("sub", (0.687, 0.436), 6, (("1-0-0", 6), ("1-0-1", 8))),
        ProvenTower("dart", (0.740, 0.607), 6),
    )),
    Proven("Polyphemus", "20261113_021606_Polyphemus_chimps", 82, (
        ProvenTower("druid", (0.366, 0.317), 6),
        ProvenTower("dart", (0.323, 0.334), 6),
        ProvenTower("druid", (0.345, 0.709), 8),
        ProvenTower("sniper", (0.484, 0.274), 10),
    )),
)

# The guide's own first purchases, in its order (docs/chimps_map_guides.md):
# a tower kind places one, "kind a-b-c" upgrades the latest of that kind.
GUIDE = {
    "Lost Crevasse": ("hero", "tack", "sniper", "druid"),
    "Sulfur Springs": ("wizard", "hero", "wizard 2-0-0", "buccaneer"),
    "Spring Spring": ("sub", "mermonkey", "hero", "buccaneer"),
    "Moon Landing": ("dart", "sniper", "dart", "dart 0-1-0", "dart 0-1-0", "dart", "hero"),
    "Rake": ("desperado", "desperado", "tack", "tack 0-0-2", "hero", "spike"),
    "Luminous Cove": ("dart", "buccaneer", "buccaneer 1-0-0", "hero"),
    "Ancient Portal": ("ninja", "ninja 2-0-1", "hero"),
    "Haunted": ("dart", "sub", "sub 0-0-1", "hero"),
    "Firing Range": ("sub", "dart", "sub 1-0-1", "hero"),
    "Water Park": ("dart", "boomerang", "boomerang 0-1-2"),
    "Covered Garden": ("desperado", "desperado", "druid", "hero"),
    "Bloonarius Prime": ("dart", "dart", "sub", "dart", "sniper"),
    "Bazaar": ("dart", "dart", "dart", "boomerang", "druid", "hero"),
    "Polyphemus": ("druid", "sniper", "hero"),
    "Quiet Street": ("dart", "sniper", "sniper", "sniper", "sniper"),
    "Balance": ("hero", "tack"),
}
# maps whose guide opening has lost live in its own rounds: the guide is no
# warrant there (journals)
GUIDE_LOST = {
    "Water Park": "20261112_202347 (round 6) and 20261113_041113 (round 7): dart + boomerang",
    "Luminous Cove": "20261112_160247 and 20261112_164008 (round 8): dart + boat 1-0-0, rated 2.48",
}


@dataclass
class Purchase:
    """One plan step bought by OPENING_END: what it buys and when."""
    step: dict
    kind: str               # the tower kind ("hero" for the hero)
    tiers: tuple            # the tower's tiers after this step
    rnd: int                # pin_spots.buy_rounds: the round it is bought in
    at: tuple | None        # the tower's spot
    tid: str | None = None


def opening(d, end=OPENING_END):
    """[Purchase] of plan ``d`` (a parsed build) bought by round ``end``, in
    plan order (pin_spots.buy_rounds on the mode's cash curve)."""
    steps = d.get("plan") or []
    bought = pin_spots.buy_rounds(steps, d["modes"][0], d.get("hero"))
    towers, out = {}, []
    for i, st in enumerate(steps):
        if i not in bought or bought[i] > end:
            if i in bought:
                break
            continue
        if st.get("do") == "place":
            towers[st.get("id")] = (st["kind"], (0, 0, 0), tuple(st["at"]) if st.get("at") else None)
            out.append(Purchase(st, st["kind"], (0, 0, 0), bought[i], towers[st.get("id")][2], st.get("id")))
        elif st.get("do") == "upgrade" and st.get("id") in towers:
            kind, _, at = towers[st["id"]]
            tiers = O.parse_cross(st["to"])
            towers[st["id"]] = (kind, tiers, at)
            out.append(Purchase(st, kind, tiers, bought[i], at, st["id"]))
    return out


def d_start(d):
    """The build's mode's first round (CHIMPS: 6)."""
    return O.economy(d["modes"][0]).start_round


def _bot_starter(d, buys):
    """Will the bot add its own starter dart beside a lone round-start tower
    (match._lone_opener: one life, one non-hero tower before the first Play,
    no `starter: none`)? The won Ancient Portal game (20261113_024226) opened
    with the plan's ninja and that dart."""
    if d.get("starter") == "none":
        return False
    first = [p for p in buys if p.rnd == d_start(d) and p.step.get("do") == "place" and p.kind != "hero"]
    return len(first) == 1


def _near(a, b):
    return a is not None and b is not None and all(abs(x - y) <= SPOT_TOL for x, y in zip(a, b))


def matches_proven(d, proven):
    """Does build ``d`` buy every tower and tier of ``proven`` at its spot,
    no later than the proven game did (ROUND_SLACK)? Returns (ok, why)."""
    buys = opening(d, OPENING_END + ROUND_SLACK)
    used = set()
    starter = _bot_starter(d, buys)
    for pt in proven.towers:
        # the tower: a placement of that kind at that spot (the hero: any spot)
        cands = [p for p in buys if p.step.get("do") == "place" and p.kind == pt.kind
                 and (pt.at is None or _near(p.at, pt.at))]
        cands = [p for p in cands if p.tid not in used] or cands
        if not cands and starter and pt.kind == "dart" and pt.placed == d_start(d) and not pt.upgrades:
            starter = False     # the bot's own starter dart stands for it (match._lone_opener)
            continue
        if not cands:
            return False, f"no {pt.kind} at {pt.at}"
        p = cands[0]
        used.add(p.tid)
        if p.rnd > pt.placed + ROUND_SLACK:
            return False, f"{pt.kind} at {pt.at} bought round {p.rnd}, proven by {pt.placed}"
        for tiers, by in pt.upgrades:
            want = O.parse_cross(tiers)
            ups = [q for q in buys if q.tid == p.tid and all(a >= b for a, b in zip(q.tiers, want))]
            if not ups or ups[0].rnd > by + ROUND_SLACK:
                return False, f"{pt.kind} {tiers} not by round {by}"
    return True, f"proven by {proven.journal} (held to round {proven.held_through})"


def _guide_item(p):
    """A purchase as GUIDE writes it: the kind, or "kind a-b-c" for an upgrade."""
    if p.step.get("do") == "place":
        return p.kind
    return f"{p.kind} {'-'.join(map(str, p.tiers))}"


def matches_guide(d):
    """Are the build's purchases by OPENING_END the guide's own, in its order?
    Returns (ok, why). A plan whose opening outruns the guide's listed
    purchases still matches when every listed one comes first."""
    order = GUIDE.get(d["map"])
    if not order:
        return False, "no guide opening listed"
    if d["map"] in GUIDE_LOST:
        return False, f"the guide's opening lost live: {GUIDE_LOST[d['map']]}"
    buys = [_guide_item(p) for p in opening(d)]
    k = 0                   # the guide's purchases met so far
    for item in buys:
        if k == len(order):
            break           # the guide's listed opening is all bought first
        if item == order[k]:
            k += 1
        elif not _on_the_way(item, order[k]):
            return False, f"opening {buys} is not the guide's {list(order)} (at {item!r})"
    if k == 0:
        return False, f"opening {buys} is not the guide's {list(order)}"
    return True, f"the guide's opening {list(order[:k])}"


def _on_the_way(item, target):
    """Is upgrade ``item`` ("kind a-b-c") a tier the plan buys on the way to
    the guide's next upgrade ``target`` of the same kind (the guide writes
    "Sub 1-0-1", a plan 1-0-0 then 1-0-1)?"""
    a, b = item.split(" "), target.split(" ")
    if len(a) != 2 or len(b) != 2 or a[0] != b[0]:
        return False
    got, want = O.parse_cross(a[1]), O.parse_cross(b[1])
    return all(x <= y for x, y in zip(got, want))


def corrected_margin(margin, rnd):
    """The model's margin as the game honours it: rounds up to OPENING_END
    times EARLY_CREDIT (see the module docstring), later rounds unchanged."""
    return margin * EARLY_CREDIT if rnd <= OPENING_END else margin


def model_margins(d, rounds=None):
    """{round: worst margin over the lanes the round may take} of build ``d``
    for ``rounds`` (default the mode's first through OPENING_END), corrected
    (corrected_margin), live sight. On a map whose rounds take turns on
    several lanes every round is played on every lane (lane_margins)."""
    start = O.economy(d["modes"][0]).start_round
    rounds = rounds or range(start, OPENING_END + 1)
    lanes = O.lane_margins(d, rounds)
    if lanes:
        raw = {r: min(m[r] for m in lanes.values()) for r in rounds}
    else:
        raw = O.replay_plan(d, rounds, live_sight=True)
    return {r: round(corrected_margin(m, r), 2) for r, m in raw.items()}


def aimed_pierce_opening(d):
    """The AIMED_PIERCE tower kinds among the build's damage towers bought
    by OPENING_END (empty when there is none). The model credits a boat
    close to its full pierce against bloons that pass it one at a time
    (backlog 107): Luminous Cove's dart + boat 1-0-0, rated 2.48, lost
    round 8 twice; Firing Range's lone boat, rated 2.25, lost round 6. Its
    rating cannot carry an opening until 107 is fixed - a proven one can."""
    from btd6bot import strategy as S
    return sorted({p.kind for p in opening(d) if p.step.get("do") == "place" and p.kind in AIMED_PIERCE
                   and p.step.get("role", "dps") == "dps" and p.kind not in S.Executor.BUFFERS})


def matches_model(d):
    """Does the corrected model rate every round of the opening as held?
    Returns (ok, why)."""
    aimed = aimed_pierce_opening(d)
    if aimed:
        return False, f"{'/'.join(aimed)} in the opening: the model over-rates aimed pierce (backlog 107)"
    m = model_margins(d)
    worst = min(m, key=m.get)
    if m[worst] < EARLY_HOLD:
        return False, f"corrected model: round {worst} at {m[worst]} (all: {m})"
    return True, f"corrected model: worst {m[worst]} (round {worst})"


def opening_source(d):
    """(source, why) for build ``d``: "proven", "guide" or "model" when the
    opening meets the rule, None (with every reason) when it does not."""
    whys = []
    for p in PROVEN:
        if p.map == d["map"] and p.held_through >= PROVEN_THROUGH:
            ok, why = matches_proven(d, p)
            if ok:
                return "proven", why
            whys.append(f"{p.journal}: {why}")
    ok, why = matches_guide(d)
    if ok:
        return "guide", why
    whys.append(why)
    ok, why = matches_model(d)
    if ok:
        return "model", why
    whys.append(why)
    return None, "; ".join(whys)


# -- calibration from the journals ---------------------------------------------
def journal_rounds(journal_dir=None, first=6, last=20):
    """[(journal, round, live margin, leaked)] of every rated CHIMPS round
    ``first``..``last`` in the journals (default: the main checkout's
    logs/journal, where the live bot writes them; rounds the counter misread
    are left out)."""
    journal_dir = Path(journal_dir or O._main_checkout() / "logs" / "journal")
    out = []
    for f in sorted(journal_dir.glob("*chimps*.jsonl")):
        ev = []
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                ev.append(json.loads(line))
            except ValueError:
                continue
        if not ev or ev[0].get("ev") != "game_start":
            continue
        for i, e in enumerate(ev):
            if (e.get("ev") != "round" or e.get("reset") or e.get("margin") is None
                    or not first <= e["rnd"] <= last):
                continue
            leaked = None
            for e2 in ev[i + 1:]:
                if e2["ev"] == "leak":
                    leaked = True
                elif e2["ev"] == "round":
                    leaked = False
                elif e2["ev"] == "game_end":
                    leaked = e2.get("outcome") == "defeat"
                else:
                    continue
                break
            if leaked is not None:
                out.append((f.stem, e["rnd"], e["margin"], leaked))
    return out


def calibration(rows, corrected=False):
    """{leaked, leaked_rated_holding, held, held_rated_weak, auc} of rows
    (journal_rounds), with corrected_margin applied when ``corrected``."""
    def m_of(rnd, m):
        return corrected_margin(m, rnd) if corrected else m
    leaked = [m_of(r, m) for _, r, m, lk in rows if lk]
    held = [m_of(r, m) for _, r, m, lk in rows if not lk]
    pairs = len(leaked) * len(held)
    auc = (sum((h > x) + 0.5 * (h == x) for h in held for x in leaked) / pairs) if pairs else None
    return {"leaked": len(leaked), "leaked_rated_holding": sum(m >= EARLY_HOLD for m in leaked),
            "held": len(held), "held_rated_weak": sum(m < EARLY_HOLD for m in held),
            "auc": None if auc is None else round(auc, 2)}


def main(argv):
    O.lower_priority()
    if "--calibrate" in argv:
        rows = journal_rounds()
        for lo, hi in ((6, OPENING_END), (OPENING_END + 1, 20), (6, 20)):
            band = [r for r in rows if lo <= r[1] <= hi]
            print(f"rounds {lo}-{hi}: model {calibration(band)}, "
                  f"corrected (x{EARLY_CREDIT} to round {OPENING_END}) {calibration(band, corrected=True)}")
        return 0
    import yaml
    ids = [a for a in argv if not a.startswith("-")]
    paths = ([ROOT / "strategies" / "maps" / f"{i}.yaml" for i in ids] if ids
             else sorted((ROOT / "strategies" / "maps").glob("*chimps*.yaml")))
    for path in paths:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        src, why = opening_source(d)
        print(f"{path.stem:28s} {src or 'NONE':7s} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
