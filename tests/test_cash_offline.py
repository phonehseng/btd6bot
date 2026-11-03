"""Cash OCR must reject misreads instead of trusting them (hud.parse_cash)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa: E402

from btd6bot.hud import Hud, cash_prefixes, parse_cash, trim_to_digits  # noqa: E402


def test_valid_cash():
    assert parse_cash("$650") == 650
    assert parse_cash("$8,475") == 8475
    assert parse_cash("$8.475") == 8475            # comma read as a dot
    assert parse_cash("$20,002,398") == 20002398
    assert parse_cash("$650T") == 650              # stray glyph after the number


def test_misreads_are_rejected():
    assert parse_cash("$6507") is None             # an extra digit, no separator
    assert parse_cash("$1,2345") is None           # digit inserted into a group
    assert parse_cash("$1885") is None             # thousands always have a comma
    assert parse_cash("") is None


def test_scenery_after_the_number_is_cut_off():
    """Tricky Tracks (2026-11-02): Halloween graffiti right of the counter
    made every read '$3.700-00元' and the bot bought nothing for a whole setup."""
    assert parse_cash("$3.700-00元") == 3700
    assert parse_cash("$12,345克x") == 12345
    assert parse_cash("$8'475") is None            # a cut without separator is never trusted
    assert parse_cash("$3.70000") is None          # ambiguous on its own (see below)


def test_dash_read_for_the_separator():
    """Tricky Tracks (2026-11-03 stills): the comma came out as a dash."""
    assert parse_cash("$2-873") == 2873
    assert parse_cash("$3-127") == 3127
    assert parse_cash("$2-87300") is None          # still padded: not trusted


def test_trim_cuts_the_scenery_right_of_the_digits():
    """White digits, then a gap, then a bright colourful wall (the graffiti):
    the trimmed crop ends shortly after the digits and keeps all of them."""
    import cv2
    img = np.zeros((40, 200, 3), np.uint8)
    cv2.putText(img, "$2,873", (2, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    text_end = int(np.flatnonzero(img.max(axis=(0, 2)) > 200).max())
    img[:, 150:] = (60, 220, 90)                   # saturated green: not text
    short = trim_to_digits(img)
    assert text_end < short.shape[1] < 150
    blank = np.zeros((40, 200, 3), np.uint8)
    assert trim_to_digits(blank) is blank          # no text: nothing to cut


class _ScriptedHud(Hud):
    """A Hud whose OCR returns scripted texts instead of reading a frame."""

    def __init__(self, texts):
        super().__init__({"cash": (0, 0, 1, 1)})
        self.texts = iter(texts)

    def cash(self, frame=None, dx=0.0):
        import btd6bot.hud as H
        saved = H.rec_text
        H.rec_text = lambda img: (next(self.texts), 0.9)
        try:
            return super().cash(np.zeros((10, 10, 3), np.uint8), dx)
        finally:
            H.rec_text = saved


def test_padded_read_is_believed_only_when_it_repeats_a_clean_read():
    """Encrypted: falling leaves add a phantom trailing digit ('$6.2155')."""
    assert cash_prefixes("$6.2155") == [6215]
    hud = _ScriptedHud(["$6.2155", "$6.215", "$6.2155", "$6.2153"])
    assert hud.cash() is None, "no clean read yet: nothing to confirm"
    assert hud.cash() == 6215
    assert hud.cash() == 6215 and hud.cash() == 6215


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
