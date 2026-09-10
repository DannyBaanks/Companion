import json
from pathlib import Path

import pytest

from companion.config import load_config
from companion.pack import AssetPack, PackError
from companion.render_request import load_render_request


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


def test_checked_in_malbolgato_request_and_pack_validate():
    project_root = Path(__file__).resolve().parents[1]
    request = load_render_request(project_root / "examples" / "render_request.json")
    pack = AssetPack.load(project_root / "packs" / "malbolge-cat")

    assert request["name"] == "Malbolgato"
    assert set(request["states"]) == set(pack.animations)
    assert set(pack.animations) == {
        "idle",
        "thinking",
        "working",
        "success",
        "error",
        "waiting",
    }
