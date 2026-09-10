"""Atomic local writes with crash recovery. No network, no shell."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        try:
            os.fsync(stream.fileno())
        except OSError:
            pass
    tmp.replace(path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=True) + "\n")


def read_json_with_recovery(path: Path, *, default: Any) -> tuple[Any, bool]:
    """Return (data, recovered). Corrupt files are backed up to .corrupt."""
    if not path.exists():
        return default, False
    try:
        return json.loads(path.read_text(encoding="utf-8")), False
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        try:
            backup = path.with_suffix(path.suffix + ".corrupt")
            data = path.read_bytes()
            backup.write_bytes(data)
        except OSError:
            pass
        return default, True
