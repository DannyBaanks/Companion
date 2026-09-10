"""Structured local logs. JSONL file plus stderr, no network."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def log_path(root: Path) -> Path:
    return root / "logs.jsonl"


def emit(root: Path, level: str, event: str, **fields: Any) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        **fields,
    }
    try:
        root.mkdir(parents=True, exist_ok=True)
        with log_path(root).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=True) + "\n")
    except OSError:
        pass
    if level in {"warning", "error"}:
        print(json.dumps(record, ensure_ascii=True), file=sys.stderr)


def read_tail(root: Path, limit: int = 50) -> list[dict[str, Any]]:
    path = log_path(root)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
