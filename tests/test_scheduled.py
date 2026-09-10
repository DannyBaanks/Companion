from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from companion.runtime import Runtime
from companion.scheduled import LocalScheduler, ReminderError, ReminderStore


UTC = timezone.utc


def test_create_persists_and_restart_keeps_pending(tmp_path: Path):
    now = datetime(2026, 9, 9, 18, 0, tzinfo=UTC)
    store_path = tmp_path / "reminders.json"
    ReminderStore(store_path).create(due_at="19:30", message="Sacar la ropa", now=now)

    reminders = ReminderStore(store_path).list()
    assert len(reminders) == 1
    assert reminders[0].status == "pending"
    assert reminders[0].due_at == "2026-09-09T19:30:00+00:00"


def test_due_event_uses_existing_inbox_and_fires_once(tmp_path: Path):
    now = datetime(2026, 9, 9, 19, 29, 59, tzinfo=UTC)
    store = ReminderStore(tmp_path / "reminders.json")
    reminder = store.create(due_at="19:30", message="Sacar la ropa", mood="success", now=now)
    clock = [now]
    scheduler = LocalScheduler(store, tmp_path / "inbox.jsonl", clock=lambda: clock[0])

    assert scheduler.tick() == []
    clock[0] = now + timedelta(seconds=1)
    assert [item.id for item in scheduler.tick()] == [reminder.id]
    assert scheduler.tick() == []
    assert store.list()[0].status == "fired"

    events = [json.loads(line) for line in (tmp_path / "inbox.jsonl").read_text().splitlines()]
    assert [event["type"] for event in events] == ["say", "mood"]
    runtime = Runtime(tmp_path)
    assert runtime.process_once() == 2
    assert runtime.state["message"]["text"] == "Sacar la ropa"


def test_overdue_pending_fires_after_restart(tmp_path: Path):
    now = datetime(2026, 9, 9, 20, 0, tzinfo=UTC)
    store = ReminderStore(tmp_path / "reminders.json")
    reminder = store.create(due_at="19:30", message="Cerrar build", now=datetime(2026, 9, 9, 18, tzinfo=UTC))
    restarted = ReminderStore(tmp_path / "reminders.json")

    assert [item.id for item in LocalScheduler(restarted, tmp_path / "inbox.jsonl", clock=lambda: now).tick()] == [reminder.id]
    assert restarted.list()[0].status == "fired"


def test_cancelled_reminder_never_fires(tmp_path: Path):
    now = datetime(2026, 9, 9, 18, tzinfo=UTC)
    store = ReminderStore(tmp_path / "reminders.json")
    reminder = store.create(due_at="19:30", message="No ejecutar", now=now)
    store.cancel(reminder.id)

    assert LocalScheduler(store, tmp_path / "inbox.jsonl", clock=lambda: now + timedelta(hours=2)).tick() == []
    assert not (tmp_path / "inbox.jsonl").exists()


@pytest.mark.parametrize("value", ["25:00", "tomorrow", "19:xx"])
def test_invalid_timestamp_fails_clearly(tmp_path: Path, value: str):
    with pytest.raises(ReminderError):
        ReminderStore(tmp_path / "reminders.json").create(
            due_at=value,
            message="invalid",
            now=datetime(2026, 9, 9, 18, tzinfo=UTC),
        )


def test_snooze_reminder(tmp_path: Path):
    store = ReminderStore(tmp_path / "reminders.json")
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    reminder = store.create(due_at="2026-09-09T12:05:00+00:00", message="reunion", now=now)
    assert reminder.status == "pending"

    snoozed = store.snooze(reminder.id, minutes=15, now=now)
    assert snoozed.status == "snoozed"
    assert snoozed.snoozed_until is not None

    fired = store.fire_due(inbox=tmp_path / "inbox.jsonl", now=now + timedelta(minutes=10))
    assert len(fired) == 0

    fired = store.fire_due(inbox=tmp_path / "inbox.jsonl", now=now + timedelta(minutes=20))
    assert len(fired) == 1
    assert fired[0].status == "fired"


def test_daily_recurrence(tmp_path: Path):
    store = ReminderStore(tmp_path / "reminders.json")
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    reminder = store.create(due_at="2026-09-09T12:00:00+00:00", message="diario", now=now, recurrence="daily")

    fired = store.fire_due(inbox=tmp_path / "inbox.jsonl", now=now)
    assert len(fired) == 1

    reminder_data = store._read()[0]
    assert reminder_data.status == "pending"
    assert "2026-09-10" in reminder_data.due_at


def test_countdown_recurrence(tmp_path: Path):
    store = ReminderStore(tmp_path / "reminders.json")
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    reminder = store.create(due_at="2026-09-09T12:00:00+00:00", message="5", now=now, recurrence="countdown")

    fired = store.fire_due(inbox=tmp_path / "inbox.jsonl", now=now)
    assert len(fired) == 1

    reminder_data = store._read()[0]
    assert reminder_data.status == "pending"
    assert reminder_data.message == "4"


def test_weekly_recurrence(tmp_path: Path):
    store = ReminderStore(tmp_path / "reminders.json")
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    reminder = store.create(due_at="2026-09-09T12:00:00+00:00", message="semanal", now=now, recurrence="weekly")

    fired = store.fire_due(inbox=tmp_path / "inbox.jsonl", now=now)
    assert len(fired) == 1

    reminder_data = store._read()[0]
    assert reminder_data.status == "pending"
    assert "2026-09-16" in reminder_data.due_at


def test_cancel_snoozed_reminder(tmp_path: Path):
    store = ReminderStore(tmp_path / "reminders.json")
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    reminder = store.create(due_at="2026-09-09T12:05:00+00:00", message="test", now=now)
    store.snooze(reminder.id, minutes=10, now=now)

    cancelled = store.cancel(reminder.id)
    assert cancelled.status == "cancelled"


def test_fired_reminder_cannot_snooze(tmp_path: Path):
    store = ReminderStore(tmp_path / "reminders.json")
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    reminder = store.create(due_at="2026-09-09T12:00:00+00:00", message="test", now=now)
    store.fire_due(inbox=tmp_path / "inbox.jsonl", now=now)

    with pytest.raises(ReminderError, match="cannot snooze"):
        store.snooze(reminder.id, minutes=10, now=now)
