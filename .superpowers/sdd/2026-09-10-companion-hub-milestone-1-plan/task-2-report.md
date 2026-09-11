# Task 2 report: Hub-owned process lifecycle

## Files

- `src/companion/hub/processes.py`
- `tests/test_hub_processes.py`

`ProcessManager` records only successfully created subprocess handles, keyed by
companion ID for the current Hub session. It starts each GUI with the record's
own runtime root and pack root, publishes `summon`/`hide` protocol events to
that record's own inbox, and terminates only its recorded handle. Termination
waits for at most three seconds before killing that same handle. Lifecycle
status distinguishes unmanaged, running, hidden, exited, and explicitly
stopped records.

## TDD and verification evidence

- Red: `py -m pytest tests/test_hub_processes.py -q` failed during collection
  with `ModuleNotFoundError: No module named 'companion.hub.processes'` before
  the implementation was added.
- Green: `py -m pytest tests/test_hub_processes.py -q` — 7 passed.
- Full regression: `py -m pytest -q` — 95 passed; one pre-existing
  `DeprecationWarning` in `tests/test_adapters.py::test_websocket_rejects_non_loopback`.
- `py -m compileall -q src` — passed.
- `git diff --check` — passed before the implementation commit.

The focused tests cover the independent-root launch arguments, unmanaged stop
protection, record-local show/hide events, exited status, repeated stop,
three-second timeout/kill behavior, and failed-start ownership cleanup.

## Commit

Implementation commit: `0793210600c37fe78456b0bff149a82f30b6d9ac`

## Concerns

The full suite retains the existing asyncio deprecation warning noted above;
this task does not modify the affected adapter test or runtime behavior.
