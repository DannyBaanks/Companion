"""Companion Hub window — collection, lifecycle, and first-run flow."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

from .hub import HubState, HubStore, HubController
from .tokens import Theme, get_theme


_STATUS_COLORS = {
    "running": "success",
    "hidden": "waiting",
    "stopped": "error",
}


class HubWindow:
    """Top-level Hub window managing multiple companions."""

    def __init__(self, store: HubStore, *, theme: Theme | None = None):
        self.store = store
        self.controller = HubController(store)
        self.theme = theme or get_theme("dark")
        self.state = store.load()

        self.root = tk.Tk()
        self.root.title("Companion Hub")
        self.root.geometry("520x420")
        self.root.resizable(True, True)
        self.root.configure(bg=self.theme.bg_menu)

        self._build_ui()

    def _build_ui(self) -> None:
        t = self.theme

        # Header
        header = tk.Frame(self.root, bg=t.bg_menu, padx=12, pady=8)
        header.pack(fill="x")
        tk.Label(
            header, text="Companion Hub",
            bg=t.bg_menu, fg=t.fg_accent,
            font=(t.typography.font_family, t.typography.size_title, "bold"),
        ).pack(side="left")

        # First-run banner
        if self.state.first_run:
            banner = tk.Frame(self.root, bg=t.bg_bubble, padx=12, pady=10)
            banner.pack(fill="x", padx=8, pady=(0, 6))
            tk.Label(
                banner,
                text="Welcome! Create your first companion to get started.",
                bg=t.bg_bubble, fg=t.fg_primary,
                font=(t.typography.font_family, t.typography.size_body),
                wraplength=460, justify="left",
            ).pack(side="left", expand=True, fill="x")

        # Companion list
        self.list_frame = tk.Frame(self.root, bg=t.bg_menu)
        self.list_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self._refresh_list()

        # Bottom bar
        bottom = tk.Frame(self.root, bg=t.bg_menu, padx=12, pady=8)
        bottom.pack(fill="x")
        for text, cmd in (
            ("New Companion", self._on_new),
            ("Rescan Packs", self._on_rescan),
        ):
            tk.Button(
                bottom, text=text, bg=t.bg_menu_hover, fg=t.fg_primary,
                command=cmd, relief="flat", padx=10, pady=4,
            ).pack(side="left", padx=(0, 6))

    def _refresh_list(self) -> None:
        t = self.theme
        for w in self.list_frame.winfo_children():
            w.destroy()

        if not self.state.companions:
            tk.Label(
                self.list_frame, text="No companions yet.",
                bg=t.bg_menu, fg=t.fg_secondary,
                font=(t.typography.font_family, t.typography.size_body),
            ).pack(pady=20)
            return

        for entry in self.state.companions:
            row = tk.Frame(self.list_frame, bg=t.bg_menu, padx=4, pady=4)
            row.pack(fill="x", pady=2)

            # Status dot
            state_name = _STATUS_COLORS.get(entry.status, "waiting")
            dot_color = t.states[state_name].accent
            tk.Label(
                row, text="\u25cf", bg=t.bg_menu, fg=dot_color,
                font=(t.typography.font_family, t.typography.size_label),
            ).pack(side="left", padx=(0, 6))

            # Name + info
            info = entry.name
            if entry.pack_name:
                info += f"  ({entry.pack_name})"
            info += f"  [{entry.status}]"
            tk.Label(
                row, text=info, bg=t.bg_menu, fg=t.fg_primary,
                font=(t.typography.font_family, t.typography.size_body),
            ).pack(side="left", expand=True, fill="x")

            # Action buttons
            for label, cmd in self._buttons_for(entry):
                tk.Button(
                    row, text=label, bg=t.bg_menu_disabled, fg=t.fg_secondary,
                    command=cmd, relief="flat", padx=6, pady=2,
                    font=(t.typography.font_family, t.typography.size_name),
                ).pack(side="right", padx=2)

    def _buttons_for(self, entry):
        """Return (label, command) pairs for a companion row."""
        if entry.status == "stopped":
            return [("Start", lambda e=entry: self._start(e))]
        elif entry.status == "starting":
            return [("Starting…", lambda: None)]
        elif entry.status == "running":
            return [
                ("Hide", lambda e=entry: self._hide(e)),
                ("Stop", lambda e=entry: self._stop(e)),
            ]
        elif entry.status == "hidden":
            return [
                ("Show", lambda e=entry: self._show_companion(e)),
                ("Stop", lambda e=entry: self._stop(e)),
            ]
        else:  # failed
            return [("Retry", lambda e=entry: self._start(e))]

    # ── Actions ─────────────────────────────────────────────────────────

    def _on_new(self) -> None:
        self._show_create_dialog()

    def _on_rescan(self) -> None:
        self.state = self.store.load()
        self._refresh_list()

    def _start(self, entry) -> None:
        self.controller.start(entry)
        self.state = self.store.load()
        self._refresh_list()

    def _hide(self, entry) -> None:
        self.controller.hide(entry)
        self.state = self.store.load()
        self._refresh_list()

    def _show_companion(self, entry) -> None:
        self.controller.show(entry)
        self.state = self.store.load()
        self._refresh_list()

    def _stop(self, entry) -> None:
        self.controller.stop(entry)
        self.state = self.store.load()
        self._refresh_list()

    def _show_create_dialog(self) -> None:
        t = self.theme
        dialog = tk.Toplevel(self.root)
        dialog.title("New Companion")
        dialog.geometry("340x160")
        dialog.resizable(False, False)
        dialog.configure(bg=t.bg_menu)
        dialog.attributes("-topmost", True)

        frame = tk.Frame(dialog, bg=t.bg_menu, padx=16, pady=12)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame, text="Name:", bg=t.bg_menu, fg=t.fg_primary,
            font=(t.typography.font_family, t.typography.size_body),
        ).grid(row=0, column=0, sticky="w", pady=4)
        name_var = tk.StringVar(value="Companion")
        name_entry = tk.Entry(frame, textvariable=name_var, width=24,
                              bg=t.bg_bubble, fg=t.fg_primary,
                              insertbackground=t.fg_primary)
        name_entry.grid(row=0, column=1, pady=4, padx=(8, 0))

        def create():
            name = name_var.get().strip() or "Companion"
            self.store.create_companion(name)
            self.state = self.store.load()
            self._refresh_list()
            dialog.destroy()

        tk.Button(
            frame, text="Create", bg=t.fg_accent, fg="#000000",
            command=create, relief="flat", padx=12, pady=4,
        ).grid(row=1, column=0, columnspan=2, pady=10)

        name_entry.focus_set()
        dialog.bind("<Return>", lambda _: create())

    def show(self) -> None:
        self.root.mainloop()


def launch_hub(root: Path | None = None, *, theme: Theme | None = None) -> None:
    """Convenience launcher for the Hub window."""
    if root is None:
        root = Path(".companion")
    store = HubStore(root)
    HubWindow(store, theme=theme).show()
