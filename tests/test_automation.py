from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from companion.adapters.notify import notify
from companion.adapters.pomodoro import plan_pomodoro
from companion.cli import main
from companion.scheduled import ReminderError, ReminderStore, parse_in_duration


UTC = timezone.utc


def test_parse_in_duration_supports_units():
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    assert parse_in_duration("30s", now=now) == now + timedelta(seconds=30)
    assert parse_in_duration("10m", now=now) == now + timedelta(minutes=10)
    assert parse_in_duration("2h", now=now) == now + timedelta(hours=2)
    assert parse_in_duration("1d", now=now) == now + timedelta(days=1)


def test_parse_in_duration_rejects_garbage():
    with pytest.raises(ReminderError):
        parse_in_duration("tomorrow")


def test_recurrence_validation(tmp_path: Path):
    store = ReminderStore(tmp_path / "reminders.json")
    with pytest.raises(ReminderError, match="recurrence"):
        store.create(due_at="19:30", message="x", now=datetime(2026, 9, 9, 18, tzinfo=UTC), recurrence="monthly")
    with pytest.raises(ReminderError, match="weekdays"):
        store.create(due_at="19:30", message="x", now=datetime(2026, 9, 9, 18, tzinfo=UTC), recurrence="weekly", weekdays=["funday"])


def test_pomodoro_creates_two_reminders(tmp_path: Path):
    store = ReminderStore(tmp_path / "reminders.json")
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    planned = plan_pomodoro(store, work_minutes=25, break_minutes=5, message="Focus", now=now)
    assert len(planned) == 2
    assert len(store.list(status="pending")) == 2
    assert "descanso" in planned[0].message


def test_pomodoro_rejects_non_positive():
    from companion.scheduled import ReminderStore as RS

    with pytest.raises(ValueError):
        plan_pomodoro(RS(Path("dummy.json")), work_minutes=0, break_minutes=5)


def test_notify_empty_returns_false():
    assert notify("Companion", "   ") is False


def test_notify_returns_bool():
    assert isinstance(notify("Companion", "hello from test"), bool)


def test_cli_timer_creates_reminder(tmp_path: Path, capsys):
    assert main(["--root", str(tmp_path), "timer", "--in", "10m", "--message", "tea ready"]) == 0
    out = capsys.readouterr().out
    assert "rem_" in out
    assert len(ReminderStore(tmp_path / "reminders.json").list()) == 1


def test_cli_remind_add_with_in_and_recurrence(tmp_path: Path, capsys):
    assert main(["--root", str(tmp_path), "remind", "add", "--in", "1h", "--message", "stand up", "--recurrence", "daily"]) == 0
    stored = ReminderStore(tmp_path / "reminders.json").list()[0]
    assert stored.recurrence == "daily"


def test_cli_remind_add_requires_one_time_source(tmp_path: Path):
    assert main(["--root", str(tmp_path), "remind", "add", "--message", "x"]) == 2
    assert main(["--root", str(tmp_path), "remind", "add", "--at", "19:30", "--in", "10m", "--message", "x"]) == 2


def test_cli_remind_snooze(tmp_path: Path, capsys):
    assert main(["--root", str(tmp_path), "remind", "add", "--at", "19:30", "--message", "call"]) == 0
    reminder_id = ReminderStore(tmp_path / "reminders.json").list()[0].id
    capsys.readouterr()
    assert main(["--root", str(tmp_path), "remind", "snooze", reminder_id, "--minutes", "5"]) == 0
    assert ReminderStore(tmp_path / "reminders.json").list()[0].status == "snoozed"


def test_cli_pomodoro(tmp_path: Path, capsys):
    assert main(["--root", str(tmp_path), "pomodoro", "--work", "25", "--break", "5", "--message", "Deep"]) == 0
    assert len(ReminderStore(tmp_path / "reminders.json").list()) == 2


def test_cli_notify(tmp_path: Path, capsys):
    assert main(["--root", str(tmp_path), "notify", "hello"]) == 0
    assert "shown" in capsys.readouterr().out
