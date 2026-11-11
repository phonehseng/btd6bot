"""Will this round leak? The damage model asked about the towers standing now.

At the start of every round the match loop hands the towers on the board to
dps_model.round_margin (a few milliseconds): the factor by which they could
be weaker and the round still pop. A margin under CRISIS_MARGIN makes the
round a crisis round before any life is lost - abilities fire as soon as
bloons are out and idle cash is spent at once (match.py).

Calibrated on 2,104 logged rounds (docs/optimizer.md, section 3): rounds
rated 0-0.5 lost lives 11.8% of the time, 0.5-1.0 2.8%, above 2.0 0.5%.
The model is on the safe side (heroes and abilities are not counted), so
only the lowest band counts as a crisis. Example: the Water Park Easy game
lost on 2026-10-22 rated 0.29-0.45 at rounds 27-30, where it collapsed.

A round rated between 0.5 and 1 leaks in the model too, only less often in
the game; what makes it a crisis is how much it would cost. Pat's Pond ABR
(2026-11-05) went into round 54 rated 0.58 with 74 lives and $15,243 in
the bank, no crisis by the margin alone, and the round took every life
while the cash waited for a $21,600 plan step. So a round under 1 whose
expected leak at full strength (leaks, the model's own lives-lost count)
would cost LETHAL_SHARE of the lives left is a crisis round as well
(lethal_leak, is_crisis).

Line of sight is not passed to the model here (it rates towers behind
walls a little high); any failure turns the forecast off for the game.

Every answer is remembered per board and round (_memo): the model is a pure
function of the towers (kind, tiers, spot, placement round), the round and
the strength or search depth asked for, and the same board is asked about
again and again. One reinforce look on X Factor Impoppable (2026-11-10,
round 85, 37 towers) asked 58 margins and 23 leak counts, many of them the
same board and round (crisis_now and danger_round both rate the board at
the round being played and the next; strongest and plan_claim_in_crisis
re-rate the options), at 0.3-0.7 s each that late; and the looks repeat on
an unchanged board every few seconds while the bank fills. Remembered, a
repeated question costs nothing, so a look cut short by its time budget
(reinforce.LOOK_BUDGET_S) picks up at the next one where it left off.
"""
from __future__ import annotations

import logging
from collections import OrderedDict

log = logging.getLogger("forecast")

CRISIS_MARGIN = 0.5
LETHAL_SHARE = 0.5            # a round expected to cost this share of the lives left is a crisis too
REVERSE_SUFFIX = " reverse"   # map models of Reverse games are keyed "<map> reverse"
# Answers remembered (_memo), least recently used dropped first. One look
# asks about 60-150 (board, round) pairs; this keeps the last several looks'
# boards, a few MB of keys on a 40-tower board.
MEMO_SIZE = 4096
STATIONS_MEMO_SIZE = 64       # model stations (dps_model.stations_for) kept per board


def board_key(towers, phased=False):
    """What the model's answer for `towers` depends on, as a hashable key:
    each tower's id, kind, tiers and spot, in the order given, and with
    `phased` (a map that freezes towers, _phases) its placement round.
    Elsewhere the placement round is left out, so the executor's towers
    (which carry one) and reinforce.board()'s copies (which do not) share
    their answers."""
    if phased:
        return tuple((p.tid, p.kind, tuple(p.tiers), p.x, p.y, getattr(p, "placed_round", None))
                     for p in towers)
    return tuple((p.tid, p.kind, tuple(p.tiers), p.x, p.y) for p in towers)


def lowest(margins):
    """(lowest margin, its round) of a {round: margin} mapping, or None."""
    return min((m, r) for r, m in margins.items()) if margins else None


