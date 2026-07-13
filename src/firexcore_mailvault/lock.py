from __future__ import annotations

from pathlib import Path

from filelock import FileLock, Timeout

from firexcore_mailvault.errors import MailVaultError


class RunLock:
    def __init__(self, path: Path, timeout_seconds: float = 0.0) -> None:
        self._lock = FileLock(str(path), timeout=timeout_seconds)

    def __enter__(self) -> RunLock:
        try:
            self._lock.acquire()
        except Timeout as exc:
            raise MailVaultError("Another archive process is already running.") from exc
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._lock.release()
