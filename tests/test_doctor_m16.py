"""Tests for Doctor M16 — standardized outcomes and check-based architecture."""

import json
from pathlib import Path

from companion.doctor import (
    CheckResult,
    DoctorReport,
    Outcome,
    run_checks,
    run_checks_report,
    _check_filesystem,
    _check_event_pipeline,
    _check_pack,
    _check_reminders,
    _check_timeline,
    _check_personality,
    _check_platform,
    _check_security,
)


# ── Outcome enum ─────────────────────────────────────────────────────────────

def test_outcome_ordering():
    assert Outcome.READY < Outcome.UNKNOWN < Outcome.NEEDS_ACTION < Outcome.BLOCKED
    assert Outcome.BLOCKED > Outcome.NEEDS_ACTION > Outcome.UNKNOWN > Outcome.READY
    assert Outcome.READY <= Outcome.READY
    assert Outcome.BLOCKED >= Outcome.BLOCKED


def test_outcome_values():
    assert Outcome.READY.value == "READY"
    assert Outcome.NEEDS_ACTION.value == "NEEDS_ACTION"
    assert Outcome.BLOCKED.value == "BLOCKED"
    assert Outcome.UNKNOWN.value == "UNKNOWN"


# ── CheckResult ──────────────────────────────────────────────────────────────

def test_check_result_to_dict():
    cr = CheckResult(section="test", outcome=Outcome.READY, message="all good")
    d = cr.to_dict()
    assert d["section"] == "test"
    assert d["outcome"] == "READY"
    assert d["message"] == "all good"


def test_check_result_with_issues():
    cr = CheckResult(section="test", outcome=Outcome.NEEDS_ACTION, issues=["fix this"])
    d = cr.to_dict()
    assert d["issues"] == ["fix this"]


# ── DoctorReport ─────────────────────────────────────────────────────────────

def test_report_global_outcome_worst():
    report = DoctorReport(checks=[
        CheckResult(section="a", outcome=Outcome.READY),
        CheckResult(section="b", outcome=Outcome.NEEDS_ACTION),
        CheckResult(section="c", outcome=Outcome.READY),
    ])
    assert report.outcome == Outcome.NEEDS_ACTION


def test_report_global_outcome_blocked():
    report = DoctorReport(checks=[
        CheckResult(section="a", outcome=Outcome.READY),
        CheckResult(section="b", outcome=Outcome.BLOCKED),
    ])
    assert report.outcome == Outcome.BLOCKED


def test_report_ok_true_when_all_ready_or_unknown():
    report = DoctorReport(checks=[
        CheckResult(section="a", outcome=Outcome.READY),
        CheckResult(section="b", outcome=Outcome.UNKNOWN),
    ])
    assert report.ok is True


def test_report_ok_false_when_needs_action():
    report = DoctorReport(checks=[
        CheckResult(section="a", outcome=Outcome.READY),
        CheckResult(section="b", outcome=Outcome.NEEDS_ACTION),
    ])
    assert report.ok is False


def test_report_ok_false_when_blocked():
    report = DoctorReport(checks=[
        CheckResult(section="a", outcome=Outcome.BLOCKED),
    ])
    assert report.ok is False


def test_report_ok_true_when_empty():
    report = DoctorReport(checks=[])
    assert report.ok is True  # no bad checks = ok


def test_report_issues_aggregated():
    report = DoctorReport(checks=[
        CheckResult(section="a", outcome=Outcome.NEEDS_ACTION, issues=["a1"]),
        CheckResult(section="b", outcome=Outcome.BLOCKED, issues=["b1", "b2"]),
    ])
    assert report.issues == ["a1", "b1", "b2"]


def test_report_summary_lines():
    report = DoctorReport(checks=[
        CheckResult(section="fs", outcome=Outcome.READY, message="OK"),
        CheckResult(section="net", outcome=Outcome.BLOCKED, message="down"),
    ])
    lines = report.summary_lines()
    assert len(lines) == 2
    assert "\u2713" in lines[0]  # checkmark for READY
    assert "\u2718" in lines[1]  # X for BLOCKED


