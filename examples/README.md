# Examples

- `example-cat/`: minimal real pack (`idle.png`, `success.png`, 1x1 PNG).
  Validate with `companion pack validate examples/example-cat`.
- `demo_e2e.py`: end-to-end pipeline without GUI or network. Creates an
  isolated root, validates the pack, sends `say`, creates an immediate
  one-shot reminder, runs scheduler + runtime once, prints `status` and
  `doctor`. Run with `py examples/demo_e2e.py`.
