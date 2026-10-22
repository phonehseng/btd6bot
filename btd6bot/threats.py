"""What every bloon is, what can pop it, and when it arrives.

The bot must never lose to a bloon it cannot pop. This module answers the
three questions behind that rule, each from its own data file:

  * What is each bloon?      data/bloons.json   (layers, HP, children, properties)
  * What can pop it?         the game's own model (btd6bot/gamemodel.py, decoded
                             from the game files: per crosspath, which properties
                             some attack pops, camo detection, decamo, radar, MIB),
                             with data/counters.json for what it does not say
                             (which ONE attack does it, blimps, buffs)
  * When does it come?       data/game_data/round_sets.json (the game's own rounds)

Signatures
----------
A bloon's *signature* is the set of properties ONE attack has to get past
to pop it. A camo lead's signature is {camo, lead}: the attack must come from
a tower that can see camo AND be of a damage type lead is not immune to. A
Ninja (sees camo, sharp) next to a Bomb Shooter (pops lead, cannot see camo)
covers {camo} and {lead} but not {camo, lead} - the camo lead walks through.

Children inherit camo and regrow, so a round needs the signatures of every
bloon it can produce, children included: a lead pops into two blacks, so a
defence of bombs alone pops the lead and leaks its children. DDTs carry camo,
lead and black at once and drop camo regrow ceramics.

The signature properties are:
  camo    needs camo detection (or damage that lies on the track, or a decamo)
  lead    immune to sharp, cold and energy damage
  black   immune to explosions
  white   immune to cold (freeze)
  purple  immune to energy, fire and plasma
  blimp   MOAB-class: cannot be frozen (the Ice Monkey's attacks do nothing)
Regrow and fortified are not immunities (they need more damage, not a
different kind of damage), so they are not part of a signature.

Facts marked "likely" in counters.json are documented but never counted: the
bot only trusts what is established or confirmed by the game model.
"""
from __future__ import annotations

import itertools
import json
import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("threats")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Properties that make up a signature, in the order used to name them.
SIG_ORDER = ("camo", "lead", "black", "white", "purple", "blimp")
# Readable names for signatures that have a well-known name of their own.
SIG_NAMES = {
    frozenset({"black", "white"}): "zebra",
    frozenset({"camo", "black", "white"}): "camo+zebra",
    frozenset({"blimp", "camo", "lead", "black"}): "ddt",
}
# A modifier a parent passes on to its children (camo and regrow do;
# fortified only passes from one blimp to the next, see _signatures).
INHERITED = ("camo", "regrow")


