from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from filelock import FileLock
from pydantic import ValidationError

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
            session = self._load_locked()
            if not self._path.exists():
                self._write_locked(session)
            return session

    def save(self, session: RobotSession) -> RobotSession:
        with self._lock:
            session.updated_at = utc_now()
            self._write_locked(session)
            return session

    def update(self, mutate: Callable[[RobotSession], None]) -> RobotSession:
        with self._lock:
            session = self._load_locked()
            mutate(session)
            session.updated_at = utc_now()
            self._write_locked(session)
            return session

    def _load_locked(self) -> RobotSession:
        if not self._path.exists():
            return RobotSession()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return RobotSession.model_validate(data)
        except (OSError, json.JSONDecodeError, TypeError, ValidationError, ValueError):
            self._archive_corrupt_state()
            return RobotSession()

    def _archive_corrupt_state(self) -> None:
        if not self._path.exists():
            return
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = self._path.with_suffix(f".corrupt-{timestamp}{self._path.suffix}")
        counter = 1
        while backup_path.exists():
            backup_path = self._path.with_suffix(
                f".corrupt-{timestamp}-{counter}{self._path.suffix}"
            )
            counter += 1
        try:
            os.replace(self._path, backup_path)
        except OSError:
            pass

    def _write_locked(self, session: RobotSession) -> None:
        atomic_write(
            self._path,
            json.dumps(session.model_dump(mode="json"), indent=2, sort_keys=True),
        )
