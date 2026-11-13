"""Nothing the recorder starts may open a console window (no game needed).

The recorder runs under pythonw.exe, which has no console. A console program
(ffmpeg, git) started from it without CREATE_NO_WINDOW gets a brand-new
console window, and Windows puts that window in front of the game. The bot
pauses while BTD6 is not the foreground window, so the game then runs with
nobody playing it.

2026-11-13: the full-run video of every CHIMPS game (timelapse.py) was
encoded with only BELOW_NORMAL_PRIORITY_CLASS as its creation flags. With
CHIMPS games played back to back, a window titled with ffmpeg's path covered
the next game for about 20 s each time: eight pauses between 00:43 and 04:12
(logs/bot.log "paused: BTD6 is not the foreground window"), each ending in
the second the recorder logged "full run saved". In the Water Park CHIMPS
game of 04:09 the whole of round 6 ran during such a pause.

The test reads the source of every module the recorder process runs and
requires each subprocess call to name CREATE_NO_WINDOW (or its value) in its
creationflags.

Run: python tests/test_recorder_no_console_window_offline.py"""
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: The modules that run inside the windowless recorder process
#: (recorder.main and what it imports and calls).
RECORDER_MODULES = ("recorder", "highlights", "timelapse", "losses", "gameaudio")

#: The subprocess functions that start a program.
STARTERS = {"run", "Popen", "call", "check_call", "check_output"}

#: How a creationflags expression may spell the flag.
NO_WINDOW_SPELLINGS = ("CREATE_NO_WINDOW", f"0x{subprocess.CREATE_NO_WINDOW:08x}")


def subprocess_calls(source):
    """Every `subprocess.<starter>(...)` call in `source`, as AST nodes."""
    return [node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in STARTERS
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"]


def hides_its_window(call, source):
    """Does this call pass creationflags that include CREATE_NO_WINDOW?"""
    for kw in call.keywords:
        if kw.arg == "creationflags":
            text = ast.get_source_segment(source, kw.value) or ""
            return any(s.lower() in text.lower() for s in NO_WINDOW_SPELLINGS)
    return False


def test_every_program_the_recorder_starts_has_no_window():
    found = 0
    for name in RECORDER_MODULES:
        source = (ROOT / "btd6bot" / f"{name}.py").read_text(encoding="utf-8")
        for call in subprocess_calls(source):
            found += 1
            assert hides_its_window(call, source), (
                f"btd6bot/{name}.py line {call.lineno}: subprocess.{call.func.attr} without "
                "CREATE_NO_WINDOW - under pythonw it opens a console window over the game")
    assert found >= 5, f"only {found} subprocess calls found - did the modules move?"
    print(f"ok all {found} programs started by the recorder's modules are windowless")


def test_the_check_tells_the_flags_apart():
    """The 2026-11-13 line fails the check; the fixed spellings pass it."""
    cases = {
        'subprocess.run(c, creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))': False,
        "subprocess.run(c)": False,
        "subprocess.run(c, creationflags=subprocess.CREATE_NO_WINDOW)": True,
        "subprocess.Popen(c, creationflags=0x08000000)": True,
        'subprocess.run(c, creationflags=subprocess.CREATE_NO_WINDOW | getattr(subprocess, "X", 0))': True,
    }
    for source, expected in cases.items():
        (call,) = subprocess_calls(source)
        assert hides_its_window(call, source) is expected, source
    print("ok a priority class alone does not count as hiding the window")


if __name__ == "__main__":
    test_every_program_the_recorder_starts_has_no_window()
    test_the_check_tells_the_flags_apart()
    print("ALL OK")
