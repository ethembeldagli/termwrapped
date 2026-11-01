"""Small helpers shared by the collectors. Nothing here touches the network."""

from __future__ import annotations

import datetime as dt
import os
import shutil
import sqlite3
import subprocess

HOME = os.path.expanduser("~")


def run(args: list[str], timeout: float = 15) -> str | None:
    """Run a command and return its stdout, or None if anything goes wrong."""
    if not shutil.which(args[0]):
        return None
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def open_sqlite_ro(path: str) -> sqlite3.Connection | None:
    """Open a database read-only without taking locks on a live file."""
    if not os.path.isfile(path):
        return None
    try:
        return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=2)
    except sqlite3.Error:
        return None


def year_bounds(year: int) -> tuple[float, float]:
    """Local-time epoch seconds for [Jan 1 of year, Jan 1 of year+1)."""
    start = dt.datetime(year, 1, 1).timestamp()
    end = dt.datetime(year + 1, 1, 1).timestamp()
    return start, end


def in_year(ts: float | None, year: int) -> bool:
    if ts is None:
        return False
    start, end = year_bounds(year)
    return start <= ts < end


def in_container() -> bool:
    return (
        os.path.exists("/run/.containerenv")
        or os.path.exists("/.dockerenv")
        or bool(os.environ.get("container"))
    )
