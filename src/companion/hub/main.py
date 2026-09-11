"""Local composition root and console entry point for Companion Hub."""

from __future__ import annotations

import argparse
import ctypes
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
_LOCK_WAIT_SECONDS = 5
_LOCK_OWNER_FILE = "owner.json"
_LOCK_OPERATION_FILE = ".operation.json"
_LOCK_OPERATION_MUTATION_FILE = ".operation-mutation.json"
_PROCESS_SYNCHRONIZE = 0x00100000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x00001000
_PROCESS_IDENTITY_ACCESS = _PROCESS_SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION
_STILL_ACTIVE = 259
_ERROR_INVALID_PARAMETER = 87


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]


def _windows_process_state(pid: int) -> tuple[str, int | None]:
    """Return dead, running+creation time, or unknown without signaling a process."""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        get_exit_code = kernel32.GetExitCodeProcess
        get_process_times = kernel32.GetProcessTimes
        close_handle = kernel32.CloseHandle
        try:
            open_process.argtypes = (ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong)
            open_process.restype = ctypes.c_void_p
            get_exit_code.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
            get_exit_code.restype = ctypes.c_bool
            get_process_times.argtypes = (
                ctypes.c_void_p,
                ctypes.POINTER(_FileTime),
                ctypes.POINTER(_FileTime),
                ctypes.POINTER(_FileTime),
                ctypes.POINTER(_FileTime),
            )
            get_process_times.restype = ctypes.c_bool
            close_handle.argtypes = (ctypes.c_void_p,)
            close_handle.restype = ctypes.c_bool
        except AttributeError:
            pass
        handle = open_process(_PROCESS_IDENTITY_ACCESS, False, pid)
    except OSError:
        return "unknown", None
    if not handle:
        if ctypes.get_last_error() == _ERROR_INVALID_PARAMETER:
            return "dead", None
        return "unknown", None
    try:
        exit_code = ctypes.c_ulong()
        if not get_exit_code(handle, ctypes.byref(exit_code)):
            return "unknown", None
        if exit_code.value != _STILL_ACTIVE:
            return "dead", None
        created = _FileTime()
        unused_exit = _FileTime()
        kernel = _FileTime()
        user = _FileTime()
        if not get_process_times(
            handle,
            ctypes.byref(created),
            ctypes.byref(unused_exit),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return "unknown", None
        return "running", (created.high << 32) | created.low
    finally:
        close_handle(handle)


def _windows_process_is_alive(pid: int) -> bool:
    return _windows_process_state(pid)[0] == "running"


def _pid_is_alive(pid: object) -> bool:
    """Return False only when this local process is known to have exited."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_process_is_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def _owner_is_reclaimable(owner: dict[str, object]) -> bool:
    """Return whether the exact recorded owner process is known to be gone."""
    pid = owner.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform != "win32":
        return not _pid_is_alive(pid)
    expected_created_at = owner.get("process_created_at")
    if not isinstance(expected_created_at, int):
        return False
    state, actual_created_at = _windows_process_state(pid)
    if state == "dead":
        return True
    if state != "running" or not isinstance(actual_created_at, int):
        return False
    return actual_created_at != expected_created_at


def _read_lock_owner(lock: Path) -> dict[str, object] | None:
    """Read absent or malformed metadata, while exposing filesystem failures."""
    try:
        payload = json.loads((lock / _LOCK_OWNER_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _anonymous_lock_generation(lock: Path) -> str | None:
    try:
        state = lock.stat()
    except OSError:
        return None
    # Directory mtime changes whenever a guard file is created. Use the
    # directory identity only so crash recovery remains valid while guards
    # are being claimed and released inside the lock.
    return f"anonymous:{state.st_dev}:{state.st_ino}"


def _lock_generation(lock: Path) -> str | None:
    try:
        owner = _read_lock_owner(lock)
    except OSError:
        return None
    owner_id = owner.get("owner_id") if owner is not None else None
    if isinstance(owner_id, str) and owner_id:
        return f"owner:{owner_id}"
    return _anonymous_lock_generation(lock)


def _owner_matches(lock: Path, generation: str) -> bool:
    return _lock_generation(lock) == generation


def _lock_is_old(lock: Path) -> bool:
    try:
        return time.time() - lock.stat().st_mtime >= _LOCK_LEASE_SECONDS
    except OSError:
        return False


def _reclaimable_lock_generation(lock: Path) -> tuple[bool, str | None]:
    """Return a stale generation token only when its owner is known dead."""
    try:
        owner = _read_lock_owner(lock)
    except OSError:
        return False, None
    generation = _lock_generation(lock)
    if generation is None:
        return False, None
    if owner is None or not isinstance(owner.get("owner_id"), str):
        return _lock_is_old(lock), generation
    expires_at = owner.get("lease_expires_at")
    if isinstance(expires_at, (int, float)) and time.time() < expires_at:
        return False, generation
    return _owner_is_reclaimable(owner), generation


def _lock_is_reclaimable(lock: Path) -> bool:
    return _reclaimable_lock_generation(lock)[0]


def _write_lock_owner(lock: Path, owner_id: str) -> None:
    process_created_at: int | None = None
    if sys.platform == "win32":
        state, process_created_at = _windows_process_state(os.getpid())
        if state != "running":
            raise RuntimeError("Companion Hub could not establish a safe Windows process identity for its snapshot lock.")
    atomic_write_json(
        lock / _LOCK_OWNER_FILE,
        {
            "owner_id": owner_id,
            "pid": os.getpid(),
            "process_created_at": process_created_at,
            "lease_expires_at": time.time() + _LOCK_LEASE_SECONDS,
        },
    )


def _process_identity() -> int | None:
    """Return this process' creation identity when Windows can prove it."""
    if sys.platform != "win32":
        return None
    state, created_at = _windows_process_state(os.getpid())
    return created_at if state == "running" else None


def _operation_owner_is_reclaimable(payload: dict[str, object]) -> bool:
    """Fail closed on Windows when operation metadata lacks process identity."""
    if sys.platform == "win32":
        return _owner_is_reclaimable(payload)
    return not _pid_is_alive(payload.get("pid"))


def _operation_is_reclaimable(operation: Path) -> bool:
    try:
        payload = json.loads(operation.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return _lock_is_old(operation)
    except OSError:
        return False
    if not isinstance(payload, dict):
        return _lock_is_old(operation)
    expires_at = payload.get("lease_expires_at")
    if isinstance(expires_at, (int, float)) and time.time() < expires_at:
        return False
    return _operation_owner_is_reclaimable(payload)


def _operation_generation(operation: Path) -> str | None:
    """Return an owner token, including for crash-partial metadata files."""
    try:
        payload = json.loads(operation.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _anonymous_lock_generation(operation)
    operation_id = payload.get("operation_id") if isinstance(payload, dict) else None
    return operation_id if isinstance(operation_id, str) and operation_id else _anonymous_lock_generation(operation)


def _reclaim_operation(operation: Path) -> bool:
    """Retire only an abandoned operation guard, never a live one."""
    if not _operation_is_reclaimable(operation):
        return False
    operation_id = _operation_generation(operation)
    if operation_id is None:
        return False
    mutation_id = _claim_operation_mutation(operation, operation_id)
    if mutation_id is None:
        return False
    try:
        if not _operation_matches(operation, operation_id) or not _operation_is_reclaimable(operation):
            return False
        retired = operation.parent / f".reclaimed-operation-{uuid.uuid4().hex}"
        try:
            operation.replace(retired)
        except OSError:
            return not _path_exists(operation)
        if not _operation_matches(retired, operation_id):
            if not _path_exists(operation):
                try:
                    retired.replace(operation)
                except OSError:
                    pass
            return False
        _remove_owned_path(retired)
        return True
    finally:
        _release_operation_mutation(operation, mutation_id)


def _claim_lock_operation(lock: Path, generation: str) -> str | None:
    """Create the single mutation guard for one observed lock generation."""
    operation = lock / _LOCK_OPERATION_FILE
    while True:
        operation_id = uuid.uuid4().hex
        process_identity = _process_identity()
        if sys.platform == "win32" and process_identity is None:
            return None
        payload = {
            "operation_id": operation_id,
            "generation": generation,
            "pid": os.getpid(),
            "process_created_at": process_identity,
            "lease_expires_at": time.time() + _LOCK_LEASE_SECONDS,
        }
        try:
            with operation.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream)
            return operation_id
        except FileExistsError:
            if not _reclaim_operation(operation):
                return None
        except FileNotFoundError:
            return None


def _release_lock_operation(lock: Path, operation_id: str) -> None:
    operation = lock / _LOCK_OPERATION_FILE
    mutation_id = _claim_operation_mutation(operation, operation_id)
    if mutation_id is None:
        return
    try:
        if not _operation_matches(operation, operation_id):
            return
        try:
            operation.unlink()
        except FileNotFoundError:
            return
    finally:
        _release_operation_mutation(operation, mutation_id)


def _operation_matches(operation: Path, operation_id: str) -> bool:
    try:
        payload = json.loads(operation.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        payload = None
    if isinstance(payload, dict) and payload.get("operation_id") == operation_id:
        return True
    return operation_id.startswith("anonymous:") and _anonymous_lock_generation(operation) == operation_id


def _mutation_is_reclaimable(mutation: Path) -> bool:
    try:
        payload = json.loads(mutation.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return _lock_is_old(mutation)
    except OSError:
        return False
    if not isinstance(payload, dict):
        return _lock_is_old(mutation)
    expires_at = payload.get("lease_expires_at")
    if isinstance(expires_at, (int, float)) and time.time() < expires_at:
        return False
    return _operation_owner_is_reclaimable(payload)


def _mutation_generation(mutation: Path) -> str | None:
    try:
        payload = json.loads(mutation.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _anonymous_lock_generation(mutation)
    mutation_id = payload.get("mutation_id") if isinstance(payload, dict) else None
    return mutation_id if isinstance(mutation_id, str) and mutation_id else _anonymous_lock_generation(mutation)


def _reclaim_operation_mutation(mutation: Path) -> bool:
    if not _mutation_is_reclaimable(mutation):
        return False
    mutation_id = _mutation_generation(mutation)
    if mutation_id is None:
        return False
    if not _mutation_matches(mutation, mutation_id):
        return False
    retired = mutation.parent / f".reclaimed-mutation-{uuid.uuid4().hex}"
    try:
        mutation.replace(retired)
    except OSError:
        return not _path_exists(mutation)
    if not _mutation_matches(retired, mutation_id):
        if not _path_exists(mutation):
            try:
                retired.replace(mutation)
            except OSError:
                pass
        return False
    _remove_owned_path(retired)
    return True


def _claim_operation_mutation(operation: Path, operation_id: str) -> str | None:
    mutation = operation.parent / _LOCK_OPERATION_MUTATION_FILE
    while True:
        mutation_id = uuid.uuid4().hex
        process_identity = _process_identity()
        if sys.platform == "win32" and process_identity is None:
            return None
        payload = {
            "mutation_id": mutation_id,
            "operation_id": operation_id,
            "pid": os.getpid(),
            "process_created_at": process_identity,
            "lease_expires_at": time.time() + _LOCK_LEASE_SECONDS,
        }
        try:
            with mutation.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream)
            return mutation_id
        except FileExistsError:
            if not _reclaim_operation_mutation(mutation):
                return None
        except FileNotFoundError:
            return None


def _release_operation_mutation(operation: Path, mutation_id: str) -> None:
    mutation = operation.parent / _LOCK_OPERATION_MUTATION_FILE
    if not _mutation_matches(mutation, mutation_id):
        return
    try:
        mutation.unlink()
    except FileNotFoundError:
        return


def _mutation_matches(mutation: Path, mutation_id: str) -> bool:
    try:
        payload = json.loads(mutation.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        payload = None
    if isinstance(payload, dict) and payload.get("mutation_id") == mutation_id:
        return True
    return mutation_id.startswith("anonymous:") and _anonymous_lock_generation(mutation) == mutation_id


def _retire_locked_generation(lock: Path, generation: str, operation_id: str) -> bool:
    """Rename the exact guarded generation, leaving successors untouched."""
    try:
        if not _operation_matches(lock / _LOCK_OPERATION_FILE, operation_id):
            return False
        if not _owner_matches(lock, generation):
            return False
        retired = lock.parent / f".retired-{lock.name}-{uuid.uuid4().hex}"
        lock.replace(retired)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    _remove_owned_path(retired)
    return True


def _reclaim_snapshot_lock(lock: Path) -> bool:
    """Take over only a stale observed generation under a mutation guard."""
    reclaimable, generation = _reclaimable_lock_generation(lock)
    if not reclaimable or generation is None:
        return False
    operation_id = _claim_lock_operation(lock, generation)
    if operation_id is None:
        return False
    try:
        reclaimable, current_generation = _reclaimable_lock_generation(lock)
        # Claiming the operation guard updates the directory mtime. For an
        # ownerless crash-partial lock, retain the initial age decision and
        # only require that the directory identity is unchanged.
        if generation.startswith("anonymous:") and current_generation == generation:
            reclaimable = True
        if not reclaimable or current_generation != generation:
            return False
        return _retire_locked_generation(lock, generation, operation_id)
    finally:
        _release_lock_operation(lock, operation_id)


def _release_snapshot_lock(lock: Path, generation: str) -> None:
    operation_id = _claim_lock_operation(lock, generation)
    if operation_id is None:
        return
    try:
        _retire_locked_generation(lock, generation, operation_id)
    finally:
        _release_lock_operation(lock, operation_id)


def _acquire_snapshot_lock(snapshot_root: Path, expected_digest: str) -> tuple[Path, str] | None:
    """Serialize cooperating Hub starts while a snapshot is repaired."""
    locks_root = snapshot_root / ".locks"
    locks_root.mkdir(exist_ok=True)
    lock = locks_root / expected_digest
    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    while True:
        try:
            lock.mkdir()
            owner_id = uuid.uuid4().hex
            try:
                _write_lock_owner(lock, owner_id)
            except Exception:
                _remove_owned_path(lock)
                raise
            return lock, f"owner:{owner_id}"
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
    lock, generation = acquired_lock
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
        _release_snapshot_lock(lock, generation)


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