class RoundForecast:
    def __init__(self, map_key, mode, sight_grid=None, sight_heights=None):
        """sight_grid: the MapModel's line-of-sight blockers (MapModel.sight),
        so towers that need sight - snipers included - count only the track
        they can see; sight_heights: (MapModel.sight_height,
        MapModel.ground_height), so towers on raised ground see over
        blockers no higher than it."""
        reverse = bool(map_key) and map_key.endswith(REVERSE_SUFFIX)
        self.map_name = map_key[:-len(REVERSE_SUFFIX)] if reverse else map_key
        self.reverse = reverse
        self.mode = mode or "medium"
        self.track = None
        self.sight = None
        self._sight_grid = sight_grid
        self._sight_heights = sight_heights
        self.off = not map_key
        self._memo = OrderedDict()          # (what, board_key, round) -> answer
        self._stations_memo = OrderedDict()  # board_key -> stations
        # ratings the model actually ran (not answered from _memo): a look
        # cut short by its budget is cut only once it has rated something
        # new (reinforce.LookBudget), so the looks always get further
        self.computed = 0

    @staticmethod
    def _remember(memo, key, value, size):
        """Store `value` under `key` in an LRU `memo` of at most `size` entries."""
        memo[key] = value
        memo.move_to_end(key)
        while len(memo) > size:
            memo.popitem(last=False)

    def _key(self, towers):
        """board_key for this forecast's map: with placement rounds where
        towers freeze (track uptime under 1, _phases)."""
        return board_key(towers, phased=getattr(self.track, "uptime", 1.0) < 1.0)

    def _ready(self):
        """Load the track once; False when the forecast is off."""
        if self.off:
            return False
        if self.track is None:
            from . import dps_model as D
            if not D.available():
                self.off = True
                return False
            self.track = D.Track(self.map_name, reverse=self.reverse)
            self.sight = D.sight_test(self._sight_grid, self.track, heights=self._sight_heights)
        return True

    def stations(self, towers):
        """The model's stations for `towers` (objects with tid, kind, tiers,
        x, y in screen fractions; the hero is left out), or None.

        Remembered per board (_stations_memo): building them took 50 ms a
        call on a 37-tower board, 3 s of a 37 s look. Reusing them is safe:
        dps_model._play sets every station's strength before it plays."""
        key = board_key(towers)            # stations do not depend on placement rounds
        if key in self._stations_memo:
            self._stations_memo.move_to_end(key)
            return self._stations_memo[key]
        st = self._build_stations(towers)
        self._remember(self._stations_memo, key, st, STATIONS_MEMO_SIZE)
        return st

    def _build_stations(self, towers):
        """stations() without the memo."""
        from . import dps_model as D
        from . import towers as T
        placed = []
        for p in towers:
            if p.kind == "hero" or p.kind not in T.TOWERS:
                continue
            x, z, _ = self.track.frac_to_world(p.x, p.y)
            placed.append(D.Placed(p.tid, p.kind, tuple(p.tiers), x, z))
        return D.stations_for(placed, self.track, self.sight) if placed else None

    def _phases(self, towers, rounds):
        """Split `rounds` by which towers are awake in them, on maps that
        freeze towers (dps_model.TOWER_FREEZE): [(stations, rounds, exact)].

        When every tower's placement round is known (Executor sets
        placed_round), each round is rated with only the towers that are
        not in ice then, at full strength (exact=True) - a Fast Track opening
        bought in one round freezes all at once, and the average uptime rated
        that round 1.70 (Medium 2026-11-07) and 0.81 (ABR 2026-11-09) while it
        had nothing awake. Otherwise every round is rated with the whole
        defence at the average uptime (exact=False). Stations are [] when
        every tower is frozen, None when there is no tower at all."""
        return [(stations(), rs, exact) for stations, rs, exact in self._phase_groups(towers, rounds)]

    def _phase_groups(self, towers, rounds):
        """_phases with each group's stations left to build: [(a function
        returning the stations, rounds, exact)], so a group whose rounds
        are all remembered (_rate) builds none."""
        from . import dps_model as D
        built = [p for p in towers if p.kind != "hero"]
        if (getattr(self.track, "uptime", 1.0) >= 1.0 or not built
                or any(getattr(p, "placed_round", None) is None for p in built)):
            return [(lambda: self.stations(towers), list(rounds), False)]
        groups = {}
        for r in rounds:
            awake = tuple(p for p in built if not D.frozen_in(self.map_name, p.placed_round, r))
            groups.setdefault(tuple(p.tid for p in awake), (awake, []))[1].append(r)
        return [((lambda awake=awake: (self.stations(list(awake)) or []) if awake else []), rs, True)
                for awake, rs in groups.values()]

    def _rate(self, towers, rounds, rate, what=None):
        """{round: rate(stations, round)} over `rounds`, rating each round
        with the towers awake in it (_phases); None without towers.

        what: names the question (with its strength or search depth) so the
        answer is remembered per board and round (_memo); None: not
        remembered. The rounds come out in the order an unremembered call
        rates them, whatever was remembered: best() takes the first of
        equally bad rounds as the worst."""
        key = self._key(towers) if what is not None else None
        out = {}
        for stations, rs, exact in self._phase_groups(towers, rounds):
            known = {}
            if key is not None:
                for r in rs:
                    if (what, key, r) in self._memo:
                        self._memo.move_to_end((what, key, r))
                        known[r] = self._memo[(what, key, r)]
            st = None
            if len(known) < len(rs):
                st = stations()
                if st is None:
                    return None
            saved = self.track.uptime
            if exact:
                self.track.uptime = 1.0     # the frozen towers are left out instead
            try:
                for r in rs:
                    if r in known:
                        out[r] = known[r]
                        continue
                    out[r] = rate(st, r)
                    self.computed += 1
                    if key is not None:
                        self._remember(self._memo, (what, key, r), out[r], MEMO_SIZE)
            finally:
                self.track.uptime = saved
        return out

    def margins(self, towers, rounds, iterations=9):
        """{round: margin} over `rounds` for `towers`, or None.
        The defence is built once and rated round by round (~70 ms each;
        fewer `iterations` of the margin search are quicker and coarser)."""
        if not rounds:
            return None
        try:
            if not self._ready():
                return None
            from . import dps_model as D
            return self._rate(towers, rounds, lambda st, r: D.round_margin(
                st, self.mode, r, self.track, iterations=iterations), what=("margin", iterations))
        except Exception:   # a forecast must never cost a game
            log.exception("round forecast failed - off for the rest of this game")
            self.off = True
            return None

    def remembered_margin(self, towers, rnd, iterations=9):
        """The margin of round `rnd` for `towers` if an earlier question
        already rated it (_memo), else None - without rating anything.

        The last pass of a reinforce look that ran out of time on several
        passes in a row (reinforce.MAX_BUSY_LOOKS) chooses from what those
        passes rated instead of rating everything again: on Water Park
        Impoppable (2026-11-11, round 88, 28 towers) a whole look rated 67
        growth paths at ~0.7 s each, ten passes of 6 s, and the game was
        lost before one finished."""
        if rnd is None or self.off or self.track is None:
            return None
        key = (("margin", iterations), self._key(towers), rnd)
        if key not in self._memo:
            return None
        self._memo.move_to_end(key)
        return self._memo[key]

    def worst(self, towers, rounds, iterations=9):
        """(lowest margin, its round) over `rounds` for `towers`, or None."""
        return lowest(self.margins(towers, rounds, iterations))

    def leaks(self, towers, rounds, strength, per_round=False):
        """Lives the model's defence would lose over `rounds` with every
        tower at `strength` (0.5 = half strength: what a margin of 2 must
        hold); {round: lives} with per_round. One simulation per round, and
        it moves with every purchase - unlike the margin search, whose steps
        hide small gains. None when it cannot be rated."""
        try:
            if not self._ready():
                return None
            from . import dps_model as D
            lost = self._rate(towers, rounds, lambda st, r: D.simulate_round(
                st, self.mode, r, self.track, strength=strength).lives_lost, what=("leaks", strength))
            if lost is None:
                return None
            return lost if per_round else sum(lost.values())
        except Exception:   # a forecast must never cost a game
            log.exception("round forecast failed - off for the rest of this game")
            self.off = True
            return None

    def margin(self, towers, rnd):
        """The model's margin of round `rnd` for `towers`, or None."""
        if rnd is None:
            return None
        w = self.worst(towers, [rnd])
        return None if w is None else w[0]

    def lethal_leak(self, towers, rnd, margin):
        """Lives the model expects round `rnd` to cost with every tower at
        full strength, asked only of a round rated under 1 (one rated 1 or
        more pops in the model); None otherwise, or when it cannot be rated.
        One simulation, so the margin that is known already decides whether
        it runs at all."""
        if margin is None or margin >= 1.0 or rnd is None:
            return None
        return self.leaks(towers, [rnd], 1.0)

    @staticmethod
    def is_crisis(margin, lives=None, leak=None):
        """A crisis round: rated under CRISIS_MARGIN, or under 1 while its
        expected leak (`leak`, lethal_leak) would cost LETHAL_SHARE of the
        `lives` left. Without lives or a leak count the margin alone decides."""
        if margin is None:
            return False
        if margin < CRISIS_MARGIN:
            return True
        return bool(margin < 1.0 and leak is not None and lives and leak >= LETHAL_SHARE * lives)
