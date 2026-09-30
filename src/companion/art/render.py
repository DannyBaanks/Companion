"""Pillow renderer for data-only, layered vector character recipes."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .spec import ArtError, CharacterDocument


SUPERSAMPLE = 3


def _pillow() -> Any:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise ArtError("local art rendering needs Pillow; install Companion with its [art] extra") from exc
    return Image, ImageDraw


def _rgba(
    color: str | None,
    palette: dict[str, Any],
    opacity: int = 255,
    bindings: dict[str, str] | None = None,
) -> tuple[int, int, int, int] | None:
    if color is None:
        return None
    if color.startswith("$") and bindings:
        color = bindings.get(color[1:], color)
    value = palette.get(color, color)
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), opacity


def _path_subpaths(commands: list[list[Any]], scale: int) -> list[tuple[list[tuple[float, float]], bool]]:
    result: list[tuple[list[tuple[float, float]], bool]] = []
    points: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    start = current
    for command in commands:
        op = command[0]
        if op == "M":
            if points:
                result.append((points, False))
            points = []
            current = (float(command[1]), float(command[2]))
            start = current
            points.append((current[0] * scale, current[1] * scale))
        elif op == "L":
            current = (float(command[1]), float(command[2]))
            points.append((current[0] * scale, current[1] * scale))
        elif op == "C":
            p0 = current
            p1 = (float(command[1]), float(command[2]))
            p2 = (float(command[3]), float(command[4]))
            p3 = (float(command[5]), float(command[6]))
            for step in range(1, 25):
                t = step / 24
                u = 1 - t
                x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
                y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
                points.append((x * scale, y * scale))
            current = p3
        elif op == "Z":
            current = start
            if points and points[-1] != (start[0] * scale, start[1] * scale):
                points.append((start[0] * scale, start[1] * scale))
            if points:
                result.append((points, True))
            points = []
    if points:
        result.append((points, False))
    return result


def _draw_shape(
    draw: Any,
    layer_image: Any,
    shape: dict[str, Any],
    palette: dict[str, Any],
    root: Path,
    parts: dict[str, Any] | None = None,
    bindings: dict[str, str] | None = None,
    part_cache: dict[tuple[Any, ...], Any] | None = None,
) -> None:
    Image, _ = _pillow()
    scale = SUPERSAMPLE
    opacity = int(shape.get("opacity", 255))
    fill = _rgba(shape.get("fill"), palette, opacity, bindings)
    stroke = _rgba(shape.get("stroke"), palette, opacity, bindings)
    stroke_width = max(1, round(float(shape.get("strokeWidth", 1)) * scale))
    kind = shape["type"]
    if kind in {"rect", "ellipse"}:
        x, y, width, height = shape["bounds"]
        bounds = (round(x * scale), round(y * scale), round((x + width) * scale), round((y + height) * scale))
        fn = draw.rectangle if kind == "rect" else draw.ellipse
        fn(bounds, fill=fill, outline=stroke, width=stroke_width if stroke else 1)
    elif kind == "polygon":
        points = [(round(x * scale), round(y * scale)) for x, y in shape["points"]]
        if fill:
            draw.polygon(points, fill=fill)
        if stroke:
            draw.line(points + [points[0]], fill=stroke, width=stroke_width, joint="curve")
    elif kind == "path":
        for points, closed in _path_subpaths(shape["commands"], scale):
            if fill and closed and len(points) >= 3:
                draw.polygon(points, fill=fill)
            if stroke and len(points) >= 2:
                line_points = points + ([points[0]] if closed and points[-1] != points[0] else [])
                draw.line(line_points, fill=stroke, width=stroke_width, joint="curve")
    elif kind == "image":
        x, y, width, height = shape["bounds"]
        image_path = (root / shape["path"]).resolve()
        try:
            with Image.open(image_path) as opened:
                image = opened.convert("RGBA")
        except OSError as exc:
            raise ArtError(f"cannot open PNG asset: {shape['path']}") from exc
        target_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        image = image.resize(target_size, Image.Resampling.LANCZOS)
        if opacity != 255:
            image.putalpha(image.getchannel("A").point(lambda alpha: alpha * opacity // 255))
        layer_image.alpha_composite(image, (round(x * scale), round(y * scale)))
    elif kind == "part":
        Image, ImageDraw = _pillow()
        part = (parts or {})[shape["part"]]
        part_bindings = shape.get("colors", {})
        cache_key = (shape["part"], *sorted(part_bindings.items()))
        if part_cache is not None and cache_key in part_cache:
            part_image = part_cache[cache_key]
        else:
            part_width, part_height = part["canvas"]
            part_image = Image.new("RGBA", (part_width * scale, part_height * scale), (0, 0, 0, 0))
            part_draw = ImageDraw.Draw(part_image, "RGBA")
            for part_shape in part["shapes"]:
                _draw_shape(
                    part_draw, part_image, part_shape, palette, Path(part["_source"]).parent,
                    bindings=part_bindings, part_cache=part_cache,
                )
            if part_cache is not None:
                part_cache[cache_key] = part_image
        part_image = part_image.copy()
        if shape.get("flipX", False):
            part_image = part_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        x, y, width, height = shape["bounds"]
        target_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        part_image = part_image.resize(target_size, Image.Resampling.LANCZOS)
        rotation = float(shape.get("rotation", 0))
        if rotation:
            part_image = part_image.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=False)
        layer_image.alpha_composite(part_image, (round(x * scale), round(y * scale)))


def render_layers(character: CharacterDocument) -> dict[str, Any]:
    Image, ImageDraw = _pillow()
    size = (character.width * SUPERSAMPLE, character.height * SUPERSAMPLE)
    layers: dict[str, Any] = {}
    part_cache: dict[tuple[Any, ...], Any] = {}
    for layer in character.data["layers"]:
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(image, "RGBA")
        for shape in layer["shapes"]:
            _draw_shape(
                draw, image, shape, character.data["palette"], character.path.parent,
                parts=character.data.get("parts", {}), part_cache=part_cache,
            )
        layers[layer["id"]] = image
    return layers


def transformed_layer(image: Any, pivot: tuple[float, float], transform: dict[str, Any]) -> Any:
    Image, _ = _pillow()
    scale = SUPERSAMPLE
    px, py = pivot[0] * scale, pivot[1] * scale
    tx = float(transform.get("x", 0)) * scale
    ty = float(transform.get("y", 0)) * scale
    sx = float(transform.get("scaleX", 1))
    sy = float(transform.get("scaleY", 1))
    angle = math.radians(float(transform.get("rotation", 0)))
    cosine, sine = math.cos(angle), math.sin(angle)
    a, b = cosine / sx, sine / sx
    d, e = -sine / sy, cosine / sy
    c = px - a * (px + tx) - b * (py + ty)
    f = py - d * (px + tx) - e * (py + ty)
    moved = image.transform(
        image.size,
        Image.Transform.AFFINE,
        (a, b, c, d, e, f),
        resample=Image.Resampling.BICUBIC,
    )
    opacity = int(transform.get("opacity", 255))
    if opacity != 255:
        moved.putalpha(moved.getchannel("A").point(lambda alpha: alpha * opacity // 255))
    return moved


def compose_frame(character: CharacterDocument, layers: dict[str, Any], transforms: dict[str, dict[str, Any]] | None = None) -> Any:
    Image, _ = _pillow()
    transforms = transforms or {}
    canvas = Image.new("RGBA", (character.width * SUPERSAMPLE, character.height * SUPERSAMPLE), (0, 0, 0, 0))
    for layer in character.data["layers"]:
        transform = transforms.get(layer["id"], {})
        if not transform.get("visible", layer.get("visible", True)):
            continue
        pivot = (float(layer["pivot"][0]), float(layer["pivot"][1]))
        moved = transformed_layer(layers[layer["id"]], pivot, transform)
        canvas.alpha_composite(moved)
    return canvas.resize((character.width, character.height), Image.Resampling.LANCZOS)


def render_character(character: CharacterDocument, output: Path) -> dict[str, Any]:
    image = compose_frame(character, render_layers(character))
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    return {"path": str(output), "width": character.width, "height": character.height, "anchor": list(character.anchor)}


def inspect_image(path: Path) -> dict[str, Any]:
    Image, _ = _pillow()
    path = Path(path).expanduser().resolve()
    try:
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
            alpha = image.getchannel("A")
            return {
                "path": str(path),
                "width": image.width,
                "height": image.height,
                "mode": opened.mode,
                "frames": getattr(opened, "n_frames", 1),
                "alphaBounds": list(alpha.getbbox()) if alpha.getbbox() else None,
                "hasTransparency": alpha.getextrema()[0] < 255,
            }
    except OSError as exc:
        raise ArtError(f"cannot inspect image: {path}") from exc
