"""Stateful JSONL runtime. The GUI will consume the same Runtime later."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Callable

from .protocol import validate_event
from .queue import append_jsonl, read_jsonl
from .storage import atomic_write_json, read_json_with_recovery


class Runtime:
    def __init__(self, root: Path, *, companion_id: str | None = None, clock: Callable[[], float] = time.time):
        self.root = root
        self.companion_id = companion_id
        self.inbox = root / "inbox.jsonl"
        self.outbox = root / "outbox.jsonl"
        self.state_path = root / ("state.json" if companion_id is None else f"state-{companion_id}.json")
        self.offset = 0
        self.clock = clock
        self._message_queue: list[dict[str, Any]] = []
        self._message_sequence = 0
        self.state: dict[str, Any] = {
            "visible": False,
            "state": "idle",
            "mood": "idle",
            "position": "bottom-right",
            "message": None,
        }
        self.recovered = False
        self._load_state()

    def _load_state(self) -> None:
        data, recovered = read_json_with_recovery(self.state_path, default={})
        self.recovered = recovered
        if isinstance(data, dict):
            for key in ("visible", "state", "mood", "position", "message"):
                if key in data:
                    self.state[key] = data[key]
            offset = data.get("inbox_offset")
            if isinstance(offset, int) and offset >= 0:
                inbox_size = self.inbox.stat().st_size if self.inbox.exists() else 0
                self.offset = min(offset, inbox_size)
            seq = data.get("message_sequence")
            if isinstance(seq, int) and seq >= 0:
                self._message_sequence = seq
            queue = data.get("message_queue")
            if isinstance(queue, list):
                self._message_queue = [item for item in queue if self._valid_queued_message(item)]
                sequences = [item["sequence"] for item in self._message_queue]
                if sequences:
                    self._message_sequence = max(self._message_sequence, *sequences)

    @staticmethod
    def _valid_queued_message(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        if not isinstance(value.get("text"), str) or not value["text"]:
            return False
        ttl = value.get("ttl")
        if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or ttl < 0):
            return False
        priority = value.get("priority")
        sequence = value.get("sequence")
        return (
            isinstance(priority, int)
            and not isinstance(priority, bool)
            and isinstance(sequence, int)
            and not isinstance(sequence, bool)
            and sequence >= 0
            and value.get("expires_at") is None
        )

    def _save_state(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = dict(self.state)
        payload["inbox_offset"] = self.offset
        payload["message_sequence"] = self._message_sequence
        payload["message_queue"] = self._message_queue
        atomic_write_json(self.state_path, payload)

    def process_once(self) -> int:
        self.expire_messages()
        events, self.offset = read_jsonl(self.inbox, self.offset)
        processed = 0
        for event in events:
            processed += 1
            if "_error" in event:
                self._emit("error", error=event["_error"], raw=event["_raw"])
                continue
            self._apply(event)
        if processed:
            self._save_state()
        return processed

    def expire_messages(self) -> None:
        message = self.state.get("message")
        if not message or message.get("expires_at") is None or self.clock() < message["expires_at"]:
            return
        self.state["message"] = None
        self._show_next_message()
        self._save_state()

    def _show_next_message(self) -> None:
        if self._message_queue:
            self._message_queue.sort(key=lambda item: (-item["priority"], item["sequence"]))
            message = self._message_queue.pop(0)
            message["expires_at"] = self.clock() + message["ttl"] if message["ttl"] is not None else None
            self.state["message"] = message
        else:
            self.state["message"] = None

    def _apply(self, event: dict[str, Any]) -> None:
        event_id = event["id"]
        event_type = event["type"]
        if self.companion_id is not None:
            event_companion_id = event.get("companion_id")
            if event_companion_id is not None and event_companion_id != self.companion_id:
                self._emit("accepted", event_id=event_id, event_type=event_type)
                return
        if event_type in {"summon", "status"}:
            self.state["visible"] = True
        elif event_type == "hide":
            self.state["visible"] = False
            self.state["state"] = "hidden"
        elif event_type == "say":
            self._message_sequence += 1
            ttl = event.get("ttl")
            message = {
                "text": event["text"],
                "ttl": ttl,
                "priority": event.get("priority", 0),
                "sequence": self._message_sequence,
                "expires_at": None,
            }
            current = self.state.get("message")
            if current is None or message["priority"] > current.get("priority", 0):
                if current is not None:
                    current["expires_at"] = None
                    self._message_queue.append(current)
                message["expires_at"] = self.clock() + ttl if ttl is not None else None
                self.state["message"] = message
            else:
                self._message_queue.append(message)
            self.state["visible"] = True
        elif event_type in {"state", "mood"}:
            self.state[event_type] = event["value"]
            self.state["visible"] = True
        elif event_type == "move":
            self.state["position"] = event["value"]
        self._emit("accepted", event_id=event_id, event_type=event_type)

    def _emit(self, status: str, **fields: Any) -> None:
        append_jsonl(self.outbox, {"version": "companion-event-v1", "status": status, **fields})

    def run(self, poll_interval: float = 0.1) -> None:
        while True:
            self.process_once()
            time.sleep(poll_interval)
