"""GTK renderer for transparent Codex sprite atlases on Linux desktops."""

from __future__ import annotations

import ctypes
import ctypes.util
import time
from typing import Any

from .pack import AssetPack
from .queue import append_jsonl
from .runtime import Runtime
from .protocol import new_event


# Codex v2 standard animation rows. The look-direction rows (9 and 10) are
# intentionally reserved for a future directional interaction.
_STATE_ROWS = {
    "idle": 0,
    "success": 3,   # wave
    "error": 5,     # failed
    "waiting": 6,
    "working": 7,   # running/work
    "thinking": 8,  # review
    "hidden": 0,
}
_IDLE_SEQUENCE = (0, 1, 2, 3, 5, 6, 7)  # skip the second closed-eye cell
_IDLE_FRAME_MS = {0: 1000, 1: 120, 2: 1000, 3: 1300, 5: 1000, 6: 1100, 7: 1500}
_FRAME_MS = {1: 95, 2: 95, 3: 110, 5: 130, 6: 160, 7: 120, 8: 150}


class _X11InputShape:
    """Set an X11 window's pointer hitbox without changing its visible alpha."""

    class Rectangle(ctypes.Structure):
        _fields_ = [
            ("x", ctypes.c_short),
            ("y", ctypes.c_short),
            ("width", ctypes.c_ushort),
            ("height", ctypes.c_ushort),
        ]

    def __init__(self):
        self.x11 = None
        self.xext = None
        self.display = None
        try:
            x11_path = ctypes.util.find_library("X11")
            xext_path = ctypes.util.find_library("Xext")
            if not x11_path or not xext_path:
                return
            self.x11 = ctypes.CDLL(x11_path)
            self.xext = ctypes.CDLL(xext_path)
            self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self.x11.XOpenDisplay.restype = ctypes.c_void_p
            self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            self.x11.XFlush.argtypes = [ctypes.c_void_p]
            self.display = self.x11.XOpenDisplay(None)
            if not self.display:
                return
            self.xext.XShapeCombineRectangles.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.POINTER(self.Rectangle), ctypes.c_int,
                ctypes.c_int, ctypes.c_int,
            ]
        except (OSError, AttributeError):
            self.close()

    @property
    def available(self) -> bool:
        return bool(self.display and self.xext)

    def set_rectangles(self, window_id: int, rectangles: tuple[tuple[int, int, int, int], ...]) -> None:
        if not self.available or not window_id or not rectangles:
            return
        native = (self.Rectangle * len(rectangles))(
            *(self.Rectangle(*rectangle) for rectangle in rectangles)
        )
        # ShapeInput = 2, ShapeSet = 0, Unsorted = 0.
        self.xext.XShapeCombineRectangles(
            self.display, window_id, 2, 0, 0, native, len(rectangles), 0, 0,
        )
        self.x11.XFlush(self.display)

    def close(self) -> None:
        if self.display and self.x11:
            self.x11.XCloseDisplay(self.display)
        self.display = None


