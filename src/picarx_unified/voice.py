from __future__ import annotations

import base64
import json

from fastapi import WebSocket, WebSocketDisconnect

from .models import VoiceMode
from .runtime import RobotRuntime


class VoiceConnection:
    def __init__(self, runtime: RobotRuntime, websocket: WebSocket) -> None:
        self._runtime = runtime
        self._websocket = websocket
        self._pcm_buffer = bytearray()
        self._transcript = ""

    async def run(self) -> None:
        await self._websocket.accept()
        self._runtime.register_browser_client(self._websocket)
        await self._websocket.send_text(
            json.dumps({"type": "state", "state": self._runtime.current_session().model_dump(mode="json")})
        )
        try:
            while True:
                payload = json.loads(await self._websocket.receive_text())
                await self._handle_message(payload)
        except WebSocketDisconnect:
            pass
        finally:
            self._runtime.unregister_browser_client(self._websocket)

    async def _handle_message(self, payload: dict) -> None:
        event_type = payload.get("type")
        if event_type == "ping":
            await self._websocket.send_text(json.dumps({"type": "pong"}))
            return
        if event_type == "pcm_chunk":
            await self._handle_pcm_chunk(payload)
            return
        if event_type == "transcript":
            self._transcript = str(payload.get("text", "")).strip()
            return
        if event_type == "commit":
            await self._commit_turn()

    async def _handle_pcm_chunk(self, payload: dict) -> None:
        audio_b64 = payload.get("audio")
        if not audio_b64:
            return
        try:
            pcm_bytes = base64.b64decode(audio_b64)
        except Exception:
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
            self._pcm_buffer.extend(pcm_bytes)

    async def _commit_turn(self) -> None:
        session = self._runtime.current_session()
        if session.voice_mode != VoiceMode.AI_REPLY:
            self._pcm_buffer.clear()
            self._transcript = ""
            return
        transcript = self._transcript
        if not transcript:
            transcript = self._runtime.ai.transcribe_pcm(
                bytes(self._pcm_buffer),
                self._runtime.config.voice_sample_rate,
            ) or ""
        self._pcm_buffer.clear()
        self._transcript = ""
        if not transcript:
            await self._websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": (
                            "No transcript was available. Use a browser with Web Speech API support "
                            "or configure OPENAI_API_KEY for server-side transcription."
                        ),
                    }
                )
            )
            return
        self._runtime.handle_ai_turn(transcript)
