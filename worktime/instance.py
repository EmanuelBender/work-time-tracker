"""Single-instance identity and graceful process shutdown helpers."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import IO

from . import config


class InstanceGuard:
    """Owns an advisory lock and publishes the exact active process ID."""

    def __init__(self, lock_path=None, pid_path=None, process_id=None):
        project_root = Path(__file__).resolve().parents[1]
        self.lock_path = Path(lock_path or Path(config.support_dir()) / "worktime-gui.lock")
        self.pid_path = Path(pid_path or project_root / ".runtime" / "worktime.pid")
        self.process_id = int(process_id or os.getpid())
        self._lock_file: IO[str] | None = None

    @property
    def is_acquired(self):
        return self._lock_file is not None

    def acquire(self):
        if self.is_acquired:
            return True

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            return False

        self._lock_file = lock_file
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"{self.process_id}\n")
        lock_file.flush()

        self.pid_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.pid_path.with_name(f".{self.pid_path.name}.{self.process_id}.tmp")
        temporary.write_text(f"{self.process_id}\n", encoding="utf-8")
        os.replace(temporary, self.pid_path)
        return True

    def release(self):
        if not self._lock_file:
            return

        try:
            published_pid = int(self.pid_path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            published_pid = None
        if published_pid == self.process_id:
            try:
                self.pid_path.unlink()
            except FileNotFoundError:
                pass

        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
        self._lock_file.close()
        self._lock_file = None


def stop_tracker(tracker, thread, timeout):
    """Stop sampling, wait for its final session flush, and report completion."""

    tracker.stop()
    thread.join(timeout=timeout)
    return not thread.is_alive()
