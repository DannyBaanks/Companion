import json
from pathlib import Path

from companion.hub.discovery import discover_packs


def make_pack(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "idle.png").write_bytes(b"png")
    (root / "manifest.json").write_text(
        json.dumps({"id": "cat", "name": "Cat", "animations": {"idle": "idle.png"}}),
        encoding="utf-8",
    )
    return root


def test_discover_packs_returns_valid_and_invalid_records(tmp_path):
    valid = make_pack(tmp_path / "valid")
    invalid = tmp_path / "broken"
    invalid.mkdir()
    (invalid / "manifest.json").write_text("{}", encoding="utf-8")

    records = discover_packs(tmp_path)

    assert [(r.name, r.error is None) for r in records] == [("Cat", True), ("broken", False)]
    assert records[0].preview == valid / "idle.png"


def test_discover_packs_only_checks_immediate_children(tmp_path):
    nested = tmp_path / "nested"
    make_pack(nested / "cat")

    assert discover_packs(tmp_path) == []
