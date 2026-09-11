"""Local composition root and console entry point for Companion Hub."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
import uuid

from ..paths import default_data_dir
from ..storage import atomic_write_json
from .discovery import discover_packs
from .processes import ProcessManager
from .registry import CompanionRegistry


def default_hub_root() -> Path:
    """Return the private local data root used by the Hub."""
    return default_data_dir() / "hub"


def bundled_packs_dir() -> Path:
    """Locate packs bundled beside source or extracted by PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "packs"
    return Path(__file__).resolve().parents[3] / "packs"


def default_packs_dir(hub_root: Path) -> Path:
    """Prefer user-local packs, falling back to packs shipped with the app."""
    local_packs = hub_root / "packs"
    return local_packs if local_packs.is_dir() else bundled_packs_dir()


def _directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _snapshot_matches(snapshot: Path, expected_digest: str) -> bool:
    """Return whether a published snapshot still exactly matches its name."""
    try:
        mode = snapshot.stat().st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(mode):
        return False
    try:
        return _directory_digest(snapshot) == expected_digest
    except FileNotFoundError:
        return False


def _path_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _remove_owned_path(path: Path) -> None:
    """Remove only a uniquely named staging or backup path we created."""
    if not _path_exists(path):
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


_LOCK_LEASE_SECONDS = 30
_LOCK_OWNER_FILE = "owner.json"