def test_report_to_dict():
    report = DoctorReport(checks=[
        CheckResult(section="x", outcome=Outcome.READY),
    ])
    d = report.to_dict()
    assert d["outcome"] == "READY"
    assert d["ok"] is True
    assert len(d["checks"]) == 1


# ── Individual checks ────────────────────────────────────────────────────────

def test_filesystem_fresh_root(tmp_path):
    result = _check_filesystem(tmp_path)
    assert result.outcome == Outcome.READY
    assert result.section == "filesystem"
    assert result.details["writable"] is True


def test_filesystem_corrupt_state(tmp_path):
    (tmp_path / "state.json").write_text("{bad", encoding="utf-8")
    result = _check_filesystem(tmp_path)
    assert result.outcome == Outcome.NEEDS_ACTION
    assert any("state.json" in i for i in result.issues)


def test_filesystem_corrupt_backup_reported(tmp_path):
    (tmp_path / "state.json.corrupt").write_text("{}", encoding="utf-8")
    result = _check_filesystem(tmp_path)
    assert any("corrupt" in i for i in result.issues)


def test_event_pipeline_fresh_root(tmp_path):
    result = _check_event_pipeline(tmp_path)
    assert result.outcome == Outcome.READY
    assert "no inbox" in result.message


def test_event_pipeline_healthy(tmp_path):
    from companion.queue import append_jsonl
    from companion.protocol import new_event
    append_jsonl(tmp_path / "inbox.jsonl", new_event("say", text="hola"))
    result = _check_event_pipeline(tmp_path)
    assert result.outcome == Outcome.READY
    assert result.details["inbox_lines"] == 1


def test_event_pipeline_outbox_errors(tmp_path):
    from companion.queue import append_jsonl
    from companion.protocol import new_event
    append_jsonl(tmp_path / "inbox.jsonl", new_event("say", text="hola"))
    outbox = tmp_path / "outbox.jsonl"
    outbox.write_text(json.dumps({"version": "companion-event-v1", "status": "error", "detail": "bad"}) + "\n", encoding="utf-8")
    result = _check_event_pipeline(tmp_path)
    assert result.outcome == Outcome.NEEDS_ACTION
    assert result.details["outbox_errors"] == 1


def test_reminders_reports_overdue_records(tmp_path):
    (tmp_path / "reminders.json").write_text(json.dumps([{
        "id": "rem-1",
        "due_at": "2020-01-01T00:00:00+00:00",
        "message": "old",
        "status": "pending",
        "created_at": "2019-12-31T00:00:00+00:00",
        "ttl": 8,
        "mood": None,
        "companion_id": None,
        "recurrence": None,
        "weekdays": None,
        "snoozed_until": None,
    }]), encoding="utf-8")
    result = _check_reminders(tmp_path)
    assert result.details["overdue"] == 1
    assert result.outcome == Outcome.NEEDS_ACTION


def test_pack_no_config(tmp_path):
    result = _check_pack(tmp_path)
    assert result.outcome == Outcome.UNKNOWN
    assert "no pack configured" in result.message


def test_pack_valid(tmp_path):
    pack_dir = tmp_path / "cat"
    pack_dir.mkdir()
    (pack_dir / "idle.png").write_bytes(b"img")
    (pack_dir / "manifest.json").write_text(
        '{"id":"cat","name":"Cat","animations":{"idle":"idle.png"}}', encoding="utf-8"
    )
    (tmp_path / "companion.toml").write_text(
        f'[companion]\npack = "cat"', encoding="utf-8"
    )
    result = _check_pack(tmp_path)
    assert result.outcome == Outcome.READY
    assert result.details["pack_id"] == "cat"


def test_pack_invalid(tmp_path):
    pack_dir = tmp_path / "bad"
    pack_dir.mkdir()
    (pack_dir / "manifest.json").write_text('{"id":""}', encoding="utf-8")
    (tmp_path / "companion.toml").write_text(
        f'[companion]\npack = "bad"', encoding="utf-8"
    )
    result = _check_pack(tmp_path)
    assert result.outcome == Outcome.NEEDS_ACTION
    assert "invalid" in result.message