class GtkSpriteWindow:
    """Render atlas frames with native alpha compositing instead of GIF color keys."""

    def __init__(
        self,
        runtime: Runtime,
        pack: AssetPack,
        *,
        name: str,
        topmost: bool,
        allow_dock_games: bool,
    ):
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

        self.Gdk, self.GdkPixbuf, self.GLib, self.Gtk = Gdk, GdkPixbuf, GLib, Gtk
        self.runtime = runtime
        self.pack = pack
        self.name = name
        self.allow_dock_games = allow_dock_games
        self.running = False
        self.dragging = False
        self.drag_frame_index = 0
        self.direction = 1
        self.x = 12.0
        self.drag_offset: tuple[float, float] | None = None
        self.dragged = False
        self.last_frame_at = time.monotonic()
        self.last_tick_at = self.last_frame_at
        self.last_state_at = 0.0
        self.last_position: str | None = None
        self.frame_index = 0
        self.current_row: int | None = None
        self.visible = bool(runtime.state.get("visible", True))

        atlas_path = pack.root / (pack.sprite_sheet or "")
        self.atlas = GdkPixbuf.Pixbuf.new_from_file(str(atlas_path))
        self.cell_width = pack.sprite_cell_width
        self.cell_height = pack.sprite_cell_height
        if self.atlas.get_width() < self.cell_width * pack.sprite_columns:
            raise ValueError("sprite sheet is narrower than its declared grid")
        if self.atlas.get_height() < self.cell_height * 11:
            raise ValueError("Codex v2 sprite sheet must contain all 11 rows")
        self.drag_atlas = None
        self.drag_cell_width = pack.drag_cell_width
        self.drag_cell_height = pack.drag_cell_height
        self.drag_columns = pack.drag_columns
        self.drag_floor_offset = pack.drag_floor_offset
        if pack.drag_sprite_sheet:
            self.drag_atlas = GdkPixbuf.Pixbuf.new_from_file(str(pack.root / pack.drag_sprite_sheet))
            if self.drag_atlas.get_width() < self.drag_cell_width * self.drag_columns:
                raise ValueError("drag animation sheet is narrower than its declared grid")
            if self.drag_atlas.get_height() < self.drag_cell_height:
                raise ValueError("drag animation sheet is shorter than its declared cell height")

        Gtk.init([])
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_title(name)
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_default_size(self.cell_width, self.cell_height)
        self.window.set_size_request(self.cell_width, self.cell_height)
        self.window.set_app_paintable(True)
        self.window.set_keep_above(topmost)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        screen = self.window.get_screen()
        rgba_visual = screen.get_rgba_visual()
        if rgba_visual is not None:
            self.window.set_visual(rgba_visual)

        # Gtk.Image renders GdkPixbuf alpha natively, without Tk's GIF palette
        # transparency or an application-level Cairo surface.
        self.area = Gtk.Image()
        self.area.set_size_request(self.cell_width, self.cell_height)
        self.window.add(self.area)
        self.window.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
        )
        self.window.connect("button-press-event", self._button_press)
        self.window.connect("button-release-event", self._button_release)
        self.window.connect("motion-notify-event", self._motion)
        self.window.connect("key-press-event", self._key_press)
        self.window.connect("delete-event", self._delete)
        self.input_shape = _X11InputShape()

        self.menu = Gtk.Menu()
        self.allow_item = Gtk.CheckMenuItem.new_with_label("Allow scripted Dock play (fixed strip)")
        self.allow_item.set_active(allow_dock_games)
        self.allow_item.connect("toggled", self._toggle_permission)
        self.menu.append(self.allow_item)
        self.run_item = Gtk.CheckMenuItem.new_with_label("Run along preset bottom strip")
        self.run_item.set_sensitive(allow_dock_games)
        self.run_item.connect("toggled", self._toggle_run)
        self.menu.append(self.run_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        close_item = Gtk.MenuItem.new_with_label("Close")
        close_item.connect("activate", lambda *_: self.close())
        self.menu.append(close_item)
        self.menu.show_all()

    def _frame(self, row: int, column: int):
        return self.atlas.new_subpixbuf(
            column * self.cell_width,
            row * self.cell_height,
            self.cell_width,
            self.cell_height,
        )

    def _drag_frame(self, column: int):
        return self.drag_atlas.new_subpixbuf(
            column * self.drag_cell_width,
            0,
            self.drag_cell_width,
            self.drag_cell_height,
        )

    def _set_dragging(self, active: bool) -> None:
        if active == self.dragging or self.drag_atlas is None:
            return
        self.dragging = active
        self.drag_frame_index = 0
        self.last_frame_at = time.monotonic()
        if active:
            self.area.set_size_request(self.drag_cell_width, self.drag_cell_height)
            self.window.resize(self.drag_cell_width, self.drag_cell_height)
            self.area.set_from_pixbuf(self._drag_frame(0))
            self._apply_drag_hitbox()
        else:
            x, y = self.window.get_position()
            # Keep the tail-tip floor point fixed as the carried pose shrinks
            # back to the seated sprite, so it is set down without a jump.
            floor_y = y + self.drag_floor_offset
            seated_y = max(0, floor_y - self.pack.sprite_floor_offset)
            self.area.set_size_request(self.cell_width, self.cell_height)
            self.window.resize(self.cell_width, self.cell_height)
            self.area.set_from_pixbuf(self._frame(self.current_row or 0, self.frame_index))
            self.window.move(x, seated_y)
            self._apply_default_hitbox()

    def _native_window_id(self) -> int | None:
        native_window = self.window.get_window()
        get_xid = getattr(native_window, "get_xid", None)
        return int(get_xid()) if get_xid else None

    def _apply_drag_hitbox(self) -> None:
        window_id = self._native_window_id()
        # The upper rectangle covers head and torso; the lower one covers paws.
        # The tail hangs below and left of the paws, so it no longer intercepts
        # Dock input while the cat is being dragged.
        self.input_shape.set_rectangles(window_id, ((20, 0, 152, 218), (64, 218, 108, 58)))

    def _apply_default_hitbox(self) -> None:
        window_id = self._native_window_id()
        self.input_shape.set_rectangles(
            window_id,
            ((0, 0, self.cell_width, self.cell_height),),
        )

    def _set_row(self, row: int) -> None:
        if row != self.current_row:
            self.current_row = row
            self.frame_index = 0
            self.last_frame_at = time.monotonic()
            self.area.set_from_pixbuf(self._frame(row, self.frame_index))

    def _publish(self, event_type: str, **fields: Any) -> None:
        append_jsonl(
            self.runtime.inbox,
            new_event(event_type, agent="companion-gui", companion_id=self.runtime.companion_id, **fields),
        )

    def _toggle_permission(self, item: Any) -> None:
        self.allow_dock_games = item.get_active()
        self.run_item.set_sensitive(self.allow_dock_games)
        if not self.allow_dock_games:
            self.running = False
            self.run_item.set_active(False)

    def _toggle_run(self, item: Any) -> None:
        if item.get_active() and not self.allow_dock_games:
            item.set_active(False)
            return
        self.running = item.get_active()
        if self.running:
            self.direction = 1
            self.x = 12.0
            self.drag_offset = None

    def _button_press(self, _window: Any, event: Any) -> bool:
        if event.button == 3:
            self.menu.popup_at_pointer(event)
            return True
        if event.button == 1:
            self.running = False
            self.run_item.set_active(False)
            self.dragged = True
            self.drag_offset = (event.x_root - self.window.get_position()[0], event.y_root - self.window.get_position()[1])
            self.dragged = True
            self._publish("move", value="free")
            return True
        return False

    def _button_release(self, _window: Any, event: Any) -> bool:
        if event.button == 1:
            self.drag_offset = None
            self._set_dragging(False)
            return True
        return False

    def _motion(self, _window: Any, event: Any) -> bool:
        if self.drag_offset is not None:
            if not self.dragging and self.drag_atlas is not None:
                self._set_dragging(True)
            screen = self.window.get_screen()
            screen_width, screen_height = screen.get_width(), screen.get_height()
            target_x = round(event.x_root - self.drag_offset[0])
            target_y = round(event.y_root - self.drag_offset[1])
            target_x = max(0, min(target_x, screen_width - self.drag_cell_width))
            # Fixed floor matches the regular sprite's bottom-strip baseline;
            # the tail tip marks it while the separate input hitbox excludes
            # the tail. Companion never queries Dock geometry.
            strip_y = screen_height - self.cell_height - 24
            floor_y = strip_y + self.pack.sprite_floor_offset
            max_y = max(0, floor_y - self.drag_floor_offset)
            target_y = max(0, min(target_y, max_y))
            self.window.move(target_x, target_y)
            return True
        return False

    def _key_press(self, _window: Any, event: Any) -> bool:
        if event.keyval == self.Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def _delete(self, *_args: Any) -> bool:
        self.input_shape.close()
        self.Gtk.main_quit()
        return False

    def close(self) -> None:
        if self.Gtk.main_level():
            self.input_shape.close()
            self.window.destroy()
            self.Gtk.main_quit()

    def _place(self, position: str) -> None:
        screen = self.window.get_screen()
        width, height = screen.get_width(), screen.get_height()
        margin = 24
        positions = {
            "top-left": (margin, margin),
            "top-right": (width - self.cell_width - margin, margin),
            "bottom-left": (margin, height - self.cell_height - margin),
            "bottom-right": (width - self.cell_width - margin, height - self.cell_height - margin),
            "dock": ((width - self.cell_width) // 2, height - self.cell_height - margin),
        }
        if position in positions:
            self.x = float(positions[position][0])
            self.window.move(*positions[position])

    def _tick(self) -> bool:
        now = time.monotonic()
        if now - self.last_state_at >= 0.1:
            self.runtime.process_once()
            self.last_state_at = now
        state = self.runtime.state
        if bool(state.get("visible")) != self.visible:
            self.visible = bool(state.get("visible"))
            self.window.show_all() if self.visible else self.window.hide()

        if self.running and not self.visible:
            self.running = False
            self.run_item.set_active(False)

        position = state.get("position", "bottom-right")
        if not self.dragged and not self.running and position != self.last_position:
            self._place(position)
            self.last_position = position

        if self.running:
            screen_width = self.window.get_screen().get_width()
            right = max(12, screen_width - self.cell_width - 12)
            speed = 250.0
            self.x += self.direction * speed * min(0.05, max(0.0, now - self.last_tick_at))
            if self.x >= right:
                self.x, self.direction = float(right), -1
            elif self.x <= 12:
                self.x, self.direction = 12.0, 1
            self.window.move(round(self.x), max(0, self.window.get_screen().get_height() - self.cell_height - 24))
            row = 1 if self.direction > 0 else 2
        elif self.dragging:
            row = self.current_row or 0
        else:
            row = _STATE_ROWS.get(state.get("state", "idle"), 0)
        if not self.dragging:
            self._set_row(row)
            frame_ms = _IDLE_FRAME_MS.get(self.frame_index, 1000) if row == 0 else _FRAME_MS.get(row, 150)
            elapsed_ms = (now - self.last_frame_at) * 1000
            if elapsed_ms >= frame_ms:
                if row == 0:
                    current = _IDLE_SEQUENCE.index(self.frame_index) if self.frame_index in _IDLE_SEQUENCE else 0
                    self.frame_index = _IDLE_SEQUENCE[(current + 1) % len(_IDLE_SEQUENCE)]
                else:
                    self.frame_index = (self.frame_index + 1) % self.pack.sprite_columns
                self.last_frame_at += frame_ms / 1000
                self.area.set_from_pixbuf(self._frame(row, self.frame_index))
        elif (now - self.last_frame_at) * 1000 >= 110:
            self.drag_frame_index = (self.drag_frame_index + 1) % self.drag_columns
            self.last_frame_at += 0.11
            self.area.set_from_pixbuf(self._drag_frame(self.drag_frame_index))
        self.last_tick_at = now
        return True

    def show(self) -> None:
        self.window.show_all() if self.visible else self.window.hide()
        initial_position = self.runtime.state.get("position", "bottom-right")
        self._place(initial_position)
        self.last_position = initial_position
        self._set_row(_STATE_ROWS.get(self.runtime.state.get("state", "idle"), 0))
        self.GLib.timeout_add(16, self._tick)
        self.Gtk.main()


def launch_sprite_window(runtime: Runtime, pack: AssetPack, *, name: str, topmost: bool, allow_dock_games: bool) -> None:
    # A previous session can leave a terminal state on disk. Start idle, while
    # still letting any queued fresh state event override it in the next tick.
    if runtime.state.get("state") not in {"idle", "hidden"}:
        runtime.state["state"] = "idle"
        runtime.state["mood"] = "idle"
        runtime._save_state()
    GtkSpriteWindow(
        runtime,
        pack,
        name=name,
        topmost=topmost,
        allow_dock_games=allow_dock_games,
    ).show()
