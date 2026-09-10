# Companion Hub Milestone 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a consumer-facing Windows Companion Hub that discovers packs, persists independent companions, manages only its own pet processes, and ships as `Companion Hub.exe`.

**Architecture:** Add a focused `companion.hub` package over the existing `AssetPack`, runtime, storage, and CLI contracts. Domain services remain UI-independent; one Tkinter window consumes them and uses one preview widget. M11 includes first-run visual-companion onboarding but does not execute Forge recipes or install agents.

**Tech Stack:** Python 3.11+, Tkinter, pathlib/json, subprocess, existing atomic storage, pytest, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-09-10-companion-hub-milestone-1-design.md`

## Global Constraints

- No network requests.
- No agent installation or Companion Recipe execution in M11.
- Each companion receives an independent runtime root.
- Stop only processes launched and tracked by the current Hub session.
- Reuse `AssetPack.load`; never modify pack manifests.
- Keep technical paths/details out of the primary screen.
- Preserve the current CLI/runtime/event protocol.

---

## File map

- `src/companion/hub/models.py`: immutable pack and companion records.
- `src/companion/hub/discovery.py`: validated local pack discovery.
- `src/companion/hub/registry.py`: atomic persisted companion registry.
- `src/companion/hub/processes.py`: Hub-owned process lifecycle and event actions.
- `src/companion/hub/window.py`: consumer-facing Tkinter Hub and first-run route.
- `src/companion/hub/main.py`: Hub composition root and CLI-callable entry point.
- `tests/test_hub_discovery.py`, `tests/test_hub_registry.py`, `tests/test_hub_processes.py`, `tests/test_hub_window.py`: focused tests.
- `src/companion/cli.py`, `pyproject.toml`, `tools/build_exe.ps1`, `README.md`: entry points, packaging, and usage.

### Task 1: Pack catalog and companion registry

**Files:**
- Create: `src/companion/hub/__init__.py`
- Create: `src/companion/hub/models.py`
- Create: `src/companion/hub/discovery.py`
- Create: `src/companion/hub/registry.py`
- Create: `tests/test_hub_discovery.py`
- Create: `tests/test_hub_registry.py`

**Interfaces:**
- Produces: `PackRecord(pack_id: str, name: str, root: Path, preview: Path | None, error: str | None)`.
- Produces: `CompanionRecord(companion_id: str, name: str, pack_root: Path, runtime_root: Path)`.
- Produces: `discover_packs(packs_dir: Path) -> list[PackRecord]`.
- Produces: `CompanionRegistry(path: Path, runtimes_dir: Path)` with `list()`, `create(name, pack_root)`, and `get(companion_id)`.

- [ ] **Step 1: Write failing discovery tests**

```python
def test_discover_packs_returns_valid_and_invalid_records(tmp_path):
    valid = make_pack(tmp_path / "valid")
    invalid = tmp_path / "broken"; invalid.mkdir(); (invalid / "manifest.json").write_text("{}")
    records = discover_packs(tmp_path)
    assert [(r.name, r.error is None) for r in records] == [("Cat", True), ("broken", False)]
    assert records[0].preview == valid / "idle.png"
```

- [ ] **Step 2: Run discovery test and confirm it fails**

Run: `py -m pytest tests/test_hub_discovery.py -q`
Expected: FAIL because `companion.hub.discovery` does not exist.

- [ ] **Step 3: Implement models and deterministic one-level discovery**

Use `AssetPack.load(candidate)` for every immediate child containing
`manifest.json`; sort output by `name.casefold(), pack_id` and represent invalid
manifests with `error=str(exc)` and no preview.

- [ ] **Step 4: Write failing registry tests**

```python
def test_registry_round_trip_uses_independent_runtime_roots(tmp_path):
    registry = CompanionRegistry(tmp_path / "companions.json", tmp_path / "runtimes")
    a = registry.create("Malbolge", tmp_path / "packs" / "malbolge")
    b = registry.create("Shinji", tmp_path / "packs" / "shinji")
    assert a.runtime_root != b.runtime_root
    assert CompanionRegistry(registry.path, registry.runtimes_dir).get(a.companion_id) == a
