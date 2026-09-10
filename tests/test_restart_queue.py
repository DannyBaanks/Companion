from pathlib import Path

from companion.protocol import new_event
from companion.queue import append_jsonl
from companion.runtime import Runtime


def test_pending_queue_survives_runtime_restart(tmp_path: Path):
    now = [100.0]
    root = tmp_path / "companion"
    first = Runtime(root, clock=lambda: now[0])
    append_jsonl(first.inbox, new_event("say", text="visible", ttl=10, priority=0))
    append_jsonl(first.inbox, new_event("say", text="pending", ttl=10, priority=-1))
    assert first.process_once() == 2
    del first

    restarted = Runtime(root, clock=lambda: now[0])
    now[0] = 111.0
    restarted.expire_messages()
    assert restarted.state["message"]["text"] == "pending"


def test_preempted_message_priority_and_fifo_survive_restart(tmp_path: Path):
    now = [100.0]
    root = tmp_path / "companion"
    runtime = Runtime(root, clock=lambda: now[0])
    for text, priority in (("low", 0), ("high", 10), ("same-first", 0), ("same-second", 0)):
        append_jsonl(runtime.inbox, new_event("say", text=text, ttl=1, priority=priority))
    assert runtime.process_once() == 4

    restarted = Runtime(root, clock=lambda: now[0])
    assert restarted.state["message"]["text"] == "high"
    for expected in ("low", "same-first", "same-second"):
        now[0] += 2
        restarted.expire_messages()
        assert restarted.state["message"]["text"] == expected


def test_queued_ttl_starts_after_restart_activation(tmp_path: Path):
    now = [100.0]
    root = tmp_path / "companion"
    runtime = Runtime(root, clock=lambda: now[0])
    append_jsonl(runtime.inbox, new_event("say", text="active", ttl=100, priority=1))
    append_jsonl(runtime.inbox, new_event("say", text="waiting", ttl=5, priority=0))
    assert runtime.process_once() == 2

    now[0] = 1000.0
    restarted = Runtime(root, clock=lambda: now[0])
    assert restarted.state["message"]["text"] == "active"
    now[0] = 1101.0
    restarted.expire_messages()
    assert restarted.state["message"]["text"] == "waiting"
    assert restarted.state["message"]["expires_at"] == 1106.0


def test_legacy_state_without_queue_loads_safely(tmp_path: Path):
    root = tmp_path / "companion"
    root.mkdir()
    (root / "state.json").write_text(
        '{"visible": true, "state": "idle", "mood": "idle", '
        '"position": "bottom-right", "message": null, "message_sequence": 2}',
        encoding="utf-8",
    )
    runtime = Runtime(root)
    assert runtime._message_queue == []


def test_companion_queues_are_isolated_across_restart(tmp_path: Path):
    now = [100.0]
    root = tmp_path / "companion"
    for companion in ("alpha", "beta"):
        append_jsonl(root / "inbox.jsonl", new_event("say", text=f"{companion} active", companion_id=companion, ttl=1))
        append_jsonl(root / "inbox.jsonl", new_event("say", text=f"{companion} next", companion_id=companion, ttl=1))
    alpha = Runtime(root, companion_id="alpha", clock=lambda: now[0])
    beta = Runtime(root, companion_id="beta", clock=lambda: now[0])
    assert alpha.process_once() == 4
    assert beta.process_once() == 4

    now[0] = 102.0
    alpha = Runtime(root, companion_id="alpha", clock=lambda: now[0])
    beta = Runtime(root, companion_id="beta", clock=lambda: now[0])
    alpha.expire_messages()
    beta.expire_messages()
    assert alpha.state["message"]["text"] == "alpha next"
    assert beta.state["message"]["text"] == "beta next"
