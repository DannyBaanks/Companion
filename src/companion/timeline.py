"""Activity Timeline and Trust Center — local event history and diagnostics.

M16: timeline for states, messages, reminders, and adapter events;
filtering by companion/agent/type; export canonical JSONL; Doctor as
first-class diagnostic capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any


@dataclass(frozen=True)
class TimelineEntry:
    """One event in the activity timeline."""
    timestamp: str
    event_type: str
    agent: str
    companion_id: str | None = None
    detail: str | None = None
    source: str = "event"  # event | reminder | adapter | system

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "agent": self.agent,
            "source": self.source,
        }
        if self.companion_id:
            d["companion_id"] = self.companion_id
        if self.detail:
            d["detail"] = self.detail
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimelineEntry":
        return cls(
            timestamp=str(data.get("timestamp", "")),
            event_type=str(data.get("event_type", "")),
            agent=str(data.get("agent", "")),
            companion_id=data.get("companion_id"),
            detail=data.get("detail"),
            source=str(data.get("source", "event")),
        )


class ActivityTimeline:
    """Append-only local event timeline with filtering and export."""

    def __init__(self, root: Path):
        self.path = root / "timeline.jsonl"

    def append(self, entry: TimelineEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def entries(
        self,
        *,
        companion_id: str | None = None,
        agent: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[TimelineEntry]:
        result: list[TimelineEntry] = []
        if not self.path.exists():
            return result
        for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                entry = TimelineEntry.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                continue
            if companion_id and entry.companion_id != companion_id:
                continue
            if agent and entry.agent != agent:
                continue
            if event_type and entry.event_type != event_type:
                continue
            result.append(entry)
            if len(result) >= limit:
                break
        return result

    def export_jsonl(self, dest: Path, **filters: Any) -> int:
        """Export filtered timeline to a canonical JSONL file. Returns count."""
        entries = self.entries(**filters)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return len(entries)

    def summary(self) -> dict[str, Any]:
        """Compact summary for the Trust Center."""
        all_entries = self.entries(limit=10_000)
        by_type: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for e in all_entries:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
            by_source[e.source] = by_source.get(e.source, 0) + 1
        return {
            "total": len(all_entries),
            "by_type": by_type,
            "by_source": by_source,
        }
