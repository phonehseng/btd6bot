"""Dev log: a voiceover script and a video of how the bot's bugs were found and fixed.

The git history is the script. Every commit message says what went wrong and
what changed; this tool lays the commits of one day out as narration, and
pairs each with footage from the rolling recording (btd6bot/recorder.py):

  * BEFORE - the last problem the bot's log recorded before the commit (an
    error, a defeat, a leak, a refused spot, a misread) - what the bug looked like
  * AFTER  - the start of the bot's next game on the new code

It also shows the pictures the bot's diagnostics left behind: the media
library docs/devlog/media/ listed in docs/devlog/media.json (each entry: file,
time, topic, caption; btd6bot/devmedia.py adds new ones):

  * PROGRESSION ARC - the video opens with how the bot learned to see the map,
    stage by stage (ARC_STAGES): blotchy heat maps from watching games, the
    Sandbox learner, exact geometry from the game files, the height
    correction, placement, and the latest loss. Every picture of those topics
    up to the end of the day is shown with its caption, under a short title
    card per stage. Early, bad attempts are kept on purpose: they are the arc.
  * every other picture of the day is shown after the title card of the first
    commit made after it (what was seen, then what was changed); pictures
    from after the day's last commit close the video.

A picture is on screen for 4-7 s (longer captions get more reading time),
with its date and topic at the top and its caption underneath. A short .mp4 in
the manifest is cut in the same way (at most VIDEO_MAX_SECONDS).

Output for a day YYYY-MM-DD:
  docs/devlog/YYYY-MM-DD.md                  the voiceover script (commit it)
  ~/Videos/BTD6 Bot/BTD6 bot devlog YYYY-MM-DD.mp4
      the progression arc, then per commit: a title card, the pictures made
      before it, the BEFORE clip, the AFTER clip

    python tools/devlog.py              # today
    python tools/devlog.py 2026-10-22   # another day

Moments before the recorder was running have no footage; the script still
covers them.
"""
import bisect
import functools
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import devmedia  # noqa: E402
from btd6bot import highlights as H  # noqa: E402
from btd6bot.recorder import ffmpeg_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEVLOG_DIR = ROOT / "docs" / "devlog"
PROBLEM = re.compile(r"game loop error|defeat|lost \d+ lives|invalid for|refus|misread|"
                     r"giving up|benched|could not|not responding|back at the menus", re.I)
BEFORE_WINDOW = 30 * 60      # look this far back for the problem a commit fixed
AFTER_WINDOW = 20 * 60       # and this far ahead for the next game

# The progression arc: (manifest topic, card title, card subtitle), in the
# order the story is told. Topics not listed here are shown with their commit.
ARC_STAGES = [
    ("track learning", "Watching bloons move", "heat maps from real games"),
    ("sandbox learner", "A private Sandbox", "learning the track with no towers in the way"),
    ("map geometry", "Reading the game's own map files", "exact track, water and blocked ground"),
    ("height correction", "The camera is tilted", "raised paths need a height correction"),
    ("placement", "Where towers can stand", "and what they can see from there"),
    ("losses", "Where it still goes wrong", "the latest loss, seen through the bot's eyes"),
]
ARC_TITLE = "How the bot learned to see the map"

# How pictures are shown
MEDIA_CACHE = H.CLIP_DIR / "devlog-media"   # encoded pictures, shared by every day's video
STILL_SECONDS = 4.0              # a picture stays on screen at least this long ...
STILL_MAX_SECONDS = 7.0          # ... and longer captions get reading time up to this
READING_CHARS_PER_SECOND = 25
VIDEO_MAX_SECONDS = 12.0         # a longer clip in the manifest is cut short
STAGE_CARD_SECONDS = 3.0
WIDTH, HEIGHT = (int(v) for v in H.CARD_SIZE.split("x"))
LABEL_BAND = 40                  # pixels above the picture for its date label
CAPTION_BAND = 150               # pixels below the picture for its caption (about 3 lines)
BACKGROUND = "0x101418"          # the colour of highlights.title_card, so cards and pictures match


