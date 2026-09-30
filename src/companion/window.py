"""Small Tk window that renders the runtime state on Windows and other Tk hosts."""

from __future__ import annotations

from pathlib import Path
import ctypes
import ctypes.util
import re
import tkinter as tk
from tkinter import filedialog
import time

from .paths import platform_name
from .protocol import POSITIONS, STATES, new_event
from .pack import AssetPack, PackError
from .queue import append_jsonl
from .runtime import Runtime
from .scheduled import LocalScheduler, ReminderError, ReminderStore
from .tokens import Theme, get_theme


# ── Glow canvas helpers ──────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _tk_color(hex_color: str) -> str:
    """Convert CSS-like #rrggbbaa tokens to Tk's #rrggbb format."""
    if hex_color.startswith("#") and len(hex_color) == 9:
        return hex_color[:7]
    return hex_color


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))  # type: ignore[return-value]


class _X11Shape:
    """Use the X11 Shape extension to remove transparent pixels on Linux."""

    class Rectangle(ctypes.Structure):
        _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short),
                    ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]

    def __init__(self):
        self.x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        self.xext = ctypes.CDLL(ctypes.util.find_library("Xext") or "libXext.so.6")
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.x11.XFlush.argtypes = [ctypes.c_void_p]
        self.xdisplay = self.x11.XOpenDisplay(None)
        self.xext.XShapeCombineRectangles.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.POINTER(self.Rectangle), ctypes.c_int,
            ctypes.c_int, ctypes.c_int,
        ]
        if not self.xdisplay:
            # No X server (headless test runner, SSH session): the shape
            # fallback is unavailable. Raise so callers treat this as absent.
            self.close()
            raise OSError("X11 shape support unavailable: no display")
        # Cache the silhouette per frame, keeping the frame itself in each
        # entry so a recycled id() can never alias two different PhotoImages.
        self._mask_cache: dict[int, tuple[tk.PhotoImage, tuple[tuple[int, int, int, int], ...]]] = {}
        self._last_applied: tuple[tk.PhotoImage, tuple[tuple[int, int, int, int], ...]] | None = None

    def _frame_mask(self, frame: tk.PhotoImage) -> tuple[tuple[int, int, int, int], ...]:
        key = id(frame)
        cached = self._mask_cache.get(key)
        if cached is not None and cached[0] is frame:
            return cached[1]
        width, height = frame.width(), frame.height()
        rows: list[tuple[int, int, int, int]] = []
        for y in range(height):
            left = 0
            right = width - 1
            try:
                while left < width and frame.transparency_get(left, y):
                    left += 1
                while right >= left and frame.transparency_get(right, y):
                    right -= 1
            except tk.TclError:
                left, right = 0, width - 1
            if left <= right:
                rows.append((left, y, right - left + 1, 1))
        self._mask_cache[key] = (frame, tuple(rows))
        return self._mask_cache[key][1]

    def apply(self, window_id: int, frame: tk.PhotoImage, x: int, y: int,
              extra_rectangles: list[tuple[int, int, int, int]]) -> None:
        if not self.xdisplay or not window_id:
            return
        signature = (frame, tuple(extra_rectangles))
        if signature == self._last_applied:
            return
        rectangles = [
            (x + left, y + top, width, height)
            for left, top, width, height in self._frame_mask(frame)
        ]
        rectangles.extend(extra_rectangles)
        if not rectangles:
            return
        native = (self.Rectangle * len(rectangles))(
            *(self.Rectangle(px, py, width, height) for px, py, width, height in rectangles)
        )
        # ShapeBounding = 0, ShapeSet = 0, Unsorted = 0.
        self.xext.XShapeCombineRectangles(
            self.xdisplay, window_id, 0, 0, 0, native, len(rectangles), 0, 0,
        )
        self.x11.XFlush(self.xdisplay)
        self._last_applied = signature

    def close(self) -> None:
        if self.xdisplay:
            self.x11.XCloseDisplay(self.xdisplay)
            self.xdisplay = None


