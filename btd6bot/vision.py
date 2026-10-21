"""OCR and image helpers. All positions returned are fractions of the client area."""
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

_ocr = None


def _engine():
    global _ocr
    if _ocr is None:
        import logging
        from rapidocr_onnxruntime import RapidOCR

        _ocr = RapidOCR()
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
    return _ocr


@dataclass
class Word:
    text: str
    x: float  # centre, fraction of client width
    y: float  # centre, fraction of client height
    w: float
    h: float
    conf: float

    def __repr__(self):
        return f"Word({self.text!r} @ {self.x:.3f},{self.y:.3f} c={self.conf:.2f})"


def norm(s):
    return re.sub(r"[^a-z0-9$#]", "", s.lower())


class Vision:
    def __init__(self, screen):
        self.screen = screen

    def frame(self):
        return self.screen.grab()

    # -- OCR -------------------------------------------------------------
    def read(self, region=(0, 0, 1, 1), img=None, scale=1.0):
        """OCR a region (fractions). Returns list[Word] in client fractions."""
        fx0, fy0, fx1, fy1 = region
        if img is None:
            img = self.screen.grab(region)
            ox, oy = fx0, fy0
        else:
            h, w = img.shape[:2]
            img = img[int(fy0 * h):int(fy1 * h), int(fx0 * w):int(fx1 * w)]
            ox, oy = fx0, fy0
        if img.size == 0:
            return []
        if scale != 1.0:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        result, _ = _engine()(img)
        words = []
        rw = (fx1 - fx0) / img.shape[1]
        rh = (fy1 - fy0) / img.shape[0]
        for box, text, conf in result or []:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            words.append(Word(
                text=text,
                x=ox + (min(xs) + max(xs)) / 2 * rw,
                y=oy + (min(ys) + max(ys)) / 2 * rh,
                w=(max(xs) - min(xs)) * rw,
                h=(max(ys) - min(ys)) * rh,
                conf=float(conf),
            ))
        return words

    def find_text(self, *targets, region=(0, 0, 1, 1), words=None, exact=False):
        """First word matching any target (case/punct-insensitive substring)."""
        words = self.read(region) if words is None else words
        tnorm = [norm(t) for t in targets]
        for t in tnorm:
            for w in words:
                n = norm(w.text)
                if (n == t) if exact else (t in n):
                    return w
        return None

    def read_number(self, region, img=None):
        """Read digits (commas, $ stripped) from a HUD region, or None."""
        words = self.read(region, img=img, scale=2.0)
        text = "".join(w.text for w in sorted(words, key=lambda w: w.x))
        text = text.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
        digits = re.sub(r"[^0-9]", "", text)
        return int(digits) if digits else None

    def read_fraction(self, region, img=None):
        """Read 'a/b' (e.g. round 12/80). Returns (a, b) or None."""
        words = self.read(region, img=img, scale=2.0)
        text = "".join(w.text for w in sorted(words, key=lambda w: w.x))
        m = re.search(r"(\d+)\s*/\s*(\d+)", text)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None


def crop(img, region):
    h, w = img.shape[:2]
    fx0, fy0, fx1, fy1 = region
    return img[int(fy0 * h):int(fy1 * h), int(fx0 * w):int(fx1 * w)]


def save(img, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