# ---------------------------------------------------------------------------
# data files
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _load(rel):
    """A JSON file under data/, or None when it is missing or unreadable.
    Cached for the life of the process (the bot reloads code between games)."""
    try:
        return json.loads((DATA / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def bloons():
    """{bloon type: facts} from data/bloons.json."""
    return (_load("bloons.json") or {}).get("bloons", {})


def counters():
    """The whole data/counters.json ({} when missing)."""
    return _load("counters.json") or {}


def available():
    """True when both knowledge files are present; without them the bot
    falls back to the older tier tables in strategy.py."""
    return bool(bloons().get("ceramic", {}).get("children")) and bool(counters().get("towers"))


def counted_levels():
    """Confidence levels the bot trusts when deciding coverage."""
    return set(counters().get("bot_counts") or ("game_model", "established"))


# ---------------------------------------------------------------------------
# bloons: signatures of a bloon and of everything it pops into
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _signatures(bloon, camo, regrow, fortified):
    """frozensets of properties of this bloon and of all its descendants.

    camo/regrow are inherited by every child. A fortified blimp's children
    are fortified too, a fortified ceramic or lead releases normal children;
    fortification never changes a signature, it is passed along only so the
    same recursion can be reused for HP sums."""
    facts = bloons().get(bloon, {})
    props = set(facts.get("properties") or ())
    if camo:
        props.add("camo")
    out = {frozenset(p for p in props if p in SIG_ORDER)}
    child_camo = camo or "camo" in (facts.get("child_modifiers") or ()) or "camo" in props
    child_regrow = regrow or "regrow" in (facts.get("child_modifiers") or ())
    child_fort = fortified and facts.get("class") == "blimp"
    for child in set(facts.get("children") or ()):
        out |= _signatures(child, child_camo, child_regrow, child_fort)
    out.discard(frozenset())
    return frozenset(out)


def signatures(bloon, camo=False, regrow=False, fortified=False):
    """Every signature a bloon (with modifiers) and its children carry."""
    return set(_signatures(bloon, bool(camo), bool(regrow), bool(fortified)))


def sig_name(sig):
    """frozenset({'camo', 'lead'}) -> 'camo+lead'; well-known ones by name."""
    sig = frozenset(sig)
    if sig in SIG_NAMES:
        return SIG_NAMES[sig]
    return "+".join(p for p in SIG_ORDER if p in sig)


def sig_from_name(name):
    """Inverse of sig_name; None for names that are not signatures
    (the older strength threats: ceramic, moab, rush, ...)."""
    for sig, n in SIG_NAMES.items():
        if n == name:
            return sig
    parts = str(name).replace("_", "+").split("+")
    if parts and all(p in SIG_ORDER for p in parts):
        return frozenset(parts)
    return None


def rbe(bloon, fortified=False, super_ceramic=False):
    """Red Bloon Equivalent: HP of every layer of the bloon and its children
    (non-freeplay: each child released in full)."""
    facts = bloons().get(bloon, {})
    hp = facts.get("hp", 1)
    if fortified and facts.get("hp_fortified"):
        hp = facts["hp_fortified"]
    if bloon == "ceramic" and super_ceramic:
        hp = facts.get("hp_super_fortified" if fortified else "hp_super", hp)
    child_fort = fortified and facts.get("class") == "blimp"
    return hp + sum(rbe(c, child_fort, super_ceramic) for c in facts.get("children") or ())


def blimp_hp(bloon, fortified=False):
    """HP of the MOAB-class layers only (a ZOMG's own 4000 + its 4 BFBs + their
    16 MOABs): what blimp damage has to chew through before ceramics fall out."""
    facts = bloons().get(bloon, {})
    if facts.get("class") != "blimp":
        return 0
    hp = facts.get("hp_fortified") if fortified and facts.get("hp_fortified") else facts.get("hp", 0)
    return hp + sum(blimp_hp(c, fortified) for c in facts.get("children") or ())


# ---------------------------------------------------------------------------
# rounds: which signatures each round brings, per round set
# ---------------------------------------------------------------------------

def set_for_mode(mode):
    """The round set a mode plays: Alternate Bloons Rounds or the standard one."""
    return "abr" if mode == "abr" else "standard"


@lru_cache(maxsize=None)
def round_groups(set_name, rnd):
    """Bloon groups of a round, from the game's own round sets (data/rounds.json
    as a fallback, which holds the same groups)."""
    rs = _load("game_data/round_sets.json") or {}
    groups = (rs.get(set_name) or {}).get(str(rnd), {}).get("groups")
    if groups is None:
        groups = ((_load("rounds.json") or {}).get(set_name) or {}).get(str(rnd), {}).get("groups")
    return tuple(groups or ())


@lru_cache(maxsize=None)
def round_signatures(set_name, rnd):
    """frozenset of signatures that round rnd can put on the track."""
    out = set()
    for g in round_groups(set_name, rnd):
        out |= signatures(g["bloon"], g.get("camo"), g.get("regrow"), g.get("fortified"))
    return frozenset(out)


@lru_cache(maxsize=None)
def calendar(set_name, start, end):
    """{signature name: [rounds start..end that need it]} - when each threat comes."""
    out = {}
    for rnd in range(start, end + 1):
        for sig in round_signatures(set_name, rnd):
            out.setdefault(sig_name(sig), []).append(rnd)
    return out


def first_rounds(set_name, start, end):
    """{signature name: first round in start..end that needs it}."""
    return {name: rounds[0] for name, rounds in calendar(set_name, start, end).items()}


def next_round(set_name, need, rnd, end):
    """First round >= rnd (and <= end) that needs this signature, or None."""
    for r in calendar(set_name, 1, end).get(need, ()):
        if r >= rnd:
            return r
    return None


def round_cash(set_name, rnd):
    """Cash a round pays at base difficulty (pops + end-of-round bonus), from
    data/rounds.json; 0 when unknown. Double Cash and farms are left out on
    purpose: the threat calendar plans with the money it can count on."""
    rd = ((_load("rounds.json") or {}).get(set_name) or {}).get(str(rnd)) or {}
    return float(rd.get("cash") or 0.0)


# ---------------------------------------------------------------------------
# towers: what one tower at one crosspath can do
# ---------------------------------------------------------------------------

def _tiers(cross):
    """'0-2-1' or [0, 2, 1] -> (0, 2, 1)."""
    if isinstance(cross, tuple):
        return cross
    if isinstance(cross, str):
        return tuple(int(c) for c in cross.split("-"))
    return tuple(int(c) for c in cross)


def _within(tiers, entry):
    """Is a crosspath inside an entry's [min, max] window (see conventions)?"""
    lo = _tiers(entry.get("min", "0-0-0"))
    hi = _tiers(entry.get("max", "5-5-5"))
    return all(l <= t <= h for t, l, h in zip(tiers, lo, hi))


def _counted(entry):
    return entry.get("confidence", "established") in counted_levels()


def tower_facts(kind):
    return (counters().get("towers") or {}).get(kind, {})


# -- the game's own model ------------------------------------------------------
# gamemodel.can(kind, tiers, word) says, per crosspath, whether SOME attack of
# the tower pops a property ('lead', 'black', 'white', 'purple'), detects camo
# ('camo'), hits camo unaimed ('hits_camo'), strips camo ('decamo'), or lends
# camo / every damage type to towers in range ('gives_camo', 'gives_damage_type').
# Where it answers, it is the truth; counters.json is the fallback, and still
# says which single attack pops a bloon with several immunities at once.

def _gm():
    """btd6bot.gamemodel when its tables exist, else None."""
    try:
        from . import gamemodel
        return gamemodel if gamemodel.available() else None
    except Exception:          # a missing or broken model only means: use counters.json
        return None


@lru_cache(maxsize=None)
def gm_can(kind, tiers, word):
    """The game model's verdict (True/False), or None when it has none."""
    gm = _gm()
    if gm is None:
        return None
    try:
        return gm.can(kind, _tiers(tiers), word)
    except Exception:
        return None


def attacks(kind, tiers):
    """The attacks a tower has at this crosspath (counted facts only)."""
    return _attacks(kind, _tiers(tiers))


@lru_cache(maxsize=None)
def _attacks(kind, tiers):
    return tuple(a for a in tower_facts(kind).get("attacks") or () if _counted(a) and _within(tiers, a))


def cannot_pop(damage_type):
    """Bloon properties a damage type cannot pop."""
    return set(((counters().get("damage_types") or {}).get(damage_type) or {}).get("cannot_pop") or ())


def camo_access(kind, tiers):
    """How a tower gets at camo bloons on its own, e.g. 'detect (Night Vision
    Goggles)' or 'track (spikes lie on the track)'; None if it cannot."""
    return _camo_access(kind, _tiers(tiers))


@lru_cache(maxsize=None)
def _camo_access(kind, tiers):
    mine = None
    for c in tower_facts(kind).get("camo") or ():
        if c.get("how") in ("detect", "track") and _counted(c) and _within(tiers, c):
            mine = c
            break
    detect = gm_can(kind, tiers, "camo")
    if detect:
        name = mine.get("upgrade") if mine and mine.get("how") == "detect" else "game model"
        return f"detect ({name})"
    # damage lying on the track (Spike Factory) hits camo without detection; only
    # towers counters.json lists as such count, as other unaimed hits need a target
    if mine is not None and mine["how"] == "track" and gm_can(kind, tiers, "hits_camo") is not False:
        return f"track ({mine.get('upgrade', '')})"
    if detect is None and mine is not None:
        return f"{mine['how']} ({mine.get('upgrade', '')})"
    return None


def decamos(kind, tiers):
    """Does this tower strip camo from the bloons it hits (everyone sees them after)?"""
    return _decamos(kind, _tiers(tiers))


@lru_cache(maxsize=None)
def _decamos(kind, tiers):
    verdict = gm_can(kind, tiers, "decamo")
    if verdict is not None:
        return verdict
    return any(c.get("how") == "decamo" and _counted(c) and _within(tiers, c)
               for c in tower_facts(kind).get("camo") or ())


def auras(kind, tiers):
    """What this tower grants towers in its range: {'camo', 'all_types', ...}."""
    return _auras(kind, _tiers(tiers))


@lru_cache(maxsize=None)
def _auras(kind, tiers):
    mine = {a["grant"] for a in tower_facts(kind).get("auras") or ()
            if _counted(a) and _within(tiers, a)}
    for grant, word in (("camo", "gives_camo"), ("all_types", "gives_damage_type")):
        verdict = gm_can(kind, tiers, word)
        if verdict is not None:
            mine.discard(grant)
            if verdict:
                mine.add(grant)
    return frozenset(mine)


def _attack_pops(attack, sig):
    """Can this one attack pop a bloon with this signature (camo aside)?"""
    if "blimp" in sig and attack.get("blimp") is False:
        return False
    return not (cannot_pop(attack["type"]) & (set(sig) - {"camo", "blimp"}))


GAME_MODEL_ATTACK = {"type": "game model", "what": "the game says some attack pops it"}


@lru_cache(maxsize=None)
def _hit(kind, tiers, sig):
    """The attack of this tower that pops sig on its own (camo aside), or None.

    The game model decides each single property: if it says the tower cannot
    pop lead at this crosspath, nothing here can. A signature with ONE damage
    property (lead, purple, camo+black ...) is popped when the game says so.
    With two or more at once (zebra, DDT) the game model cannot say whether
    the same attack does both, so counters.json's attack must, too."""
    dmg = set(sig) - {"camo", "blimp"}
    verdicts = [gm_can(kind, tiers, p) for p in sorted(dmg)]
    if any(v is False for v in verdicts):
        return None
    mine = next((a for a in _attacks(kind, tiers) if _attack_pops(a, sig)), None)
    if mine is not None or len(dmg) > 1 or any(v is None for v in verdicts):
        return mine
    # one property (or none) and the game says yes: trust it - unless our facts
    # know every attack of this tower and none can hurt blimps (the Ice Monkey)
    if "blimp" in sig and _attacks(kind, tiers) and \
            all(a.get("blimp") is False for a in _attacks(kind, tiers)):
        return None
    if not dmg and not any(gm_can(kind, tiers, p) for p in ("black", "white", "purple", "lead")):
        return None          # it pops nothing at all (a village, a farm)
    return GAME_MODEL_ATTACK


@lru_cache(maxsize=None)
def _hit_with_mib(kind, tiers, sig):
    """The attack that pops sig inside a Monkey Intelligence Bureau's range
    (every damage type pops every bloon there; it must still hurt blimps), or None."""
    mine = next((a for a in _attacks(kind, tiers)
                 if not ("blimp" in sig and a.get("blimp") is False)), None)
    if mine is None and not _attacks(kind, tiers) and \
            any(gm_can(kind, tiers, p) for p in ("black", "white", "purple", "lead")):
        return GAME_MODEL_ATTACK   # the game says it deals damage; our facts do not list it
    return mine


# ---------------------------------------------------------------------------
# a defence: does it cover a signature?
# ---------------------------------------------------------------------------

def _tower_tuple(t):
    """(tid, kind, tiers) from a strategy Placed, a dict or a tuple."""
    if isinstance(t, tuple):
        return t[0], t[1], _tiers(t[2])
    if isinstance(t, dict):
        return t.get("tid") or t.get("id"), t["kind"], _tiers(t.get("tiers", (0, 0, 0)))
    return getattr(t, "tid", None), t.kind, _tiers(t.tiers)


def covers(towers, sig, in_range=None, poppers=None):
    """(True, how) if some tower of the defence can pop a bloon with signature
    sig, else (False, what is missing).

    towers: (tid, kind, tiers) tuples, Placed objects or dicts; heroes are
            ignored (their abilities change with level and are not modelled).
    in_range(aura_tid, tower_tid) -> bool: is the tower inside that support
            tower's range? None means yes (strategy-level checks, where
            villages are placed `near` the towers they serve).
    poppers: only these tower ids may be the one that pops it (the others
            still lend their auras and decamo); None = any tower.

    One attack has to get past every immunity at once, from a tower that can
    get at camo (if the signature has camo): its own detection, damage on the
    track, a Radar Scanner/MIB village in range, or any decamo tower (decamo
    bloons stay visible for everyone downstream; position is not modelled).
    Decamo is not counted against blimps: whether a decamo strips a DDT's
    camo is not established, so a DDT needs real detection. Nor does a
    tower's own decamo let it see camo (a Sub 3-x-x only strips camo: its
    own camo attack comes at 4-x-x).
    Support in range can lift immunities: a Monkey Intelligence Bureau all
    of them, an Alchemist's Acidic Mixture Dip the lead one."""
    sig = frozenset(sig)
    tw = [_tower_tuple(t) for t in towers]
    tw = [t for t in tw if t[1] != "hero"]
    inr = in_range or (lambda a, b: True)
    radar = [tid for tid, kind, tiers in tw if auras(kind, tiers) & {"camo", "all_types"}]
    mib = [tid for tid, kind, tiers in tw if "all_types" in auras(kind, tiers)]
    dip = [tid for tid, kind, tiers in tw if "lead" in auras(kind, tiers)]
    decamo = [(tid, kind) for tid, kind, tiers in tw if decamos(kind, tiers)] if "blimp" not in sig else []
    missing = "nothing pops it"
    for tid, kind, tiers in tw:
        if poppers is not None and tid not in poppers:
            continue
        hit, via = _hit(kind, tiers, sig), ""
        if hit is None and "lead" in sig:
            dipped = [v for v in dip if v != tid and inr(v, tid)]
            if dipped:   # acid-coated attacks pop lead
                hit, via = _hit(kind, tiers, sig - {"lead"}), f" + Acidic Mixture Dip {dipped[0]}"
        if hit is None:
            boosted = [v for v in mib if v != tid and inr(v, tid)]
            if boosted:  # MIB: every type pops every bloon
                hit, via = _hit_with_mib(kind, tiers, sig), f" via MIB {boosted[0]}"
        if hit is None:
            continue
        if "camo" in sig:
            own = camo_access(kind, tiers)
            seen_by = [v for v in radar if v != tid and inr(v, tid)]
            stripped = [k for d, k in decamo if d != tid]   # its own decamo does not count
            if own:
                how_camo = f"camo: {own}"
            elif seen_by:
                how_camo = f"camo: Radar Scanner {seen_by[0]}"
            elif stripped:
                how_camo = f"camo: decamo by a {stripped[0]}"
            else:
                missing = f"{kind} could pop it but cannot see camo"
                continue
        else:
            how_camo = ""
        how = f"{tid or kind} ({kind} {'-'.join(map(str, tiers))}: {hit['type']}{via}"
        how += f"; {how_camo})" if how_camo else ")"
        return True, how
    return False, missing


# ---------------------------------------------------------------------------
# answers: crosspaths of one tower kind that close a gap
# ---------------------------------------------------------------------------

def legal(tiers):
    """At most two paths used and at most one of them above tier 2."""
    return sum(t > 0 for t in tiers) <= 2 and sum(t > 2 for t in tiers) <= 1


@lru_cache(maxsize=None)
def all_crosspaths():
    """Every legal crosspath, cheapest-looking first (fewest total tiers)."""
    out = [t for t in itertools.product(range(6), repeat=3) if legal(t)]
    return tuple(sorted(out, key=lambda t: (sum(t), t)))


def covering_crosspaths(kind, sig, others=(), caps=(5, 5, 5), start=(0, 0, 0), in_range=None,
                        tid="__new__"):
    """Crosspaths >= start (and <= caps) at which a tower of this kind makes the
    defence cover sig, together with the `others`. Minimal ones only: a
    crosspath is dropped when a smaller one on the way to it already works.

    tid: the id of the tower being bought or upgraded ('__new__' for a tower
    not placed yet), so that in_range can tell where it stands.

    Gives the same answer as calling covers() on others + the tower at each
    crosspath (tests/test_threats_offline.py checks that), but works out the
    fixed part of the defence once: with 30 towers on the map and every
    tower kind to try, calling covers() each time took seconds."""
    start, sig = _tiers(start), frozenset(sig)
    camo = "camo" in sig
    inr = in_range or (lambda a, b: True)
    base = [b for b in (_tower_tuple(o) for o in others) if b[1] != "hero"]
    radar = [b[0] for b in base if _auras(b[1], b[2]) & {"camo", "all_types"}]
    mib = [b[0] for b in base if "all_types" in _auras(b[1], b[2])]
    dip = [b[0] for b in base if "lead" in _auras(b[1], b[2])]
    no_blimp = "blimp" not in sig            # decamo is not counted against blimps
    decamo_ids = [b[0] for b in base if no_blimp and _decamos(b[1], b[2])]
    base_decamo = bool(decamo_ids)
    unleaded = sig - {"lead"} if "lead" in sig else None   # what is left under a lead dip

    def pops_with(k, t, in_dip, in_mib):
        """Does a tower pop it, given the support it stands in?"""
        return (_hit(k, t, sig) is not None
                or (in_dip and unleaded is not None and _hit(k, t, unleaded) is not None)
                or (in_mib and _hit_with_mib(k, t, sig) is not None))

    # each placed tower: (id, pops it with the help it has, pops it if dipped,
    #                     pops it inside an MIB, gets at camo with the help it has)
    info = []
    for bid, bkind, btiers in base:
        pops = pops_with(bkind, btiers, any(v != bid and inr(v, bid) for v in dip),
                         any(v != bid and inr(v, bid) for v in mib))
        pops_dip = unleaded is not None and _hit(bkind, btiers, unleaded) is not None
        pops_mib = _hit_with_mib(bkind, btiers, sig) is not None
        sees = (not camo or _camo_access(bkind, btiers) is not None
                or any(d != bid for d in decamo_ids)
                or any(v != bid and inr(v, bid) for v in radar))
        info.append((bid, pops, pops_dip, pops_mib, sees))
    new_in_mib = any(v != tid and inr(v, tid) for v in mib)
    new_in_dip = any(v != tid and inr(v, tid) for v in dip)
    new_seen = any(v != tid and inr(v, tid) for v in radar) or base_decamo
    near_ids = {b[0]: b[0] != tid and inr(tid, b[0]) for b in base}   # in the changed tower's range
    found = []
    for t in all_crosspaths():
        if any(a < s or a > c for a, s, c in zip(t, start, caps)):
            continue
        if any(all(f[i] <= t[i] for i in range(3)) for f in found):
            continue  # a smaller crosspath already covers it
        grants = _auras(kind, t)
        decamo = no_blimp and _decamos(kind, t)
        # 1. the tower itself pops it ...
        pops = pops_with(kind, t, new_in_dip, new_in_mib)
        ok = pops and (not camo or _camo_access(kind, t) is not None or new_seen)
        # 2. ... or it lets a placed tower pop it (radar, MIB, lead dip, decamo)
        if not ok:
            for bid, bpops, bpops_dip, bpops_mib, bsees in info:
                near = near_ids[bid]
                if not (bpops or (near and "all_types" in grants and bpops_mib)
                        or (near and "lead" in grants and bpops_dip)):
                    continue
                if bsees or decamo or (near and grants & {"camo", "all_types"}):
                    ok = True
                    break
        if ok:
            found.append(t)
    return found


# ---------------------------------------------------------------------------
# blimp damage: the MOAB-class ramp
# ---------------------------------------------------------------------------

RED_SPEED_UNITS_S = 25.0   # bloonswiki base speed of a red bloon (bloons.json speeds are relative)


def blimp_dps(kind, tiers):
    """Rough single-target damage per second against blimps (counters.json
    blimp_dps; the highest entry the crosspath reaches)."""
    tiers = _tiers(tiers)
    best = 0.0
    for cross, dps in (counters().get("blimp_dps") or {}).get(kind) or ():
        if all(t >= c for t, c in zip(tiers, _tiers(cross))):
            best = max(best, float(dps))
    return best


def round_blimp_load(set_name, rnd, double_hp=False):
    """What blimp damage a round asks for: total MOAB-class HP (children
    blimps included, fortified x2, Double HP MOABs x2, freeplay ramp from
    data/rounds.json), the number of top-level blimps, the spawn span and the
    slowest blimp's speed (units/s). None for rounds without blimps."""
    rd = ((_load("rounds.json") or {}).get(set_name) or {}).get(str(rnd)) or {}
    mult = float(rd.get("blimp_hp_mult") or 1.0) * (2.0 if double_hp else 1.0)
    speed_mult = float(rd.get("speed_mult") or 1.0)
    hp = 0.0
    count = 0
    span = 0.0
    slowest = None
    for g in round_groups(set_name, rnd):
        facts = bloons().get(g["bloon"], {})
        if facts.get("class") != "blimp":
            continue
        hp += g["count"] * blimp_hp(g["bloon"], g.get("fortified")) * mult
        count += g["count"]
        span = max(span, float(g.get("end_s", 0.0)))
        v = float(facts.get("speed", 1.0)) * RED_SPEED_UNITS_S * speed_mult
        slowest = v if slowest is None else min(slowest, v)
    if not count:
        return None
    return {"hp": hp, "blimps": count, "span_s": span, "speed": slowest}


def blimp_capacity(towers, load, track_len, range_of=None, reach_of=None):
    """Damage the defence can deal to that round's blimps (very rough).

    Each tower works while blimps are inside its range: a map-wide tower for
    the whole crossing of the track; a ranged one for the length of track
    inside its range - reach_of(tid, kind) in world units when the map model
    knows it, else about 2.5 x its range (a chord through its circle plus
    some winding). With several blimps spaced over the spawn span, a tower
    keeps busy for at most the spawn span plus one crossing."""
    if not load:
        return 0.0
    cross_t = track_len / max(load["speed"], 1e-6)
    total = 0.0
    for tid, kind, tiers in (_tower_tuple(t) for t in towers):
        if kind == "hero":
            continue
        dps = blimp_dps(kind, tiers)
        if dps <= 0:
            continue
        if tower_facts(kind).get("map_wide"):
            t_in = cross_t
        else:
            reach = reach_of(tid, kind) if reach_of else None
            if reach is None:
                reach = 2.5 * (range_of(kind) if range_of else 40.0)
            t_in = min(cross_t, reach / max(load["speed"], 1e-6))
        busy = min(load["span_s"] + t_in, load["blimps"] * t_in)
        total += dps * busy
    return total


def track_length(geom, playfield=None):
    """Visible length (world units) of a map's bloon lane: the median of its
    active, visible paths, counted between the first and last point that is
    on screen. None without geometry."""
    if not geom:
        return None
    import numpy as np
    from .layout import LAYOUTS
    from .mapgeom import Projection, _visible_span
    proj = Projection(playfield or LAYOUTS["16:10"]["playfield"])
    lengths = []
    for path in geom.get("paths") or ():
        if path.get("hidden") or not path.get("active", True) or len(path.get("points") or ()) < 2:
            continue
        pts = np.asarray(path["points"], float)
        a, b = _visible_span(proj.to_cells(pts))
        seg = np.linalg.norm(np.diff(pts[a:b + 1, :2], axis=0), axis=1)
        if seg.size:
            lengths.append(float(seg.sum()))
    if not lengths:
        return None
    lengths.sort()
    return lengths[len(lengths) // 2]


def clear_caches():
    """Forget every cached answer (after the data files or the game model
    changed, or to compare with and without the game model in tests)."""
    for f in (_load, _signatures, round_groups, round_signatures, calendar, all_crosspaths,
              gm_can, _attacks, _camo_access, _decamos, _auras, _hit, _hit_with_mib):
        f.cache_clear()
