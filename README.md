# Goku Teleport

A standalone **Linux desktop application** for x86_64 PCs, with an original, code-drawn anime teleport animation. The webcam remains off until **Start Preview** is pressed. The app can optionally write its processed frames to an existing Linux V4L2 loopback camera for use in meeting software.

## Features

- Live preview with selectable camera, resolution, frame rate, status, and gesture diagnostics.
- Step out of frame for background calibration. Hold a clear V sign with the index and middle fingers for one second to vanish; repeat to reappear. Either hand works, and the gesture can be held anywhere visible to the camera.
- `V` triggers the effect manually, `R` returns, and `Q`/`Esc` quits.
- Hold a V sign for one second to vanish and repeat it to reappear. The optional sound checkbox plays a randomly selected WAV cue on vanish.
- Optional V4L2 virtual camera output through `pyvirtualcam` and an already-installed `v4l2loopback` device.
- AI model files are downloaded on first camera start into `~/.cache/goku-teleport/models` (or `$XDG_CACHE_HOME/goku-teleport/models`). They are not downloaded during install or app startup.
- Includes an original synthesized teleport whoosh. Add WAV cues you own or are licensed to redistribute to `assets/sounds/` for random selection among multiple sounds. The public repository does not include third-party meme/reel audio.

## Run from source

Requires Python 3.10 or newer. Python 3.12 or 3.13 is a good starting point on distributions that provide it; Python 3.14 is supported by the dependency versions in `requirements.txt` where matching wheels are published. The setup script creates a local `.venv` and installs only into it.

```bash
./scripts/setup-dev.sh
./run.sh
```

The app window opens with the camera off. Select the webcam and press **Start Preview** when ready. On first use, the app needs internet access to download the two MediaPipe model files. After that, those files are cached locally.

To add a per-user launcher to your desktop menu without installing system packages:

```bash
./scripts/install-local.sh
```

Safe checks that never open a webcam:

```bash
./run.sh --check
./run.sh --smoke-test
./run.sh --list-cameras
```

Run the gesture geometry unit tests with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Flatpak

Flatpak is the preferred install format for common desktop Linux distributions. The manifest targets the Freedesktop 26.08 runtime and x86_64 wheels. The app requests Wayland and X11 sockets, network access for first-run models, and device access for camera input and optional V4L2 output. These permissions are declared in `org.codex.GokuTeleport.yml`.

Install `flatpak-builder` and the Flathub runtime with your distribution's software tools, then build a per-user bundle:

```bash
./scripts/build-flatpak.sh
```

The script creates `GokuTeleport.flatpak` in this folder. Install it for your account:

```bash
flatpak install --user --bundle ./GokuTeleport.flatpak
```

Launch **Goku Teleport** from your desktop's application menu. If the camera is not listed, check the Flatpak device permission and reopen the app. The app does not load kernel modules or change system permissions.

## AppImage

An optional AppImage build script is provided for x86_64. It requires PyInstaller and `appimagetool` to be available as user tools:

```bash
.venv/bin/python -m pip install pyinstaller
./scripts/build-appimage.sh
```

The resulting AppImage is `GokuTeleport-x86_64.AppImage`. AppImage bundling of camera devices still depends on host V4L2 support; it cannot provide a missing kernel driver.

## Virtual camera and meeting apps

Linux virtual camera output uses `v4l2loopback`; `pyvirtualcam` writes processed frames directly to that device. This app does not need OBS. To enable output, select **Send to virtual webcam** before starting the preview. If needed, enter a specific output device such as `/dev/video4`; otherwise leave it blank for autodetection. The terminal/status area reports the virtual device name.

Then choose the new device in the meeting app's camera settings. Discord, Zoom, Google Meet, Microsoft Teams, and other camera clients can use it when they support V4L2 webcams and can access the device. Some Flatpak or browser clients may need camera access granted or a restart after the virtual device starts. Meeting apps and Linux package sandboxing vary, so compatibility is not universal.