def _style(**changes):
    """highlights.SUBTITLE_STYLE with some fields changed, e.g. _style(FontSize=13)."""
    fields = dict(field.split("=", 1) for field in H.SUBTITLE_STYLE.split(","))
    fields.update({key: str(value) for key, value in changes.items()})
    return ",".join(f"{key}={value}" for key, value in fields.items())


# Subtitle sizes are in ffmpeg's .srt canvas units (288 = the frame height):
# the caption is smaller than the clips' subtitles so up to 3 lines fit under
# a picture; a thinner box and small margins keep it inside the caption band.
CAPTION_STYLE = _style(FontSize=13, MarginV=4, Outline=3)
LABEL_FONT_SIZE = 9              # the date label above the picture


def _label_text(label):
    """A subtitle line drawn at the top centre in the small label font
    (.srt subtitles in ffmpeg understand {\\an8} and <font size>)."""
    return f'{H.TOP}<font size="{LABEL_FONT_SIZE}">{label}</font>'


# ---------------------------------------------------------------------------
# commits and the bot log
# ---------------------------------------------------------------------------

def day_bounds(day):
    """(start, end) epoch seconds of the local calendar day YYYY-MM-DD."""
    start = datetime.strptime(day, "%Y-%m-%d")
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


def day_commits(day):
    """[(epoch, hash, subject, body)] committed on `day`, oldest first."""
    start = datetime.strptime(day, "%Y-%m-%d")
    end = start + timedelta(days=1)
    for git in ("git", H.GIT):
        try:
            out = subprocess.run([git, "-C", str(ROOT), "log", f"--since={start:%Y-%m-%d %H:%M}",
                                  f"--until={end:%Y-%m-%d %H:%M}", "--format=%ct%x1f%h%x1f%s%x1f%b%x1e"],
                                 capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError:
            continue
        if out.returncode == 0:
            rows = []
            for rec in out.stdout.split("\x1e"):
                parts = rec.strip("\n").split("\x1f")
                if len(parts) == 4:
                    rows.append((int(parts[0]), parts[1], parts[2], parts[3].strip()))
            return sorted(rows)
    return []


def log_lines():
    """[(epoch, text)] of the bot log."""
    out = []
    with open(H.LOG_FILE, encoding="utf-8", errors="ignore") as f:
        for line in f:
            t = H._time(line)
            if t is not None:
                out.append((t, line[24:].strip()))
    return out


def before_moment(lines, t):
    """The last problem logged in the half hour before time t."""
    hits = [(lt, text) for lt, text in lines if t - BEFORE_WINDOW <= lt < t and PROBLEM.search(text)]
    return hits[-1] if hits else None


def after_moment(lines, t):
    """The first tower placed (a game on the new code) after time t."""
    hits = [(lt, text) for lt, text in lines if t < lt <= t + AFTER_WINDOW and "game: placed" in text]
    return hits[0] if hits else None


def narration(subject, body):
    """Commit message -> the points to read out: the subject, then one point
    per body bullet or paragraph (wrapped lines are joined back together)."""
    points, current = [subject.rstrip(".") + "."], []
    for raw in body.splitlines() + [""]:
        line = raw.strip()
        if line.lower().startswith(("co-authored-by", "signed-off-by")):
            continue
        starts_point = not line or line.startswith(("-", "*"))
        if starts_point and current:
            points.append(" ".join(current))
            current = []
        if line:
            current.append(line.lstrip("-*").strip())
    return points


def moment_owners(moments):
    """Neighbouring commits often share a moment: the same problem before
    them, the same next game after them. Each clip is shown once - a BEFORE
    with the first commit of such a run (the first fix made after the
    problem), an AFTER with the last one (that game ran all of their code).

    moments: [(before, after)] per commit, oldest first.
    Returns [(index showing its BEFORE, index showing its AFTER)] per commit."""
    owners = []
    for i, (before, after) in enumerate(moments):
        first = i
        while first > 0 and moments[first - 1][0] == before:
            first -= 1
        last = i
        while last + 1 < len(moments) and moments[last + 1][1] == after:
            last += 1
        owners.append((first, last))
    return owners


# ---------------------------------------------------------------------------
# the media library: which picture goes where
# ---------------------------------------------------------------------------

def load_media(manifest=None, media_dir=None):
    """Manifest entries whose file exists, oldest first, each with "t" (epoch
    seconds of its "time") and "path" (the file) added. Broken entries are skipped."""
    media_dir = Path(media_dir or devmedia.MEDIA_DIR)
    out = []
    for entry in devmedia.load_manifest(manifest):
        try:
            t = datetime.fromisoformat(entry["time"]).timestamp()
            path = media_dir / entry["file"]
            if not (entry["topic"] and entry["caption"]):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        if path.is_file():
            out.append({**entry, "t": t, "path": path})
    return sorted(out, key=lambda m: (m["t"], m["file"]))


def arc_media(media, until):
    """The progression arc up to time `until`: [(stage, [pictures])] for every
    ARC_STAGES stage that has pictures from before then, in story order; each
    stage's pictures oldest first. stage = (topic, title, subtitle)."""
    stages = []
    for stage in ARC_STAGES:
        pictures = [m for m in media if m["topic"] == stage[0] and m["t"] < until]
        if pictures:
            stages.append((stage, pictures))
    return stages


def assign_to_commits(media, commit_times, day_start, day_end, exclude=()):
    """Share the day's pictures (day_start <= time < day_end) out among the
    day's commits: each goes to the first commit made at or after it - what
    was seen, then what was changed. Commits made in the same second (one
    batch) count as one: their pictures go to the last of them, after all of
    their title cards. Pictures in `exclude` (file names, e.g. those already
    shown in the arc) are left out.
    commit_times: sorted epoch seconds.
    Returns ([pictures for each commit], [pictures after the last commit])."""
    per_commit, tail = [[] for _ in commit_times], []
    for m in media:
        if m["file"] in exclude or not day_start <= m["t"] < day_end:
            continue
        i = bisect.bisect_left(commit_times, m["t"])
        if i == len(commit_times):
            tail.append(m)
            continue
        while i + 1 < len(commit_times) and commit_times[i + 1] == commit_times[i]:
            i += 1                                  # the last commit of a same-second batch
        per_commit[i].append(m)
    return per_commit, tail


def still_seconds(caption):
    """How long a picture stays on screen: enough time to read its caption."""
    return min(STILL_MAX_SECONDS, max(STILL_SECONDS, len(caption) / READING_CHARS_PER_SECOND))


def media_label(m):
    """The small label above a picture, e.g. 'Oct 21 22:41  ·  track learning'."""
    return f"{datetime.fromtimestamp(m['t']):%b %d %H:%M}  ·  {m['topic']}"


# ---------------------------------------------------------------------------
# video parts (all encoded like highlights' clips, so they join with -c copy)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _encoder(ffmpeg):
    """highlights' encoder arguments (asking ffmpeg once per run, not per part)."""
    return tuple(H._encoder_args(ffmpeg))


def _fps(ffmpeg):
    """The frame rate the encoder arguments ask for (-r), as text."""
    args = _encoder(ffmpeg)
    return args[args.index("-r") + 1]


def _key(*parts):
    """A short, stable hash for cache file names: a part is rebuilt only when
    what it shows (or how it is drawn) changes."""
    return hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:12]


