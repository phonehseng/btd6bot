"""Fast reading of the in-game HUD (lives, cash, round)."""
import re

import cv2
import numpy as np

from .vision import _engine, crop


def _binarize(img):
    """HUD digits are white with a dark outline -> black text on white."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 0, 205), (180, 50, 255))
    out = 255 - mask
    out = cv2.copyMakeBorder(out, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def rec_text(img, binarize=False):
    """Recognition-only OCR of a single text line (~30 ms).

    The raw colour crop reads far more reliably than a binarised one (tested on
    the HUD and upgrade prices), so binarising is opt-in.
    """
    if binarize:
        img = _binarize(img)
    res, _ = _engine()(img, use_det=False, use_cls=False, use_rec=True)
    if not res:
        return "", 0.0
    text, conf = res[0][0], float(res[0][1])
    return text, conf


def parse_int(text):
    t = text.strip().lstrip("$sS")
    t = t.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
    digits = re.sub(r"[^0-9]", "", t)
    return int(digits) if digits else None


class Hud:
    def __init__(self, layout):
        self.layout = layout
        self.last_round = None
        self.total_rounds = None
        self._cash_reads = []

    def read(self, frame):
        return {
            "lives": self.lives(frame),
            "cash": self.cash(frame),
            "round": self.round(frame),
        }

    def lives(self, frame, dx=0.0):
        return parse_int(rec_text(crop(frame, _shift(self.layout["lives"], dx)))[0])

    def cash(self, frame, dx=0.0):
        """Cash, as the median of the last three reads.

        OCR occasionally inserts a phantom digit when scenery scrolls behind the
        number ('$137' -> '$1237'); a single outlier never survives the median.
        dx: horizontal shift of the HUD (an upgrade panel on the left pushes it right).
        """
        text, _ = rec_text(crop(frame, _shift(self.layout["cash"], dx)))
        value = parse_int(text)
        if value is None:
            return None
        self._cash_reads = (self._cash_reads + [value])[-3:]
        return sorted(self._cash_reads)[(len(self._cash_reads) - 1) // 2]  # lower median

    def round(self, frame, shifted=None):
        regions = [self.layout["round"], self.layout["round_shifted"]]
        if shifted is not None:
            regions = [regions[1] if shifted else regions[0]]
        for reg in regions:
            text, conf = rec_text(crop(frame, reg))
            value = self._parse_round(text)
            if value is not None:
                self.last_round = value
                return value
        return None

    def _parse_round(self, text):
        text = text.replace(" ", "")
        m = re.search(r"(\d+)[/|\\](\d+)", text)
        if m and self._plausible_total(int(m.group(2))):
            self.total_rounds = int(m.group(2))
            return int(m.group(1))
        digits = re.sub(r"[^0-9]", "", text)
        # The slash is often read as a digit ('1/40' -> '1740'): strip the
        # known total plus one separator character from the end.
        for total in ([self.total_rounds] if self.total_rounds else []) + [40, 60, 80, 100]:
            ts = str(total)
            if digits.endswith(ts) and len(digits) >= len(ts) + 2:
                head = digits[: -len(ts) - 1]
                if head and int(head) <= 200:
                    self.total_rounds = total
                    return int(head)
        return None

    @staticmethod
    def _plausible_total(t):
        return t in (40, 50, 60, 80, 100) or 1 <= t <= 200


def _shift(region, dx):
    x0, y0, x1, y1 = region
    return (x0 + dx, y0, x1 + dx, y1)


def red_fraction(frame, region):
    """Fraction of saturated red pixels in a region (cancel X, invalid placement)."""
    c = crop(frame, region)
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, (0, 120, 120), (10, 255, 255))
    m2 = cv2.inRange(hsv, (170, 120, 120), (180, 255, 255))
    return float(np.count_nonzero(m1 | m2)) / max(1, m1.size)
