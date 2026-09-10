"""The transport contract shared by agents and the companion runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

EVENT_TYPES = {"say", "state", "mood", "move", "summon", "hide", "status"}
STATES = {"idle", "thinking", "working", "success", "error", "waiting", "hidden"}
POSITIONS = {"top-left", "top-right", "bottom-left", "bottom-right", "dock", "free"}


class ProtocolError(ValueError):
    """Raised when an incoming JSON object violates the protocol."""


def new_event(event_type: str, *, agent: str = "cli", companion_id: str | None = None, **fields: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "version": "companion-event-v1",
        "id": f"evt-{uuid.uuid4().hex[:12]}",
        "agent": agent,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        **fields,
    }
    if companion_id is not None:
        event["companion_id"] = companion_id
    validate_event(event)
    return event


def validate_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ProtocolError("event must be a JSON object")
    for key in ("id", "agent", "type"):
        if not isinstance(event.get(key), str) or not event[key].strip():
            raise ProtocolError(f"{key} must be a non-empty string")
    if event["type"] not in EVENT_TYPES:
        raise ProtocolError(f"unsupported event type: {event['type']}")
    if event["type"] == "say":
        if not isinstance(event.get("text"), str) or not event["text"].strip():
            raise ProtocolError("say events require non-empty text")
        priority = event.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ProtocolError("priority must be an integer")
    if event["type"] in {"state", "mood"}:
        value = event.get("value")
        if not isinstance(value, str) or value not in STATES:
            raise ProtocolError(f"value must be one of: {', '.join(sorted(STATES))}")
    if event["type"] == "move":
        value = event.get("value")
        if not isinstance(value, str) or value not in POSITIONS:
            raise ProtocolError(f"value must be one of: {', '.join(sorted(POSITIONS))}")
    ttl = event.get("ttl")
    if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or ttl < 0):
        raise ProtocolError("ttl must be a non-negative number")
    return event
