# PCStream

[![Build APK](https://github.com/mustafafoisol/pcstream/actions/workflows/android.yml/badge.svg)](https://github.com/mustafafoisol/pcstream/actions/workflows/android.yml)

Stream files from a folder on your PC to an Android 10+ phone on the same Wi-Fi.

- `pcserver/` — small Python 3 server (standard library only) that shares one folder read-only over HTTP, with `Range` support so you can seek.
- `app/` — Android client: browse the folder, tap a video or audio file, it plays with ExoPlayer.
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
3. Tap a folder to open it, a media file to stream it. **Up** or the back button goes back.

The URL and token are remembered, so it reconnects on the next launch.

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

Auth is `X-Auth-Token: <token>` or `?token=<token>`.
