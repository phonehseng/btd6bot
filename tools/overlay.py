"""The bot's on-screen HUD, started by run_forever.ps1; single instance.

Three HUDs, one chosen at start:

  glass   (the default) tools/glass_hud.py: a few small see-through
          "liquid glass" widgets at the screen's edges - a status pill at
          the top centre, the coming rounds' margins and the latest decision
          along the bottom in a game, the planner's pick and the
          black-border progress at the right edge in menus - and faint ghost
          towers where the build still wants towers
  big     tools/big_hud.py: the full-screen HUD it replaced (a thinking
          panel down the left, a black-border board over the menus); used
          when a HUD_BIG file exists in the repo root or BTD6BOT_HUD is
          "big", or when the glass HUD fails to start
  strip   the thin strip at the top of the screen with what the bot is
          doing (latest log line) and how long ago it last did anything;
          used when a HUD_STRIP file exists in the repo root or BTD6BOT_HUD
          is "strip", or when the others fail to start

A HUD that fails to start leaves its error in logs/hud_error.txt. All three
keep the STOP / GO / OFF buttons at the top of the screen, right of the
status pill or strip (tools/hud_controls.py says what they do), never take
focus, let every click pass through to the game and stay out of screen
captures; the bot captures the game with PrintWindow, so none shows up in
its OCR.

Close it with the STOP file or by ending the process.
"""
import ctypes
import os
import sys
import time
import tkinter as tk
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hud_controls import (CLICK_THROUGH, HOLD, ROOT, ButtonPanel, exclude_from_capture,  # noqa: E402
                          hand_focus_back, set_ex_style, take_single_instance, user32)

LOG = ROOT / "logs" / "bot.log"
STATE = ROOT / "logs" / "state.txt"
FOCUS = ROOT / "logs" / "focus.txt"    # the game's XP focus (btd6bot.status.set_focus)
LEVEL = ROOT / "logs" / "level.txt"    # player level and XP bar (btd6bot.status.set_level)
STRIP_SWITCH = ROOT / "HUD_STRIP"      # this file: the thin strip
BIG_SWITCH = ROOT / "HUD_BIG"          # this file: the big full-screen HUD
HUD_ENV = "BTD6BOT_HUD"                # ... or this variable set to "strip", "big" or "glass"
HUDS = ("glass", "big", "strip")       # the HUDs, each falling back to the ones after it
ERROR_FILE = ROOT / "logs" / "hud_error.txt"

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


def strip_wanted():
    """The owner's switch back to the thin strip (HUD_STRIP file or BTD6BOT_HUD=strip)."""
    return STRIP_SWITCH.exists() or os.environ.get(HUD_ENV, "").strip().lower() == "strip"


def hud_wanted():
    """Which HUD the owner wants: "strip" (HUD_STRIP file or BTD6BOT_HUD=strip),
    "big" (HUD_BIG file or BTD6BOT_HUD=big), else "glass"."""
    if strip_wanted():
        return "strip"
    if BIG_SWITCH.exists() or os.environ.get(HUD_ENV, "").strip().lower() == "big":
        return "big"
    return "glass"


def note_error(what):
    """Keep the latest HUD error where the owner (or the caretaker) can read it."""
    try:
        ERROR_FILE.parent.mkdir(exist_ok=True)
        ERROR_FILE.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {what}\n{traceback.format_exc()}",
                              encoding="utf-8")
    except OSError:
        pass


def run_strip():
    """The thin status strip with the buttons beside it."""
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
    line2 = tk.Frame(root, bg=BG)
    line2.pack(fill="x", padx=8)
    # player level and XP, as last read from the main menu
    level = tk.Label(line2, text="", fg="#81D4FA", bg=BG, font=("Segoe UI", 9, "bold"), anchor="e")
    level.pack(side="right")
    bot = tk.Label(line2, text="", fg="#E0E0E0", bg=BG, font=("Segoe UI", 9), anchor="w")
    bot.pack(side="left", fill="x", expand=True)
    # the strip: click-through, never focused, left out of captures
    set_ex_style(root, CLICK_THROUGH)
    exclude_from_capture(root)
    buttons = ButtonPanel(root, x0 + w + 6, h)
    exclude_from_capture(buttons.win)

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
        lv = last_line(LEVEL)
        level.config(text=lv)
        bot.config(text=msg[:150 - len(lv)])
        xp = ""
        if FOCUS.exists() and (age(FOCUS) or 0) < 3 * 3600:      # a stale note from a crashed game is ignored
            xp = "XP: " + last_line(FOCUS)[:60]
        focus.config(text=xp)
        buttons.refresh()            # the pressed state shows on the buttons too
        root.attributes("-topmost", True)
        buttons.win.attributes("-topmost", True)
        root.after(700, tick)

    hand_focus_back(root, was_in_front)
    tick()
    root.mainloop()


def main():
    if not take_single_instance():
        return
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    chain = HUDS[HUDS.index(hud_wanted()):]
    for name, fallback in zip(chain, chain[1:]):     # the strip, last, has nothing to fall back to
        try:
            module = __import__({"glass": "glass_hud", "big": "big_hud"}[name])
            return module.run()
        except Exception:
            note_error(f"the {name} HUD failed to start - trying the {fallback} HUD")
    run_strip()


if __name__ == "__main__":
    sys.exit(main())
