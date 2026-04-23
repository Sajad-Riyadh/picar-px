from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from picarx_unified.config import AppConfig
from picarx_unified.runtime import RobotRuntime
from picarx_unified.state import StateStore
from picarx_unified.models import CameraState, DriveRequest, DriveState, RobotSession, SettingsUpdateRequest


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
        gemini_transcription_model="gemini-2.5-flash",
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

    def test_update_settings_applies_camera_color_gains(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            runtime = RobotRuntime(make_config(state_dir))

            session = runtime.update_settings(
                SettingsUpdateRequest(
                    greeting_text="Hello there. Welcome.",
                    greeting_enabled=True,
                    greeting_mode="simple_greeting",
                    auto_tracking_enabled=True,
                    camera_step_degrees=5,
                    camera_red_gain=1.4,
                    camera_green_gain=1.05,
                    camera_blue_gain=0.8,
                    startup_voice_mode="mute",
                    startup_audio_target="car",
                )
            )
            persisted = StateStore(state_dir).load()

            self.assertAlmostEqual(session.settings.camera_red_gain, 1.4)
            self.assertAlmostEqual(session.settings.camera_green_gain, 1.05)
            self.assertAlmostEqual(session.settings.camera_blue_gain, 0.8)
            self.assertAlmostEqual(persisted.settings.camera_red_gain, 1.4)
            self.assertAlmostEqual(persisted.settings.camera_green_gain, 1.05)
            self.assertAlmostEqual(persisted.settings.camera_blue_gain, 0.8)
            red_gain, green_gain, blue_gain = runtime.camera.color_gains
            self.assertAlmostEqual(red_gain, 1.4)
            self.assertAlmostEqual(green_gain, 1.05)
            self.assertAlmostEqual(blue_gain, 0.8)

    def test_manual_drive_sets_manual_override_even_when_autonomy_is_enabled(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            runtime = RobotRuntime(make_config(state_dir))

            runtime.update_settings(SettingsUpdateRequest(autonomous_mode_enabled=True))
            runtime.apply_drive(DriveRequest(speed=15, steering=0, source="browser"))
            session = runtime.current_session()

            self.assertTrue(session.manual_override_active)
            self.assertFalse(session.autonomous_mode_active)

    def test_steering_only_command_turns_wheels_without_drive_motion(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            runtime = RobotRuntime(make_config(Path(tmp_dir)))

            session = runtime.apply_drive(DriveRequest(speed=0, steering=20, source="browser"))
            hardware = runtime.hardware.snapshot()

            self.assertEqual(session.drive.speed, 0)
            self.assertEqual(session.drive.steering, 20)
            self.assertEqual(hardware.drive_speed, 0)
            self.assertEqual(hardware.steering, 20)

    def test_clear_emergency_stop_releases_estop_without_restoring_motion(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            runtime = RobotRuntime(make_config(Path(tmp_dir)))

            runtime.trigger_emergency_stop("Test stop.")
            session = runtime.clear_emergency_stop()
            hardware = runtime.hardware.snapshot()

            self.assertFalse(session.emergency_stop)
            self.assertEqual(session.drive.speed, 0)
            self.assertEqual(session.drive.steering, 0)
            self.assertEqual(hardware.drive_speed, 0)


if __name__ == "__main__":
    unittest.main()
