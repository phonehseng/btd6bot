"""Mouse/keyboard input via SendInput, guarded so it only ever reaches BTD6.

Every single event re-checks that BTD6 is the foreground window right before it
is sent. If focus moved elsewhere (another app, a notification)
the bot stops instead of typing into that window. F8 aborts the bot at any time.
"""
import logging
import time

import pydirectinput as pdi
import win32api
import win32con
import win32gui

log = logging.getLogger("inputs")

pdi.PAUSE = 0.0
pdi.FAILSAFE = False

KILL_KEY = win32con.VK_F8


class FocusLost(RuntimeError):
    pass


class Aborted(RuntimeError):
    pass


_STOP_FILE = __import__("pathlib").Path(__file__).resolve().parents[1] / "STOP"


# The HUD's STOP button writes this file and GO removes it (tools/overlay.py):
# while it exists the bot sends no input at all and waits where it is.
HOLD_FILE = _STOP_FILE.with_name("HOLD")


def held():
    """Has the owner pressed STOP in the HUD (and not GO yet)?"""
    return HOLD_FILE.exists()


def kill_requested():
    """Ctrl+Alt+F8 (plain F8 is too easy to hit by accident) or a STOP file."""
    down = lambda vk: bool(win32api.GetAsyncKeyState(vk) & 0x8000)  # noqa: E731
    if down(KILL_KEY) and down(win32con.VK_CONTROL) and down(win32con.VK_MENU):
        return True
    return _STOP_FILE.exists()


class Input:
    def __init__(self, screen, delay=0.07):
        self.screen = screen
        self.delay = delay
        self._held_keys = []

    # While paused for the game, say so this often in the log and status, so
    # the supervisor's watchdog sees a live bot rather than a hung one.
    PAUSE_NOTE_S = 120

    def _wait_for(self, ready, why):
        """Pause until ready() is true - for as long as it takes.

        The bot never raises, restores or launches the game and never moves
        other windows aside: whoever is at the PC brings BTD6 back to the
        front, and the bot carries on from where it stopped.
        """
        from .status import set_state
        self.release_all()
        log.warning("paused: %s - waiting for BTD6 to be back in front", why)
        noted = time.time()
        set_state(f"paused: {why} - waiting for BTD6 to be back in front")
        while not ready():
            if kill_requested():
                raise Aborted("stop requested")
            if not win32gui.IsWindow(self.screen.hwnd):
                # the game closed (its crash dialog's EXIT quits it): find a
                # new window, or raise GameNotFound so the runner waits for
                # the game to be opened again
                self.screen.refresh()
            time.sleep(1)
            if time.time() - noted >= self.PAUSE_NOTE_S:
                noted = time.time()
                log.info("still paused: %s", why)
                set_state(f"paused: {why} - waiting for BTD6 to be back in front")
        log.info("BTD6 is back in front - resuming")
        time.sleep(0.5)          # let the window settle before the next input
        self.screen.refresh()    # it may have moved or been resized meanwhile

    def guard(self):
        if kill_requested():
            self.release_all()
            raise Aborted("F8 pressed")
        if held():
            self._wait_for(lambda: not held() and self.screen.is_foreground(),
                           "stopped from the HUD - press GO to continue")
        if not self.screen.is_foreground():
            self._wait_for(self.screen.is_foreground, "BTD6 is not the foreground window")

    def release_all(self):
        for k in reversed(self._held_keys):
            pdi.keyUp(k)
        self._held_keys.clear()

    # -- mouse -----------------------------------------------------------
    def move(self, fx, fy, fast=False):
        """fast: for hover probes - no settling pause for UI clicks."""
        self.guard()
        x, y = self.screen.to_px(fx, fy)
        # Unity only registers hover/click if the cursor actually travels.
        win32api.SetCursorPos((x - 3, y - 3))
        time.sleep(0.012 if fast else 0.03)
        win32api.SetCursorPos((x, y))
        if not fast:
            time.sleep(self.delay)

    def guard_point(self, fx, fy):
        """Never click through another window (a notification, an overlay):
        pause while one covers the game at (fx, fy)."""
        self.guard()
        if not self.screen.owns_point(fx, fy):
            self._wait_for(lambda: self.screen.is_foreground() and self.screen.owns_point(fx, fy),
                           f"another window covers the game at ({fx:.3f}, {fy:.3f})")

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

    def type_text(self, text):
        """Type into a focused game text box (letters, digits, spaces, ' and #)."""
        for ch in text:
            self.guard()
            if ch == " ":
                pdi.press("space")
            elif ch.isalnum():
                if ch.isupper():
                    pdi.keyDown("shift")
                    pdi.press(ch.lower())
                    pdi.keyUp("shift")
                else:
                    pdi.press(ch)
            elif ch == "'":
                pdi.press("'")
            elif ch == "#":
                pdi.keyDown("shift")
                pdi.press("3")
                pdi.keyUp("shift")
            time.sleep(0.03)
        time.sleep(self.delay)

    def press(self, key, hold=0.05):
        """key like 'q', 'space', 'shift+space', ','.

        Esc is refused: other programs on this machine treat a global Esc as
        "stop", so a stray Esc could end them. Use clicks instead.
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
