"""Record the game's own sound - only BloonsTD6.exe, nothing else.

Windows 10 2004+ / 11 can capture the audio of one process and its children
("process loopback", the same thing OBS's Application Audio Capture uses).
This module does that with plain ctypes against the Windows audio API, so
the recordings hold the pops and the music of the game and never the
microphone, a call, or any other program.

Files: ~/.btd6bot_cache/recordings/aud_YYYYmmdd_HHMMSS_mmm.opus, one per
minute, named by the exact wall-clock time of their first sample (to the
millisecond). The stream is paced by the clock: when the game is silent the
gap is filled with silence, so sample n of a file is at name + n / RATE and
the audio lines up with the video chunks of recorder.py.

    python -m btd6bot.gameaudio            # record until stopped (Ctrl+C)
    python -m btd6bot.gameaudio --test 5   # 5 s test, print the level
"""
import ctypes
import ctypes.wintypes as wt
import logging
import subprocess
import threading
import time
import uuid
import wave
from datetime import datetime
from pathlib import Path

log = logging.getLogger("gameaudio")

RATE = 44100
CHANNELS = 2
BYTES_PER_FRAME = 2 * CHANNELS          # 16-bit PCM
SEGMENT_SECONDS = 60
OUT_DIR = Path.home() / ".btd6bot_cache" / "recordings"
PROCESS = "BloonsTD6.exe"

# ---------------------------------------------------------------- COM plumbing
ole32 = ctypes.OleDLL("ole32")
mmdevapi = ctypes.WinDLL("Mmdevapi")
HRESULT = ctypes.c_long


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        u = uuid.UUID(text)
        self.Data1, self.Data2, self.Data3 = u.fields[0], u.fields[1], u.fields[2]
        self.Data4[:] = list(u.bytes[8:])

    def __eq__(self, other):
        return bytes(self) == bytes(other)


IID_IUnknown = GUID("00000000-0000-0000-C000-000000000046")
IID_IAgileObject = GUID("94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90")
IID_CompletionHandler = GUID("41D949AB-9862-444A-80F6-C261334DA5EB")
IID_IAudioClient = GUID("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2")
IID_IAudioCaptureClient = GUID("C8ADBD64-E71E-48a0-A4DE-185C395CD317")

VT_BLOB = 65
AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2


class ACTIVATION_PARAMS(ctypes.Structure):
    _fields_ = [("ActivationType", ctypes.c_int), ("TargetProcessId", wt.DWORD), ("ProcessLoopbackMode", ctypes.c_int)]


class BLOB(ctypes.Structure):
    _fields_ = [("cbSize", wt.ULONG), ("pBlobData", ctypes.c_void_p)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", wt.USHORT), ("r1", wt.WORD), ("r2", wt.WORD), ("r3", wt.WORD), ("blob", BLOB),
                ("pad", ctypes.c_byte * 8)]


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", wt.WORD), ("nChannels", wt.WORD), ("nSamplesPerSec", wt.DWORD),
                ("nAvgBytesPerSec", wt.DWORD), ("nBlockAlign", wt.WORD), ("wBitsPerSample", wt.WORD), ("cbSize", wt.WORD)]


