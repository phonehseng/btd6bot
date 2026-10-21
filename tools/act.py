"""Dev helper: focus BTD6 and run a tiny action script from the command line.

Usage: python tools/act.py "click 0.5 0.5" "wait 1" "key esc" "scroll -5 0.5 0.5" "shot out.png"
Coordinates are fractions of the game client area (0..1), so they are resolution independent.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.screen import Screen  # noqa: E402
from btd6bot.inputs import Input  # noqa: E402


def main(cmds):
    screen = Screen()
    inp = Input(screen)
    screen.focus()
    for cmd in cmds:
        parts = cmd.split()
        op, args = parts[0], parts[1:]
        if op == "click":
            inp.click(float(args[0]), float(args[1]))
        elif op == "move":
            inp.move(float(args[0]), float(args[1]))
        elif op == "rclick":
            inp.right_click(float(args[0]), float(args[1]))
        elif op == "key":
            inp.press(args[0])
        elif op == "scroll":
            inp.scroll(int(args[0]), float(args[1]), float(args[2]))
        elif op == "wait":
            time.sleep(float(args[0]))
        elif op == "text":
            from btd6bot.vision import Vision
            w = Vision(screen).find_text(" ".join(args))
            if not w:
                raise SystemExit(f"text {' '.join(args)!r} not found")
            print("clicking", w)
            inp.click(w.x, w.y)
        elif op == "shot":
            import cv2
            cv2.imwrite(args[0], screen.grab())
        else:
            raise SystemExit(f"unknown op {op}")


if __name__ == "__main__":
    main(sys.argv[1:])
