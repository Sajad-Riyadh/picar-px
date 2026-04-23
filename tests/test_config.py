from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import picarx_unified.config as config_module
from picarx_unified.config import AppConfig, PROJECT_ROOT


class AppConfigTests(unittest.TestCase):
    def test_from_env_resolves_relative_paths_and_trims_text_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PICARX_HOST": " 127.0.0.1 ",
                "PICARX_STATE_DIR": "custom-state",
                "PICARX_STATIC_DIR": "custom-static",
                "PICARX_API_TOKEN": " secret-token ",
                "GEMINI_API_KEY": " gemini-test ",
                "PICARX_VOICE_CAPTURE_MAX_SECONDS": "7.5",
            },
            clear=True,
        ):
            config = AppConfig.from_env()

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.state_dir, (PROJECT_ROOT / "custom-state").resolve())
        self.assertEqual(config.static_dir, (PROJECT_ROOT / "custom-static").resolve())
        self.assertEqual(config.api_token, "secret-token")
        self.assertEqual(config.gemini_api_key, "gemini-test")
        self.assertEqual(config.voice_capture_max_seconds, 7.5)
        self.assertEqual(config.gemini_transcription_model, "gemini-2.5-flash")

    def test_from_env_loads_project_dotenv_without_overriding_real_environment(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            (project_root / ".env").write_text(
                "\n".join(
                    [
                        'GEMINI_API_KEY="dotenv-key"',
                        "PICARX_CAMERA_WIDTH=1296",
                        "PICARX_CAMERA_HEIGHT=972",
                        "PICARX_CAMERA_FPS=20",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.object(config_module, "PROJECT_ROOT", project_root):
                with patch.dict(os.environ, {"PICARX_CAMERA_WIDTH": "800"}, clear=True):
                    config = AppConfig.from_env()

        self.assertEqual(config.gemini_api_key, "dotenv-key")
        self.assertEqual(config.camera_width, 800)
        self.assertEqual(config.camera_height, 972)
        self.assertEqual(config.camera_fps, 20)


if __name__ == "__main__":
    unittest.main()
