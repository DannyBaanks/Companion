import json
from pathlib import Path

import pytest

from companion.protocol import ProtocolError, new_event
from companion.runtime import Runtime


def test_event_validation_rejects_unknown_state():
    with pytest.raises(ProtocolError):
        new_event("state", value="confused")


def test_runtime_processes_events_and_writes_ack(tmp_path: Path):
    root = tmp_path / "companion"
    runtime = Runtime(root)
    from companion.queue import append_jsonl

    append_jsonl(root / "inbox.jsonl", new_event("summon", agent="terra"))
    append_jsonl(root / "inbox.jsonl", new_event("say", agent="terra", text="Milestone 1 terminado", ttl=5))

    assert runtime.process_once() == 2
    assert runtime.state["visible"] is True
    assert runtime.state["message"]["text"] == "Milestone 1 terminado"
    acknowledgements = [json.loads(line) for line in (root / "outbox.jsonl").read_text().splitlines()]
    assert [item["status"] for item in acknowledgements] == ["accepted", "accepted"]


def test_runtime_reports_malformed_json(tmp_path: Path):
    root = tmp_path / "companion"
    root.mkdir()
    (root / "inbox.jsonl").write_text('{"type":\n', encoding="utf-8")
    runtime = Runtime(root)

    assert runtime.process_once() == 1
    report = json.loads((root / "outbox.jsonl").read_text().splitlines()[0])
    assert report["status"] == "error"


def test_runtime_waits_for_incomplete_final_line(tmp_path: Path):
    root = tmp_path / "companion"
    root.mkdir()
    event = new_event("summon", agent="terra")
    (root / "inbox.jsonl").write_text(json.dumps(event), encoding="utf-8")
    runtime = Runtime(root)

    assert runtime.process_once() == 0
    with (root / "inbox.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    assert runtime.process_once() == 1


def test_runtime_expires_ttl_and_releases_next_priority_message(tmp_path: Path):
    now = [100.0]
    runtime = Runtime(tmp_path / "companion", clock=lambda: now[0])
    from companion.queue import append_jsonl

    append_jsonl(runtime.inbox, new_event("say", text="first", ttl=20, priority=0))
    append_jsonl(runtime.inbox, new_event("say", text="urgent", ttl=10, priority=2))
    assert runtime.process_once() == 2
    assert runtime.state["message"]["text"] == "urgent"

    now[0] = 111.0
    runtime.expire_messages()
    assert runtime.state["message"]["text"] == "first"
    now[0] = 132.0
    runtime.expire_messages()
    assert runtime.state["message"] is None


def test_companion_id_routes_events_to_specific_companion(tmp_path: Path):
    from companion.queue import append_jsonl

    root = tmp_path / "companion"
    root.mkdir()

    event_a = new_event("say", text="para companion A", companion_id="alpha")
    event_b = new_event("say", text="para companion B", companion_id="beta")
    append_jsonl(root / "inbox.jsonl", event_a)
    append_jsonl(root / "inbox.jsonl", event_b)

    runtime_a = Runtime(root, companion_id="alpha")
    runtime_b = Runtime(root, companion_id="beta")
    runtime_a.process_once()
    runtime_b.process_once()

    assert runtime_a.state["message"]["text"] == "para companion A"
    assert runtime_b.state["message"]["text"] == "para companion B"
    assert runtime_a.state_path.name == "state-alpha.json"
    assert runtime_b.state_path.name == "state-beta.json"


def test_companion_id_ignores_events_for_other_companions(tmp_path: Path):
    from companion.queue import append_jsonl

    root = tmp_path / "companion"
    root.mkdir()

    event = new_event("say", text="solo beta", companion_id="beta")
    append_jsonl(root / "inbox.jsonl", event)

    runtime = Runtime(root, companion_id="alpha")
    processed = runtime.process_once()

    assert processed == 1
    assert runtime.state["message"] is None


def test_companion_id_none_accepts_all_events(tmp_path: Path):
    from companion.queue import append_jsonl

    root = tmp_path / "companion"
    root.mkdir()

    event = new_event("say", text="universal")
    append_jsonl(root / "inbox.jsonl", event)

    runtime = Runtime(root)
    processed = runtime.process_once()

    assert processed == 1
    assert runtime.state["message"]["text"] == "universal"


def test_multiple_companions_share_inbox_but_have_independent_state(tmp_path: Path):
    from companion.queue import append_jsonl

    root = tmp_path / "companion"
    root.mkdir()

    event_a = new_event("state", value="working", companion_id="alpha")
    event_b = new_event("state", value="error", companion_id="beta")
    append_jsonl(root / "inbox.jsonl", event_a)
    append_jsonl(root / "inbox.jsonl", event_b)

    runtime_a = Runtime(root, companion_id="alpha")
    runtime_b = Runtime(root, companion_id="beta")
    runtime_a.process_once()
    runtime_b.process_once()

    assert runtime_a.state["state"] == "working"
    assert runtime_b.state["state"] == "error"
