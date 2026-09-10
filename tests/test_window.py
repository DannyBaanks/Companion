import json
from pathlib import Path

import tkinter as tk

from companion.pack import AssetPack
from companion.protocol import POSITIONS, STATES
from companion.runtime import Runtime
from companion.window import AnimatedAsset, DesktopWindow


class FakeRoot:
    def __init__(self):
        self.bindings = {}
        self.attribute_calls = []
        self.geometry_calls = []
        self.destroyed = False

    def title(self, _value):
        pass

    def overrideredirect(self, _value):
        pass

    def attributes(self, *values):
        self.attribute_calls.append(values)

    wm_attributes = attributes

    def configure(self, **_values):
        pass

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def winfo_x(self):
        return 10

    def winfo_y(self):
        return 20

    def winfo_reqwidth(self):
        return 100

    def winfo_reqheight(self):
        return 120

    def winfo_screenwidth(self):
        return 1000

    def winfo_screenheight(self):
        return 800

    def geometry(self, value):
        self.geometry_calls.append(value)

    def withdraw(self):
        pass

    def deiconify(self):
        pass

    def after(self, _delay, _callback):
        pass

    def destroy(self):
        self.destroyed = True

    def mainloop(self):
        pass


class FakeLabel:
    def __init__(self, _parent, **values):
        self.values = values
        self.bindings = {}
        self.mapped = False

    def pack(self):
        self.mapped = True

    def pack_forget(self):
        self.mapped = False

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def configure(self, **values):
        self.values.update(values)

    def winfo_ismapped(self):
        return self.mapped


