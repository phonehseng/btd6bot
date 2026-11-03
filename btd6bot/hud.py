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


_CASH_FORMAT = re.compile(r"^\d{1,3}([,.]\d{3})*$")


def parse_cash(text):
    """'$8,475' -> 8475, or None when the text cannot be the game's cash.

    The game always writes cash with thousands separators ($650, $8,475,
    $20,002,398). OCR sometimes adds a digit (a seasonal decoration next to
    the counter read as '7': '$650' -> '6507', or one inserted mid-number):
    four or more digits without separators, or groups that are not three
    digits long, are rejected instead of trusted."""
    t = _clean_cash_text(text)
    # a comma read as a dash ('$2-873', '$3-127' on Tricky Tracks): the game
    # never writes a dash in the cash, so one before exactly three last
    # digits can only be the separator
    t = re.sub(r"(?<=\d)-(?=\d{3}(?!\d))", ",", t)
    whole = re.sub(r"[^0-9,.]", "", t).strip(",.")   # drop stray symbols around the number
    if whole and _CASH_FORMAT.match(whole):
        return int(re.sub(r"[^0-9]", "", whole))
    # Scenery right of the counter read as more characters (Tricky Tracks'
    # Halloween graffiti: '$3,700' -> '$3.700-00元'): the number ends at the
    # first character that cannot be part of it. Only trusted when what is
    # left still has a separator - a cut '$8'475' must not become $8.
    head = re.match(r"[0-9,.]+", t)
    head = head.group(0).strip(",.") if head else ""
    if head != whole and re.search(r"[,.]", head) and _CASH_FORMAT.match(head):
        return int(re.sub(r"[^0-9]", "", head))
    return None


def _clean_cash_text(text):
    """The OCR text with '$' and spaces gone and letters that are digit
    look-alikes (O, l, I) turned into digits."""
    t = text.strip().lstrip("$sS").replace(" ", "")
    return t.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")


def cash_prefixes(text):
    """Every well-formed cash value (with a separator) that the OCR text
    starts with: '$6.2155' -> [6215]. A trailing phantom digit and a digit
    inserted into the last group look the same, so a prefix is only a
    candidate - Hud.cash accepts it when it repeats a recent clean read."""
    digits = re.sub(r"[^0-9,.]", "", _clean_cash_text(text))
    out = []
    for end in range(len(digits) - 1, 0, -1):
        head = digits[:end]
        if re.search(r"[,.]", head) and _CASH_FORMAT.match(head):
            out.append(int(re.sub(r"[^0-9]", "", head)))
    return out


def trim_to_digits(img):
    """The HUD crop cut off right of its white text.

    The cash crop is wide enough for '$20,002,398', so with a few thousand
    dollars most of it is scenery - on Tricky Tracks a colourful graffiti
    wall that OCR reads as extra digits ('$2,980' -> '$2.98000'). HUD digits
    are white (low saturation, high value); the text ends at the first gap
    between white columns wider than ~half the text height (a separator or
    the space between digits is much narrower). Returns ``img`` unchanged
    when no white text is found.

    Tested on the stills of the Tricky Tracks Easy loss of 2026-11-03: of the
    first 17 frames, correct cash reads went from 4 to 11 (with the dash
    rule in parse_cash); tests/test_cash_offline.py checks the cut."""
    h = img.shape[0]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, (0, 0, 205), (180, 60, 255)) > 0
    # a column belongs to the text when enough of it is white (not a speck)
    xs = np.flatnonzero(white.sum(axis=0) >= max(2, h // 12))
    if xs.size == 0:
        return img
    end = xs[0]
    for x in xs[1:]:
        if x - end > h * 0.45:
            break
        end = x
    # keep a small margin so the last digit's dark outline stays whole
    return img[:, :min(img.shape[1], end + max(3, h // 6))]


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
        img = crop(frame, _shift(self.layout["cash"], dx))
        text, _ = rec_text(img)
        value = parse_cash(text)
        if value is None:
            # scenery right of the number read as more digits ('$2,873' ->
            # '$2-87300'): read again with the crop cut where the white
            # digits end - only when that really cuts something off
            short = trim_to_digits(img)
            if short.shape[1] < img.shape[1]:
                value = parse_cash(rec_text(short)[0])
        if value is None:
            # '$6.2155' on Encrypted (leaves falling past the counter): the
            # padded read is believed only when its prefix repeats a clean read
            value = next((v for v in cash_prefixes(text) if v in self._cash_reads), None)
        if value is None:
            return None   # unreadable or malformed this frame: the next one will do
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