def vcall(obj, index, restype, *argtypes):
    """A bound COM method: the `index`-th entry of obj's vtable."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    fn = proto(vtbl[index])
    return lambda *a: fn(obj, *a)


def check(hr, what):
    if hr < 0:
        raise OSError(f"{what} failed: HRESULT 0x{hr & 0xFFFFFFFF:08X}")


class _Handler:
    """IActivateAudioInterfaceCompletionHandler (and IAgileObject, which the
    API requires), built as a ctypes vtable: ActivateCompleted fetches the
    activated IAudioClient and signals the waiting thread."""

    def __init__(self):
        self.done = threading.Event()
        self.client = ctypes.c_void_p()
        self.hr = 0
        QI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
        REF = ctypes.WINFUNCTYPE(wt.ULONG, ctypes.c_void_p)
        DONE = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p)
        self._fns = [QI(self._qi), REF(lambda this: 1), REF(lambda this: 1), DONE(self._completed)]
        self._vtbl = (ctypes.c_void_p * 4)(*[ctypes.cast(f, ctypes.c_void_p) for f in self._fns])
        self._obj = ctypes.pointer(ctypes.cast(self._vtbl, ctypes.c_void_p))
        self.ptr = ctypes.cast(self._obj, ctypes.c_void_p)

    def _qi(self, this, riid, ppv):
        if riid[0] in (IID_IUnknown, IID_IAgileObject, IID_CompletionHandler):
            ppv[0] = this
            return 0
        ppv[0] = None
        return -2147467262      # E_NOINTERFACE

    def _completed(self, this, op):
        hr = HRESULT()
        unk = ctypes.c_void_p()
        vcall(op, 3, HRESULT, ctypes.POINTER(HRESULT), ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(hr), ctypes.byref(unk))
        self.hr = hr.value
        self.client = unk
        self.done.set()
        return 0


def game_pid():
    """Process id of the running game, or None."""
    import win32process
    import win32api
    import win32con
    for pid in win32process.EnumProcesses():
        try:
            h = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            name = win32process.GetModuleFileNameEx(h, 0)
            win32api.CloseHandle(h)
        except Exception:
            continue
        if name.lower().endswith(PROCESS.lower()):
            return pid
    return None


class Capture:
    """The game's audio as 16-bit stereo PCM at RATE, read with read()."""

    def __init__(self, pid):
        ole32.CoInitializeEx(None, 0)       # COINIT_MULTITHREADED
        params = ACTIVATION_PARAMS(AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK, pid,
                                   PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE)
        pv = PROPVARIANT()
        pv.vt = VT_BLOB
        pv.blob.cbSize = ctypes.sizeof(params)
        pv.blob.pBlobData = ctypes.cast(ctypes.pointer(params), ctypes.c_void_p)
        self._keep = (params, pv)
        handler = _Handler()
        self._handler = handler
        op = ctypes.c_void_p()
        fn = mmdevapi.ActivateAudioInterfaceAsync
        fn.restype = HRESULT
        fn.argtypes = [wt.LPCWSTR, ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        check(fn("VAD\\Process_Loopback", ctypes.byref(IID_IAudioClient), ctypes.byref(pv), handler.ptr, ctypes.byref(op)),
              "ActivateAudioInterfaceAsync")
        if not handler.done.wait(5):
            raise OSError("audio activation timed out")
        check(handler.hr, "process loopback activation")
        self.client = handler.client
        fmt = WAVEFORMATEX(1, CHANNELS, RATE, RATE * BYTES_PER_FRAME, BYTES_PER_FRAME, 16, 0)
        flags = AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY
        check(vcall(self.client, 3, HRESULT, ctypes.c_int, wt.DWORD, ctypes.c_longlong, ctypes.c_longlong,
                    ctypes.POINTER(WAVEFORMATEX), ctypes.c_void_p)(0, flags, 2_000_000, 0, ctypes.byref(fmt), None),
              "IAudioClient.Initialize")
        cap = ctypes.c_void_p()
        check(vcall(self.client, 14, HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
            ctypes.byref(IID_IAudioCaptureClient), ctypes.byref(cap)), "IAudioClient.GetService")
        self.cap = cap
        self._next = vcall(cap, 5, HRESULT, ctypes.POINTER(wt.UINT))
        self._get = vcall(cap, 3, HRESULT, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.UINT),
                          ctypes.POINTER(wt.DWORD), ctypes.c_void_p, ctypes.c_void_p)
        self._release = vcall(cap, 4, HRESULT, wt.UINT)
        check(vcall(self.client, 10, HRESULT)(), "IAudioClient.Start")

    def read(self):
        """All PCM bytes captured since the last call (may be empty)."""
        out = bytearray()
        n = wt.UINT()
        while True:
            check(self._next(ctypes.byref(n)), "GetNextPacketSize")
            if n.value == 0:
                return bytes(out)
            data, frames, flags = ctypes.c_void_p(), wt.UINT(), wt.DWORD()
            check(self._get(ctypes.byref(data), ctypes.byref(frames), ctypes.byref(flags), None, None), "GetBuffer")
            size = frames.value * BYTES_PER_FRAME
            if flags.value & AUDCLNT_BUFFERFLAGS_SILENT or not data.value:
                out += bytes(size)
            else:
                out += ctypes.string_at(data.value, size)
            self._release(frames.value)

    def close(self):
        try:
            vcall(self.client, 11, HRESULT)()           # Stop
            vcall(self.cap, 2, wt.ULONG)()              # Release
            vcall(self.client, 2, wt.ULONG)()
        except Exception:
            pass