def test_reminders_clean_root(tmp_path):
    result = _check_reminders(tmp_path)
    assert result.outcome == Outcome.READY
    assert "no reminders" in result.message


def test_reminders_healthy(tmp_path):
    from companion.scheduled import ReminderStore
    store = ReminderStore(tmp_path / "reminders.json")
    store.create(due_at="2099-01-01T00:00:00Z", message="test")
    result = _check_reminders(tmp_path)
    assert result.outcome == Outcome.READY
    assert result.details["pending"] == 1


def test_timeline_clean_root(tmp_path):
    result = _check_timeline(tmp_path)
    assert result.outcome == Outcome.READY
    assert "no timeline" in result.message


def test_timeline_healthy(tmp_path):
    from companion.timeline import ActivityTimeline, TimelineEntry
    tl = ActivityTimeline(tmp_path)
    tl.append(TimelineEntry(timestamp="t1", event_type="say", agent="cli"))
    result = _check_timeline(tmp_path)
    assert result.outcome == Outcome.READY
    assert result.details["total"] == 1


def test_personality_defaults(tmp_path):
    result = _check_personality(tmp_path)
    assert result.outcome == Outcome.READY
    assert "defaults" in result.message


def test_personality_valid(tmp_path):
    from companion.personality import PersonalityStore, PersonalityProfile
    store = PersonalityStore(tmp_path)
    store.save(PersonalityProfile(tone="formal"))
    result = _check_personality(tmp_path)
    assert result.outcome == Outcome.READY
    assert result.details["tone"] == "formal"


def test_personality_bad_tone(tmp_path):
    (tmp_path / "personality.json").write_text('{"tone": "weird"}', encoding="utf-8")
    result = _check_personality(tmp_path)
    assert result.outcome == Outcome.NEEDS_ACTION
    assert any("unknown tone" in i for i in result.issues)


def test_platform_ready():
    result = _check_platform()
    assert result.outcome == Outcome.READY
    assert result.details["platform"]


def test_security_always_ready():
    result = _check_security()
    assert result.outcome == Outcome.READY
    assert "shell" in result.message.lower() or "shell" in str(result.details)


# ── run_checks backward compatibility ────────────────────────────────────────

def test_run_checks_returns_legacy_fields(tmp_path):
    report = run_checks(tmp_path)
    assert "ok" in report
    assert "issues" in report
    assert "files" in report
    assert "tk" in report
    assert "optional" in report
    assert "security" in report
    assert "outcome" in report


def test_run_checks_ok_on_fresh_root(tmp_path):
    report = run_checks(tmp_path)
    assert report["ok"] is True  # UNKNOWN is acceptable, not a failure
    # outcome may be UNKNOWN (pack/personality not configured) — that's fine


def test_run_checks_not_ok_on_corrupt(tmp_path):
    (tmp_path / "state.json").write_text("{bad", encoding="utf-8")
    report = run_checks(tmp_path)
    assert report["ok"] is False
    assert report["outcome"] in ("NEEDS_ACTION", "BLOCKED")


def test_run_checks_has_checks_array(tmp_path):
    report = run_checks(tmp_path)
    assert "checks" in report
    assert len(report["checks"]) == 8  # 8 sections
    sections = [c["section"] for c in report["checks"]]
    assert "filesystem" in sections
    assert "event-pipeline" in sections
    assert "pack" in sections
    assert "reminders" in sections
    assert "timeline" in sections
    assert "personality" in sections
    assert "platform" in sections
    assert "security" in sections


# ── run_checks_report (structured) ───────────────────────────────────────────

def test_run_checks_report_returns_doctor_report(tmp_path):
    report = run_checks_report(tmp_path)
    assert isinstance(report, DoctorReport)
    assert report.ok is True
    assert len(report.checks) == 8
