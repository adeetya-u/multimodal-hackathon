"""Prevent duplicate local API processes (fcntl lock on .run/api.lock)."""

from __future__ import annotations

import fcntl
import os
import sys
from pathlib import Path

_lock_fd: int | None = None


def repo_run_dir() -> Path:
    override = os.environ.get("SURGICAL_RUN_DIR", "").strip()
    if override:
        return Path(override)
    # backend/cases/dev_lock.py → repo root
    return Path(__file__).resolve().parents[2] / ".run"


def acquire_api_lock() -> None:
    """Exit if another Scalpel API process already holds the API lock."""
    if os.environ.get("SURGICAL_ALLOW_DUPLICATE", "0") == "1":
        return

    global _lock_fd
    run_dir = repo_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    lock_path = run_dir / "api.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        holder = ""
        try:
            holder = os.read(fd, 64).decode("utf-8", errors="ignore").strip()
        except OSError:
            pass
        os.close(fd)
        msg = "Scalpel API already running"
        if holder:
            msg += f" (pid {holder})"
        msg += ". Use ./stop.sh or ./start.sh --force."
        print(msg, file=sys.stderr)
        raise SystemExit(1)

    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    _lock_fd = fd


def release_api_lock() -> None:
    global _lock_fd
    if _lock_fd is None:
        return
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_UN)
        os.close(_lock_fd)
    except OSError:
        pass
    _lock_fd = None
