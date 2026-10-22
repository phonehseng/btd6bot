"""The dev log's media library and how tools/devlog.py places its pictures
(no game, no ffmpeg needed).

Covers:
  * docs/devlog/media.json: every entry is complete, its file exists, pictures
    fit the video frame and stay small, captions fit under a picture;
  * the progression arc takes the arc topics in story order, only up to the
    end of the day being built;
  * every other picture goes to the first commit made at or after it (the
    last of a same-second batch), later ones to the tail, each day's
    pictures exactly once;
  * a BEFORE/AFTER moment shared by neighbouring commits is shown once;
  * the voiceover script gets a "Progression arc" section with the captions;
  * btd6bot.devmedia.save shrinks and records pictures, copies clips, is safe
    from several threads, and never raises.
Run: python tests/test_devlog_media_offline.py"""
import json
import logging
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import devlog  # noqa: E402
from btd6bot import devmedia  # noqa: E402

logging.getLogger("devmedia").setLevel(logging.CRITICAL)


def _picture(name, when, topic, caption="A caption."):
    """A media entry as load_media returns it."""
    t = datetime.fromisoformat(when).timestamp()
    return {"file": name, "time": when, "topic": topic, "caption": caption, "t": t, "path": Path(name)}


def _ts(when):
    return datetime.fromisoformat(when).timestamp()


# ---------------------------------------------------------------------------
# the committed library
# ---------------------------------------------------------------------------

def test_committed_manifest_is_complete():
    entries = devmedia.load_manifest()
    assert entries, "docs/devlog/media.json is missing or empty"
    files = set()
    for e in entries:
        assert set(e) >= {"file", "time", "topic", "caption"}, e
        datetime.fromisoformat(e["time"])                       # a valid ISO time
        assert e["topic"].strip() and e["caption"].strip(), e
        assert len(e["caption"]) <= devmedia.CAPTION_MAX_CHARS, e["file"]
        path = devmedia.MEDIA_DIR / e["file"]
        assert path.is_file(), f"{e['file']} is listed but missing"
        assert e["file"] not in files, f"{e['file']} is listed twice"
        files.add(e["file"])
        if path.suffix.lower() == ".jpg":
            img = devmedia.read_image(path)
            h, w = img.shape[:2]
            assert w <= devmedia.MAX_WIDTH and h <= devmedia.MAX_HEIGHT, (e["file"], w, h)
            assert path.stat().st_size <= devmedia.MAX_BYTES, (e["file"], path.stat().st_size)
        else:
            assert path.suffix.lower() in devmedia.VIDEO_SUFFIXES, e["file"]
    # nothing in the folder that the manifest does not know about
    on_disk = {p.name for p in devmedia.MEDIA_DIR.iterdir()}
    assert on_disk == files, f"unlisted files: {sorted(on_disk - files)}"


def test_committed_library_tells_the_whole_arc():
    media = devlog.load_media()
    arc = devlog.arc_media(media, until=float("inf"))
    assert [stage[0] for stage, _ in arc] == [topic for topic, _, _ in devlog.ARC_STAGES], \
        "every arc stage should have at least one picture"


# ---------------------------------------------------------------------------
# which picture goes where
# ---------------------------------------------------------------------------

def test_load_media_skips_broken_entries():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "a.jpg").write_bytes(b"x")
        (tmp / "b.jpg").write_bytes(b"x")
        entries = [{"file": "b.jpg", "time": "2026-10-22T01:00:00", "topic": "medals", "caption": "B"},
                   {"file": "a.jpg", "time": "2026-10-21T01:00:00", "topic": "medals", "caption": "A"},
                   {"file": "gone.jpg", "time": "2026-10-21T02:00:00", "topic": "medals", "caption": "missing file"},
                   {"file": "a.jpg", "time": "not a time", "topic": "medals", "caption": "bad time"},
                   {"file": "a.jpg", "time": "2026-10-21T03:00:00", "topic": "", "caption": "no topic"},
                   {"time": "2026-10-21T03:00:00", "topic": "medals", "caption": "no file"},
                   "not an entry"]
        (tmp / "media.json").write_text(json.dumps(entries), encoding="utf-8")
        media = devlog.load_media(tmp / "media.json", tmp)
    assert [m["caption"] for m in media] == ["A", "B"], "oldest first, broken ones skipped"
    assert media[0]["t"] == _ts("2026-10-21T01:00:00") and media[0]["path"].name == "a.jpg"


