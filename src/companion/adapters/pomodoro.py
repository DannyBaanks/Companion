"""Pomodoro as a separate event producer. Uses the scheduling pipeline only."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from ..scheduled import ReminderStore, ScheduledEvent, local_now


def plan_pomodoro(
    store: ReminderStore,
    *,
    work_minutes: int = 25,
    break_minutes: int = 5,
    message: str = "Pomodoro",
    companion_id: str | None = None,
    now: datetime | None = None,
) -> Sequence[ScheduledEvent]:
    """Create work-end and break-end one-shot reminders. Returns both records."""
    if work_minutes <= 0 or break_minutes <= 0:
        raise ValueError("work and break minutes must be positive")
    current = now or local_now()
    base_message = message.strip() or "Pomodoro"
    work_end = current + timedelta(minutes=work_minutes)
    break_end = work_end + timedelta(minutes=break_minutes)
    first = store.create(
        due_at=work_end.isoformat(),
        message=f"{base_message}: fin del foco, toma un descanso",
        companion_id=companion_id,
        mood="success",
        now=current,
    )
    second = store.create(
        due_at=break_end.isoformat(),
        message=f"{base_message}: descanso terminado",
        companion_id=companion_id,
        mood="working",
        now=current,
    )
    return [first, second]
