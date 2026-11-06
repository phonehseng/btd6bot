"""The big HUD: the whole screen as a see-through, click-through window
showing what the bot is thinking (what it shows: tools/hud_scene.py; where
the facts come from: tools/hud_data.py).

Started by tools/overlay.py (itself started by run_forever.ps1), which
holds the single-instance lock and falls back to the thin strip when this
fails to start or the owner switches it off (HUD_STRIP file).

The window covers the primary screen, topmost. Everything not drawn is in
its transparent colour key, so the game shows through; the whole window is
WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE (clicks and keys reach
the game, focus never leaves it, the bot's cover check sees the game) and
left out of screen captures - tools/hud_controls.py explains each. The
STOP / GO / OFF buttons keep their own small clickable window, right of
the status strip at the top, as before.

Cheap on purpose, as the bot and BTD6 share the laptop: FPS frames a
second, of which only the animation layer (a few dozen canvas items) is
redrawn each time; the bot's files are polled every POLL_S seconds and a
layer is rebuilt only when what it shows changed.
"""
import sys
import time
import tkinter as tk
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hud_controls as C            # noqa: E402
import hud_data                     # noqa: E402
import hud_scene as S               # noqa: E402

HUD_ALPHA = 0.9          # the whole window's opacity: panels stay readable, the game shows faintly through
FPS = 12                 # animation frames per second
POLL_S = 0.5             # seconds between reads of the bot's files
RECT_S = 1.0             # seconds between looks at where the game window is
TOPMOST_S = 0.7          # seconds between re-asserting topmost (as the old strip did)
ERROR_EVERY_S = 60       # at most one error note a minute
ERROR_FILE = hud_data.ROOT / "logs" / "hud_error.txt"


def draw(canvas, shapes, tag):
    """Create the shapes' canvas items under one tag (a layer)."""
    for s in shapes:
        getattr(canvas, "create_" + s.kind)(*s.coords, tags=(tag,), **s.opts)


class LayeredCanvas:
    """A canvas whose layers (hud_scene.LAYER_ORDER) are rebuilt only when
    their key changes."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.keys = {}

    def show(self, layers):
        changed = False
        for name, key, build in layers:
            if name in self.keys and self.keys[name] == key:
                continue
            self.canvas.delete(name)
            draw(self.canvas, build(), name)
            self.keys[name] = key
            changed = True
        if changed:            # a rebuilt layer lands on top: put them back in order
            for name in S.LAYER_ORDER:
                self.canvas.tag_raise(name)


class BigHud:
    def __init__(self, root, collector=None, clock=time.time):
        self.root = root
        self.clock = clock
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.size = (sw, sh)
        self.collector = collector or hud_data.Collector()
        self.scene = S.Scene(sw, sh)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=S.KEY)
        root.attributes("-transparentcolor", S.KEY)
        root.attributes("-alpha", HUD_ALPHA)
        root.geometry(f"{sw}x{sh}+0+0")
        self.canvas = tk.Canvas(root, width=sw, height=sh, bg=S.KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.layers = LayeredCanvas(self.canvas)
        self.snap = None
        self.game_rect = None
        self._t_poll = self._t_rect = self._t_top = self._t_error = -1e9
        self.buttons = None

    def make_windowed(self):
        """The Windows side: click-through, no focus, out of captures, and
        the button panel right of the status strip."""
        C.set_ex_style(self.root, C.CLICK_THROUGH)
        self.capture_excluded = C.exclude_from_capture(self.root)
        x0, _y0, x1, y1 = self.scene.lay.strip
        self.buttons = C.ButtonPanel(self.root, int(x1) + C.BUTTON_GAP, int(y1))
        C.exclude_from_capture(self.buttons.win)

    def frame(self):
        """One animation frame; the files and the game window are looked at
        only when their interval has passed."""
        now = self.clock()
        if now - self._t_poll >= POLL_S or self.snap is None:
            self._t_poll = now
            self.snap = self.collector.poll()
        if now - self._t_rect >= RECT_S:
            self._t_rect = now
            self.game_rect = C.game_client_rect()
        self.layers.show(self.scene.layers(self.snap, now, self.game_rect))
        if self.buttons and now - self._t_top >= TOPMOST_S:
            self._t_top = now
            self.root.attributes("-topmost", True)
            self.buttons.refresh()

    def note_error(self):
        now = self.clock()
        if now - self._t_error < ERROR_EVERY_S:
            return
        self._t_error = now
        try:
            ERROR_FILE.parent.mkdir(exist_ok=True)
            ERROR_FILE.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} big HUD frame failed\n"
                                  f"{traceback.format_exc()}", encoding="utf-8")
        except OSError:
            pass

    def loop(self):
        if (C.ROOT / "STOP").exists():
            self.root.destroy()
            return
        try:
            self.frame()
        except Exception:      # one bad frame (a file read mid-write, an odd value) must not end the HUD
            self.note_error()
        self.root.after(1000 // FPS, self.loop)


def run():
    """Build the big HUD and run it until the STOP file (overlay.py holds
    the lock). Errors while building are raised, the window gone, so the
    caller can fall back to the strip."""
    was_in_front = C.user32.GetForegroundWindow()
    root = tk.Tk()
    try:
        hud = BigHud(root)
        hud.make_windowed()
        hud.frame()
    except Exception:
        root.destroy()
        raise
    C.hand_focus_back(root, was_in_front)
    root.after(1000 // FPS, hud.loop)
    root.mainloop()
