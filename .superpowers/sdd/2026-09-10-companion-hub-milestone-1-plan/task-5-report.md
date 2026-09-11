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

## Limitations

The Hub-only packaging smoke did not rebuild the unchanged CLI executable; the
same script retains a separate `cli` target. The frozen bundle path is covered
by unit tests and the successful PyInstaller data inclusion, but the built
windowed executable was not launched because that would open an interactive
desktop window during automated verification.

## Commit

Implementation commit: this report is committed with the Task 5 implementation.
