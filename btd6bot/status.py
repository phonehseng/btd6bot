"""One-line 'what am I doing' status in logs/state.txt (shown by tools/overlay.py)."""
import time
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parents[1] / "logs" / "state.txt"
_game = ""


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
