"""Tests for Companion Forge (M17) and Recipe ecosystem (M18)."""

import json
from pathlib import Path

import pytest

from companion.forge import (
    Forge,
    ForgeExecutionError,
    PlatformInfo,
    Recipe,
    RecipeReceipt,
    RecipeStage,
    RecipeStore,
    RecipeStep,
)


def _sample_recipe(**overrides) -> Recipe:
    data = {
        "id": "setup-python",
        "name": "Python Companion Setup",
        "description": "Set up a Python coding companion",
        "author": "Danny",
        "license": "MIT",
        "platform": ["linux", "windows", "macos"],
        "capabilities": ["chat", "status"],
        "steps": [
            {"name": "install-pip", "action": "install", "command": ["pip", "install", "open-agent-companion"],
             "description": "Install the companion package"},
            {"name": "create-config", "action": "configure", "target": "companion.toml",
             "description": "Create configuration file", "rollback_action": ["rm", "companion.toml"]},
        ],
    }
    data.update(overrides)
    return Recipe.from_dict(data)


def test_recipe_roundtrip():
    r = _sample_recipe()
    d = r.to_dict()
    restored = Recipe.from_dict(d)
    assert restored.id == "setup-python"
    assert len(restored.steps) == 2
    assert restored.steps[1].requires_elevation is False
    assert restored.steps[0].rollback_action is None


def test_recipe_step_rollback():
    r = _sample_recipe()
    assert r.steps[1].rollback_action == ["rm", "companion.toml"]


def test_recipe_store_save_load_list(tmp_path):
    store = RecipeStore(tmp_path)
    r = _sample_recipe()
    store.save(r)
    loaded = store.load("setup-python")
    assert loaded is not None
    assert loaded.name == "Python Companion Setup"
    assert len(store.list_recipes()) == 1


def test_recipe_store_remove(tmp_path):
    store = RecipeStore(tmp_path)
    store.save(_sample_recipe())
    assert store.remove("setup-python") is True
    assert store.load("setup-python") is None
    assert store.remove("setup-python") is False


def test_recipe_store_export_import(tmp_path):
    store = RecipeStore(tmp_path)
    store.save(_sample_recipe())
    export_path = tmp_path / "export.json"
    assert store.export("setup-python", export_path) is True
    assert export_path.exists()

    store2 = RecipeStore(tmp_path / "other")
    imported = store2.import_recipe(export_path)
    assert imported is not None
    assert imported.id == "setup-python"


def test_recipe_store_import_invalid(tmp_path):
    store = RecipeStore(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert store.import_recipe(bad) is None


def test_platform_detect():
    p = PlatformInfo.detect()
    assert p.os in ("linux", "windows", "macos")
    assert p.arch
    assert p.python_version


def test_platform_matches():
    assert PlatformInfo("linux", "x86_64", "3.12").matches(["linux"]) is True
    assert PlatformInfo("linux", "x86_64", "3.12").matches(["windows"]) is False
    assert PlatformInfo("linux", "x86_64", "3.12").matches(["any"]) is True


def test_forge_detect():
    forge = Forge(Path("/tmp/test"), dry_run=True)
    r = _sample_recipe()
    ok, msg = forge.detect(r)
    assert ok is True
    assert "compatible" in msg


def test_forge_detect_wrong_platform():
    forge = Forge(Path("/tmp/test"), dry_run=True)
    r = _sample_recipe(platform=["plan9"])
    ok, msg = forge.detect(r)
    assert ok is False
    assert "mismatch" in msg


def test_forge_propose():
    forge = Forge(Path("/tmp/test"), dry_run=True)
    r = _sample_recipe()
    proposal = forge.propose(r)
    assert proposal["recipe"] == "Python Companion Setup"
    assert proposal["total_steps"] == 2
    assert proposal["dry_run"] is True


def test_forge_execute_dry_run():
    forge = Forge(Path("/tmp/test"), dry_run=True)
    r = _sample_recipe()
    receipt = forge.execute(r)
    assert len(receipt.steps_completed) == 2
    assert receipt.steps_failed == []
    assert receipt.recipe_id == "setup-python"


def test_forge_non_dry_run_refuses_unimplemented_execution():
    forge = Forge(Path("/tmp/test"), dry_run=False)
    with pytest.raises(ForgeExecutionError, match="not implemented"):
        forge.execute(_sample_recipe())


def test_forge_verify_success():
    forge = Forge(Path("/tmp/test"), dry_run=True)
    r = _sample_recipe()
    receipt = forge.execute(r)
    ok, msg = forge.verify(r, receipt)
    assert ok is True
    assert "verified" in msg


def test_forge_verify_failure():
    forge = Forge(Path("/tmp/test"), dry_run=True)
    r = _sample_recipe()
    receipt = RecipeReceipt(
        recipe_id="setup-python", recipe_version="1.0.0",
        executed_at="t", platform="linux",
        steps_completed=["install-pip"], steps_failed=["create-config"],
    )
    ok, msg = forge.verify(r, receipt)
    assert ok is False
    assert "failed" in msg


def test_forge_verify_incomplete():
    forge = Forge(Path("/tmp/test"), dry_run=True)
    r = _sample_recipe()
    receipt = RecipeReceipt(
        recipe_id="setup-python", recipe_version="1.0.0",
        executed_at="t", platform="linux",
        steps_completed=["install-pip"], steps_failed=[],
    )
    ok, msg = forge.verify(r, receipt)
    assert ok is False
    assert "not all" in msg


def test_recipe_stage_enum():
    assert RecipeStage.DETECT.value == "detect"
    assert RecipeStage.RECEIPT.value == "receipt"


def test_recipe_capabilities():
    r = _sample_recipe(capabilities=["chat", "notifications", "actions"])
    assert "notifications" in r.capabilities


def test_cli_hub_command_exists():
    from companion.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["hub"])
    assert args.command == "hub"
