from __future__ import annotations

import asyncio
import base64
import binascii
import json

from fastapi import WebSocket, WebSocketDisconnect

from .models import VoiceMode
from .runtime import RobotRuntime


MAX_TRANSCRIPT_CHARS = 4000


class VoiceConnection:
    def __init__(self, runtime: RobotRuntime, websocket: WebSocket) -> None:
        self._runtime = runtime
        self._websocket = websocket
        self._pcm_buffer = bytearray()
        self._transcript = ""
        self._max_pcm_bytes = max(
            1,
            int(
                runtime.config.voice_sample_rate
                * 2
                * max(runtime.config.voice_capture_max_seconds, 0.25)
            ),
        )

    async def run(self) -> None:
        await self._websocket.accept()
        self._runtime.register_browser_client(self._websocket)
        await self._send_state()
        try:
            while True:
                raw_message = await self._websocket.receive_text()
                try:
                    payload = json.loads(raw_message)
                except json.JSONDecodeError:
                    await self._send_error("Voice socket received invalid JSON.")
                    continue
                if not isinstance(payload, dict):
                    await self._send_error("Voice socket messages must be JSON objects.")
                    continue
                await self._handle_message(payload)
        except WebSocketDisconnect:
            pass
        finally:
            self._pcm_buffer.clear()
            self._transcript = ""
            self._runtime.unregister_browser_client(self._websocket)

    async def _send_json(self, payload: dict) -> None:
        await self._websocket.send_text(json.dumps(payload))

    async def _send_state(self) -> None:
        await self._send_json(
            {"type": "state", "state": self._runtime.current_session().model_dump(mode="json")}
        )

    async def _send_error(self, message: str) -> None:
        await self._send_json({"type": "error", "message": message})

    async def _handle_message(self, payload: dict) -> None:
        event_type = str(payload.get("type", "")).strip()
        if event_type == "ping":
            await self._send_json({"type": "pong"})
            return
        if event_type == "pcm_chunk":
            await self._handle_pcm_chunk(payload)
            return
        if event_type == "transcript":
            self._transcript = str(payload.get("text", "")).strip()[:MAX_TRANSCRIPT_CHARS]
            return
        if event_type == "commit":
            await self._commit_turn()
            return
        await self._send_error(
            f"Unsupported voice message type: {event_type or 'missing type'}."
        )

    async def _handle_pcm_chunk(self, payload: dict) -> None:
        audio_b64 = payload.get("audio")
        if not isinstance(audio_b64, str) or not audio_b64:
            await self._send_error("PCM chunk is missing audio data.")
            return
        try:
            pcm_bytes = base64.b64decode(audio_b64, validate=True)
        except (binascii.Error, ValueError):
            await self._send_error("PCM chunk was not valid base64 audio.")
            return
        session = self._runtime.current_session()
        if session.voice_mode == VoiceMode.RELAY:
            self._runtime.audio.route_relay_chunk(
                pcm_bytes,
                session.audio_target,
                self._runtime.publish_browser_event,
            )
            return
        if session.voice_mode == VoiceMode.AI_REPLY:
            if len(self._pcm_buffer) + len(pcm_bytes) > self._max_pcm_bytes:
                self._pcm_buffer.clear()
                self._transcript = ""
                await self._send_error(
                    "Voice capture exceeded the configured limit. "
                    "Commit sooner or shorten the utterance."
                )
                return
            self._pcm_buffer.extend(pcm_bytes)

    async def _commit_turn(self) -> None:
        session = self._runtime.current_session()
        if session.voice_mode != VoiceMode.AI_REPLY:
            self._pcm_buffer.clear()
            self._transcript = ""
            return
        transcript = self._transcript.strip()[:MAX_TRANSCRIPT_CHARS]
        pcm_bytes = bytes(self._pcm_buffer)
        self._pcm_buffer.clear()
        self._transcript = ""
        if not transcript:
            transcript = await asyncio.to_thread(
                self._runtime.ai.transcribe_pcm,
                pcm_bytes,
                self._runtime.config.voice_sample_rate,
            ) or ""
        transcript = transcript.strip()[:MAX_TRANSCRIPT_CHARS]
        if not transcript:
            await self._send_error(
                "No transcript was available. Use a browser with Web Speech API support "
                "or configure OPENAI_API_KEY for server-side transcription."
            )
            return
        try:
            await asyncio.to_thread(self._runtime.handle_ai_turn, transcript)
        except Exception:
            await self._send_error("Assistant processing failed for the current turn.")
