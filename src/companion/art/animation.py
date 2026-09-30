"""Deterministic layer-timeline renderer and GIF/atlas exporters."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .render import SUPERSAMPLE, _pillow, compose_frame, render_layers
from .spec import AnimationDocument, ArtError


_DEFAULTS: dict[str, Any] = {"x": 0.0, "y": 0.0, "rotation": 0.0, "scaleX": 1.0, "scaleY": 1.0, "opacity": 255}


def _track_transform(track: dict[str, Any], time_ms: int, base_visible: bool) -> dict[str, Any]:
    frames = track["keyframes"]
    if time_ms <= frames[0]["atMs"]:
        before = after = frames[0]
    elif time_ms >= frames[-1]["atMs"]:
        before = after = frames[-1]
    else:
        before = frames[0]
        after = frames[-1]
        for left, right in zip(frames, frames[1:]):
            if left["atMs"] <= time_ms <= right["atMs"]:
                before, after = left, right
                break
    span = after["atMs"] - before["atMs"]
    amount = 0.0 if span == 0 else (time_ms - before["atMs"]) / span
    if before.get("easing", "linear") == "smoothstep":
        amount = amount * amount * (3 - 2 * amount)
    result: dict[str, Any] = {}
    for key, default in _DEFAULTS.items():
        start = float(before.get(key, default))
        end = float(after.get(key, default))
        result[key] = start + (end - start) * amount
    # Visibility is categorical and changes at its keyframe, never blended.
    result["visible"] = bool(before.get("visible", base_visible))
    for frame in frames:
        if frame["atMs"] <= time_ms and "visible" in frame:
            result["visible"] = frame["visible"]
    return result


def render_animation_frames(animation: AnimationDocument) -> tuple[list[Any], list[int]]:
    Image, _ = _pillow()
    layers = render_layers(animation.character)
    frame_duration = int(animation.data.get("frameDurationMs", 120))
    frame_count = animation.frame_count
    duration = int(animation.data["durationMs"])
    base_visible = {layer["id"]: layer.get("visible", True) for layer in animation.character.data["layers"]}
    tracks = {track["layer"]: track for track in animation.data["tracks"]}
    frames: list[Any] = []
    for index in range(frame_count):
        time_ms = index * frame_duration
        transforms = {
            layer_id: _track_transform(track, time_ms, base_visible[layer_id])
            for layer_id, track in tracks.items()
        }
        frame = compose_frame(animation.character, layers, transforms)
        if animation.data.get("flipX", False):
            frame = frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        frames.append(frame)
    if not frames:
        raise ArtError("animation produced no frames")
    return frames, [frame_duration] * frame_count


def _gif_frames(frames: list[Any]) -> list[Any]:
    Image, _ = _pillow()
    width, height = frames[0].size
    palette_source = Image.new("RGB", (width, height * len(frames)), (0, 0, 0))
    for index, frame in enumerate(frames):
        palette_source.paste(frame.convert("RGB"), (0, index * height))
    global_palette = palette_source.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    palette = (global_palette.getpalette() or [])[:765]
    palette.extend([0, 0, 0] * (256 - len(palette) // 3))
    converted: list[Any] = []
    for frame in frames:
        indexed = frame.convert("RGB").quantize(palette=global_palette, dither=Image.Dither.NONE)
        indexed.putpalette(palette[:768])
        transparent = frame.getchannel("A").point(lambda alpha: 255 if alpha < 128 else 0)
        indexed.paste(255, mask=transparent)
        converted.append(indexed)
    return converted


def _save_atlas(frames: list[Any], output: Path, columns: int) -> dict[str, Any]:
    Image, _ = _pillow()
    cell_width, cell_height = frames[0].size
    rows = math.ceil(len(frames) / columns)
    atlas = Image.new("RGBA", (cell_width * columns, cell_height * rows), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        atlas.alpha_composite(frame, ((index % columns) * cell_width, (index // columns) * cell_height))
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(output, format="PNG", optimize=True)
    return {"path": str(output), "width": atlas.width, "height": atlas.height, "columns": columns, "rows": rows}


def render_animation(animation: AnimationDocument, output: Path, atlas_output: Path | None = None) -> dict[str, Any]:
    frames, durations = render_animation_frames(animation)
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    gif_frames = _gif_frames(frames)
    save_options: dict[str, Any] = {
        "format": "GIF",
        "save_all": True,
        "append_images": gif_frames[1:],
        "duration": durations,
        "transparency": 255,
        "disposal": 2,
        "optimize": False,
    }
    if animation.data["loop"]:
        save_options["loop"] = 0
    gif_frames[0].save(output, **save_options)
    result: dict[str, Any] = {
        "gif": str(output),
        "frames": len(frames),
        "durationMs": sum(durations),
        "width": frames[0].width,
        "height": frames[0].height,
        "loop": animation.data["loop"],
    }
    if atlas_output is not None:
        atlas = _save_atlas(frames, Path(atlas_output), int(animation.data.get("frameColumns", 8)))
        result["atlas"] = atlas
    return result
