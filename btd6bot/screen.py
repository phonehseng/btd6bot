"""Locating the BTD6 window and capturing its client area."""
import ctypes
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

    def _pid(self):
        return win32process.GetWindowThreadProcessId(self.hwnd)[1]

    def focus(self):
        """Bring BTD6 to the front without sending any keystrokes.

        Never synthesises keys to get focus: a stray key (Esc especially) landing
        in another window can have real consequences.
        """
        if self.is_foreground():
            return True
        if win32gui.IsIconic(self.hwnd):
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
        self._move_aside_foreground()
        # Joining the foreground thread's input queue lifts the focus-steal lock.
        fg = win32gui.GetForegroundWindow()
        me = win32api.GetCurrentThreadId()
        other = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
        attached = False
        try:
            if other and other != me:
                attached = bool(ctypes.windll.user32.AttachThreadInput(me, other, True))
            win32gui.BringWindowToTop(self.hwnd)
            win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            pass
        finally:
            if attached:
                ctypes.windll.user32.AttachThreadInput(me, other, False)
        time.sleep(0.3)
        self.refresh()
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

    # Windows the bot may minimize when they cover the game (title of the
    # top-level window). The Claude desktop app restores its window over the
    # game's right side when a message arrives; twice on 2026-10-22 the bot
    # then waited for minutes, refusing to click under it.
    MINIMIZE_WHEN_COVERING = ("Claude",)

    USER_IDLE_S = 20.0   # no keyboard/mouse input this long: nobody is using the PC

    @staticmethod
    def user_idle_s():
        """Seconds since the last keyboard or mouse input (GetLastInputInfo)."""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0

    def _move_aside_foreground(self):
        """The Claude app took the foreground (a message arrived, 2026-10-22
        20:53: the bot left a game in progress after a minute of waiting):
        minimize it - only while nobody is using the PC, so a person typing
        there is never interrupted."""
        fg = win32gui.GetForegroundWindow()
        if not fg or fg == self.hwnd or win32gui.GetWindowText(fg) not in self.MINIMIZE_WHEN_COVERING:
            return
        if self.user_idle_s() >= self.USER_IDLE_S:
            win32gui.ShowWindow(fg, win32con.SW_MINIMIZE)

    def clear_point(self, fx, fy):
        """If a known app window covers the game at (fx, fy), minimize it.
        Returns its title when it did, else None (other windows are left
        alone: the bot waits for them)."""
        x, y = self.to_px(fx, fy)
        h = win32gui.WindowFromPoint((x, y))
        top = win32gui.GetAncestor(h, 2) if h else 0     # GA_ROOT: the top-level window
        title = win32gui.GetWindowText(top) if top else ""
        if top and top != self.hwnd and title in self.MINIMIZE_WHEN_COVERING:
            win32gui.ShowWindow(top, win32con.SW_MINIMIZE)
            return title
        return None

    # -- capture ----------------------------------------------------------
    def grab(self, region=None):
        """BGR image of the client area, or of region=(fx0, fy0, fx1, fy1).

        Uses PrintWindow so overlapping windows do not end up in the image;
        falls back to a screen grab if the game returns a black frame.
        """
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
