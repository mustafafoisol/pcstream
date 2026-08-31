"""Screen + desktop-audio capture, encoded to MPEG-TS on stdout by ffmpeg.

Windows only. Video comes from gdigrab cropped to one monitor; audio, when a
loopback device exists, comes from DirectShow. See pick_audio_device() for why
that is the fiddly half.
"""

import ctypes
import ctypes.wintypes as wintypes
import re
import shutil
import subprocess

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

# DirectShow names that are actually "what the speakers are playing" rather
# than a microphone. Checked lowercase, as substrings.
LOOPBACK_HINTS = (
    "stereo mix",
    "virtual-audio-capturer",
    "what u hear",
    "wave out mix",
    "cable output",
    "voicemeeter out",
    "loopback",
)

# Preference order. NVENC is listed first but is often unusable on older
# drivers, which is exactly why every candidate is probed before use.
ENCODER_CANDIDATES = (
    ("h264_nvenc", ["-preset", "p4", "-tune", "ll", "-rc", "cbr"]),
    ("h264_qsv", ["-preset", "veryfast"]),
    ("h264_amf", ["-usage", "lowlatency"]),
    ("libx264", ["-preset", "ultrafast", "-tune", "zerolatency"]),
)

_encoder_cache = None


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


# --------------------------------------------------------------------------
# monitors
# --------------------------------------------------------------------------

class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_RECT), ctypes.c_double
)


def list_monitors():
    """Monitors in virtual-desktop coordinates.

    Deliberately does NOT call SetProcessDPIAware: gdigrab is DPI-unaware and
    captures the scaled desktop, so these rectangles have to be in the same
    logical coordinate space ffmpeg will use. Making this process DPI-aware
    reports physical pixels instead and the crop lands outside gdigrab's idea
    of the desktop on any display with scaling.
    """
    user32 = ctypes.windll.user32
    found = []

    def callback(hmon, hdc, lprect, data):
        r = lprect.contents
        found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    user32.EnumDisplayMonitors(0, 0, _MONITORENUMPROC(callback), 0)

    monitors = []
    for i, (x, y, w, h) in enumerate(found):
        # gdigrab needs even dimensions for yuv420p/nv12.
        w -= w % 2
        h -= h % 2
        monitors.append({
            "index": i,
            "x": x, "y": y, "width": w, "height": h,
            "primary": x == 0 and y == 0,
            "label": "Screen %d - %dx%d%s" % (i + 1, w, h, " (primary)" if x == 0 and y == 0 else ""),
        })

    if monitors:
        # A pseudo-entry for "everything at once".
        left = min(m["x"] for m in monitors)
        top = min(m["y"] for m in monitors)
        right = max(m["x"] + m["width"] for m in monitors)
        bottom = max(m["y"] + m["height"] for m in monitors)
        if len(monitors) > 1:
            monitors.append({
                "index": -1,
                "x": left, "y": top,
                "width": (right - left) - (right - left) % 2,
                "height": (bottom - top) - (bottom - top) % 2,
                "primary": False,
                "label": "All screens - %dx%d" % (right - left, bottom - top),
            })
    return monitors


def find_monitor(monitors, index):
    for m in monitors:
        if m["index"] == index:
            return m
    return None


# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------

def list_audio_devices():
    """DirectShow audio inputs, each flagged as loopback-capable or not."""
    try:
        proc = subprocess.run(
            [FFMPEG, "-hide_banner", "-f", "dshow", "-list_devices", "true", "-i", "dummy"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    devices = []
    for line in (proc.stderr or "").splitlines():
        m = re.search(r'"([^"]+)"\s*\(audio\)', line)
        if not m:
            continue
        name = m.group(1)
        low = name.lower()
        devices.append({
            "name": name,
            "loopback": any(h in low for h in LOOPBACK_HINTS),
        })
    return devices


def pick_audio_device(requested=""):
    """Resolve the --audio argument to a concrete dshow device name.

    'none' disables audio, 'auto' looks for a loopback device and silently
    gives up (video only) if the PC has none, and anything else is used
    verbatim so an unusual device name still works.
    """
    if requested == "none":
        return None
    devices = list_audio_devices()
    if requested and requested != "auto":
        for d in devices:
            if d["name"].lower() == requested.lower():
                return d["name"]
        return requested          # trust the user; ffmpeg will complain if wrong
    for d in devices:
        if d["loopback"]:
            return d["name"]
    return None


# --------------------------------------------------------------------------
# encoder
# --------------------------------------------------------------------------

def _encoder_works(name):
    """Probe by actually encoding a few frames - listing is not enough."""
    try:
        proc = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
             "-frames:v", "5", "-c:v", name, "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
        return proc.returncode == 0 and not proc.stderr.strip()
    except (OSError, subprocess.SubprocessError):
        return False


def pick_encoder():
    """(encoder name, extra args). Probed once, then cached."""
    global _encoder_cache
    if _encoder_cache is None:
        for name, args in ENCODER_CANDIDATES:
            if _encoder_works(name):
                _encoder_cache = (name, args)
                break
        else:
            _encoder_cache = ("libx264", ["-preset", "ultrafast", "-tune", "zerolatency"])
    return _encoder_cache


# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------

def build_command(monitor, fps=30, height=720, bitrate="4M", audio_device=None, draw_mouse=True):
    """ffmpeg argv that writes MPEG-TS to stdout."""
    encoder, encoder_args = pick_encoder()
    pix_fmt = "nv12" if encoder == "h264_qsv" else "yuv420p"

    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error",
        "-fflags", "+genpts",
        # video: one monitor out of the virtual desktop
        "-f", "gdigrab",
        "-framerate", str(fps),
        "-draw_mouse", "1" if draw_mouse else "0",
        "-offset_x", str(monitor["x"]),
        "-offset_y", str(monitor["y"]),
        "-video_size", "%dx%d" % (monitor["width"], monitor["height"]),
        "-i", "desktop",
    ]

    if audio_device:
        cmd += [
            "-f", "dshow",
            "-audio_buffer_size", "50",     # smaller buffer, less audio latency
            "-i", "audio=%s" % audio_device,
        ]

    # Downscale only when the monitor is taller than the requested height.
    if height and monitor["height"] > height:
        cmd += ["-vf", "scale=-2:%d" % height]

    cmd += [
        "-c:v", encoder, *encoder_args,
        "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", bitrate,
        "-g", str(fps * 2),                 # keyframe every 2s, so the phone starts fast
        "-pix_fmt", pix_fmt,
        "-fps_mode", "cfr",
    ]

    if audio_device:
        cmd += [
            "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000",
            # Independent capture clocks drift; resample to keep A/V together.
            "-af", "aresample=async=1000",
        ]

    cmd += ["-f", "mpegts", "-muxdelay", "0", "-muxpreload", "0", "pipe:1"]
    return cmd
