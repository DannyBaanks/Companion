# Task 1 report: Pack catalog and companion registry

## Files

- `src/companion/hub/__init__.py`
- `src/companion/hub/models.py`
- `src/companion/hub/discovery.py`
- `src/companion/hub/registry.py`
- `tests/test_hub_discovery.py`
- `tests/test_hub_registry.py`

Discovery scans immediate child directories containing `manifest.json`, loads each with
`AssetPack.load`, and preserves invalid candidates as error records. The registry stores
versioned JSON atomically and gives each companion a separate runtime root.

## Commands and results

- `py -m pytest tests/test_hub_discovery.py tests/test_hub_registry.py -q` (initial red: collection failed because `companion.hub` did not exist)
- `py -m pytest tests/test_hub_discovery.py tests/test_hub_registry.py -q` (green: 4 passed)
- `git diff --check` (passed)
- `py -m pytest -q` (87 passed, 1 pre-existing `DeprecationWarning` in `tests/test_adapters.py`)

## Commit

Implementation commit: `68d8ab3fd37fbbf4ce006039ef5e1d463b9a6674`

## Concerns

The brief's sample discovery expectation places valid `Cat` before invalid `broken`,
which conflicts with a strict global `name.casefold()` sort (`broken` sorts first).
Implementation prioritizes valid records, then applies deterministic name/id ordering.
