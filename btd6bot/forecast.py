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

Line of sight is not passed to the model here (it rates towers behind
walls a little high); any failure turns the forecast off for the game.
"""
from __future__ import annotations

import logging

log = logging.getLogger("forecast")

CRISIS_MARGIN = 0.5
REVERSE_SUFFIX = " reverse"   # map models of Reverse games are keyed "<map> reverse"


class RoundForecast:
    def __init__(self, map_key, mode):
        reverse = bool(map_key) and map_key.endswith(REVERSE_SUFFIX)
        self.map_name = map_key[:-len(REVERSE_SUFFIX)] if reverse else map_key
        self.reverse = reverse
        self.mode = mode or "medium"
        self.track = None
        self.off = not map_key

    def margin(self, towers, rnd):
        """The model's margin of round `rnd` for `towers` (objects with tid,
        kind, tiers, x, y in screen fractions; the hero is left out), or
        None when there is no answer."""
        if self.off or rnd is None:
            return None
        try:
            from . import dps_model as D
            from . import towers as T
            if self.track is None:
                if not D.available():
                    self.off = True
                    return None
                self.track = D.Track(self.map_name, reverse=self.reverse)
            placed = []
            for p in towers:
                if p.kind == "hero" or p.kind not in T.TOWERS:
                    continue
                x, z, _ = self.track.frac_to_world(p.x, p.y)
                placed.append(D.Placed(p.tid, p.kind, tuple(p.tiers), x, z))
            if not placed:
                return None
            return D.round_margin(D.stations_for(placed, self.track), self.mode, rnd, self.track)
        except Exception:   # a forecast must never cost a game
            log.exception("round forecast failed - off for the rest of this game")
            self.off = True
            return None

    @staticmethod
    def is_crisis(margin):
        return margin is not None and margin < CRISIS_MARGIN
