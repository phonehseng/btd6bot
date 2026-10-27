"""Status overlay: a thin always-on-top strip at the top of the screen showing
what the bot is doing (latest log line) and how long ago it last did anything,
with STOP and GO buttons beside it.

The strip never takes focus and lets every click pass through to the game,
and the bot captures the game with PrintWindow, so the overlay never shows up
in its OCR. The buttons sit in a small window of their own, right of the strip
(off the game's play field), which takes clicks but never focus:

  STOP  writes the HOLD file: the bot sends no more input and waits where it
        is (btd6bot/inputs.py). It stops the bot, not the game - a round in
        progress keeps running.
  GO    resumes, whatever stopped the bot: removes HOLD, PAUSE and STOP,
        brings BTD6 to the front (or starts BloonsTD6.exe when it is
        closed) and starts the supervisor when no bot is running. (The bot
        itself never takes focus or opens the game; GO is the owner's click.)

Started by run_forever.ps1; single instance. Close it with the STOP file or by
ending the process.
"""
import ctypes
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "bot.log"
STATE = ROOT / "logs" / "state.txt"
FOCUS = ROOT / "logs" / "focus.txt"    # the game's XP focus (btd6bot.status.set_focus)
HOLD = ROOT / "HOLD"                # the same file btd6bot.inputs.HOLD_FILE waits on
GAME_TITLE = "BloonsTD6"            # btd6bot.screen.WINDOW_TITLE

GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80, 0x8000000, 0x8

BG = "#101010"
user32 = ctypes.windll.user32


def last_line(path, max_bytes=4096):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            lines = f.read().decode("utf-8", "replace").splitlines()
        return next((ln for ln in reversed(lines) if ln.strip()), "")
    except OSError:
        return ""


def age(path):
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return None


def describe():
    line = last_line(LOG)
    # "2026-10-21 21:53:38,246 I runner: syncing ..." -> "runner: syncing ..."
    parts = line.split(" ", 3)
    msg = parts[3] if len(parts) == 4 else line
    state = last_line(STATE)
    st = state.split(" ", 2)[2] if state.count(" ") >= 2 else state
    ages = [a for a in (age(LOG), age(STATE)) if a is not None]
    quiet = min(ages) if ages else None
    return st, msg, quiet


def bring_game_forward():
    """Put BTD6 in front (restoring it if minimised). Windows only lets the
    foreground app hand focus over, so this joins the foreground window's
    input queue for the moment of the switch."""
    hwnd = user32.FindWindowW(None, GAME_TITLE)
    if not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)                 # SW_RESTORE
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


# the game's own executable (started directly, not through Steam's URL)
GAME_EXE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\BloonsTD6\BloonsTD6.exe")
NO_WINDOW = 0x08000000                        # subprocess.CREATE_NO_WINDOW


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


def set_ex_style(win, extra):
    """Add extended window styles to a Tk window (its real top-level hwnd)."""
    win.update_idletasks()
    hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | extra)


def main():
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\BTD6BotOverlay")
    if ctypes.windll.kernel32.GetLastError() == 183:  # already running
        return
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    # Tk activates its first window when it appears, before the no-activate
    # style is set: remember who was in front and give focus straight back
    # (otherwise starting the overlay would pause the bot)
    was_in_front = user32.GetForegroundWindow()

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.85)
    root.configure(bg=BG)
    sw = root.winfo_screenwidth()
    w, h = int(sw * 0.42), 46
    # top centre, above the play field: the game's HUD sits further down
    x0 = (sw - w) // 2
    root.geometry(f"{w}x{h}+{x0}+0")
    line1 = tk.Frame(root, bg=BG)
    line1.pack(fill="x", padx=8)
    top = tk.Label(line1, text="", fg="#7CFC9A", bg=BG, font=("Segoe UI", 10, "bold"), anchor="w")
    top.pack(side="left")
    # which tower the game is favouring for XP (paragon focus / XP build)
    focus = tk.Label(line1, text="", fg="#FFD54F", bg=BG, font=("Segoe UI", 10, "bold"), anchor="e")
    focus.pack(side="right")
    bot = tk.Label(root, text="", fg="#E0E0E0", bg=BG, font=("Segoe UI", 9), anchor="w")
    bot.pack(fill="x", padx=8)
    # the strip: click-through, never focused
    set_ex_style(root, WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST)

    # the buttons: clickable, but never take focus away from the game
    panel = tk.Toplevel(root)
    panel.overrideredirect(True)
    panel.attributes("-topmost", True)
    panel.configure(bg=BG)
    pw = 180
    panel.geometry(f"{pw}x{h}+{x0 + w + 6}+0")

    def press_stop():
        HOLD.write_text(time.strftime("%Y-%m-%d %H:%M:%S stopped from the HUD\n"), encoding="utf-8")

    def press_go():
        go()

    style = dict(font=("Segoe UI", 11, "bold"), bd=0, relief="flat", width=7, cursor="hand2")
    stop_btn = tk.Button(panel, text="■ STOP", bg="#7a1e1e", fg="white", activebackground="#a32929",
                         activeforeground="white", command=press_stop, **style)
    go_btn = tk.Button(panel, text="▶ GO", bg="#1e6b34", fg="white", activebackground="#27914a",
                       activeforeground="white", command=press_go, **style)
    stop_btn.pack(side="left", fill="y", padx=(4, 2), pady=4)
    go_btn.pack(side="left", fill="y", padx=(2, 4), pady=4)
    set_ex_style(panel, WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST)

    def tick():
        if (ROOT / "STOP").exists():
            root.destroy()
            return
        st, msg, quiet = describe()
        q = "" if quiet is None else (f"{int(quiet)}s ago" if quiet < 120 else f"{int(quiet // 60)} min ago")
        colour = "#7CFC9A" if quiet is None or quiet < 120 else ("#FFD54F" if quiet < 480 else "#FF6E6E")
        flags = (" | STOPPED - press GO" if HOLD.exists() else "") + (" | PAUSED" if (ROOT / "PAUSE").exists() else "")
        if HOLD.exists():
            colour = "#FF6E6E"
        top.config(text=f"BTD6 bot: {st}{flags}   ({q})", fg=colour)
        bot.config(text=msg[:150])
        xp = ""
        if FOCUS.exists() and (age(FOCUS) or 0) < 3 * 3600:      # a stale note from a crashed game is ignored
            xp = "XP: " + last_line(FOCUS)[:60]
        focus.config(text=xp)
        # the pressed state shows on the buttons too
        stop_btn.config(bg="#c62828" if HOLD.exists() else "#7a1e1e")
        go_btn.config(bg="#1e6b34" if HOLD.exists() else "#2e7d32")
        root.attributes("-topmost", True)
        panel.attributes("-topmost", True)
        root.after(700, tick)

    def give_focus_back():
        if was_in_front and user32.IsWindow(was_in_front):
            user32.SetForegroundWindow(was_in_front)   # we are in front now, so Windows allows it

    root.after(300, give_focus_back)
    tick()
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())
