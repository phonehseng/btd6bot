"""The HUD's window plumbing and the owner's STOP / GO / OFF buttons, shared
by the thin strip (tools/overlay.py) and the big HUD (tools/big_hud.py).

Every HUD window stays out of the bot's way:

  * WS_EX_NOACTIVATE: it never takes focus, so the bot's "BTD6 is not the
    foreground window" pause (btd6bot/inputs.py, Screen.is_foreground)
    never fires because of it;
  * WS_EX_LAYERED | WS_EX_TRANSPARENT on the drawing windows: every click
    and key passes through to the game, and WindowFromPoint skips them, so
    the bot's "another window covers the game" check (Screen.owns_point)
    still finds the game under them;
  * WDA_EXCLUDEFROMCAPTURE: screen captures leave it out - the recorder's
    desktop capture (btd6bot/recorder.py: ddagrab / gdigrab), the mss
    fallback of Screen.grab and tools/shot.py. The bot's own capture is
    PrintWindow of the game window, which never contains another window.

The button panel is the one window that takes clicks; it never takes focus
and sits at the top of the screen, right of the status strip.

  STOP  writes the HOLD file: the bot sends no more input and waits where it
        is (btd6bot/inputs.py). It stops the bot, not the game - a round in
        progress keeps running.
  GO    resumes, whatever stopped the bot: removes HOLD, PAUSE and STOP,
        brings BTD6 to the front (or starts BloonsTD6.exe when it is
        closed) and starts the supervisor when no bot is running. (The bot
        itself never takes focus or opens the game; GO is the owner's click.)
  OFF   turns the bot off completely (tools/bot_off.ps1): bot, supervisor,
        the HUD and the recorder close; BTD6 stays open. The STOP file it
        leaves keeps everything off until tools/bot_on.ps1 (BTD6 Bot ON).
"""
import ctypes
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOLD = ROOT / "HOLD"                # the same file btd6bot.inputs.HOLD_FILE waits on
GAME_TITLE = "BloonsTD6"            # btd6bot.screen.WINDOW_TITLE

GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80, 0x8000000, 0x8
CLICK_THROUGH = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
NO_FOCUS = WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
WDA_EXCLUDEFROMCAPTURE = 0x11       # Windows 10 2004+: the window is left out of captures
SW_RESTORE = 9
FOCUS_BACK_MS = 300                 # Tk shows its first window activated: focus goes back after this

BG = "#101010"
BUTTON_PANEL_WIDTH = 270
BUTTON_GAP = 6                      # pixels between the status strip and the buttons
user32 = ctypes.windll.user32

# the game's own executable (started directly, not through Steam's URL)
GAME_EXE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\BloonsTD6\BloonsTD6.exe")
NO_WINDOW = 0x08000000                        # subprocess.CREATE_NO_WINDOW


def hwnd_of(win):
    """The real top-level window handle of a Tk window."""
    win.update_idletasks()
    return user32.GetParent(win.winfo_id()) or win.winfo_id()


def set_ex_style(win, extra):
    """Add extended window styles to a Tk window (its real top-level hwnd)."""
    hwnd = hwnd_of(win)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | extra)
    return hwnd


def exclude_from_capture(win):
    """Leave the window out of screen captures and recordings; False where
    Windows refuses (before Windows 10 2004) - the HUD then shows in them,
    as the old strip did."""
    return bool(user32.SetWindowDisplayAffinity(hwnd_of(win), WDA_EXCLUDEFROMCAPTURE))


def game_client_rect():
    """(left, top, width, height) of BTD6's client area in screen pixels,
    or None when the game is closed or minimised (as btd6bot.screen
    measures it: GetClientRect + ClientToScreen)."""
    hwnd = user32.FindWindowW(None, GAME_TITLE)
    if not hwnd or user32.IsIconic(hwnd):
        return None
    r = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    if not user32.GetClientRect(hwnd, ctypes.byref(r)) or not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    if r.right <= 0 or r.bottom <= 0:
        return None
    return origin.x, origin.y, r.right, r.bottom


def bring_game_forward():
    """Put BTD6 in front (restoring it if minimised). Windows only lets the
    foreground app hand focus over, so this joins the foreground window's
    input queue for the moment of the switch."""
    hwnd = user32.FindWindowW(None, GAME_TITLE)
    if not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other and other != me and user32.AttachThreadInput(me, other, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)
    return user32.GetForegroundWindow() == hwnd


