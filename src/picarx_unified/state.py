from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from filelock import FileLock

from .models import RobotSession, utc_now


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class StateStore:
    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "robot_session.json"
        self._lock = FileLock(str(state_dir / ".robot_session.lock"))
        state_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> RobotSession:
        with self._lock:
            if not self._path.exists():
                session = RobotSession()
                self._write_locked(session)
                return session
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return RobotSession.model_validate(data)

    def save(self, session: RobotSession) -> RobotSession:
        with self._lock:
            session.updated_at = utc_now()
            self._write_locked(session)
            return session

    def update(self, mutate: Callable[[RobotSession], None]) -> RobotSession:
        with self._lock:
            if self._path.exists():
                session = RobotSession.model_validate(
                    json.loads(self._path.read_text(encoding="utf-8"))
                )
            else:
                session = RobotSession()
            mutate(session)
            session.updated_at = utc_now()
            self._write_locked(session)
            return session

    def _write_locked(self, session: RobotSession) -> None:
        atomic_write(
            self._path,
            json.dumps(session.model_dump(mode="json"), indent=2, sort_keys=True),
        )
