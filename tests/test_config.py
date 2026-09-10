import json
from pathlib import Path

from companion import cli
from companion.config import load_config


def test_legacy_json_config_keeps_gui_defaults(tmp_path: Path):
    config_path = tmp_path / "companion.json"
    config_path.write_text(
        json.dumps({"companion": {"name": "Legacy"}, "window": {"position": "dock"}}),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.show_messages is True
    assert config.pack_name is None


def test_config_loads_optional_message_and_pack_name_fields(tmp_path: Path):
    config_path = tmp_path / "companion.json"
    config_path.write_text(
        json.dumps(
            {
                "companion": {"pack_name": "malbolge-cat"},
                "window": {"show_messages": False},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.show_messages is False
    assert config.pack_name == "malbolge-cat"


def test_gui_launch_applies_optional_config_fields(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "companion.json"
    config_path.write_text(
        json.dumps(
            {
                "companion": {"name": "Malbolgato", "pack_name": "malbolge-cat"},
                "window": {"show_messages": False},
            }
        ),
        encoding="utf-8",
    )
    launched = {}

    def record_launch(runtime, **options):
        launched.update(options)

    monkeypatch.setattr(cli, "launch", record_launch)

    assert cli.main(["--root", str(tmp_path / "runtime"), "gui", "--config", str(config_path)]) == 0
    assert launched["show_messages"] is False
    assert launched["pack_name"] == "malbolge-cat"
