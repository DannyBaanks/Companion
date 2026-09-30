"""Versioned, data-only character and animation recipe validation."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any


CHARACTER_SCHEMA = "companion-character-v1"
ANIMATION_SCHEMA = "companion-animation-v1"
PARTS_SCHEMA = "companion-parts-v1"
MAX_DIMENSION = 1024
MAX_NODES = 20_000
MAX_LAYERS = 128
MAX_FRAMES = 300
MAX_RENDERED_PIXELS = 64_000_000


class ArtError(ValueError):
    """Raised when an art recipe is invalid or cannot be rendered."""


@dataclass(frozen=True)
class CharacterDocument:
    path: Path
    data: dict[str, Any]
    width: int
    height: int
    anchor: tuple[float, float]


@dataclass(frozen=True)
class AnimationDocument:
    path: Path
    data: dict[str, Any]
    character: CharacterDocument
    frame_count: int


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ArtError(f"{label} must be an object")
    return value


def _keys(value: dict[str, Any], required: set[str], optional: set[str], label: str) -> None:
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing:
        raise ArtError(f"{label} missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ArtError(f"{label} has unsupported fields: {', '.join(sorted(extra))}")


def _number(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ArtError(f"{label} must be a number")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ArtError(f"{label} must be between {low:g} and {high:g}")
    return value


def _integer(value: Any, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ArtError(f"{label} must be an integer between {low} and {high}")
    return value


def _pair(value: Any, label: str, limit_x: float, limit_y: float) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ArtError(f"{label} must be [x, y]")
    return (
        _number(value[0], f"{label}.x", -limit_x, limit_x),
        _number(value[1], f"{label}.y", -limit_y, limit_y),
    )


def _color(value: Any, palette: dict[str, Any], label: str) -> None:
    if not isinstance(value, str):
        raise ArtError(f"{label} must be a palette name or #RRGGBB color")
    if value in palette:
        return
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return
        except ValueError:
            pass
    raise ArtError(f"{label} references an unknown color: {value}")


def _bounds(value: Any, width: int, height: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ArtError(f"{label} must be [x, y, width, height]")
    x, y, w, h = (
        _number(item, f"{label}[{i}]", -MAX_DIMENSION, MAX_DIMENSION * 2)
        for i, item in enumerate(value)
    )
    if w <= 0 or h <= 0:
        raise ArtError(f"{label} width and height must be positive")
    if x < -width or y < -height or x + w > width * 2 or y + h > height * 2:
        raise ArtError(f"{label} extends too far outside the canvas")
    return [x, y, w, h]


def _resolve_asset(root: Path, name: Any, label: str) -> Path:
    if not isinstance(name, str) or not name.strip():
        raise ArtError(f"{label} requires a relative asset path")
    path = (root / name).resolve()
    if root.resolve() not in path.parents:
        raise ArtError(f"{label} asset escapes its recipe directory: {name}")
    if not path.is_file():
        raise ArtError(f"{label} asset not found: {name}")
    if path.suffix.lower() != ".png":
        raise ArtError(f"{label} raster assets must be PNG files")
    return path


def _validate_shape(
    shape: Any,
    palette: dict[str, Any],
    root: Path,
    width: int,
    height: int,
    label: str,
    *,
    parts: dict[str, Any] | None = None,
    part_tokens: set[str] | None = None,
) -> int:
    shape = _object(shape, label)
    kind = shape.get("type")
    base_optional = {"fill", "stroke", "strokeWidth", "opacity"}
    if kind in {"rect", "ellipse"}:
        _keys(shape, {"type", "bounds"}, base_optional, label)
        _bounds(shape["bounds"], width, height, f"{label}.bounds")
    elif kind == "polygon":
        _keys(shape, {"type", "points"}, base_optional, label)
        points = shape["points"]
        if not isinstance(points, list) or not 3 <= len(points) <= 2048:
            raise ArtError(f"{label}.points must contain 3 to 2048 points")
        for i, point in enumerate(points):
            _pair(point, f"{label}.points[{i}]", MAX_DIMENSION * 2, MAX_DIMENSION * 2)
    elif kind == "path":
        _keys(shape, {"type", "commands"}, base_optional, label)
        commands = shape["commands"]
        if not isinstance(commands, list) or not 1 <= len(commands) <= 8192:
            raise ArtError(f"{label}.commands must contain 1 to 8192 commands")
        has_move = False
        active_subpath = False
        for index, command in enumerate(commands):
            if not isinstance(command, list) or not command or not isinstance(command[0], str):
                raise ArtError(f"{label}.commands[{index}] is malformed")
            op = command[0]
            expected = {"M": 3, "L": 3, "C": 7, "Z": 1}.get(op)
            if expected is None or len(command) != expected:
                raise ArtError(f"{label}.commands[{index}] must use M, L, C, or Z coordinates")
            if op == "M":
                has_move = True
                active_subpath = True
            elif not active_subpath:
                raise ArtError(f"{label}.commands[{index}] needs an active path starting with M")
            if op == "Z":
                active_subpath = False
            for coordinate in command[1:]:
                _number(coordinate, f"{label}.commands[{index}] coordinate", -MAX_DIMENSION * 2, MAX_DIMENSION * 2)
        if not has_move:
            raise ArtError(f"{label}.commands must start with a move command")
    elif kind == "image":
        _keys(shape, {"type", "path", "bounds"}, {"opacity"}, label)
        _resolve_asset(root, shape["path"], label)
        _bounds(shape["bounds"], width, height, f"{label}.bounds")
    elif kind == "part":
        _keys(shape, {"type", "part", "bounds"}, {"flipX", "rotation", "colors"}, label)
        if not isinstance(shape["part"], str) or shape["part"] not in (parts or {}):
            raise ArtError(f"{label}.part references an unknown reusable part")
        _bounds(shape["bounds"], width, height, f"{label}.bounds")
        if "flipX" in shape and not isinstance(shape["flipX"], bool):
            raise ArtError(f"{label}.flipX must be boolean")
        if "rotation" in shape:
            _number(shape["rotation"], f"{label}.rotation", -3600, 3600)
        definition = (parts or {})[shape["part"]]
        allowed_tokens = set(definition.get("colors", []))
        bindings = shape.get("colors", {})
        if not isinstance(bindings, dict) or bindings.keys() - allowed_tokens:
            raise ArtError(f"{label}.colors must map declared part color slots")
        missing_tokens = allowed_tokens - bindings.keys()
        if missing_tokens:
            raise ArtError(f"{label}.colors is missing slots: {', '.join(sorted(missing_tokens))}")
        for token, color in bindings.items():
            _color(color, palette, f"{label}.colors.{token}")
    else:
        raise ArtError(f"{label}.type must be rect, ellipse, polygon, path, image, or part")

    for name in ("fill", "stroke"):
        if name in shape and shape[name] is not None:
            color = shape[name]
            if isinstance(color, str) and color.startswith("$") and part_tokens is not None:
                if color[1:] not in part_tokens:
                    raise ArtError(f"{label}.{name} references an undeclared part color slot")
            else:
                _color(color, palette, f"{label}.{name}")
    if "strokeWidth" in shape:
        _number(shape["strokeWidth"], f"{label}.strokeWidth", 0.1, 64)
    if "opacity" in shape:
        _integer(shape["opacity"], f"{label}.opacity", 0, 255)
    if kind not in {"image", "part"} and "fill" not in shape and "stroke" not in shape:
        raise ArtError(f"{label} needs fill, stroke, or both")
    return 1


def _load_part_libraries(path: Path, names: Any, palette: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(names, list) or len(names) > 32:
        raise ArtError("character.libraries must be a list of at most 32 local part libraries")
    parts: dict[str, Any] = {}
    for library_index, name in enumerate(names):
        if not isinstance(name, str) or not name.strip():
            raise ArtError(f"character.libraries[{library_index}] must be a relative path")
        library_path = (path.parent / name).resolve()
        if path.parent.resolve() not in library_path.parents or library_path.suffix.lower() != ".json":
            raise ArtError(f"character.libraries[{library_index}] must be a JSON file inside the character directory")
        if not library_path.is_file():
            raise ArtError(f"part library not found: {name}")
        try:
            library = json.loads(library_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ArtError(f"cannot read part library: {library_path}") from exc
        except json.JSONDecodeError as exc:
            raise ArtError(f"invalid JSON in part library at line {exc.lineno}") from exc
        library = _object(library, f"part library {library_path.name}")
        _keys(library, {"schema", "id", "parts"}, set(), f"part library {library_path.name}")
        if library["schema"] != PARTS_SCHEMA:
            raise ArtError(f"part library schema must be {PARTS_SCHEMA}")
        if not isinstance(library["id"], str) or not library["id"].strip():
            raise ArtError("part library id must be a non-empty string")
        definitions = _object(library["parts"], "part library parts")
        for part_id, part in definitions.items():
            if not isinstance(part_id, str) or not part_id or part_id in parts:
                raise ArtError(f"duplicate or invalid reusable part id: {part_id}")
            part = _object(part, f"part {part_id}")
            _keys(part, {"canvas", "colors", "shapes"}, set(), f"part {part_id}")
            canvas = part["canvas"]
            if not isinstance(canvas, list) or len(canvas) != 2:
                raise ArtError(f"part {part_id}.canvas must be [width, height]")
            part_width = _integer(canvas[0], f"part {part_id}.canvas.width", 1, MAX_DIMENSION)
            part_height = _integer(canvas[1], f"part {part_id}.canvas.height", 1, MAX_DIMENSION)
            tokens = part["colors"]
            if not isinstance(tokens, list) or len(tokens) > 32 or any(not isinstance(token, str) or not token for token in tokens):
                raise ArtError(f"part {part_id}.colors must be a list of color slot names")
            if len(tokens) != len(set(tokens)):
                raise ArtError(f"part {part_id}.colors contains duplicates")
            shapes = part["shapes"]
            if not isinstance(shapes, list) or not shapes:
                raise ArtError(f"part {part_id}.shapes must be a non-empty list")
            count = 0
            for shape_index, shape in enumerate(shapes):
                if isinstance(shape, dict) and shape.get("type") == "part":
                    raise ArtError(f"part {part_id} cannot contain nested part instances")
                count += _validate_shape(
                    shape, palette, library_path.parent, part_width, part_height,
                    f"part {part_id}.shapes[{shape_index}]", part_tokens=set(tokens),
                )
                if count > MAX_NODES:
                    raise ArtError(f"part {part_id} contains too many drawing nodes")
            parts[part_id] = {**part, "_source": str(library_path)}
    return parts


def load_character(path: Path) -> CharacterDocument:
    path = Path(path).expanduser().resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ArtError(f"cannot read character recipe: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ArtError(f"invalid JSON in character recipe at line {exc.lineno}") from exc
    data = _object(data, "character")
    _keys(data, {"schema", "id", "name", "canvas", "palette", "layers"}, {"libraries", "rig"}, "character")
    if data["schema"] != CHARACTER_SCHEMA:
        raise ArtError(f"character.schema must be {CHARACTER_SCHEMA}")
    for field in ("id", "name"):
        if not isinstance(data[field], str) or not data[field].strip():
            raise ArtError(f"character.{field} must be a non-empty string")
    canvas = _object(data["canvas"], "character.canvas")
    _keys(canvas, {"width", "height"}, {"anchor"}, "character.canvas")
    width = _integer(canvas["width"], "canvas.width", 1, MAX_DIMENSION)
    height = _integer(canvas["height"], "canvas.height", 1, MAX_DIMENSION)
    anchor = _pair(canvas.get("anchor", [width / 2, height - 5]), "canvas.anchor", MAX_DIMENSION, MAX_DIMENSION)
    palette = _object(data["palette"], "character.palette")
    if len(palette) > 256:
        raise ArtError("character.palette may contain at most 256 colors")
    for name, color in palette.items():
        if not isinstance(name, str) or not name:
            raise ArtError("palette keys must be non-empty strings")
        _color(color, {}, f"palette.{name}")
    parts = _load_part_libraries(path, data.get("libraries", []), palette)
    data["parts"] = parts
    layers = data["layers"]
    if not isinstance(layers, list) or not 1 <= len(layers) <= MAX_LAYERS:
        raise ArtError(f"character.layers must contain 1 to {MAX_LAYERS} layers")
    seen: set[str] = set()
    node_count = 0
    for index, raw_layer in enumerate(layers):
        label = f"layers[{index}]"
        layer = _object(raw_layer, label)
        _keys(layer, {"id", "pivot", "shapes"}, {"visible"}, label)
        layer_id = layer["id"]
        if not isinstance(layer_id, str) or not layer_id or layer_id in seen:
            raise ArtError(f"{label}.id must be unique and non-empty")
        seen.add(layer_id)
        _pair(layer["pivot"], f"{label}.pivot", MAX_DIMENSION, MAX_DIMENSION)
        if "visible" in layer and not isinstance(layer["visible"], bool):
            raise ArtError(f"{label}.visible must be boolean")
        shapes = layer["shapes"]
        if not isinstance(shapes, list):
            raise ArtError(f"{label}.shapes must be a list")
        for shape_index, shape in enumerate(shapes):
            node_count += _validate_shape(shape, palette, path.parent, width, height, f"{label}.shapes[{shape_index}]", parts=parts)
            if isinstance(shape, dict) and shape.get("type") == "part":
                node_count += len(parts[shape["part"]]["shapes"])
            if node_count > MAX_NODES:
                raise ArtError(f"character contains more than {MAX_NODES} drawing nodes")
    rig = _object(data.get("rig", {}), "character.rig")
    for role, layer_id in rig.items():
        if not isinstance(role, str) or not role.strip():
            raise ArtError("character.rig role names must be non-empty strings")
        if not isinstance(layer_id, str) or layer_id not in seen:
            raise ArtError(f"character.rig.{role} must reference an existing layer id")
    data["rig"] = rig
    return CharacterDocument(path, data, width, height, anchor)


def load_animation(path: Path) -> AnimationDocument:
    path = Path(path).expanduser().resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ArtError(f"cannot read animation recipe: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ArtError(f"invalid JSON in animation recipe at line {exc.lineno}") from exc
    data = _object(data, "animation")
    _keys(data, {"schema", "id", "character", "durationMs", "loop", "tracks"}, {"frameDurationMs", "frameColumns", "flipX"}, "animation")
    if data["schema"] != ANIMATION_SCHEMA:
        raise ArtError(f"animation.schema must be {ANIMATION_SCHEMA}")
    if not isinstance(data["id"], str) or not data["id"].strip():
        raise ArtError("animation.id must be a non-empty string")
    if not isinstance(data["loop"], bool):
        raise ArtError("animation.loop must be boolean")
    if "flipX" in data and not isinstance(data["flipX"], bool):
        raise ArtError("animation.flipX must be boolean")
    duration = _integer(data["durationMs"], "animation.durationMs", 10, 36_000)
    frame_duration = _integer(data.get("frameDurationMs", 120), "animation.frameDurationMs", 10, 1000)
    if frame_duration % 10 != 0 or duration % frame_duration != 0:
        raise ArtError("animation duration and frameDurationMs must align to GIF 10ms timing")
    frame_count = duration // frame_duration
    if frame_count > MAX_FRAMES:
        raise ArtError(f"animation may contain at most {MAX_FRAMES} frames")
    columns = _integer(data.get("frameColumns", 8), "animation.frameColumns", 1, 32)
    character_name = data["character"]
    if not isinstance(character_name, str) or not character_name.strip():
        raise ArtError("animation.character must reference a character JSON file")
    character_path = (path.parent / character_name).resolve()
    if path.parent.resolve() not in character_path.parents:
        raise ArtError("animation.character must stay inside its recipe directory")
    character = load_character(character_path)
    if character.width * character.height * frame_count > MAX_RENDERED_PIXELS:
        raise ArtError(f"animation exceeds {MAX_RENDERED_PIXELS} rendered pixels")

    layer_ids = {layer["id"] for layer in character.data["layers"]}
    rig = character.data.get("rig", {})
    tracks = data["tracks"]
    if not isinstance(tracks, list) or not tracks:
        raise ArtError("animation.tracks must be a non-empty list")
    seen_tracks: set[str] = set()
    allowed_frame_fields = {"atMs", "x", "y", "rotation", "scaleX", "scaleY", "opacity", "visible", "easing"}
    for index, raw_track in enumerate(tracks):
        label = f"tracks[{index}]"
        track = _object(raw_track, label)
        _keys(track, {"layer", "keyframes"}, set(), label)
        layer_id = track["layer"]
        if isinstance(layer_id, str) and layer_id.startswith("$"):
            role = layer_id[1:]
            if role not in rig:
                raise ArtError(f"{label}.layer references an unknown character rig role: {role}")
            layer_id = rig[role]
            track["layer"] = layer_id
        if not isinstance(layer_id, str) or layer_id not in layer_ids:
            raise ArtError(f"{label}.layer does not exist in the character")
        if layer_id in seen_tracks:
            raise ArtError(f"animation has more than one track for layer {layer_id}")
        seen_tracks.add(layer_id)
        keyframes = track["keyframes"]
        if not isinstance(keyframes, list) or not keyframes:
            raise ArtError(f"{label}.keyframes must be a non-empty list")
        if not isinstance(keyframes[0], dict) or keyframes[0].get("atMs") != 0:
            raise ArtError(f"{label}.keyframes must start at 0ms")
        previous = -1
        for frame_index, raw_frame in enumerate(keyframes):
            frame_label = f"{label}.keyframes[{frame_index}]"
            frame = _object(raw_frame, frame_label)
            extra = frame.keys() - allowed_frame_fields
            if extra or "atMs" not in frame:
                raise ArtError(f"{frame_label} needs atMs and only supported transform fields")
            at_ms = _integer(frame["atMs"], f"{frame_label}.atMs", 0, duration)
            if at_ms <= previous:
                raise ArtError(f"{frame_label}.atMs values must be strictly increasing")
            previous = at_ms
            for field in ("x", "y"):
                if field in frame:
                    _number(frame[field], f"{frame_label}.{field}", -MAX_DIMENSION * 2, MAX_DIMENSION * 2)
            if "rotation" in frame:
                _number(frame["rotation"], f"{frame_label}.rotation", -3600, 3600)
            for field in ("scaleX", "scaleY"):
                if field in frame:
                    _number(frame[field], f"{frame_label}.{field}", 0.05, 8)
            if "opacity" in frame:
                _integer(frame["opacity"], f"{frame_label}.opacity", 0, 255)
            if "visible" in frame and not isinstance(frame["visible"], bool):
                raise ArtError(f"{frame_label}.visible must be boolean")
            if frame.get("easing", "linear") not in {"linear", "smoothstep"}:
                raise ArtError(f"{frame_label}.easing must be linear or smoothstep")
    return AnimationDocument(path, data, character, frame_count)
