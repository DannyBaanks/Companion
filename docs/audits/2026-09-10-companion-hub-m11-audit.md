# Companion Hub M11 audit

Date: 2026-09-11

## Scope

This audit covers the consumer-facing Companion Hub launcher, local pack
discovery, first-run creation, Hub-owned process lifecycle, and Windows
distribution. Forge, agent installation, and Capability Doctor remain M12/M13
work; this milestone performs no network requests or shell installation.

## Automated verification

| Check | Result |
| --- | --- |
| `py -m pytest -q` | 155 passed; one pre-existing asyncio deprecation warning |
| `py -m compileall -q src` | passed |
| `companion pack validate packs/malbolge-cat` | passed |
| `companion pack validate packs/tabby-shinji-cat` | passed |
| `git diff --check` | passed |
| `companion hub --help` | passed without constructing Tk |
| `companion-hub --help` | passed without constructing Tk |

The tests cover empty welcome routing, two independent companion records and
runtime roots, one preview authority, start/show/hide/stop ownership, frozen
pack materialization across extraction-root changes, corrupt snapshot repair,
and crash-safe publication locks.

## Windows packaging

`powershell -NoProfile -ExecutionPolicy Bypass -File tools\\build_exe.ps1
-Target hub` produced both artifacts in `dist\\`:

- `companion.exe` (13,616,094 bytes in the clean packaging smoke)
- `Companion Hub.exe` (13,531,708 bytes in the clean packaging smoke)

The Hub executable keeps a sibling `companion.exe` for Hub-owned pets and
bundles default packs into stable, content-addressed user data before a
companion record persists its pack path. A hidden `Companion Hub.exe --help`
smoke exited successfully. An interactive windowed smoke was not run in the
headless verification session; Tk behavior is covered by the fake-widget UI
tests and should be repeated on a desktop before publishing a release.

## Acceptance walkthrough

1. Start `companion hub --hub-root <temporary-directory>`.
2. With an empty registry, the Hub shows the welcome view and a single
   **Create my companion** action.
3. Select a valid local pack, create Malbolge, then use **Add companion** to
   create Tabby Shinji. Each record receives a distinct
   `<hub-root>\\runtimes\\<id>` directory.
4. Select one record and use Start, Hide/Show, and Stop. The process manager
   only terminates processes started by that Hub session; stopping one record
   does not affect the other.
5. The stage keeps one preview widget/state authority. Invalid packs expose
   details but disable folder opening and creation.

## Data ownership and limitations

Hub registry and runtime roots are local-user data. Pack manifests are read,
not modified. Hub shutdown does not terminate pets it did not start, and a
pet's stable bundled-pack snapshot can outlive the Hub process. The executable
build is self-contained as a pair; distributing only `Companion Hub.exe` is
not supported because it intentionally requires its sibling runtime.

