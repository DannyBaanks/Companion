# Companion Hub — Milestone 1 Design

## Goal

Deliver a local Windows launcher, `Companion Hub.exe`, where a non-technical
user can discover installed packs, create/select companions, preview the
selected companion, and start or stop only the desktop-pet processes launched
by the Hub.

The Hub is a consumer-facing local application. Its interface uses the
approved composition: companion collection on the left, a dominant living
stage in the center, and human-readable context on the right. Internal paths,
runtime offsets, and logs are not primary-screen content.

## Scope

Included:

- Discover and validate packs under a configurable local packs directory.
- Persist a local registry of created companions.
- Show pack previews using each pack's idle asset.
- Select a companion and display its name, status, last activity, and actions.
- Create a companion by choosing a validated pack and a display name.
- Present a first-run welcome with two routes: `Create my companion` and
  `Open my collection`. In M11, creation configures a local visual companion;
  agent installation and Capability Doctor execution begin in M12.
- Start, show, hide, and stop Hub-owned companion processes.
- Build separate `companion.exe` and `Companion Hub.exe` Windows executables.

Excluded until later milestones:

- Pack editing, ZIP import, a pack marketplace, profiles, or cloud sync.
- Managing processes not launched by this Hub instance.
- Replacing the existing Companion runtime or its event protocol.
- Installing agents, executing Companion Recipes, or presenting license/source
  reviews. M11 may preview that future path but must label it as unavailable.

## Architecture

### `companion.hub.discovery`

Scans a configured pack directory one level deep for `manifest.json`, loads
each candidate with `AssetPack.load`, and returns a record containing pack ID,
name, idle asset path, and validation error if invalid. Invalid packs remain
visible only in an error state and cannot be selected for creation.

### `companion.hub.registry`

Stores user-created companion records in `<hub-root>/companions.json`. A record
has a stable ID, display name, absolute pack path, and an independent runtime
root `<hub-root>/runtimes/<id>`. Registry writes use the existing atomic JSON
writer. It never modifies a pack manifest.

### `companion.hub.processes`

Maintains the in-memory process handles that the current Hub started. Starting
a record invokes the existing CLI GUI path with that record's runtime root and
pack path. Showing/hiding emits normal `summon`/`dismiss` events through the
existing CLI/runtime semantics. Stopping terminates only a recorded Hub-owned
process and updates its visible status. After a Hub restart, an old process is
reported as `Not managed by this session`; the Hub does not terminate it.

### `companion.hub.window`

Tkinter window with three responsive regions:

- Collection: compact pack/companion cards with idle previews and human status.
- Living stage: selected preview, soft ambient effect, status, primary action
  (`Open`/`Start`) and secondary `Hide`, then a tertiary overflow menu.
- Context: current user-facing activity, last activity, and a personality
  summary derived from pack metadata or explicit product defaults, plus
  `Personalize` and an advanced-details affordance.

The window changes selected cards and button labels immediately; process status
is refreshed on a bounded timer. It uses one preview widget per selected
companion, replacing its image rather than stacking widgets.

On an empty registry, the first screen introduces Companion in user language
and offers `Create my companion` as the primary action. Users may instead open
the empty collection and add a local pack. The onboarding companion explains
that connecting a coding agent will arrive through Companion Forge; it does not
pretend that M11 can install or configure one.

## Persistence and paths

The Hub root defaults to the existing platform data directory plus `hub`; a
CLI `--hub-root` override is available for portable/testing use. Pack discovery
defaults to `<hub-root>/packs` and also accepts an explicit `--packs-dir`.
Created companion runtime roots are independent, preventing state-file lock
conflicts between pets.

## Error handling

- Missing/invalid packs show an inline error and disabled create action.
- A failed start preserves the prior UI selection and reports the subprocess
  error without crashing the Hub.
- Stop is idempotent for an already-exited Hub-owned process.
- No filesystem scan or subprocess action occurs from a pack display name.

## Packaging

`tools/build_exe.ps1` gains an explicit Hub build target and produces:

- `dist/companion.exe` for CLI/runtime use.
- `dist/Companion Hub.exe` for end users.

PyInstaller includes package source and bundled example packs when present.
The Hub makes no network requests.

## Verification

- Unit-test pack discovery with valid, invalid, and missing manifests.
- Unit-test registry round trips and unique independent runtime roots.
- Unit-test process ownership: Hub stops only handles it started.
- UI tests verify selected-record action labels and a single preview widget.
- UI tests verify the first-run routing and that Forge features are not exposed
  as executable actions in M11.
- Smoke-test both executable build commands and `companion hub --help`.
- Manual Windows check: discover Malbolge and Tabby Shinji, create two records,
  start one, hide/show it, stop it, and confirm the other remains unaffected.

## Acceptance criteria

- A user can open `Companion Hub.exe` without using a terminal.
- A first-time user understands how to create a visual companion and where the
  future guided coding-agent flow will live.
- At least Malbolge and Tabby Shinji appear as validated local packs when
  installed in the configured packs folder.
- Starting one companion does not share state files with another.
- Main UI stays consumer-focused; technical details are secondary.
- Hub does not kill processes it did not launch.
