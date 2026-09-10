from io import StringIO
from pathlib import Path
import json

from companion.adapters.hooks import forward_stream
from companion.protocol import new_event
from companion.runtime import Runtime


def test_hook_forwards_valid_events_and_reports_invalid_lines(tmp_path: Path):
    valid = new_event("say", agent="hook", text="desde hook")
    output = StringIO()
    count = forward_stream(StringIO(json.dumps(valid) + "\n{broken\n"), tmp_path / "inbox.jsonl", output)

    assert count == 1
    reports = [json.loads(line) for line in output.getvalue().splitlines()]
    assert reports[0]["status"] == "queued"
    assert reports[1]["status"] == "error"
    assert json.loads((tmp_path / "inbox.jsonl").read_text())["id"] == valid["id"]


def test_hook_multiple_events_are_all_queued(tmp_path: Path):
    events = "\n".join(json.dumps(new_event("say", text=f"msg{i}")) for i in range(3))
    output = StringIO()
    count = forward_stream(StringIO(events + "\n"), tmp_path / "inbox.jsonl", output)

    assert count == 3
    lines = [json.loads(line) for line in output.getvalue().splitlines()]
    assert all(r["status"] == "queued" for r in lines)


def test_hook_empty_input_produces_no_output(tmp_path: Path):
    output = StringIO()
    count = forward_stream(StringIO(""), tmp_path / "inbox.jsonl", output)

    assert count == 0
    assert output.getvalue() == ""
    assert not (tmp_path / "inbox.jsonl").exists()


def test_hook_output_is_valid_jsonl_per_line(tmp_path: Path):
    valid = new_event("say", text="line check")
    output = StringIO()
    forward_stream(StringIO(json.dumps(valid) + "\n"), tmp_path / "inbox.jsonl", output)

    for line in output.getvalue().splitlines():
        parsed = json.loads(line)
        assert "line" in parsed
        assert "status" in parsed


def test_websocket_rejects_non_loopback(tmp_path: Path):
    from companion.adapters.websocket import serve
    import pytest

    with pytest.raises(ValueError, match="loopback"):
        import asyncio
        asyncio.get_event_loop().run_until_complete(serve(tmp_path / "inbox.jsonl", host="0.0.0.0", port=9999))


def test_websocket_requires_websockets_package(tmp_path: Path):
    import importlib
    import sys
    from unittest.mock import MagicMock
    from companion.adapters import websocket as ws_mod
    import pytest

    original = ws_mod.__dict__.copy()
    saved = sys.modules.pop("websockets", None)
    try:
        sys.modules["websockets"] = MagicMock()
        importlib.reload(ws_mod)

        import asyncio
        with pytest.raises(RuntimeError, match="websocket"):
            asyncio.get_event_loop().run_until_complete(ws_mod.serve(tmp_path / "inbox.jsonl"))
    finally:
        if saved:
            sys.modules["websockets"] = saved
        else:
            sys.modules.pop("websockets", None)
        importlib.reload(ws_mod)
