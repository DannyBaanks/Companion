"""Lifecycle management for processes launched by the current Companion Hub."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
import subprocess
from typing import Callable, Protocol

from companion.protocol import new_event
from companion.queue import append_jsonl

from .models import CompanionRecord


class ProcessStatus(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    HIDDEN = "hidden"
    EXITED = "exited"
    UNMANAGED = "unmanaged"


class ManagedProcess(Protocol):
    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


class ProcessManager:
    """Manage only the GUI processes this Hub instance successfully launches."""

    def __init__(
        self,
        executable: list[str],
        popen: Callable[[list[str]], ManagedProcess] = subprocess.Popen,
    ) -> None:
        self.executable = list(executable)
        self.popen = popen
        self._handles: dict[str, ManagedProcess] = {}
        self._hidden: set[str] = set()
        self._stopped: set[str] = set()

    def start(self, record: CompanionRecord) -> ManagedProcess:
        """Launch the record's GUI using its own runtime root and pack."""
        current = self._handles.get(record.companion_id)
        if current is not None and current.poll() is None:
            return current

        arguments = [
            *self.executable,
            "--root",
            str(record.runtime_root),
            "gui",
            "--pack",
            str(record.pack_root),
        ]
        handle = self.popen(arguments)
        self._handles[record.companion_id] = handle
        self._hidden.discard(record.companion_id)
        self._stopped.discard(record.companion_id)
        return handle

    def show(self, record: CompanionRecord) -> ProcessStatus:
        self._publish(record, "summon")
        self._hidden.discard(record.companion_id)
        return self.status(record)

    def hide(self, record: CompanionRecord) -> ProcessStatus:
        self._publish(record, "hide")
        self._hidden.add(record.companion_id)
        return self.status(record)

    def stop(self, record: CompanionRecord) -> bool:
        """Stop a process owned by this Hub session, if one is still tracked."""
        handle = self._handles.get(record.companion_id)
        if handle is None:
            return False

        if handle.poll() is None:
            try:
                handle.terminate()
                handle.wait(timeout=3)
            except subprocess.TimeoutExpired:
                handle.kill()

        del self._handles[record.companion_id]
        self._hidden.discard(record.companion_id)
        self._stopped.add(record.companion_id)
        return True

    def status(self, record: CompanionRecord) -> ProcessStatus:
        handle = self._handles.get(record.companion_id)
        if handle is None:
            if record.companion_id in self._stopped:
                return ProcessStatus.STOPPED
            return ProcessStatus.UNMANAGED
        if handle.poll() is not None:
            return ProcessStatus.EXITED
        if record.companion_id in self._hidden:
            return ProcessStatus.HIDDEN
        return ProcessStatus.RUNNING

    @staticmethod
    def _inbox(record: CompanionRecord) -> Path:
        return record.runtime_root / "inbox.jsonl"

    def _publish(self, record: CompanionRecord, event_type: str) -> None:
        append_jsonl(
            self._inbox(record),
            new_event(event_type, agent="hub", companion_id=record.companion_id),
        )
