"""Composition and entry-point contracts for the local Companion Hub."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import runpy
import shutil

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
