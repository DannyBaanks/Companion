"""Shared design tokens and presentation themes for the Companion stage.

Tokens are plain data — no tkinter imports. The window module reads them
to style every widget consistently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Color primitives ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Color:
    """Hex RGB color with optional alpha (0-1)."""

    hex: str  # "#rrggbb"
    alpha: float = 1.0

    @property
    def rgb(self) -> tuple[int, int, int]:
        h = self.hex.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def with_alpha(self, alpha: float) -> "Color":
        return Color(self.hex, alpha)


# ── Typography tokens ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Typography:
    font_family: str = "Segoe UI"
    size_name: int = 9
    size_label: int = 10
    size_body: int = 11
    size_title: int = 13
    weight_normal: str = "normal"
    weight_bold: str = "bold"


# ── Spacing / radii / motion ────────────────────────────────────────────────

@dataclass(frozen=True)
class Spacing:
    xxs: int = 2
    xs: int = 4
    sm: int = 6
    md: int = 8
    lg: int = 12
    xl: int = 16
    xxl: int = 24


@dataclass(frozen=True)
class Radii:
    none: int = 0
    sm: int = 4
    md: int = 8
    lg: int = 12
    pill: int = 999


@dataclass(frozen=True)
class Shadows:
    """Drop-shadow specs as (dx, dy, blur, color)."""
    sm: tuple[int, int, int, str] = (0, 1, 3, "#00000033")
    md: tuple[int, int, int, str] = (0, 2, 8, "#00000044")
    lg: tuple[int, int, int, str] = (0, 4, 16, "#00000055")
    glow_idle: tuple[int, int, int, str] = (0, 0, 12, "#6ee7b788")
    glow_thinking: tuple[int, int, int, str] = (0, 0, 16, "#93c5fd88")
    glow_working: tuple[int, int, int, str] = (0, 0, 14, "#fcd34d88")
    glow_success: tuple[int, int, int, str] = (0, 0, 18, "#34d399aa")
    glow_error: tuple[int, int, int, str] = (0, 0, 18, "#f87171aa")
    glow_waiting: tuple[int, int, int, str] = (0, 0, 14, "#a78bfa88")


@dataclass(frozen=True)
class Motion:
    """Duration in milliseconds for standard transitions."""
    fast: int = 120
    normal: int = 200
    slow: int = 350
    poll_ms: int = 100  # mainloop refresh interval


# ── Per-state visual spec ────────────────────────────────────────────────────

@dataclass(frozen=True)
class StateVisual:
    """What a semantic state looks like: accent color, glow, icon label."""
    accent: str           # hex for borders / text highlights
    glow: tuple[int, int, int, str] = (0, 0, 0, "#00000000")
    icon: str = ""        # short label shown as accessible fallback
    # icon_font is NOT a tkinter font — just a family hint for the label
    icon_font: str = "Segoe UI Emoji"


# ── Theme ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Theme:
    """Complete visual theme: every widget color in one place."""

    name: str

    # ── Background layers ────────────────────────────────────────────────
    bg_stage: str         # transparent magenta / stage background
    bg_bubble: str        # message bubble background
    bg_menu: str          # context menu background
    bg_menu_hover: str    # menu item hover
    bg_menu_disabled: str # disabled menu item

    # ── Text ─────────────────────────────────────────────────────────────
    fg_primary: str       # main text
    fg_secondary: str     # secondary / dimmed text
    fg_bubble: str        # bubble text
    fg_accent: str        # highlighted text / state label

    # ── Borders / outlines ──────────────────────────────────────────────
    border_bubble: str    # bubble border
    border_focus: str     # keyboard focus ring

    # ── State accents ────────────────────────────────────────────────────
    states: dict[str, StateVisual] = field(default_factory=dict)

    # ── Shared tokens ────────────────────────────────────────────────────
    typography: Typography = field(default_factory=Typography)
    spacing: Spacing = field(default_factory=Spacing)
    radii: Radii = field(default_factory=Radii)
    shadows: Shadows = field(default_factory=Shadows)
    motion: Motion = field(default_factory=Motion)


# ── Built-in themes ──────────────────────────────────────────────────────────

def _state_map(**overrides: str) -> dict[str, StateVisual]:
    """Return the six-state map, merging per-theme accent overrides."""
    base = {
        "idle":     StateVisual(accent="#6ee7b7", glow=(0, 0, 12, "#6ee7b788"), icon="●"),
        "thinking": StateVisual(accent="#93c5fd", glow=(0, 0, 16, "#93c5fd88"), icon="◐"),
        "working":  StateVisual(accent="#fcd34d", glow=(0, 0, 14, "#fcd34d88"), icon="◑"),
        "success":  StateVisual(accent="#34d399", glow=(0, 0, 18, "#34d399aa"), icon="✔"),
        "error":    StateVisual(accent="#f87171", glow=(0, 0, 18, "#f87171aa"), icon="✖"),
        "waiting":  StateVisual(accent="#a78bfa", glow=(0, 0, 14, "#a78bfa88"), icon="◌"),
    }
    for key, accent in overrides.items():
        if key in base:
            old = base[key]
            base[key] = StateVisual(accent=accent, glow=old.glow, icon=old.icon)
    return base


DARK = Theme(
    name="dark",
    bg_stage="magenta",            # transparent on Windows
    bg_bubble="#1e2430",
    bg_menu="#1a1f2b",
    bg_menu_hover="#252d3a",
    bg_menu_disabled="#14181f",
    fg_primary="#e2e8f0",
    fg_secondary="#94a3b8",
    fg_bubble="#e2e8f0",
    fg_accent="#6ee7b7",
    border_bubble="#334155",
    border_focus="#6ee7b7",
    states=_state_map(),
)

LIGHT = Theme(
    name="light",
    bg_stage="magenta",
    bg_bubble="#ffffff",
    bg_menu="#f8fafc",
    bg_menu_hover="#e2e8f0",
    bg_menu_disabled="#f1f5f9",
    fg_primary="#1e293b",
    fg_secondary="#64748b",
    fg_bubble="#1e293b",
    fg_accent="#059669",
    border_bubble="#cbd5e1",
    border_focus="#059669",
    states=_state_map(),
)

SOFT_NEON = Theme(
    name="soft-neon",
    bg_stage="magenta",
    # Tk only accepts #rrggbb.  Keep these opaque; alpha belongs to the
    # window/canvas layer, not to widget color strings.
    bg_bubble="#0f172a",
    bg_menu="#0f172a",
    bg_menu_hover="#1e293b",
    bg_menu_disabled="#162033",
    fg_primary="#f0fdfa",
    fg_secondary="#5eead4",
    fg_bubble="#f0fdfa",
    fg_accent="#22d3ee",
    border_bubble="#164e63",
    border_focus="#22d3ee",
    states=_state_map(),
)


def get_theme(name: str) -> Theme:
    """Return a built-in theme by name, falling back to DARK."""
    themes = {"dark": DARK, "light": LIGHT, "soft-neon": SOFT_NEON}
    return themes.get(name, DARK)
