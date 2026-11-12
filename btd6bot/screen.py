"""Locating the BTD6 window and capturing its client area."""
import ctypes
import functools
import time

import mss
import numpy as np
import win32api
import win32con
import win32gui
import win32process
import win32ui

try:  # physical pixels, not DPI-scaled ones
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except OSError:
    pass

WINDOW_TITLE = "BloonsTD6"


class GameNotFound(RuntimeError):
    pass


class Screen:
    def __init__(self, title=WINDOW_TITLE):
        self.title = title
        self._sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        self.hwnd = None
        self.refresh()

    # -- window -----------------------------------------------------------
    def refresh(self):
        self.hwnd = win32gui.FindWindow(None, self.title)
        if not self.hwnd:
            raise GameNotFound(f"window '{self.title}' not found - is BTD6 running?")
        left, top, right, bottom = win32gui.GetClientRect(self.hwnd)
        x0, y0 = win32gui.ClientToScreen(self.hwnd, (left, top))
        self.left, self.top = x0, y0
        self.width, self.height = right - left, bottom - top

    def is_foreground(self):
        fg = win32gui.GetForegroundWindow()
        if not fg:
            return False
        if fg == self.hwnd:
            return True
        # Unity can own more than one top-level window; compare processes.
        return win32process.GetWindowThreadProcessId(fg)[1] == self._pid()

    # Points of the client area sampled for a window lying over the game
    # (fractions of its width and height), and how many must be covered.
    OBSCURED_GRID = (0.15, 0.5, 0.85)
    OBSCURED_MIN_POINTS = 2

    def obscured_by(self):
        """The title of a window from another program that lies over the game,
        or None when the game is visible.

        BTD6 can be the foreground window while another program's window sits
        on top of it (an always-on-top app window). The bot then plays blind
        on that part of the map: Luminous Cove CHIMPS (2026-11-12 16:04,
        loss case 20261112_160448) was lost at round 8 with the Claude app's
        window over the right third of the game - is_foreground() was True.

        Windows of python processes are not counted: the bot's own HUD
        windows lie over the game on purpose (click-through overlays)."""
        try:
            own = self._pid()
            covered = []
            for fy in self.OBSCURED_GRID:
                for fx in self.OBSCURED_GRID:
                    hwnd = win32gui.WindowFromPoint(self.to_px(fx, fy))
                    if not hwnd:
                        continue
                    root = win32gui.GetAncestor(hwnd, 2)        # GA_ROOT
                    pid = win32process.GetWindowThreadProcessId(root)[1]
                    if pid == own or _is_python(pid):
                        continue
                    covered.append(root)
            if len(covered) < self.OBSCURED_MIN_POINTS:
                return None
            return win32gui.GetWindowText(covered[0]) or "another window"
        except Exception:
            return None          # never pause on a failed check

    def _pid(self):
        return win32process.GetWindowThreadProcessId(self.hwnd)[1]

    def focus(self):
        """True when BTD6 is the foreground window.

        The bot never brings the game to the front itself (owner's rule,
        2026-10-23): the person at the PC decides which window is in front,
        and the bot pauses until they put the game back.
        """
        return self.is_foreground()

    # -- coordinates ------------------------------------------------------
    def to_px(self, fx, fy):
        """Fraction of client area -> absolute screen pixel."""
        return int(self.left + fx * self.width), int(self.top + fy * self.height)

    def to_frac(self, px, py):
        """Pixel inside a grabbed frame -> fraction of client area."""
        return px / self.width, py / self.height

    def owns_point(self, fx, fy):
        """True if the on-screen pixel at (fx, fy) belongs to the game window.

        Always-on-top windows (overlays, notifications, chat panels) can cover the
        game; a click there would land in that other app instead.
        """
        x, y = self.to_px(fx, fy)
        h = win32gui.WindowFromPoint((x, y))
        if not h:
            return False
        return h == self.hwnd or win32process.GetWindowThreadProcessId(h)[1] == self._pid()

    # -- capture ----------------------------------------------------------
    def grab(self, region=None):
        """BGR image of the client area, or of region=(fx0, fy0, fx1, fy1).

        Uses PrintWindow so overlapping windows do not end up in the image;
        falls back to a screen grab if the game returns a black frame.
        """
        if not win32gui.IsWindow(self.hwnd):
            # the window was replaced: a freshly started game shows a splash
            # window with the same title first (2026-10-23: the bot kept
            # capturing the dead splash and read every screen as "unknown")
            self.refresh()
        img = self._grab_window()
        if img is None:
            img = self._grab_screen()
        if region:
            fx0, fy0, fx1, fy1 = region
            h, w = img.shape[:2]
            img = img[int(fy0 * h):int(fy1 * h), int(fx0 * w):int(fx1 * w)]
        return np.ascontiguousarray(img)

    def _grab_window(self):
        """The game window's own pixels (PrintWindow), or None - then grab()
        falls back to a screen grab. A failing GDI call must not end a game:
        on 2026-10-22, with the CPU at 100%, CreateCompatibleDC failed on a
        last round, and the cleanup itself then raised and skipped freeing
        the other handles."""
        w, h = self.width, self.height
        hdc = dc = mem = bmp = None
        try:
            hdc = win32gui.GetWindowDC(self.hwnd)
            dc = win32ui.CreateDCFromHandle(hdc)
            mem = dc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(dc, w, h)
            mem.SelectObject(bmp)
            # 3 = PW_CLIENTONLY | PW_RENDERFULLCONTENT (needed for DirectX surfaces)
            ok = ctypes.windll.user32.PrintWindow(self.hwnd, mem.GetSafeHdc(), 3)
            arr = np.frombuffer(bmp.GetBitmapBits(True), dtype=np.uint8).reshape(h, w, 4)
            img = arr[:, :, :3].copy()
        except Exception:
            return None
        finally:
            # every handle on its own: one that was never created must not
            # keep the others from being freed
            for free in (lambda: win32gui.DeleteObject(bmp.GetHandle()), lambda: mem.DeleteDC(),
                         lambda: dc.DeleteDC(), lambda: win32gui.ReleaseDC(self.hwnd, hdc)):
                try:
                    free()
                except Exception:
                    pass
        if not ok or img[::50, ::50].max() == 0:
            return None
        return img

    def _grab_screen(self):
        mon = {"left": self.left, "top": self.top, "width": self.width, "height": self.height}
        return np.asarray(self._sct.grab(mon))[:, :, :3]


@functools.lru_cache(maxsize=256)
def _is_python(pid):
    """Is process `pid` a Python interpreter (the bot, its HUD, its tools)?
    Cached: Input.guard asks before every input."""
    try:
        h = win32api.OpenProcess(0x1000, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION
        try:
            name = win32process.GetModuleFileNameEx(h, 0)
        finally:
            win32api.CloseHandle(h)
        return name.lower().endswith(("python.exe", "pythonw.exe"))
    except Exception:
        return False
