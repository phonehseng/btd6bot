"""Save diagnostic pictures (and short clips) as dev log content.

Any part of the bot, or a tool, that draws a diagnostic overlay - projected
bloon paths, a placement grid, a misread crop - can hand it to save() with a
caption saying what it shows:

    from btd6bot import devmedia
    devmedia.save(overlay, "Projected paths over the lost game: every tower "
                  "sat at the bottom while the bloons ran the top loops", "placement")

The picture is downscaled to fit the video frame, stored as a JPEG in
docs/devlog/media/ and listed in docs/devlog/media.json:

    [{"file": "20261022_041609_lc_paths.jpg", "time": "2026-10-22T04:16:09",
      "topic": "losses", "caption": "..."}, ...]

tools/devlog.py turns that list into video: pictures about how the bot sees
the map open each day's dev log as a "progression arc", and every other
picture appears after the title card of the commit that followed it.

save() never raises: a failed save is logged and returns None, so a
diagnostic can never break a game.
"""
import json
import logging
import os
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .highlights import CARD_SIZE

ROOT = Path(__file__).resolve().parents[1]
MEDIA_DIR = ROOT / "docs" / "devlog" / "media"
MANIFEST = ROOT / "docs" / "devlog" / "media.json"

# Pictures are shown in the dev log video, so nothing bigger than its frame is kept.
MAX_WIDTH, MAX_HEIGHT = (int(v) for v in CARD_SIZE.split("x"))
MAX_BYTES = 150_000                      # per picture, to keep the repository small
JPEG_QUALITIES = (90, 84, 78, 72, 66, 60, 54)  # tried in turn until a picture fits MAX_BYTES
SHRINK_STEP = 0.85                       # ... then the picture is shrunk by this and tried again
VIDEO_SUFFIXES = (".mp4",)               # copied as they are (keep them short)
CAPTION_MAX_CHARS = 180                  # about three lines under a picture in the video

log = logging.getLogger("devmedia")
_lock = threading.RLock()                # one writer at a time (file names, media.json)


# ---------------------------------------------------------------------------
# the manifest (docs/devlog/media.json)
# ---------------------------------------------------------------------------

def load_manifest(path=None):
    """The manifest's entries, oldest first; [] when it is missing or unreadable."""
    path = Path(path or MANIFEST)
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _write_manifest(entries, path):
    """Write the whole list atomically (a crash mid-write cannot truncate it)."""
    entries = sorted(entries, key=lambda e: (e.get("time", ""), e.get("file", "")))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def add_entry(entry, path=None):
    """Append one entry to the manifest (replacing an older entry for the same file)."""
    path = Path(path or MANIFEST)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = [e for e in load_manifest(path) if e.get("file") != entry["file"]]
        _write_manifest(entries + [entry], path)


# ---------------------------------------------------------------------------
# pictures
# ---------------------------------------------------------------------------

def read_image(path):
    """Read an image file as a BGR array (works for non-ASCII paths, unlike cv2.imread)."""
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"not an image: {path}")
    return img


def fit(img, max_width=MAX_WIDTH, max_height=MAX_HEIGHT):
    """Downscale to fit max_width x max_height, keeping the aspect ratio.
    Small pictures are left as they are (the video scales them up when shown)."""
    h, w = img.shape[:2]
    scale = min(max_width / w, max_height / h)
    if scale >= 1:
        return img
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA)


def encode_jpeg(img, max_bytes=MAX_BYTES):
    """JPEG bytes at the best quality that fits max_bytes. A busy picture that
    does not fit even at the lowest quality is shrunk a little and tried again."""
    while True:
        for quality in JPEG_QUALITIES:
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ok:
                raise ValueError("JPEG encoding failed")
            if len(buf) <= max_bytes:
                return buf.tobytes()
        h, w = img.shape[:2]
        if min(h, w) < 64:                     # tiny already: give up on the size limit
            return buf.tobytes()
        img = cv2.resize(img, (round(w * SHRINK_STEP), round(h * SHRINK_STEP)), interpolation=cv2.INTER_AREA)


def slug(text, max_len=40):
    """'Lost game: paths!' -> 'lost_game_paths' (for file names)."""
    out = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return out[:max_len].rstrip("_") or "image"


def _free_name(folder, stem, suffix):
    """stem+suffix, or stem_2+suffix, ... whichever does not exist yet."""
    candidate, n = folder / f"{stem}{suffix}", 2
    while candidate.exists():
        candidate, n = folder / f"{stem}_{n}{suffix}", n + 1
    return candidate


# ---------------------------------------------------------------------------
# the one call the bot needs
# ---------------------------------------------------------------------------

def save(image_or_path, caption, topic, when=None, name=None, media_dir=None, manifest=None):
    """Store a picture (a BGR numpy array or an image file) or a short .mp4
    clip as dev log content. Returns the stored file's Path, or None on any
    failure (logged, never raised).

    caption  one or two plain sentences: what it shows and why it mattered
    topic    e.g. "track learning", "map geometry", "placement", "medals"
    when     the moment it shows (datetime); default: the file's modification
             time for a path, else now
    name     a short file name hint; default: the source file name or the caption
    media_dir, manifest   where to store it (tests); default docs/devlog/media
             and the media.json next to that folder
    """
    try:
        media_dir = Path(media_dir or MEDIA_DIR)
        manifest = Path(manifest) if manifest else media_dir.parent / MANIFEST.name
        source = None if isinstance(image_or_path, np.ndarray) else Path(image_or_path)
        if when is None:
            when = datetime.fromtimestamp(source.stat().st_mtime) if source else datetime.now()
        stem = f"{when:%Y%m%d_%H%M%S}_{slug(name or (source.stem if source else caption))}"
        is_video = source is not None and source.suffix.lower() in VIDEO_SUFFIXES
        if not is_video:   # prepare the JPEG before taking the lock
            img = image_or_path if source is None else read_image(source)
            if img.ndim == 2:                                  # greyscale masks
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif img.shape[2] == 4:                            # drop transparency
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            jpeg = encode_jpeg(fit(img))
        caption = " ".join(str(caption).split())
        if len(caption) > CAPTION_MAX_CHARS:
            log.warning("dev media caption is %d characters; the video shows about %d",
                        len(caption), CAPTION_MAX_CHARS)
        with _lock:        # choosing a free name and writing it must not interleave
            media_dir.mkdir(parents=True, exist_ok=True)
            if is_video:
                target = _free_name(media_dir, stem, source.suffix.lower())
                shutil.copyfile(source, target)
            else:
                target = _free_name(media_dir, stem, ".jpg")
                target.write_bytes(jpeg)
            add_entry({"file": target.name, "time": when.isoformat(timespec="seconds"),
                       "topic": str(topic), "caption": caption}, manifest)
        return target
    except Exception as e:  # noqa: BLE001 - a diagnostic must never break the bot
        log.warning("dev media not saved (%s): %s", topic, e)
        return None
