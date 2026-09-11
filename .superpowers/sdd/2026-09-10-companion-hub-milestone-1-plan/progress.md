# SDD ledger — plan: docs/superpowers/plans/2026-09-10-companion-hub-milestone-1-plan.md

## Preflight scan

| Scope | Shared file/interface | Finding | Ruling |
|---|---|---|---|
| Task 1 ↔ Task 2 | `CompanionRecord` | Process manager consumes the exact immutable registry record produced by Task 1. | Compatible. |
| Task 1 ↔ Task 3 | pack records and registry | UI consumes the catalog and registry without duplicating persistence. | Compatible. |
| Task 2 ↔ Task 3 | `ProcessManager` and `ProcessStatus` | UI labels/actions depend on lifecycle results from Task 2. | Compatible. |
| Task 3 ↔ Task 4 | `hub/window.py` | Task 4 extends the same window with first-run routing. | Preserve the single window/controller and add views; no parallel UI. |
| Task 1–4 ↔ Task 5 | composition interfaces | CLI composition wires earlier services and must not redefine them. | Compatible. |
| Task 5 ↔ Task 6 | launch/build commands | Documentation and audit consume exact CLI/packaging outputs. | Compatible. |

| Task | Self-consistency check | Ruling |
|---|---|---|
| 1 | Discovery/registry tests match declared records and persistence interfaces. | Proceed. |
| 2 | Ownership tests match the lifecycle contract; three-second termination bound is explicit. | Proceed. |
| 3 | One-preview invariant and consumer layout tests match the spec. | Proceed. |
| 4 | Welcome route creates only a visual local companion and clearly defers Forge execution. | Proceed. |
| 5 | CLI and build outputs match the spec, preserving existing commands. | Proceed. |
| 6 | Full tests plus manual smoke cover M11 and leave M12/M13 unchecked. | Proceed. |

## Decisions

- Ruling: M11 onboarding may explain Companion Forge but exposes no agent-install action — the approved spec assigns execution and Capability Doctor to M12 — cost if wrong is revising first-run copy and routing later.
- Ruling: discovery sorts valid packs before invalid packs, then by `name.casefold(), pack_id` — this satisfies the plan's example and consumer UX despite the prose saying one global name sort — cost if wrong is a small catalog-order migration.

Task 1: fix round 1/5 (1 addressed, 0 open — stale runtime roots are reserved after registry recovery; commits 9f0bf9b..3822c2a)
Task 1: complete (commits 0aae576..3822c2a, review clean)
Task 2: fix round 1/5 (1 addressed, 0 open — failed termination retains ownership for retry; commits 9ce394c..0900764)
Task 2: complete (commits 3822c2a..0900764, review clean)
Task 3: fix round 1/5 (3 addressed, 0 open — invalid-pack folder action gated, busy selection/progress stabilized, regression coverage added; commits ab24a67..1b5949a)
Task 3: complete (commits 0900764..1b5949a, review clean)
Task 4: fix round 1/5 (5 addressed, 1 new open — added populated creation route, persistence recovery/rollback, explicit pack errors, real UI tests, friendly pack names; commits cd05b7d..7870189)
Task 4: fix round 2/5 (1 addressed, 0 open — welcome now exposes exactly one creation action; commits 7870189..b96a5e2)
Task 4: complete (commits 1b5949a..b96a5e2, review clean)
Task 5: fix round 1/5 (3 addressed, 1 open — stable bundled snapshots, complete hub distribution, bundled CLI packs; commits 0d29767..030e394)
Task 5: fix round 2/5 (1 addressed, 1 open — content verification and concurrent repair; commits 030e394..823d585)
Task 5: fix round 3/5 (1 addressed, 1 open — crash-safe lock lease; commits 823d585..4cb4565)
Task 5: fix round 4/5 (3 addressed, 1 open — Windows liveness/identity and owner-generation guards; commits 4cb4565..038ed90)
Task 5: fix round 5/5 (2 addressed, 0 open — crash-partial metadata recovery and fail-closed identity acquisition; commits 038ed90..447ee87)
Task 5: complete (commits b96a5e2..447ee87, review clean)
Task 6: fix round 1/5 (2 addressed, 0 open — build extra prerequisite documented and manual packaged UI gate left explicitly unchecked in headless environment; commits 5e3efb8..2716642)
Task 6: complete (commits 447ee87..2716642, review clean)
Final whole-branch review: fix round 1/1 (2 addressed, 0 open — ownerless lock recovery no longer depends on mutable mtime; PyInstaller native failures propagate; commits 2716642..12a0331)
Final whole-branch review: complete (review clean, 156 tests passed)
