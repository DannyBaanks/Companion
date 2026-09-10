# Companion Roadmap

This roadmap is the current project plan. The public name is intentionally
left undecided until the product shape is stable.

## Product boundary

An open local desktop companion for agents, CLIs, reminders, and other local
processes. The companion renders generic semantic events; it does not contain
AI, cloud services, accounts, calendar synchronization, or arbitrary command
execution.

## Completed

### M0. Event protocol

- [x] Versioned JSONL event envelope.
- [x] `say`, `state`, `mood`, `move`, `summon`, `hide`, and `status` events.
- [x] Ordered inbox and acknowledgement outbox.
- [x] Invalid events produce errors without stopping the runtime.

### M1. Local runtime and CLI

- [x] Persistent companion state.
- [x] CLI for summon, hide, say, mood, move, status, and run.
- [x] Direct JSONL publishing from any process.

### M2. Desktop companion

- [x] Transparent Tk window.
- [x] Always-on-top behavior.
- [x] GIF/PNG asset loading.
- [x] Dragging and simple positions: corners, dock, and free.
- [x] Escape-to-close behavior.

### M3. Local reminders V1

- [x] One-shot `ScheduledEvent` records.
- [x] Local `HH:MM` and ISO-8601 timestamps with preserved offsets.
- [x] Persistent `pending`, `fired`, and `cancelled` statuses.
- [x] Due rule is `now >= due_at`.
- [x] Overdue pending reminders fire once after restart.
- [x] Fired reminders become normal `say`/optional `mood` events.
- [x] CLI add, list, cancel, and fire operations.
- [x] Small GUI editor and pending-reminder list.
- [x] Deterministic fake-clock tests.

## Next milestones

### M4. Companion packs and configuration

- [x] JSON/TOML companion configuration.
- [x] Asset folder manifests with path and state validation.
- [x] Named animation states: idle, thinking, working, success, error, and waiting.
- [x] Generic presentation hints without pack-specific commands.
- [ ] Example pack with documented GIF/PNG assets.

### M5. Message presentation

- [x] Reliable TTL expiration for message bubbles.
- [x] Short-message queue and priority policy.
- [x] Visual fallback when an animation state has no asset.
- [x] Accessible text/status fallback for missing or invalid assets.

### M6. External producers

- [x] Generic hook adapter for local processes.
- [x] WebSocket adapter on localhost, opt-in only.
- [x] OpenCode adapter, isolated from the core protocol.
- [x] OpenISy TUI adapter, isolated from the core protocol.
- [x] Document standalone, manual/local, and external-control modes equally.

### M7. Multiple companions

- [x] Per-companion state files (`state-{id}.json`).
- [x] Independent state, messages, and reminders.
- [x] Companion selection from CLI (`--companion-id`) and generic `companion_id` routing.
- [x] Multiple windows without shared-state collisions.

### M8. Local automation extensions

- [x] Timers and countdowns as later event producers.
- [x] Recurring reminders and weekdays as a separate scheduling layer.
- [x] Snooze as an explicit reminder state transition.
- [x] System notifications as an optional presentation adapter.
- [x] Pomodoro as a separate producer, not a runtime feature.

These features reuse the same scheduling-to-event pipeline. They are not
part of Reminders V1.

### M9. Distribution and hardening

- [x] Cross-platform runtime strategy after Windows is stable.
- [x] Installer or standalone executable for Windows.
- [x] Configuration and data-directory discovery.
- [x] Crash recovery and safe store writes.
- [x] Structured logs and diagnostics command.
- [x] Security review: no shell execution, no network by default, local paths only.

### M10. Open source release

- [x] Choose final project name and command name.
- [x] Choose license and contribution policy.
- [x] Complete README, Spanish owner guide, protocol specification, and examples.
- [x] End-to-end demo with a real asset pack and local reminder.
- [x] CI test matrix and versioned release artifacts.
- [x] Release 1.0.

Release: **Open Agent Companion 1.0.0 (MIT)**, command `companion`,
package `open-agent-companion`. See `CHANGELOG.md`, `LICENSE`,
`CONTRIBUTING.md`, `SECURITY.md`, `examples/`, and `.github/workflows/ci.yml`.

## Explicitly out of scope for now

- Natural-language reminder parsing.
- Cloud or remote scheduling.
- Accounts and synchronization.
- Calendar integration.
- AI or inference inside the companion.
- Reminder text executing shell commands.
- Pack-specific actions such as `cat_jump()` or browser automation.

## Definition of done for 1.0

An independent user can install the project, create or choose a companion pack,
launch a transparent desktop companion, send it a message from a CLI or local
process, create a reminder, restart before or after its due time, and observe
the same canonical event pipeline without network access or provider-specific
software.
