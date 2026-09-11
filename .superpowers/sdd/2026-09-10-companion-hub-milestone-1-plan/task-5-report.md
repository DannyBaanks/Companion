# Task 5 report: Hub entry points and Windows packaging

## Implementation

- Added `companion.hub.main`, the local-only Hub composition root. It creates
  the Hub data and runtime directories, discovers local packs, wires the
  existing registry and process manager, then opens one `HubWindow`.
- Added `companion hub [--hub-root PATH] [--packs-dir PATH]` without changing
  existing command dispatch. The command routes before runtime construction.
- Added the `companion-hub` console script.
- Source/console launches run the existing runtime as an argument list,
  `sys.executable -m companion.cli`; frozen Hub launches its sibling
  `companion.exe`. Neither form relies on shell quoting, so paths containing
  spaces remain intact.
- Hub discovery prefers an existing `<hub-root>/packs` directory and otherwise
  uses checked-in source packs or PyInstaller's `_MEIPASS/packs` bundle.
- Reworked `tools/build_exe.ps1` with `all`, `cli`, and `hub` targets. The Hub
  target builds windowed, one-file `Companion Hub.exe` and includes
  `packs;packs` as PyInstaller data. The script performs no package install or
  network action.

## TDD and verification evidence

- Red: `py -m pytest tests/test_hub_cli.py -q` failed at collection with
  `ImportError: cannot import name 'main' from 'companion.hub'`, before the
  composition module existed.
- Green: `py -m pytest tests/test_hub_cli.py tests/test_config.py -q` —
  initially 10 passed, then 12 passed after source/frozen bundle and runtime
  command coverage was added.
- Entry-point smoke after refreshing the local editable install with
  `py -m pip install --editable . --no-deps`:
  `companion hub --help` and `companion-hub --help` both printed usage and
  returned without constructing a Tk window.
- Packaging red: the first `-Target hub` invocation reported `param` as an
  unrecognized command because the PowerShell parameter block followed an
  executable statement. Moving it to the top of the script fixed the entry
  point.
- Packaging green: `powershell -NoProfile -ExecutionPolicy Bypass -File
  tools\build_exe.ps1 -Target hub` completed using PyInstaller 6.22.0 and
  created `dist\Companion Hub.exe` (13,349,981 bytes). The generated spec file
  was removed afterwards.
- Full regression: `py -m pytest -q` — 133 passed, with one existing asyncio
  deprecation warning in `tests/test_adapters.py`.
- `py -m compileall -q src` and `git diff --check` — passed.

### Final lock hardening — crash-partial metadata and Windows identity

- Partial operation/mutation metadata is recoverable through an inode/stat
  generation token after the lease expires; replacement verification restores
  a successor instead of deleting it.
- Windows lock acquisition now aborts and cleans up when process creation
  identity cannot be established, preventing unreclaimable locks after a
  crash. PID reuse is rejected by creation-time identity matching.
- Added crash-partial tests for both guards and an identity-unavailable test.
- Focused lock/materialization tests: `31 passed`.
- Full regression: `py -m pytest -q` — `155 passed`, with the existing asyncio
  deprecation warning in `tests/test_adapters.py`.
- `py -m compileall -q src` and `git diff --check` — passed.

### Fix round 4/5 — Windows-safe ownership and replacement guards

- Windows liveness now uses `OpenProcess` with synchronization/query rights,
  `GetExitCodeProcess`, and `GetProcessTimes`; it never probes with
  `os.kill`, and PID reuse is rejected unless the recorded creation identity
  matches.
- Snapshot and nested operation guards carry owner generations and use
  mutation tokens; replacement verification restores an observed successor
  instead of deleting it. Unreadable metadata fails closed and waits are
  bounded.
- Focused lock/materialization tests: `28 passed`.
- Full regression: `py -m pytest -q` — `152 passed`, with the existing
  asyncio deprecation warning in `tests/test_adapters.py`.
- `py -m compileall -q src` and `git diff --check` — passed.

## Review round 4: Windows-safe, generation-guarded lock recovery

- Windows owner checks now call `OpenProcess(SYNCHRONIZE)` and
  `GetExitCodeProcess`; they never use `os.kill` and therefore never send a
  termination signal. Unknown Windows API failures conservatively count as a
  live owner. POSIX keeps a non-signalling `kill(pid, 0)` fallback, likewise
  treating access or other OS failures as live.
- A lock owner has an immutable UUID generation. Before either release or
  stale reclaim renames the lock directory, it acquires a single short-lease
  operation guard, rechecks that exact owner generation, and then retires only
  that guarded directory. A changed successor owner causes the takeover to
  stop without moving or deleting it.
- Owner metadata missing or malformed is distinct from filesystem read errors:
  old missing/corrupt locks can be recovered by their stable directory
  generation, while access-denied/sharing errors are non-reclaimable and time
  out without deletion. Abandoned operation guards use the same dead-owner,
  bounded-lease recovery rule.

Verification evidence:

- Red: `py -m pytest tests/test_hub_cli.py -q` — 6 failures before the lock
  ownership API existed, covering abandoned recovery, live-owner protection,
  Windows liveness, ownership replacement, unreadable metadata, and bounded
  timeout.
