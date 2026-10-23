"""Loss case files (btd6bot/losses.py): which games are filed, when, under
what name, and from which moment the evidence is cut. Offline: synthetic
games, files in a temporary folder."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import losses as L   # noqa: E402

T = 1792779108.0


def game(outcome="defeat", end=T + 430):
    return {"start": T, "end": end, "map": "Pat's Pond", "mode": "double_hp", "outcome": outcome, "round": 40,
            "lines": [(T + 5, "I game: placed s1 (sniper) at 0.5,0.5"),
                      (end - 22, "I match: game over: {'outcome': 'defeat'}"),
                      (end - 20, "I menus: click 'Home'")]}


def test_the_evidence_is_cut_at_the_defeat_not_the_result_line():
    assert L._defeat_time(game()) == T + 430 - 22


def test_names_are_safe_folder_names():
    assert L._name(game()).endswith("_PatsPond_double_hp")


def test_only_finished_losses_are_filed():
    with tempfile.TemporaryDirectory() as tmp:
        L.LOSS_DIR = Path(tmp)
        games = [game(), game("victory"), game(end=T + 99999)]
        filed = []
        L._games = lambda: games
        L.file_loss = lambda ffmpeg, g: filed.append(g) or Path(tmp)
        # right after the defeat: its last recording chunk is still being written
        L.update(None, now=T + 430 + 10)
        assert filed == []
        L.update(None, now=T + 430 + L.CLOSED_AFTER + 5)
        assert [g["outcome"] for g in filed] == ["defeat"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
