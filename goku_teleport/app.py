"""Goku Teleport: original anime-style webcam effect for Linux."""

from __future__ import annotations

import argparse
import os
import queue
import random
import sys
import time
import urllib.request
from pathlib import Path

_cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
_mpl_cache = _cache_home / "goku-teleport" / "matplotlib"
try:
    _mpl_cache.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_cache))


def configure_qt() -> None:
    """Prefer the Qt plugins bundled with PySide over OpenCV's private Qt copy."""
    try:
        import PySide6

        plugin_root = Path(PySide6.__file__).parent / "Qt" / "plugins"
        if (plugin_root / "platforms").is_dir():
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugin_root / "platforms")
            os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_root))
    except ImportError:
        pass


configure_qt()

import cv2
import mediapipe as mp
import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .gesture import is_v_sign
from .audio import AudioRouter


APP_NAME = "Goku Teleport"
APP_ID = "org.codex.GokuTeleport"
WINDOW_TITLE = "Goku Teleport — Instant Transmission"
CALIBRATION_SECONDS = 3.5
GESTURE_HOLD_SECONDS = 1.0
EFFECT_SECONDS = 1.15
MODEL_URLS = {
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task"
    ),
    "selfie_segmenter.tflite": (
        "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
        "selfie_segmenter_landscape/float16/1/selfie_segmenter_landscape.tflite"
    ),
}


def cache_dir() -> Path:
    return _cache_home / "goku-teleport" / "models"


def sound_files() -> list[Path]:
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / "assets" / "sounds")
    candidates.extend((
        Path("/app/share/goku-teleport/sounds"),
        Path(__file__).resolve().parents[1] / "assets" / "sounds",
    ))
    for folder in candidates:
        files = sorted(folder.glob("*.wav")) if folder.is_dir() else []
        if files:
            return files
    return []


def ensure_models(report) -> dict[str, Path]:
    folder = cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for filename, url in MODEL_URLS.items():
        target = folder / filename
        if target.exists() and target.stat().st_size > 100_000:
            result[filename] = target
            continue
        report(f"Downloading first-run AI model: {filename}")
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "GokuTeleport/0.1"})
            with urllib.request.urlopen(request, timeout=45) as response, temporary.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            if temporary.stat().st_size < 100_000:
                raise RuntimeError(f"Downloaded model appears incomplete: {filename}")
            temporary.replace(target)
            result[filename] = target
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    return result


