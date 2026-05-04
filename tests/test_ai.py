from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

from picarx_unified.ai import AIService
from picarx_unified.config import AppConfig


def make_config(state_dir: Path) -> AppConfig:
    project_root = Path(__file__).resolve().parents[1]
    return AppConfig(
        host="127.0.0.1",
        port=8080,
        https_enable=False,
        ssl_certfile=None,
        ssl_keyfile=None,
        state_dir=state_dir,
        static_dir=project_root / "src" / "picarx_unified" / "static",
        camera_width=64,
        camera_height=48,
        camera_fps=5,
        camera_index=0,
        camera_force_backend="auto",
        camera_format="RGB888",
        camera_color_fix="auto",
        camera_jpeg_encoder="auto",
        camera_full_fov=True,
        camera_disable_scaler_crop=True,
        camera_awb_enable=True,
        camera_awb_mode="auto",
        jpeg_quality=80,
        voice_sample_rate=16000,
        voice_chunk_samples=2048,
        voice_capture_max_seconds=20.0,
        drive_max_speed=50,
        steering_limit=30,
        camera_pan_limit=70,
        camera_tilt_up_limit=35,
        camera_tilt_down_limit=-35,
        obstacle_stop_cm=18.0,
        drive_watchdog_seconds=0.9,
        greet_cooldown_seconds=20.0,
        tracking_step_degrees=5,
        tracking_deadband_px=30,
        tracking_smoothing=0.35,
        tracking_lost_target_timeout=2.0,
        tracking_update_interval_ms=120,
        face_min_size=40,
        face_scale_factor=1.08,
        face_min_neighbors=4,
        vision_loop_seconds=0.2,
        motion_object_min_area=1200,
        autonomous_max_speed=20,
        autonomous_manual_override_seconds=2.5,
        use_mock_hardware=True,
        hardware_init_mode="mock",
        force_mock_camera=True,
        hog_enabled=False,
        api_token=None,
        gemini_api_key=None,
        gemini_live_model="gemini-3.1-flash-live-preview",
        gemini_native_audio_model="gemini-2.5-flash-native-audio-preview-12-2025",
        gemini_transcription_model="gemini-2.5-flash",
    )


class AIServiceTests(unittest.TestCase):
    def test_async_public_methods_fall_back_without_gemini(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            ai = AIService(make_config(Path(tmp_dir)))

            reply, reply_audio = asyncio.run(
                ai.generate_reply("what can you see", "1 person in frame")
            )
            answer = asyncio.run(ai.answer_vision("What is visible?", "1 cat in frame"))
            greeting, greeting_audio = asyncio.run(
                ai.generate_detection_greeting("Welcome aboard.", "1 face in frame")
            )
            transcript = asyncio.run(ai.transcribe_pcm(b"\x00\x00" * 64, 16000))

            self.assertIn("I can currently report", reply)
            self.assertIsNone(reply_audio)
            self.assertIn("Current summary", answer)
            self.assertEqual(greeting, "Welcome aboard.")
            self.assertIsNone(greeting_audio)
            self.assertIsNone(transcript)

    def test_transcribe_pcm_falls_back_to_generate_content_when_live_fails(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            ai = AIService(make_config(Path(tmp_dir)))
            ai._client = object()
            ai._live_transcription_turn = AsyncMock(side_effect=RuntimeError("live failed"))
            ai._content_transcription_turn = AsyncMock(return_value="hello from fallback")

            transcript = asyncio.run(ai.transcribe_pcm(b"\x01\x02" * 64, 16000))

            self.assertEqual(transcript, "hello from fallback")
            ai._live_transcription_turn.assert_awaited_once()
            ai._content_transcription_turn.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
