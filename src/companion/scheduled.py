"""Persistent one-shot local reminders and their event producer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, time, timedelta
import json
from pathlib import Path
import re
from typing import Callable
import uuid

from .protocol import STATES, new_event
from .queue import append_jsonl
from .storage import atomic_write_json, read_json_with_recovery

REMINDER_STATUSES = {"pending", "fired", "cancelled", "snoozed"}
RECURRENCES = {"daily", "weekly", "countdown"}
_CLOCK_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")
_DURATION = re.compile(r"^(\d+)\s*([smhd])$", re.IGNORECASE)
WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


class ReminderError(ValueError):
    """Raised when a reminder cannot be represented safely."""


def local_now() -> datetime:
    return datetime.now().astimezone()


def parse_in_duration(value: str, *, now: datetime | None = None) -> datetime:
    current = now or local_now()
    match = _DURATION.fullmatch(value.strip())
    if not match:
        raise ReminderError("duration must look like 30s, 10m, 2h, or 1d")
    amount, unit = int(match.group(1)), match.group(2).lower()
    deltas = {"s": timedelta(seconds=amount), "m": timedelta(minutes=amount), "h": timedelta(hours=amount), "d": timedelta(days=amount)}
    return current + deltas[unit]


def parse_due_at(value: str, *, now: datetime | None = None) -> datetime:
    """Parse ISO-8601 or HH:MM and always return an aware local/offset datetime."""
    value = value.strip()
    current = now or local_now()
    if current.tzinfo is None:
        current = current.astimezone()
    match = _CLOCK_TIME.fullmatch(value)
    if match:
        hour, minute = (int(part) for part in match.groups())
        if hour > 23 or minute > 59:
            raise ReminderError("time must use HH:MM with a valid 24-hour time")
        candidate = datetime.combine(current.date(), time(hour, minute), tzinfo=current.tzinfo)
        if candidate <= current:
            candidate += timedelta(days=1)
        return candidate
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReminderError("time must be HH:MM or ISO-8601, for example 2026-09-09T19:30:00-06:00") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=current.tzinfo)
    return parsed


@dataclass
class ScheduledEvent:
    id: str
    due_at: str
    message: str
    companion_id: str | None = None
    mood: str | None = None
    ttl: float = 8
    created_at: str = ""
    status: str = "pending"
    recurrence: str | None = None
    weekdays: list[str] | None = None
    snoozed_until: str | None = None


class ReminderStore:
    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> list[ScheduledEvent]:
        raw, _recovered = read_json_with_recovery(self.path, default=[])
        if not isinstance(raw, list):
            raise ReminderError("reminder store must contain a JSON array")
        items: list[ScheduledEvent] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            known = {field for field in ScheduledEvent.__dataclass_fields__}
            filtered = {key: entry[key] for key in entry if key in known}
            try:
                items.append(ScheduledEvent(**filtered))  # type: ignore[arg-type]
            except TypeError:
                continue
        return items

    def _write(self, reminders: list[ScheduledEvent]) -> None:
        atomic_write_json(self.path, [asdict(item) for item in reminders])

    def list(self, *, status: str | None = None) -> list[ScheduledEvent]:
        reminders = self._read()
        return [item for item in reminders if status is None or item.status == status]

    def create(self, *, due_at: str, message: str, companion_id: str | None = None, mood: str | None = None, ttl: float = 8, now: datetime | None = None, recurrence: str | None = None, weekdays: list[str] | None = None) -> ScheduledEvent:
        if not message.strip():
            raise ReminderError("message must not be empty")
        if mood is not None and mood not in STATES:
            raise ReminderError(f"mood must be one of: {', '.join(sorted(STATES))}")
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or ttl < 0:
            raise ReminderError("ttl must be a non-negative number")
        if recurrence is not None and recurrence not in RECURRENCES:
            raise ReminderError(f"recurrence must be one of: {', '.join(sorted(RECURRENCES))}")
        if weekdays is not None:
            normalized = [day.lower()[:3] for day in weekdays]
            unknown = [day for day in normalized if day not in WEEKDAYS]
            if unknown:
                raise ReminderError(f"unknown weekdays: {', '.join(unknown)}")
            weekdays = normalized
        parsed = parse_due_at(due_at, now=now)
        reminder = ScheduledEvent(
            id=f"rem_{uuid.uuid4().hex[:12]}",
            due_at=parsed.isoformat(),
            message=message.strip(),
            companion_id=companion_id,
            mood=mood,
            ttl=ttl,
            created_at=(now or local_now()).isoformat(),
            recurrence=recurrence,
            weekdays=weekdays,
        )
        reminders = self._read()
        reminders.append(reminder)
        self._write(reminders)
        return reminder

    def cancel(self, reminder_id: str) -> ScheduledEvent:
        reminders = self._read()
        for reminder in reminders:
            if reminder.id == reminder_id:
                if reminder.status in {"pending", "snoozed"}:
                    reminder.status = "cancelled"
                    self._write(reminders)
                return reminder
        raise ReminderError(f"reminder not found: {reminder_id}")

    def snooze(self, reminder_id: str, *, minutes: int = 10, now: datetime | None = None) -> ScheduledEvent:
        current = now or local_now()
        reminders = self._read()
        for reminder in reminders:
            if reminder.id == reminder_id:
                if reminder.status not in {"pending", "snoozed"}:
                    raise ReminderError(f"cannot snooze reminder in status: {reminder.status}")
                snoozed_until = current + timedelta(minutes=minutes)
                reminder.snoozed_until = snoozed_until.isoformat()
                reminder.status = "snoozed"
                self._write(reminders)
                return reminder
        raise ReminderError(f"reminder not found: {reminder_id}")

    def fire_due(self, *, inbox: Path, now: datetime | None = None) -> list[ScheduledEvent]:
        current = now or local_now()
        reminders = self._read()
        due: list[ScheduledEvent] = []

        for reminder in reminders:
            if reminder.status == "snoozed" and reminder.snoozed_until:
                snoozed_dt = datetime.fromisoformat(reminder.snoozed_until)
                if snoozed_dt <= current:
                    reminder.status = "pending"
                    reminder.snoozed_until = None
                    due.append(reminder)
            elif reminder.status == "pending":
                due_dt = datetime.fromisoformat(reminder.due_at)
                if due_dt <= current:
                    due.append(reminder)

        if not due:
            return []

        fired_reminders: list[ScheduledEvent] = []
        emissions: list[dict] = []
        for reminder in due:
            due_dt = datetime.fromisoformat(reminder.due_at)
            base = due_dt if due_dt > current else current
            original_message = reminder.message
            if reminder.recurrence == "daily":
                reminder.due_at = (base + timedelta(days=1)).isoformat()
                fired_reminders.append(replace(reminder, status="fired", message=original_message, due_at=due_dt.isoformat()))
                emissions.append({"message": original_message, "mood": reminder.mood, "ttl": reminder.ttl, "companion_id": reminder.companion_id, "reminder_id": reminder.id})
            elif reminder.recurrence == "weekly":
                if reminder.weekdays:
                    wanted = set(reminder.weekdays)
                    advanced = None
                    for i in range(1, 8):
                        candidate = base + timedelta(days=i)
                        if candidate.strftime("%a").lower()[:3] in wanted:
                            advanced = candidate
                            break
                    reminder.due_at = (advanced or (base + timedelta(days=7))).isoformat()
                else:
                    reminder.due_at = (due_dt + timedelta(days=7)).isoformat()
                fired_reminders.append(replace(reminder, status="fired", message=original_message, due_at=due_dt.isoformat()))
                emissions.append({"message": original_message, "mood": reminder.mood, "ttl": reminder.ttl, "companion_id": reminder.companion_id, "reminder_id": reminder.id})
            elif reminder.recurrence == "countdown":
                try:
                    remaining = int(original_message.strip())
                except (ValueError, AttributeError):
                    remaining = 1
                if remaining > 1:
                    reminder.message = str(remaining - 1)
                    reminder.due_at = (current + timedelta(minutes=1)).isoformat()
                    fired_reminders.append(replace(reminder, status="fired", message=original_message, due_at=due_dt.isoformat()))
                    emissions.append({"message": original_message, "mood": reminder.mood, "ttl": reminder.ttl, "companion_id": reminder.companion_id, "reminder_id": reminder.id})
                else:
                    reminder.status = "fired"
                    fired_reminders.append(replace(reminder, status="fired"))
                    emissions.append({"message": original_message, "mood": reminder.mood, "ttl": reminder.ttl, "companion_id": reminder.companion_id, "reminder_id": reminder.id})
            else:
                reminder.status = "fired"
                fired_reminders.append(replace(reminder, status="fired"))
                emissions.append({"message": original_message, "mood": reminder.mood, "ttl": reminder.ttl, "companion_id": reminder.companion_id, "reminder_id": reminder.id})

        self._write(reminders)

        for item in emissions:
            append_jsonl(inbox, new_event("say", agent="scheduler", text=item["message"], ttl=item["ttl"], companion_id=item["companion_id"], reminder_id=item["reminder_id"]))
            if item["mood"]:
                append_jsonl(inbox, new_event("mood", agent="scheduler", value=item["mood"], companion_id=item["companion_id"], reminder_id=item["reminder_id"]))
        return fired_reminders


class LocalScheduler:
    def __init__(self, store: ReminderStore, inbox: Path, clock: Callable[[], datetime] = local_now):
        self.store = store
        self.inbox = inbox
        self.clock = clock

    def tick(self) -> list[ScheduledEvent]:
        return self.store.fire_due(inbox=self.inbox, now=self.clock())