def frame_filter(srt_name):
    """ffmpeg filters: fit the picture between the label band and the caption
    band on a WIDTHxHEIGHT background, then burn in the subtitles.

    JPEG and PNG pictures decode as full-range colour; they are converted to
    the limited range video uses, and their colour tags cleared like the title
    cards', so the encoded stream matches the other parts for -c copy."""
    box_h = HEIGHT - LABEL_BAND - CAPTION_BAND
    return (f"scale={WIDTH}:{box_h}:force_original_aspect_ratio=decrease:force_divisible_by=2:out_range=tv,"
            f"format=yuv420p,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:{LABEL_BAND}+({box_h}-ih)/2:color={BACKGROUND},"
            f"setsar=1,subtitles={srt_name}:force_style='{CAPTION_STYLE}',"
            f"setparams=range=tv:color_primaries=unknown:color_trc=unknown:colorspace=unknown")


def _subtitle_text(text):
    """Caption text that libass shows as written ({...} would be read as a style tag)."""
    return " ".join(str(text).replace("{", "(").replace("}", ")").split())


def media_clip(ffmpeg, m, folder=MEDIA_CACHE):
    """One manifest entry as a video part: the picture (or the first
    VIDEO_MAX_SECONDS of a clip) with its date label on top and its caption
    underneath. Cached; None if ffmpeg fails."""
    is_video = m["path"].suffix.lower() in devmedia.VIDEO_SUFFIXES
    caption, label = _subtitle_text(m["caption"]), media_label(m)
    seconds = VIDEO_MAX_SECONDS if is_video else still_seconds(caption)
    name = "media_" + _key(m["file"], m["path"].stat().st_size, caption, label, seconds,
                           frame_filter(""), _encoder(ffmpeg))
    out = folder / f"{name}.mp4"
    if out.exists():
        return out
    folder.mkdir(parents=True, exist_ok=True)
    srt = folder / f"{name}.srt"
    H._write_srt(srt, [(0, seconds, caption), (0, seconds, _label_text(label))])
    if is_video:
        source = ["-t", f"{seconds:.2f}", "-i", str(m["path"])]
    else:   # a still: the same picture repeated at the video frame rate
        source = ["-loop", "1", "-framerate", _fps(ffmpeg), "-t", f"{seconds:.2f}", "-i", str(m["path"])]
    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", *source,
           "-vf", frame_filter(srt.name), *_encoder(ffmpeg), "-an", out.name]
    done = subprocess.run(cmd, cwd=str(folder), capture_output=True, text=True, timeout=300, creationflags=subprocess.CREATE_NO_WINDOW)
    srt.unlink(missing_ok=True)
    if done.returncode != 0:
        H.log.warning("dev log picture %s failed: %s", m["file"], done.stderr[-300:])
        out.unlink(missing_ok=True)
        return None
    return out


