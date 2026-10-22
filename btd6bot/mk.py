"""Monkey Knowledge: spend new points automatically, best value first.

Calibrated live (1920x1200, v57.3). Main menu KNOWLEDGE -> six tree tiles ->
a tree of icon nodes (no names on the icons). Clicking a node opens a panel at
the bottom with its NAME, effect and a button: "ASSIGN +1" when a point can be
spent on it, an "Enable" checkbox when it is already learned; nodes that are
not available yet say "Needs <parent>" or "Requires N more point(s)".

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
# The node panel, right of its icon. The tree's own row labels ("Requires 8
# points", "Requires 14 points") sit at the left edge and just below the
# panel, so the region must not reach them: reading them made every learned
# node look locked, and the bot re-checked them every session.
PANEL = (0.17, 0.81, 0.92, 0.96)
ASSIGN = (0.804, 0.884)       # "ASSIGN +1"; the "Enable" checkbox sits in the same place
POLL = 0.2                    # seconds between screen reads while waiting for a change

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

    def _points(self, timeout=0.0):
        """Unspent points shown at the top right; waits up to `timeout` s for
        the counter to appear (the screen fades in)."""
        from .hud import parse_int
        end = time.time() + timeout
        while True:
            pts = parse_int(self._read(POINTS))
            if pts is not None or time.time() >= end:
                return pts
            time.sleep(POLL)

    def _panel(self, name, want=None, timeout=2.0):
        """Wait until the node panel names `name` (and, if given, contains the
        word `want`); returns its normalised text, or None on timeout. Waiting
        for the change instead of sleeping a fixed time keeps each node to
        about half a second."""
        end = time.time() + timeout
        while True:
            text = norm(self._read(PANEL))
            if norm(name)[:8] in text and (want is None or want in text):
                return text
            if time.time() >= end:
                return None
            time.sleep(POLL)

    def _learned(self, name):
        if name not in self.account.mk_unlocked:
            self.account.mk_unlocked.append(name)

    def spend(self):
        """From the main menu: assign available points following PLAN.

        Fast paths: nothing is opened when every PLAN node is already known
        to be learned, and the trees are not visited when there are no
        unspent points (the counter is read on the first screen)."""
        todo = [e for e in PLAN if e[2] not in self.account.mk_unlocked]
        if not todo or self.menus.identify() != "main_menu":
            return []
        self.inp.click(*KNOWLEDGE_BUTTON)
        bought, tree_open = [], None
        try:
            pts = self._points(timeout=3.0)
            if not pts:
                return []      # nothing to spend
            for tree, pos, name in todo:
                if pts <= 0:
                    break
                if tree_open != tree:
                    if tree_open:
                        self.inp.click(*BACK)
                        time.sleep(1.0)
                    self.inp.click(*TREES[tree])
                    time.sleep(1.2)   # the tree slides in
                    tree_open = tree
                self.inp.click(*pos)
                panel = self._panel(name)
                if panel is None:
                    log.warning("expected %r at %s, panel shows %r - skipping", name, pos, self._read(PANEL))
                    continue
                if "enable" in panel:
                    self._learned(name)          # learned before (by hand or an earlier run)
                    continue
                if "assign" not in panel:
                    continue                     # "Needs ..." / "Requires ...": not available yet
                self.inp.click(*ASSIGN)
                # learned: the button turns into the "Enable" checkbox (or the
                # point counter drops, if the panel could not be read)
                after = self._panel(name, want="enable")
                left = self._points() if after is None else None
                if after is not None or (left is not None and left < pts):
                    self._learned(name)
                    bought.append(name)
                    pts -= 1
                    log.info("Monkey Knowledge learned: %s", name)
        finally:
            for _ in range(3):
                if self.menus.identify() == "main_menu":
                    break
                self.inp.click(*BACK)
                time.sleep(0.8)
            self.account.save()
        return bought
