"""Declarative companion asset packs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .protocol import STATES


class PackError(ValueError):
    """Raised when a pack manifest is invalid."""


@dataclass(frozen=True)
class AssetPack:
    root: Path
    pack_id: str
    name: str
    animations: dict[str, str]

    @classmethod
    def load(cls, root: Path) -> "AssetPack":
        manifest_path = root / "manifest.json"
        if not manifest_path.exists():
            raise PackError(f"manifest not found: {manifest_path}")
        try:
            manifest: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PackError(f"invalid JSON manifest: {manifest_path}") from exc
        if not isinstance(manifest, dict):
            raise PackError("manifest must be a JSON object")
        pack_id = manifest.get("id")
        name = manifest.get("name", pack_id)
        animations = manifest.get("animations")
        if not isinstance(pack_id, str) or not pack_id.strip():
            raise PackError("manifest requires a non-empty id")
        if not isinstance(name, str) or not name.strip():
            raise PackError("manifest name must be a non-empty string")
        if not isinstance(animations, dict) or "idle" not in animations:
            raise PackError("manifest animations requires an idle asset")
        normalized: dict[str, str] = {}
        for state, filename in animations.items():
            if state not in STATES:
                raise PackError(f"unsupported animation state: {state}")
            if not isinstance(filename, str) or not filename.strip():
                raise PackError(f"asset for {state} must be a non-empty string")
            path = (root / filename).resolve()
            if root.resolve() not in path.parents:
                raise PackError(f"asset escapes pack directory: {filename}")
            if not path.is_file():
                raise PackError(f"asset not found for {state}: {filename}")
            normalized[state] = filename
        return cls(root.resolve(), pack_id, name, normalized)

    def animation_for(self, *, state: str, mood: str | None = None) -> Path:
        filename = self.animations.get(mood or "") or self.animations.get(state) or self.animations["idle"]
        return self.root / filename