def card(ffmpeg, text, seconds=STAGE_CARD_SECONDS, folder=MEDIA_CACHE):
    """A title card (highlights.title_card), cached by its text. None on failure."""
    out = folder / f"card_{_key(text, seconds, _encoder(ffmpeg))}.mp4"
    folder.mkdir(parents=True, exist_ok=True)
    return out if out.exists() or H.title_card(ffmpeg, text, out, seconds) else None


def arc_cards_text(day, arc):
    """The texts of the arc's opening card and its stage cards."""
    first = datetime.fromtimestamp(min(m["t"] for _, pictures in arc for m in pictures))
    last = datetime.strptime(day, "%Y-%m-%d")
    span = f"{first:%b %d}" + ("" if first.date() == last.date() else f" to {last:%b %d}")
    opening = f"{ARC_TITLE}\na progression arc, {span}"
    stages = [f"{i}/{len(arc)}  {title}\n{subtitle}" for i, ((_, title, subtitle), _) in enumerate(arc, 1)]
    return opening, stages


# ---------------------------------------------------------------------------
# the voiceover script
# ---------------------------------------------------------------------------

def _footage_note(it, which):
    """'' when the BEFORE/AFTER clip is in the video with this commit, else why not."""
    if it[f"{which}_clip"]:
        return ""
    shared = it.get(f"{which}_with")
    return f" — footage shown with `{shared}`" if shared else " — no footage"


