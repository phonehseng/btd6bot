"""Dev helper: scan the achievements list (bot must be paused at the main menu)."""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from btd6bot.achievements import Achievements  # noqa: E402
from btd6bot.inputs import Input  # noqa: E402
from btd6bot.menus import Menus  # noqa: E402
from btd6bot.screen import Screen  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    s = Screen()
    inp = Input(s)
    s.focus()
    cards = Achievements(s, inp, Menus(s, inp)).scan(collect="--no-collect" not in sys.argv)
    for name, c in cards.items():
        print(f"{c['status']:9s} {str(c['progress'] or ''):>4s}  {name}: {c['desc']}")
