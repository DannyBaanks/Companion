# Task 4 report: First-run companion creation

## Delivered

- Empty registries open the existing Hub window in a welcome state with the
  `Create my companion` and `Open my collection` routes.
- Creation stays local: it selects only a valid discovered pack, persists one
  `CompanionRecord` through the existing registry, rebuilds the collection,
  and selects the new companion on the existing living stage.
- The creation dialog exposes no network, agent-installation, recipe, or shell
  actions. Forge is disabled informational copy only:
  `Companion Forge — guided coding-agent setup arrives in M12`.
- Existing collection, process controls, one-preview-widget behavior, and the
  single refresh timer remain intact.

## TDD evidence

1. Added welcome and Forge-boundary contracts, then ran
   `py -m pytest tests/test_hub_window.py -q`.
   The focused suite failed as expected with missing `current_view` and
   `forge_copy` attributes (2 failed, 15 passed).
2. Implemented the minimal welcome state and disabled Forge copy; focused UI
   tests passed (17 passed).
3. Added local creation and invalid-pack contracts, then ran the focused suite
   again. It failed as expected because `create_from_pack` was absent (2
   failed, 17 passed).
4. Implemented validated local creation; focused UI tests passed (19 passed).

## Verification

- `py -m pytest tests/test_hub_window.py -q` — 19 passed.
- `py -m pytest -q` — 115 passed. One pre-existing
  `DeprecationWarning` remains in
  `tests/test_adapters.py::test_websocket_rejects_non_loopback`.
- `git diff --check` — passed.

## Scope

Only `src/companion/hub/window.py` and `tests/test_hub_window.py` were
modified for the feature, plus this report. No plan, approved specification,
or ledger files were changed.
