"""Data-directory and config discovery. Local only, no network."""

from __future__ import annotations

import os
from pathlib import Path
import sys


APP_NAME = "Companion"


def default_data_dir() -> Path:
    """Platform data dir: LOCALAPPDATA on Windows, XDG/share elsewhere."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "ISyCoCompanion"
        return Path.home() / "AppData" / "Local" / "ISyCoCompanion"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ISyCoCompanion"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "isyco-companion"
    return Path.home() / ".local" / "share" / "isyco-companion"


def resolve_root(explicit: str | None) -> Path:
    """Explicit --root wins, then COMPANION_ROOT env, then cwd .companion."""
    if explicit is not None and explicit != ".companion":
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("COMPANION_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    return Path(".companion").expanduser().resolve()


def discover_config(root: Path) -> Path | None:
    for name in ("companion.toml", "companion.json"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def platform_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"
