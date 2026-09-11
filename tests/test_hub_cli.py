"""Composition and entry-point contracts for the local Companion Hub."""

from pathlib import Path

import pytest

from companion import cli
from companion.hub import main as hub_main


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
    monkeypatch.setattr(hub_main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(hub_main.sys, "executable", str(executable))

    assert hub_main.runtime_command() == [str(tmp_path / "companion.exe")]


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
