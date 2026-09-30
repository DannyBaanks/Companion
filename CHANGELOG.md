# Registro de cambios

## 1.1.0 (2026-09-29)

Local pet art and animation engine, Codex sprite rendering, and dock play.

- Art engine: `companion art validate/render/inspect` and
  `companion animate validate/render` over versioned, data-only recipes
  (`companion-character-v1`, `companion-animation-v1`, `companion-parts-v1`).
  Rendering uses local Pillow only; no network, no shell.
- Packs: optional `spriteSheet` and `dragAnimation` manifest blocks plus
  action animations (`running-left`, `running-right`, `drag`). The loader
  validates the grid and rejects escaping paths.
- Linux: new GTK sprite window renders Codex atlases with native alpha
  (Tk path still available for GIF packs); Tk windows use the X11 Shape
  extension for per-frame transparency.
- Hub: pack selection when creating a companion, plus an opt-in
  "Allow this pet to run along Companion's preset bottom strip" permission;
  the strip uses fixed screen coordinates and never queries the Dock.
- Fix: X11 shape cache kept stale masks when `id()` was recycled; masks are
  now cached per frame with the frame itself kept alive.
- Fix: window construction on a headless Linux session no longer pretends
  X11 shaping is active.
- Tests: 229 passing. New suites for art recipes, pack sprite sheets,
  dock play permissions, and Hub dock flags. `Pillow` moved into the
  `[test]` extra so asset checks run in CI.

## 1.0.0 (2026-09-10)

First stable release as **Open Agent Companion** (`companion`).

- Protocol `companion-event-v1`: `say`, `state`, `mood`, `move`, `summon`,
  `hide`, `status` over append-only JSONL with `inbox_offset` recovery.
- Runtime: persistent state, TTL + priority queue, per-companion routing.
- Desktop: transparent Tk window, packs, drag, positions, text fallback.
- Reminders: one-shot, timers (`--in`), recurrence (`daily`, `weekly` +
  `weekdays`, `countdown`), `snooze`, overdue-on-restart, pomodoro producer.
- Adapters: generic hook, localhost WebSocket (opt-in), OpenCode plugin,
  OpenISy TUI plugin, optional OS notifications.
- Hardening: atomic writes + `*.corrupt` backups, structured logs,
  `doctor`, `path`, data-dir discovery, security review (no shell, no
  network by default).
- Docs: README, GUIA (es), SPEC, SECURITY, examples, end-to-end demo.