The vanish sound normally plays through the desktop audio output. **Test sound** plays a sample on demand. The bundled cue has been normalized to a -1 dBFS peak for stronger playback without clipping the file. To send it into a meeting, check **Mix sound with microphone for Discord** before starting preview. The app creates a temporary **Goku Teleport Mic** virtual input in the current PipeWire-PulseAudio/PulseAudio user session and mixes your default microphone into it. With that option enabled, the cue is sent both to your speakers and the virtual mic. In Discord, select **Goku Teleport Mic** under **Input Device** (it is a source, separate from the temporary mixer output); Discord may need to be restarted or its device list refreshed while the preview is running. The temporary route is removed when preview stops or the app quits. This uses the existing desktop audio server and does not install packages, use administrator access, or load a kernel module. It has not been verified with Discord or other meeting clients.

If the virtual microphone option reports that `pactl` is unavailable, the session audio server cannot be reached, or the input cannot be created, the app leaves the system unchanged and shows an error. The mix requires a working PulseAudio-compatible control interface plus `paplay` or `pw-play`; local playback without mic mixing can also use `aplay`.

If the app says no loopback camera is available, the required driver/device is missing or inaccessible. The app will not install or load it automatically. On Bazzite or another immutable distribution, use the supported system package workflow for that OS and kernel, or ask an administrator. Stop here until the system-level change has been approved.

## Troubleshooting

- **Camera cannot open:** refresh the camera list, select a different `/dev/videoN`, close other apps using the webcam, and check the device permissions.
- **Discord gets a robotic voice or removes the vanish cue:** choose **Goku Teleport Mic** as Discord's input (keep your real headphones/speakers as output), then turn Discord **Noise Suppression/Krisp** off for this mixed feed. Noise suppression is designed to remove non-voice sounds and can distort a processed mic mix; Discord recommends testing with suppression disabled when voice quality is poor. Use headphones to avoid speaker feedback. In **Voice & Video**, use **Let's Check** to confirm the selected input.
- **The preview appears dark or the hand is missed:** improve front lighting, show the full hand, and enable **Show gesture diagnostics in terminal**. The UI also displays the current recognition reason.
- **The app says face not detected:** move closer to the camera, keep your face visible, and avoid a bright light behind you.
- **Vanish looks incomplete:** step out of frame during calibration so the background contains no person. Recalibrate by restarting the preview.
- **Virtual camera missing in a meeting client:** start Goku Teleport with output enabled first, then reopen the meeting app's camera selector. Confirm the client is allowed to access the host camera device.
- **First start needs internet:** allow the app to reach `storage.googleapis.com` to cache its MediaPipe models. Subsequent starts use the cache.

## Linux support notes

### Supported platform

- **Operating system:** Linux only.
- **Architecture:** x86_64 for the provided Flatpak/AppImage build paths.
- **Developed on:** Bazzite 44 (Fedora Atomic base), KDE Plasma, Wayland.
- **Expected to work with:** Fedora/Bazzite, Ubuntu/Debian, Arch, and openSUSE desktop installations that provide compatible Python wheels (source mode), V4L2 webcam access, and a supported Qt desktop session. X11 and Wayland are both targeted.
- **Not verified:** every release/version of those distributions, ARM or other architectures, every kernel, Flatpak camera permissions on every desktop, or Discord/Zoom/Google Meet/Teams end-to-end behavior.

The project targets common Linux desktops; it does **not** claim literal support for every Linux distribution or meeting client. Virtual webcam output always needs an existing, working host `v4l2loopback` device. Flatpak and AppImage scripts are provided, but release builds should be validated on the target host before distribution.

## Audio asset licensing

The repository includes only a short original synthesized whoosh (`assets/sounds/teleport-whoosh.wav`). It does not redistribute the meme/reel sound previously used in a personal local copy. Add only audio you created or have permission to redistribute. The personal filename `assets/sounds/disappearing-gaster.wav` is ignored by Git so it is not accidentally published.

## Project layout

- `goku_teleport/` — desktop app and gesture geometry
- `assets/icon.svg` — original app icon
- `org.codex.GokuTeleport.yml` — Flatpak manifest
- `scripts/` — source setup and package build helpers
- `tests/` — camera-independent gesture geometry checks

## License

MIT. See `LICENSE`.
