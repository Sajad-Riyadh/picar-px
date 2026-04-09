from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from picarx_unified.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_load_recovers_from_corrupt_state_file(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir)
            state_dir.mkdir(parents=True, exist_ok=True)
            state_path = state_dir / "robot_session.json"
            state_path.write_text("{ not valid json", encoding="utf-8")

            session = StateStore(state_dir).load()

            self.assertFalse(session.emergency_stop)
            self.assertTrue(state_path.exists())
            json.loads(state_path.read_text(encoding="utf-8"))
            backups = list(state_dir.glob("robot_session.corrupt-*.json"))
            self.assertEqual(len(backups), 1)


if __name__ == "__main__":
    unittest.main()
