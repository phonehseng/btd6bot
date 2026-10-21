"""Dev helper: take over the game currently on screen and play it to the end.

Usage: python tools/test_match.py "Monkey Meadow" easy starter_tack_dart [tid:kind:x:y ...]
Existing towers can be registered so the plan does not re-buy them.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import layout as L  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402
from btd6bot.game import Game, Placed  # noqa: E402
from btd6bot.inputs import Input  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402
from btd6bot.match import Match  # noqa: E402
from btd6bot.menus import Menus  # noqa: E402
from btd6bot.screen import Screen  # noqa: E402
from btd6bot.strategy import Executor, load_all  # noqa: E402

if __name__ == "__main__":
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
                        handlers=[logging.FileHandler("logs/test_match.log"), logging.StreamHandler()])
    map_name, mode, sid = sys.argv[1:4]
    s = Screen()
    inp = Input(s)
    lay = L.get(s.width, s.height)
    acct = AccountState.load()
    g = Game(s, inp, lay, difficulty={"easy": "easy", "medium": "medium"}.get(mode, "hard"))
    for spec in sys.argv[4:]:
        tid, kind, x, y = spec.split(":")
        g.towers[tid] = Placed(tid, kind, float(x), float(y))
    m = MapModel.load(map_name, lay["playfield"])
    strat = load_all()[sid]
    ex = Executor(g, m, strat, mode, acct)
    menus = Menus(s, inp, g)
    s.focus()
    from btd6bot.choices import tower_chooser
    res = Match(g, menus, m, ex, acct, on_tower_choice=tower_chooser(acct)).play()
    acct.save()
    print(res)
