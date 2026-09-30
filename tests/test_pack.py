import json
from pathlib import Path

import pytest

from companion.config import load_config
from companion.pack import AssetPack, PackError
from companion.render_request import load_render_request

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _pack(tmp_path: Path) -> Path:
    root = tmp_path / "cat"
    root.mkdir()
    (root / "idle.ppm").write_text("P3\n1 1\n255\n0 255 0\n", encoding="ascii")
    (root / "manifest.json").write_text(
        json.dumps({"id": "cat", "name": "Green Cat", "animations": {"idle": "idle.ppm"}}),
        encoding="utf-8",
    )
    return root


def test_pack_loads_and_falls_back_to_idle(tmp_path: Path):
    pack = AssetPack.load(_pack(tmp_path))
    assert pack.pack_id == "cat"
    assert pack.animation_for(state="thinking").name == "idle.ppm"


def test_pack_rejects_asset_outside_root(tmp_path: Path):
    root = _pack(tmp_path)
    (root / "manifest.json").write_text(
        json.dumps({"id": "cat", "animations": {"idle": "../outside.png"}}), encoding="utf-8"
    )
    with pytest.raises(PackError, match="escapes"):
        AssetPack.load(root)


def test_pack_supports_action_animations_and_fallback(tmp_path: Path):
    root = tmp_path / "runner"
    root.mkdir()
    for name in ("idle.ppm", "run-right.ppm", "run-left.ppm"):
        (root / name).write_text("P3\n1 1\n255\n0 255 0\n", encoding="ascii")
    manifest = {
        "id": "runner",
        "name": "Runner",
        "animations": {
            "idle": "idle.ppm",
            "running-right": "run-right.ppm",
            "running-left": "run-left.ppm",
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    pack = AssetPack.load(root)
    assert pack.animation_for(state="idle", action="running-right").name == "run-right.ppm"
    assert pack.animation_for(state="idle", action="running-left").name == "run-left.ppm"
    # An unknown action falls back to the state, then to idle.
    assert pack.animation_for(state="thinking", action="unknown").name == "idle.ppm"


def test_pack_rejects_unknown_animation_state(tmp_path: Path):
    root = _pack(tmp_path)
    (root / "manifest.json").write_text(
        json.dumps({"id": "cat", "animations": {"idle": "idle.ppm", "dancing": "idle.ppm"}}),
        encoding="utf-8",
    )
    with pytest.raises(PackError, match="unsupported animation state"):
        AssetPack.load(root)


def test_pack_sprite_sheet_validation(tmp_path: Path):
    root = tmp_path / "sheet-cat"
    root.mkdir()
    (root / "idle.ppm").write_text("P3\n1 1\n255\n0 255 0\n", encoding="ascii")
    (root / "sheet.webp").write_bytes(b"webp-bytes")
    base = {"id": "sheet-cat", "name": "Sheet Cat", "animations": {"idle": "idle.ppm"}}

    # Valid spriteSheet block.
    manifest = dict(base, spriteSheet={"path": "sheet.webp", "cellWidth": 192, "cellHeight": 208, "columns": 8})
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pack = AssetPack.load(root)
    assert pack.sprite_sheet == "sheet.webp"
    assert pack.sprite_cell_width == 192 and pack.sprite_columns == 8

    # Escaping path is rejected.
    manifest = dict(base, spriteSheet={"path": "../sheet.webp"})
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PackError, match="escapes pack directory"):
        AssetPack.load(root)

    # Non-integer dimensions are rejected.
    manifest = dict(base, spriteSheet={"path": "sheet.webp", "cellWidth": "wide"})
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PackError, match="positive integers"):
        AssetPack.load(root)

    # floorOffset outside the cell is rejected.
    manifest = dict(base, spriteSheet={"path": "sheet.webp", "cellHeight": 208, "floorOffset": 999})
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PackError, match="floorOffset"):
        AssetPack.load(root)


def test_toml_config_resolves_pack_relative_to_config(tmp_path: Path):
    pack = _pack(tmp_path)
    config_path = tmp_path / "companion.toml"
    config_path.write_text(
        "[companion]\nname = 'Terra'\npack = 'cat'\n[window]\nposition = 'dock'\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.name == "Terra"
    assert config.pack == pack.resolve()
    assert config.position == "dock"


def test_malbolgato_gifs_have_no_chroma_border():
    pytest.importorskip("PIL")
    from PIL import Image

    def is_cyan_screen(r: int, g: int, b: int) -> bool:
        # Cyan screen key: green/blue high and close, red far below both.
        # The Malbolgato design palette (neon green #c8ff00, purple #bd19ff)
        # cannot match this rule; only a leftover key would.
        return g >= 100 and b >= 100 and abs(g - b) <= 80 and r + 40 < min(g, b)

    manifest = json.loads((PROJECT_ROOT / "packs" / "malbolge-cat" / "manifest.json").read_text(encoding="utf-8"))
    # Validate every GIF the manifest actually references, including previewGif.
    referenced = sorted(set(manifest["animations"].values()) | {manifest.get("preview", "")} | {manifest["dragAnimation"].get("previewGif", "")})

    for name in referenced:
        if not name or not name.endswith(".gif"):
            continue
        image = Image.open(PROJECT_ROOT / "packs" / "malbolge-cat" / name)
        for index in range(image.n_frames):
            image.seek(index)
            rgba = image.convert("RGBA")
            pixels = getattr(rgba, "get_flattened_data", rgba.getdata)()
            for red, green, blue, alpha in pixels:
                if alpha and is_cyan_screen(red, green, blue):
                    raise AssertionError(f"{name} frame {index} still has cyan-screen pixel {(red, green, blue)}")


def test_checked_in_malbolgato_request_and_pack_validate():
    request = load_render_request(PROJECT_ROOT / "examples" / "render_request.json")
    pack = AssetPack.load(PROJECT_ROOT / "packs" / "malbolge-cat")

    assert request["name"] == "Malbolgato"
    assert set(request["states"]) == set(pack.animations)
    assert set(pack.animations) == {
        "idle",
        "thinking",
        "working",
        "success",
        "error",
        "waiting",
        "running-right",
        "running-left",
        "drag",
    }
