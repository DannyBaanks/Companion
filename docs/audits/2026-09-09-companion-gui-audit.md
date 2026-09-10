# Companion GUI audit — 2026-09-09

## Scope

End-to-end verification of the Tkinter Companion GUI, the Malbolge Cat pack,
the render-request contract, and the state/control paths added in this cycle.

## Automated evidence

All commands were run from the repository root with Python 3.12 (`py`).

| Check | Result |
| --- | --- |
| `py -m pytest -q` | PASS — 78 passed, 2 non-failing deprecation warnings (`pytest-asyncio` configuration and an existing `asyncio.get_event_loop()` use in `tests/test_adapters.py`) |
| `py -m companion.cli pack validate packs/malbolge-cat` | PASS — pack `malbolge-cat`, six states: `error`, `idle`, `success`, `thinking`, `waiting`, `working` |
| `py -m companion.cli render-request validate examples/render_request.json` | PASS — normalized request for `Malbolgato`, pixel-art style, six states, `cell_size: [128, 128]` |
| `py -m companion.cli --help` | PASS — includes `gui`, `pack`, and `render-request` commands |
| `py -m companion.cli gui --help` | PASS — exposes `--asset`, `--name`, `--pack`, and `--config` |
| Python compile check | PASS — source and tests compile successfully |

## GUI smoke coverage

The GUI launch command was exercised with:

```text
py -m companion.cli gui --pack packs/malbolge-cat
```

The process remained active as expected for a desktop event loop and was
stopped after the bounded smoke window. The current shell session did not
provide an inspectable desktop surface or screenshot capture, so this audit
does not claim a visual screenshot acceptance.

The state/control paths are covered by the automated window tests: idle,
thinking, working, success, error, waiting, opacity/configuration, right-click
control callbacks, drag bindings, and Escape binding. The six pack states also
validate successfully against the checked-in manifest.

## Known limits

- A human-visible screenshot and mouse-driven drag/right-click/Escape pass
  still needs to be repeated in a desktop session with the GUI visible.
- The CLI launch is intentionally a long-running process; a successful smoke
  run is represented by the process entering its Tk event loop, not by a
  normal immediate exit code.
- The two deprecation warnings above are pre-existing and do not fail the
  suite.

## Conclusion

Automated verification is green and the pack/render-request workflows are
usable. No product code changes were needed for this audit; the only deferred
verification is visual/manual interaction in an available desktop session.
