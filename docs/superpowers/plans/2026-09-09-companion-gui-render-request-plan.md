# Companion GUI and Render Request Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a simple Tkinter GUI for the Companion, reliable animated pack playback, basic controls, and a validated customizable `render_request.json` contract.

**Architecture:** Keep the JSONL runtime and existing `DesktopWindow` as the source of truth. Add focused render-request validation and GUI control helpers around the current window instead of introducing a web server or new GUI framework. Preserve pack fallback behavior and make animation timing local and deterministic.

**Tech Stack:** Python 3.12+, Tkinter, GIF/PNG `PhotoImage`, JSON/TOML config, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-companion-gui-render-request-design.md`

## Global Constraints

- Extend the existing transparent Tkinter window; do not add Electron, a browser, or a server.
- Keep the JSONL runtime/state model as the source of truth.
- Preserve missing-state fallback to `idle`.
- Keep `Esc` close, left-drag move, right-click controls.
- Invalid render requests fail in the CLI and never block the runtime.
- Existing tests must remain green.

---

### Task 1: Render-request contract and CLI validation

**Files:**
- Create: `src/companion/render_request.py`
- Modify: `src/companion/cli.py`
- Test: `tests/test_render_request.py`

**Interfaces:**
- `validate_render_request(data: object) -> dict[str, object]` returns a normalized copy or raises `RenderRequestError` with field-specific text.
- `load_render_request(path: Path) -> dict[str, object]` parses JSON and delegates to validation.
- CLI command: `companion render-request validate <path>` prints normalized JSON and returns `0`; invalid input prints `error: ...` and returns `2`.

- [ ] **Step 1: Write failing tests** for required `name`/`style`, palette validation, known state validation, positive two-item `output.cell_size`, unknown-field preservation, invalid JSON, and CLI exit codes.
- [ ] **Step 2: Run `py -m pytest tests/test_render_request.py -q` and confirm the new module/command fail.
- [ ] **Step 3: Implement the validator with explicit `RenderRequestError` messages and no renderer/network calls.
- [ ] **Step 4: Add the parser and CLI subcommand, keeping the existing parser structure.
- [ ] **Step 5: Run the focused tests and commit `feat: add render request validation`.

### Task 2: Timing-aware animated assets

**Files:**
- Modify: `src/companion/window.py:20-45`
- Test: `tests/test_window.py`

**Interfaces:**
- `AnimatedAsset(path, clock=time.monotonic)` loads GIF frames plus per-frame durations and exposes `current`, `advance(now=None)`, and `reset()`.
- Static image assets continue to expose one frame and never fail on missing GIF metadata.

- [ ] **Step 1: Write failing tests** for GIF frame count, duration-based advancement, reset, and static PNG behavior using a fake clock and temporary assets.
- [ ] **Step 2: Run the focused tests and confirm `AnimatedAsset` currently advances every refresh regardless of duration.
- [ ] **Step 3: Implement elapsed-time advancement while retaining Tk `PhotoImage` references and a 100ms refresh loop.
- [ ] **Step 4: Run `py -m pytest tests/test_window.py -q` and confirm timing tests pass.
- [ ] **Step 5: Commit `fix: honor animation frame timing`.

### Task 3: Small right-click GUI controls

**Files:**
- Modify: `src/companion/window.py`
- Modify: `src/companion/config.py`
- Test: `tests/test_window.py`
- Test: `tests/test_config.py`

**Interfaces:**
- `DesktopWindow` gets a compact context menu/panel with callbacks for `set_state(value)`, `set_position(value)`, `set_opacity(value)`, `toggle_messages()`, and `reload_pack()`.
- Controls publish state/mood through `Runtime` events or update the existing runtime state through its public event path; they do not mutate pack files.
- `CompanionConfig` gains optional `show_messages: bool = True` and `pack_name: str | None = None` while old TOML/JSON remains valid.

- [ ] **Step 1: Write failing tests** for config defaults/backward compatibility and menu callbacks changing runtime state/position without breaking drag/Escape behavior.
- [ ] **Step 2: Run focused tests and confirm the controls/config fields are absent.
- [ ] **Step 3: Implement a compact `tk.Menu` or small `Toplevel` panel anchored to the mascot; keep the main window borderless and unobstructed.
- [ ] **Step 4: Wire state choices to the existing `STATES`, positions to `POSITIONS`, opacity to clamped values in `[0.35, 1.0]`, and message toggle to bubble visibility.
- [ ] **Step 5: Apply config values during `cli gui` launch and add focused tests.
- [ ] **Step 6: Commit `feat: add companion control panel`.

### Task 4: Pack preview and render-request examples

**Files:**
- Create: `examples/render_request.json`
- Modify: `README.md`
- Modify: `GUIA.md`
- Test: `tests/test_pack.py`

**Interfaces:**
- Document `companion pack validate <path>` and `companion render-request validate <path>`.
- Document GUI launch with a pack/config and the right-click controls.
- Add a test that validates the checked-in example request and the Malbolge pack manifest.

- [ ] **Step 1: Add a concrete Malbolgato-like `examples/render_request.json` using only the supported contract.
- [ ] **Step 2: Add concise usage docs and troubleshooting for missing assets/fallback-to-idle.
- [ ] **Step 3: Run pack and render-request validation against the example and `packs/malbolge-cat`.
- [ ] **Step 4: Commit `docs: document gui and render requests`.

### Task 5: End-to-end verification and GUI smoke test

**Files:**
- Modify: `tests/test_companion.py` only if an integration assertion is needed.
- Create: `docs/audits/2026-09-09-companion-gui-audit.md`

**Interfaces:**
- The audit records commands, screenshots if a desktop session is available, state transitions, and known limits.

- [ ] **Step 1: Run `py -m pytest -q` and require all tests to pass.
- [ ] **Step 2: Run `py -m companion.cli pack validate packs/malbolge-cat` and `py -m companion.cli render-request validate examples/render_request.json`.
- [ ] **Step 3: Launch the GUI with the Malbolge pack, exercise idle/thinking/working/success/error/waiting, right-click controls, drag, and Escape; save an accepted screenshot if the desktop is available.
- [ ] **Step 4: Record evidence and limitations in the audit note.
- [ ] **Step 5: Commit `test: verify companion gui workflow`.

