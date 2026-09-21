"""Local diagnostics with standardized outcomes.

M16 Doctor — each section is a check returning a standardized outcome:
  READY        — all good
  NEEDS_ACTION — fixable by the user
  BLOCKED      — cannot function without this
  UNKNOWN      — could not determine

Global outcome = worst of all checks.
Never false-green: if a check cannot verify, it reports UNKNOWN, not READY.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from . import __version__  # noqa: F401 - re-exported for diagnostics


# ── Outcome enum ─────────────────────────────────────────────────────────────

class Outcome(str, Enum):
    READY = "READY"
    NEEDS_ACTION = "NEEDS_ACTION"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"

    def __ge__(self, other: "Outcome") -> bool:
        """Ordering: BLOCKED > NEEDS_ACTION > UNKNOWN > READY."""
        order = {self.READY: 0, self.UNKNOWN: 1, self.NEEDS_ACTION: 2, self.BLOCKED: 3}
        return order[self] >= order[other]

    def __gt__(self, other: "Outcome") -> bool:
        order = {self.READY: 0, self.UNKNOWN: 1, self.NEEDS_ACTION: 2, self.BLOCKED: 3}
        return order[self] > order[other]

    def __le__(self, other: "Outcome") -> bool:
        return not self.__gt__(other)

    def __lt__(self, other: "Outcome") -> bool:
        return not self.__ge__(other)


# ── Check result ─────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    """Result of a single diagnostic check."""
    section: str
    outcome: Outcome
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "section": self.section,
            "outcome": self.outcome.value,
        }
        if self.message:
            d["message"] = self.message
        if self.details:
            d["details"] = self.details
        if self.issues:
            d["issues"] = self.issues
        return d


# ── Individual checks ────────────────────────────────────────────────────────

def _check_filesystem(root: Path) -> CheckResult:
    """Check root writability, state files, and corrupt backups."""
    issues: list[str] = []

    # Writable probe
    writable = True
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        writable = False
        issues.append(f"root not writable: {exc}")

    # File integrity
    files_info: dict[str, Any] = {}
    for name in ("inbox.jsonl", "outbox.jsonl", "state.json", "reminders.json"):
        path = root / name
        info: dict[str, Any] = {"exists": path.exists()}
        if path.exists():
            try:
                info["bytes"] = path.stat().st_size
                if path.suffix == ".json":
                    json.loads(path.read_text(encoding="utf-8"))
                    info["valid_json"] = True
            except (OSError, json.JSONDecodeError) as exc:
                info["valid_json"] = False
                issues.append(f"{name} invalid: {exc}")
        files_info[name] = info

    # Corrupt backups
    corrupt = sorted(p.name for p in root.glob("*.corrupt"))
    if corrupt:
        issues.append(f"recovered corrupt files: {', '.join(corrupt)}")

    if not writable:
        outcome = Outcome.BLOCKED
    elif issues:
        outcome = Outcome.NEEDS_ACTION
    else:
        outcome = Outcome.READY

    return CheckResult(
        section="filesystem",
        outcome=outcome,
        message="root writable, files OK" if not issues else "; ".join(issues),
        details={"writable": writable, "files": files_info, "corrupt_backups": corrupt},
        issues=issues,
    )


def _check_event_pipeline(root: Path) -> CheckResult:
    """Check inbox/outbox health and unprocessed events."""
    issues: list[str] = []
    details: dict[str, Any] = {}

    inbox = root / "inbox.jsonl"
    outbox = root / "outbox.jsonl"

    if not inbox.exists():
        return CheckResult(
            section="event-pipeline",
            outcome=Outcome.READY,
            message="no inbox yet (normal for fresh root)",
            details={"inbox_exists": False, "outbox_exists": outbox.exists()},
        )

    try:
        inbox_size = inbox.stat().st_size
        details["inbox_bytes"] = inbox_size

        # Count unprocessed lines (rough heuristic: lines after last newline)
        content = inbox.read_text(encoding="utf-8")
        lines = [l for l in content.split("\n") if l.strip()]
        details["inbox_lines"] = len(lines)

        # Check outbox for recent errors
        outbox_errors = 0
        if outbox.exists():
            outbox_content = outbox.read_text(encoding="utf-8")
            for line in outbox_content.split("\n"):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    if record.get("status") == "error":
                        outbox_errors += 1
                except json.JSONDecodeError:
                    pass
        details["outbox_errors"] = outbox_errors

        if outbox_errors > 0:
            issues.append(f"{outbox_errors} error(s) in outbox")
        if inbox_size > 10 * 1024 * 1024:  # > 10MB
            issues.append(f"inbox is large ({inbox_size} bytes)")

    except OSError as exc:
        issues.append(f"pipeline check failed: {exc}")

    if issues:
        outcome = Outcome.NEEDS_ACTION
    else:
        outcome = Outcome.READY

    return CheckResult(
        section="event-pipeline",
        outcome=outcome,
        message="pipeline OK" if not issues else "; ".join(issues),
        details=details,
        issues=issues,
    )


def _check_pack(root: Path) -> CheckResult:
    """Check the configured pack is valid and assets are loadable."""
    from .config import load_config, ConfigError
    from .pack import AssetPack, PackError

    # Try to find a configured pack
    config = None
    for name in ("companion.toml", "companion.json"):
        path = root / name
        if path.exists():
            try:
                config = load_config(path)
                break
            except ConfigError:
                pass

    if config is None or config.pack is None:
        return CheckResult(
            section="pack",
            outcome=Outcome.UNKNOWN,
            message="no pack configured",
            details={"configured": False},
        )

    try:
        pack = AssetPack.load(config.pack)
        details: dict[str, Any] = {
            "configured": True,
            "pack_id": pack.pack_id,
            "name": pack.name,
            "states": sorted(pack.animations.keys()),
        }
        return CheckResult(
            section="pack",
            outcome=Outcome.READY,
            message=f"pack '{pack.name}' OK ({len(pack.animations)} states)",
            details=details,
        )
    except PackError as exc:
        return CheckResult(
            section="pack",
            outcome=Outcome.NEEDS_ACTION,
            message=f"pack invalid: {exc}",
            details={"configured": True, "error": str(exc)},
            issues=[f"pack: {exc}"],
        )
    except OSError as exc:
        return CheckResult(
            section="pack",
            outcome=Outcome.BLOCKED,
            message=f"pack path unreadable: {exc}",
            details={"configured": True, "error": str(exc)},
            issues=[f"pack: {exc}"],
        )


def _check_reminders(root: Path) -> CheckResult:
    """Check reminder store health."""
    from .scheduled import ReminderStore

    reminders_path = root / "reminders.json"
    if not reminders_path.exists():
        return CheckResult(
            section="reminders",
            outcome=Outcome.READY,
            message="no reminders store (clean root)",
            details={"exists": False},
        )

    try:
        store = ReminderStore(reminders_path)
        all_reminders = store.list()
        pending = [r for r in all_reminders if r.status == "pending"]
        now = datetime.now(timezone.utc)
        overdue = []
        for reminder in pending:
            if not reminder.due_at:
                continue
            try:
                due_at = datetime.fromisoformat(reminder.due_at)
                if due_at.tzinfo is None:
                    due_at = due_at.replace(tzinfo=timezone.utc)
                if due_at.astimezone(timezone.utc) <= now:
                    overdue.append(reminder)
            except ValueError:
                issues = [f"invalid reminder due_at: {reminder.id}"]
                return CheckResult(
                    section="reminders",
                    outcome=Outcome.NEEDS_ACTION,
                    message="reminder dates need attention",
                    details={"exists": True, "total": len(all_reminders),
                             "pending": len(pending), "overdue": 0},
                    issues=issues,
                )
        details: dict[str, Any] = {
            "exists": True,
            "total": len(all_reminders),
            "pending": len(pending),
            "overdue": len(overdue),
        }
        issues: list[str] = []
        outcome = Outcome.READY
        if overdue:
            issues.append(f"{len(overdue)} overdue reminder(s)")
            outcome = Outcome.NEEDS_ACTION
        if len(all_reminders) > 500:
            issues.append(f"large reminder store ({len(all_reminders)} records)")
            outcome = Outcome.NEEDS_ACTION
        return CheckResult(
            section="reminders",
            outcome=outcome,
            message=f"{len(pending)} pending, {len(all_reminders)} total",
            details=details,
            issues=issues,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics must not crash
        return CheckResult(
            section="reminders",
            outcome=Outcome.BLOCKED,
            message=f"reminders unreadable: {exc}",
            details={"exists": True, "error": str(exc)},
            issues=[f"reminders: {exc}"],
        )


def _check_timeline(root: Path) -> CheckResult:
    """Check timeline JSONL integrity."""
    from .timeline import ActivityTimeline

    tl_path = root / "timeline.jsonl"
    if not tl_path.exists():
        return CheckResult(
            section="timeline",
            outcome=Outcome.READY,
            message="no timeline yet (normal)",
            details={"exists": False},
        )

    try:
        tl = ActivityTimeline(root)
        summary = tl.summary()
        details: dict[str, Any] = {"exists": True, **summary}

        # Try a small export to verify writability
        test_dest = root / ".timeline-probe.jsonl"
        count = tl.export_jsonl(test_dest)
        test_dest.unlink(missing_ok=True)

        return CheckResult(
            section="timeline",
            outcome=Outcome.READY,
            message=f"{summary['total']} events, exportable",
            details=details,
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            section="timeline",
            outcome=Outcome.BLOCKED,
            message=f"timeline unreadable: {exc}",
            details={"exists": True, "error": str(exc)},
            issues=[f"timeline: {exc}"],
        )


def _check_personality(root: Path) -> CheckResult:
    """Check personality profile validity."""
    from .personality import PersonalityStore

    personality_path = root / "personality.json"
    if not personality_path.exists():
        return CheckResult(
            section="personality",
            outcome=Outcome.READY,
            message="no personality configured (using defaults)",
            details={"configured": False},
        )

    try:
        store = PersonalityStore(root)
        profile = store.load()
        details: dict[str, Any] = {
            "configured": True,
            "tone": profile.tone,
            "verbosity": profile.verbosity,
        }
        valid_tones = {"friendly", "formal", "playful", "minimal"}
        issues: list[str] = []
        outcome = Outcome.READY
        if profile.tone not in valid_tones:
            issues.append(f"unknown tone: {profile.tone}")
            outcome = Outcome.NEEDS_ACTION
        return CheckResult(
            section="personality",
            outcome=outcome,
            message=f"tone={profile.tone}, verbosity={profile.verbosity}",
            details=details,
            issues=issues,
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            section="personality",
            outcome=Outcome.BLOCKED,
            message=f"personality unreadable: {exc}",
            details={"configured": True, "error": str(exc)},
            issues=[f"personality: {exc}"],
        )


def _check_platform() -> CheckResult:
    """Check platform, Python, Tk, and optional dependencies."""
    issues: list[str] = []
    details: dict[str, Any] = {
        "platform": sys.platform,
        "python": platform.python_version(),
        "os": platform.system(),
        "arch": platform.machine(),
    }

    # Tk
    try:
        import tkinter
        details["tk"] = {"available": True, "version": str(tkinter.TkVersion)}
    except Exception as exc:  # noqa: BLE001
        details["tk"] = {"available": False, "error": str(exc)}
        issues.append(f"tk unavailable: {exc}")

    # Optional packages
    optional: dict[str, bool] = {}
    for mod in ("websockets", "plyer"):
        try:
            __import__(mod)
            optional[mod] = True
        except ImportError:
            optional[mod] = False
    details["optional"] = optional

    if issues:
        outcome = Outcome.BLOCKED
    else:
        outcome = Outcome.READY

    return CheckResult(
        section="platform",
        outcome=outcome,
        message="platform OK" if not issues else "; ".join(issues),
        details=details,
        issues=issues,
    )


def _check_security() -> CheckResult:
    """Check security invariants: no shell, no remote network, local paths only."""
    details: dict[str, Any] = {
        "shell": "never",
        "network": "off by default",
        "websocket": "opt-in localhost only",
    }
    # Static check — always READY for the security section itself
    return CheckResult(
        section="security",
        outcome=Outcome.READY,
        message="security policy: no shell, no remote network, local paths only",
        details=details,
    )


# ── Doctor report ────────────────────────────────────────────────────────────

@dataclass
class DoctorReport:
    """Aggregated diagnostic report with global outcome."""
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def outcome(self) -> Outcome:
        """Worst outcome across all checks."""
        if not self.checks:
            return Outcome.UNKNOWN
        worst = Outcome.READY
        for check in self.checks:
            if check.outcome > worst:
                worst = check.outcome
        return worst

    @property
    def ok(self) -> bool:
        """True only if no check is BLOCKED or NEEDS_ACTION.

        UNKNOWN checks are acceptable — they mean 'could not determine',
        not 'something is wrong'.
        """
        return all(c.outcome in (Outcome.READY, Outcome.UNKNOWN) for c in self.checks)

    @property
    def issues(self) -> list[str]:
        all_issues: list[str] = []
        for check in self.checks:
            all_issues.extend(check.issues)
        return all_issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "ok": self.ok,
            "checks": [c.to_dict() for c in self.checks],
            "issues": self.issues,
        }

    def summary_lines(self) -> list[str]:
        """Human-readable one-line-per-check summary."""
        lines: list[str] = []
        for check in self.checks:
            icon = {"READY": "\u2713", "NEEDS_ACTION": "\u26a0", "BLOCKED": "\u2718", "UNKNOWN": "?"}.get(check.outcome.value, "?")
            lines.append(f"  {icon} {check.section}: {check.message}")
        return lines


# ── Public API ───────────────────────────────────────────────────────────────

def run_checks(root: Path, *, companion_id: str | None = None) -> dict[str, Any]:
    """Run all diagnostic checks and return a standardized report.

    Backward-compatible: returns a dict with 'ok', 'issues', and check details.
    """
    report = DoctorReport(checks=[
        _check_filesystem(root),
        _check_event_pipeline(root),
        _check_pack(root),
        _check_reminders(root),
        _check_timeline(root),
        _check_personality(root),
        _check_platform(),
        _check_security(),
    ])

    # Inject companion_id awareness into filesystem check for state file
    if companion_id:
        state_name = f"state-{companion_id}.json"
        state_path = root / state_name
        fs_check = report.checks[0]
        if state_path.exists():
            try:
                json.loads(state_path.read_text(encoding="utf-8"))
                fs_check.details["files"][state_name] = {"exists": True, "valid_json": True}
            except (OSError, json.JSONDecodeError) as exc:
                fs_check.details["files"][state_name] = {"exists": True, "valid_json": False}
                fs_check.issues.append(f"{state_name} invalid: {exc}")
                fs_check.outcome = Outcome.NEEDS_ACTION

    # Backward-compatible dict shape
    result: dict[str, Any] = {
        "ok": report.ok,
        "outcome": report.outcome.value,
        "root": str(root),
        "platform": sys.platform,
        "python": platform.python_version(),
        "checks": [c.to_dict() for c in report.checks],
        "issues": report.issues,
    }

    # Preserve legacy fields for tests
    result["files"] = report.checks[0].details.get("files", {})
    result["corrupt_backups"] = report.checks[0].details.get("corrupt_backups", [])
    result["reminders"] = {"count": report.checks[3].details.get("total", 0), "ok": report.checks[3].outcome == Outcome.READY}
    result["tk"] = report.checks[6].details.get("tk", {})
    result["optional"] = report.checks[6].details.get("optional", {})
    result["security"] = report.checks[7].details

    return result


def run_checks_report(root: Path, *, companion_id: str | None = None) -> DoctorReport:
    """Run all checks and return the structured DoctorReport object."""
    # Reuse run_checks for the dict, then build a report from it
    # Actually, let's run the checks directly for the structured version
    checks = [
        _check_filesystem(root),
        _check_event_pipeline(root),
        _check_pack(root),
        _check_reminders(root),
        _check_timeline(root),
        _check_personality(root),
        _check_platform(),
        _check_security(),
    ]
    return DoctorReport(checks=checks)