class Writer:
    """Minute files paced by the wall clock: silence fills any gap, so a
    file's sample n is at its start time + n / RATE."""

    def __init__(self, out_dir=OUT_DIR, ffmpeg=None):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = ffmpeg
        self.wav = None
        self.t0 = None          # wall-clock time of the current file's first sample
        self.frames = 0

    def _open(self, t):
        self._close()
        self.t0 = t
        self.frames = 0
        stamp = datetime.fromtimestamp(t).strftime("%Y%m%d_%H%M%S_") + f"{int(t * 1000) % 1000:03d}"
        self.path = self.out_dir / f"aud_{stamp}.wav"
        self.wav = wave.open(str(self.path), "wb")
        self.wav.setnchannels(CHANNELS)
        self.wav.setsampwidth(2)
        self.wav.setframerate(RATE)

    def _close(self):
        if self.wav is None:
            return
        self.wav.close()
        self.wav = None
        if self.ffmpeg:           # compress in the background: ~0.5 MB a minute
            opus = self.path.with_suffix(".opus")
            subprocess.Popen([str(self.ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(self.path),
                              "-c:a", "libopus", "-b:a", "64k", str(opus)], stdin=subprocess.DEVNULL,
                             creationflags=0x08000000).wait()
            if opus.exists():
                self.path.unlink(missing_ok=True)

    def write(self, pcm, now):
        """Add captured PCM; pad with silence up to `now` so the file keeps
        pace with the clock."""
        if self.wav is None:
            self._open(now - len(pcm) / BYTES_PER_FRAME / RATE)
        self.wav.writeframes(pcm)
        self.frames += len(pcm) // BYTES_PER_FRAME
        behind = int((now - self.t0) * RATE) - self.frames
        if behind > RATE // 10:       # more than 0.1 s of silence from the game
            self.wav.writeframes(bytes(behind * BYTES_PER_FRAME))
            self.frames += behind
        if self.frames >= SEGMENT_SECONDS * RATE:
            self._open(self.t0 + self.frames / RATE)

    def close(self):
        self._close()


def run(stop=None, test_seconds=None, ffmpeg=None):
    """Record the game's audio until `stop` is set (or test_seconds pass).
    Waits for the game, and starts again when it restarts."""
    stop = stop or threading.Event()
    writer = Writer(ffmpeg=ffmpeg)
    started = time.time()
    level = 0
    try:
        while not stop.is_set():
            pid = game_pid()
            if pid is None:
                writer.close()
                stop.wait(10)
                continue
            try:
                cap = Capture(pid)
            except OSError as e:
                log.warning("game audio unavailable: %s", e)
                stop.wait(30)
                continue
            log.info("recording the game's audio (pid %d)", pid)
            try:
                while not stop.is_set() and game_pid_alive(pid):
                    pcm = cap.read()
                    writer.write(pcm, time.time())
                    if pcm:
                        import array
                        a = array.array("h", pcm)
                        level = max(level, max(abs(x) for x in a[::50]) if a else 0)
                    if test_seconds and time.time() - started > test_seconds:
                        stop.set()
                    time.sleep(0.05)
            finally:
                cap.close()
    finally:
        writer.close()
    return level


def game_pid_alive(pid):
    import win32api
    import win32con
    import win32event
    try:
        h = win32api.OpenProcess(win32con.SYNCHRONIZE, False, pid)
    except Exception:
        return False
    alive = win32event.WaitForSingleObject(h, 0) == win32event.WAIT_TIMEOUT
    win32api.CloseHandle(h)
    return alive


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=float, help="record this many seconds and print the peak level")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname).1s %(name)s: %(message)s")
    if a.test:
        global OUT_DIR
        level = run(test_seconds=a.test)
        print(f"peak level {level} / 32767 ({'game audio captured' if level > 100 else 'silent: is the game muted?'})")
        return
    from .recorder import ffmpeg_path
    run(ffmpeg=ffmpeg_path())


if __name__ == "__main__":
    main()