class FakeBooleanVar:
    def __init__(self, *, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeMenu:
    def __init__(self, _parent, *, tearoff=False):
        self.tearoff = tearoff
        self.entries = []
        self.popup = None
        self.released = False

    def add_command(self, **values):
        self.entries.append(("command", values))

    def add_cascade(self, **values):
        self.entries.append(("cascade", values))

    def add_checkbutton(self, **values):
        self.entries.append(("checkbutton", values))

    def add_separator(self):
        self.entries.append(("separator", {}))

    def tk_popup(self, x, y):
        self.popup = (x, y)

    def grab_release(self):
        self.released = True


def make_window(monkeypatch, tmp_path: Path, **options):
    monkeypatch.setattr("companion.window.tk.Tk", FakeRoot)
    monkeypatch.setattr("companion.window.tk.Label", FakeLabel)
    monkeypatch.setattr("companion.window.tk.BooleanVar", FakeBooleanVar)
    monkeypatch.setattr("companion.window.tk.Menu", FakeMenu)
    runtime = Runtime(tmp_path / "runtime")
    return DesktopWindow(runtime, **options)


def test_window_module_exports_gui_types():
    assert AnimatedAsset is not None
    assert DesktopWindow is not None


def test_animated_asset_loads_gif_frames_and_durations(monkeypatch, tmp_path):
    gif = tmp_path / "animated.gif"
    # Two Graphic Control Extensions with 10cs and 25cs delays.
    gif.write_bytes(b"GIF89a\x21\xf9\x04\x00\x0a\x00\x00\x00\x21\xf9\x04\x00\x19\x00\x00\x00")

    class FakePhotoImage:
        count = 0

        def __init__(self, *, file, format=None):
            if format is not None and FakePhotoImage.count >= 2:
                raise tk.TclError("no more frames")
            FakePhotoImage.count += 1

    monkeypatch.setattr("companion.window.tk.PhotoImage", FakePhotoImage)
    asset = AnimatedAsset(gif, clock=lambda: 0.0)

    assert len(asset.frames) == 2
    assert asset.durations == [0.1, 0.25]


def test_animated_asset_advances_when_frame_duration_elapses(monkeypatch, tmp_path):
    gif = tmp_path / "animated.gif"
    gif.write_bytes(b"GIF89a\x21\xf9\x04\x00\x0a\x00\x00\x00\x21\xf9\x04\x00\x19\x00\x00\x00")

    class FakePhotoImage:
        count = 0

        def __init__(self, *, file, format=None):
            if format is not None and FakePhotoImage.count >= 2:
                raise tk.TclError("no more frames")
            FakePhotoImage.count += 1

    monkeypatch.setattr("companion.window.tk.PhotoImage", FakePhotoImage)
    asset = AnimatedAsset(gif, clock=lambda: 0.0)

    asset.advance(now=0.09)
    assert asset.index == 0
    asset.advance(now=0.1)
    assert asset.index == 1
    asset.advance(now=0.35)
    assert asset.index == 0


def test_animated_asset_reset_restarts_timing(monkeypatch, tmp_path):
    gif = tmp_path / "animated.gif"
    gif.write_bytes(b"GIF89a\x21\xf9\x04\x00\x0a\x00\x00\x00\x21\xf9\x04\x00\x19\x00\x00\x00")

    class FakePhotoImage:
        count = 0

        def __init__(self, *, file, format=None):
            if format is not None and FakePhotoImage.count >= 2:
                raise tk.TclError("no more frames")
            FakePhotoImage.count += 1

    monkeypatch.setattr("companion.window.tk.PhotoImage", FakePhotoImage)
    now = [0.0]
    asset = AnimatedAsset(gif, clock=lambda: now[0])
    asset.advance(now=0.1)
    assert asset.index == 1
    now[0] = 1.0
    asset.reset()
    assert asset.index == 0
    asset.advance(now=1.05)
    assert asset.index == 0


def test_static_image_asset_has_one_frame(monkeypatch, tmp_path):
    image = tmp_path / "static.png"
    image.write_bytes(b"not a real png")

    class FakePhotoImage:
        def __init__(self, *, file, format=None):
            assert format is None

    monkeypatch.setattr("companion.window.tk.PhotoImage", FakePhotoImage)
    asset = AnimatedAsset(image, clock=lambda: 0.0)

    assert len(asset.frames) == 1
    asset.advance(now=100.0)
    assert asset.index == 0


def test_context_controls_preserve_drag_escape_and_right_click_bindings(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)

    assert {"<ButtonPress-1>", "<B1-Motion>", "<Escape>", "<Button-3>"} <= window.root.bindings.keys()
    window.root.bindings["<Escape>"](object())
    assert window.root.destroyed is True

    event = type("Event", (), {"x_root": 45, "y_root": 67})()
    window.image_label.bindings["<Button-3>"](event)
    assert window.context_menu.popup == (45, 67)
    assert window.context_menu.released is True


def test_context_menu_exposes_all_runtime_states_and_positions(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)

    cascades = {
        entry[1]["label"]: entry[1]["menu"]
        for entry in window.context_menu.entries
        if entry[0] == "cascade"
    }
    assert {entry[1]["label"] for entry in cascades["State"].entries} == STATES
    assert {entry[1]["label"] for entry in cascades["Position"].entries} == POSITIONS


def test_state_and_position_controls_use_runtime_event_path(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)

    window.set_state("working")
    window.set_position("top-left")

    assert window.runtime.state["state"] == "working"
    assert window.runtime.state["mood"] == "working"
    assert window.runtime.state["position"] == "top-left"
    event_types = [json.loads(line)["event_type"] for line in window.runtime.outbox.read_text().splitlines()]
    assert event_types == ["state", "mood", "move"]


def test_opacity_control_clamps_values(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)

    window.set_opacity(0.1)
    assert window.opacity == 0.35
    assert window.root.attribute_calls[-1] == ("-alpha", 0.35)

    window.set_opacity(2.0)
    assert window.opacity == 1.0
    assert window.root.attribute_calls[-1] == ("-alpha", 1.0)


def test_message_toggle_keeps_bubble_hidden_during_refresh(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)
    window.runtime.state.update(
        {
            "visible": True,
            "message": {"text": "hello", "ttl": None, "priority": 0, "sequence": 1, "expires_at": None},
        }
    )
    window._refresh()
    assert window.bubble.winfo_ismapped() is True

    assert window.toggle_messages() is False
    window._refresh()
    assert window.bubble.winfo_ismapped() is False


def test_reload_pack_reloads_manifest_without_writing_pack(monkeypatch, tmp_path):
    pack_root = tmp_path / "cat"
    pack_root.mkdir()
    idle = pack_root / "idle.png"
    idle.write_bytes(b"image")
    manifest = pack_root / "manifest.json"
    manifest.write_text(
        '{"id":"cat","name":"Cat","animations":{"idle":"idle.png"}}',
        encoding="utf-8",
    )
    pack = AssetPack.load(pack_root)

    class FakeAsset:
        def __init__(self, path):
            self.path = path
            self.current = object()

        def advance(self):
            pass

    monkeypatch.setattr("companion.window.AnimatedAsset", FakeAsset)
    window = make_window(monkeypatch, tmp_path, pack=pack, pack_name="Configured Cat")
    before = manifest.read_text(encoding="utf-8")

    assert window.reload_pack() is True
    assert window.pack is not pack
    assert window.pack_name == "Configured Cat"
    assert manifest.read_text(encoding="utf-8") == before
