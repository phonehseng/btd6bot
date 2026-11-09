"""Towers carried around by moving ground (Geared's gears, Sanctuary's platforms).

On Geared both gears turn after every round - the big one by 45 degrees,
the small one by 108 (`data/map_geometry/geared.json`, RotateAreaAction) -
and every tower standing on a gear turns with it. The bot remembers each
tower as the screen spot where it clicked to place it (`game.Placed.x/y`),
and `Game.select` clicks that spot again to open the upgrade panel. After
one turn of the gear the spot is empty ground, so the selection failed,
the tower was "not on the map; forgotten" and bought again (Geared Medium,
2026-11-03: ac1, ac2, ac3 and sniper3).

CarriedTowers follows the gears instead: whenever the round counter moves
on, it turns the remembered spot of every tower on a gear by the same angle
about the same pivot, so the next click lands on the tower again.

Everything comes from the game's own map data (pivot, angle, which rounds
the event fires after); nothing here is specific to Geared except that it is
the only standard map with RotateAreaAction today.

Sanctuary's six platforms (MovingPlatformAction) move when a round STARTS,
not when the HUD round changes: follow_platforms() is told the last round
started (Executor._pose_round) and moves every tower on a platform from the
platform's old layout to its new one (mapgeom.move_with_platform). Without
it the bot clicked the water where a sniper had stood, forgot the tower
after two failed selections and bought it again (2026-11-05 round 33; on
2026-11-09 s4 at round 18).
"""
import logging
from types import SimpleNamespace

import cv2
import numpy as np

from . import mapgeom

log = logging.getLogger("carried")


class _Rotor:
    """One area that turns about a fixed pivot by a fixed angle at round ends."""

    def __init__(self, area, step, first, every):
        self.id = area["id"]
        self.name = area.get("name", str(self.id))
        self.polygons = area["polygons"]          # outline first, holes after (as in the game)
        self.step = step                          # degrees per turn (Unity: + is clockwise from above)
        self.pivot = tuple((area.get("pivot") or area.get("origin") or [0.0, 0.0])[:2])
        # The area's height lifts it on screen (Projection.to_frac); a tower
        # on it is drawn as high as the ground it stands on.
        heights = [pt[2] for poly in self.polygons for pt in poly if len(pt) > 2]
        self.height = float(np.mean(heights)) if heights else 0.0
        self.first = first                        # first HUD round that shows the first turn
        self.every = max(1, every)                # rounds between turns
        self.turns = 0                            # turns made so far this game

    def pose(self, turns):
        """mapgeom pose (dx, dz, degrees, cx, cz) after `turns` turns."""
        return (0.0, 0.0, turns * self.step, *self.pivot)

    def contains(self, x, z):
        """True when world point (x, z) lies on the area as it stands now
        (inside its turned outline and outside every hole)."""
        polys = mapgeom._pose_polygons(self.polygons, self.pose(self.turns))
        for i, poly in enumerate(polys):
            pts = np.asarray([p[:2] for p in poly], np.float32)
            if len(pts) < 3:
                continue
            inside = cv2.pointPolygonTest(pts, (float(x), float(z)), False) >= 0
            if i == 0 and not inside:
                return False
            if i > 0 and inside:
                return False
        return True

    def turns_between(self, old_round, new_round):
        """How many turns happen while the HUD round goes from old_round to
        new_round: one for each round n in (old, new] that is a turning
        round (n >= first, every `every` rounds from there)."""
        return sum(1 for n in range(old_round + 1, new_round + 1)
                   if n >= self.first and (n - self.first) % self.every == 0)


def _every_nth(event):
    """Rounds between firings of a round-triggered event (1 = every round)."""
    ns = [t.get("everyNthRound") or 0 for t in event.get("triggers", [])
          if t.get("type") in ("StartRoundTrigger", "AfterRoundTrigger")]
    return min((n for n in ns if n > 0), default=1)


