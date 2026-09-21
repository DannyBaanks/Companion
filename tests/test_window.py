import json
from pathlib import Path

import tkinter as tk

from companion.pack import AssetPack
from companion.protocol import POSITIONS, STATES
from companion.runtime import Runtime
from companion.window import AnimatedAsset, DesktopWindow, _tk_color


def test_tk_color_strips_css_alpha_for_canvas():
    assert _tk_color("#6ee7b788") == "#6ee7b7"
    assert _tk_color("#6ee7b7") == "#6ee7b7"


class FakeRoot:
    def __init__(self):
        self.bindings = {}
        self.attribute_calls = []
        self.geometry_calls = []
        self.destroyed = False
        self._bg = "magenta"

    def title(self, _value):
        pass

    def overrideredirect(self, _value):
        pass

    def attributes(self, *values):
        self.attribute_calls.append(values)

    wm_attributes = attributes

    def configure(self, **_values):
        self._bg = _values.get("bg", self._bg)

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
    def __init__(self, parent, **values):
        self.parent = parent
        self.values = values
        self.bindings = {}
        self.mapped = False

    def pack(self):
        self.mapped = True

    def pack_forget(self):
        self.mapped = False

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def dispatch(self, sequence, event):
        result = self.bindings[sequence](event) if sequence in self.bindings else None
        if result != "break" and sequence in self.parent.bindings:
            self.parent.bindings[sequence](event)

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
    def __init__(self, _parent, *, tearoff=False, **_kw):
        self.tearoff = tearoff
        self.entries = []
        self.popup = None
        self.popup_calls = []
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
        self.popup_calls.append((x, y))

    def grab_release(self):
        self.released = True


class FakeCanvas:
    def __init__(self, parent, **kw):
        self.parent = parent
        self.kw = kw
        self._items = []
        self._tag_counter = 0

    def pack(self, **_kw):
        pass

    def configure(self, **kw):
        self.kw.update(kw)

    def create_oval(self, x1, y1, x2, y2, *, fill="", outline="", width=1, tags=""):
        self._tag_counter += 1
        item_id = self._tag_counter
        self._items.append({"id": item_id, "type": "oval", "coords": (x1, y1, x2, y2),
                            "fill": fill, "outline": outline, "width": width, "tags": tags})
        return item_id

    def delete(self, tag):
        self._items = [i for i in self._items if i["tags"] != tag]


def make_window(monkeypatch, tmp_path: Path, **options):
    monkeypatch.setattr("companion.window.tk.Tk", FakeRoot)
    monkeypatch.setattr("companion.window.tk.Label", FakeLabel)
    monkeypatch.setattr("companion.window.tk.BooleanVar", FakeBooleanVar)
    monkeypatch.setattr("companion.window.tk.Menu", FakeMenu)
    monkeypatch.setattr("companion.window.tk.Canvas", FakeCanvas)
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


def test_context_controls_preserve_drag_escape_and_single_right_click_behavior(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)

    assert {"<ButtonPress-1>", "<B1-Motion>", "<Escape>", "<Button-3>"} <= window.root.bindings.keys()
    drag_start = type("Event", (), {"x_root": 25, "y_root": 50})()
    drag_move = type("Event", (), {"x_root": 100, "y_root": 120})()
    window.root.bindings["<ButtonPress-1>"](drag_start)
    window.root.bindings["<B1-Motion>"](drag_move)
    assert window.root.geometry_calls[-1] == "+85+90"

    window.root.bindings["<Escape>"](object())
    assert window.root.destroyed is True

    event = type("Event", (), {"x_root": 45, "y_root": 67})()
    window.image_label.dispatch("<Button-3>", event)
    assert window.context_menu.popup_calls == [(45, 67)]
    assert window.context_menu.released is True


def test_constructor_applies_opacity_when_windows_transparent_color_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr("companion.window.platform_name", lambda: "windows")

    window = make_window(monkeypatch, tmp_path, opacity=0.6)

    assert ("-transparentcolor", "magenta") in window.root.attribute_calls
    assert ("-alpha", 0.6) in window.root.attribute_calls


def test_context_menu_exposes_all_runtime_states_and_positions(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)

    cascades = {
        entry[1]["label"]: entry[1]["menu"]
        for entry in window.context_menu.entries
        if entry[0] == "cascade"
    }
    # M12: sectioned labels — "Companion  ▶  State" and "Window  ▶  Position"
    state_labels = {entry[1]["label"] for entry in cascades.get("Companion  \u25b6  State", FakeMenu(None)).entries}
    position_labels = {entry[1]["label"] for entry in cascades.get("Window  \u25b6  Position", FakeMenu(None)).entries}
    # State labels now include icon prefix, so extract the state name after the icon
    state_values = {label.split("  ")[-1].strip() for label in state_labels}
    assert state_values == STATES
    assert position_labels == POSITIONS


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


# ── M11: Glow and theme tests ────────────────────────────────────────────────

def test_glow_canvas_is_created(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)
    assert hasattr(window, "glow_canvas")
    assert window.glow_canvas.kw["bg"] == window.theme.bg_stage


def test_draw_glow_creates_ovals(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)
    window._draw_glow("idle")
    ovals = [i for i in window.glow_canvas._items if i["type"] == "oval"]
    assert len(ovals) == 2  # outer ring + inner fill
    assert window._last_glow_state == "idle"


def test_draw_glow_skips_if_same_state(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)
    window._draw_glow("idle")
    count_before = len(window.glow_canvas._items)
    window._draw_glow("idle")  # same state → no new items
    assert len(window.glow_canvas._items) == count_before


def test_draw_glow_clears_previous_on_state_change(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)
    window._draw_glow("idle")
    assert any(i["tags"] == "glow" for i in window.glow_canvas._items)
    window._draw_glow("error")
    old_items = [i for i in window.glow_canvas._items if i["tags"] == "glow"]
    assert len(old_items) == 2  # new glow for error


def test_set_theme_switches_and_rebuilds_menu(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)
    old_menu = window.context_menu
    window.set_theme("soft-neon")
    assert window.theme.name == "soft-neon"
    assert window.context_menu is not old_menu  # rebuilt
    assert window._last_glow_state is None  # forces redraw


def test_sectioned_menu_has_expected_labels(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)
    labels = [
        entry[1].get("label", "")
        for entry in window.context_menu.entries
        if entry[0] == "cascade"
    ]
    # Companion section
    assert any("Companion" in l and "State" in l for l in labels)
    assert any("Companion" in l and "Theme" in l for l in labels)
    # Window section
    assert any("Window" in l and "Position" in l for l in labels)
    assert any("Window" in l and "Opacity" in l for l in labels)


def test_close_command_exists_in_menu(monkeypatch, tmp_path):
    window = make_window(monkeypatch, tmp_path)
    command_labels = [
        entry[1].get("label", "")
        for entry in window.context_menu.entries
        if entry[0] == "command"
    ]
    assert "Close" in command_labels


def test_theme_checkbutton_reflects_current(monkeypatch, tmp_path):
    """Theme submenu shows checkmark next to current theme."""
    from companion.tokens import DARK
    window = make_window(monkeypatch, tmp_path)
    # Find the Theme cascade
    for entry in window.context_menu.entries:
        if entry[0] == "cascade" and "Theme" in entry[1].get("label", ""):
            submenu = entry[1]["menu"]
            labels = [e[1].get("label", "") for e in submenu.entries]
            # dark should have ✓ prefix
            assert any("dark" in l and "\u2713" in l for l in labels)
            break
    else:
        raise AssertionError("Theme cascade not found")
