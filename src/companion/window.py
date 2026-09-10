"""Small Tk window that renders the runtime state on Windows and other Tk hosts."""

from __future__ import annotations

from pathlib import Path
import re
import tkinter as tk
import time

from .paths import platform_name
from .protocol import POSITIONS, STATES, new_event
from .pack import AssetPack, PackError
from .queue import append_jsonl
from .runtime import Runtime
from .scheduled import LocalScheduler, ReminderError, ReminderStore


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
        # A GCE stores its delay as hundredths of a second, little-endian,
        # between the packed field and transparency index.
        for match in re.finditer(rb"\x21\xf9\x04(.)(.)(.)", data, flags=re.DOTALL):
            delay = match.group(2)[0] | (match.group(3)[0] << 8)
            durations.append(delay / 100.0)
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


class DesktopWindow:
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
    ):
        self.runtime = runtime
        self.name = name
        self.opacity = max(0.35, min(1.0, float(opacity)))
        self.show_messages = show_messages
        self.reminders = ReminderStore(runtime.root / "reminders.json")
        self.scheduler = LocalScheduler(self.reminders, runtime.inbox)
        self.reminder_panel: ReminderPanel | None = None
        self.root = tk.Tk()
        self.root.title(name)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", topmost)
        self.root.configure(bg="magenta")
        if platform_name() == "windows":
            try:
                self.root.wm_attributes("-transparentcolor", "magenta")
            except tk.TclError:
                self.root.attributes("-alpha", self.opacity)
        else:
            # Linux/macOS Tk rarely supports -transparentcolor; use alpha.
            try:
                self.root.attributes("-alpha", self.opacity)
            except tk.TclError:
                pass
        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.bind("<Button-3>", self._show_controls)

        self.pack = pack
        self.pack_name = pack_name or (pack.name if pack else None)
        self.image_path = asset or (pack.animation_for(state="idle") if pack else None)
        try:
            self.image = AnimatedAsset(self.image_path) if self.image_path else None
        except (OSError, ValueError, tk.TclError):
            self.image = None
        self.image_label = tk.Label(self.root, bg="magenta", fg="#a9ffcb", bd=0, highlightthickness=0)
        self.image_label.pack()
        self.image_label.bind("<Button-3>", self._show_controls)
        self.bubble = tk.Label(
            self.root,
            text="",
            bg="#10151b",
            fg="#a9ffcb",
            padx=8,
            pady=5,
            wraplength=260,
            justify="left",
        )
        self.control_error = tk.Label(self.root, text="", bg="#10151b", fg="#ffadad", padx=6, pady=3)
        self.messages_var = tk.BooleanVar(value=show_messages)
        self.context_menu = self._build_context_menu()
        self._drag_origin: tuple[int, int] | None = None
        self._refresh()

    def _build_context_menu(self) -> tk.Menu:
        menu = tk.Menu(self.root, tearoff=False)
        state_menu = tk.Menu(menu, tearoff=False)
        for value in sorted(STATES):
            state_menu.add_command(label=value, command=lambda value=value: self.set_state(value))
        menu.add_cascade(label="State", menu=state_menu)

        position_menu = tk.Menu(menu, tearoff=False)
        for value in sorted(POSITIONS):
            position_menu.add_command(label=value, command=lambda value=value: self.set_position(value))
        menu.add_cascade(label="Position", menu=position_menu)

        opacity_menu = tk.Menu(menu, tearoff=False)
        for label, value in (("35%", 0.35), ("50%", 0.5), ("75%", 0.75), ("100%", 1.0)):
            opacity_menu.add_command(label=label, command=lambda value=value: self.set_opacity(value))
        menu.add_cascade(label="Opacity", menu=opacity_menu)
        menu.add_checkbutton(label="Show messages", variable=self.messages_var, command=self.toggle_messages)
        menu.add_command(label="Reload pack", command=self.reload_pack)
        menu.add_separator()
        menu.add_command(label="Reminders...", command=self.open_reminders)
        return menu

    def _show_controls(self, event: tk.Event) -> None:
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

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
        self.image_path = image_path
        self.image = image
        self._show_control_error("")
        return True

    def _drag_start(self, event: tk.Event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

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

    def _refresh(self) -> None:
        self.scheduler.tick()
        self.runtime.process_once()
        state = self.runtime.state
        next_image_path = self.pack.animation_for(state=state["state"], mood=state.get("mood")) if self.pack else self.image_path
        if next_image_path is not None and next_image_path != self.image_path and next_image_path.exists():
            self.image_path = next_image_path
            try:
                self.image = AnimatedAsset(next_image_path)
            except (OSError, ValueError, tk.TclError):
                self.image = None
        if self.image:
            self.image_label.configure(image=self.image.current)
            self.image.advance()
        else:
            self.image_label.configure(image="", text=f"{self.name}\n[{state['state']}]", padx=12, pady=12)
        self.root.withdraw() if not state["visible"] else self.root.deiconify()
        self._place(state["position"])
        message = state.get("message")
        if self.show_messages and state["visible"] and message and message.get("text"):
            self.bubble.configure(text=message["text"])
            if not self.bubble.winfo_ismapped():
                self.bubble.pack()
        elif self.bubble.winfo_ismapped():
            self.bubble.pack_forget()
        self.root.after(100, self._refresh)

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
) -> None:
    DesktopWindow(
        runtime,
        asset=asset,
        pack=pack,
        name=name,
        topmost=topmost,
        opacity=opacity,
        show_messages=show_messages,
        pack_name=pack_name,
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
