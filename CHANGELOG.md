# Changelog

## 1.0.0 (2026-09-10)

First stable release as **Open Agent Companion** (`companion`).

- Protocol `companion-event-v1`: `say`, `state`, `mood`, `move`, `summon`,
  `hide`, `status` over append-only JSONL with `inbox_offset` recovery.
- Runtime: persistent state, TTL + priority queue, per-companion routing.
- Desktop: transparent Tk window, packs, drag, positions, text fallback.
- Reminders: one-shot, timers (`--in`), recurrence (`daily`, `weekly` +
  `weekdays`, `countdown`), `snooze`, overdue-on-restart, pomodoro producer.
- Adapters: generic hook, localhost WebSocket (opt-in), OpenCode plugin,
  OpenISy TUI plugin, optional OS notifications.
- Hardening: atomic writes + `*.corrupt` backups, structured logs,
  `doctor`, `path`, data-dir discovery, security review (no shell, no
  network by default).
- Docs: README, GUIA (es), SPEC, SECURITY, examples, end-to-end demo.
