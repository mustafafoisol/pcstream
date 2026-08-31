# PCStream

[![Build APK](https://github.com/mustafafoisol/pcstream/actions/workflows/android.yml/badge.svg)](https://github.com/mustafafoisol/pcstream/actions/workflows/android.yml)

Two things, from your PC to an Android 10+ phone on the same Wi-Fi:

1. **Files** — browse a shared folder and stream any video or audio file from it.
2. **Screen** — watch one of your monitors live, with desktop audio.

- `pcserver/` — Python 3 server. File sharing is standard library only; screen sharing shells out to ffmpeg.
- `app/` — Android client: browse and play files, or pick a monitor and watch it live.
- `.github/workflows/android.yml` — builds the debug APK on every push.

## 1. Start the server on the PC

Needs Python 3.7+ on PATH.

```
python pcserver/serve.py --root "D:\Videos" --port 8765 --token mysecret
```

Or edit `SHARE_FOLDER` / `TOKEN` at the top of `pcserver/start-server.bat` and double-click it.

It prints the URL to type into the app:

```
Sharing : D:\Videos
URL     : http://192.168.1.20:8765
Token   : mysecret
```

**First run only:** allow the port through Windows Firewall — right-click `pcserver/allow-firewall.ps1` → *Run with PowerShell* as Administrator. It opens TCP 8765 for Private networks only.

## 2. Get the APK

Push to GitHub. The **Build APK** workflow runs automatically — open the run on
the *Actions* tab and download the `pcstream-debug-apk` artifact. Unzip it, copy
the APK to the phone, and install it (Android will ask you to allow "install
unknown apps" for whichever file manager you used).

To build it yourself instead, with Android Studio or a local SDK:

```
gradle assembleDebug     # output: app/build/outputs/apk/debug/app-debug.apk
```

## 3. Use the app

1. Phone and PC on the same Wi-Fi.
2. Enter the URL and token the server printed, tap **Connect**.
3. **Files:** tap a folder to open it, a media file to stream it. **Up** or the back button goes back.
4. **Screen:** tap **Screen**, pick a monitor, and it starts playing live.

The URL and token are remembered, so it reconnects on the next launch.

## Screen sharing

Needs **ffmpeg** on PATH (`choco install ffmpeg` or `winget install Gyan.FFmpeg`).
The server picks a hardware encoder automatically, probing `h264_nvenc` →
`h264_qsv` → `h264_amf` and falling back to `libx264`. It probes by actually
encoding a few frames, because an encoder can be listed and still be unusable —
NVENC on an older driver fails with `Cannot load cuMemAllocAsync`, for instance.

Tuning flags, all optional:

```
--fps 30        capture frame rate
--height 720    scale down to this height (0 = native)
--bitrate 4M    video bitrate
--no-screen     turn the feature off entirely
```

**Expect roughly 1–2 seconds of latency.** This is for watching, not for remote
control — you cannot game or do precise mouse work over it.

Capture is at your desktop's *logical* resolution, so a display running at 150%
scaling is captured at its scaled size (a 2880×1620 panel captures as 1920×1080).
That is a gdigrab limitation, and it is fine for phone-sized viewing.

### Desktop audio

This is the fiddly part. Windows has no built-in way for ffmpeg to record "what
the speakers are playing", so you need a loopback device. Check what you have:

```
python pcserver/serve.py --list-audio
```

If nothing is marked `<- loopback`, the screen share will be **silent** (the
server warns about this at startup). Fix it with whichever is easiest:

1. **Stereo Mix** — free, no install. Right-click the speaker icon → *Sound
   settings* → *More sound settings* → **Recording** tab → right-click → *Show
   Disabled Devices* → enable **Stereo Mix**. Not every sound driver has it.
2. **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — free; route your
   output through it, then capture `CABLE Output`.
3. **screen-capture-recorder** — provides a `virtual-audio-capturer` device
   built for exactly this, and does not take over your speakers.

The server finds any of these automatically. To force a specific one:

```
python pcserver/serve.py --root "D:\Videos" --audio "Stereo Mix (Realtek Audio)"
```

Video and audio are captured on independent clocks, so they can drift apart on a
long session; restarting the stream resyncs them.

## Notes

- `minSdk 29` (Android 10), `targetSdk 34`.
- The token is a shared secret for a trusted home network, not real auth. The server is read-only and refuses any path outside `--root` — but don't forward the port to the internet.
- Plain HTTP is allowed via `res/xml/network_security_config.xml`; Android 10 blocks cleartext by default and the LAN server has no TLS certificate.
- Playable formats are whatever ExoPlayer and the device support — `.mp4` and `.mkv` are fine, some `.avi` files and unusual codecs are not.

### Server endpoints

| Route | Purpose |
| --- | --- |
| `GET /api/ping` | reachability check, returns the PC hostname |
| `GET /api/list?path=sub/dir` | JSON listing of a folder |
| `GET /media/<relative/path>` | the file itself, supports `Range` |
| `GET /api/screens` | monitors, detected audio device, chosen encoder |
| `GET /screen.ts?monitor=0` | live MPEG-TS of that monitor (`-1` = all screens) |

Auth is `X-Auth-Token: <token>` or `?token=<token>`.
