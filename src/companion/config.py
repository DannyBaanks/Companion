"""Optional JSON/TOML configuration for a desktop companion."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when a configuration file cannot be loaded."""


@dataclass(frozen=True)
class CompanionConfig:
    name: str = "Companion"
    pack: Path | None = None
    position: str = "bottom-right"
    topmost: bool = True
    opacity: float = 1.0


def load_config(path: Path) -> CompanionConfig:
    try:
        if path.suffix.lower() == ".toml":
            import tomllib  # type: ignore[import-not-found]

            data: Any = tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"could not load config: {path}") from exc
    if not isinstance(data, dict):
        raise ConfigError("config must be an object")
    values = data.get("companion", data)
    window = data.get("window", {})
    if not isinstance(values, dict) or not isinstance(window, dict):
        raise ConfigError("companion and window config sections must be objects")
    pack = values.get("pack")
    return CompanionConfig(
        name=str(values.get("name", "Companion")),
        pack=(path.parent / pack).resolve() if isinstance(pack, str) else None,
        position=str(window.get("position", "bottom-right")),
        topmost=bool(window.get("topmost", True)),
        opacity=float(window.get("opacity", 1.0)),
    )
