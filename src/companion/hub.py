"""Companion Hub — collection, creation, and lifecycle management.

The Hub is a separate top-level window that discovers installed packs,
lists running companions, and provides create/start/show/hide/stop controls.
It never mutates pack files or bypasses the event protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import subprocess
import sys
from typing import Any, Callable

from .pack import AssetPack, PackError
from .protocol import new_event
from .queue import append_jsonl
from .runtime import Runtime


@dataclass
class CompanionEntry:
    """One companion tracked by the Hub."""
    companion_id: str
    name: str
    pack_id: str | None = None
    pack_name: str | None = None
    status: str = "stopped"  # starting | running | hidden | stopping | stopped | failed
    last_activity: str | None = None
    root: Path | None = None


@dataclass
class HubState:
    """Persistent Hub state: known companions and first-run flag."""
    companions: list[CompanionEntry] = field(default_factory=list)
    first_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "companions": [
                {
                    "companion_id": c.companion_id,
                    "name": c.name,
                    "pack_id": c.pack_id,
                    "pack_name": c.pack_name,
                    "status": c.status,
                    "last_activity": c.last_activity,
                }
                for c in self.companions
            ],
            "first_run": self.first_run,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HubState":
        companions = []
        for item in data.get("companions", []):
            companions.append(CompanionEntry(
                companion_id=item["companion_id"],
                name=item.get("name", item["companion_id"]),
                pack_id=item.get("pack_id"),
                pack_name=item.get("pack_name"),
                status=item.get("status", "stopped"),
                last_activity=item.get("last_activity"),
            ))
        return cls(companions=companions, first_run=data.get("first_run", True))


class HubStore:
    """Persistent Hub state stored in the data root."""

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "hub.json"

    def load(self) -> HubState:
        if not self.path.exists():
            return HubState()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return HubState.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return HubState()

    def save(self, state: HubState) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def discover_packs(self, pack_dirs: list[Path] | None = None) -> list[AssetPack]:
        """Find and validate all packs in the given directories."""
        if pack_dirs is None:
            pack_dirs = [self.root / "packs"]
        packs: list[AssetPack] = []
        for base in pack_dirs:
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir()):
                if child.is_dir() and (child / "manifest.json").exists():
                    try:
                        packs.append(AssetPack.load(child))
                    except PackError:
                        continue
        return packs

    def create_companion(
        self,
        name: str,
        pack: AssetPack | None = None,
        data_root: Path | None = None,
    ) -> CompanionEntry:
        """Create a new companion entry and initialize its state."""
        state = self.load()
        # Generate a unique ID
        existing_ids = {c.companion_id for c in state.companions}
        idx = 1
        while f"c{idx}" in existing_ids:
            idx += 1
        cid = f"c{idx}"

        entry = CompanionEntry(
            companion_id=cid,
            name=name,
            pack_id=pack.pack_id if pack else None,
            pack_name=pack.name if pack else None,
            status="stopped",
        )
        state.companions.append(entry)
        state.first_run = False
        self.save(state)

        # Initialize the companion runtime directory
        if data_root:
            runtime_root = data_root / f"companion-{cid}"
            runtime_root.mkdir(parents=True, exist_ok=True)
            runtime = Runtime(runtime_root, companion_id=cid)
            runtime._save_state()

        return entry

    def update_status(self, companion_id: str, status: str, last_activity: str | None = None) -> None:
        state = self.load()
        for c in state.companions:
            if c.companion_id == companion_id:
                c.status = status
                if last_activity:
                    c.last_activity = last_activity
        self.save(state)

    def remove_companion(self, companion_id: str) -> bool:
        state = self.load()
        before = len(state.companions)
        state.companions = [c for c in state.companions if c.companion_id != companion_id]
        if len(state.companions) < before:
            self.save(state)
            return True
        return False

    def get_companion(self, companion_id: str) -> CompanionEntry | None:
        state = self.load()
        for c in state.companions:
            if c.companion_id == companion_id:
                return c
        return None


class HubController:
    """Own the lifecycle of companions launched by the Hub.

    The store is persistence; this controller is the process authority for
    the current Hub session.  UI state is only changed after a process/event
    operation has a meaningful result.
    """

    def __init__(
        self,
        store: HubStore,
        *,
        python_executable: str | None = None,
        process_factory: Callable[..., Any] | None = None,
    ):
        self.store = store
        self.python_executable = python_executable or sys.executable
        self.process_factory = process_factory or subprocess.Popen
        self._processes: dict[str, Any] = {}

    def runtime_root(self, entry: CompanionEntry) -> Path:
        root = self.store.root / f"companion-{entry.companion_id}"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def command(self, entry: CompanionEntry) -> list[str]:
        return [
            self.python_executable,
            "-m",
            "companion.cli",
            "--root",
            str(self.runtime_root(entry)),
            "--companion-id",
            entry.companion_id,
            "gui",
            "--name",
            entry.name,
        ]

    def start(self, entry: CompanionEntry) -> bool:
        existing = self._processes.get(entry.companion_id)
        if existing is not None and existing.poll() is None:
            self.store.update_status(entry.companion_id, "running", "process already running")
            return True

        runtime_root = self.runtime_root(entry)
        runtime = Runtime(runtime_root, companion_id=entry.companion_id)
        if not runtime.state_path.exists():
            runtime._save_state()
        self.store.update_status(entry.companion_id, "starting", "launching companion")
        try:
            process = self.process_factory(
                self.command(entry),
                cwd=str(self.store.root),
            )
        except OSError as exc:
            self.store.update_status(entry.companion_id, "failed", str(exc))
            return False
        self._processes[entry.companion_id] = process
        if process.poll() is not None:
            self.store.update_status(entry.companion_id, "failed", "process exited during startup")
            return False
        self.store.update_status(entry.companion_id, "running", "companion started")
        return True

    def _publish(self, entry: CompanionEntry, event_type: str) -> bool:
        process = self._processes.get(entry.companion_id)
        if process is None or process.poll() is not None:
            self.store.update_status(entry.companion_id, "failed", "companion process is not managed")
            return False
        append_jsonl(
            self.runtime_root(entry) / "inbox.jsonl",
            new_event(event_type, agent="hub", companion_id=entry.companion_id),
        )
        return True

    def hide(self, entry: CompanionEntry) -> bool:
        if not self._publish(entry, "hide"):
            return False
        self.store.update_status(entry.companion_id, "hidden", "companion hidden")
        return True

    def show(self, entry: CompanionEntry) -> bool:
        if not self._publish(entry, "summon"):
            return False
        self.store.update_status(entry.companion_id, "running", "companion shown")
        return True

    def stop(self, entry: CompanionEntry) -> bool:
        process = self._processes.get(entry.companion_id)
        if process is None or process.poll() is not None:
            self.store.update_status(entry.companion_id, "failed", "companion process is not managed")
            return False
        self.store.update_status(entry.companion_id, "stopping", "stopping companion")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        self._processes.pop(entry.companion_id, None)
        self.store.update_status(entry.companion_id, "stopped", "companion stopped")
        return True