class AnimatedAsset:
    def __init__(self, path: Path, clock=time.monotonic):
        self.path = path
        self.clock = clock
        self.frames: list[tk.PhotoImage] = []
        self.durations: list[float] = []
        self.index = 0
        self._last_time = self.clock()
        self._load()

    def _load(self) -> None:
        if self.path.suffix.lower() == ".gif":
            metadata_durations = self._gif_durations()
            index = 0
            while True:
                try:
                    self.frames.append(tk.PhotoImage(file=str(self.path), format=f"gif -index {index}"))
                except tk.TclError:
                    break
                index += 1
            default_duration = 0.1
            self.durations = [
                duration if duration > 0 else default_duration
                for duration in (metadata_durations[: len(self.frames)] + [default_duration] * len(self.frames))[: len(self.frames)]
            ]
        elif self.path.exists():
            self.frames.append(tk.PhotoImage(file=str(self.path)))
            self.durations = [float("inf")]
        if not self.frames:
            raise ValueError(f"could not load image asset: {self.path}")

    def _gif_durations(self) -> list[float]:
        """Read GIF Graphic Control Extension delays, tolerating missing metadata."""
        try:
            data = self.path.read_bytes()
        except OSError:
            return []
        durations: list[float] = []
        if len(data) < 13 or data[:3] != b"GIF":
            return durations
        packed = data[10]
        offset = 13 + (3 * (2 ** ((packed & 7) + 1)) if packed & 0x80 else 0)
        pending = 0.1
        while offset < len(data):
            marker = data[offset]; offset += 1
            if marker == 0x3B: break
            if marker == 0x21:
                if offset >= len(data): break
                label = data[offset]; offset += 1
                if label == 0xF9 and offset + 5 <= len(data) and data[offset] == 4:
                    delay = data[offset + 2] | (data[offset + 3] << 8)
                    pending = delay / 100.0 or 0.1
                    offset += 5
                else:
                    while offset < len(data):
                        size = data[offset]; offset += 1
                        if size == 0: break
                        offset += size
            elif marker == 0x2C:
                if offset + 9 > len(data): break
                flags = data[offset + 8]; offset += 9
                if flags & 0x80: offset += 3 * (2 ** ((flags & 7) + 1))
                if offset >= len(data): break
                offset += 1
                while offset < len(data):
                    size = data[offset]; offset += 1
                    if size == 0: break
                    offset += size
                durations.append(pending)
                pending = 0.1
            else:
                break
        # Keep compatibility with tiny synthetic fixtures that contain only
        # GCE records; real GIFs are handled by the block-aware parser above.
        if not durations:
            for match in re.finditer(rb"\x21\xf9\x04.(.)(.)", data, flags=re.DOTALL):
                delay = match.group(1)[0] | (match.group(2)[0] << 8)
                durations.append(delay / 100.0 or 0.1)
        return durations

    @property
    def current(self) -> tk.PhotoImage:
        return self.frames[self.index]

    def advance(self, now=None) -> None:
        if len(self.frames) <= 1:
            return
        current_time = self.clock() if now is None else now
        if current_time < self._last_time:
            self._last_time = current_time
            return
        elapsed = current_time - self._last_time
        while elapsed + 1e-9 >= self.durations[self.index]:
            elapsed -= self.durations[self.index]
            self.index = (self.index + 1) % len(self.frames)
        self._last_time = current_time - elapsed

    def reset(self) -> None:
        self.index = 0
        self._last_time = self.clock()


# ── Desktop window ───────────────────────────────────────────────────────────

