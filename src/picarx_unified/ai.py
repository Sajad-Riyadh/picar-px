from __future__ import annotations

import base64
import io
import shutil
import subprocess
import tempfile
import wave

from .config import AppConfig

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional during local development
    OpenAI = None


def pcm16_to_wav(pcm_bytes: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_bytes)
    return buffer.getvalue()


def silent_wav(duration_seconds: float = 0.2, sample_rate: int = 16000) -> bytes:
    frame_count = int(duration_seconds * sample_rate)
    return pcm16_to_wav(b"\x00\x00" * frame_count, sample_rate)


class AIService:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._client = None
        if OpenAI is not None and config.openai_api_key:
            try:
                self._client = OpenAI(api_key=config.openai_api_key)
            except Exception:
                self._client = None

    @property
    def provider_name(self) -> str:
        return "openai" if self._client is not None else "rule-based"

    def generate_reply(self, transcript: str, vision_summary: str) -> str:
        transcript = transcript.strip()
        if not transcript:
            return "I did not catch that."
        if self._client is None:
            return self._fallback_reply(transcript, vision_summary)
        try:
            response = self._client.responses.create(
                model=self._config.openai_text_model,
                input=[
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "You are a PiCar-X robot running on a Raspberry Pi 5. "
                                    "You may answer questions, describe the camera scene, and greet people, "
                                    "but you must never claim to directly control the motors."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"Camera summary: {vision_summary}\n"
                                    f"User transcript: {transcript}\n"
                                    "Reply in 1-3 short sentences."
                                ),
                            }
                        ],
                    },
                ],
                max_output_tokens=180,
            )
            text = getattr(response, "output_text", None)
            return text.strip() if text else self._fallback_reply(transcript, vision_summary)
        except Exception:
            return self._fallback_reply(transcript, vision_summary)

    def answer_vision(self, question: str, vision_summary: str, frame_jpeg: bytes | None = None) -> str:
        if self._client is None or not frame_jpeg:
            return self._fallback_vision_answer(question, vision_summary)
        try:
            image_b64 = base64.b64encode(frame_jpeg).decode("ascii")
            response = self._client.responses.create(
                model=self._config.openai_vision_model,
                input=[
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Answer questions about the robot camera view. "
                                    "Do not invent motor actions or unseen objects."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"Current local detection summary: {vision_summary}\n"
                                    f"Question: {question}"
                                ),
                            },
                            {
                                "type": "input_image",
                                "image_url": f"data:image/jpeg;base64,{image_b64}",
                            },
                        ],
                    },
                ],
                max_output_tokens=220,
            )
            text = getattr(response, "output_text", None)
            return text.strip() if text else self._fallback_vision_answer(question, vision_summary)
        except Exception:
            return self._fallback_vision_answer(question, vision_summary)

    def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int) -> str | None:
        if self._client is None or not pcm_bytes:
            return None
        wav_bytes = pcm16_to_wav(pcm_bytes, sample_rate)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                handle.write(wav_bytes)
                temp_path = handle.name
            with open(temp_path, "rb") as audio_file:
                transcript = self._client.audio.transcriptions.create(
                    model=self._config.openai_stt_model,
                    file=audio_file,
                )
            text = getattr(transcript, "text", None)
            return text.strip() if text else None
        except Exception:
            return None
        finally:
            if temp_path:
                try:
                    import os

                    os.unlink(temp_path)
                except OSError:
                    pass

    def synthesize(self, text: str) -> bytes:
        command = shutil.which("espeak-ng") or shutil.which("espeak")
        if command is None:
            return silent_wav()
        try:
            result = subprocess.run(
                [command, "--stdout", text],
                capture_output=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except OSError:
            pass
        return silent_wav()

    def _fallback_reply(self, transcript: str, vision_summary: str) -> str:
        lower = transcript.lower()
        if any(word in lower for word in {"see", "camera", "look"}):
            return f"I can currently report: {vision_summary}"
        if "status" in lower:
            return (
                "Drive, camera, vision, and browser control are online. "
                "Cloud AI is not configured, so I am using local fallback replies."
            )
        if any(word in lower for word in {"hello", "hi", "hey"}):
            return "Hello. PiCar-X is online and ready."
        return (
            "I heard you, but full cloud AI is not configured yet. "
            f"My current local scene summary is: {vision_summary}"
        )

    def _fallback_vision_answer(self, question: str, vision_summary: str) -> str:
        _ = question
        return (
            "This first-version local vision answer is based on onboard detections only. "
            f"Current summary: {vision_summary}"
        )
