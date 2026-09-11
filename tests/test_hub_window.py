"""Controller contracts without a desktop or real companion processes."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from companion.hub import window
from companion.hub.models import PackRecord
from companion.hub.processes import ProcessManager, ProcessStatus
from companion.hub.registry import CompanionRegistry


class Widget:
    def __init__(self, master=None, **options):
        self.master = master
        self.options = options
        self.children = []
        self.bindings = {}
        self.entries = []
        if master is not None:
            master.children.append(self)

    def configure(self, **options):
        self.options.update(options)

    config = configure

    def __getitem__(self, key):
        return self.options[key]

    def grid(self, **options):
        self.grid_options = options

    def grid_remove(self):
        self.grid_options = {"removed": True}

    def title(self, text):
        self.options["title"] = text

    def grid_columnconfigure(self, *args, **kwargs):
        pass

    grid_rowconfigure = grid_columnconfigure

    def bind(self, event, callback, **kwargs):
        self.bindings[event] = callback

    def destroy(self):
        if self.master:
            self.master.children.remove(self)

    def add_command(self, **options):
        self.entries.append(options)

    def entryconfigure(self, index, **options):
        self.entries[index].update(options)

    def create_window(self, *args, **kwargs):
        return 1

    def itemconfigure(self, *args, **kwargs):
        pass

    def bbox(self, *args):
        return (0, 0, 200, 400)

    def yview(self, *args):
        pass

    def set(self, *args):
        pass

    def invoke(self):
        if self.options.get("state") != "disabled":
            self.options["command"]()


class Root(Widget):
    def __init__(self):
        super().__init__()
        self.pending = {}
        self.next_id = 0

    def title(self, text):
        pass

    def geometry(self, value):
        pass

    def minsize(self, *args):
        pass

    def after(self, milliseconds, callback):
        self.next_id += 1
        self.pending[self.next_id] = (milliseconds, callback)
        return self.next_id

    def after_cancel(self, callback_id):
        self.pending.pop(callback_id, None)

    def tick(self):
        callback_id = next(iter(self.pending))
        _, callback = self.pending.pop(callback_id)
        callback()


class StringVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class OptionMenu(Widget):
    def __init__(self, master, variable, *values):
        super().__init__(master, variable=variable, values=values)


class Entry(Widget):
    def focus_set(self):
        self.focused = True


class Photo:
    def __init__(self, **options):
        self.file = options["file"]

    def width(self):
        return 640

    def height(self):
        return 480

    def subsample(self, *args):
        return self


class Handle:
    returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode


class DeferredThread:
    jobs = []

    def __init__(self, *, target, daemon):
        self.target = target

    def start(self):
        self.jobs.append(self.target)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    for name in ("Frame", "Label", "Button", "Menubutton", "Menu", "Canvas", "Scrollbar", "Toplevel"):
        monkeypatch.setattr(window.tk, name, Widget)
    monkeypatch.setattr(window.tk, "PhotoImage", Photo)
    monkeypatch.setattr(window.tk, "StringVar", StringVar)
    monkeypatch.setattr(window.tk, "OptionMenu", OptionMenu)
    monkeypatch.setattr(window.tk, "Entry", Entry)
    monkeypatch.setattr(window, "Thread", DeferredThread)
    DeferredThread.jobs = []
    packs = [PackRecord(name, name.title(), tmp_path / name, tmp_path / name / "idle.png", None)
             for name in ("cat", "fox")]
    registry = CompanionRegistry(tmp_path / "companions.json", tmp_path / "runtimes")
    first = registry.create("Mochi", packs[0].root)
    second = registry.create("Fern", packs[1].root)
    manager = ProcessManager(["companion"], popen=lambda args: Handle())
    root = Root()
    hub = window.HubWindow(root, packs, registry, manager)
    return SimpleNamespace(hub=hub, root=root, first=first, second=second,
                           packs=packs, registry=registry, manager=manager)


def finish_action(setup):
    DeferredThread.jobs.pop(0)()
    setup.root.tick()


def test_selection_replaces_image_in_one_preview_widget(setup):
    hub = setup.hub
    preview = hub.preview_label
    hub.select(setup.first.companion_id)
    first_image = preview["image"]
    hub.select(setup.second.companion_id)
    assert hub.preview_label is preview
    assert hub.selected_id == setup.second.companion_id
    assert preview["image"].file == str(setup.packs[1].preview)
    assert preview["image"] is not first_image
    assert hub.name_label["text"] == "Fern"


@pytest.mark.parametrize("status, primary, hide, stop", [
    (ProcessStatus.UNMANAGED, "Start companion", "disabled", "disabled"),
    (ProcessStatus.STOPPED, "Start companion", "disabled", "disabled"),
    (ProcessStatus.RUNNING, "Show companion", "normal", "normal"),
    (ProcessStatus.HIDDEN, "Show companion", "disabled", "normal"),
    (ProcessStatus.EXITED, "Start companion", "disabled", "normal"),
])
def test_status_controls_available_actions(setup, status, primary, hide, stop):
    record, manager = setup.first, setup.manager
    if status != ProcessStatus.UNMANAGED:
        handle = manager.start(record)
        if status == ProcessStatus.STOPPED:
            manager.stop(record)
        elif status == ProcessStatus.HIDDEN:
            manager.hide(record)
        elif status == ProcessStatus.EXITED:
            handle.returncode = 1
    setup.hub.refresh_status()
    assert setup.hub.primary_action_text == primary
    assert setup.hub.primary_button["state"] == "normal"
    assert setup.hub.hide_button["state"] == hide
    assert setup.hub.overflow_menu.entries[0]["state"] == stop
    assert setup.hub.status_label["text"]


def test_actions_target_selection_and_expose_busy_state(setup):
    hub = setup.hub
    hub.select(setup.second.companion_id)
    hub.primary_button.invoke()
    assert hub.primary_action_text == "Starting…"
    assert hub.primary_button["state"] == "disabled"
    assert hub.hide_button["state"] == "disabled"
    hub.start_selected()
    assert len(DeferredThread.jobs) == 1
    finish_action(setup)
    assert setup.manager.status(setup.second) == ProcessStatus.RUNNING
    assert setup.manager.status(setup.first) == ProcessStatus.UNMANAGED
    hub.hide_button.invoke()
    finish_action(setup)
    assert setup.manager.status(setup.second) == ProcessStatus.HIDDEN
    hub.primary_button.invoke()
    finish_action(setup)
    assert setup.manager.status(setup.second) == ProcessStatus.RUNNING
    events = [
        json.loads(line)
        for line in (setup.second.runtime_root / "inbox.jsonl").read_text().splitlines()
    ]
    assert events[-1]["type"] == "summon"
    hub.overflow_menu.entries[0]["command"]()
    finish_action(setup)
    assert setup.manager.status(setup.second) == ProcessStatus.STOPPED
    assert "Stopped" in hub.last_activity_label["text"]


def test_refresh_chain_remains_single_and_cancels_on_destroy(setup):
    for _ in range(5):
        setup.hub.refresh_status()
        setup.hub.select(setup.second.companion_id)
        assert len(setup.root.pending) == 1
        assert next(iter(setup.root.pending.values()))[0] == 500
        setup.root.tick()
    # Destroying a child should not cancel the Hub's timer.
    callback = setup.root.bindings["<Destroy>"]
    callback(SimpleNamespace(widget=setup.hub.preview_label))
    assert len(setup.root.pending) == 1
    callback(SimpleNamespace(widget=setup.root))
    assert not setup.root.pending


def test_empty_and_unknown_selection_disable_actions(setup, tmp_path):
    registry = CompanionRegistry(tmp_path / "empty.json", tmp_path / "empty-runtimes")
    hub = window.HubWindow(Root(), setup.packs, registry, setup.manager)
    assert hub.selected_id is None
    assert hub.primary_button["state"] == "normal"
    assert hub.primary_action_text == "Create my companion"
    assert "local visual companion" in hub.status_label["text"].lower()
    hub.select("not-a-companion")
    hub.start_selected()
    hub.hide_selected()
    hub.show_selected()
    hub.stop_selected()
    assert not DeferredThread.jobs


def test_empty_registry_opens_welcome(setup, tmp_path):
    registry = CompanionRegistry(tmp_path / "empty.json", tmp_path / "empty-runtimes")

    hub = window.HubWindow(Root(), setup.packs, registry, setup.manager)

    assert hub.current_view == "welcome"
    assert hub.welcome_actions == ("Create my companion", "Open my collection")


def test_m11_does_not_expose_forge_as_an_executable_action(setup, tmp_path):
    registry = CompanionRegistry(tmp_path / "empty.json", tmp_path / "empty-runtimes")
    hub = window.HubWindow(Root(), setup.packs, registry, setup.manager)

    assert hub.forge_copy == "Companion Forge — guided coding-agent setup arrives in M12"
    assert "Install agent" not in hub.executable_actions


def test_create_from_valid_local_pack_persists_and_selects_one_companion(setup, tmp_path):
    registry = CompanionRegistry(tmp_path / "empty.json", tmp_path / "empty-runtimes")
    hub = window.HubWindow(Root(), setup.packs, registry, setup.manager)

    created = hub.create_from_pack("fox", "Fern")

    assert registry.list() == [created]
    assert created.pack_root == setup.packs[1].root.resolve()
    assert hub.current_view == "collection"
    assert hub.selected_id == created.companion_id
    assert hub.name_label["text"] == "Fern"


def test_create_from_invalid_pack_does_not_write_a_companion(setup, tmp_path):
    registry = CompanionRegistry(tmp_path / "empty.json", tmp_path / "empty-runtimes")
    hub = window.HubWindow(Root(), setup.packs, registry, setup.manager)

    with pytest.raises(ValueError, match="valid local companion pack"):
        hub.create_from_pack("missing", "Fern")

    assert registry.list() == []


def test_populated_collection_add_route_creates_selected_local_companion(setup):
    hub = setup.hub

    hub.add_companion_button.invoke()
    dialog = setup.root.children[-1]
    pack_picker = next(child for child in dialog.children if isinstance(child, OptionMenu))
    name_entry = next(child for child in dialog.children if isinstance(child, Entry))
    submit = next(child for child in dialog.children if child.options.get("text") == "Create my companion")
    assert pack_picker.options["values"] == ("Cat", "Fox")
    pack_picker.options["variable"].set("Fox")
    name_entry.options["textvariable"].set("Juniper")

    submit.invoke()

    created = setup.registry.get("juniper")
    assert created is not None
    assert created.pack_root == setup.packs[1].root.resolve()
    assert hub.selected_id == created.companion_id
    assert dialog not in setup.root.children


@pytest.mark.parametrize("error", [OSError("disk unavailable"), PermissionError("denied")])
def test_creation_dialog_keeps_user_recoverable_when_registry_write_fails(setup, monkeypatch, error):
    hub = setup.hub
    monkeypatch.setattr(setup.registry, "create", lambda name, root: (_ for _ in ()).throw(error))

    hub.add_companion_button.invoke()
    dialog = setup.root.children[-1]
    submit = next(child for child in dialog.children if child.options.get("text") == "Create my companion")

    submit.invoke()

    feedback = next(child for child in dialog.children if getattr(child, "hub_role", None) == "creation-feedback")
    assert "couldn’t save" in feedback.options["text"].lower()
    assert dialog in setup.root.children
    assert hub.selected_id == setup.first.companion_id


def test_creation_dialog_shows_name_validation_feedback_without_closing(setup):
    hub = setup.hub

    hub.add_companion_button.invoke()
    dialog = setup.root.children[-1]
    name_entry = next(child for child in dialog.children if isinstance(child, Entry))
    submit = next(child for child in dialog.children if child.options.get("text") == "Create my companion")
    name_entry.options["textvariable"].set(" ")

    submit.invoke()

    feedback = next(child for child in dialog.children if getattr(child, "hub_role", None) == "creation-feedback")
    assert "name" in feedback.options["text"].lower()
    assert dialog in setup.root.children


@pytest.mark.parametrize("packs, expected", [
    ([], "No local companion packs were found"),
    ([PackRecord("broken", "Broken", Path("broken"), None, "manifest invalid")], "No valid local companion packs were found"),
])
def test_empty_first_run_explains_missing_or_invalid_packs_and_disables_creation(tmp_path, monkeypatch, packs, expected):
    for name in ("Frame", "Label", "Button", "Menubutton", "Menu", "Canvas", "Scrollbar", "Toplevel"):
        monkeypatch.setattr(window.tk, name, Widget)
    monkeypatch.setattr(window.tk, "PhotoImage", Photo)
    monkeypatch.setattr(window.tk, "StringVar", StringVar)
    monkeypatch.setattr(window.tk, "OptionMenu", OptionMenu)
    monkeypatch.setattr(window.tk, "Entry", Entry)
    monkeypatch.setattr(window, "Thread", DeferredThread)
    registry = CompanionRegistry(tmp_path / "companions.json", tmp_path / "runtimes")
    hub = window.HubWindow(Root(), packs, registry, ProcessManager(["companion"], popen=lambda args: Handle()))

    assert hub.current_view == "welcome"
    assert hub.primary_button["state"] == "disabled"
    assert expected in hub.status_label["text"]


@pytest.mark.parametrize("catalog", ["invalid", "missing"])
def test_unusable_pack_disables_actions_and_keeps_diagnostics_secondary(setup, catalog):
    pack = setup.packs[0]
    packs = [PackRecord(pack.pack_id, pack.name, pack.root, None, "secret/manifest is broken")]
    if catalog == "missing":
        packs = []
    hub = window.HubWindow(Root(), packs, setup.registry, setup.manager)
    assert hub.primary_button["state"] == "disabled"
    assert hub.hide_button["state"] == "disabled"
    hub.start_selected()
    assert not DeferredThread.jobs
    assert "pack" in hub.status_label["text"].lower()
    assert "secret/manifest" not in hub.status_label["text"]
    assert hub.overflow_menu.entries[1]["state"] == "normal"
    assert hub.overflow_menu.entries[2]["state"] == "disabled"


def test_failed_start_keeps_selection_and_reports_friendly_error(setup):
    def fail(args):
        raise OSError("private/path: executable missing")
    setup.manager.popen = fail
    setup.hub.start_selected()
    finish_action(setup)
    assert setup.hub.selected_id == setup.first.companion_id
    assert setup.hub.primary_action_text == "Start companion"
    assert "couldn’t start" in setup.hub.status_label["text"].lower()
    assert "private/path" not in setup.hub.status_label["text"]
    setup.root.tick()
    assert "couldn’t start" in setup.hub.status_label["text"].lower()


def test_selection_during_action_keeps_active_companion_and_progress_visible(setup):
    setup.hub.start_selected()
    setup.hub.select(setup.second.companion_id)
    assert setup.hub.selected_id == setup.first.companion_id
    assert setup.hub.name_label["text"] == "Mochi"
    assert setup.hub.primary_action_text == "Starting…"
    finish_action(setup)
    assert setup.manager.status(setup.first) == ProcessStatus.RUNNING
    setup.hub.select(setup.second.companion_id)
    assert setup.hub.name_label["text"] == "Fern"
    assert setup.hub.primary_action_text == "Start companion"


def test_bad_preview_falls_back_without_disabling_valid_pack(setup, monkeypatch):
    def fail(**kwargs):
        raise window.tk.TclError("image format unsupported")
    monkeypatch.setattr(window.tk, "PhotoImage", fail)
    setup.hub.select(setup.second.companion_id)
    assert setup.hub.preview_label["image"] == ""
    assert setup.hub.preview_label["text"] == "Fern"
    assert setup.hub.primary_button["state"] == "normal"


def test_advanced_details_and_folder_action_use_selected_record(setup, monkeypatch):
    dialogs = []
    opened = []
    monkeypatch.setattr(window.messagebox, "showinfo", lambda title, message, **kwargs: dialogs.append(message))
    monkeypatch.setattr(window.os, "startfile", lambda path: opened.append(path))
    setup.hub.select(setup.second.companion_id)
    setup.hub.overflow_menu.entries[1]["command"]()
    assert str(setup.second.runtime_root) in dialogs[0]
    assert str(setup.second.pack_root) in dialogs[0]
    setup.hub.overflow_menu.entries[2]["command"]()
    assert opened == [str(setup.second.pack_root)]