class DesktopWindow:
    # Glow render size (doubled for canvas)
    _GLOW_R = 48

    def __init__(
        self,
        runtime: Runtime,
        *,
        asset: Path | None = None,
        pack: AssetPack | None = None,
        name: str = "Companion",
        topmost: bool = True,
        opacity: float = 1.0,
        show_messages: bool = True,
        pack_name: str | None = None,
        allow_dock_games: bool = False,
        theme: Theme | None = None,
    ):
        self.runtime = runtime
        self.name = name
        self.opacity = max(0.35, min(1.0, float(opacity)))
        self.show_messages = show_messages
        self.allow_dock_games = allow_dock_games
        self._dock_running = False
        self._dock_after_id: str | None = None
        self._dock_x = 0
        self._dock_direction = 1
        self._active_animation_action: str | None = None
        self.theme = theme or get_theme("dark")
        self.reminders = ReminderStore(runtime.root / "reminders.json")
        self.scheduler = LocalScheduler(self.reminders, runtime.inbox)
        self.reminder_panel: ReminderPanel | None = None
        self._last_glow_state: str | None = None

        self.root = tk.Tk()
        self._x11_shape: _X11Shape | None = None
        if platform_name() == "linux":
            try:
                self._x11_shape = _X11Shape()
            except (OSError, AttributeError):
                self._x11_shape = None
        self.root.title(name)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", topmost)
        self.root.configure(bg=self.theme.bg_stage)
        if platform_name() == "windows":
            try:
                self.root.wm_attributes("-transparentcolor", self.theme.bg_stage)
            except tk.TclError:
                pass
        try:
            self.root.attributes("-alpha", self.opacity)
        except tk.TclError:
            pass
        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<Escape>", self._escape)
        self.root.bind("<ButtonRelease-1>", self._left_click_release)
        self.root.bind("<Button-3>", self._show_controls)

        self.pack = pack
        self.pack_name = pack_name or (pack.name if pack else None)
        self.image_path = asset or (pack.animation_for(state="idle") if pack else None)
        try:
            self.image = AnimatedAsset(self.image_path) if self.image_path else None
        except (OSError, ValueError, tk.TclError):
            self.image = None

        # Glow canvas behind the sprite
        glow_size = self._GLOW_R * 2
        self.glow_canvas = tk.Canvas(
            self.root, width=glow_size, height=glow_size,
            bg=self.theme.bg_stage, highlightthickness=0,
        )
        self._glow_oval: int | None = None

        self.image_label = tk.Label(
            self.root,
            bg=self.theme.bg_stage,
            fg=self.theme.fg_accent,
            bd=0,
            highlightthickness=0,
        )
        self.glow_canvas.pack()
        if self._x11_shape:
            # The neon color-key glow is useful on Windows but would be opaque on X11.
            self.glow_canvas.pack_forget()
        self.image_label.pack()

        self._scale = 1.0
        self._menu_open = False
        self.bubble = tk.Label(
            self.root,
            text="",
            bg=self.theme.bg_bubble,
            fg=self.theme.fg_bubble,
            padx=self.theme.spacing.lg,
            pady=self.theme.spacing.sm,
            wraplength=260,
            justify="left",
            relief="solid",
            borderwidth=1,
        )
        self.control_error = tk.Label(
            self.root,
            text="",
            bg=self.theme.bg_bubble,
            fg=self.theme.states["error"].accent,
            padx=self.theme.spacing.sm,
            pady=self.theme.spacing.xs,
        )
        self.messages_var = tk.BooleanVar(value=show_messages)
        self.dock_games_var = tk.BooleanVar(value=allow_dock_games)
        self.dock_running_var = tk.BooleanVar(value=False)
        self.context_menu = self._build_context_menu()
        self._drag_origin: tuple[int, int] | None = None
        self._dragged = False
        self._refresh()

    # ── Sectioned context menu (M12) ────────────────────────────────────

    def _make_submenu(self, parent: tk.Menu) -> tk.Menu:
        t = self.theme
        return tk.Menu(parent, tearoff=False, bg=t.bg_menu, fg=t.fg_primary,
                       activebackground=t.bg_menu_hover, activeforeground=t.fg_primary,
                       disabledforeground=t.bg_menu_disabled)

    def _build_context_menu(self) -> tk.Menu:
        t = self.theme
        menu = tk.Menu(self.root, tearoff=False, bg=t.bg_menu, fg=t.fg_primary,
                       activebackground=t.bg_menu_hover, activeforeground=t.fg_primary,
                       disabledforeground=t.bg_menu_disabled)

        # ── Companion section ────────────────────────────────────────────
        state_menu = self._make_submenu(menu)
        for value in sorted(STATES):
            sv = t.states.get(value)
            label = f"{sv.icon}  {value}" if sv else value
            state_menu.add_command(label=label, command=lambda v=value: self.set_state(v))
        menu.add_cascade(label="Companion  \u25b6  State", menu=state_menu)

        theme_menu = self._make_submenu(menu)
        for name in ("dark", "light", "soft-neon"):
            prefix = "\u2713 " if t.name == name else "   "
            theme_menu.add_command(label=f"{prefix}{name}", command=lambda n=name: self.set_theme(n))
        menu.add_cascade(label="Companion  \u25b6  Theme", menu=theme_menu)

        menu.add_checkbutton(label="Show messages", variable=self.messages_var, command=self.toggle_messages)
        menu.add_checkbutton(
            label="Allow scripted Dock play (fixed strip)",
            variable=self.dock_games_var,
            command=self.toggle_dock_games,
        )
        menu.add_checkbutton(
            label="Run along preset bottom strip",
            variable=self.dock_running_var,
            command=self.toggle_dock_run,
        )
        menu.add_separator()

        # ── Window section ───────────────────────────────────────────────
        position_menu = self._make_submenu(menu)
        for value in sorted(POSITIONS):
            position_menu.add_command(label=value, command=lambda v=value: self.set_position(v))
        menu.add_cascade(label="Window  \u25b6  Position", menu=position_menu)

        opacity_menu = self._make_submenu(menu)
        for label, value in (("35%", 0.35), ("50%", 0.5), ("75%", 0.75), ("100%", 1.0)):
            opacity_menu.add_command(label=label, command=lambda v=value: self.set_opacity(v))
        menu.add_cascade(label="Window  \u25b6  Opacity", menu=opacity_menu)
        menu.add_separator()

        # ── Runtime section ──────────────────────────────────────────────
        menu.add_command(label="Reload pack", command=self.reload_pack)
        menu.add_command(label="Choose pack\u2026", command=self.choose_pack)
        menu.add_separator()

        # ── System section ───────────────────────────────────────────────
        menu.add_command(label="Reminders\u2026", command=self.open_reminders)
        menu.add_separator()

        # ── Exit ─────────────────────────────────────────────────────────
        menu.add_command(label="Close", command=self.close)
        return menu

    def close(self) -> None:
        self._stop_dock_run()
        if self._x11_shape:
            self._x11_shape.close()
        self.root.destroy()

    def toggle_dock_games(self) -> bool:
        self.allow_dock_games = self.dock_games_var.get()
        if not self.allow_dock_games:
            self._stop_dock_run()
        return self.allow_dock_games

    def toggle_dock_run(self) -> bool:
        if self._dock_running:
            self._stop_dock_run()
            return False
        if not self.allow_dock_games:
            self.dock_running_var.set(False)
            self._show_control_error("Enable scripted Dock play in the menu first")
            return False
        if not self.pack or not {"running-right", "running-left"}.issubset(self.pack.animations):
            self.dock_running_var.set(False)
            self._show_control_error("This appearance has no running animations")
            return False
        self._show_control_error("")
        self._dock_running = True
        self.dock_running_var.set(True)
        self._dock_direction = 1
        self._dock_x = 12
        self._set_dock_animation()
        self._advance_dock_run()
        return True

    def _set_dock_animation(self) -> None:
        action = "running-right" if self._dock_direction > 0 else "running-left"
        if not self.pack:
            return
        path = self.pack.animation_for(state="idle", action=action)
        self._active_animation_action = action
        if path == self.image_path:
            return
        try:
            self.image = AnimatedAsset(path)
            self.image_path = path
            self._render_current_frame()
        except (OSError, ValueError, tk.TclError):
            self._show_control_error(f"Could not load animation: {path.name}")
            self._stop_dock_run()

    def _stop_dock_run(self) -> None:
        self._dock_running = False
        self.dock_running_var.set(False)
        if self._dock_after_id is not None:
            try:
                self.root.after_cancel(self._dock_after_id)
            except tk.TclError:
                pass
            self._dock_after_id = None
        self._active_animation_action = None

    def _advance_dock_run(self) -> None:
        if not self._dock_running:
            return
        width = self.root.winfo_reqwidth()
        height = self.root.winfo_reqheight()
        strip_left = 12
        strip_right = max(strip_left, self.root.winfo_screenwidth() - width - 12)
        # Companion uses a fixed bottom-edge band and never queries Dock/taskbar geometry.
        y = max(0, self.root.winfo_screenheight() - height - 24)
        self._dock_x += self._dock_direction * 4
        if self._dock_x >= strip_right:
            self._dock_x = strip_right
            self._dock_direction = -1
            self._set_dock_animation()
        elif self._dock_x <= strip_left:
            self._dock_x = strip_left
            self._dock_direction = 1
            self._set_dock_animation()
        self.root.geometry(f"+{self._dock_x}+{y}")
        self._dock_after_id = self.root.after(16, self._advance_dock_run)

    def _escape(self, _event: tk.Event) -> str:
        if self._menu_open:
            self.context_menu.unpost()
            self._menu_open = False
            return "break"
        self.close()
        return "break"

    def resize(self, delta: float) -> None:
        self._scale = max(0.6, min(1.8, self._scale + delta))
        self._render_current_frame()

    def _render_current_frame(self) -> None:
        if not self.image:
            return
        frame = self.image.current
        if self._scale > 1:
            frame = frame.zoom(max(1, round(self._scale)))
        elif self._scale < 1:
            frame = frame.subsample(max(1, round(1 / self._scale)))
        self._display_frame = frame
        self.image_label.configure(image=frame)

    def _show_controls(self, event: tk.Event) -> None:
        try:
            self.context_menu.update_idletasks()
            width = self.context_menu.winfo_reqwidth()
            height = self.context_menu.winfo_reqheight()
            x = max(0, min(event.x_root + 12, self.root.winfo_screenwidth() - width - 8))
            y = max(0, min(event.y_root + 12, self.root.winfo_screenheight() - height - 8))
        except AttributeError:
            x, y = event.x_root, event.y_root
        self._menu_open = True
        try:
            self.context_menu.tk_popup(x, y)
        finally:
            self.context_menu.grab_release()
            self._menu_open = False

    def _left_click_release(self, event: tk.Event) -> None:
        if self._drag_origin:
            dx = abs(event.x_root - self.root.winfo_x() - self._drag_origin[0])
            dy = abs(event.y_root - self.root.winfo_y() - self._drag_origin[1])
            if dx <= 4 and dy <= 4:
                self._show_controls(event)
        self._drag_origin = None

    def _publish_events(self, *events: tuple[str, str]) -> None:
        for event_type, value in events:
            append_jsonl(
                self.runtime.inbox,
                new_event(event_type, agent="gui", companion_id=self.runtime.companion_id, value=value),
            )
        self.runtime.process_once()

    def set_state(self, value: str) -> None:
        if value not in STATES:
            raise ValueError(f"unknown state: {value}")
        self._publish_events(("state", value), ("mood", value))

    def set_position(self, value: str) -> None:
        if value not in POSITIONS:
            raise ValueError(f"unknown position: {value}")
        self._publish_events(("move", value))
        self._place(value)

    def set_opacity(self, value: float) -> None:
        self.opacity = max(0.35, min(1.0, float(value)))
        try:
            self.root.attributes("-alpha", self.opacity)
        except tk.TclError:
            pass

    def set_theme(self, name: str) -> None:
        """Switch the presentation theme at runtime."""
        self.theme = get_theme(name)
        self._last_glow_state = None  # force glow redraw
        self._apply_theme()

    def _apply_theme(self) -> None:
        """Push current theme colors into every widget."""
        t = self.theme
        self.root.configure(bg=t.bg_stage)
        self.glow_canvas.configure(bg=t.bg_stage)
        self.image_label.configure(bg=t.bg_stage, fg=t.fg_accent)
        self.bubble.configure(bg=t.bg_bubble, fg=t.fg_bubble,
                              padx=t.spacing.lg, pady=t.spacing.sm)
        self.control_error.configure(bg=t.bg_bubble, fg=t.states["error"].accent,
                                     padx=t.spacing.sm, pady=t.spacing.xs)
        # Rebuild the context menu with new colors
        self.context_menu = self._build_context_menu()

    def toggle_messages(self) -> bool:
        self.show_messages = not self.show_messages
        self.messages_var.set(self.show_messages)
        if not self.show_messages and self.bubble.winfo_ismapped():
            self.bubble.pack_forget()
        return self.show_messages

    def _show_control_error(self, message: str) -> None:
        self.control_error.configure(text=message)
        if message:
            if not self.control_error.winfo_ismapped():
                self.control_error.pack()
        elif self.control_error.winfo_ismapped():
            self.control_error.pack_forget()

    def reload_pack(self) -> bool:
        if self.pack is None:
            self._show_control_error("No pack is configured")
            return False
        try:
            pack = AssetPack.load(self.pack.root)
            image_path = pack.animation_for(
                state=self.runtime.state["state"],
                mood=self.runtime.state.get("mood"),
            )
            image = AnimatedAsset(image_path)
        except (OSError, ValueError, PackError, tk.TclError) as exc:
            self._show_control_error(str(exc))
            return False
        self.pack = pack
        self.context_menu = self._build_context_menu()
        self.image_path = image_path
        self.image = image
        self._show_control_error("")
        return True

    def choose_pack(self) -> bool:
        selected = filedialog.askdirectory(parent=self.root, title="Choose companion pack")
        if not selected:
            return False
        try:
            pack = AssetPack.load(Path(selected))
            image_path = pack.animation_for(state=self.runtime.state["state"], mood=self.runtime.state.get("mood"))
            image = AnimatedAsset(image_path)
        except (OSError, ValueError, PackError, tk.TclError) as exc:
            self._show_control_error(str(exc))
            return False
        self.pack, self.pack_name, self.image_path, self.image = pack, pack.name, image_path, image
        self.context_menu = self._build_context_menu()
        self._show_control_error("")
        return True

    def _drag_start(self, event: tk.Event) -> None:
        self._stop_dock_run()
        self._drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())
        self._dragged = True
        self._publish_events(("move", "free"))

    def _drag_move(self, event: tk.Event) -> None:
        if self._drag_origin:
            x = event.x_root - self._drag_origin[0]
            y = event.y_root - self._drag_origin[1]
            self.root.geometry(f"+{x}+{y}")

    def _place(self, position: str) -> None:
        if position == "free":
            return
        width = self.root.winfo_reqwidth()
        height = self.root.winfo_reqheight()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        margin = 24
        coordinates = {
            "top-left": (margin, margin),
            "top-right": (screen_width - width - margin, margin),
            "bottom-left": (margin, screen_height - height - margin),
            "bottom-right": (screen_width - width - margin, screen_height - height - margin),
            "dock": (screen_width // 2 - width // 2, screen_height - height - margin),
        }
        if position in POSITIONS:
            x, y = coordinates[position]
            self.root.geometry(f"+{max(0, x)}+{max(0, y)}")

    # ── Glow rendering ──────────────────────────────────────────────────

    def _draw_glow(self, state_name: str) -> None:
        """Draw a soft glow circle behind the companion sprite."""
        if self._x11_shape:
            return
        if self._last_glow_state == state_name:
            return
        self._last_glow_state = state_name
        t = self.theme
        sv = t.states.get(state_name)
        if sv is None:
            return
        glow_color = sv.glow[3]  # token may include CSS alpha
        if glow_color.endswith("00"):
            return  # fully transparent → skip
        glow_color = _tk_color(glow_color)
        r = self._GLOW_R
        self.glow_canvas.delete("glow")
        # Outer glow ring
        self._glow_oval = self.glow_canvas.create_oval(
            4, 4, r * 2 - 4, r * 2 - 4,
            fill="", outline=glow_color, width=3,
            tags="glow",
        )
        # Subtle fill
        self.glow_canvas.create_oval(
            12, 12, r * 2 - 12, r * 2 - 12,
            fill=glow_color, outline="",
            tags="glow",
        )

    # ── Refresh loop ────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self.scheduler.tick()
        self.runtime.process_once()
        state = self.runtime.state
        t = self.theme
        if self._dock_running and not state["visible"]:
            self._stop_dock_run()

        # Update image asset if state changed
        next_image_path = (
            self.pack.animation_for(state="idle", action=self._active_animation_action)
            if self.pack and self._active_animation_action
            else self.pack.animation_for(state=state["state"], mood=state.get("mood"))
            if self.pack
            else self.image_path
        )
        if next_image_path is not None and next_image_path != self.image_path and next_image_path.exists():
            self.image_path = next_image_path
            try:
                candidate = AnimatedAsset(next_image_path)
                self.image = candidate
                self.image_path = next_image_path
            except (OSError, ValueError, tk.TclError):
                self._show_control_error(f"Could not load asset: {next_image_path.name}")

        if self.image:
            self._render_current_frame()
            self.image.advance()
        else:
            # Accessible fallback: show name + state + icon
            sv = t.states.get(state["state"])
            icon = sv.icon if sv else ""
            self.image_label.configure(
                image="",
                text=f"{self.name}\n{icon} [{state['state']}]",
                padx=t.spacing.lg,
                pady=t.spacing.lg,
            )

        # Glow updates
        self._draw_glow(state["state"])

        self.root.withdraw() if not state["visible"] else self.root.deiconify()
        if not self._dragged and not self._dock_running:
            self._place(state["position"])

        # Message bubble
        message = state.get("message")
        if self.show_messages and state["visible"] and message and message.get("text"):
            self.bubble.configure(text=message["text"])
            if not self.bubble.winfo_ismapped():
                self.bubble.pack()
        elif self.bubble.winfo_ismapped():
            self.bubble.pack_forget()

        if self._x11_shape and self.image and self.root.winfo_ismapped():
            extra_rectangles = []
            for widget in (self.bubble, self.control_error):
                if widget.winfo_ismapped():
                    extra_rectangles.append((
                        widget.winfo_x(), widget.winfo_y(),
                        widget.winfo_width(), widget.winfo_height(),
                    ))
            try:
                self._x11_shape.apply(
                    self.root.winfo_id(), self.image.current,
                    self.image_label.winfo_x(), self.image_label.winfo_y(),
                    extra_rectangles,
                )
            except (OSError, tk.TclError):
                pass

        self.root.after(16 if self._dock_running else t.motion.poll_ms, self._refresh)

    def show(self) -> None:
        self.root.mainloop()

    def open_reminders(self) -> None:
        if self.reminder_panel and self.reminder_panel.root.winfo_exists():
            self.reminder_panel.root.lift()
            return
        self.reminder_panel = ReminderPanel(self.root, self.reminders)


def launch(
    runtime: Runtime,
    *,
    asset: Path | None = None,
    pack: AssetPack | None = None,
    name: str = "Companion",
    topmost: bool = True,
    opacity: float = 1.0,
    show_messages: bool = True,
    pack_name: str | None = None,
    allow_dock_games: bool = False,
    theme: Theme | None = None,
) -> None:
    if platform_name() == "linux" and pack is not None and pack.sprite_sheet:
        from .gtk_sprite_window import launch_sprite_window

        launch_sprite_window(
            runtime,
            pack,
            name=name,
            topmost=topmost,
            allow_dock_games=allow_dock_games,
        )
        return
    DesktopWindow(
        runtime,
        asset=asset,
        pack=pack,
        name=name,
        topmost=topmost,
        opacity=opacity,
        show_messages=show_messages,
        pack_name=pack_name,
        allow_dock_games=allow_dock_games,
        theme=theme,
    ).show()


class ReminderPanel:
    """Small local reminder editor; it only writes ScheduledEvent records."""

    def __init__(self, parent: tk.Tk, store: ReminderStore):
        self.store = store
        self.root = tk.Toplevel(parent)
        self.root.title("Reminder")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        frame = tk.Frame(self.root, padx=12, pady=12)
        frame.pack()
        tk.Label(frame, text="Message:").grid(row=0, column=0, sticky="w")
        self.message = tk.Entry(frame, width=30)
        self.message.grid(row=0, column=1, columnspan=2, pady=3)
        tk.Label(frame, text="Time:").grid(row=1, column=0, sticky="w")
        self.when = tk.Entry(frame, width=10)
        self.when.insert(0, "19:30")
        self.when.grid(row=1, column=1, sticky="w", pady=3)
        tk.Button(frame, text="Save reminder", command=self.save).grid(row=2, column=0, columnspan=3, pady=7)
        self.error = tk.Label(frame, text="", fg="#a00000")
        self.error.grid(row=3, column=0, columnspan=3)
        self.listbox = tk.Listbox(frame, width=52, height=6)
        self.listbox.grid(row=4, column=0, columnspan=2, pady=(8, 0))
        tk.Button(frame, text="Cancel selected", command=self.cancel_selected).grid(row=4, column=2, padx=(8, 0), sticky="n")
        self.refresh()

    def save(self) -> None:
        try:
            self.store.create(due_at=self.when.get(), message=self.message.get())
        except ReminderError as exc:
            self.error.configure(text=str(exc))
            return
        self.error.configure(text="")
        self.message.delete(0, tk.END)
        self.refresh()

    def refresh(self) -> None:
        self.listbox.delete(0, tk.END)
        for reminder in self.store.list(status="pending"):
            due = reminder.due_at.replace("T", " ")[:16]
            self.listbox.insert(tk.END, f"{due}  {reminder.message}")

    def cancel_selected(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        pending = self.store.list(status="pending")
        self.store.cancel(pending[selection[0]].id)
        self.refresh()

    def save(self) -> None:
        try:
            self.store.create(due_at=self.when.get(), message=self.message.get())
        except ReminderError as exc:
            self.error.configure(text=str(exc))
            return
        self.error.configure(text="")
        self.message.delete(0, tk.END)
        self.refresh()

    def refresh(self) -> None:
        self.listbox.delete(0, tk.END)
        for reminder in self.store.list(status="pending"):
            due = reminder.due_at.replace("T", " ")[:16]
            self.listbox.insert(tk.END, f"{due}  {reminder.message}")

    def cancel_selected(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        pending = self.store.list(status="pending")
        self.store.cancel(pending[selection[0]].id)
        self.refresh()
