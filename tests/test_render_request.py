import json
from pathlib import Path

import pytest

from companion.cli import main
from companion.render_request import RenderRequestError, load_render_request, validate_render_request


def valid_request() -> dict[str, object]:
    return {
        "name": "Malbolgato",
        "style": "pixel art",
        "palette": ["#111111", "#ffffff"],
        "states": ["idle", "thinking", "success"],
        "output": {"cell_size": [64, 64]},
    }


def test_required_name_and_style_are_non_empty_strings():
    with pytest.raises(RenderRequestError, match="name must be a non-empty string"):
        validate_render_request({"style": "pixel art"})
    with pytest.raises(RenderRequestError, match="style must be a non-empty string"):
        validate_render_request({"name": "Cat"})


def test_palette_must_be_a_non_empty_list_of_non_empty_strings():
    request = valid_request()
    request["palette"] = []
    with pytest.raises(RenderRequestError, match="palette must be a non-empty list"):
        validate_render_request(request)

    request = valid_request()
    request["palette"] = ["#fff", 4]
    with pytest.raises(RenderRequestError, match=r"palette\[1\] must be a non-empty string"):
        validate_render_request(request)


def test_states_must_contain_only_known_companion_states():
    request = valid_request()
    request["states"] = ["idle", "unknown"]
    with pytest.raises(RenderRequestError, match=r"states\[1\] must be one of"):
        validate_render_request(request)


def test_output_cell_size_requires_two_positive_integers():
    request = valid_request()
    request["output"] = {"cell_size": [64, 0]}
    with pytest.raises(RenderRequestError, match="output.cell_size values must be positive integers"):
        validate_render_request(request)

    request = valid_request()
    request["output"] = {"cell_size": [64, 64, 64]}
    with pytest.raises(RenderRequestError, match="output.cell_size must contain exactly two"):
        validate_render_request(request)


def test_unknown_fields_are_preserved_and_input_is_not_mutated():
    request = valid_request()
    request["renderer"] = {"seed": 7}
    normalized = validate_render_request(request)
    assert normalized == request
    assert normalized is not request
    assert normalized["renderer"] is not request["renderer"]


def test_load_render_request_reports_invalid_json(tmp_path: Path):
    path = tmp_path / "request.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(RenderRequestError, match="invalid JSON"):
        load_render_request(path)


def test_cli_validates_and_prints_normalized_json(tmp_path: Path, capsys):
    path = tmp_path / "request.json"
    request = valid_request()
    path.write_text(json.dumps(request), encoding="utf-8")
    assert main(["render-request", "validate", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == request


def test_cli_invalid_request_prints_error_and_returns_two(tmp_path: Path, capsys):
    path = tmp_path / "request.json"
    path.write_text(json.dumps({"name": "Cat"}), encoding="utf-8")
    assert main(["render-request", "validate", str(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error: style must be a non-empty string" in captured.err
