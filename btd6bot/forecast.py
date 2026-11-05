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
"""
from __future__ import annotations

import logging

log = logging.getLogger("forecast")

CRISIS_MARGIN = 0.5
LETHAL_SHARE = 0.5            # a round expected to cost this share of the lives left is a crisis too
REVERSE_SUFFIX = " reverse"   # map models of Reverse games are keyed "<map> reverse"


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
        x, y in screen fractions; the hero is left out), or None."""
        from . import dps_model as D
        from . import towers as T
        placed = []
        for p in towers:
            if p.kind == "hero" or p.kind not in T.TOWERS:
                continue
            x, z, _ = self.track.frac_to_world(p.x, p.y)
            placed.append(D.Placed(p.tid, p.kind, tuple(p.tiers), x, z))
        return D.stations_for(placed, self.track, self.sight) if placed else None

    def worst(self, towers, rounds, iterations=9):
        """(lowest margin, its round) over `rounds` for `towers`, or None.
        The defence is built once and rated round by round (~70 ms each;
        fewer `iterations` of the margin search are quicker and coarser)."""
        if not rounds:
            return None
        try:
            if not self._ready():
                return None
            from . import dps_model as D
            st = self.stations(towers)
            if not st:
                return None
            return min((D.round_margin(st, self.mode, r, self.track, iterations=iterations), r) for r in rounds)
        except Exception:   # a forecast must never cost a game
            log.exception("round forecast failed - off for the rest of this game")
            self.off = True
            return None

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
            st = self.stations(towers)
            if not st:
                return None
            lost = {r: D.simulate_round(st, self.mode, r, self.track, strength=strength).lives_lost
                    for r in rounds}
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