- Green: `py -m pytest tests/test_hub_cli.py -q` — 25 passed.
- Windows API smoke: `py -c "from companion.hub.main import _pid_is_alive;
  import os; print(_pid_is_alive(os.getpid()))"` — printed `True` without a
  signal-based process check.
- Full regression: `py -m pytest -q` — 149 passed, with the same existing
  asyncio deprecation warning in `tests/test_adapters.py`.
- `py -m compileall -q src` and `git diff --check` — passed.

### Fix round 2/3 — crash-safe snapshot publication lock

- Snapshot publication locks now record an owner PID, unique owner ID, and
  bounded lease. Expired locks are reclaimed only when the recorded owner is
  no longer alive; live owners are left untouched.
- Added deterministic coverage for abandoned-lock recovery and for refusing
  to reclaim an expired lock whose owner is still alive.
- Focused Hub CLI/materialization tests: `21 passed`.
- Full regression: `py -m pytest -q` — `145 passed`, with the same existing
  asyncio deprecation warning in `tests/test_adapters.py`.
- `py -m compileall -q src` and `git diff --check` — passed.

## Review round 2: verified snapshot repair and publication races

The prior snapshot logic trusted a directory solely because its name matched
the expected SHA-256 value. A deleted asset, partial copy, or colliding publisher
could therefore leave a bad directory accepted as durable pack data.

- Every reuse and every post-publication winner now has its full tree rehashed
  and compared with the destination name.
- Corrupt or incomplete snapshots are moved only to a uniquely named,
  task-owned backup while a uniquely named staging directory is copied and
  verified. Both staging and backup paths are cleaned after publication; no
  broad Hub-root removal is used.
- Cooperating Hub starts serialize snapshot repair with a per-digest lock
  directory. Rename/replace errors accept another publisher only after the
  winner passes exact digest verification; an invalid collision is repaired
  once from the current bundle, while other I/O errors continue to propagate.

Verification evidence:

- Red: `py -m pytest tests/test_hub_cli.py -q` — 4 failures: an incomplete
  snapshot was reused, concurrent publish raised Windows `PermissionError`,
  and both valid and invalid publication-collision behaviors were absent.
- Green: `py -m pytest tests/test_hub_cli.py tests/test_config.py -q` —
  22 passed.
- Full regression: `py -m pytest -q` — 143 passed, with the same existing
  asyncio deprecation warning in `tests/test_adapters.py`.
- `py -m compileall -q src` and `git diff --check` — passed.

## Limitations

The Hub-only packaging smoke did not rebuild the unchanged CLI executable; the
same script retains a separate `cli` target. The frozen bundle path is covered
by unit tests and the successful PyInstaller data inclusion, but the built
windowed executable was not launched because that would open an interactive
desktop window during automated verification.

## Commit

Implementation commit: this report is committed with the Task 5 implementation.

## Review round 1: durable frozen packs and self-contained distribution

### Root causes

- Frozen Hub discovery passed `sys._MEIPASS/packs` directly into persisted
  companion records. PyInstaller removes that extraction location after exit,
  leaving later pet launches without their pack assets.
- The `hub` build target created only `Companion Hub.exe`, while a frozen Hub
  launches a sibling `companion.exe` for pet processes. The CLI target also did
  not include packs, so `companion.exe hub` could not use default packs.
- PyInstaller treated `src/companion/cli.py` and `src/companion/hub/main.py`
  as top-level scripts, which broke their relative imports in frozen builds.

### Fixes

- Frozen bundled packs are copied to immutable, content-addressed snapshots
  under `<hub-root>/bundled-packs/<sha256>`. An unchanged bundle extracted to a
  different temporary directory resolves to the same stable snapshot; changed
  content receives a new snapshot while prior companion records retain their
  old stable assets.
- A frozen Hub validates that `companion.exe` is present beside itself before
  opening. `-Target hub` now builds the CLI runtime first and then the Hub; both
  artifacts include bundled packs.
- Added top-level PyInstaller wrapper scripts that import the established
  package entry points absolutely, eliminating relative-import failures.

### Evidence

- Red: `py -m pytest tests/test_hub_cli.py -q` — 4 failed, covering missing
  frozen runtime validation, missing stable materialization, and the persisted
  extraction-root path.
- Green after the composition fix: `py -m pytest tests/test_hub_cli.py -q` —
  13 passed.
- Artifact red: the first clean frozen smoke failed in `companion.exe` with
  `ImportError: attempted relative import with no known parent package`.
- Wrapper red: the new wrapper tests failed with `FileNotFoundError` before
  the wrappers were added.
- Green after wrapper/build changes: `py -m pytest tests/test_hub_cli.py -q` —
  15 passed.
- Clean packaging: `powershell -NoProfile -ExecutionPolicy Bypass -File
  tools\build_exe.ps1 -Target hub` completed with PyInstaller 6.22.0 and
  produced `dist\companion.exe` (13,616,094 bytes) plus
  `dist\Companion Hub.exe` (13,531,708 bytes).
- Frozen entry smoke: `dist\companion.exe hub --help` printed Hub usage; the
  windowed `dist\Companion Hub.exe --help` exited 0 when run hidden.
- Full regression: `py -m pytest -q` — 139 passed, with the same existing
  asyncio deprecation warning in `tests/test_adapters.py`.
- `py -m compileall -q src` and `git diff --check` — passed.
