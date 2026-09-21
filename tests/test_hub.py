"""Tests for Companion Hub (M13) — store, state, and pack discovery."""

import json
from pathlib import Path

from companion.hub import CompanionEntry, HubController, HubState, HubStore
from companion.pack import AssetPack


def test_hub_state_roundtrip():
    state = HubState(
        companions=[
            CompanionEntry("c1", "Terra", pack_id="cat", status="running"),
            CompanionEntry("c2", "Beta", status="stopped"),
        ],
        first_run=False,
    )
    d = state.to_dict()
    restored = HubState.from_dict(d)
    assert len(restored.companions) == 2
    assert restored.companions[0].companion_id == "c1"
    assert restored.companions[0].status == "running"
    assert restored.first_run is False


def test_hub_store_save_and_load(tmp_path):
    store = HubStore(tmp_path)
    state = HubState(first_run=True)
    store.save(state)
    loaded = store.load()
    assert loaded.first_run is True
    assert loaded.companions == []


def test_hub_store_load_returns_empty_on_missing(tmp_path):
    store = HubStore(tmp_path)
    loaded = store.load()
    assert loaded.first_run is True
    assert loaded.companions == []


def test_hub_store_load_returns_empty_on_corrupt(tmp_path):
    (tmp_path / "hub.json").write_text("{bad", encoding="utf-8")
    store = HubStore(tmp_path)
    loaded = store.load()
    assert loaded.first_run is True


def test_hub_create_companion(tmp_path):
    store = HubStore(tmp_path)
    entry = store.create_companion("Terra", data_root=tmp_path)
    assert entry.companion_id == "c1"
    assert entry.name == "Terra"
    assert (tmp_path / "companion-c1").is_dir()

    state = store.load()
    assert len(state.companions) == 1
    assert state.first_run is False


def test_hub_create_multiple_companions(tmp_path):
    store = HubStore(tmp_path)
    c1 = store.create_companion("Alpha", data_root=tmp_path)
    c2 = store.create_companion("Beta", data_root=tmp_path)
    assert c1.companion_id != c2.companion_id
    assert len(store.load().companions) == 2


def test_hub_update_status(tmp_path):
    store = HubStore(tmp_path)
    entry = store.create_companion("Terra", data_root=tmp_path)
    store.update_status(entry.companion_id, "running", last_activity="started")
    loaded = store.get_companion(entry.companion_id)
    assert loaded is not None
    assert loaded.status == "running"
    assert loaded.last_activity == "started"


def test_hub_remove_companion(tmp_path):
    store = HubStore(tmp_path)
    entry = store.create_companion("Terra", data_root=tmp_path)
    assert store.remove_companion(entry.companion_id) is True
    assert store.get_companion(entry.companion_id) is None


def test_hub_remove_nonexistent_returns_false(tmp_path):
    store = HubStore(tmp_path)
    assert store.remove_companion("nope") is False


def test_hub_discover_packs(tmp_path):
    pack_dir = tmp_path / "packs" / "cat"
    pack_dir.mkdir(parents=True)
    (pack_dir / "idle.png").write_bytes(b"img")
    (pack_dir / "manifest.json").write_text(
        '{"id":"cat","name":"Cat","animations":{"idle":"idle.png"}}',
        encoding="utf-8",
    )
    store = HubStore(tmp_path)
    packs = store.discover_packs([tmp_path / "packs"])
    assert len(packs) == 1
    assert packs[0].pack_id == "cat"


def test_hub_discover_packs_skips_invalid(tmp_path):
    bad_dir = tmp_path / "packs" / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "manifest.json").write_text('{"id":""}', encoding="utf-8")
    store = HubStore(tmp_path)
    packs = store.discover_packs([tmp_path / "packs"])
    assert len(packs) == 0


def test_hub_discover_packs_ignores_nonexistent_dir(tmp_path):
    store = HubStore(tmp_path)
    packs = store.discover_packs([tmp_path / "nope"])
    assert packs == []


def test_hub_cli_hub_command_exists():
    from companion.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["hub"])
    assert args.command == "hub"


def test_hub_controller_lifecycle_publishes_events(tmp_path):
    class FakeProcess:
        def __init__(self, command, cwd):
            self.command = command
            self.cwd = cwd
            self.terminated = False

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

    store = HubStore(tmp_path)
    entry = store.create_companion("Terra", data_root=tmp_path)
    processes = []

    def spawn(command, cwd):
        process = FakeProcess(command, cwd)
        processes.append(process)
        return process

    controller = HubController(store, python_executable="python", process_factory=spawn)
    controller.start(entry)
    assert "gui" in processes[0].command
    assert store.get_companion("c1").status == "running"

    controller.hide(entry)
    controller.show(entry)
    events = [
        json.loads(line)
        for line in (tmp_path / "companion-c1" / "inbox.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [event["type"] for event in events] == ["hide", "summon"]

    controller.stop(entry)
    assert store.get_companion("c1").status == "stopped"