```

- [ ] **Step 5: Implement atomic registry persistence**

Generate stable IDs from a normalized name plus a collision suffix, resolve
pack/runtime paths, serialize a versioned JSON object, and write it through
`atomic_write_json`.

- [ ] **Step 6: Run focused tests and commit**

Run: `py -m pytest tests/test_hub_discovery.py tests/test_hub_registry.py -q`
Expected: PASS.

```bash
git add src/companion/hub tests/test_hub_discovery.py tests/test_hub_registry.py
git commit -m "feat: add Hub catalog and companion registry"
```

### Task 2: Hub-owned process lifecycle

**Files:**
- Create: `src/companion/hub/processes.py`
- Create: `tests/test_hub_processes.py`

**Interfaces:**
- Consumes: `CompanionRecord`.
- Produces: `ProcessStatus` enum values `STOPPED`, `RUNNING`, `HIDDEN`, `EXITED`, `UNMANAGED`.
- Produces: `ProcessManager(executable: list[str], popen=subprocess.Popen)` with `start(record)`, `show(record)`, `hide(record)`, `stop(record)`, and `status(record)`.

- [ ] **Step 1: Write ownership and argument tests**

```python
def test_manager_starts_with_independent_root_and_pack(fake_popen, record):
    manager = ProcessManager(["companion"], popen=fake_popen)
    manager.start(record)
    assert fake_popen.calls[0] == ["companion", "--root", str(record.runtime_root), "gui", "--pack", str(record.pack_root)]

def test_manager_never_stops_unowned_process(record):
    manager = ProcessManager(["companion"])
    assert manager.stop(record) is False
```

- [ ] **Step 2: Run test and confirm missing module failure**

Run: `py -m pytest tests/test_hub_processes.py -q`
Expected: FAIL importing `ProcessManager`.

- [ ] **Step 3: Implement lifecycle and event actions**

Store handles by companion ID only after successful `Popen`. `stop` calls
`terminate`, waits up to three seconds, then calls `kill` only on that same
handle. `show`/`hide` publish `summon`/`hide` events to the record's runtime
inbox through existing queue/protocol functions.

- [ ] **Step 4: Cover exited and idempotent paths**

Add tests proving an exited handle reports `EXITED`, repeated stop is harmless,
and a failed `Popen` leaves no owned entry.

- [ ] **Step 5: Run tests and commit**

Run: `py -m pytest tests/test_hub_processes.py -q`
Expected: PASS.

```bash
git add src/companion/hub/processes.py tests/test_hub_processes.py
git commit -m "feat: manage Hub-owned companion processes"
```

### Task 3: Consumer-facing Hub window

**Files:**
- Create: `src/companion/hub/window.py`
- Create: `tests/test_hub_window.py`

**Interfaces:**
- Consumes: `list[PackRecord]`, `CompanionRegistry`, and `ProcessManager`.
- Produces: `HubWindow(root, packs, registry, processes)` with `select`, `start_selected`, `show_selected`, `hide_selected`, `stop_selected`, and `refresh_status`.

- [ ] **Step 1: Write UI-controller tests using fake Tk widgets**

```python
def test_selection_reuses_one_preview_widget(hub, first, second):
    preview_id = id(hub.preview_label)
    hub.select(first.companion_id); hub.select(second.companion_id)
    assert id(hub.preview_label) == preview_id
    assert hub.selected_id == second.companion_id

def test_primary_action_reflects_status(hub):
    hub.processes.status.return_value = ProcessStatus.STOPPED
    hub.refresh_status()
    assert hub.primary_action_text == "Start companion"
```

- [ ] **Step 2: Run tests and confirm missing window failure**

Run: `py -m pytest tests/test_hub_window.py -q`
Expected: FAIL importing `HubWindow`.

- [ ] **Step 3: Implement approved three-region layout**

Build a responsive Tk grid with collection, living stage, and contextual
detail regions. Use one preview label and replace its retained `PhotoImage`.
Use user-facing strings and move pack paths/status diagnostics into an advanced
dialog.

- [ ] **Step 4: Connect real actions without duplicate surfaces**

Primary action starts or shows; secondary hides; overflow contains stop,
advanced details, open pack folder, and existing actions that M11 actually
supports. Disable actions when no companion is selected or a pack is invalid.

- [ ] **Step 5: Add bounded status refresh and visual-state tests**

Schedule one 500 ms refresh callback. Test running, hidden, stopped, exited,
invalid-pack, empty, and action-in-progress labels without creating another
preview widget.

- [ ] **Step 6: Run tests and commit**

Run: `py -m pytest tests/test_hub_window.py -q`
Expected: PASS.

```bash
git add src/companion/hub/window.py tests/test_hub_window.py
git commit -m "feat: add consumer Companion Hub window"
```

### Task 4: First-run creation flow

**Files:**
- Modify: `src/companion/hub/window.py`
- Modify: `tests/test_hub_window.py`

**Interfaces:**
- Produces: `show_welcome()`, `show_collection()`, and `create_from_pack(pack_id: str, name: str) -> CompanionRecord`.

- [ ] **Step 1: Write first-run routing tests**

```python
def test_empty_registry_opens_welcome(hub):
    assert hub.current_view == "welcome"
    assert hub.welcome_actions == ("Create my companion", "Open my collection")

