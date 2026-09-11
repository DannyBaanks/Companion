"""Consumer-facing local Companion Hub and its process-action controller."""

from __future__ import annotations

import math
import os
from queue import Empty, SimpleQueue
from threading import Thread
import tkinter as tk
from tkinter import messagebox

from .models import CompanionRecord, PackRecord
from .processes import ProcessManager, ProcessStatus
from .registry import CompanionRegistry


_BG = "#F5F2EC"
_PANEL = "#FFFDFA"
_STAGE = "#E5ECE2"
_INK = "#263C31"
_MUTED = "#627166"
_ACCENT = "#355D47"
_STATUS = {
    ProcessStatus.UNMANAGED: "Not managed by this session",
    ProcessStatus.STOPPED: "Resting · ready when you are",
    ProcessStatus.RUNNING: "Out on your desktop",
    ProcessStatus.HIDDEN: "Tucked away · still running",
    ProcessStatus.EXITED: "Your companion has closed",
}
_PROGRESS = {"start": "Starting…", "show": "Showing…", "hide": "Hiding…", "stop": "Stopping…"}
_DONE = {"start": "Started", "show": "Shown on your desktop", "hide": "Tucked away", "stop": "Stopped"}


class HubWindow:
    """One collection, one living stage, and contextual information.

    Tk updates stay on the owning thread. Process operations run in a worker;
    the single refresh timer collects their results without blocking Tk.
    """

    def __init__(self, root, packs: list[PackRecord], registry: CompanionRegistry,
                 processes: ProcessManager):
        self.root = root
        self.packs = packs
        self.registry = registry
        self.processes = processes
        self.companions = {record.companion_id: record for record in registry.list()}
        self.selected_id: str | None = None
        self._packs_by_root = {pack.root.resolve(): pack for pack in packs}
        self._preview_image = None
        self._busy: tuple[str, str] | None = None
        self._results = SimpleQueue()
        self._errors: dict[str, tuple[str, str]] = {}
        self._last_activity: dict[str, str] = {}
        self._closed = False
        self._refresh_id = None
        self.collection_cards: dict[str, tk.Button] = {}
        self._build()
        self.select(next(iter(self.companions), None))
        self.root.bind("<Destroy>", self._on_destroy, add="+")
        self._schedule_refresh()

    def _build(self):
        self.root.title("Companion Hub")
        self.root.geometry("1120x720")
        self.root.minsize(940, 580)
        self.root.configure(bg=_BG)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.content = tk.Frame(self.root, bg=_BG, padx=24, pady=24)
        self.content.grid(row=0, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, minsize=210)
        self.content.grid_columnconfigure(1, weight=1, minsize=360)
        self.content.grid_columnconfigure(2, minsize=220)
        self.content.grid_rowconfigure(1, weight=1)
        self._label(self.content, "Companion Hub", size=22, bold=True).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 24))

        self.collection = tk.Frame(self.content, bg=_PANEL, padx=16, pady=20)
        self.collection.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        self.collection.grid_columnconfigure(0, weight=1)
        self.collection.grid_rowconfigure(2, weight=1)
        self._label(self.collection, "Your collection", size=14, bold=True).grid(row=0, column=0, sticky="w")
        self._label(self.collection, "A little company, close by.", color=_MUTED, wrap=175).grid(
            row=1, column=0, sticky="w", pady=(6, 20))
        self.collection_canvas = tk.Canvas(self.collection, bg=_PANEL, highlightthickness=0, width=185)
        self.collection_canvas.grid(row=2, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(self.collection, orient="vertical", command=self.collection_canvas.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.collection_canvas.configure(yscrollcommand=scrollbar.set)
        self.cards_frame = tk.Frame(self.collection_canvas, bg=_PANEL)
        self.cards_frame.grid_columnconfigure(0, weight=1)
        cards_id = self.collection_canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.cards_frame.bind("<Configure>", lambda event: self.collection_canvas.configure(
            scrollregion=self.collection_canvas.bbox("all")))
        self.collection_canvas.bind("<Configure>", lambda event: self.collection_canvas.itemconfigure(
            cards_id, width=event.width))
        self._build_cards()

        self.stage = tk.Frame(self.content, bg=_STAGE, padx=24, pady=24)
        self.stage.grid(row=1, column=1, sticky="nsew")
        self.stage.grid_columnconfigure(0, weight=1)
        self.stage.grid_rowconfigure(2, weight=1)
        self._label(self.stage, "A SPACE FOR YOUR COMPANION", size=9, color=_MUTED).grid(row=0, column=0)
        self.name_label = self._label(self.stage, "", size=25, bold=True, wrap=340)
        self.name_label.grid(row=1, column=0, pady=(16, 8))
        # The soft stage is ambient framing; only this label hosts the preview.
        self.preview_label = self._label(self.stage, "", size=20, wrap=300)
        self.preview_label.grid(row=2, column=0, sticky="nsew", pady=12)
        self.status_label = self._label(self.stage, "", color=_MUTED, wrap=320)
        self.status_label.grid(row=3, column=0, pady=(12, 16))
        actions = tk.Frame(self.stage, bg=_STAGE)
        actions.grid(row=4, column=0, pady=(0, 8))
        self.primary_button = tk.Button(actions, command=self._primary_action, bg=_ACCENT, fg="white",
                                        activebackground=_INK, activeforeground="white", relief="flat",
                                        padx=18, pady=12, font=("Segoe UI", 11, "bold"), cursor="hand2")
        self.primary_button.grid(row=0, column=0, padx=(0, 8))
        self.hide_button = tk.Button(actions, text="Hide", command=self.hide_selected, bg=_STAGE,
                                     fg=_INK, relief="flat", padx=10, pady=12, font=("Segoe UI", 11))
        self.hide_button.grid(row=0, column=1)
        self.overflow_button = tk.Menubutton(actions, text="More ▾", bg=_STAGE, fg=_INK,
                                            relief="flat", padx=10, pady=12, font=("Segoe UI", 10))
        self.overflow_button.grid(row=0, column=2)
        self.overflow_menu = tk.Menu(self.overflow_button, tearoff=False)
        self.overflow_menu.add_command(label="Stop companion", command=self.stop_selected)
        self.overflow_menu.add_command(label="Advanced details", command=self._show_details)
        self.overflow_menu.add_command(label="Open pack folder", command=self._open_pack_folder)
        self.overflow_button.configure(menu=self.overflow_menu)

        self.context = tk.Frame(self.content, bg=_PANEL, padx=20, pady=24)
        self.context.grid(row=1, column=2, sticky="nsew", padx=(16, 0))
        self._label(self.context, "Together, at a glance", size=13, bold=True, wrap=185).grid(row=0, column=0, sticky="w")
        self._label(self.context, "RIGHT NOW", size=9, color=_MUTED).grid(row=1, column=0, sticky="w", pady=(28, 8))
        self.activity_label = self._label(self.context, "", wrap=185)
        self.activity_label.grid(row=2, column=0, sticky="w")
        self._label(self.context, "LAST ACTIVITY", size=9, color=_MUTED).grid(row=3, column=0, sticky="w", pady=(28, 8))
        self.last_activity_label = self._label(self.context, "", wrap=185)
        self.last_activity_label.grid(row=4, column=0, sticky="w")
        self._label(self.context, "A LITTLE ABOUT THEM", size=9, color=_MUTED).grid(row=5, column=0, sticky="w", pady=(28, 8))
        self.personality_label = self._label(
            self.context, "A quiet desktop companion to share your day. Make a little room for a familiar face.", wrap=185)
        self.personality_label.grid(row=6, column=0, sticky="w")

    @staticmethod
    def _label(parent, text, *, size=11, bold=False, color=_INK, wrap=0):
        return tk.Label(parent, text=text, bg=parent["bg"], fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"),
                        justify="left", wraplength=wrap)

    def _build_cards(self):
        for card in self.collection_cards.values():
            card.destroy()
        self.collection_cards.clear()
        for index, record in enumerate(self.companions.values()):
            image = self._load_preview(self._pack(record), 42)
            card = tk.Button(self.cards_frame, text=record.name, image=image or "", compound="left",
                             anchor="w", justify="left", wraplength=125, bg=_PANEL, fg=_INK,
                             activebackground=_STAGE, relief="flat", padx=8, pady=12,
                             font=("Segoe UI", 10), command=lambda cid=record.companion_id: self.select(cid))
            card.image = image
            card.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            self.collection_cards[record.companion_id] = card

    def _pack(self, record: CompanionRecord | None) -> PackRecord | None:
        return self._packs_by_root.get(record.pack_root.resolve()) if record else None

    def _load_preview(self, pack: PackRecord | None, size: int):
        if pack is None or pack.error or pack.preview is None:
            return None
        try:
            image = tk.PhotoImage(master=self.root, file=str(pack.preview))
            scale = max(1, math.ceil(max(image.width(), image.height()) / size))
            return image.subsample(scale, scale) if scale > 1 else image
        except (tk.TclError, OSError):
            return None

    def select(self, companion_id: str | None):
        self.selected_id = companion_id if companion_id in self.companions else None
        record = self.companions.get(self.selected_id)
        self._preview_image = self._load_preview(self._pack(record), 300)
        self.preview_label.configure(image=self._preview_image or "",
                                     text="" if self._preview_image else record.name if record else "Your next little companion")
        self.name_label.configure(text=record.name if record else "Make yourself at home")
        self.refresh_status()

    def refresh_status(self):
        """Render current state without scheduling extra callbacks or reading disk."""
        if self._closed:
            return
        for cid, card in self.collection_cards.items():
            record = self.companions[cid]
            pack = self._pack(record)
            state = _STATUS[self.processes.status(record)] if pack and not pack.error else "Pack needs attention"
            card.configure(text=f"{record.name}\n{state}", bg=_STAGE if cid == self.selected_id else _PANEL)
        record = self.companions.get(self.selected_id)
        pack = self._pack(record)
        valid = record is not None and pack is not None and not pack.error
        status = self.processes.status(record) if record else None
        running = status in (ProcessStatus.RUNNING, ProcessStatus.HIDDEN)
        self.primary_action_text = "Show companion" if running else "Start companion"
        text = _STATUS[status] if record else "Your collection is waiting for its first companion."
        if record and not valid:
            text = "This companion’s pack needs attention. See Advanced details."
        if record and record.companion_id in self._errors:
            text = self._errors[record.companion_id][0]
        if self._busy and self._busy[0] == self.selected_id:
            self.primary_action_text = _PROGRESS[self._busy[1]]
            text = self.primary_action_text
        enabled = bool(valid and self._busy is None)
        self.primary_button.configure(text=self.primary_action_text, state="normal" if enabled else "disabled")
        self.hide_button.configure(state="normal" if enabled and status == ProcessStatus.RUNNING else "disabled")
        self.overflow_menu.entryconfigure(0, state="normal" if enabled and status in (
            ProcessStatus.RUNNING, ProcessStatus.HIDDEN, ProcessStatus.EXITED) else "disabled")
        self.overflow_menu.entryconfigure(1, state="normal" if record else "disabled")
        self.overflow_menu.entryconfigure(2, state="normal" if pack else "disabled")
        self.overflow_button.configure(state="normal" if record else "disabled")
        self.status_label.configure(text=text)
        self.activity_label.configure(text=text if record else "Choose a companion from your collection.")
        self.last_activity_label.configure(text=self._last_activity.get(self.selected_id, "No activity in this session yet."))

    def _primary_action(self):
        record = self.companions.get(self.selected_id)
        if record and self.processes.status(record) in (ProcessStatus.RUNNING, ProcessStatus.HIDDEN):
            self.show_selected()
        else:
            self.start_selected()

    def start_selected(self):
        self._begin_action("start", (ProcessStatus.STOPPED, ProcessStatus.EXITED, ProcessStatus.UNMANAGED))

    def show_selected(self):
        self._begin_action("show", (ProcessStatus.RUNNING, ProcessStatus.HIDDEN))

    def hide_selected(self):
        self._begin_action("hide", (ProcessStatus.RUNNING,))

    def stop_selected(self):
        self._begin_action("stop", (ProcessStatus.RUNNING, ProcessStatus.HIDDEN, ProcessStatus.EXITED))

    def _begin_action(self, action: str, allowed: tuple[ProcessStatus, ...]):
        record = self.companions.get(self.selected_id)
        pack = self._pack(record)
        if (self._closed or self._busy or record is None or pack is None or pack.error
                or self.processes.status(record) not in allowed):
            return
        self._busy = (record.companion_id, action)
        self._errors.pop(record.companion_id, None)
        self.refresh_status()

        def perform():
            error = None
            try:
                getattr(self.processes, action)(record)
            except Exception as exc:
                error = str(exc)
            self._results.put((record.companion_id, action, error))

        try:
            Thread(target=perform, daemon=True).start()
        except RuntimeError as exc:
            self._results.put((record.companion_id, action, str(exc)))

    def _schedule_refresh(self):
        if not self._closed and self._refresh_id is None:
            self._refresh_id = self.root.after(500, self._tick)

    def _tick(self):
        self._refresh_id = None
        if self._closed:
            return
        while True:
            try:
                cid, action, error = self._results.get_nowait()
            except Empty:
                break
            self._busy = None
            if error is not None:
                self._errors[cid] = (f"We couldn’t {action} your companion. Try again or see Advanced details.", error)
            else:
                self._last_activity[cid] = _DONE[action] + " · this session"
        self.refresh_status()
        self._schedule_refresh()

    def _show_details(self):
        record = self.companions.get(self.selected_id)
        if record is None:
            return
        pack = self._pack(record)
        details = [record.name, f"Pack folder: {record.pack_root}", f"Companion data: {record.runtime_root}",
                   f"Session status: {self.processes.status(record).value}"]
        if pack is None:
            details.append("This pack was not found in the current local catalog.")
        elif pack.error:
            details.append(f"Pack problem: {pack.error}")
        if record.companion_id in self._errors:
            details.append(f"Last error: {self._errors[record.companion_id][1]}")
        messagebox.showinfo("Advanced details", "\n\n".join(details), parent=self.root)

    def _open_pack_folder(self):
        record = self.companions.get(self.selected_id)
        if record is None or self._pack(record) is None:
            return
        try:
            os.startfile(str(record.pack_root))
        except OSError as exc:
            self._errors[record.companion_id] = ("We couldn’t open the pack folder. See Advanced details.", str(exc))
            self.refresh_status()

    def _on_destroy(self, event):
        if event.widget is self.root:
            self._closed = True
            if self._refresh_id is not None:
                self.root.after_cancel(self._refresh_id)
                self._refresh_id = None
