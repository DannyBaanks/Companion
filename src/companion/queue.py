"""Append-only JSONL transport used by agents and the local runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .protocol import ProtocolError, validate_event


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n")
        stream.flush()
        try:
            os.fsync(stream.fileno())
        except OSError:
            pass


def read_jsonl(path: Path, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], offset
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        stream.seek(offset)
        while True:
            line_start = stream.tell()
            line = stream.readline()
            if not line:
                break
            if not line.endswith("\n"):
                return events, line_start
            offset = stream.tell()
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                events.append(validate_event(event))
            except (json.JSONDecodeError, ProtocolError) as exc:
                events.append({"_error": str(exc), "_raw": line.rstrip("\n")})
    return events, offset
