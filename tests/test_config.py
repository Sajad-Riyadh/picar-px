from __future__ import annotations

import os
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