def smoothstep(edge0: float, edge1: float, x: np.ndarray | float):
    if edge1 <= edge0:
        return np.asarray(x >= edge1, dtype=np.float32)
    t = np.clip((np.asarray(x, dtype=np.float32) - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def subject_center(mask: np.ndarray) -> tuple[int, int]:
    moments = cv2.moments((mask > 0.18).astype(np.uint8))
    if moments["m00"] <= 1:
        height, width = mask.shape[:2]
        return width // 2, height // 2
    return int(moments["m10"] / moments["m00"]), int(moments["m01"] / moments["m00"])


def render_energy_lines(frame: np.ndarray, mask: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0.01 or mask is None:
        return frame
    binary = (mask > 0.22).astype(np.uint8)
    ys, xs = np.where(binary > 0)
    if xs.size == 0:
        return frame
    overlay = frame.copy()
    edge = cv2.morphologyEx(binary, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    overlay[edge > 0] = (225, 238, 255)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if contours:
        contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
        center = np.array(subject_center(mask), dtype=np.float32)
        spacing = max(1, len(contour) // 18)
        dash_length = max(4, min(10, int(min(frame.shape[:2]) * 0.018)))
        # Short outward ticks sit on the contour; none cross the person vertically.
        for index in range(0, len(contour), spacing):
            point = contour[index].astype(np.float32)
            before = contour[(index - 2) % len(contour)].astype(np.float32)
            after = contour[(index + 2) % len(contour)].astype(np.float32)
            tangent = after - before
            normal = np.array([tangent[1], -tangent[0]], dtype=np.float32)
            norm = float(np.linalg.norm(normal))
            if norm < 1e-4:
                continue
            normal /= norm
            if float(np.dot(normal, point - center)) < 0:
                normal *= -1
            end = point + normal * dash_length
            cv2.line(
                overlay,
                tuple(np.rint(point).astype(int)),
                tuple(np.rint(end).astype(int)),
                (225, 238, 255), 1, cv2.LINE_AA,
            )
    opacity = min(0.42, amount * 0.42)
    return cv2.addWeighted(frame, 1.0 - opacity, overlay, opacity, 0)


def composite_teleport(
    live: np.ndarray,
    background: np.ndarray,
    mask: np.ndarray | None,
    progress: float,
    reappearing: bool,
) -> np.ndarray:
    if mask is None or mask.shape[:2] != live.shape[:2]:
        return live.copy()
    p = float(np.clip(progress, 0.0, 1.0))
    if p >= 1.0:
        visible = np.ones_like(mask) if reappearing else np.zeros_like(mask)
    else:
        # The solid person clears quickly; the fine outline/streaks linger briefly.
        subject_visibility = float(smoothstep(0.58, 1.0, p)) if reappearing else (
            1.0 - float(smoothstep(0.0, 0.42, p))
        )
        visible = np.full_like(mask, subject_visibility, dtype=np.float32)
    alpha = np.clip(mask * visible, 0.0, 1.0)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.1)[:, :, None]
    out = np.clip(live * alpha + background * (1.0 - alpha), 0, 255).astype(np.uint8)

    line_strength = 1.0 - float(smoothstep(0.40, 0.94, p))
    out = render_energy_lines(out, mask, line_strength)
    return out


class CameraWorker(QThread):
    frame_ready = Signal(QImage)
    state_changed = Signal(str, str, float)
    log_line = Signal(str)
    failed = Signal(str)
    sound_requested = Signal()

    def __init__(self, device: str, width: int, height: int, fps: int,
                 virtual_enabled: bool, virtual_device: str, debug: bool):
        super().__init__()
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.virtual_enabled = virtual_enabled
        self.virtual_device = virtual_device
        self.debug = debug
        self.stop_requested = False
        self.commands: queue.Queue[str] = queue.Queue()

    def submit_command(self, command: str) -> None:
        self.commands.put(command)

    def stop(self) -> None:
        self.stop_requested = True

    def _say(self, message: str) -> None:
        self.log_line.emit(message)

    def run(self) -> None:
        capture = None
        virtual_camera = None
        tasks = []
        try:
            model_paths = ensure_models(self._say)
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            running_video = vision.RunningMode.VIDEO
            hand = vision.HandLandmarker.create_from_options(
                vision.HandLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=str(model_paths["hand_landmarker.task"])),
                    running_mode=running_video,
                    num_hands=2,
                    min_hand_detection_confidence=0.45,
                    min_hand_presence_confidence=0.45,
                    min_tracking_confidence=0.45,
                )
            )
            segmenter = vision.ImageSegmenter.create_from_options(
                vision.ImageSegmenterOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=str(model_paths["selfie_segmenter.tflite"])),
                    running_mode=running_video,
                    output_category_mask=False,
                    output_confidence_masks=True,
                )
            )
            tasks = [hand, segmenter]

            # OpenCV's Linux V4L2 backend expects a numeric camera index. Passing
            # `/dev/videoN` as a string can fail with "backend ... can't be used
            # to capture by name" on some builds, even when the device exists.
            if self.device.startswith("/dev/video"):
                camera_index = int(Path(self.device).name.removeprefix("video"))
            else:
                camera_index = int(self.device)
            capture = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            capture.set(cv2.CAP_PROP_FPS, self.fps)
            if not capture.isOpened():
                raise RuntimeError(
                    f"Could not open camera {self.device}. Check camera permissions, close other apps, "
                    "or choose another camera in Settings."
                )

            if self.virtual_enabled:
                import pyvirtualcam

                arguments = dict(
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                    fmt=pyvirtualcam.PixelFormat.BGR,
                    backend="v4l2loopback",
                )
                if self.virtual_device:
                    arguments["device"] = self.virtual_device
                virtual_camera = pyvirtualcam.Camera(**arguments)
                self._say(f"Virtual camera ready: {virtual_camera.device}")

            self._say("Camera ready. Step out of view while the background is calibrated.")
            started_at = time.monotonic()
            phase = "calibrating"
            background_samples: list[np.ndarray] = []
            background = None
            current_mask = None
            pose_started = None
            effect_started = None
            reappearing = False
            last_inference = 0.0
            next_timestamp = 0
            status_reason = "waiting for camera"
            cv2.setNumThreads(2)

            while not self.stop_requested:
                while True:
                    try:
                        command = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    now = time.monotonic()
                    if command == "vanish" and phase == "ready":
                        phase, effect_started, pose_started = "vanishing", now, None
                        self.sound_requested.emit()
                    elif command == "reappear" and phase == "vanished":
                        phase, effect_started, reappearing = "reappearing", now, True
                    elif command == "toggle":
                        if phase == "ready":
                            phase, effect_started = "vanishing", now
                            self.sound_requested.emit()
                        elif phase == "vanished":
                            phase, effect_started, reappearing = "reappearing", now, True

                ok, frame = capture.read()
                if not ok or frame is None:
                    raise RuntimeError("The webcam stopped returning frames.")
                frame = cv2.flip(frame, 1)  # selfie mirror; landmarks use the same image.
                frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)
                now = time.monotonic()
                elapsed_ms = max(next_timestamp + 1, int((now - started_at) * 1000))
                next_timestamp = elapsed_ms
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                small_w = min(640, frame.shape[1])
                small_h = max(1, int(frame.shape[0] * small_w / frame.shape[1]))
                inference_rgb = cv2.resize(rgb, (small_w, small_h), interpolation=cv2.INTER_AREA)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=inference_rgb)

                hand_result = hand.detect_for_video(mp_image, elapsed_ms)
                hands = hand_result.hand_landmarks or []

                found_pose = False
                confidence = 0.0
                status_reason = "no hand detected"
                for hand_points in hands:
                    points = np.array([(p.x, p.y, p.z) for p in hand_points], dtype=np.float32)
                    found_pose, status_reason, confidence = is_v_sign(points)
                    if found_pose:
                        break
                if not hands:
                    status_reason = "no hand detected"

                # Run segmentation at camera rate for a stable silhouette.
                segment_result = segmenter.segment_for_video(mp_image, elapsed_ms)
                if segment_result.confidence_masks:
                    raw_mask = np.squeeze(segment_result.confidence_masks[0].numpy_view()).astype(np.float32)
                    current_mask = cv2.resize(raw_mask, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
                    current_mask = cv2.GaussianBlur(current_mask, (0, 0), 1.7)
                    current_mask = np.clip((current_mask - 0.10) / 0.70, 0, 1)

                if phase == "calibrating":
                    elapsed = now - started_at
                    if elapsed >= 1.6:
                        background_samples.append(frame.copy())
                    if elapsed >= CALIBRATION_SECONDS:
                        if not background_samples:
                            raise RuntimeError("No background frames captured. Restart calibration in a brighter room.")
                        background = np.median(np.stack(background_samples[-24:]), axis=0).astype(np.uint8)
                        phase = "ready"
                        self._say("Background ready. Return to frame and hold a V sign to vanish.")
                elif phase in ("ready", "vanished"):
                    if found_pose:
                        if pose_started is None:
                            pose_started = now
                        held = min(1.0, (now - pose_started) / GESTURE_HOLD_SECONDS)
                        if held >= 1.0:
                            if phase == "ready":
                                phase, effect_started, reappearing = "vanishing", now, False
                                self.sound_requested.emit()
                            else:
                                phase, effect_started, reappearing = "reappearing", now, True
                            pose_started = None
                    else:
                        pose_started = None
                        held = 0.0
                else:
                    held = 0.0

                output = background.copy() if phase == "vanished" and background is not None else frame.copy()
                progress = 0.0
                charging = 0.0
                if phase == "calibrating":
                    remaining = max(0.0, CALIBRATION_SECONDS - (now - started_at))
                    self.state_changed.emit(
                        f"Calibrating background — step out ({remaining:.0f}s)", status_reason, 0.0
                    )
                elif phase in ("ready", "vanishing", "reappearing") and background is not None:
                    if phase == "vanishing":
                        progress = min(1.0, (now - effect_started) / EFFECT_SECONDS)
                    elif phase == "reappearing":
                        progress = min(1.0, (now - effect_started) / EFFECT_SECONDS)
                    elif pose_started is not None:
                        charging = min(1.0, (now - pose_started) / GESTURE_HOLD_SECONDS)

                    if phase in ("vanishing", "reappearing"):
                        output = composite_teleport(frame, background, current_mask, progress,
                                                    phase == "reappearing")
                        if progress >= 1.0:
                            if phase == "vanishing":
                                phase = "vanished"
                                self._say("Vanished. Hold a V sign again to reappear, or press R.")
                            else:
                                phase = "ready"
                                self._say("Reappeared. Hold a V sign to teleport again.")
                    elif charging > 0 and current_mask is not None:
                        output = render_energy_lines(output, current_mask, charging * 0.65)
                    else:
                        output = frame
                    if phase == "vanished":
                        output = background.copy()
                    pose_progress = 0.0 if pose_started is None else min(1.0, (now - pose_started) / GESTURE_HOLD_SECONDS)
                    label = "Vanished — V sign to return" if phase == "vanished" else (
                        "Charging energy" if pose_progress > 0 else "Ready — hold up an index + middle finger V"
                    )
                    self.state_changed.emit(label, status_reason, pose_progress)

                if self.debug and int(now * 2) != int(last_inference * 2):
                    self._say(f"Gesture debug: {status_reason}; hand={bool(hands)}; score={confidence:.2f}")
                    last_inference = now

                if phase == "vanished" and background is not None:
                    output = background.copy()
                    self.state_changed.emit("Vanished — hold a V sign to return, or press R", status_reason, 0.0)

                if virtual_camera is not None:
                    virtual_camera.send(np.ascontiguousarray(output))
                    virtual_camera.sleep_until_next_frame()

                image_rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
                image_rgb = np.ascontiguousarray(image_rgb)
                qimage = QImage(image_rgb.data, image_rgb.shape[1], image_rgb.shape[0],
                                image_rgb.strides[0], QImage.Format.Format_RGB888).copy()
                self.frame_ready.emit(qimage)

        except Exception as error:
            self.failed.emit(str(error))
        finally:
            if virtual_camera is not None:
                try:
                    virtual_camera.close()
                except Exception:
                    pass
            if capture is not None:
                capture.release()
            for task in tasks:
                try:
                    task.close()
                except Exception:
                    pass


STYLE = """
QMainWindow, QWidget { background:#11131a; color:#f3f4f8; font-family:'Noto Sans',sans-serif; }
QFrame#panel { background:#191d27; border:1px solid #2c3342; border-radius:18px; }
QLabel#title { font-size:27px; font-weight:700; }
QLabel#subtitle { color:#aab3c2; font-size:13px; }
QLabel#status { color:#80e7f0; font-weight:600; }
QLabel#preview { background:#08090d; border:1px solid #30394a; border-radius:14px; color:#818a9c; }
QPushButton { background:#f1a94f; color:#17130d; font-weight:700; border:0; border-radius:10px; padding:11px 16px; }
QPushButton:hover { background:#ffc66d; }
QPushButton:disabled { background:#353b49; color:#8b94a4; }
QComboBox, QLineEdit, QSpinBox { background:#11151e; border:1px solid #394255; border-radius:8px; padding:8px; }
QCheckBox { spacing:8px; }
QLabel#hint { color:#aab3c2; font-size:12px; }
"""


def camera_choices() -> list[tuple[str, str]]:
    nodes = sorted(Path("/dev").glob("video[0-9]*"), key=lambda p: int(p.name.removeprefix("video")))
    choices = []
    for node in nodes:
        sys_node = Path("/sys/class/video4linux") / node.name
        device_path = sys_node / "device"
        try:
            resolved_device = str(device_path.resolve())
            device_name = (sys_node / "name").read_text().strip()
        except OSError:
            resolved_device, device_name = "", ""
        # Keep loopback outputs out of the capture-camera list: selecting one
        # as input commonly fails or creates a feedback loop.
        if "/devices/virtual/video4linux/" in resolved_device:
            continue
        label = f"{node.name} — {device_name}" if device_name else f"{node.name} ({node})"
        choices.append((label, str(node)))
    if choices:
        return choices
    return [(f"Camera {index} (/dev/video{index})", str(index)) for index in range(4)]


def virtual_camera_choices() -> list[tuple[str, str]]:
    """Find existing v4l2loopback nodes without opening them."""
    nodes = sorted(Path("/dev").glob("video[0-9]*"), key=lambda p: int(p.name.removeprefix("video")))
    choices = []
    for node in nodes:
        sys_node = Path("/sys/class/video4linux") / node.name
        try:
            resolved_device = str((sys_node / "device").resolve())
            device_name = (sys_node / "name").read_text().strip()
        except OSError:
            continue
        if "/devices/virtual/video4linux/" in resolved_device:
            label = f"{device_name} ({node})" if device_name else str(node)
            choices.append((label, str(node)))
    return choices


class MainWindow(QMainWindow):
    command_requested = Signal(str)

    def __init__(self, debug: bool = False):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLE)
        self.worker: CameraWorker | None = None
        self.debug = debug
        self.audio_router = AudioRouter()
        self.vanish_sounds = sound_files()

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("GOKU TELEPORT")
        title.setObjectName("title")
        subtitle = QLabel("A live anime-style instant transmission effect for Linux")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.status = QLabel("Camera off — preview starts only when you press Start")
        self.status.setObjectName("status")
        header.addWidget(self.status, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(18)
        self.preview = QLabel("Camera is off\n\nPress Start Preview when you are ready")
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(560, 390)
        self.preview.setSizePolicy(self.preview.sizePolicy().horizontalPolicy(), self.preview.sizePolicy().verticalPolicy())
        content.addWidget(self.preview, 1)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setMinimumWidth(285)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(12)
        panel_title = QLabel("CAMERA & OUTPUT")
        panel_title.setStyleSheet("font-size:12px; letter-spacing:1px; font-weight:700; color:#aab3c2")
        panel_layout.addWidget(panel_title)

        panel_layout.addWidget(QLabel("Webcam"))
        self.camera = QComboBox()
        for label, value in camera_choices():
            self.camera.addItem(label, value)
        panel_layout.addWidget(self.camera)

        self.refresh_button = QPushButton("Refresh camera list")
        self.refresh_button.clicked.connect(self.refresh_cameras)
        panel_layout.addWidget(self.refresh_button)

        size_row = QHBoxLayout()
        size_box = QVBoxLayout()
        size_box.addWidget(QLabel("Width"))
        self.width = QSpinBox()
        self.width.setRange(320, 1920)
        self.width.setSingleStep(160)
        self.width.setValue(1280)
        size_box.addWidget(self.width)
        size_row.addLayout(size_box)
        size_box = QVBoxLayout()
        size_box.addWidget(QLabel("Height"))
        self.height = QSpinBox()
        self.height.setRange(240, 1080)
        self.height.setSingleStep(90)
        self.height.setValue(720)
        size_box.addWidget(self.height)
        size_row.addLayout(size_box)
        panel_layout.addLayout(size_row)

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("FPS"))
        self.fps = QSpinBox()
        self.fps.setRange(15, 60)
        self.fps.setSingleStep(5)
        self.fps.setValue(30)
        fps_row.addWidget(self.fps)
        panel_layout.addLayout(fps_row)

        self.virtual_enabled = QCheckBox("Send to virtual webcam")
        panel_layout.addWidget(self.virtual_enabled)
        panel_layout.addWidget(QLabel("Optional V4L2 device"))
        self.virtual_device = QLineEdit()
        self.virtual_device.setPlaceholderText("Auto-detect (or /dev/videoN)")
        existing_virtual_cameras = virtual_camera_choices()
        if len(existing_virtual_cameras) == 1:
            self.virtual_device.setText(existing_virtual_cameras[0][1])
        panel_layout.addWidget(self.virtual_device)
        if existing_virtual_cameras:
            outputs = ", ".join(label for label, _ in existing_virtual_cameras)
            vcam_message = f"Detected virtual output: {outputs}"
        else:
            vcam_message = "Needs an existing v4l2loopback device; this option does not create one."
        vcam_hint = QLabel(vcam_message)
        vcam_hint.setObjectName("hint")
        panel_layout.addWidget(vcam_hint)

        self.sound_checkbox = QCheckBox("Play a random vanish sound")
        self.sound_checkbox.setChecked(True)
        panel_layout.addWidget(self.sound_checkbox)
        self.test_sound_button = QPushButton("Test sound")
        self.test_sound_button.clicked.connect(self.test_vanish_sound)
        panel_layout.addWidget(self.test_sound_button)
        self.mix_mic_checkbox = QCheckBox("Mix sound with microphone for Discord")
        panel_layout.addWidget(self.mix_mic_checkbox)
        mic_hint = QLabel("Select before Start Preview (locked while running). In Discord, choose ‘Goku Teleport Mic’ under Input Device; the mix includes your mic and vanish sound.")
        mic_hint.setObjectName("hint")
        mic_hint.setWordWrap(True)
        panel_layout.addWidget(mic_hint)

        self.debug_checkbox = QCheckBox("Show gesture diagnostics in terminal")
        self.debug_checkbox.setChecked(debug)
        panel_layout.addWidget(self.debug_checkbox)
        panel_layout.addStretch(1)

        self.start_button = QPushButton("Start Preview")
        self.start_button.clicked.connect(self.toggle_preview)
        panel_layout.addWidget(self.start_button)
        action_row = QHBoxLayout()
        self.vanish_button = QPushButton("Vanish  ·  V")
        self.return_button = QPushButton("Return  ·  R")
        self.vanish_button.clicked.connect(lambda: self.send_command("vanish"))
        self.return_button.clicked.connect(lambda: self.send_command("reappear"))
        self.vanish_button.setEnabled(False)
        self.return_button.setEnabled(False)
        action_row.addWidget(self.vanish_button)
        action_row.addWidget(self.return_button)
        panel_layout.addLayout(action_row)
        content.addWidget(panel)
        layout.addLayout(content, 1)

        footer = QLabel("Step out for background calibration · hold an index + middle finger V for one second · Q / Esc to quit")
        footer.setObjectName("hint")
        layout.addWidget(footer)
        self.setCentralWidget(root)

        file_menu = self.menuBar().addMenu("&App")
        exit_action = QAction("Quit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        self.add_shortcut("V", lambda: self.send_command("toggle"))
        self.add_shortcut("R", lambda: self.send_command("reappear"))
        self.add_shortcut("Q", self.close)
        self.add_shortcut("Escape", self.close)

    def add_shortcut(self, key: str, callback) -> None:
        shortcut = QShortcut(QKeySequence(key), self)
        shortcut.activated.connect(callback)

    def refresh_cameras(self) -> None:
        current = self.camera.currentData()
        self.camera.clear()
        for label, value in camera_choices():
            self.camera.addItem(label, value)
        index = self.camera.findData(current)
        if index >= 0:
            self.camera.setCurrentIndex(index)

    def toggle_preview(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.start_button.setEnabled(False)
            self.status.setText("Stopping camera…")
            return
        if self.mix_mic_checkbox.isChecked():
            try:
                mic_status = self.audio_router.start()
            except RuntimeError as error:
                self.audio_router.close()
                QMessageBox.warning(self, "Virtual microphone unavailable", str(error))
                return
        else:
            mic_status = ""
        device = str(self.camera.currentData())
        self.worker = CameraWorker(
            device=device,
            width=self.width.value(),
            height=self.height.value(),
            fps=self.fps.value(),
            virtual_enabled=self.virtual_enabled.isChecked(),
            virtual_device=self.virtual_device.text().strip(),
            debug=self.debug_checkbox.isChecked(),
        )
        self.worker.frame_ready.connect(self.show_frame)
        self.worker.state_changed.connect(self.show_state)
        self.worker.log_line.connect(self.status.setText)
        self.worker.failed.connect(self.show_error)
        self.worker.sound_requested.connect(self.play_vanish_sound)
        self.worker.finished.connect(self.worker_finished)
        self.command_requested.connect(self.worker.submit_command)
        self.start_button.setText("Stop Preview")
        self.start_button.setEnabled(True)
        self.vanish_button.setEnabled(True)
        self.return_button.setEnabled(True)
        self.status.setText("Starting…" + (f" · {mic_status}" if mic_status else ""))
        self.mix_mic_checkbox.setEnabled(False)
        self.worker.start()

    def send_command(self, command: str) -> None:
        if self.worker and self.worker.isRunning():
            self.command_requested.emit(command)

    def play_vanish_sound(self) -> None:
        if not self.sound_checkbox.isChecked() or not self.vanish_sounds:
            return
        if not self.audio_router.play(random.choice(self.vanish_sounds)):
            self.status.setText("No audio player found (install a desktop audio player to hear the cue)")

    def test_vanish_sound(self) -> None:
        if not self.vanish_sounds:
            QMessageBox.warning(self, "Sound unavailable", "The bundled vanish sound file could not be found.")
            return
        if not self.audio_router.play(random.choice(self.vanish_sounds)):
            QMessageBox.warning(self, "Sound unavailable", "No audio player was found. Install paplay, pw-play, or aplay.")

    def show_frame(self, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(pixmap)

    def show_state(self, phase: str, gesture: str, progress: float) -> None:
        if progress > 0:
            self.status.setText(f"{phase}  ·  {gesture}  ·  {progress * 100:.0f}%")
        else:
            self.status.setText(f"{phase}  ·  {gesture}")

    def show_error(self, message: str) -> None:
        self.status.setText("Camera stopped")
        QMessageBox.critical(self, "Goku Teleport", message)

    def worker_finished(self) -> None:
        self.audio_router.close()
        self.mix_mic_checkbox.setEnabled(True)
        self.start_button.setText("Start Preview")
        self.start_button.setEnabled(True)
        self.vanish_button.setEnabled(False)
        self.return_button.setEnabled(False)
        if self.status.text().startswith("Stopping"):
            self.status.setText("Camera off")
        self.preview.setPixmap(QPixmap())
        self.preview.setText("Camera is off\n\nPress Start Preview when you are ready")

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(4000)
        self.audio_router.close()
        event.accept()


def check_dependencies() -> int:
    print(f"{APP_NAME} {__import__('goku_teleport').__version__}")
    print(f"Python {sys.version.split()[0]}")
    print(f"OpenCV {cv2.__version__}")
    print(f"MediaPipe {mp.__version__}")
    print(f"NumPy {np.__version__}")
    try:
        import PySide6
        print(f"PySide6 {PySide6.__version__}")
    except Exception as error:
        print(f"PySide6 import failed: {error}")
        return 1
    try:
        import pyvirtualcam
        print(f"pyvirtualcam {pyvirtualcam.__version__}")
    except Exception as error:
        print(f"pyvirtualcam import failed: {error}")
        return 1
    print("Dependencies imported. The webcam was not opened.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Original anime-style Linux webcam teleport effect.")
    parser.add_argument("--check", action="store_true", help="check imports without opening the webcam")
    parser.add_argument("--smoke-test", action="store_true", help="open and close the app window without camera access")
    parser.add_argument("--debug-gesture", action="store_true", help="show detailed gesture diagnostics in the terminal")
    parser.add_argument("--list-cameras", action="store_true", help="list likely V4L2 paths without opening them")
    args = parser.parse_args(argv)
    if args.list_cameras:
        nodes = list(Path("/dev").glob("video[0-9]*"))
        if nodes:
            for node in nodes:
                print(node)
        else:
            print("No /dev/video nodes found. The camera is not probed or opened.")
        return 0
    if args.check:
        return check_dependencies()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setStyle("Fusion")
    window = MainWindow(debug=args.debug_gesture)
    local_icon = Path(__file__).resolve().parents[1] / "assets" / "icon.svg"
    packaged_icon = Path("/app/share/icons/hicolor/scalable/apps/org.codex.GokuTeleport.svg")
    icon_path = local_icon if local_icon.exists() else packaged_icon
    if icon_path.exists():
        from PySide6.QtGui import QIcon
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    if args.smoke_test:
        QTimer.singleShot(250, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