def _picture_lines(pictures):
    """Markdown bullets: one per picture, its caption as the narration."""
    return [f"- **{datetime.fromtimestamp(m['t']):%b %d %H:%M}** ({m['topic']}): {m['caption']}  "
            f"`media/{m['file']}`" for m in pictures]


def script_lines(day, items, arc, tail):
    """The voiceover script for `day` as Markdown lines."""
    out = [f"# Dev log {day}: finding and fixing the bot's bugs", "",
           "Voiceover script built from the day's commits and the bot's diagnostic pictures",
           "(tools/devlog.py, docs/devlog/media.json). Each commit entry: what the bot did wrong",
           "(BEFORE footage, pictures made before the fix), what changed, and the next game (AFTER).", ""]
    if arc:
        _, stage_cards = arc_cards_text(day, arc)
        out += ["## Progression arc: " + ARC_TITLE.lower(), "",
                "The video opens with these pictures, oldest first within each stage; read each",
                "caption as the narration. The early, rough attempts are the point: they show",
                "how far the bot's picture of the map has come.", ""]
        for text, (_, pictures) in zip(stage_cards, arc):
            out += [f"### {text.replace(chr(10), ': ', 1)}", ""] + _picture_lines(pictures) + [""]
    for it in items:
        when = datetime.fromtimestamp(it["t"]).strftime("%H:%M")
        out.append(f"## {when} — {it['subject']}  (`{it['hash']}`)")
        out.append("")
        if it["before"]:
            out.append(f"**Before** ({datetime.fromtimestamp(it['before'][0]):%H:%M:%S}): "
                       f"`{it['before'][1][:140]}`" + _footage_note(it, "before"))
            out.append("")
        if it["pictures"]:
            out += ["**Pictures** (shown after the title card):", ""] + _picture_lines(it["pictures"]) + [""]
        out.append("**Voiceover:**")
        out.append("")
        out.extend(f"- {point}" for point in narration(it["subject"], it["body"]))
        out.append("")
        if it["after"]:
            out.append(f"**After** ({datetime.fromtimestamp(it['after'][0]):%H:%M:%S}): "
                       f"`{it['after'][1][:140]}`" + _footage_note(it, "after"))
            out.append("")
    if tail:
        out += ["## After the last commit", ""] + _picture_lines(tail) + [""]
    return out


