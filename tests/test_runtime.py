from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from picarx_unified.config import AppConfig
from picarx_unified.runtime import RobotRuntime
from picarx_unified.state import StateStore
from picarx_unified.models import CameraState, DriveState, RobotSession


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
        use_mock_hardware=True,
        force_mock_camera=True,
        api_token=None,
        openai_api_key=None,
        openai_text_model="gpt-4.1-mini",
        openai_vision_model="gpt-4.1-mini",
        openai_stt_model="gpt-4o-mini-transcribe",
    )


class RobotRuntimeTests(unittest.TestCase):
    def test_start_syncs_persisted_hardware_state_after_reset_pose(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            store = StateStore(state_dir)
            store.save(
                RobotSession(
                    drive=DriveState(speed=25, steering=9),
                    camera=CameraState(pan=12, tilt=-3),
                    emergency_stop=True,
                )
            )

            runtime = RobotRuntime(make_config(state_dir))
            loop = asyncio.new_event_loop()
            try:
                runtime.start(loop)
                session = runtime.current_session()
            finally:
                runtime.stop()
                loop.close()

            persisted = store.load()
            self.assertEqual((session.drive.speed, session.drive.steering), (0, 0))
            self.assertEqual((session.camera.pan, session.camera.tilt), (0, 0))
            self.assertEqual((persisted.drive.speed, persisted.drive.steering), (0, 0))
            self.assertEqual((persisted.camera.pan, persisted.camera.tilt), (0, 0))
            self.assertTrue(persisted.emergency_stop)

    def test_record_camera_pose_persists_behavior_updates(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            runtime = RobotRuntime(make_config(state_dir))

            runtime.hardware.set_camera(18, -7)
            session = runtime.record_camera_pose(18, -7)
            persisted = StateStore(state_dir).load()

            self.assertEqual((session.camera.pan, session.camera.tilt), (18, -7))
            self.assertEqual((persisted.camera.pan, persisted.camera.tilt), (18, -7))


if __name__ == "__main__":
    unittest.main()
