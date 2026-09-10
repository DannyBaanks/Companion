# Contributing

Local-first project. No accounts, no cloud, no AI in the runtime.

## Rules

1. Protocol first: `SPEC.md` is the contract. New events need validation,
   tests, and a SPEC entry.
2. Evidence over prose: every guide command must be executed before it is
   written down. Paste real output, mark `NO PROBADO` otherwise.
3. No new code edges by accident: adapters write JSONL to an inbox. They
   never call engines, browsers, or shells.
4. Tests: `py -m pytest` must stay green. Add a test with every behavior
   change (`tests/test_*.py`).
5. Small diffs: one milestone slice per change, docs updated in the same
   change (README/GUIA/SPEC/ROADMAP as needed).

## Setup

```powershell
py -m pip install --editable ".[build]"
py -m pytest
companion doctor
```
