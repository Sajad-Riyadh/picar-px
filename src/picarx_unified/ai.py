from __future__ import annotations

import asyncio
import io
import shutil
import subprocess
import threading
import wave
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

from .config import AppConfig

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover - optional during local development
    genai = None
    types = None


_T = TypeVar("_T")


@dataclass(slots=True)
class _LiveTurnResult:
    text: str | None = None
    input_transcription: str | None = None


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
        if genai is not None and config.gemini_api_key:
            try:
                self._client = genai.Client(api_key=config.gemini_api_key)
            except Exception:
                self._client = None

    @property
    def provider_name(self) -> str:
        return "gemini-live" if self._client is not None else "rule-based"

    @staticmethod
    def _clean_text(text: str | None) -> str | None:
        if not isinstance(text, str):
            return None
        stripped = text.strip()
        return stripped or None

    def _run_async(self, factory: Callable[[], Awaitable[_T]]) -> _T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(factory())

        result: dict[str, _T] = {}
        error: dict[str, BaseException] = {}

        def runner() -> None:
            try:
                result["value"] = asyncio.run(factory())
            except BaseException as exc:
                error["value"] = exc

        thread = threading.Thread(target=runner, name="gemini-live-call", daemon=True)
        thread.start()
        thread.join()
        if "value" in error:
            raise error["value"]
        return result["value"]

    async def _live_text_turn(
        self,
        *,
        system_instruction: str,
        parts: list,
        max_output_tokens: int,
    ) -> _LiveTurnResult:
        assert self._client is not None
        assert types is not None
        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction,
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        )
        async with self._client.aio.live.connect(
            model=self._config.gemini_live_model,
            config=config,
        ) as session:
            await session.send_client_content(
                turns=types.Content(role="user", parts=parts),
                turn_complete=True,
            )
            chunks: list[str] = []
            async for message in session.receive():
                chunk = self._clean_text(message.text)
                if chunk:
                    chunks.append(chunk)
        return _LiveTurnResult(text=self._clean_text("".join(chunks)))

    async def _live_transcription_turn(self, pcm_bytes: bytes, sample_rate: int) -> _LiveTurnResult:
        assert self._client is not None
        assert types is not None
        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            max_output_tokens=120,
            system_instruction=(
                "Transcribe the user's speech verbatim in plain text. "
                "Return only the transcript and do not answer the user."
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        )
        audio = types.Blob(
            data=pcm_bytes,
            mime_type=f"audio/pcm;rate={sample_rate}",
        )
        async with self._client.aio.live.connect(
            model=self._config.gemini_live_model,
            config=config,
        ) as session:
            await session.send_realtime_input(audio=audio)
            await session.send_realtime_input(audio_stream_end=True)
            chunks: list[str] = []
            transcript: str | None = None
            async for message in session.receive():
                chunk = self._clean_text(message.text)
                if chunk:
                    chunks.append(chunk)
                server_content = getattr(message, "server_content", None)
                input_transcription = getattr(server_content, "input_transcription", None)
                transcription_text = self._clean_text(getattr(input_transcription, "text", None))
                if transcription_text:
                    transcript = transcription_text
        return _LiveTurnResult(
            text=self._clean_text("".join(chunks)),
            input_transcription=transcript,
        )

    def generate_reply(self, transcript: str, vision_summary: str) -> str:
        transcript = transcript.strip()
        if not transcript:
            return "I did not catch that."
        if self._client is None:
            return self._fallback_reply(transcript, vision_summary)
        try:
            response = self._run_async(
                lambda: self._live_text_turn(
                    system_instruction=(
                        "You are a PiCar-X robot running on a Raspberry Pi 5. "
                        "You may answer questions, describe the camera scene, and greet people, "
                        "but you must never claim to directly control the motors."
                    ),
                    parts=[
                        types.Part(
                            text=(
                                f"Camera summary: {vision_summary}\n"
                                f"User transcript: {transcript}\n"
                                "Reply in 1-3 short sentences."
                            )
                        )
                    ],
                    max_output_tokens=180,
                )
            )
            return response.text or self._fallback_reply(transcript, vision_summary)
        except Exception:
            return self._fallback_reply(transcript, vision_summary)

    def answer_vision(self, question: str, vision_summary: str, frame_jpeg: bytes | None = None) -> str:
        if self._client is None or not frame_jpeg:
            return self._fallback_vision_answer(question, vision_summary)
        try:
            response = self._run_async(
                lambda: self._live_text_turn(
                    system_instruction=(
                        "Answer questions about the robot camera view. "
                        "Do not invent motor actions or unseen objects."
                    ),
                    parts=[
                        types.Part(
                            text=(
                                f"Current local detection summary: {vision_summary}\n"
                                f"Question: {question}"
                            )
                        ),
                        types.Part(
                            inline_data=types.Blob(
                                data=frame_jpeg,
                                mime_type="image/jpeg",
                            )
                        ),
                    ],
                    max_output_tokens=220,
                )
            )
            return response.text or self._fallback_vision_answer(question, vision_summary)
        except Exception:
            return self._fallback_vision_answer(question, vision_summary)

    def generate_detection_greeting(self, greeting_text: str, vision_summary: str) -> str:
        greeting_text = greeting_text.strip()
        if not greeting_text:
            greeting_text = "Hello there. Welcome."
        if self._client is None:
            return greeting_text
        try:
            response = self._run_async(
                lambda: self._live_text_turn(
                    system_instruction=(
                        "You are the voice of a PiCar-X robot greeting a person who just appeared "
                        "in front of the camera. Keep the reply warm, short, and safe. "
                        "Do not mention driving or claim motor control."
                    ),
                    parts=[
                        types.Part(
                            text=(
                                f"Preferred greeting phrase: {greeting_text}\n"
                                f"Current camera summary: {vision_summary}\n"
                                "Speak in 1-2 short sentences and invite the person to talk."
                            )
                        )
                    ],
                    max_output_tokens=120,
                )
            )
            return response.text or greeting_text
        except Exception:
            return greeting_text

    def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int) -> str | None:
        if self._client is None or not pcm_bytes:
            return None
        try:
            response = self._run_async(
                lambda: self._live_transcription_turn(pcm_bytes, sample_rate)
            )
            return response.input_transcription or response.text
        except Exception:
            return None

    def synthesize(self, text: str) -> bytes:
        text = text.strip()
        if not text:
            return silent_wav()
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