def bot_running():
    """Is a bot (bot.py run) or its supervisor (run_forever.ps1) running?"""
    import subprocess
    ps = ("Get-CimInstance Win32_Process | ? { $_.CommandLine -match 'bot.py run|run_forever.ps1' "
          "-and $_.Name -ne 'bash.exe' } | Measure-Object | % Count")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             timeout=20, creationflags=NO_WINDOW).stdout.strip()
        return int(out or 0) > 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return True      # unknown: never start a second supervisor on a guess


def go():
    """The GO button: undo whatever stopped the bot, whatever it was.

      * the HUD's STOP (HOLD), the PAUSE and STOP files are removed;
      * BTD6 is brought to the front - or started from its .exe when it is
        not running (the owner's click; the bot itself never does either);
      * the supervisor is started when no bot is running (it starts the bot).
    """
    import subprocess
    for name in ("HOLD", "PAUSE", "STOP"):
        (ROOT / name).unlink(missing_ok=True)
    if user32.FindWindowW(None, GAME_TITLE):
        bring_game_forward()
    elif GAME_EXE.exists():
        subprocess.Popen([str(GAME_EXE)], cwd=str(GAME_EXE.parent))
    if not bot_running():
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                          "-File", str(ROOT / "run_forever.ps1")], cwd=str(ROOT), creationflags=NO_WINDOW)


def turn_off():
    """The OFF button: run tools/bot_off.ps1, which writes the STOP file
    (every part of the bot, the HUD included, exits on it) and ends anything
    still running after 45 s."""
    import subprocess
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                      "-File", str(ROOT / "tools" / "bot_off.ps1")], cwd=str(ROOT), creationflags=NO_WINDOW)


def stop():
    """The STOP button: the HOLD file the bot's input layer waits on."""
    HOLD.write_text(time.strftime("%Y-%m-%d %H:%M:%S stopped from the HUD\n"), encoding="utf-8")


class ButtonPanel:
    """STOP / GO / OFF in a small window of their own at (x, 0), `height`
    tall: it takes clicks but never focus. refresh() shows the pressed
    state and keeps the panel on top."""

    def __init__(self, master, x, height):
        panel = self.win = tk.Toplevel(master)
        panel.overrideredirect(True)
        panel.attributes("-topmost", True)
        panel.configure(bg=BG)
        panel.geometry(f"{BUTTON_PANEL_WIDTH}x{height}+{x}+0")
        style = dict(font=("Segoe UI", 11, "bold"), bd=0, relief="flat", width=7, cursor="hand2")
        self.stop_btn = tk.Button(panel, text="■ STOP", bg="#7a1e1e", fg="white", activebackground="#a32929",
                                  activeforeground="white", command=stop, **style)
        self.go_btn = tk.Button(panel, text="▶ GO", bg="#1e6b34", fg="white", activebackground="#27914a",
                                activeforeground="white", command=go, **style)
        self.off_btn = tk.Button(panel, text="⏻ OFF", bg="#333333", fg="white", activebackground="#555555",
                                 activeforeground="white", command=turn_off, **style)
        self.stop_btn.pack(side="left", fill="y", padx=(4, 2), pady=4)
        self.go_btn.pack(side="left", fill="y", padx=2, pady=4)
        self.off_btn.pack(side="left", fill="y", padx=(2, 4), pady=4)
        set_ex_style(panel, NO_FOCUS)

    def refresh(self):
        held = HOLD.exists()
        self.stop_btn.config(bg="#c62828" if held else "#7a1e1e")
        self.go_btn.config(bg="#1e6b34" if held else "#2e7d32")
        self.win.attributes("-topmost", True)


def take_single_instance():
    """The HUD's single-instance lock (held for the life of the process);
    False when another HUD - strip or big - already runs."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\BTD6BotOverlay")
    return ctypes.windll.kernel32.GetLastError() != 183      # ERROR_ALREADY_EXISTS


def hand_focus_back(root, was_in_front):
    """Tk activates its first window when it appears, before the no-activate
    style is set: give focus straight back to whoever was in front
    (otherwise starting the HUD would pause the bot)."""
    def back():
        if was_in_front and user32.IsWindow(was_in_front):
            user32.SetForegroundWindow(was_in_front)   # we are in front now, so Windows allows it
    root.after(FOCUS_BACK_MS, back)
