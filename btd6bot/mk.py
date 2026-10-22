"""Monkey Knowledge: spend new points automatically, best value first.

Calibrated live (1920x1200, v57.3). Main menu KNOWLEDGE -> six tree tiles ->
a tree of icon nodes (no names on the icons). Clicking a node opens a panel at
the bottom with its NAME, effect and an "ASSIGN +1" button; nodes that are not
available yet say "Needs <parent>" or "Requires N more point(s)".

The plan below is in priority order for a farming bot: Monkey Money first,
then tower XP. Each entry is verified by its on-screen name before a point is
spent, and nodes in Monkey Money-gated rows are not in the plan (never spends MM).
"""
import logging
import time

from .vision import norm

log = logging.getLogger("mk")

KNOWLEDGE_BUTTON = (0.868, 0.88)
TREES = {"primary": (0.222, 0.40), "military": (0.41, 0.40), "magic": (0.597, 0.40),
         "support": (0.785, 0.40), "heroes": (0.41, 0.73)}
BACK = (0.044, 0.055)
POINTS = (0.925, 0.115, 0.965, 0.165)
NAME = (0.25, 0.80, 0.75, 0.85)
ASSIGN = (0.804, 0.884)

# (tree, node position, expected name) - in buying order
PLAN = [
    ("magic", (0.735, 0.175), "Magic Tricks"),
    ("magic", (0.735, 0.338), "Speedy Brewing"),
    ("magic", (0.84, 0.338), "Mo' Monkey Money"),          # +10% Monkey Money per win
    ("support", (0.296, 0.175), "Flat Pack Buildings"),
    ("support", (0.502, 0.175), "One More Spike"),
    ("support", (0.342, 0.338), "More Valuable Bananas"),
    ("support", (0.711, 0.498), "Monkey Education"),        # +8% tower and hero XP
]


class Knowledge:
    def __init__(self, screen, inp, menus, account):
        self.s, self.inp, self.menus, self.account = screen, inp, menus, account

    def _read(self, region):
        return " ".join(w.text for w in self.menus.v.read(region))

    def _points(self):
        from .hud import parse_int
        return parse_int(self._read(POINTS))

    def spend(self):
        """From the main menu: assign available points following PLAN."""
        todo = [e for e in PLAN if e[2] not in self.account.mk_unlocked]
        if not todo or self.menus.identify() != "main_menu":
            return []
        self.inp.click(*KNOWLEDGE_BUTTON)
        time.sleep(1.5)
        bought, tree_open = [], None
        try:
            for tree, pos, name in todo:
                pts = self._points()
                if not pts:
                    break
                if tree_open != tree:
                    if tree_open:
                        self.inp.click(*BACK)
                        time.sleep(1.2)
                    self.inp.click(*TREES[tree])
                    time.sleep(1.5)
                    tree_open = tree
                self.inp.click(*pos)
                time.sleep(0.9)
                shown = self._read(NAME)
                if norm(name)[:8] not in norm(shown):
                    log.warning("expected %r at %s, panel shows %r - skipping", name, pos, shown)
                    continue
                panel = norm(self._read((0.0, 0.78, 1.0, 1.0)))
                if "needs" in panel or "requires" in panel:
                    continue  # prerequisites not met yet
                if "assign" not in panel:
                    self.account.mk_unlocked.append(name)  # already learned
                    continue
                self.inp.click(*ASSIGN)
                time.sleep(1.0)
                after = self._points()
                if after is not None and after < pts:
                    self.account.mk_unlocked.append(name)
                    bought.append(name)
                    log.info("Monkey Knowledge learned: %s", name)
        finally:
            for _ in range(3):
                if self.menus.identify() == "main_menu":
                    break
                self.inp.click(*BACK)
                time.sleep(1.0)
            self.account.save()
        return bought
