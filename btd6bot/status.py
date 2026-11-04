"""One-line 'what am I doing' status in logs/state.txt (shown by tools/overlay.py)."""
import time
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parents[1] / "logs" / "state.txt"
_game = ""


FOCUS_FILE = STATE_FILE.with_name("focus.txt")


def set_focus(text):
    """What the current game is biased toward for tower XP (shown by the
    HUD, tools/overlay.py), e.g. "bomb - paragon focus, needs 208k XP";
    None clears it."""
    try:
        if text:
            FOCUS_FILE.write_text(text, encoding="utf-8")
        else:
            FOCUS_FILE.unlink(missing_ok=True)
    except OSError:
        pass     # the HUD is a convenience; a locked file must not stop a game


LEVEL_FILE = STATE_FILE.with_name("level.txt")


def set_level(level, xp=None):
    """The player level, and xp = (earned into this level, needed for it)
    from the main menu's XP bar, for the HUD (tools/overlay.py), e.g.
    "Lv 142 | 678,907 / 2,750,000 XP (25%)"."""
    text = f"Lv {level}"
    if xp:
        have, need = xp
        text += f" | {have:,} / {need:,} XP ({100 * have // need}%)"
    try:
        LEVEL_FILE.write_text(text, encoding="utf-8")
    except OSError:
        pass     # the HUD is a convenience; a locked file must not stop a game


def set_state(text, game=None):
    """game: sticky prefix for in-game updates ('playing Logs hard')."""
    global _game
    if game is not None:
        _game = game
    try:
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n", encoding="utf-8")
    except OSError:
        pass


def in_game(text):
    set_state(f"{_game} - {text}" if _game else text)
