"""Personality settings — tone, verbosity, and message policy.

M15: configurable greetings, success/error messages, tone control.
Personality is presentation policy over canonical events: no inference,
no cloud calls, no hidden interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any


@dataclass(frozen=True)
class PersonalityProfile:
    """Local personality configuration for a companion."""
    tone: str = "friendly"           # friendly | formal | playful | minimal
    verbosity: str = "normal"        # quiet | normal | verbose
    greeting: str = "Hello!"
    success_message: str = "Done!"
    error_prefix: str = "Oops:"
    thinking_message: str = "Thinking..."
    waiting_message: str = "Waiting..."
    idle_messages: list[str] = field(default_factory=lambda: ["Ready."])

    @classmethod
    def load(cls, data: dict[str, Any]) -> "PersonalityProfile":
        return cls(
            tone=str(data.get("tone", "friendly")),
            verbosity=str(data.get("verbosity", "normal")),
            greeting=str(data.get("greeting", "Hello!")),
            success_message=str(data.get("success_message", "Done!")),
            error_prefix=str(data.get("error_prefix", "Oops:")),
            thinking_message=str(data.get("thinking_message", "Thinking...")),
            waiting_message=str(data.get("waiting_message", "Waiting...")),
            idle_messages=[str(m) for m in data.get("idle_messages", ["Ready."]) if m],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tone": self.tone,
            "verbosity": self.verbosity,
            "greeting": self.greeting,
            "success_message": self.success_message,
            "error_prefix": self.error_prefix,
            "thinking_message": self.thinking_message,
            "waiting_message": self.waiting_message,
            "idle_messages": self.idle_messages,
        }

    def message_for_state(self, state: str, detail: str | None = None) -> str | None:
        """Return a personality-appropriate message for a semantic state."""
        if state == "idle":
            return self.idle_messages[0] if self.idle_messages else None
        if state == "thinking":
            return self.thinking_message
        if state == "waiting":
            return self.waiting_message
        if state == "success":
            return self.success_message
        if state == "error":
            msg = detail or "something went wrong"
            return f"{self.error_prefix} {msg}"
        return None


DEFAULT_PROFILE = PersonalityProfile()


class PersonalityStore:
    """Persistent personality store in the companion data root."""

    def __init__(self, root: Path):
        self.path = root / "personality.json"

    def load(self) -> PersonalityProfile:
        if not self.path.exists():
            return DEFAULT_PROFILE
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return PersonalityProfile.load(data)
        except (json.JSONDecodeError, OSError):
            return DEFAULT_PROFILE

    def save(self, profile: PersonalityProfile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(profile.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