def _pid_is_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_lock_owner(lock: Path) -> dict[str, object] | None:
    try:
        payload = json.loads((lock / _LOCK_OWNER_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _lock_is_reclaimable(lock: Path) -> bool:
    """Return whether an expired lock has no live local owner."""
    owner = _read_lock_owner(lock)
    now = time.time()
    if owner is not None:
        expiry = owner.get("lease_expires_at")
        if isinstance(expiry, (int, float)) and now < expiry:
            return False
        return not _pid_is_alive(owner.get("pid"))
    try:
        return now - lock.stat().st_mtime >= _LOCK_LEASE_SECONDS
    except FileNotFoundError:
        return False


def _write_lock_owner(lock: Path, owner_id: str) -> None:
    atomic_write_json(
        lock / _LOCK_OWNER_FILE,
        {
            "owner_id": owner_id,
            "pid": os.getpid(),
            "lease_expires_at": time.time() + _LOCK_LEASE_SECONDS,
        },
    )


def _reclaim_snapshot_lock(lock: Path) -> bool:
    """Atomically retire a stale lock without touching a live owner's lock."""
    if not _lock_is_reclaimable(lock) or not _lock_is_reclaimable(lock):
        return False
    reclaimed = lock.parent / f".reclaimed-{lock.name}-{uuid.uuid4().hex}"
    try:
        lock.replace(reclaimed)
    except OSError:
        if not _path_exists(lock):
            return True
        if _lock_is_reclaimable(lock):
            raise
        return False
    _remove_owned_path(reclaimed)
    return True


def _release_snapshot_lock(lock: Path, owner_id: str) -> None:
    owner = _read_lock_owner(lock)
    if owner is None or owner.get("owner_id") != owner_id:
        return
    try:
        (lock / _LOCK_OWNER_FILE).unlink()
        lock.rmdir()
    except FileNotFoundError:
        return


def _acquire_snapshot_lock(snapshot_root: Path, expected_digest: str) -> tuple[Path, str] | None:
    """Serialize cooperating Hub starts while a snapshot is repaired."""
    locks_root = snapshot_root / ".locks"
    locks_root.mkdir(exist_ok=True)
    lock = locks_root / expected_digest
    deadline = time.monotonic() + 5
    while True:
        try:
            lock.mkdir()
            owner_id = uuid.uuid4().hex
            _write_lock_owner(lock, owner_id)
            return lock, owner_id
        except FileExistsError:
            if _snapshot_matches(snapshot_root / expected_digest, expected_digest):
                return None
            if _reclaim_snapshot_lock(lock):
                continue
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out waiting for another Companion Hub to publish bundled packs.")
            time.sleep(0.02)


def _stage_snapshot(source: Path, snapshot_root: Path, expected_digest: str) -> tuple[Path, Path]:
    temporary_root = Path(tempfile.mkdtemp(prefix="bundled-packs-", dir=snapshot_root))
    staged_snapshot = temporary_root / "packs"
    try:
        shutil.copytree(source, staged_snapshot)
        if _directory_digest(staged_snapshot) != expected_digest:
            raise RuntimeError("Bundled packs changed while Companion Hub was copying them.")
    except Exception:
        _remove_owned_path(temporary_root)
        raise
    return temporary_root, staged_snapshot


def _move_corrupt_snapshot_aside(snapshot: Path, expected_digest: str) -> tuple[bool, Path | None]:
    """Move an invalid target aside; flag when a valid winner appeared."""
    if not _path_exists(snapshot):
        return False, None
    backup = snapshot.parent / f".backup-{expected_digest}-{uuid.uuid4().hex}"
    try:
        snapshot.replace(backup)
    except OSError:
        if _snapshot_matches(snapshot, expected_digest):
            return True, None
        if not _path_exists(snapshot):
            return False, None
        raise
    return False, backup


def materialize_bundled_packs(packs_dir: Path, hub_root: Path) -> Path:
    """Copy an ephemeral bundle to a stable, content-addressed Hub snapshot."""
    source = packs_dir.resolve()
    snapshot_root = hub_root / "bundled-packs"
    expected_digest = _directory_digest(source)
    snapshot = snapshot_root / expected_digest
    if _snapshot_matches(snapshot, expected_digest):
        return snapshot

    snapshot_root.mkdir(parents=True, exist_ok=True)
    acquired_lock = _acquire_snapshot_lock(snapshot_root, expected_digest)
    if acquired_lock is None:
        if _snapshot_matches(snapshot, expected_digest):
            return snapshot
        raise RuntimeError("Bundled pack publication completed without a valid snapshot.")
    lock, owner_id = acquired_lock
    try:
        if _snapshot_matches(snapshot, expected_digest):
            return snapshot
        for attempt in range(2):
            temporary_root, staged_snapshot = _stage_snapshot(source, snapshot_root, expected_digest)
            backup: Path | None = None
            try:
                winner_published, backup = _move_corrupt_snapshot_aside(snapshot, expected_digest)
                if winner_published:
                    return snapshot
                try:
                    staged_snapshot.replace(snapshot)
                except OSError:
                    if _snapshot_matches(snapshot, expected_digest):
                        return snapshot
                    if attempt == 0 and _path_exists(snapshot):
                        continue
                    raise
                if _snapshot_matches(snapshot, expected_digest):
                    return snapshot
                if attempt == 1:
                    raise RuntimeError("Companion Hub could not verify its bundled pack snapshot after publication.")
            finally:
                _remove_owned_path(temporary_root)
                if backup is not None:
                    _remove_owned_path(backup)
        raise RuntimeError("Companion Hub could not repair its bundled pack snapshot.")
    finally:
        _release_snapshot_lock(lock, owner_id)


def _is_ephemeral_bundle_path(packs_dir: Path) -> bool:
    return getattr(sys, "frozen", False) and packs_dir.resolve() == bundled_packs_dir().resolve()


def runtime_command() -> list[str]:
    """Return an argument-safe command for the existing Companion runtime."""
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve().with_name("companion.exe")
        if not executable.is_file():
            raise RuntimeError("Companion Hub needs companion.exe beside its executable.")
        return [str(executable)]
    return [sys.executable, "-m", "companion.cli"]


def open_hub(*, hub_root: Path, packs_dir: Path) -> None:
    """Construct one Hub window from local services, then enter Tk's loop."""
    hub_root.mkdir(parents=True, exist_ok=True)
    runtimes_dir = hub_root / "runtimes"
    runtimes_dir.mkdir(parents=True, exist_ok=True)
    if _is_ephemeral_bundle_path(packs_dir):
        packs_dir = materialize_bundled_packs(packs_dir, hub_root)
    registry = CompanionRegistry(hub_root / "companions.json", runtimes_dir)
    packs = discover_packs(packs_dir)
    processes = ProcessManager(runtime_command())

    import tkinter as tk

    from .window import HubWindow

    root = tk.Tk()
    HubWindow(root, packs, registry, processes)
    root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="companion-hub", description="Open your local Companion Hub.")
    parser.add_argument("--hub-root", type=Path, help="local directory for Hub companion data")
    parser.add_argument("--packs-dir", type=Path, help="local directory containing companion packs")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Open the Hub after parsing local-only launch options."""
    args = build_parser().parse_args(argv)
    hub_root = args.hub_root.expanduser().resolve() if args.hub_root else default_hub_root().resolve()
    packs_dir = args.packs_dir.expanduser().resolve() if args.packs_dir else default_packs_dir(hub_root).resolve()
    open_hub(hub_root=hub_root, packs_dir=packs_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