def test_arc_in_story_order_up_to_the_day():
    media = [_picture("loss.jpg", "2026-10-22T04:16:00", "losses"),
             _picture("geom.jpg", "2026-10-22T00:27:00", "map geometry"),
             _picture("heat2.jpg", "2026-10-21T20:59:00", "track learning"),
             _picture("heat1.jpg", "2026-10-21T15:25:00", "track learning"),
             _picture("medal.jpg", "2026-10-21T22:05:00", "medals")]        # not an arc topic
    media.sort(key=lambda m: m["t"])
    day1 = devlog.arc_media(media, devlog.day_bounds("2026-10-21")[1])
    assert [(stage[0], [m["file"] for m in pics]) for stage, pics in day1] == \
        [("track learning", ["heat1.jpg", "heat2.jpg"])], "the day before shows no later pictures"
    day2 = devlog.arc_media(media, devlog.day_bounds("2026-10-22")[1])
    assert [stage[0] for stage, _ in day2] == ["track learning", "map geometry", "losses"]
    opening, cards = devlog.arc_cards_text("2026-10-22", day2)
    assert opening.startswith(devlog.ARC_TITLE) and "Oct 21 to Oct 22" in opening
    assert cards[0].startswith("1/3") and cards[2].startswith("3/3")


def test_pictures_go_to_the_next_commit():
    day_start, day_end = devlog.day_bounds("2026-10-22")
    commits = [_ts("2026-10-22T01:00:00"), _ts("2026-10-22T02:00:00"),
               _ts("2026-10-22T03:00:00"), _ts("2026-10-22T03:00:00"), _ts("2026-10-22T03:00:00")]
    media = [_picture("yesterday.jpg", "2026-10-21T23:50:00", "medals"),
             _picture("early.jpg", "2026-10-22T00:10:00", "medals"),
             _picture("exact.jpg", "2026-10-22T01:00:00", "medals"),   # made in the commit's second
             _picture("mid.jpg", "2026-10-22T01:30:00", "menus"),
             _picture("batch.jpg", "2026-10-22T02:30:00", "hero picker"),
             _picture("in_arc.jpg", "2026-10-22T02:40:00", "losses"),
             _picture("late.jpg", "2026-10-22T04:16:00", "menus"),
             _picture("tomorrow.jpg", "2026-10-23T00:00:00", "menus")]
    per_commit, tail = devlog.assign_to_commits(media, commits, day_start, day_end, exclude={"in_arc.jpg"})
    names = [[m["file"] for m in pics] for pics in per_commit]
    assert names == [["early.jpg", "exact.jpg"], ["mid.jpg"], [], [], ["batch.jpg"]], names
    assert [m["file"] for m in tail] == ["late.jpg"]
    # the day's pictures are shared out exactly once
    shown = [n for pics in names for n in pics] + [m["file"] for m in tail]
    assert sorted(shown) == ["batch.jpg", "early.jpg", "exact.jpg", "late.jpg", "mid.jpg"]
    # no commits that day: everything is the tail
    per_commit, tail = devlog.assign_to_commits(media, [], day_start, day_end)
    assert per_commit == [] and len(tail) == 6


def test_shared_moments_are_shown_once():
    problem, game1, game2 = (100, "lost 5 lives"), (200, "placed dart"), (300, "placed ninja")
    moments = [(problem, game1), (problem, game1), (None, game2), (None, None)]
    owners = devlog.moment_owners(moments)
    assert [o[0] for o in owners[:2]] == [0, 0], "a BEFORE goes with the first fix after it"
    assert [o[1] for o in owners[:2]] == [1, 1], "an AFTER goes with the last commit that game ran"
    assert owners[2] == (2, 2)


def test_still_seconds_and_label():
    assert devlog.still_seconds("short") == devlog.STILL_SECONDS
    assert devlog.still_seconds("x" * 10_000) == devlog.STILL_MAX_SECONDS
    mid = "x" * int(devlog.READING_CHARS_PER_SECOND * 5)
    assert abs(devlog.still_seconds(mid) - 5) < 0.1
    assert devlog.media_label(_picture("a.jpg", "2026-10-21T22:41:00", "track learning")) == \
        "Oct 21 22:41  ·  track learning"
    assert "{" not in devlog._subtitle_text("a {\\b1} tag") and "font" in devlog._label_text("x")


