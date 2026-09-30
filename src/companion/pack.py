"""Declarative companion asset packs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .protocol import STATES

PACK_ANIMATIONS = STATES | {
    "running-right", "running-left", "drag",
}


class PackError(ValueError):
    """Raised when a pack manifest is invalid."""


@dataclass(frozen=True)
class AssetPack:
    root: Path
    pack_id: str
    name: str
    animations: dict[str, str]
    sprite_sheet: str | None = None
    sprite_cell_width: int = 192
    sprite_cell_height: int = 208
    sprite_columns: int = 8
    sprite_floor_offset: int = 203
    drag_sprite_sheet: str | None = None
    drag_cell_width: int = 192
    drag_cell_height: int = 336
    drag_columns: int = 8
    drag_floor_offset: int = 276

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
            if state not in PACK_ANIMATIONS:
                raise PackError(f"unsupported animation state: {state}")
            if not isinstance(filename, str) or not filename.strip():
                raise PackError(f"asset for {state} must be a non-empty string")
            path = (root / filename).resolve()
            if root.resolve() not in path.parents:
                raise PackError(f"asset escapes pack directory: {filename}")
            if not path.is_file():
                raise PackError(f"asset not found for {state}: {filename}")
            normalized[state] = filename
        sprite_sheet = None
        cell_width, cell_height, columns, sprite_floor_offset = 192, 208, 8, 203
        sprite = manifest.get("spriteSheet")
        if sprite is not None:
            if not isinstance(sprite, dict):
                raise PackError("manifest spriteSheet must be an object")
            filename = sprite.get("path")
            if not isinstance(filename, str) or not filename.strip():
                raise PackError("spriteSheet requires a non-empty path")
            sprite_path = (root / filename).resolve()
            if root.resolve() not in sprite_path.parents:
                raise PackError(f"sprite sheet escapes pack directory: {filename}")
            if not sprite_path.is_file():
                raise PackError(f"sprite sheet not found: {filename}")
            dimensions = (sprite.get("cellWidth", 192), sprite.get("cellHeight", 208), sprite.get("columns", 8))
            if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in dimensions):
                raise PackError("spriteSheet cellWidth, cellHeight and columns must be positive integers")
            floor_offset = sprite.get("floorOffset", dimensions[1] - 5)
            if isinstance(floor_offset, bool) or not isinstance(floor_offset, int) or not 1 <= floor_offset <= dimensions[1]:
                raise PackError("spriteSheet floorOffset must be a positive pixel offset inside the cell")
            sprite_sheet = filename
            cell_width, cell_height, columns = dimensions
            sprite_floor_offset = floor_offset
        drag_sheet = None
        drag_width, drag_height, drag_columns, drag_floor_offset = 192, 336, 8, 276
        drag_animation = manifest.get("dragAnimation")
        if drag_animation is not None:
            if not isinstance(drag_animation, dict):
                raise PackError("manifest dragAnimation must be an object")
            filename = drag_animation.get("path")
            if not isinstance(filename, str) or not filename.strip():
                raise PackError("dragAnimation requires a non-empty path")
            drag_path = (root / filename).resolve()
            if root.resolve() not in drag_path.parents:
                raise PackError(f"drag animation sheet escapes pack directory: {filename}")
            if not drag_path.is_file():
                raise PackError(f"drag animation sheet not found: {filename}")
            dimensions = (
                drag_animation.get("cellWidth", 192),
                drag_animation.get("cellHeight", 336),
                drag_animation.get("columns", 8),
            )
            if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in dimensions):
                raise PackError("dragAnimation cellWidth, cellHeight and columns must be positive integers")
            floor_offset = drag_animation.get("floorOffset", dimensions[1] - 60)
            if isinstance(floor_offset, bool) or not isinstance(floor_offset, int) or not 1 <= floor_offset <= dimensions[1]:
                raise PackError("dragAnimation floorOffset must be a positive pixel offset inside the cell")
            drag_sheet = filename
            drag_width, drag_height, drag_columns = dimensions
            drag_floor_offset = floor_offset
        return cls(
            root.resolve(), pack_id, name, normalized,
            sprite_sheet, cell_width, cell_height, columns, sprite_floor_offset,
            drag_sheet, drag_width, drag_height, drag_columns, drag_floor_offset,
        )

    def animation_for(self, *, state: str, mood: str | None = None, action: str | None = None) -> Path:
        filename = (
            self.animations.get(action or "")
            or self.animations.get(mood or "")
            or self.animations.get(state)
            or self.animations["idle"]
        )
        return self.root / filename
