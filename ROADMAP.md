# Roadmap de Companion

This roadmap is the current project plan. The public name is intentionally
left undecided until the product shape is stable.

## Límite del producto

Una mascota virtual de escritorio, abierta y local. Companion presenta eventos
semánticos, animaciones, mensajes, reminders y personalidad configurable. Los
agentes, CLIs y procesos locales son integraciones opcionales, no la identidad
principal del producto.

Companion no contiene IA, servicios cloud, cuentas ni sincronización de
calendario. Las recipes futuras pueden proponer comandos locales, pero solo
después de mostrar la acción exacta y recibir confirmación explícita.

## Completado

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

## Próximos milestones

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

## Roadmap visual y de experiencia de mascota

La dirección posterior a 1.0 es una experiencia local pulida: una mascota
cálida, expresiva y premium, sin fingir ser un agente de IA. La calidad visual
puede recordar a herramientas modernas, pero el límite permanece intacto:
eventos locales entran y la mascota los presenta honestamente.

### M11. Companion Stage v2 — visual foundation

- [x] Define shared design tokens for color, typography, spacing, radii,
  shadows, focus rings, and motion.
- [x] Add light, dark, and soft-neon presentation themes.
- [x] Standardize the visual treatment of `idle`, `thinking`, `working`,
  `success`, `error`, and `waiting`.
- [x] Add accessible text/status fallbacks and non-color-only state cues.
- [x] Redesign the transparent stage with soft state-aware glow, message
  bubbles, and non-invasive transitions.
- [x] Preserve drag, opacity, position, topmost, and Escape behavior.

### M12. Context menu and interaction polish

- [x] Group controls into Companion, Window, Runtime, and System sections.
- [x] Add keyboard navigation, Escape handling, focus visibility, and shortcut
  hints.
- [x] Add human-readable descriptions and disabled-state explanations.
- [x] Keep destructive actions explicit and confirmable.
- [x] Keep state authority external: the menu may inspect state but must not
  fabricate agent state or bypass the event protocol.

### M13. Companion Hub

- [x] Build a consumer-facing Hub with collection, living stage, and
  contextual-detail layouts.
- [x] Discover and validate installed packs.
- [x] Create/select companions with independent runtime roots.
- [x] Preview, start, show, hide, and stop Hub-owned companions.
- [x] Show human-readable status and last activity; keep technical details in
  an Advanced view.
- [x] Add a first-run flow with clear paths: create a companion or open the
  local pet collection.
- [ ] Produce a separate `Companion Hub.exe` build for Windows.

### M14. Pack Gallery

- [x] Add animated pack previews with author, license, palette, and supported
  states.
- [x] Add `Preview` and `Use this pack` flows with validation before use.
- [x] Document the visual contract for `idle`, `thinking`, `working`,
  `success`, `error`, and `waiting`.
- [x] Keep packs declarative and sandboxed; no pack-specific executable
  actions or browser automation.

### M15. Personality without AI

- [x] Add local personality settings for tone, verbosity, and message policy.
- [x] Support configurable greetings, success messages, and error detail level.
- [x] Keep personality as presentation policy over canonical events.
- [x] Do not add inference, cloud calls, accounts, or hidden interpretation of
  reminder text.

### M16. Activity Timeline and Trust Center

- [x] Add a local activity timeline for states, messages, reminders, and
  adapter events.
- [x] Support filtering by companion, agent, and event type.
- [x] Allow copying/exporting canonical event JSONL and diagnostics.
- [ ] Promote `cap.doctor` to a first-class provider-agnostic diagnostic
  capability.
- [ ] Standardize Doctor outcomes as `READY`, `NEEDS_ACTION`, `BLOCKED`, or
  `UNKNOWN`; never show false-green success states.
- [ ] Keep technical evidence available without making it the default UI.

### M17. Companion Forge and guided onboarding

- [x] Make `Create Companion` the primary onboarding experience.
- [x] Offer intention-first choices: coding companion, local AI companion,
  existing agent, or pets without an agent.
- [x] Add portable declarative recipes with the lifecycle
  `detect -> propose -> confirm -> execute -> verify -> receipt`.
- [x] Detect platform, architecture, PATH, permissions, ports, versions,
  conflicts, and rollback feasibility where relevant.
- [x] Show official source, artifact, version, checksum/signature, permissions,
  license metadata, and exact actions before execution.
- [x] Require explicit confirmation before any installation or configuration
  mutation.
- [x] Verify the full path: agent launches, adapter responds, events reach the
  runtime, and the companion renders the resulting state/message.
- [x] Produce readable installation receipts and recovery steps.

### M18. Recipe ecosystem and companion creation

- [x] Add recipes for more CLI/TUI agents, local models, and API-backed
  providers without coupling them to Companion core.
- [x] Define capability contracts for chat, notifications, status, and actions.
- [x] Allow providers to contribute Doctor hooks through the same diagnostic
  contract.
- [x] Add provenance policies for official sources, registries, checksums,
  signatures, version pinning, and license metadata.
- [x] Combine adapter, capabilities, visual pack, and personality into one
  portable companion definition.
- [x] Add safe rollback/uninstall hooks for recipe-owned changes.
- [x] Import/export recipes and companion configurations.
- [x] Add a validated visual pack/manifest editor.
- [x] Document a public recipe-authoring contract and verification suite.

### M19. Distribution polish

- [ ] Ship native Windows and Linux launchers/installers.
- [x] Add configuration migration, crash recovery, safe-store repair, and
  exportable diagnostics.
- [x] Add versioned pack distribution and compatibility checks.
- [ ] Add real GUI smoke tests to the CI matrix where a display is available.
- [ ] Publish a visual demo, screenshots, accessibility notes, and release
  receipts for supported platforms.

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
