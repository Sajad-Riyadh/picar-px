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
        camera_force_backend="auto",
        camera_format="RGB888",
        camera_color_fix="auto",
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
        gemini_transcription_model="gemini-2.5-flash",
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

    def test_select_sensor_mode_prefers_full_fov_mode_at_requested_fps(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            camera = CameraService(make_config(Path(tmp_dir)))
            camera._config.camera_width = 1296
            camera._config.camera_height = 972
            camera._config.camera_fps = 20
            sensor_modes = [
                {"size": (640, 480), "bit_depth": 10, "fps": 58.92},
                {"size": (1296, 972), "bit_depth": 10, "fps": 43.25},
                {"size": (1920, 1080), "bit_depth": 10, "fps": 30.62},
                {"size": (2592, 1944), "bit_depth": 10, "fps": 15.63},
            ]

            selected = camera._select_sensor_mode(sensor_modes)

            self.assertIsNotNone(selected)
            self.assertEqual(selected["size"], (1296, 972))

    def test_build_picamera_sensor_config_uses_selected_mode(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            camera = CameraService(make_config(Path(tmp_dir)))
            camera._config.camera_width = 1296
            camera._config.camera_height = 972

            class FakePicamera:
                sensor_modes = [
                    {"size": (640, 480), "bit_depth": 10, "fps": 58.92},
                    {"size": (1296, 972), "bit_depth": 10, "fps": 43.25},
                ]

            camera._picamera = FakePicamera()

            sensor_config = camera._build_picamera_sensor_config()

            self.assertEqual(sensor_config, {"output_size": (1296, 972), "bit_depth": 10})


if __name__ == "__main__":
    unittest.main()
