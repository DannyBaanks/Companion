"""Tests for the local art and animation recipe engine (companion.art)."""

import json
from pathlib import Path

import pytest

from companion.art import ArtError, load_animation, load_character


def _character(tmp_path: Path, **overrides) -> Path:
    data = {
        "schema": "companion-character-v1",
        "id": "test-cat",
        "name": "Test Cat",
        "canvas": {"width": 32, "height": 32},
        "palette": {"body": "#222222", "accent": "#8cff00"},
        "layers": [
            {
                "id": "body",
                "pivot": [16, 16],
                "shapes": [{"type": "ellipse", "bounds": [4, 4, 24, 24], "fill": "body"}],
            },
            {
                "id": "eye",
                "pivot": [20, 12],
                "shapes": [{"type": "rect", "bounds": [18, 10, 4, 4], "fill": "accent"}],
            },
        ],
    }
    data.update(overrides)
    path = tmp_path / "character.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _animation(tmp_path: Path, character_path: Path, **overrides) -> Path:
    data = {
        "schema": "companion-animation-v1",
        "id": "blink",
        "character": character_path.name,
        "durationMs": 240,
        "loop": True,
        "tracks": [
            {
                "layer": "eye",
                "keyframes": [
                    {"atMs": 0, "scaleY": 1.0},
                    {"atMs": 120, "scaleY": 0.1},
                    {"atMs": 240, "scaleY": 1.0},
                ],
            }
        ],
    }
    data.update(overrides)
    path = tmp_path / "blink.animation.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ── Character validation ──────────────────────────────────────────────────────


def test_load_character_accepts_minimal_recipe(tmp_path):
    character = load_character(_character(tmp_path))
    assert character.data["id"] == "test-cat"
    assert character.width == 32 and character.height == 32
    assert [layer["id"] for layer in character.data["layers"]] == ["body", "eye"]


def test_character_rejects_wrong_schema(tmp_path):
    path = _character(tmp_path, schema="companion-character-v2")
    with pytest.raises(ArtError, match="schema"):
        load_character(path)


def test_character_rejects_unknown_color(tmp_path):
    path = _character(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["layers"][0]["shapes"][0]["fill"] = "not-a-palette-color"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ArtError, match="unknown color"):
        load_character(path)


def test_character_rejects_duplicate_layer_ids(tmp_path):
    data = {
        "schema": "companion-character-v1",
        "id": "dup",
        "name": "Dup",
        "canvas": {"width": 8, "height": 8},
        "palette": {"a": "#000000"},
        "layers": [
            {"id": "same", "pivot": [0, 0], "shapes": [{"type": "rect", "bounds": [0, 0, 4, 4], "fill": "a"}]},
            {"id": "same", "pivot": [0, 0], "shapes": [{"type": "rect", "bounds": [0, 0, 4, 4], "fill": "a"}]},
        ],
    }
    path = tmp_path / "dup.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ArtError, match="unique"):
        load_character(path)


def test_character_rig_must_reference_existing_layer(tmp_path):
    data = json.loads(_character(tmp_path).read_text(encoding="utf-8"))
    data["rig"] = {"$body-role": "does-not-exist"}
    path = tmp_path / "character.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ArtError, match="existing layer id"):
        load_character(path)


def test_character_parts_resolve_color_slots(tmp_path):
    library = {
        "schema": "companion-parts-v1",
        "id": "mini-kit",
        "parts": {
            "dot": {
                "canvas": [8, 8],
                "colors": ["fill"],
                "shapes": [{"type": "ellipse", "bounds": [1, 1, 6, 6], "fill": "$fill"}],
            }
        },
    }
    (tmp_path / "kit.json").write_text(json.dumps(library), encoding="utf-8")
    data = json.loads(_character(tmp_path).read_text(encoding="utf-8"))
    data["libraries"] = ["kit.json"]
    data["layers"].append(
        {
            "id": "spot",
            "pivot": [4, 4],
            "shapes": [
                {
                    "type": "part",
                    "part": "dot",
                    "bounds": [20, 20, 8, 8],
                    "colors": {"fill": "accent"},
                }
            ],
        }
    )
    path = tmp_path / "character.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    character = load_character(path)
    assert "spot" in {layer["id"] for layer in character.data["layers"]}
    assert "dot" in character.data["parts"]


