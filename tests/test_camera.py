from __future__ import annotations

import queue
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from picarx_unified.config import AppConfig
from picarx_unified.hardware.camera import CameraService


def make_config(state_dir: Path) -> AppConfig:
    project_root = Path(__file__).resolve().parents[1]
    return AppConfig(
        host="127.0.0.1",
        port=8080,
        state_dir=state_dir,
        static_dir=project_root / "src" / "picarx_unified" / "static",
        camera_width=64,
        camera_height=48,
        camera_fps=5,
        camera_index=0,
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
        tracking_deadband_px=36,
        vision_loop_seconds=0.2,
        motion_object_min_area=1200,
        autonomous_max_speed=20,
        autonomous_manual_override_seconds=2.5,
        use_mock_hardware=True,
        force_mock_camera=True,
        api_token=None,
        gemini_api_key=None,
        gemini_live_model="gemini-3.1-flash-live-preview",
        gemini_native_audio_model="gemini-2.5-flash-native-audio-preview-12-2025",
    )


class CameraServiceTests(unittest.TestCase):
    def test_stream_generator_waits_for_new_frame_notifications(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            camera = CameraService(make_config(Path(tmp_dir)))
            camera._running = True
            frames: queue.Queue[bytes] = queue.Queue()
            generator = camera.stream_generator()

            def read_once() -> None:
                frames.put(next(generator))

            reader = threading.Thread(target=read_once, daemon=True)
            reader.start()

            time.sleep(0.1)
            self.assertTrue(frames.empty())

            with camera._frame_ready:
                camera._frame_jpeg = b"fresh-frame"
                camera._frame_sequence = 1
                camera._frame_ready.notify_all()

            frame = frames.get(timeout=1.0)
            self.assertIn(b"fresh-frame", frame)
            reader.join(timeout=1.0)


if __name__ == "__main__":
    unittest.main()
