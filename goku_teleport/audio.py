"""Best-effort PulseAudio/PipeWire helpers for a per-user virtual microphone."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class AudioRouter:
    """Mix mic and effects, then publish the mix as a distinct input source."""

    def __init__(self) -> None:
        self.sink_name = "goku_teleport_mix"
        self.source_name = "goku_teleport_mic"
        self.module_ids: list[str] = []
        self.players: list[subprocess.Popen] = []
        self.active = False

    @staticmethod
    def _pactl(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["pactl", *args], capture_output=True, text=True, timeout=5, check=False
        )

    def start(self) -> str:
        if not shutil.which("pactl"):
            raise RuntimeError(
                "The virtual microphone needs pactl and a PipeWire-PulseAudio or PulseAudio session."
            )
        server = self._pactl("info")
        if server.returncode:
            raise RuntimeError("Could not connect to the desktop audio server; check PipeWire/PulseAudio.")

        source = self._pactl("get-default-source")
        source_name = source.stdout.strip() if not source.returncode else ""
        if not source_name or source_name.endswith(".monitor"):
            sources = self._pactl("list", "short", "sources")
            source_name = next(
                (row.split("\t")[1] for row in sources.stdout.splitlines()
                 if len(row.split("\t")) > 1 and not row.split("\t")[1].endswith(".monitor")),
                "",
            )
        if not source_name:
            raise RuntimeError("Could not find a physical microphone source in the audio server.")

        if not (shutil.which("paplay") or shutil.which("pw-play")):
            raise RuntimeError(
                "The virtual microphone needs paplay or pw-play to send the vanish sound into the mix."
            )

        sink = self._pactl(
            "load-module", "module-null-sink", f"sink_name={self.sink_name}",
            "rate=48000", "channels=2",
            'sink_properties=device.description="Goku Teleport Mix"',
        )
        if sink.returncode or not sink.stdout.strip():
            raise RuntimeError(f"Could not create the temporary audio mixer: {sink.stderr.strip()}")
        self.module_ids.append(sink.stdout.strip())

        loopback = self._pactl(
            "load-module", "module-loopback", f"source={source_name}",
            f"sink={self.sink_name}", "latency_msec=100",
        )
        if loopback.returncode or not loopback.stdout.strip():
            self.close()
            raise RuntimeError(f"Could not mix the regular microphone: {loopback.stderr.strip()}")
        self.module_ids.append(loopback.stdout.strip())

        mic_source = self._pactl(
            "load-module", "module-remap-source",
            f"master={self.sink_name}.monitor",
            f"source_name={self.source_name}",
            "rate=48000", "channels=2",
            'source_properties=device.description="Goku Teleport Mic"',
        )
        if mic_source.returncode or not mic_source.stdout.strip():
            self.close()
            raise RuntimeError(
                "Could not publish the mixed audio as a microphone input: "
                f"{mic_source.stderr.strip()}"
            )
        self.module_ids.append(mic_source.stdout.strip())
        self.active = True
        return "Goku Teleport Mic input ready (mic + vanish sound)"

    def play(self, audio_file: Path) -> bool:
        """Play locally and, when enabled, also route a copy into the virtual mic."""
        path = str(audio_file)
        commands: list[list[str]] = []
        paplay = shutil.which("paplay")
        pw_play = shutil.which("pw-play")

        if self.active:
            if paplay:
                commands.append([paplay, f"--device={self.sink_name}", path])
            elif pw_play:
                commands.append([pw_play, f"--target={self.sink_name}", path])

            # The virtual sink is intentionally silent; play a second copy to
            # the normal desktop output so the person using the app hears it.
            if paplay:
                commands.append([paplay, path])
            elif pw_play:
                commands.append([pw_play, path])
        elif pw_play:
            commands.append([pw_play, path])
        elif paplay:
            commands.append([paplay, path])
        elif shutil.which("aplay"):
            commands.append(["aplay", "-q", path])

        started = False
        for command in commands:
            try:
                process = subprocess.Popen(
                    command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self.players.append(process)
                started = True
            except OSError:
                continue
        return started

    def close(self) -> None:
        for player in self.players:
            if player.poll() is None:
                player.terminate()
        self.players.clear()
        if shutil.which("pactl"):
            for module_id in reversed(self.module_ids):
                try:
                    self._pactl("unload-module", module_id)
                except (OSError, subprocess.SubprocessError):
                    pass
        self.module_ids.clear()
        self.active = False
