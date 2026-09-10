"""Command-line interface for publishing companion events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .protocol import POSITIONS, STATES, new_event
from .config import ConfigError, load_config
from .doctor import run_checks
from .logs import emit as log_emit, read_tail
from .pack import AssetPack, PackError
from .paths import default_data_dir, discover_config, platform_name, resolve_root
from .queue import append_jsonl
from .render_request import RenderRequestError, load_render_request
from .runtime import Runtime
from .scheduled import LocalScheduler, ReminderError, ReminderStore, local_now, parse_in_duration
from .window import launch
from .adapters.hooks import forward_stream
from .adapters.notify import notify
from .adapters.pomodoro import plan_pomodoro


def _root(value: str | None) -> Path:
    return resolve_root(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="companion")
    parser.add_argument("--root", default=None, help="directory containing inbox/outbox/state (default: $COMPANION_ROOT or ./.companion)")
    parser.add_argument("--agent", default="cli")
    parser.add_argument("--companion-id", default=None, help="route events to a specific companion")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command", required=False)
    sub.add_parser("init")
    sub.add_parser("summon")
    sub.add_parser("hide")
    sub.add_parser("status")
    say = sub.add_parser("say")
    say.add_argument("text")
    say.add_argument("--ttl", type=float)
    say.add_argument("--priority", type=int, default=0)
    mood = sub.add_parser("mood")
    mood.add_argument("value", choices=sorted(STATES))
    move = sub.add_parser("move")
    move.add_argument("value", choices=sorted(POSITIONS))
    run = sub.add_parser("run")
    run.add_argument("--once", action="store_true")
    remind = sub.add_parser("remind")
    remind_sub = remind.add_subparsers(dest="remind_command", required=True)
    add = remind_sub.add_parser("add")
    add.add_argument("--at", default=None, help="HH:MM or ISO-8601 due time")
    add.add_argument("--in", dest="in_duration", default=None, help="relative duration like 30s, 10m, 2h, 1d")
    add.add_argument("--message", required=True)
    add.add_argument("--mood", choices=sorted(STATES))
    add.add_argument("--ttl", type=float, default=8)
    add.add_argument("--companion-id")
    add.add_argument("--recurrence", choices=["daily", "weekly", "countdown"], default=None)
    add.add_argument("--weekdays", default=None, help="comma-separated mon,tue,wed,thu,fri,sat,sun for weekly")
    remind_sub.add_parser("list")
    cancel = remind_sub.add_parser("cancel")
    cancel.add_argument("id")
    snooze = remind_sub.add_parser("snooze")
    snooze.add_argument("id")
    snooze.add_argument("--minutes", type=int, default=10)
    remind_sub.add_parser("fire")
    timer = sub.add_parser("timer", help="one-shot countdown using the scheduling pipeline")
    timer.add_argument("--in", dest="in_duration", required=True, help="duration like 30s, 10m, 2h")
    timer.add_argument("--message", required=True)
    timer.add_argument("--mood", choices=sorted(STATES), default=None)
    timer.add_argument("--ttl", type=float, default=8)
    pomodoro = sub.add_parser("pomodoro", help="plan a focus + break cycle as reminders")
    pomodoro.add_argument("--work", type=int, default=25, help="focus minutes")
    pomodoro.add_argument("--break", dest="break_minutes", type=int, default=5, help="break minutes")
    pomodoro.add_argument("--message", default="Pomodoro")
    notify_cmd = sub.add_parser("notify", help="show an optional local OS notification")
    notify_cmd.add_argument("text")
    notify_cmd.add_argument("--title", default="Companion")
    sub.add_parser("path", help="show resolved data dir and config discovery")
    doctor_cmd = sub.add_parser("doctor", help="run local diagnostics")
    doctor_cmd.add_argument("--json", action="store_true", help="print full JSON report")
    logs_cmd = sub.add_parser("logs", help="show recent structured log lines")
    logs_cmd.add_argument("--tail", type=int, default=20)
    gui = sub.add_parser("gui")
    gui.add_argument("--asset", type=Path)
    gui.add_argument("--name", default="Companion")
    gui.add_argument("--pack", type=Path)
    gui.add_argument("--config", type=Path)
    pack = sub.add_parser("pack")
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)
    validate = pack_sub.add_parser("validate")
    validate.add_argument("path", type=Path)
    render_request = sub.add_parser("render-request", help="validate a renderer request document")
    render_request_sub = render_request.add_subparsers(dest="render_request_command", required=True)
    render_request_validate = render_request_sub.add_parser("validate")
    render_request_validate.add_argument("path", type=Path)
    sub.add_parser("hook", help="forward canonical JSONL events from stdin")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "version", False):
        print(__version__)
        return 0
    if not getattr(args, "command", None):
        build_parser().print_usage(sys.stderr)
        print("error: a command is required (try --help)", file=sys.stderr)
        return 2
    if args.command == "render-request":
        try:
            request = load_render_request(args.path)
        except RenderRequestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(request, ensure_ascii=True))
        return 0
    root = _root(args.root)
    runtime = Runtime(root, companion_id=args.companion_id)
    reminder_store = ReminderStore(root / "reminders.json")
    scheduler = LocalScheduler(reminder_store, runtime.inbox)
    if runtime.recovered:
        log_emit(root, "warning", "state-recovered", state=str(runtime.state_path))
    if args.command == "init":
        root.mkdir(parents=True, exist_ok=True)
        runtime._save_state()
        print(f"initialized {root}")
        return 0
    if args.command == "status":
        print(json.dumps(runtime.state, ensure_ascii=True))
        return 0
    if args.command == "run":
        if args.once:
            scheduler.tick()
            print(json.dumps({"processed": runtime.process_once()}))
            return 0
        while True:
            scheduler.tick()
            runtime.process_once()
            import time

            time.sleep(0.1)
        return 0
    if args.command == "remind":
        try:
            if args.remind_command == "add":
                if (args.at is None) == (args.in_duration is None):
                    print("error: use exactly one of --at or --in", file=sys.stderr)
                    return 2
                due_at = args.at
                if due_at is None and args.in_duration is not None:
                    due_at = parse_in_duration(args.in_duration).isoformat()
                assert due_at is not None
                weekdays = None
                if args.weekdays:
                    weekdays = [day.strip() for day in args.weekdays.split(",") if day.strip()]
                reminder = reminder_store.create(
                    due_at=due_at,
                    message=args.message,
                    mood=args.mood,
                    ttl=args.ttl,
                    companion_id=args.companion_id,
                    recurrence=args.recurrence,
                    weekdays=weekdays,
                )
                print(json.dumps({"id": reminder.id, "due_at": reminder.due_at, "status": reminder.status}, ensure_ascii=True))
            elif args.remind_command == "list":
                print(json.dumps([reminder.__dict__ for reminder in reminder_store.list()], ensure_ascii=True))
            elif args.remind_command == "cancel":
                reminder = reminder_store.cancel(args.id)
                print(json.dumps({"id": reminder.id, "status": reminder.status}, ensure_ascii=True))
            elif args.remind_command == "snooze":
                reminder = reminder_store.snooze(args.id, minutes=args.minutes)
                print(json.dumps({"id": reminder.id, "status": reminder.status, "snoozed_until": reminder.snoozed_until}, ensure_ascii=True))
            else:
                fired = scheduler.tick()
                print(json.dumps({"fired": [item.id for item in fired]}, ensure_ascii=True))
        except ReminderError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "timer":
        try:
            due_at = parse_in_duration(args.in_duration).isoformat()
            reminder = reminder_store.create(
                due_at=due_at,
                message=args.message,
                mood=args.mood,
                ttl=args.ttl,
                companion_id=args.companion_id,
            )
            print(json.dumps({"id": reminder.id, "due_at": reminder.due_at, "status": reminder.status}, ensure_ascii=True))
        except ReminderError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "pomodoro":
        try:
            planned = plan_pomodoro(
                reminder_store,
                work_minutes=args.work,
                break_minutes=args.break_minutes,
                message=args.message,
                companion_id=args.companion_id,
                now=local_now(),
            )
            print(json.dumps({"ids": [item.id for item in planned], "due": [item.due_at for item in planned]}, ensure_ascii=True))
        except (ReminderError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "notify":
        shown = notify(args.title, args.text)
        print(json.dumps({"shown": shown}, ensure_ascii=True))
        return 0
    if args.command == "path":
        print(json.dumps({
            "root": str(root),
            "default_data_dir": str(default_data_dir()),
            "platform": platform_name(),
            "config": str(discover_config(root)) if discover_config(root) else None,
            "companion_id": args.companion_id,
        }, ensure_ascii=True))
        return 0
    if args.command == "doctor":
        report = run_checks(root, companion_id=args.companion_id)
        if args.json:
            print(json.dumps(report, ensure_ascii=True, indent=2))
        else:
            status = "OK" if report["ok"] else "ISSUES"
            print(f"doctor: {status}")
            for issue in report["issues"]:
                print(f"- {issue}")
            if report["ok"]:
                print(f"root={report['root']} platform={report['platform']} python={report['python']}")
        return 0 if report["ok"] else 1
    if args.command == "logs":
        for record in read_tail(root, limit=args.tail):
            print(json.dumps(record, ensure_ascii=True))
        return 0
    if args.command == "gui":
        try:
            config = load_config(args.config) if args.config else None
            pack_path = args.pack or (config.pack if config else None)
            loaded_pack = AssetPack.load(pack_path) if pack_path else None
        except (ConfigError, PackError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if config:
            runtime.state["position"] = config.position
        launch(
            runtime,
            asset=args.asset,
            pack=loaded_pack,
            name=(config.name if config and args.name == "Companion" else args.name),
            topmost=config.topmost if config else True,
            opacity=config.opacity if config else 1.0,
        )
        return 0
    if args.command == "pack":
        try:
            loaded_pack = AssetPack.load(args.path)
        except PackError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"id": loaded_pack.pack_id, "name": loaded_pack.name, "states": sorted(loaded_pack.animations)}, ensure_ascii=True))
        return 0
    if args.command == "hook":
        forward_stream(sys.stdin, runtime.inbox, sys.stdout)
        return 0
    event_type = args.command
    fields = {}
    if args.command == "say":
        fields = {"text": args.text, "priority": args.priority}
        if args.ttl is not None:
            fields["ttl"] = args.ttl
    elif args.command in {"mood", "move"}:
        fields = {"value": args.value}
    append_jsonl(root / "inbox.jsonl", new_event(event_type, agent=args.agent, companion_id=args.companion_id, **fields))
    print(f"queued {event_type}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