def write_script(day, items, arc=(), tail=()):
    DEVLOG_DIR.mkdir(parents=True, exist_ok=True)
    path = DEVLOG_DIR / f"{day}.md"
    path.write_text("\n".join(script_lines(day, items, list(arc), list(tail))) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# the day's video
# ---------------------------------------------------------------------------

def _arc_parts(ffmpeg, day, arc):
    """Video parts of the progression arc: the opening card, then per stage a
    card and its pictures."""
    if not arc:
        return []
    opening, stage_cards = arc_cards_text(day, arc)
    parts = [card(ffmpeg, opening, seconds=4.0)]
    for text, (_, pictures) in zip(stage_cards, arc):
        parts.append(card(ffmpeg, text))
        parts += [media_clip(ffmpeg, m) for m in pictures]
    return [p for p in parts if p]


def _commit_parts(ffmpeg, folder, it):
    """Video parts of one commit: its title card, the pictures made before it,
    then its BEFORE and AFTER clips (when this commit is the one showing them,
    see moment_owners). Fills in it["before_clip"] / it["after_clip"]."""
    t, h = it["t"], it["hash"]
    parts = []
    title = folder / f"{t}_{h}_0_card.mp4"     # the hash: several commits can share a second
    text = f"{datetime.fromtimestamp(t):%H:%M}  build {h}\n{it['subject'][:90]}"
    if title.exists() or H.title_card(ffmpeg, text, title):
        parts.append(title)
    parts += [p for p in (media_clip(ffmpeg, m) for m in it["pictures"]) if p]
    if it["before"] and not it["before_with"]:
        bt, btext = it["before"]
        clip = folder / f"{t}_{h}_1_before.mp4"
        if clip.exists() or H.cut_clip(ffmpeg, bt - 8, bt + 4, f"BEFORE: {btext[:90]}", clip, f"build {h} (before the fix)"):
            parts.append(clip)
            it["before_clip"] = clip
    if it["after"] and not it["after_with"]:
        at, _ = it["after"]
        clip = folder / f"{t}_{h}_2_after.mp4"
        if clip.exists() or H.cut_clip(ffmpeg, at - 2, at + 10, "AFTER the fix: the next game", clip, f"build {h}"):
            parts.append(clip)
            it["after_clip"] = clip
    return parts


def build(day):
    """Write the day's voiceover script and (with ffmpeg) its video.
    Returns (script path, video path or None, commit items, arc, tail pictures)."""
    ffmpeg = ffmpeg_path()
    lines = log_lines()
    day_start, day_end = day_bounds(day)

    # what goes where: the arc first, every other picture with its commit
    media = load_media()
    arc = arc_media(media, day_end)
    in_arc = {m["file"] for _, pictures in arc for m in pictures}
    commits = day_commits(day)
    per_commit, tail = assign_to_commits(media, [c[0] for c in commits], day_start, day_end, in_arc)
    moments = [(before_moment(lines, t), after_moment(lines, t)) for t, _, _, _ in commits]
    owners = moment_owners(moments)
    items = []
    for i, ((t, h, subject, body), pictures, (before, after)) in enumerate(zip(commits, per_commit, moments)):
        shows_before, shows_after = owners[i]
        items.append({"t": t, "hash": h, "subject": subject, "body": body, "pictures": pictures,
                      "before": before, "after": after, "before_clip": None, "after_clip": None,
                      # the commit whose part shows a shared moment (None: this one)
                      "before_with": commits[shows_before][1] if shows_before != i else None,
                      "after_with": commits[shows_after][1] if shows_after != i else None})

    video = None
    if ffmpeg:
        folder = H.CLIP_DIR / f"devlog-{day}"
        folder.mkdir(parents=True, exist_ok=True)
        order = _arc_parts(ffmpeg, day, arc)
        if order and commits:
            order += [p for p in [card(ffmpeg, f"{day}\nthe fixes, commit by commit")] if p]
        for it in items:
            order += _commit_parts(ffmpeg, folder, it)
        if tail:
            order += [p for p in [card(ffmpeg, "After the last commit")] + [media_clip(ffmpeg, m) for m in tail] if p]
        # a video needs something besides title cards: a picture or a clip
        if any(p.name.startswith("media_") or p.stem.endswith(("_before", "_after")) for p in order):
            H.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
            lst = folder / "all.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in order), encoding="utf-8")
            video = H.VIDEO_DIR / f"BTD6 bot devlog {day}.mp4"
            subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                            "-i", str(lst), "-c", "copy", str(video)], capture_output=True, timeout=600, creationflags=subprocess.CREATE_NO_WINDOW)
    # a shared moment only counts as "shown with" another commit if that one got the clip
    by_hash = {it["hash"]: it for it in items}
    for it in items:
        for which in ("before", "after"):
            owner = it[f"{which}_with"]
            if owner and not by_hash[owner][f"{which}_clip"]:
                it[f"{which}_with"] = None
    script = write_script(day, items, arc, tail)
    return script, video, items, arc, tail


if __name__ == "__main__":
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    script, video, items, arc, tail = build(day)
    with_footage = sum(1 for i in items if i["before_clip"] or i["after_clip"])
    print(f"{len(items)} commits; {with_footage} with footage")
    print(f"progression arc: {sum(len(p) for _, p in arc)} pictures in {len(arc)} stages; "
          f"{sum(len(i['pictures']) for i in items)} pictures with commits; {len(tail)} after the last commit")
    print("script:", script)
    print("video:", video)
