"""Composition and entry-point contracts for the local Companion Hub."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import ctypes
import json
import runpy
import shutil
import subprocess
import sys

import pytest

from companion import cli
from companion.hub import main as hub_main
from companion.hub.registry import CompanionRegistry


def make_pack(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "idle.ppm").write_text("P3\n1 1\n255\n0 255 0\n", encoding="ascii")
    (root / "manifest.json").write_text(
        '{"id":"local-cat","name":"Local Cat","animations":{"idle":"idle.ppm"}}',
        encoding="utf-8",
    )
    return root


def test_hub_cli_passes_resolved_paths(monkeypatch, tmp_path):
    opened = {}
    hub_root = tmp_path / "Hub with spaces"
    packs_dir = tmp_path / "Pack files"
    monkeypatch.setattr(hub_main, "open_hub", lambda **kwargs: opened.update(kwargs))

    assert hub_main.main(["--hub-root", str(hub_root), "--packs-dir", str(packs_dir)]) == 0

    assert opened["hub_root"] == hub_root.resolve()
    assert opened["packs_dir"] == packs_dir.resolve()


def test_companion_hub_command_forwards_hub_options(monkeypatch, tmp_path):
    received = []
    monkeypatch.setattr(hub_main, "main", lambda argv: received.append(argv) or 0)

    assert cli.main(["hub", "--hub-root", str(tmp_path / "hub"), "--packs-dir", str(tmp_path / "packs")]) == 0

    assert received == [["--hub-root", str(tmp_path / "hub"), "--packs-dir", str(tmp_path / "packs")]]


def test_hub_help_does_not_open_a_window(monkeypatch, capsys):
    monkeypatch.setattr(hub_main, "open_hub", lambda **kwargs: pytest.fail("Hub window was opened for --help"))

    with pytest.raises(SystemExit) as result:
        hub_main.main(["--help"])

    assert result.value.code == 0
    assert "Companion Hub" in capsys.readouterr().out


def test_default_packs_use_hub_local_directory_before_the_bundle(monkeypatch, tmp_path):
    hub_root = tmp_path / "hub"
    bundled = tmp_path / "bundled packs"
    monkeypatch.setattr(hub_main, "bundled_packs_dir", lambda: bundled)

    assert hub_main.default_packs_dir(hub_root) == bundled

    local = hub_root / "packs"
    local.mkdir(parents=True)
    assert hub_main.default_packs_dir(hub_root) == local


def test_bundled_packs_dir_uses_pyinstaller_data_root(monkeypatch, tmp_path):
    bundle_root = tmp_path / "frozen app with spaces"
    monkeypatch.setattr(hub_main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(hub_main.sys, "_MEIPASS", str(bundle_root), raising=False)

    assert hub_main.bundled_packs_dir() == bundle_root / "packs"


def test_bundled_packs_dir_uses_checked_in_source_packs(monkeypatch):
    monkeypatch.delattr(hub_main.sys, "frozen", raising=False)

    assert hub_main.bundled_packs_dir() == Path(__file__).resolve().parents[1] / "packs"


def test_runtime_command_uses_sibling_executable_when_frozen(monkeypatch, tmp_path):
    executable = tmp_path / "Companion Hub.exe"
    (tmp_path / "companion.exe").touch()
    monkeypatch.setattr(hub_main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(hub_main.sys, "executable", str(executable))

    assert hub_main.runtime_command() == [str(tmp_path / "companion.exe")]


def test_runtime_command_rejects_an_incomplete_frozen_distribution(monkeypatch, tmp_path):
    monkeypatch.setattr(hub_main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(hub_main.sys, "executable", str(tmp_path / "Companion Hub.exe"))

    with pytest.raises(RuntimeError, match="companion.exe"):
        hub_main.runtime_command()


def test_runtime_command_uses_the_current_python_in_source(monkeypatch):
    monkeypatch.delattr(hub_main.sys, "frozen", raising=False)

    assert hub_main.runtime_command() == [hub_main.sys.executable, "-m", "companion.cli"]


def test_open_hub_creates_local_services_and_opens_one_window(monkeypatch, tmp_path):
    from companion.hub import window

    opened = {}

    class Root:
        def mainloop(self):
            opened["mainloop"] = True

    class Window:
        def __init__(self, root, packs, registry, processes):
            opened.update(root=root, packs=packs, registry=registry, processes=processes)

    hub_root = tmp_path / "Hub data"
    packs_dir = tmp_path / "Packs with spaces"
    make_pack(packs_dir / "local-cat")
    monkeypatch.setattr("tkinter.Tk", Root)
    monkeypatch.setattr(window, "HubWindow", Window)

    hub_main.open_hub(hub_root=hub_root, packs_dir=packs_dir)

    assert opened["mainloop"] is True
    assert opened["registry"].path == hub_root / "companions.json"
    assert opened["registry"].runtimes_dir == hub_root / "runtimes"
    assert [pack.pack_id for pack in opened["packs"]] == ["local-cat"]


def test_frozen_bundle_snapshot_survives_a_new_pyinstaller_extraction(monkeypatch, tmp_path):
    hub_root = tmp_path / "Hub data"
    first_bundle = tmp_path / "first extraction" / "packs"
    make_pack(first_bundle / "local-cat")
    monkeypatch.setattr(hub_main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(hub_main.sys, "_MEIPASS", str(first_bundle.parent), raising=False)

    first_snapshot = hub_main.materialize_bundled_packs(first_bundle, hub_root)
    registry = CompanionRegistry(hub_root / "companions.json", hub_root / "runtimes")
    record = registry.create("Mochi", first_snapshot / "local-cat")

    second_bundle = tmp_path / "second extraction" / "packs"
    make_pack(second_bundle / "local-cat")
    monkeypatch.setattr(hub_main.sys, "_MEIPASS", str(second_bundle.parent), raising=False)
    second_snapshot = hub_main.materialize_bundled_packs(second_bundle, hub_root)

    assert second_snapshot == first_snapshot
    assert record.pack_root == (first_snapshot / "local-cat").resolve()
    assert (record.pack_root / "manifest.json").is_file()
    assert str(first_bundle) not in str(record.pack_root)


def test_changed_frozen_bundle_uses_a_new_stable_snapshot(monkeypatch, tmp_path):
    hub_root = tmp_path / "Hub data"
    first_bundle = tmp_path / "first extraction" / "packs"
    make_pack(first_bundle / "local-cat")
    monkeypatch.setattr(hub_main.sys, "frozen", True, raising=False)

    first_snapshot = hub_main.materialize_bundled_packs(first_bundle, hub_root)
    second_bundle = tmp_path / "second extraction" / "packs"
    make_pack(second_bundle / "local-cat")
    (second_bundle / "local-cat" / "idle.ppm").write_text("P3\n1 1\n255\n255 0 0\n", encoding="ascii")
    second_snapshot = hub_main.materialize_bundled_packs(second_bundle, hub_root)

    assert second_snapshot != first_snapshot
    assert (first_snapshot / "local-cat" / "idle.ppm").read_text(encoding="ascii").endswith("0 255 0\n")
    assert (second_snapshot / "local-cat" / "idle.ppm").read_text(encoding="ascii").endswith("255 0 0\n")


def test_corrupt_or_incomplete_snapshot_is_repaired_from_the_bundle(monkeypatch, tmp_path):
    hub_root = tmp_path / "Hub data"
    bundle = tmp_path / "frozen extraction" / "packs"
    make_pack(bundle / "local-cat")
    monkeypatch.setattr(hub_main.sys, "frozen", True, raising=False)
    snapshot = hub_main.materialize_bundled_packs(bundle, hub_root)

    (snapshot / "local-cat" / "idle.ppm").unlink()
    repaired = hub_main.materialize_bundled_packs(bundle, hub_root)
    assert repaired == snapshot
    assert (repaired / "local-cat" / "idle.ppm").read_text(encoding="ascii").endswith("0 255 0\n")

    (snapshot / "local-cat" / "idle.ppm").write_text("partial", encoding="ascii")
    repaired_again = hub_main.materialize_bundled_packs(bundle, hub_root)
    assert repaired_again == snapshot
    assert hub_main._directory_digest(repaired_again) == snapshot.name


def test_concurrent_snapshot_publication_leaves_one_verified_snapshot(monkeypatch, tmp_path):
    hub_root = tmp_path / "Hub data"
    bundle = tmp_path / "frozen extraction" / "packs"
    make_pack(bundle / "local-cat")
    monkeypatch.setattr(hub_main.sys, "frozen", True, raising=False)

    with ThreadPoolExecutor(max_workers=2) as executor:
        snapshots = list(executor.map(lambda _: hub_main.materialize_bundled_packs(bundle, hub_root), range(2)))

    assert snapshots[0] == snapshots[1]
    assert hub_main._directory_digest(snapshots[0]) == snapshots[0].name
    assert not list((hub_root / "bundled-packs").glob("bundled-packs-*"))
    assert not list((hub_root / "bundled-packs").glob(".backup-*"))


def test_abandoned_snapshot_lock_is_reclaimed_before_repair(monkeypatch, tmp_path):
    hub_root = tmp_path / "Hub data"
    bundle = tmp_path / "frozen extraction" / "packs"
    make_pack(bundle / "local-cat")
    expected = hub_main._directory_digest(bundle)
    lock = hub_root / "bundled-packs" / ".locks" / expected
    lock.mkdir(parents=True)
    (lock / "owner.json").write_text(
        json.dumps({"owner_id": "crashed", "pid": 991, "lease_expires_at": 0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(hub_main.sys, "platform", "linux")
    monkeypatch.setattr(hub_main, "_pid_is_alive", lambda pid: False)

    snapshot = hub_main.materialize_bundled_packs(bundle, hub_root)

    assert hub_main._directory_digest(snapshot) == expected
    assert not lock.exists()


def test_expired_lock_with_a_live_owner_is_not_reclaimable(monkeypatch, tmp_path):
    lock = tmp_path / "lock"
    lock.mkdir()
    (lock / "owner.json").write_text(
        json.dumps({"owner_id": "live", "pid": 992, "lease_expires_at": 0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(hub_main.sys, "platform", "linux")
    monkeypatch.setattr(hub_main, "_pid_is_alive", lambda pid: True)

    assert hub_main._lock_is_reclaimable(lock) is False


def test_windows_liveness_probe_uses_open_process_without_a_signal(monkeypatch):
    calls = []

    class Kernel32:
        def OpenProcess(self, access, inherit_handle, pid):
            calls.append(("open", access, inherit_handle, pid))
            return 123

        def GetExitCodeProcess(self, handle, exit_code):
            calls.append(("exit", handle))
            ctypes.cast(exit_code, ctypes.POINTER(ctypes.c_ulong)).contents.value = 259
            return True

        def GetProcessTimes(self, handle, created, unused_exit, kernel, user):
            calls.append(("times", handle))
            file_time = ctypes.cast(created, ctypes.POINTER(hub_main._FileTime)).contents
            file_time.low = 1
            file_time.high = 2
            return True

        def CloseHandle(self, handle):
            calls.append(("close", handle))
            return True

    monkeypatch.setattr(hub_main.sys, "platform", "win32")
    monkeypatch.setattr(hub_main.ctypes, "WinDLL", lambda *_args, **_kwargs: Kernel32(), raising=False)
    monkeypatch.setattr(hub_main.os, "kill", lambda *_args: pytest.fail("Windows probe sent a signal"))

    assert hub_main._pid_is_alive(712) is True
    assert calls == [
        ("open", 0x00101000, False, 712),
        ("exit", 123),
        ("times", 123),
        ("close", 123),
    ]


def test_windows_process_state_recognizes_a_terminated_subprocess():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=10)

    assert hub_main._windows_process_state(process.pid) == ("dead", None)


def test_windows_owner_reclaim_requires_an_exact_creation_identity(monkeypatch):
    owner = {"pid": 712, "process_created_at": 100}
    monkeypatch.setattr(hub_main.sys, "platform", "win32")

    monkeypatch.setattr(hub_main, "_windows_process_state", lambda pid: ("running", 101))
    assert hub_main._owner_is_reclaimable(owner) is True

    monkeypatch.setattr(hub_main, "_windows_process_state", lambda pid: ("running", 100))
    assert hub_main._owner_is_reclaimable(owner) is False

    monkeypatch.setattr(hub_main, "_windows_process_state", lambda pid: ("unknown", None))
    assert hub_main._owner_is_reclaimable(owner) is False


def test_reclaim_operation_keeps_a_replacement_operation(monkeypatch, tmp_path):
    operation = tmp_path / ".operation.json"
    operation.write_text(
        json.dumps({"operation_id": "crashed", "pid": 991, "lease_expires_at": 0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(hub_main.sys, "platform", "linux")
    monkeypatch.setattr(hub_main, "_pid_is_alive", lambda pid: False)
    original_matches = hub_main._operation_matches

    def replace_operation_after_observation(path, operation_id):
        if operation_id == "crashed":
            path.write_text(
                json.dumps({"operation_id": "live", "pid": 992, "lease_expires_at": 9999999999}),
                encoding="utf-8",
            )
        return original_matches(path, operation_id)

    monkeypatch.setattr(hub_main, "_operation_matches", replace_operation_after_observation)

    assert hub_main._reclaim_operation(operation) is False
    assert json.loads(operation.read_text(encoding="utf-8"))["operation_id"] == "live"


def test_reclaim_does_not_remove_a_successor_after_ownership_changes(monkeypatch, tmp_path):
    lock = tmp_path / "lock"
    lock.mkdir()
    (lock / "owner.json").write_text(
        json.dumps({"owner_id": "crashed", "pid": 991, "lease_expires_at": 0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(hub_main.sys, "platform", "linux")
    monkeypatch.setattr(hub_main, "_pid_is_alive", lambda pid: False)

    original_matches = hub_main._owner_matches
    calls = 0

    def replace_owner_after_observation(path, owner_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            (path / "owner.json").write_text(
                json.dumps({"owner_id": "live", "pid": 992, "lease_expires_at": 9999999999}),
                encoding="utf-8",
            )
        return original_matches(path, owner_id)

    monkeypatch.setattr(hub_main, "_owner_matches", replace_owner_after_observation)

    assert hub_main._reclaim_snapshot_lock(lock) is False
    assert json.loads((lock / "owner.json").read_text(encoding="utf-8"))["owner_id"] == "live"


def test_unreadable_lock_metadata_is_not_reclaimable(monkeypatch, tmp_path):
    lock = tmp_path / "lock"
    lock.mkdir()
    owner = lock / "owner.json"
    owner.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def deny_owner_read(path, *args, **kwargs):
        if path == owner:
            raise PermissionError("sharing violation")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_owner_read)

    assert hub_main._lock_is_reclaimable(lock) is False


def test_live_or_unreadable_snapshot_lock_times_out_without_removal(monkeypatch, tmp_path):
    hub_root = tmp_path / "Hub data"
    bundle = tmp_path / "frozen extraction" / "packs"
    make_pack(bundle / "local-cat")
    expected = hub_main._directory_digest(bundle)
    lock = hub_root / "bundled-packs" / ".locks" / expected
    lock.mkdir(parents=True)
    owner = lock / "owner.json"
    owner.write_text(
        json.dumps({"owner_id": "live", "pid": 992, "lease_expires_at": 9999999999}),
        encoding="utf-8",
    )
    monkeypatch.setattr(hub_main, "_LOCK_WAIT_SECONDS", 0)
    original_read_text = Path.read_text

    def deny_owner_read(path, *args, **kwargs):
        if path == owner:
            raise PermissionError("sharing violation")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_owner_read)

    with pytest.raises(RuntimeError, match="Timed out"):
        hub_main.materialize_bundled_packs(bundle, hub_root)

    assert lock.is_dir()
    assert owner.is_file()


def test_publication_collision_accepts_only_a_verified_winner(monkeypatch, tmp_path):
    hub_root = tmp_path / "Hub data"
    bundle = tmp_path / "frozen extraction" / "packs"
    make_pack(bundle / "local-cat")
    expected = hub_main._directory_digest(bundle)
    snapshot = hub_root / "bundled-packs" / expected
    original_replace = Path.replace

    def publish_winner_then_raise(path, target):
        if path.name == "packs" and Path(target) == snapshot and path.parent.name.startswith("bundled-packs-"):
            shutil.copytree(bundle, snapshot)
            raise OSError("simulated publication collision")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", publish_winner_then_raise)

    assert hub_main.materialize_bundled_packs(bundle, hub_root) == snapshot
    assert hub_main._directory_digest(snapshot) == expected


def test_publication_collision_repairs_an_invalid_winner(monkeypatch, tmp_path):
    hub_root = tmp_path / "Hub data"
    bundle = tmp_path / "frozen extraction" / "packs"
    make_pack(bundle / "local-cat")
    expected = hub_main._directory_digest(bundle)
    snapshot = hub_root / "bundled-packs" / expected
    original_replace = Path.replace
    collided = False

    def publish_partial_then_raise(path, target):
        nonlocal collided
        if not collided and path.name == "packs" and Path(target) == snapshot and path.parent.name.startswith("bundled-packs-"):
            collided = True
            snapshot.mkdir(parents=True)
            (snapshot / "partial").write_text("not a pack", encoding="utf-8")
            raise OSError("simulated invalid publication collision")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", publish_partial_then_raise)

    assert hub_main.materialize_bundled_packs(bundle, hub_root) == snapshot
    assert hub_main._directory_digest(snapshot) == expected


def test_open_hub_rebinds_frozen_default_packs_to_a_stable_snapshot(monkeypatch, tmp_path):
    from companion.hub import window

    opened = {}

    class Root:
        def mainloop(self):
            pass

    class Window:
        def __init__(self, root, packs, registry, processes):
            opened.update(packs=packs, registry=registry, processes=processes)

    bundle_root = tmp_path / "frozen extraction"
    packs_dir = bundle_root / "packs"
    make_pack(packs_dir / "local-cat")
    (tmp_path / "companion.exe").touch()
    monkeypatch.setattr(hub_main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(hub_main.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(hub_main.sys, "executable", str(tmp_path / "Companion Hub.exe"))
    monkeypatch.setattr("tkinter.Tk", Root)
    monkeypatch.setattr(window, "HubWindow", Window)

    hub_root = tmp_path / "Hub data"
    hub_main.open_hub(hub_root=hub_root, packs_dir=packs_dir)

    assert opened["packs"][0].root.is_relative_to(hub_root / "bundled-packs")


@pytest.mark.parametrize(
    ("entry_name", "module", "attribute"),
    [
        ("companion_cli.py", cli, "main"),
        ("companion_hub.py", hub_main, "main"),
    ],
)
def test_pyinstaller_entry_wrappers_call_the_package_main(monkeypatch, entry_name, module, attribute):
    called = []
    monkeypatch.setattr(module, attribute, lambda: called.append(True) or 0)
    entry = Path(__file__).resolve().parents[1] / "src" / entry_name

    with pytest.raises(SystemExit) as result:
        runpy.run_path(entry, run_name="__main__")

    assert result.value.code == 0
    assert called == [True]
