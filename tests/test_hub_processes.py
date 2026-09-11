import json
import subprocess

import pytest

from companion.hub.models import CompanionRecord
from companion.hub.processes import ProcessManager, ProcessStatus


class FakeProcess:
    def __init__(self, *, returncode=None, terminate_error=None, wait_error=None):
        self.returncode = returncode
        self.terminate_error = terminate_error
        self.wait_error = wait_error
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_timeouts = []

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminate_calls += 1
        if self.terminate_error:
            raise self.terminate_error

    def wait(self, timeout):
        self.wait_timeouts.append(timeout)
        if self.wait_error:
            raise self.wait_error
        self.returncode = 0

    def kill(self):
        self.kill_calls += 1
        self.returncode = -9


class FakePopen:
    def __init__(self, process=None, error=None):
        self.calls = []
        self.process = process or FakeProcess()
        self.error = error

    def __call__(self, args):
        self.calls.append(args)
        if self.error:
            raise self.error
        return self.process


@pytest.fixture
def record(tmp_path):
    return CompanionRecord(
        companion_id="malbolge",
        name="Malbolge",
        pack_root=tmp_path / "packs" / "malbolge",
        runtime_root=tmp_path / "runtimes" / "malbolge",
    )


@pytest.fixture
def fake_popen():
    return FakePopen()


def test_manager_starts_with_independent_root_and_pack(fake_popen, record):
    manager = ProcessManager(["companion"], popen=fake_popen)

    manager.start(record)

    assert fake_popen.calls[0] == [
        "companion",
        "--root",
        str(record.runtime_root),
        "gui",
        "--pack",
        str(record.pack_root),
    ]
    assert manager.status(record) is ProcessStatus.RUNNING


def test_manager_never_stops_unowned_process(record):
    manager = ProcessManager(["companion"])

    assert manager.stop(record) is False
    assert manager.status(record) is ProcessStatus.UNMANAGED


def test_show_and_hide_publish_events_to_the_record_runtime(fake_popen, record):
    manager = ProcessManager(["companion"], popen=fake_popen)
    manager.start(record)

    manager.hide(record)
    assert manager.status(record) is ProcessStatus.HIDDEN
    manager.show(record)

    events = [json.loads(line) for line in (record.runtime_root / "inbox.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["type"] for event in events] == ["hide", "summon"]
    assert all(event["companion_id"] == record.companion_id for event in events)
    assert manager.status(record) is ProcessStatus.RUNNING


def test_exited_handle_reports_exited(fake_popen, record):
    fake_popen.process.returncode = 1
    manager = ProcessManager(["companion"], popen=fake_popen)
    manager.start(record)

    assert manager.status(record) is ProcessStatus.EXITED


def test_repeated_stop_is_harmless_and_stops_only_owned_handle(fake_popen, record):
    manager = ProcessManager(["companion"], popen=fake_popen)
    manager.start(record)

    assert manager.stop(record) is True
    assert manager.stop(record) is False

    assert fake_popen.process.terminate_calls == 1
    assert fake_popen.process.wait_timeouts == [3]
    assert fake_popen.process.kill_calls == 0
    assert manager.status(record) is ProcessStatus.STOPPED


def test_stop_kills_only_its_owned_handle_after_timeout(record):
    process = FakeProcess(wait_error=subprocess.TimeoutExpired(["companion"], 3))
    fake_popen = FakePopen(process=process)
    manager = ProcessManager(["companion"], popen=fake_popen)
    manager.start(record)

    assert manager.stop(record) is True

    assert process.terminate_calls == 1
    assert process.wait_timeouts == [3]
    assert process.kill_calls == 1


def test_failed_termination_keeps_the_owned_handle_for_retry(record):
    process = FakeProcess(terminate_error=OSError("termination failed"))
    manager = ProcessManager(["companion"], popen=FakePopen(process=process))
    manager.start(record)

    with pytest.raises(OSError, match="termination failed"):
        manager.stop(record)

    assert manager.status(record) is ProcessStatus.RUNNING
    process.terminate_error = None
    assert manager.stop(record) is True
    assert process.terminate_calls == 2


def test_failed_start_leaves_no_owned_entry(record):
    fake_popen = FakePopen(error=OSError("cannot start"))
    manager = ProcessManager(["companion"], popen=fake_popen)

    with pytest.raises(OSError, match="cannot start"):
        manager.start(record)

    assert manager.status(record) is ProcessStatus.UNMANAGED
    assert manager.stop(record) is False