def test_character_part_with_missing_color_slot_is_rejected(tmp_path):
    library = {
        "schema": "companion-parts-v1",
        "id": "mini-kit",
        "parts": {
            "dot": {
                "canvas": [8, 8],
                "colors": ["fill", "outline"],
                "shapes": [
                    {"type": "ellipse", "bounds": [1, 1, 6, 6], "fill": "$fill"},
                ],
            }
        },
    }
    (tmp_path / "kit.json").write_text(json.dumps(library), encoding="utf-8")
    data = json.loads(_character(tmp_path).read_text(encoding="utf-8"))
    data["libraries"] = ["kit.json"]
    data["layers"].append(
        {
            "id": "spot",
            "pivot": [4, 4],
            "shapes": [{"type": "part", "part": "dot", "bounds": [0, 0, 8, 8], "colors": {"fill": "accent"}}],
        }
    )
    path = tmp_path / "character.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ArtError, match="missing slots"):
        load_character(path)


# ── Animation validation ──────────────────────────────────────────────────────


def test_load_animation_accepts_minimal_recipe(tmp_path):
    character_path = _character(tmp_path)
    animation = load_animation(_animation(tmp_path, character_path))
    assert animation.frame_count == 2  # 240ms / 120ms frames


def test_animation_rejects_track_for_unknown_layer(tmp_path):
    character_path = _character(tmp_path)
    path = _animation(tmp_path, character_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tracks"][0]["layer"] = "ghost-layer"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ArtError, match="does not exist in the character"):
        load_animation(path)


def test_animation_rejects_keyframes_not_starting_at_zero(tmp_path):
    character_path = _character(tmp_path)
    path = _animation(tmp_path, character_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tracks"][0]["keyframes"] = [{"atMs": 60, "scaleY": 1.0}]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ArtError, match="start at 0ms"):
        load_animation(path)


def test_animation_duration_must_align_to_frame_duration(tmp_path):
    character_path = _character(tmp_path)
    path = _animation(tmp_path, character_path, durationMs=250)
    with pytest.raises(ArtError, match="align"):
        load_animation(path)


def test_animation_rig_role_resolves_to_layer(tmp_path):
    data = json.loads(_character(tmp_path).read_text(encoding="utf-8"))
    data["rig"] = {"eye": "eye"}
    character_path = tmp_path / "character.json"
    character_path.write_text(json.dumps(data), encoding="utf-8")
    path = _animation(tmp_path, character_path)
    animation_data = json.loads(path.read_text(encoding="utf-8"))
    animation_data["tracks"][0]["layer"] = "$eye"
    path.write_text(json.dumps(animation_data), encoding="utf-8")

    animation = load_animation(path)
    assert animation.data["tracks"][0]["layer"] == "eye"


# ── Rendering (needs Pillow) ──────────────────────────────────────────────────


def test_render_character_produces_png(tmp_path):
    pytest.importorskip("PIL")
    from companion.art.render import render_character

    character = load_character(_character(tmp_path))
    output = tmp_path / "preview.png"
    result = render_character(character, output)
    assert output.is_file()
    assert result["width"] == 32 and result["height"] == 32


def test_render_animation_produces_gif_and_atlas(tmp_path):
    pytest.importorskip("PIL")
    from companion.art.animation import render_animation

    character_path = _character(tmp_path)
    animation = load_animation(_animation(tmp_path, character_path))
    output = tmp_path / "blink.gif"
    atlas = tmp_path / "blink-atlas.png"
    result = render_animation(animation, output, atlas)
    assert output.is_file() and atlas.is_file()
    assert result["frames"] == 2
    assert result["loop"] is True


def test_cli_art_and_animate_subcommands_exist():
    from companion.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["art", "validate", "x.json"]).command == "art"
    assert parser.parse_args(["animate", "render", "x.json", "--output", "y.gif"]).command == "animate"


def test_checked_in_vector_neon_cat_recipes_validate():
    project_root = Path(__file__).resolve().parents[1]
    character = load_character(project_root / "examples" / "vector-neon-cat" / "character.json")
    assert character.data["id"] == "vector-neon-cat"
    animation = load_animation(project_root / "examples" / "vector-neon-cat" / "idle.animation.json")
    assert animation.frame_count > 0
