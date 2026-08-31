#!/usr/bin/env python3
"""Tiny LAN media server for the PCStream Android app.

Serves a single folder read-only over HTTP with Range support so the phone
can seek while streaming. Standard library only.

  python serve.py --root "D:/Videos" --port 8765 --token secret
"""

import argparse
import json
import mimetypes
import os
import posixpath
import re
import socket
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import screencap

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")
CHUNK = 256 * 1024

MEDIA_EXT = {
    ".mp4", ".mkv", ".webm", ".m4v", ".mov", ".3gp", ".ts", ".avi",
    ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wav",
}

mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("audio/flac", ".flac")


class Config:
    root = os.getcwd()
    token = ""
    screen = True          # screen sharing available at all
    audio = "auto"         # 'auto', 'none', or a dshow device name
    fps = 30
    height = 720           # 0 keeps the monitor's native height
    bitrate = "4M"


def safe_join(root, rel):
    """Resolve a URL path under root, refusing anything that escapes it."""
    rel = urllib.parse.unquote(rel or "")
    rel = posixpath.normpath("/" + rel.replace("\\", "/")).lstrip("/")
    full = os.path.realpath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        return None
    return full


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PCStream/1.0"

    # ---------- helpers ----------

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.address_string(), fmt % args))

    def _authorized(self):
        if not Config.token:
            return True
        supplied = self.headers.get("X-Auth-Token", "")
        if not supplied:
            q = urllib.parse.urlparse(self.path).query
            supplied = urllib.parse.parse_qs(q).get("token", [""])[0]
        return supplied == Config.token

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _fail(self, status, msg):
        self._send_json({"error": msg}, status)

    # ---------- routes ----------

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/ping":
            return self._send_json({
                "ok": True,
                "name": socket.gethostname(),
                "auth": bool(Config.token),
                "screen": Config.screen and screencap.ffmpeg_available(),
            })
        if not self._authorized():
            return self._fail(401, "bad or missing token")
        if path == "/api/list":
            rel = urllib.parse.parse_qs(parsed.query).get("path", [""])[0]
            return self._list(rel)
        if path.startswith("/media/"):
            return self._media(path[len("/media/"):])
        if path == "/api/screens":
            return self._screens()
        if path == "/screen.ts":
            return self._screen_stream(urllib.parse.parse_qs(parsed.query))
        return self._fail(404, "not found")

    def _list(self, rel):
        full = safe_join(Config.root, rel)
        if not full or not os.path.isdir(full):
            return self._fail(404, "no such folder")
        dirs, files = [], []
        try:
            entries = list(os.scandir(full))
        except OSError as e:
            return self._fail(403, str(e))
        for e in entries:
            try:
                if e.name.startswith("."):
                    continue
                child = posixpath.join(rel, e.name) if rel else e.name
                if e.is_dir():
                    dirs.append({"name": e.name, "path": child, "dir": True})
                elif e.is_file():
                    ext = os.path.splitext(e.name)[1].lower()
                    files.append({
                        "name": e.name,
                        "path": child,
                        "dir": False,
                        "size": e.stat().st_size,
                        "media": ext in MEDIA_EXT,
                        "mime": mimetypes.guess_type(e.name)[0] or "application/octet-stream",
                    })
            except OSError:
                continue
        by_name = lambda x: x["name"].lower()
        ordered = sorted(dirs, key=by_name) + sorted(files, key=by_name)
        return self._send_json({"path": rel, "entries": ordered})

    def _media(self, rel):
        full = safe_join(Config.root, rel)
        if not full or not os.path.isfile(full):
            return self._fail(404, "no such file")
        size = os.path.getsize(full)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"

        start, end = 0, size - 1
        partial = False
        rng = self.headers.get("Range")
        if rng:
            m = RANGE_RE.match(rng.strip())
            if not m:
                return self._range_not_satisfiable(size)
            lo, hi = m.group(1), m.group(2)
            if lo == "":                      # suffix range: last N bytes
                start = max(0, size - int(hi or 0))
            else:
                start = int(lo)
                if hi:
                    end = min(int(hi), size - 1)
            if start > end or start >= size:
                return self._range_not_satisfiable(size)
            partial = True

        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if self.command == "HEAD":
            return

        remaining = length
        try:
            with open(full, "rb") as f:
                f.seek(start)
                while remaining > 0:
                    buf = f.read(min(CHUNK, remaining))
                    if not buf:
                        break
                    self.wfile.write(buf)
                    remaining -= len(buf)
        except (BrokenPipeError, ConnectionResetError):
            pass  # player seeked away or closed the stream

    # ---------- screen sharing ----------

    def _screens(self):
        if not Config.screen:
            return self._fail(403, "screen sharing is disabled (--no-screen)")
        if not screencap.ffmpeg_available():
            return self._fail(501, "ffmpeg is not installed or not on PATH")
        audio = screencap.pick_audio_device(Config.audio)
        return self._send_json({
            "monitors": screencap.list_monitors(),
            "audio": audio,
            "audioDevices": screencap.list_audio_devices(),
            "encoder": screencap.pick_encoder()[0],
            "fps": Config.fps,
            "height": Config.height,
        })

    def _screen_stream(self, query):
        if not Config.screen:
            return self._fail(403, "screen sharing is disabled (--no-screen)")
        if not screencap.ffmpeg_available():
            return self._fail(501, "ffmpeg is not installed or not on PATH")

        def arg(name, default):
            try:
                return int(query.get(name, [default])[0])
            except (TypeError, ValueError):
                return default

        monitors = screencap.list_monitors()
        monitor = screencap.find_monitor(monitors, arg("monitor", 0))
        if monitor is None:
            return self._fail(404, "no such monitor")

        cmd = screencap.build_command(
            monitor,
            fps=max(5, min(60, arg("fps", Config.fps))),
            height=max(0, min(2160, arg("height", Config.height))),
            bitrate=query.get("bitrate", [Config.bitrate])[0],
            audio_device=screencap.pick_audio_device(Config.audio),
            draw_mouse=arg("mouse", 1) == 1,
        )
        self.log_message("screen: %s", " ".join(cmd[-14:]))

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    bufsize=0)
        except OSError as e:
            return self._fail(500, "could not start ffmpeg: %s" % e)

        # Drain stderr so a chatty ffmpeg can never block on a full pipe.
        state = {"stopping": False}
        threading.Thread(target=self._drain, args=(proc.stderr, state), daemon=True).start()

        # Live stream of unknown length: no Content-Length, close when done.
        self.send_response(200)
        self.send_header("Content-Type", "video/mp2t")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command == "HEAD":
            state["stopping"] = True
            proc.kill()
            return

        try:
            while True:
                buf = proc.stdout.read(32 * 1024)
                if not buf:
                    break
                self.wfile.write(buf)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # phone closed the player
        finally:
            # The phone is gone, so stop burning CPU on encoding immediately.
            state["stopping"] = True
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            self.log_message("screen: stopped")

    def _drain(self, stream, state):
        try:
            for line in iter(stream.readline, b""):
                # Once the viewer has left, ffmpeg complains about the closed
                # pipe on its way out; that is expected, not worth printing.
                if state["stopping"]:
                    continue
                text = line.decode("utf-8", "replace").rstrip()
                if text:
                    sys.stderr.write("[ffmpeg] %s\n" % text)
        except (ValueError, OSError):
            pass

    def _range_not_satisfiable(self, size):
        self.send_response(416)
        self.send_header("Content-Range", "bytes */%d" % size)
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    ap = argparse.ArgumentParser(description="Stream a PC folder to the PCStream Android app.")
    ap.add_argument("--root", default=os.getcwd(), help="folder to share (read-only)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--token", default=os.environ.get("PCSTREAM_TOKEN", ""),
                    help="shared secret the app must send (optional but recommended)")
    ap.add_argument("--no-screen", action="store_true", help="disable screen sharing")
    ap.add_argument("--audio", default="auto",
                    help="'auto' (find a loopback device), 'none', or a DirectShow device name")
    ap.add_argument("--fps", type=int, default=30, help="screen capture frame rate")
    ap.add_argument("--height", type=int, default=720,
                    help="scale the screen down to this height (0 = native)")
    ap.add_argument("--bitrate", default="4M", help="screen video bitrate")
    ap.add_argument("--list-audio", action="store_true",
                    help="print the DirectShow audio devices ffmpeg can see, then exit")
    args = ap.parse_args()

    if args.list_audio:
        devices = screencap.list_audio_devices()
        if not devices:
            print("No DirectShow audio devices found.")
        for d in devices:
            print("%-50s %s" % (d["name"], "<- loopback (desktop audio)" if d["loopback"] else "microphone"))
        return

    Config.root = os.path.realpath(args.root)
    Config.token = args.token
    Config.screen = not args.no_screen
    Config.audio = args.audio
    Config.fps = args.fps
    Config.height = args.height
    Config.bitrate = args.bitrate
    if not os.path.isdir(Config.root):
        sys.exit("root folder does not exist: " + Config.root)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    print("Sharing : %s" % Config.root)
    print("URL     : http://%s:%d" % (lan_ip(), args.port))
    print("Token   : %s" % (Config.token or "(none - open to your LAN)"))

    if Config.screen and screencap.ffmpeg_available():
        monitors = screencap.list_monitors()
        audio = screencap.pick_audio_device(Config.audio)
        print("Screens : %d (%s)" % (len(monitors), screencap.pick_encoder()[0]))
        if audio:
            print("Audio   : %s" % audio)
        elif Config.audio == "none":
            print("Audio   : off (--audio none)")
        else:
            print("Audio   : NONE - no desktop-audio device found, screen share will be silent.")
            print("          Run with --list-audio, or see README 'Desktop audio'.")
    elif Config.screen:
        print("Screens : unavailable - ffmpeg is not on PATH")

    print("Enter that URL in the Android app. Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
        srv.shutdown()


if __name__ == "__main__":
    main()
