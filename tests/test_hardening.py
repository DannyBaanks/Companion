import json
from pathlib import Path

from companion.cli import main
from companion.doctor import run_checks
from companion.logs import emit, read_tail
from companion.paths import discover_config, resolve_root
from companion.queue import append_jsonl
from companion.protocol import new_event
from companion.runtime import Runtime
from companion.scheduled import ReminderStore
from companion.storage import atomic_write_json, read_json_with_recovery


def test_resolve_root_prefers_explicit_and_env(tmp_path: Path, monkeypatch):
    explicit = resolve_root(str(tmp_path / "a"))
    assert explicit == (tmp_path / "a").resolve()
    monkeypatch.setenv("COMPANION_ROOT", str(tmp_path / "env"))
    assert resolve_root(None) == (tmp_path / "env").resolve()
    monkeypatch.delenv("COMPANION_ROOT")
    assert resolve_root(None).name == ".companion"


def test_discover_config(tmp_path: Path):
    assert discover_config(tmp_path) is None
    (tmp_path / "companion.json").write_text("{}", encoding="utf-8")
    assert discover_config(tmp_path) is not None


def test_atomic_write_and_corrupt_recovery(tmp_path: Path):
    target = tmp_path / "state.json"
    atomic_write_json(target, {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    target.write_text("{broken", encoding="utf-8")
    data, recovered = read_json_with_recovery(target, default={})
    assert recovered is True
    assert data == {}
    assert (tmp_path / "state.json.corrupt").exists()


def test_runtime_persists_offset_across_restart(tmp_path: Path):
    append_jsonl(tmp_path / "inbox.jsonl", new_event("say", text="hola"))
    first = Runtime(tmp_path)
    assert first.process_once() == 1
    second = Runtime(tmp_path)
    assert second.process_once() == 0
    assert second.state["message"]["text"] == "hola"


def test_runtime_recovers_corrupt_state(tmp_path: Path):
    (tmp_path / "state.json").write_text("{broken", encoding="utf-8")
    runtime = Runtime(tmp_path)
    assert runtime.recovered is True
    assert runtime.state["state"] == "idle"
    assert (tmp_path / "state.json.corrupt").exists()


def test_reminder_store_skips_bad_rows(tmp_path: Path):
    (tmp_path / "reminders.json").write_text('[{"id": "x"}, {"nope": 1}]', encoding="utf-8")
    assert ReminderStore(tmp_path / "reminders.json").list() == []


def test_logs_roundtrip(tmp_path: Path):
    emit(tmp_path, "info", "test-event", detail="x")
    tail = read_tail(tmp_path, limit=5)
    assert tail and tail[-1]["event"] == "test-event"


def test_doctor_ok_and_bad_state(tmp_path: Path):
    report = run_checks(tmp_path)
    assert report["ok"] is True
    (tmp_path / "state.json").write_text("{broken", encoding="utf-8")
    report = run_checks(tmp_path)
    assert report["ok"] is False
    assert any("state.json" in issue for issue in report["issues"])


def test_cli_version_path_doctor_logs(tmp_path: Path, capsys):
    assert main(["--version"]) == 0
    assert main(["--root", str(tmp_path), "path"]) == 0
    assert "root" in capsys.readouterr().out
    assert main(["--root", str(tmp_path), "doctor"]) == 0
    assert main(["--root", str(tmp_path), "logs", "--tail", "5"]) == 0


def test_security_no_shell_or_remote_network():
    root = Path(__file__).resolve().parents[1] / "src" / "companion"
    forbidden = ["shell=True", "os.system(", "urllib.request", "requests.", "socket.bind", "Popen("]
    hits = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                hits.append(f"{path.name}:{marker}")
    assert hits == []
    websocket_src = (root / "adapters" / "websocket.py").read_text(encoding="utf-8")
    assert "127.0.0.1" in websocket_src
