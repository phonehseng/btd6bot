"""The glass HUD: a few small see-through widgets instead of a full-screen
window (what they show: tools/glass_scene.py; where the facts come from:
tools/hud_data.py).

Started by tools/overlay.py (itself started by run_forever.ps1), which
holds the single-instance lock and falls back to the big HUD, then to the
thin strip, when this fails to start.

Each widget is a window of its own whose pixels are an RGBA image pushed
with UpdateLayeredWindow (per-pixel alpha, premultiplied BGRA): the glass is
truly see-through, there is no colour key and nothing is drawn where there
is no widget. Every window is

  * WS_EX_LAYERED | WS_EX_TRANSPARENT: clicks and keys reach the game, and
    WindowFromPoint skips it (the bot's "another window covers the game"
    check still finds the game);
  * WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW: it never takes focus and has no
    taskbar button;
  * topmost, re-asserted every TOPMOST_S seconds;
  * WDA_EXCLUDEFROMCAPTURE: left out of screen captures and recordings, so
    the bot's OCR and the recorder never see it.

The windows are plain Win32 "STATIC" windows made with ctypes (no Tk window
that could flash up before its styles are set); Tk only runs the loop and
the STOP / GO / OFF buttons (tools/hud_controls.py), right of the status
pill as before.

Cheap on purpose, as the bot and BTD6 share the laptop: the loop ticks
TICK_HZ times a second, the bot's files are polled every POLL_S seconds,
and a widget is drawn and pushed again only when its key changes - the
pill a few times a second for its heartbeat, the cards when what they say
changes, the ghosts when the plan or the game window moves, the field
layer (what the bot sees of the map, over the whole play field) when the
map, the round's path phase, the learned model's file or the game window
changes - never per frame. The field's window is the lowest of the
widgets': the cards and ghosts stay on top of it. A HUD_NO_FIELD file in
the repo root hides it (glass_field.field_wanted), polled like
HUD_NO_THOUGHTS.
"""
import ctypes
import os
import sys
import time
import traceback
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hud_controls as C            # noqa: E402
import hud_data                     # noqa: E402
import glass_scene as G             # noqa: E402
import glass_field as F             # noqa: E402

TICK_HZ = 8              # loop ticks a second (the pill's heartbeat runs at glass_scene.PILL_FPS)
POLL_S = 0.5             # seconds between reads of the bot's files
RECT_S = 1.0             # seconds between looks at where the game window is
TOPMOST_S = 0.7          # seconds between re-asserting topmost (as the old strip did)
ERROR_EVERY_S = 60       # at most one error note a minute
ERROR_FILE = hud_data.ROOT / "logs" / "hud_error.txt"
THOUGHTS_OFF = hud_data.ROOT / "HUD_NO_THOUGHTS"     # this file hides the thoughts card ...
THOUGHTS_ENV = "BTD6BOT_HUD_THOUGHTS"                # ... as does this variable set to "off"
FIELD = "field"          # the field layer's widget (glass_field.py): its window is kept under the others

# -- Win32 ------------------------------------------------------------------------------------
# Own WinDLL instances, so the argument types set here never change the
# shared ctypes.windll functions other HUD code calls.
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WS_POPUP = 0x80000000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
ULW_ALPHA = 0x2
AC_SRC_OVER, AC_SRC_ALPHA = 0x0, 0x1
BI_RGB, DIB_RGB_COLORS = 0, 0


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def _sig(fn, restype, *argtypes):
    fn.restype, fn.argtypes = restype, argtypes


_sig(_user32.CreateWindowExW, wintypes.HWND, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
     ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE,
     wintypes.LPVOID)
