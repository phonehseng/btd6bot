"""Rolling screen recording of the bot at work, for highlight videos.

Runs as its own background process (started by run_forever.ps1, like the
status overlay):

    python -m btd6bot.recorder

  * records the desktop in 1-minute chunks with ffmpeg (GPU desktop capture
    "ddagrab", NVIDIA "h264_nvenc" encoding when available, else gdigrab and
    libx264), scaled to 1280 px wide, into ~/.btd6bot_cache/recordings
  * keeps the last KEEP_HOURS of chunks and deletes older ones
  * every few minutes turns newly finished games into subtitled highlight
    clips and a per-day video (btd6bot/highlights.py), and CHIMPS / Hard-family
    games into sped-up full-run videos (btd6bot/timelapse.py)

ffmpeg is not shipped with the bot: it is looked up in
~/.btd6bot_cache/tools/ffmpeg/*/bin/ffmpeg.exe (a BtbN Windows build), or the
BTD6BOT_FFMPEG environment variable. Stop: STOP file (like the bot), or a
NO_RECORD file to switch recording off while the bot keeps running.
"""
import ctypes
import glob
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path.home() / ".btd6bot_cache"
REC_DIR = CACHE / "recordings"
SEGMENT_SECONDS = 60
KEEP_HOURS = 4
WIDTH = 1280                 # recording width; height follows the screen's aspect
FPS = 30
HIGHLIGHT_EVERY = 300        # seconds between highlight passes

log = logging.getLogger("recorder")


def ffmpeg_path():
    """ffmpeg.exe from the env var, else the newest build in the tools cache."""
    env = os.environ.get("BTD6BOT_FFMPEG")
    if env and Path(env).exists():
        return Path(env)
    found = sorted(glob.glob(str(CACHE / "tools" / "ffmpeg" / "*" / "bin" / "ffmpeg.exe")))
    return Path(found[-1]) if found else None


def _has(ffmpeg, kind, name):
    """Does this ffmpeg build offer an encoder/filter called `name`?"""
    out = subprocess.run([str(ffmpeg), "-hide_banner", f"-{kind}"], capture_output=True,
                         text=True, timeout=30).stdout
    return any(line.split()[1:2] == [name] for line in out.splitlines() if len(line.split()) > 1)


def record_command(ffmpeg):
    """The ffmpeg command line for rolling 1-minute chunks of the desktop."""
    pattern = str(REC_DIR / "rec_%Y%m%d_%H%M%S.mkv")
    if _has(ffmpeg, "filters", "ddagrab"):
        # Desktop Duplication on the GPU, copied down once for scaling
        source = ["-filter_complex", f"ddagrab=framerate={FPS},hwdownload,format=bgra,scale={WIDTH}:-2,format=yuv420p"]
    else:
        source = ["-f", "gdigrab", "-framerate", str(FPS), "-i", "desktop",
                  "-vf", f"scale={WIDTH}:-2,format=yuv420p"]
    if _has(ffmpeg, "encoders", "h264_nvenc"):
        codec = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "30", "-g", str(FPS * 2)]
    else:
        codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-g", str(FPS * 2)]
    return [str(ffmpeg), "-hide_banner", "-loglevel", "error", *source, *codec,
            "-f", "segment", "-segment_time", str(SEGMENT_SECONDS), "-segment_atclocktime", "1", "-reset_timestamps", "1",
            "-strftime", "1", pattern]


def prune(keep_hours=KEEP_HOURS):
    """Delete chunks older than keep_hours (finished clips are kept elsewhere)."""
    cutoff = time.time() - keep_hours * 3600
    for f in [*REC_DIR.glob("rec_*.mkv"), *REC_DIR.glob("aud_*.*")]:
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def _record_audio(stop, ffmpeg):
    """Game audio in its own thread; a failure there never stops the video."""
    from . import gameaudio
    while not stop.is_set():
        if (ROOT / "NO_RECORD").exists():
            stop.wait(30)
            continue
        try:
            gameaudio.run(stop=stop, ffmpeg=ffmpeg)
        except Exception:
            log.exception("game audio failed - retrying in a minute")
            stop.wait(60)


def _single_instance():
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\BTD6BotRecorder")
    return ctypes.windll.kernel32.GetLastError() != 183   # 183 = already exists


def main():
    logging.basicConfig(filename=str(ROOT / "logs" / "recorder.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname).1s %(name)s: %(message)s")
    if not _single_instance():
        return 0
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        log.error("ffmpeg not found - see the module docstring")
        return 1
    REC_DIR.mkdir(parents=True, exist_ok=True)
    from . import highlights, timelapse
    proc, last_highlights = None, 0.0
    log.info("recorder started (%s)", ffmpeg)
    # the game's own sound (BloonsTD6.exe only, never the microphone), in
    # minute files next to the video chunks: see gameaudio.py
    from . import gameaudio
    audio_stop = threading.Event()
    audio = threading.Thread(target=_record_audio, args=(audio_stop, ffmpeg), name="gameaudio", daemon=True)
    audio.start()
    while not (ROOT / "STOP").exists():
        recording_wanted = not (ROOT / "NO_RECORD").exists()
        if recording_wanted and (proc is None or proc.poll() is not None):
            if proc is not None:
                log.warning("ffmpeg exited (code %s) - restarting", proc.returncode)
            proc = subprocess.Popen(record_command(ffmpeg), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=open(REC_DIR / "ffmpeg.log", "ab"),
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        elif not recording_wanted and proc is not None and proc.poll() is None:
            proc.terminate()
        prune()
        if time.time() - last_highlights > HIGHLIGHT_EVERY:
            last_highlights = time.time()
            try:
                highlights.update(ffmpeg)
            except Exception:
                log.exception("highlight pass failed")
            try:
                timelapse.update(ffmpeg)
            except Exception:
                log.exception("full-run pass failed")
        time.sleep(10)
    audio_stop.set()
    if proc is not None and proc.poll() is None:
        proc.terminate()
    log.info("recorder stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
