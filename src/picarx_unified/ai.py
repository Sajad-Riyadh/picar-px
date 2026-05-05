from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass

from .config import AppConfig

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover - optional during local development
    genai = None
    types = None


@dataclass(slots=True)
class _LiveTurnResult:
    text: str | None = None
    input_transcription: str | None = None
    audio_wav: bytes | None = None


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
        if not config.gemini_api_key:
            logger.warning("GEMINI_API_KEY is not configured; AIService will use rule-based fallbacks.")
        elif genai is not None:
            try:
                self._client = genai.Client(api_key=config.gemini_api_key)
            except Exception:
                logger.exception("Failed to initialize Gemini client; falling back to local mode.")
                self._client = None
        else:
            logger.warning("google-genai is unavailable; AIService will use rule-based fallbacks.")

    @property
    def provider_name(self) -> str:
        return "gemini-live" if self._client is not None else "rule-based"

    @staticmethod
    def _clean_text(text: str | None) -> str | None:
        if not isinstance(text, str):
            return None
        stripped = text.strip()
        return stripped or None

    @staticmethod
    def _parse_pcm_sample_rate(mime_type: str | None, default: int = 24000) -> int:
        if not isinstance(mime_type, str):
            return default
        match = re.search(r"rate=(\d+)", mime_type)
        if match is None:
            return default
        try:
            return max(int(match.group(1)), 1)
        except ValueError:
            return default

    async def _live_text_turn(
        self,
        *,
        system_instruction: str,
        parts: list,
        max_output_tokens: int,
        model: str | None = None,
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
            model=model or self._config.gemini_live_model,
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

    async def _content_transcription_turn(self, pcm_bytes: bytes, sample_rate: int) -> str | None:
        assert self._client is not None
        assert types is not None
        wav_bytes = pcm16_to_wav(pcm_bytes, sample_rate)
        response = await self._client.aio.models.generate_content(
            model=self._config.gemini_transcription_model,
            contents=[
                "Generate a transcript of the speech. Return only the transcript text.",
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                system_instruction=(
                    "Transcribe the user's speech verbatim in plain text. "
                    "Return only the transcript and do not answer the user."
                ),
            ),
        )
        return self._clean_text(getattr(response, "text", None))

    async def _live_audio_turn(
        self,
        *,
        system_instruction: str,
        parts: list,
        max_output_tokens: int,
        model: str | None = None,
    ) -> _LiveTurnResult:
        assert self._client is not None
        assert types is not None
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction,
            output_audio_transcription=types.AudioTranscriptionConfig(),
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        )
        async with self._client.aio.live.connect(
            model=model or self._config.gemini_native_audio_model,
            config=config,
        ) as session:
            await session.send_client_content(
                turns=types.Content(role="user", parts=parts),
                turn_complete=True,
            )
            audio_chunks: list[bytes] = []
            transcript_chunks: list[str] = []
            audio_mime_type: str | None = None
            async for message in session.receive():
                server_content = getattr(message, "server_content", None)
                model_turn = getattr(server_content, "model_turn", None)
                for part in getattr(model_turn, "parts", []) or []:
                    inline_data = getattr(part, "inline_data", None)
                    inline_bytes = getattr(inline_data, "data", None)
                    if isinstance(inline_bytes, bytes) and inline_bytes:
                        audio_chunks.append(inline_bytes)
                        audio_mime_type = getattr(inline_data, "mime_type", None) or audio_mime_type
                output_transcription = getattr(server_content, "output_transcription", None)
                chunk = self._clean_text(getattr(output_transcription, "text", None))
                if chunk:
                    transcript_chunks.append(chunk)

        audio_wav: bytes | None = None
        if audio_chunks:
            audio_bytes = b"".join(audio_chunks)
            if isinstance(audio_mime_type, str) and audio_mime_type.lower().startswith("audio/wav"):
                audio_wav = audio_bytes
            else:
                audio_wav = pcm16_to_wav(
                    audio_bytes,
                    self._parse_pcm_sample_rate(audio_mime_type),
                )

        return _LiveTurnResult(
            text=self._clean_text(" ".join(transcript_chunks)),
            audio_wav=audio_wav,
        )

    async def _generate_reply_via_text(
        self,
        transcript: str,
        vision_summary: str,
    ) -> str | None:
        assert types is not None
        response = await self._live_text_turn(
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
                        "Reply naturally and completely. Be concise but never cut off mid-thought."
                    )
                )
            ],
            max_output_tokens=self._config.ai_reply_max_tokens,
            model=self._config.gemini_live_model,
        )
        return response.text

    async def _generate_detection_greeting_via_text(
        self,
        greeting_text: str,
        vision_summary: str,
    ) -> str | None:
        assert types is not None
        response = await self._live_text_turn(
            system_instruction=(
                "You are the voice of a PiCar-X robot greeting a person who just appeared "
                "in front of the camera. Keep the reply warm and safe. "
                "Do not mention driving or claim motor control."
            ),
            parts=[
                types.Part(
                    text=(
                        f"Preferred greeting phrase: {greeting_text}\n"
                        f"Current camera summary: {vision_summary}\n"
                        "Greet the person warmly and invite them to talk. Finish your sentence completely."
                    )
                )
            ],
            max_output_tokens=self._config.ai_greeting_max_tokens,
            model=self._config.gemini_live_model,
        )
        return response.text

    async def generate_reply(self, transcript: str, vision_summary: str) -> tuple[str, bytes | None]:
        transcript = transcript.strip()
        if not transcript:
            return "I did not catch that.", None
        if self._client is None:
            return self._fallback_reply(transcript, vision_summary), None
        assert types is not None
        try:
            response = await self._live_audio_turn(
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
                            "Reply naturally and completely. Be concise but never cut off mid-thought."
                        )
                    )
                ],
                max_output_tokens=self._config.ai_reply_max_tokens,
                model=self._config.gemini_native_audio_model,
            )
            if response.audio_wav or response.text:
                reply_text = response.text or self._fallback_reply(transcript, vision_summary)
                return reply_text, response.audio_wav
            logger.warning(
                "Gemini audio turn returned no text or audio; retrying with text model %s.",
                self._config.gemini_live_model,
            )
        except Exception:
            logger.exception(
                "Gemini native audio reply failed on model %s; retrying with text model.",
                self._config.gemini_native_audio_model,
            )
        try:
            text_reply = await self._generate_reply_via_text(transcript, vision_summary)
            if text_reply:
                return text_reply, None
        except Exception:
            logger.exception("Gemini text reply fallback failed; using local fallback reply.")
        return self._fallback_reply(transcript, vision_summary), None

    async def generate_detection_greeting(
        self,
        greeting_text: str,
        vision_summary: str,
    ) -> tuple[str, bytes | None]:
        greeting_text = greeting_text.strip()
        if not greeting_text:
            greeting_text = "Hello there. Welcome."
        if self._client is None:
            return greeting_text, None
        assert types is not None
        try:
            response = await self._live_audio_turn(
                system_instruction=(
                    "You are the voice of a PiCar-X robot greeting a person who just appeared "
                    "in front of the camera. Keep the reply warm and safe. "
                    "Do not mention driving or claim motor control."
                ),
                parts=[
                    types.Part(
                        text=(
                            f"Preferred greeting phrase: {greeting_text}\n"
                            f"Current camera summary: {vision_summary}\n"
                            "Greet the person warmly and invite them to talk. Finish your sentence completely."
                        )
                    )
                ],
                max_output_tokens=self._config.ai_greeting_max_tokens,
                model=self._config.gemini_native_audio_model,
            )
            if response.audio_wav or response.text:
                return response.text or greeting_text, response.audio_wav
            logger.warning(
                "Gemini audio greeting returned no text or audio; retrying with text model %s.",
                self._config.gemini_live_model,
            )
        except Exception:
            logger.exception(
                "Gemini native audio greeting failed on model %s; retrying with text model.",
                self._config.gemini_native_audio_model,
            )
        try:
            text_greeting = await self._generate_detection_greeting_via_text(
                greeting_text,
                vision_summary,
            )
            if text_greeting:
                return text_greeting, None
        except Exception:
            logger.exception("Gemini text greeting fallback failed; using configured greeting text.")
        return greeting_text, None

    async def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int) -> str | None:
        if self._client is None or not pcm_bytes:
            return None
        try:
            response = await self._live_transcription_turn(pcm_bytes, sample_rate)
            transcript = response.input_transcription or response.text
            if transcript:
                return transcript
            logger.warning(
                "Gemini live transcription returned no transcript; retrying with model %s.",
                self._config.gemini_transcription_model,
            )
        except Exception:
            logger.warning(
                "Gemini live transcription failed on model %s; retrying with model %s.",
                self._config.gemini_live_model,
                self._config.gemini_transcription_model,
                exc_info=True,
            )
        try:
            transcript = await self._content_transcription_turn(pcm_bytes, sample_rate)
            if transcript:
                return transcript
        except Exception:
            logger.exception(
                "Gemini fallback transcription failed on model %s.",
                self._config.gemini_transcription_model,
            )
        logger.warning("Gemini transcription failed; server-side STT unavailable.")
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
            logger.exception("Speech synthesis failed; returning silence.")
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


