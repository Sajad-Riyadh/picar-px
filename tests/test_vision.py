from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from picarx_unified.config import AppConfig
from picarx_unified.hardware.camera import CameraService
from picarx_unified.vision import VisionService


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


class VisionServiceTests(unittest.TestCase):
    def test_diagnostics_reports_settings_and_detector_status(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            camera = CameraService(make_config(Path(tmp_dir)))
            vision = VisionService(make_config(Path(tmp_dir)), camera)

            diagnostics = vision.diagnostics()

            self.assertFalse(diagnostics["running"])
            self.assertTrue(diagnostics["settings"]["detection_enabled"])
            self.assertGreaterEqual(len(diagnostics["detectors"]), 1)
            self.assertIn("available", diagnostics["detectors"][0])
            self.assertIn("enabled", diagnostics["detectors"][0])


if __name__ == "__main__":
    unittest.main()
