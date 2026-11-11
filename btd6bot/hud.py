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


def parse_xp_bar(text):
    """'678,907/2,750,000' (the XP bar beside the level star on the main
    menu) -> (678907, 2750000): XP earned into the current level and XP that
    level needs. None unless both numbers read and the first is smaller."""
    parts = text.replace(" ", "").split("/")
    if len(parts) != 2:
        return None
    have, need = (parse_int(p) for p in parts)
    if have is None or not need or have >= need:
        return None
    return have, need


_CASH_FORMAT = re.compile(r"^\d{1,3}([,.]\d{3})*$")


def parse_cash(text):
    """'$8,475' -> 8475, or None when the text cannot be the game's cash.

    The game always writes cash with thousands separators ($650, $8,475,
    $20,002,398). OCR sometimes adds a digit (a seasonal decoration next to
    the counter read as '7': '$650' -> '6507', or one inserted mid-number):
    four or more digits without separators, or groups that are not three
    digits long, are rejected instead of trusted."""
    t = _clean_cash_text(text)
    # a comma read as a dash ('$2-873', '$3-127' on Tricky Tracks) or as a
    # colon ('$28:810' on Quad, where an upgrade panel on the left puts the
    # counter over the white garden arch): the game writes neither in the
    # cash, so one between digits and before exactly three digits can only
    # be the separator
    t = re.sub(r"(?<=\d)[-:](?=\d{3}(?!\d))", ",", t)
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


# A cash read without its comma is believed up to this many times the recent
# reads (Hud._without_separator): cash does not double between two looks, and
# a phantom digit - the misread this guards against - multiplies it by ten.
_NO_SEPARATOR_GROWTH = 2


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
            value = self._without_separator(text)
        if value is None:
            return None   # unreadable or malformed this frame: the next one will do
        value = self._dollar_read_as_four(value)
        self._cash_reads = (self._cash_reads + [value])[-3:]
        return sorted(self._cash_reads)[(len(self._cash_reads) - 1) // 2]  # lower median

    def _without_separator(self, text):
        """The cash from a read whose comma was lost ('$31380'), or None.

        Quad Deflation (2026-11-11 13:57): an upgrade panel on the left
        pushes the counter over the white garden arch at the top of the map,
        the white comma disappears into it and every read came back '$31380'.
        parse_cash turns such text down - a phantom digit looks the same
        ('$650' -> '$6507') - so the bot had no cash at all while that panel
        was open: eight tries at the bomb's next tier answered "wait (cash)"
        with $31,380 in hand, and the game was left before Play.

        The two cases differ in size: a phantom digit makes the number about
        ten times the cash, a lost comma leaves it as it was. The read is
        therefore taken when it is the '$' and digits only and is no more than
        ``_NO_SEPARATOR_GROWTH`` times the recent reads. Reading too little
        only makes the bot wait, which is what turning the read down did.
        Without recent reads nothing can be compared and it stays None."""
        match = re.fullmatch(r"\$(\d{4,})", text.strip().replace(" ", ""))
        if not match or not self._cash_reads:
            return None
        value = int(match.group(1))
        ref = sorted(self._cash_reads)[(len(self._cash_reads) - 1) // 2]
        return value if value <= ref * _NO_SEPARATOR_GROWTH else None

    def _dollar_read_as_four(self, value):
        """The cash with a '$' that OCR read as a leading '4' taken off.

        '$31,477' came back '431,477' - well formed, so parse_cash takes it.
        Alpine Run CHIMPS (2026-11-07, 10:30 and 11:02): during crisis holds
        the bot believed $431,477 and $434,225, tried the plan's Glaive Lord
        ($35,100) on that cash, the click bought nothing, and the step was
        given up for the game. Real cash never jumps tenfold between two
        reads, so a read starting with 4 is cut to the rest of its digits
        when that rest lies near the recent reads and the whole does not.
        Without recent reads it is kept as read."""
        text = str(value)
        if not self._cash_reads or len(text) < 4 or text[0] != "4":
            return value
        ref = sorted(self._cash_reads)[(len(self._cash_reads) - 1) // 2]
        rest = int(text[1:])
        near = max(5000, ref // 2)
        if abs(rest - ref) <= near and abs(value - ref) > near:
            return rest
        return value

    def round(self, frame, shifted=None):
        """The round counter ("89/100"), read at its place and at the place an
        open upgrade panel shifts it to. A reading shaped like the counter
        (round / the known total) wins over a bare run of digits from either
        place: Water Park Impoppable (2026-11-11 02:26-02:27) kept round 88 for
        79 s while the game played on to round 91 and lost, though the counter
        was in plain view, and a digits-only parse from the wrong place is one
        way that happens. The raw texts of the last call are kept in
        self.last_round_texts for the stuck-round report (Match)."""
        regions = [self.layout["round"], self.layout["round_shifted"]]
        if shifted is not None:
            regions = [regions[1] if shifted else regions[0]]
        texts, found = [], []
        for reg in regions:
            text, conf = rec_text(crop(frame, reg))
            texts.append(text)
            value = self._parse_round(text)
            if value is not None:
                found.append((self._counter_shaped(text), value))
        self.last_round_texts = texts
        if not found:
            return None
        found.sort(key=lambda sv: not sv[0])      # counter-shaped readings first
        value = found[0][1]
        self.last_round = value
        return value

    def _counter_shaped(self, text):
        """Is `text` the counter's own shape, round / known total?"""
        m = re.search(r"(\d+)[/|\\](\d+)", text.replace(" ", ""))
        return bool(m and (self.total_rounds is None or int(m.group(2)) == self.total_rounds))

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
