# PCStream

Stream files from a folder on your PC to an Android 10+ phone on the same network.

- **`pcserver/`** — a small Python 3 server (standard library only) that shares one
  folder read-only over HTTP, with `Range` support so the phone can seek.
- **`app/`** — the Android client: browse the shared folder, tap a video or audio
  file, it plays with ExoPlayer (Media3).
- **`.github/workflows/android.yml`** — builds the debug APK on every push and
  uploads it as a workflow artifact.

## 1. PC setup

Needs Python 3.7+ on PATH.

```
python pcserver/serve.py --root "D:\Videos" --port 8765 --token mysecret
```

Or edit `SHARE_FOLDER` / `TOKEN` at the top of `pcserver/start-server.bat` and
double-click it. On startup it prints the URL to type into the app, e.g.
`http://192.168.1.20:8765`.

The first time, allow the port through Windows Firewall — right-click
`pcserver/allow-firewall.ps1` → *Run with PowerShell* as Administrator (it opens
TCP 8765 for **Private** networks only).

The token is a shared secret, not real security: the server is meant for a
trusted home network. It is read-only and refuses paths outside `--root`.

### Endpoints

| Route | Purpose |
| --- | --- |
| `GET /api/ping` | reachability check, returns the PC hostname |
| `GET /api/list?path=sub/dir` | JSON listing of a folder |
| `GET /media/<relative/path>` | the file itself, supports `Range` |

Auth is `X-Auth-Token: <token>` or `?token=<token>`.

## 2. Getting the APK

Push to GitHub; the **Build APK** workflow runs and attaches
`pcstream-debug-apk` to the run. Download it from the run's *Artifacts* section,
copy it to the phone, and install (allow "install unknown apps" for your file
manager).

The workflow provisions Gradle 8.9 via `gradle/actions/setup-gradle`, so no
`gradle-wrapper.jar` binary is committed to the repo.

## 3. Using the app

1. Make sure phone and PC are on the same Wi-Fi.
2. Enter the URL and token printed by `serve.py`, tap **Connect**.
3. Browse folders, tap a media file to stream it. **Up** / back navigates out.

Settings are remembered, so the app reconnects on launch.

## Notes

- `minSdk 29` (Android 10), `targetSdk 34`, `compileSdk 34`.
- Cleartext HTTP is enabled via `res/xml/network_security_config.xml` — Android 10
  blocks plain HTTP by default and the LAN server has no TLS certificate.
- Playable formats are whatever ExoPlayer + the device support. `.mkv` and `.mp4`
  are fine; some `.avi` files and exotic codecs are not.
