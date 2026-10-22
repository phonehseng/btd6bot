"""Status overlay: a thin always-on-top strip at the top of the screen showing
what the bot is doing (latest log line) and how long ago it last did anything.

It never takes focus and lets every click pass through to the game, and the bot
captures the game with PrintWindow, so the overlay never shows up in its OCR.
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

GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80, 0x8000000, 0x8

BG = "#101010"


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


def main():
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\BTD6BotOverlay")
    if ctypes.windll.kernel32.GetLastError() == 183:  # already running
        return
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.85)
    root.configure(bg=BG)
    sw = root.winfo_screenwidth()
    w, h = int(sw * 0.42), 46
    # top centre, above the play field: the game's HUD sits further down
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+0")
    top = tk.Label(root, text="", fg="#7CFC9A", bg=BG, font=("Segoe UI", 10, "bold"), anchor="w")
    bot = tk.Label(root, text="", fg="#E0E0E0", bg=BG, font=("Segoe UI", 9), anchor="w")
    top.pack(fill="x", padx=8)
    bot.pack(fill="x", padx=8)

    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE,
        style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST)

    def tick():
        if (ROOT / "STOP").exists():
            root.destroy()
            return
        st, msg, quiet = describe()
        q = "" if quiet is None else (f"{int(quiet)}s ago" if quiet < 120 else f"{int(quiet // 60)} min ago")
        colour = "#7CFC9A" if quiet is None or quiet < 120 else ("#FFD54F" if quiet < 480 else "#FF6E6E")
        paused = " | PAUSED" if (ROOT / "PAUSE").exists() else ""
        top.config(text=f"BTD6 bot: {st}{paused}   ({q})", fg=colour)
        bot.config(text=msg[:150])
        root.attributes("-topmost", True)
        root.after(700, tick)

    tick()
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())
