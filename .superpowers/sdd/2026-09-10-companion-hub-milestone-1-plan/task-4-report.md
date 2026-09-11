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

## Fix round 1

- Added a visible `Add companion` action to the populated collection. The
  focused test opens this actual UI route, chooses the human-readable `Fox`
  pack label, enters a name, submits, and verifies that the existing Hub
  selects the newly persisted local companion.
- Creation now uses dialog-local inline feedback. Blank names keep the dialog
  open with a validation message; `OSError` and `PermissionError` from local
  registry work keep it open with a recoverable permissions/storage message.
- Registry persistence now removes the just-created, empty runtime directory
  when saving its record fails, so a failed local creation leaves no orphan
  runtime root.
- Empty first-run views distinguish absent packs from invalid local packs and
  disable creation with an explicit inline explanation.
- Pack choices show `PackRecord.name` and map the displayed choice back to its
  stable `pack_id`; no Forge, network, agent-installation, recipe, or shell
  action was added.

### Fix-round TDD evidence

The new focused contracts first failed as expected: no populated-Hub add
route, generic missing-pack messaging, and no runtime rollback (6 failed, 22
passed). After the controller and registry changes,
`py -m pytest tests/test_hub_window.py tests/test_hub_registry.py -q` passed
with 30 tests, including explicit `OSError` and `PermissionError` cases.

## Verification

- `py -m pytest tests/test_hub_window.py tests/test_hub_registry.py -q` — 30
  passed.
- `py -m pytest -q` — 123 passed. One pre-existing
  `DeprecationWarning` remains in
  `tests/test_adapters.py::test_websocket_rejects_non_loopback`.
- `git diff --check` — passed.

## Scope

The fix round modified `src/companion/hub/window.py`,
`src/companion/hub/registry.py`, `tests/test_hub_window.py`,
`tests/test_hub_registry.py`, and this report. No plan, approved specification,
or ledger files were changed.
