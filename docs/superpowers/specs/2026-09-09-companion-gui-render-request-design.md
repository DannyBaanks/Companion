# Companion GUI and render-request design

## Goal

Close the local Companion experience with a small, pleasant Tkinter GUI that reliably renders animated packs, exposes the core controls without becoming a dashboard, and gives pack authors a stable `render_request.json` contract for custom mascots.

## Scope

- Extend the existing transparent `DesktopWindow`; do not introduce a browser, server, or new GUI framework.
- Keep the current JSONL runtime and state model as the source of truth.
- Add a right-click control panel for state, position, opacity, message visibility, pack selection, and configuration reload.
- Keep keyboard behavior: `Esc` closes the companion; left-drag moves it; right-click opens controls.
- Add pack preview/validation helpers and render-request validation.
- Preserve fallback behavior: missing state assets resolve to `idle`.
- Keep animation playback local and deterministic; respect GIF frame timing when available.

## UX

The companion remains a mascot first. The main window stays borderless and transparent. Right-click opens a compact panel anchored near the mascot with the current state and five actions: choose state, choose position, choose opacity, toggle message bubbles, and open/reload settings. The panel closes after an action or Escape. A small non-blocking error label appears only when a selected pack or asset cannot load.

## Architecture

1. `AssetPack` continues to resolve state/mood assets and validates paths.
2. `DesktopWindow` owns only presentation and user controls; it delegates state changes to `Runtime` events.
3. `AnimatedAsset` loads GIF frames and durations, advances based on elapsed time, and keeps static PNG/WebP assets supported.
4. `Config` gains optional GUI defaults without changing existing config files.
5. `render_request.py` validates the small JSON contract (`name`, `style`, optional palette, states, and output cell size) without invoking a renderer. External renderers can consume the validated request later.
6. CLI commands expose pack validation and render-request validation for local workflows.

## Render request contract

Required: `name` and `style` strings. Optional: `palette` (non-empty color strings), `states` (known companion states), and `output.cell_size` as two positive integers. Unknown fields are preserved for renderer-specific extensions but do not affect Companion runtime behavior. Invalid requests fail with actionable field errors.

## Error handling

- Invalid packs remain rejected before the GUI starts.
- A missing or unreadable selected asset falls back to the previous valid asset, then to idle.
- Invalid render requests never block the companion; CLI validation reports the error and exits non-zero.
- Corrupt runtime state follows the existing recovery path.

## Verification

- Existing test suite remains green.
- Add tests for render-request validation, pack state fallback, GIF frame timing, and GUI state/mood selection through the existing runtime boundary.
- Run `pack validate` and `render-request validate` against the Malbolge pack/request.
- Smoke-test the GUI manually when a desktop display is available; otherwise report that visual GUI behavior could not be captured.
