# Companion Roadmap

This roadmap is the current project plan. The public name is intentionally
left undecided until the product shape is stable.

## Product boundary

An open local desktop companion for agents, CLIs, reminders, and other local
processes. The companion renders generic semantic events; it does not contain
AI, cloud services, accounts, or calendar synchronization. Future onboarding
recipes may propose local installation/configuration commands, but only after
showing them to the user and receiving explicit confirmation.

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

## Companion Hub roadmap

### M11. Companion Hub launcher

- [x] Consumer-facing desktop Hub with the approved collection, living stage,
  and contextual-detail layout.
- [x] Discover and validate installed companion packs.
- [x] Create/select companions with independent runtime roots.
- [x] Preview, start, show, hide, and stop Hub-owned companions.
- [x] Human-readable status and last activity; technical details stay behind
  an advanced view.
- [x] Separate `Companion Hub.exe` build for Windows.
- [x] First-run welcome flow with two clear paths: create a companion or open
  the local pet collection.
- [ ] Repeat the packaged Windows UI walkthrough on an interactive desktop
  before publishing a release artifact (headless CI uses deterministic UI
  tests and executable/help smoke checks).

### M12. Companion Forge and guided onboarding

- [ ] Make `Create Companion` the primary onboarding experience for new users.
- [ ] Provide intention-first choices: coding companion, local AI companion,
  connect an existing agent, or use pets without an agent.
- [ ] Add portable declarative Companion Recipes with the lifecycle
  `detect -> propose -> confirm -> execute -> verify -> receipt`.
- [ ] Define `cap.doctor` as a first-class, provider-agnostic diagnostic
  capability. Doctor inspects and reports; it never installs by itself.
- [ ] Standardize Doctor outcomes as `READY`, `NEEDS_ACTION`, `BLOCKED`, or
  `UNKNOWN`, without false-green success states.
- [ ] Detect common local prerequisites such as Git, Python, Node, and
  available CLI/TUI agents.
- [ ] Check platform, CPU architecture, PATH, permissions, disk space, ports,
  versions, conflicts, existing installations, upgrade paths, and rollback
  feasibility when relevant to a recipe.
- [ ] Generate a declarative installation plan rather than free-form shell:
  official source, package/artifact, version, architecture, checksum or
  signature, destination, permissions, verification, and rollback metadata.
- [ ] Display a `License & Source Review` with detected license, official source,
  terms link, redistribution/commercial-use summary, notices, and an explicit
  `UNKNOWN`/user-review state for ambiguity. It must not claim universal legal
  approval.
- [ ] Never execute installation or configuration commands before displaying
  the exact action and receiving explicit confirmation.
- [ ] Keep proposal, verification, authority, and execution separate:
  recipes propose, Doctor verifies, the user authorizes, and a constrained
  installer performs only declared operations.
- [ ] Ship one supported coding-agent recipe plus a generic
  `connect existing CLI/TUI` recipe.
- [ ] Guide the user with a bundled default companion instead of technical
  installer language.
- [ ] Verify the complete path: agent launches, adapter responds, events reach
  the runtime, and the companion renders the resulting state/message.
- [ ] Produce a readable installation receipt and actionable recovery steps.
- [ ] Run Doctor again after execution and require all mandatory checks to pass
  before reporting the companion ready.

### M13. Recipe ecosystem and full companion creation

- [ ] Add recipe packs for more CLI/TUI agents, local models, and API-backed
  providers without coupling the Companion core to any provider.
- [ ] Define capability contracts for chat, notifications, status, and actions.
- [ ] Allow providers/runtimes to contribute Doctor hooks while returning the
  same stable diagnostic contract (`opencode.doctor`, `ollama.doctor`, generic
  CLI/TUI Doctor, and future adapters).
- [ ] Add provenance policies for official sources, package registries,
  checksums/signatures, version pinning, and license metadata.
- [ ] Combine agent adapter, capabilities, visual pack, and behavior/personality
  into one portable companion definition.
- [ ] Add safe rollback/uninstall hooks for recipe-owned changes.
- [ ] Import/export recipes and companion configurations.
- [ ] Add a basic visual pack/manifest editor with validation and preview.
- [ ] Support profiles, startup preferences, and reusable creation templates.
- [ ] Document a public recipe authoring contract and verification suite.

## Explicitly out of scope for now

- Natural-language reminder parsing.
- Cloud or remote scheduling.
- Accounts and synchronization.
- Calendar integration.
- AI or inference inside the companion.
- Reminder text executing shell commands.
- Silent or unreviewed installation commands from Companion Recipes.
- Recipes terminating or modifying software they do not own.
- Pack-specific actions such as `cat_jump()` or browser automation.

## Definition of done for 1.0

An independent user can install the project, create or choose a companion pack,
launch a transparent desktop companion, send it a message from a CLI or local
process, create a reminder, restart before or after its due time, and observe
the same canonical event pipeline without network access or provider-specific
software.
