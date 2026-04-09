from __future__ import annotations

import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from picarx_unified.app import create_app
from picarx_unified.runtime import RobotRuntime


def _voice_env(state_dir: str) -> dict[str, str]:
    return {
        "PICARX_STATE_DIR": state_dir,
        "PICARX_USE_MOCK": "1",
        "PICARX_FORCE_MOCK_CAMERA": "1",
        "PICARX_VOICE_CAPTURE_MAX_SECONDS": "0.5",
    }


def _drain_initial_state_messages(websocket) -> None:
    for _ in range(2):
        payload = websocket.receive_json()
        if payload.get("type") != "state":
            raise AssertionError(f"Expected initial state payload, received {payload!r}")


class VoiceSocketTests(unittest.TestCase):
    def test_invalid_json_returns_error_and_socket_stays_open(self) -> None:
        with TemporaryDirectory() as tmp_dir, patch.dict(os.environ, _voice_env(tmp_dir), clear=False):
            with TestClient(create_app()) as client:
                with client.websocket_connect("/ws/voice") as websocket:
                    _drain_initial_state_messages(websocket)
                    websocket.send_text("{")
                    error_payload = websocket.receive_json()
                    self.assertEqual(error_payload["type"], "error")
                    self.assertIn("invalid JSON", error_payload["message"])

                    websocket.send_json({"type": "ping"})
                    pong_payload = websocket.receive_json()
                    self.assertEqual(pong_payload["type"], "pong")

    def test_commit_turn_invokes_runtime_handler_in_ai_reply_mode(self) -> None:
        with TemporaryDirectory() as tmp_dir, patch.dict(os.environ, _voice_env(tmp_dir), clear=False):
            with patch.object(RobotRuntime, "handle_ai_turn", autospec=True, return_value="ok") as handle_ai_turn:
                with TestClient(create_app()) as client:
                    response = client.post("/api/voice/mode", json={"mode": "ai_reply"})
                    self.assertEqual(response.status_code, 200)

                    with client.websocket_connect("/ws/voice") as websocket:
                        _drain_initial_state_messages(websocket)
                        websocket.send_json({"type": "transcript", "text": "hello robot"})
                        websocket.send_json({"type": "commit"})
                        websocket.send_json({"type": "ping"})
                        pong_payload = websocket.receive_json()
                        self.assertEqual(pong_payload["type"], "pong")

                self.assertEqual(handle_ai_turn.call_count, 1)
                self.assertEqual(handle_ai_turn.call_args.args[1], "hello robot")


if __name__ == "__main__":
    unittest.main()
