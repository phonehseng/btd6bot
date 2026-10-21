"""Mouse/keyboard input via SendInput, guarded so it only ever reaches BTD6.

Every single event re-checks that BTD6 is the foreground window right before it
is sent. If focus moved elsewhere (another app, a notification, the Claude app)
the bot stops instead of typing into that window. F8 aborts the bot at any time.
"""
import time

import pydirectinput as pdi
import win32api
import win32con

pdi.PAUSE = 0.0
pdi.FAILSAFE = False

KILL_KEY = win32con.VK_F8


class FocusLost(RuntimeError):
    pass


class Aborted(RuntimeError):
    pass


def kill_requested():
    return bool(win32api.GetAsyncKeyState(KILL_KEY) & 0x8000)


class Input:
    def __init__(self, screen, delay=0.07):
        self.screen = screen
        self.delay = delay
        self._held_keys = []

    def guard(self):
        if kill_requested():
            self.release_all()
            raise Aborted("F8 pressed")
        if self.screen.is_foreground():
            return
        self.release_all()
        if not self.screen.focus():
            raise FocusLost("BTD6 is not the foreground window - refusing to send input")

    def release_all(self):
        for k in reversed(self._held_keys):
            pdi.keyUp(k)
        self._held_keys.clear()

    # -- mouse -----------------------------------------------------------
    def move(self, fx, fy):
        self.guard()
        x, y = self.screen.to_px(fx, fy)
        # Unity only registers hover/click if the cursor actually travels.
        win32api.SetCursorPos((x - 3, y - 3))
        time.sleep(0.03)
        win32api.SetCursorPos((x, y))
        time.sleep(self.delay)

    def guard_point(self, fx, fy):
        self.guard()
        if not self.screen.owns_point(fx, fy):
            raise FocusLost(f"another window covers the game at ({fx:.3f}, {fy:.3f}) - not clicking")

    def click(self, fx, fy, hold=0.07):
        self.move(fx, fy)
        self.guard_point(fx, fy)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(hold)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(self.delay)

    def drag(self, fx0, fy0, fx1, fy1, steps=15):
        self.move(fx0, fy0)
        self.guard_point(fx0, fy0)
        self.guard_point(fx1, fy1)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        try:
            for i in range(1, steps + 1):
                t = i / steps
                x, y = self.screen.to_px(fx0 + (fx1 - fx0) * t, fy0 + (fy1 - fy0) * t)
                win32api.SetCursorPos((x, y))
                time.sleep(0.015)
        finally:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(self.delay)

    def scroll(self, clicks, fx=0.5, fy=0.5):
        self.move(fx, fy)
        step = 1 if clicks > 0 else -1
        for _ in range(abs(clicks)):
            self.guard_point(fx, fy)
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, 120 * step, 0)
            time.sleep(0.03)
        time.sleep(self.delay)

    # -- keyboard --------------------------------------------------------
    def right_click(self, fx, fy):
        self.move(fx, fy)
        self.guard_point(fx, fy)
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        time.sleep(self.delay)

    def press(self, key, hold=0.05):
        """key like 'q', 'space', 'shift+space', ','.

        Esc is refused: the Claude desktop app treats a global Esc as "stop", so
        sending it would kill a supervising Claude session. Use clicks instead.
        """
        keys = key.split("+") if len(key) > 1 else [key]
        if any(k.lower() in ("esc", "escape") for k in keys):
            raise ValueError("Esc is not allowed; use a click/right-click instead")
        try:
            for k in keys:
                self.guard()
                pdi.keyDown(k)
                self._held_keys.append(k)
            time.sleep(hold)
        finally:
            self.release_all()
        time.sleep(self.delay)
