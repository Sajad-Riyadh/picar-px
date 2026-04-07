from __future__ import annotations

import base64
import shutil
import subprocess
import threading
from typing import Callable

from .models import AudioTarget


BrowserSender = Callable[[dict], None]


class LocalAudioPlayer:
    def __init__(self) -> None:
        self._aplay = shutil.which("aplay")
        self._lock = threading.Lock()
        self._raw_proc: subprocess.Popen[bytes] | None = None

    @property
    def available(self) -> bool:
        return self._aplay is not None

    def play_relay_chunk(self, pcm_bytes: bytes, sample_rate: int) -> bool:
        if not self.available or not pcm_bytes:
            return False
        with self._lock:
            self._ensure_raw_proc(sample_rate)
            if self._raw_proc is None or self._raw_proc.stdin is None:
                return False
            try:
                self._raw_proc.stdin.write(pcm_bytes)
                self._raw_proc.stdin.flush()
                return True
            except OSError:
                self._close_raw_proc()
                self._ensure_raw_proc(sample_rate)
                if self._raw_proc is None or self._raw_proc.stdin is None:
                    return False
                try:
                    self._raw_proc.stdin.write(pcm_bytes)
                    self._raw_proc.stdin.flush()
                    return True
                except OSError:
                    self._close_raw_proc()
                    return False

    def play_wav(self, wav_bytes: bytes) -> bool:
        if not self.available or not wav_bytes:
            return False
        try:
            subprocess.run(
                [self._aplay, "-q", "-"],
                input=wav_bytes,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return True
        except OSError:
            return False

    def close(self) -> None:
        with self._lock:
            self._close_raw_proc()

    def _ensure_raw_proc(self, sample_rate: int) -> None:
        if self._raw_proc is not None and self._raw_proc.poll() is None:
            return
        if not self._aplay:
            return
        self._raw_proc = subprocess.Popen(
            [
                self._aplay,
                "-q",
                "-f",
                "S16_LE",
                "-r",
                str(sample_rate),
                "-c",
                "1",
                "-t",
                "raw",
                "-",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _close_raw_proc(self) -> None:
        if self._raw_proc is None:
            return
        try:
            if self._raw_proc.stdin:
                self._raw_proc.stdin.close()
        except OSError:
            pass
        try:
            self._raw_proc.terminate()
        except OSError:
            pass
        self._raw_proc = None


class AudioRouter:
    def __init__(self, sample_rate: int) -> None:
        self._sample_rate = sample_rate
        self._player = LocalAudioPlayer()

    @property
    def local_backend(self) -> str:
        return "aplay" if self._player.available else "disabled"

    def close(self) -> None:
        self._player.close()

    def route_relay_chunk(self, pcm_bytes: bytes, target: AudioTarget, browser_send: BrowserSender) -> None:
        if target in {AudioTarget.CAR, AudioTarget.BOTH}:
            self._player.play_relay_chunk(pcm_bytes, self._sample_rate)
        if target in {AudioTarget.BROWSER, AudioTarget.BOTH}:
            browser_send(
                {
                    "type": "relay_chunk",
                    "audio": base64.b64encode(pcm_bytes).decode("ascii"),
                    "sample_rate": self._sample_rate,
                }
            )

    def route_assistant_audio(
        self,
        wav_bytes: bytes,
        target: AudioTarget,
        browser_send: BrowserSender,
        *,
        text: str | None = None,
    ) -> None:
        if target in {AudioTarget.CAR, AudioTarget.BOTH}:
            self._player.play_wav(wav_bytes)
        if target in {AudioTarget.BROWSER, AudioTarget.BOTH}:
            browser_send(
                {
                    "type": "assistant_audio",
                    "audio": base64.b64encode(wav_bytes).decode("ascii"),
                }
            )
        if text:
            browser_send({"type": "assistant_reply", "text": text})