def test_script_has_the_progression_arc():
    heat = _picture("heat.jpg", "2026-10-21T15:25:00", "track learning", "Blotchy first heat map.")
    medal = _picture("medal.jpg", "2026-10-22T00:20:00", "medals", "Medals read in one sweep.")
    late = _picture("late.jpg", "2026-10-22T04:16:00", "menus", "An event screen.")
    arc = devlog.arc_media([heat], float("inf"))
    items = [{"t": _ts("2026-10-22T00:30:00"), "hash": "abc1234", "subject": "Read map files",
              "body": "- one\n- two", "pictures": [medal], "before": (_ts("2026-10-22T00:10:00"), "lost 5 lives"),
              "after": None, "before_clip": None, "after_clip": None, "before_with": "fff0000", "after_with": None}]
    text = "\n".join(devlog.script_lines("2026-10-22", items, arc, [late]))
    assert "## Progression arc" in text and "### 1/1  Watching bloons move: heat maps" in text
    assert "Blotchy first heat map." in text and "`media/heat.jpg`" in text
    assert "**Pictures**" in text and "Medals read in one sweep." in text
    assert "footage shown with `fff0000`" in text
    assert "## After the last commit" in text and "An event screen." in text
    assert text.index("Progression arc") < text.index("Read map files") < text.index("After the last commit")


# ---------------------------------------------------------------------------
# btd6bot.devmedia.save
# ---------------------------------------------------------------------------

def test_save_shrinks_records_and_never_raises():
    with tempfile.TemporaryDirectory() as tmp:
        media_dir, manifest = Path(tmp) / "media", Path(tmp) / "media.json"
        # a big, busy picture: shrunk into the frame and under the size limit
        noisy = np.random.default_rng(1).integers(0, 255, (1600, 2600, 3), dtype=np.uint8)
        when = datetime(2026, 10, 22, 4, 16, 9)
        out = devmedia.save(noisy, "  Projected paths\nover a lost game ", "placement", when=when,
                            name="lc paths!", media_dir=media_dir, manifest=manifest)
        assert out is not None and out.name == "20261022_041609_lc_paths.jpg"
        img = devmedia.read_image(out)
        assert img.shape[1] <= devmedia.MAX_WIDTH and img.shape[0] <= devmedia.MAX_HEIGHT
        assert out.stat().st_size <= devmedia.MAX_BYTES
        # a greyscale file, dated by its modification time, from a path
        src = Path(tmp) / "mask.png"
        cv2.imwrite(str(src), np.zeros((50, 80), np.uint8))
        assert devmedia.save(src, "Masks", "hero picker", media_dir=media_dir, manifest=manifest)
        # a short clip is copied as it is
        clip = Path(tmp) / "leak.mp4"
        clip.write_bytes(b"not really a video")
        copied = devmedia.save(clip, "A leak", "losses", when=when, media_dir=media_dir, manifest=manifest)
        assert copied.suffix == ".mp4" and copied.read_bytes() == b"not really a video"
        # bad input: logged, None, nothing raised, manifest untouched
        assert devmedia.save(Path(tmp) / "nothing.png", "x", "y", media_dir=media_dir, manifest=manifest) is None
        assert devmedia.save(object(), "x", "y", media_dir=media_dir, manifest=manifest) is None
        entries = devmedia.load_manifest(manifest)
        assert sorted(e["topic"] for e in entries) == ["hero picker", "losses", "placement"]
        assert [e["time"] for e in entries] == sorted(e["time"] for e in entries), "kept in time order"
        first = next(e for e in entries if e["topic"] == "placement")
        assert first["caption"] == "Projected paths over a lost game" and first["time"] == "2026-10-22T04:16:09"
        # and devlog can read what devmedia wrote
        assert len(devlog.load_media(manifest, media_dir)) == 3


def test_save_from_several_threads():
    with tempfile.TemporaryDirectory() as tmp:
        media_dir, manifest = Path(tmp) / "media", Path(tmp) / "media.json"
        when = datetime(2026, 10, 22, 5, 0, 0)       # same second and name: files must not collide
        img = np.full((100, 160, 3), 128, np.uint8)
        threads = [threading.Thread(target=devmedia.save, args=(img, f"picture {i}", "placement"),
                                    kwargs={"when": when, "name": "same", "media_dir": media_dir,
                                            "manifest": manifest}) for i in range(12)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        entries = devmedia.load_manifest(manifest)
        assert len(entries) == 12 and len({e["file"] for e in entries}) == 12
        assert len(list(media_dir.iterdir())) == 12


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