class CarriedTowers:
    """Keeps the remembered click spots of towers on rotating ground in step
    with the ground. Build it with for_map(); None means the map has no
    rotating ground and there is nothing to follow."""

    def __init__(self, rotors, proj, name="", platforms=None):
        self.rotors = rotors
        self.proj = proj
        self.name = name
        self.riders = {}    # tower id -> (id() of its Placed object, rotor or None)
        # moving platforms: a stand-in model for mapgeom (name, playfield),
        # or None on maps without them
        self.platforms = platforms
        self.pose_round = None      # the layout the remembered platform spots are in
        self.platform_riders = {}   # tower id -> (id() of its Placed object, (platform, height) or None)

    @classmethod
    def for_map(cls, name, playfield, aspect=1920 / 1200):
        geom = mapgeom.load(name) if name else None
        if not geom:
            return None
        dyn = mapgeom.dynamics(geom)
        areas = {a["id"]: a for a in geom.get("areas", []) if "id" in a}
        events = {e["id"]: e for e in (geom.get("mechanics") or {}).get("events", []) if "id" in e}
        rotors = []
        for mover in dyn.movers:
            if mover["type"] != "RotateAreaAction" or mover["first_round"] is None:
                continue   # time-based or platform moves: not followed (see module docstring)
            event = events.get(mover.get("event"), {})
            step = mover["poses"][0][2]   # the first pose is one turn
            for aid in mover["areas"]:
                if areas[aid]["type"] in mapgeom.SOLID_TYPES:
                    continue   # nothing stands on a turning obstacle
                rotors.append(_Rotor(areas[aid], step, mover["first_round"], _every_nth(event)))
        platforms = None
        if any(m["type"] == "MovingPlatformAction" and m.get("seq") for m in dyn.movers):
            platforms = SimpleNamespace(name=name, playfield=playfield)
            log.info("%s: following towers on the moving platforms", name)
        if not rotors and platforms is None:
            return None
        if rotors:
            log.info("%s: following towers on %s", name,
                     ", ".join(f"{r.name} ({r.step:g} deg after rounds from {r.first - 1})" for r in rotors))
        return cls(rotors, mapgeom.Projection(playfield, aspect), name, platforms)

    # -- screen <-> world -----------------------------------------------------------
    def _world(self, fx, fy, height):
        """Screen fractions -> world (x, z) of a point standing `height` up."""
        p = self.proj
        return (fx - p.cx) / p.ux, (p.cy - fy) / p.uy - mapgeom.HEIGHT_FACTOR * height

    def _rotor_at(self, fx, fy):
        """The rotor a tower clicked at (fx, fy) stands on, or None. Where
        two overlap (Geared's small gear lies on the big one) the higher area
        is the ground, as in the game."""
        for r in sorted(self.rotors, key=lambda r: -r.height):
            if r.contains(*self._world(fx, fy, r.height)):
                return r
        return None

    # -- the game ---------------------------------------------------------------------
    def _adopt(self, towers):
        """Note which rotor each newly placed tower stands on. A tower id
        placed again (forgotten and re-bought) is a new Placed object and
        is looked at again."""
        for tid, p in towers.items():
            known = self.riders.get(tid)
            if known is None or known[0] != id(p):
                self.riders[tid] = (id(p), self._rotor_at(p.x, p.y))

    def round_advanced(self, old_round, new_round, towers):
        """The HUD round went from old_round to new_round: turn the rotors
        that turned meanwhile and move the towers on them. Towers placed
        since the last call are first matched to the ground they were placed
        on (before this turn). Returns the ids of the towers moved."""
        if old_round is None or new_round is None or new_round <= old_round:
            return []
        self._adopt(towers)
        moved = []
        for r in self.rotors:
            k = r.turns_between(old_round, new_round)
            if not k:
                continue
            r.turns += k
            for tid, (_, rotor) in self.riders.items():
                p = towers.get(tid)
                if rotor is not r or p is None:
                    continue
                x, z = self._world(p.x, p.y, r.height)
                (nx, nz), = mapgeom._pose_points(np.array([[x, z]], float), r.pose(k))
                fx, fy = self.proj.to_frac([[nx, nz, r.height]])[0]
                p.x, p.y = float(fx), float(fy)
                moved.append(tid)
        if moved:
            log.info("round %d: %s carried round by the gears", new_round, ", ".join(moved))
        return moved

    def follow_platforms(self, pose_round, towers):
        """The platforms stand as in round pose_round (the last round
        started): move the remembered spot of every tower on one from the
        layout it was in to this one. Towers placed since the last call are
        first matched to the platform under them in that earlier layout
        (they were placed then). Call it once per pass of the match loop;
        it only acts when the layout changes. Returns the ids moved."""
        if self.platforms is None or pose_round is None:
            return []
        before = self.pose_round if self.pose_round is not None else pose_round
        for tid, p in towers.items():
            known = self.platform_riders.get(tid)
            if known is None or known[0] != id(p):
                plat, height = mapgeom.platform_under(self.platforms, p.x, p.y, before)
                self.platform_riders[tid] = (id(p), (plat, height) if plat is not None else None)
        self.pose_round = pose_round
        if before == pose_round:
            return []
        moved = []
        for tid, (_, ride) in self.platform_riders.items():
            p = towers.get(tid)
            if ride is None or p is None:
                continue
            fx, fy = mapgeom.move_with_platform(self.platforms, ride[0], ride[1], p.x, p.y, before, pose_round)
            if abs(fx - p.x) > 1e-4 or abs(fy - p.y) > 1e-4:
                p.x, p.y = fx, fy
                moved.append(tid)
        if moved:
            log.info("platforms now as in round %d: %s carried along", pose_round, ", ".join(moved))
        return moved
