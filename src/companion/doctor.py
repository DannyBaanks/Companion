"""Local diagnostics. Read-only except for ensuring the root exists."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Any

from . import __version__  # noqa: F401 - re-exported for diagnostics


def _check_writable(root: Path, issues: list[str]) -> dict[str, Any]:
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"writable": True}
    except OSError as exc:
        issues.append(f"root not writable: {exc}")
        return {"writable": False}


def run_checks(root: Path, *, companion_id: str | None = None) -> dict[str, Any]:
    from .scheduled import ReminderStore

    issues: list[str] = []
    state_name = "state.json" if companion_id is None else f"state-{companion_id}.json"
    result: dict[str, Any] = {
        "root": str(root),
        "platform": sys.platform,
        "python": platform.python_version(),
        "files": {},
    }
    result["files"]["writable"] = _check_writable(root, issues)

    for name in ("inbox.jsonl", "outbox.jsonl", state_name, "reminders.json"):
        path = root / name
        info: dict[str, Any] = {"exists": path.exists()}
        if path.exists():
            try:
                info["bytes"] = path.stat().st_size
                if path.suffix == ".json":
                    json.loads(path.read_text(encoding="utf-8"))
                    info["valid_json"] = True
            except (OSError, json.JSONDecodeError) as exc:
                info["valid_json"] = False
                issues.append(f"{name} invalid: {exc}")
        result["files"][name] = info

    corrupt = sorted(p.name for p in root.glob("*.corrupt"))
    if corrupt:
        issues.append(f"recovered corrupt files: {', '.join(corrupt)}")
    result["corrupt_backups"] = corrupt

    try:
        stored = ReminderStore(root / "reminders.json").list()
        result["reminders"] = {"count": len(stored), "ok": True}
    except Exception as exc:  # noqa: BLE001 - diagnostics must not crash
        result["reminders"] = {"count": 0, "ok": False}
        issues.append(f"reminders unreadable: {exc}")

    try:
        import tkinter

        result["tk"] = {"available": True, "version": str(tkinter.TkVersion)}
    except Exception as exc:  # noqa: BLE001
        result["tk"] = {"available": False, "error": str(exc)}
        issues.append(f"tk unavailable: {exc}")

    optional: dict[str, bool] = {}
    for mod in ("websockets", "plyer"):
        try:
            __import__(mod)
            optional[mod] = True
        except ImportError:
            optional[mod] = False
    result["optional"] = optional

    network = {"default": "off", "websocket": "opt-in localhost only", "shell": "never"}
    result["security"] = network

    result["ok"] = not issues
    result["issues"] = issues
    return result