_sig(_user32.DestroyWindow, wintypes.BOOL, wintypes.HWND)
_sig(_user32.ShowWindow, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
_sig(_user32.SetWindowPos, wintypes.BOOL, wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
     ctypes.c_int, wintypes.UINT)
_sig(_user32.SetWindowDisplayAffinity, wintypes.BOOL, wintypes.HWND, wintypes.DWORD)
_sig(_user32.GetDC, wintypes.HDC, wintypes.HWND)
_sig(_user32.ReleaseDC, ctypes.c_int, wintypes.HWND, wintypes.HDC)
_sig(_user32.UpdateLayeredWindow, wintypes.BOOL, wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
     ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
     ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD)
_sig(_gdi32.CreateCompatibleDC, wintypes.HDC, wintypes.HDC)
_sig(_gdi32.DeleteDC, wintypes.BOOL, wintypes.HDC)
_sig(_gdi32.CreateDIBSection, wintypes.HBITMAP, wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
     ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
_sig(_gdi32.SelectObject, wintypes.HGDIOBJ, wintypes.HDC, wintypes.HGDIOBJ)
_sig(_gdi32.DeleteObject, wintypes.BOOL, wintypes.HGDIOBJ)
_sig(_kernel32.GetModuleHandleW, wintypes.HMODULE, wintypes.LPCWSTR)


def premultiplied_bgra(image):
    """An RGBA Pillow image as the bytes UpdateLayeredWindow wants: each
    pixel B, G, R, A with the colours already multiplied by alpha."""
    return image.convert("RGBa").tobytes("raw", "BGRa")


class LayeredWindow:
    """One widget's window: click-through, never focused, topmost, left out
    of captures; its pixels are whatever RGBA image show() was given last."""

    STYLE = C.CLICK_THROUGH        # WS_EX_LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE | TOPMOST

    def __init__(self, name):
        self.name = name
        self.hwnd = _user32.CreateWindowExW(self.STYLE, "STATIC", f"BTD6 bot HUD - {name}", WS_POPUP,
                                            0, 0, 1, 1, None, None, _kernel32.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.capture_excluded = bool(_user32.SetWindowDisplayAffinity(self.hwnd, C.WDA_EXCLUDEFROMCAPTURE))
        self.visible = False

    def push(self, image, x, y):
        """Put `image` (RGBA) on the screen with its top-left corner at (x, y)."""
        w, h = image.size
        data = premultiplied_bgra(image)
        screen = _user32.GetDC(None)
        mem = _gdi32.CreateCompatibleDC(screen)
        header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, BI_RGB, 0, 0, 0, 0, 0)  # top-down
        bits = ctypes.c_void_p()
        bitmap = _gdi32.CreateDIBSection(mem, ctypes.byref(header), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        try:
            if not bitmap:
                raise ctypes.WinError(ctypes.get_last_error())
            ctypes.memmove(bits, data, len(data))
            old = _gdi32.SelectObject(mem, bitmap)
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            ok = _user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(wintypes.POINT(x, y)),
                                             ctypes.byref(wintypes.SIZE(w, h)), mem,
                                             ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA)
            _gdi32.SelectObject(mem, old)
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if bitmap:
                _gdi32.DeleteObject(bitmap)
            _gdi32.DeleteDC(mem)
            _user32.ReleaseDC(None, screen)

    def show(self, picture):
        """Show a glass_scene.Picture (pushed first, so the window never
        appears with stale pixels)."""
        self.push(picture.image, picture.x, picture.y)
        if not self.visible:
            _user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.visible = True

    def hide(self):
        if self.visible:
            _user32.ShowWindow(self.hwnd, SW_HIDE)
            self.visible = False

    def keep_on_top(self):
        if self.visible:
            _user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def close(self):
        if self.hwnd:
            _user32.DestroyWindow(self.hwnd)
            self.hwnd = None


def thoughts_wanted():
    """The owner's switch for the thoughts card (HUD_NO_THOUGHTS file or BTD6BOT_HUD_THOUGHTS=off)."""
    return not THOUGHTS_OFF.exists() and os.environ.get(THOUGHTS_ENV, "").strip().lower() not in ("off", "0", "no")


class GlassHud:
    """The widgets' windows and the loop that keeps them current.
    `make_window(name)` builds a widget's window (tests pass a fake)."""

    def __init__(self, root, collector=None, clock=time.time, size=None, make_window=LayeredWindow):
        self.root = root
        self.clock = clock
        sw, sh = size or (root.winfo_screenwidth(), root.winfo_screenheight())
        self.size = (sw, sh)
        self.collector = collector or hud_data.Collector()
        self.scene = G.GlassScene(sw, sh, thoughts=thoughts_wanted(),
                                  field=F.FieldLayer(Path(self.collector.root) / "data" / "maps"),
                                  show_field=F.field_wanted(self.collector.root))
        self.make_window = make_window
        self.windows = {}           # widget name -> its window, made when first shown
        self.keys = {}              # widget name -> the key of what its window shows
        self.snap = None
        self.game_rect = None
        self.buttons = None
        self._t_poll = self._t_rect = self._t_top = self._t_error = -1e9

    def make_buttons(self):
        """The STOP / GO / OFF panel right of the pill, from the screen's top
        to the pill's bottom."""
        x0, _y0, _x1, y1 = self.scene.lay.buttons
        self.buttons = C.ButtonPanel(self.root, x0, y1)
        C.exclude_from_capture(self.buttons.win)

    def window(self, name):
        if name not in self.windows:
            self.windows[name] = self.make_window(name)
        return self.windows[name]

    def frame(self):
        """One tick: the files and the game window are looked at when their
        interval has passed; a widget is drawn again only when its key changed."""
        now = self.clock()
        if now - self._t_poll >= POLL_S or self.snap is None:
            self._t_poll = now
            self.snap = self.collector.poll()
            self.scene.show_thoughts = thoughts_wanted()
            self.scene.show_field = F.field_wanted(self.collector.root)
        if now - self._t_rect >= RECT_S:
            self._t_rect = now
            self.game_rect = C.game_client_rect()
        for name, key, build in self.scene.widgets(self.snap, now, self.game_rect):
            if self.keys.get(name) == key:
                continue
            picture = build()
            if picture is None:
                if name in self.windows:
                    self.windows[name].hide()
            else:
                self.window(name).show(picture)
                if name == FIELD:
                    self._t_top = -1e9          # just shown on top of everything: put the others back above it
            self.keys[name] = key
        if now - self._t_top >= TOPMOST_S:
            self._t_top = now
            for name in self.stacking():
                self.windows[name].keep_on_top()
            if self.buttons:
                self.buttons.refresh()

    def stacking(self):
        """The widgets' windows from the bottom up: the field layer first,
        so each re-assertion of topmost leaves every other widget above it."""
        return sorted(self.windows, key=lambda name: name != FIELD)

    def note_error(self):
        now = self.clock()
        if now - self._t_error < ERROR_EVERY_S:
            return
        self._t_error = now
        try:
            ERROR_FILE.parent.mkdir(exist_ok=True)
            ERROR_FILE.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} glass HUD frame failed\n"
                                  f"{traceback.format_exc()}", encoding="utf-8")
        except OSError:
            pass

    def close(self):
        for win in self.windows.values():
            win.close()
        self.windows.clear()

    def loop(self):
        if (C.ROOT / "STOP").exists():
            self.close()
            self.root.destroy()
            return
        try:
            self.frame()
        except Exception:      # one bad frame (a file read mid-write, an odd value) must not end the HUD
            self.keys.clear()  # draw everything again next tick
            self.note_error()
        self.root.after(1000 // TICK_HZ, self.loop)


def run():
    """Build the glass HUD and run it until the STOP file (overlay.py holds
    the lock). Errors while building are raised, every window gone, so the
    caller can fall back to another HUD."""
    import tkinter as tk
    was_in_front = C.user32.GetForegroundWindow()
    root = tk.Tk()
    root.withdraw()                 # Tk's own window is never shown: only the widgets and the buttons
    hud = None
    try:
        hud = GlassHud(root)
        hud.make_buttons()
        hud.frame()
    except Exception:
        if hud:
            hud.close()
        root.destroy()
        raise
    C.hand_focus_back(root, was_in_front)
    root.after(1000 // TICK_HZ, hud.loop)
    root.mainloop()
