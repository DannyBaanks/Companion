"""Validation for renderer-facing mascot request documents."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from .protocol import STATES


class RenderRequestError(ValueError):
    """Raised when a render request does not match the supported contract."""


def _non_empty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RenderRequestError(f"{field} must be a non-empty string")


def validate_render_request(data: object) -> dict[str, object]:
    """Validate and return a deep-copied render request.

    Renderer-specific fields are intentionally left untouched. Companion only
    validates the fields in its small public contract.
    """
    if not isinstance(data, dict):
        raise RenderRequestError("request must be a JSON object")

    _non_empty_string(data.get("name"), "name")
    _non_empty_string(data.get("style"), "style")

    if "palette" in data:
        palette = data["palette"]
        if not isinstance(palette, list) or not palette:
            raise RenderRequestError("palette must be a non-empty list")
        for index, color in enumerate(palette):
            if not isinstance(color, str) or not color.strip():
                raise RenderRequestError(f"palette[{index}] must be a non-empty string")

    if "states" in data:
        states = data["states"]
        if not isinstance(states, list):
            raise RenderRequestError("states must be a list")
        known_states = ", ".join(sorted(STATES))
        for index, state in enumerate(states):
            if not isinstance(state, str) or state not in STATES:
                raise RenderRequestError(f"states[{index}] must be one of: {known_states}")

    if "output" in data:
        output = data["output"]
        if not isinstance(output, dict):
            raise RenderRequestError("output must be an object")
        if "cell_size" in output:
            cell_size = output["cell_size"]
            if not isinstance(cell_size, list) or len(cell_size) != 2:
                raise RenderRequestError("output.cell_size must contain exactly two values")
            if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in cell_size):
                raise RenderRequestError("output.cell_size values must be positive integers")

    return deepcopy(data)


def load_render_request(path: Path) -> dict[str, object]:
    """Load, parse, and validate a JSON render request from *path*."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RenderRequestError(f"could not read {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RenderRequestError(f"invalid JSON in {path}: {exc.msg}") from exc
    return validate_render_request(data)