def test_m11_does_not_execute_forge_recipe(hub):
    assert "Install agent" not in hub.executable_actions
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `py -m pytest tests/test_hub_window.py -q`
Expected: FAIL because the welcome route is absent.

- [ ] **Step 3: Implement welcome and local visual-companion creation**

Explain the two routes in user language. `Create my companion` selects a valid
local pack and name, writes one registry record, and enters the living stage.
Show `Companion Forge — guided coding-agent setup arrives in M12` as disabled
informational copy, never as an executable button.

- [ ] **Step 4: Run UI tests and commit**

Run: `py -m pytest tests/test_hub_window.py -q`
Expected: PASS.

```bash
git add src/companion/hub/window.py tests/test_hub_window.py
git commit -m "feat: add Hub first-run companion creation"
```

### Task 5: CLI composition and Windows executables

**Files:**
- Create: `src/companion/hub/main.py`
- Modify: `src/companion/cli.py`
- Modify: `pyproject.toml`
- Modify: `tools/build_exe.ps1`
- Create: `tests/test_hub_cli.py`

**Interfaces:**
- Produces: `companion.hub.main:main(argv: list[str] | None = None) -> int`.
- Produces: `companion hub [--hub-root PATH] [--packs-dir PATH]`.
- Produces: project script `companion-hub = companion.hub.main:main`.

- [ ] **Step 1: Write CLI argument/composition tests**

```python
def test_hub_cli_passes_resolved_paths(monkeypatch, tmp_path):
    opened = {}
    monkeypatch.setattr("companion.hub.main.open_hub", lambda **kw: opened.update(kw))
    assert hub_main(["--hub-root", str(tmp_path), "--packs-dir", str(tmp_path / "packs")]) == 0
    assert opened["hub_root"] == tmp_path.resolve()
```

- [ ] **Step 2: Implement composition root and CLI command**

Create required Hub directories, discover packs, load registry, create manager,
and open one `HubWindow`. Existing `companion` commands remain unchanged.

- [ ] **Step 3: Update packaging**

Add `companion-hub` script and build `Companion Hub.exe` with
`--windowed --onefile --name "Companion Hub"`, alongside existing CLI build.
Include `packs/` through PyInstaller's Windows `--add-data "packs;packs"`.

- [ ] **Step 4: Verify entry points and commit**

Run: `py -m pytest tests/test_hub_cli.py tests/test_config.py -q`
Run: `companion hub --help`
Run: `companion-hub --help`
Expected: all pass and print usage without opening a window.

```bash
git add src/companion/hub/main.py src/companion/cli.py pyproject.toml tools/build_exe.ps1 tests/test_hub_cli.py
git commit -m "feat: add Companion Hub entry points and build"
```

### Task 6: Documentation and end-to-end verification

**Files:**
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Create: `docs/audits/2026-09-10-companion-hub-m11-audit.md`

**Interfaces:**
- Consumes all prior task interfaces.
- Produces documented local launch, build, and acceptance evidence.

- [ ] **Step 1: Document install, launch, data ownership, and M11 limits**

Add `companion hub`, `companion-hub`, and Windows build instructions. State
that Forge/Doctor begin in M12 and that Hub stops only processes it owns.

- [ ] **Step 2: Run full automated verification**

Run: `py -m pytest -q`
Run: `py -m compileall -q src`
Run: `companion pack validate packs/malbolge-cat`
Run: `companion pack validate packs/tabby-shinji-cat`
Run: `git diff --check`
Expected: all commands pass; only already-documented external deprecation
warnings may remain.

- [ ] **Step 3: Perform Windows UI smoke test**

Use a temporary `--hub-root`; verify empty welcome, pack discovery, creation of
Malbolge and Shinji, independent roots, start/hide/show/stop, one preview image,
and that stopping one does not affect the other. Record exact results and any
display limitation in the audit file.

- [ ] **Step 4: Mark roadmap and commit evidence**

Check only M11 items demonstrated by the audit; leave M12/M13 unchecked.

```bash
git add README.md ROADMAP.md docs/audits/2026-09-10-companion-hub-m11-audit.md
git commit -m "docs: verify Companion Hub milestone 1"
```
