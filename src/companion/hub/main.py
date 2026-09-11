"""Local composition root and console entry point for Companion Hub."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile

from ..paths import default_data_dir
from .discovery import discover_packs
from .processes import ProcessManager
from .registry import CompanionRegistry


def default_hub_root() -> Path:
    """Return the private local data root used by the Hub."""
    return default_data_dir() / "hub"


def bundled_packs_dir() -> Path:
    """Locate packs bundled beside source or extracted by PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "packs"
    return Path(__file__).resolve().parents[3] / "packs"


def default_packs_dir(hub_root: Path) -> Path:
    """Prefer user-local packs, falling back to packs shipped with the app."""
    local_packs = hub_root / "packs"
    return local_packs if local_packs.is_dir() else bundled_packs_dir()


def _directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def materialize_bundled_packs(packs_dir: Path, hub_root: Path) -> Path:
    """Copy an ephemeral bundle to a stable, content-addressed Hub snapshot."""
    source = packs_dir.resolve()
    snapshot_root = hub_root / "bundled-packs"
    snapshot = snapshot_root / _directory_digest(source)
    if snapshot.is_dir():
        return snapshot

    snapshot_root.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix="bundled-packs-", dir=snapshot_root))
    try:
        staged_snapshot = temporary_root / "packs"
        shutil.copytree(source, staged_snapshot)
        try:
            staged_snapshot.replace(snapshot)
        except FileExistsError:
            if not snapshot.is_dir():
                raise
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
    return snapshot


def _is_ephemeral_bundle_path(packs_dir: Path) -> bool:
    return getattr(sys, "frozen", False) and packs_dir.resolve() == bundled_packs_dir().resolve()


def runtime_command() -> list[str]:
    """Return an argument-safe command for the existing Companion runtime."""
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve().with_name("companion.exe")
        if not executable.is_file():
            raise RuntimeError("Companion Hub needs companion.exe beside its executable.")
        return [str(executable)]
    return [sys.executable, "-m", "companion.cli"]


def open_hub(*, hub_root: Path, packs_dir: Path) -> None:
    """Construct one Hub window from local services, then enter Tk's loop."""
    hub_root.mkdir(parents=True, exist_ok=True)
    runtimes_dir = hub_root / "runtimes"
    runtimes_dir.mkdir(parents=True, exist_ok=True)
    if _is_ephemeral_bundle_path(packs_dir):
        packs_dir = materialize_bundled_packs(packs_dir, hub_root)
    registry = CompanionRegistry(hub_root / "companions.json", runtimes_dir)
    packs = discover_packs(packs_dir)
    processes = ProcessManager(runtime_command())

    import tkinter as tk

    from .window import HubWindow

    root = tk.Tk()
    HubWindow(root, packs, registry, processes)
    root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="companion-hub", description="Open your local Companion Hub.")
    parser.add_argument("--hub-root", type=Path, help="local directory for Hub companion data")
    parser.add_argument("--packs-dir", type=Path, help="local directory containing companion packs")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Open the Hub after parsing local-only launch options."""
    args = build_parser().parse_args(argv)
    hub_root = args.hub_root.expanduser().resolve() if args.hub_root else default_hub_root().resolve()
    packs_dir = args.packs_dir.expanduser().resolve() if args.packs_dir else default_packs_dir(hub_root).resolve()
    open_hub(hub_root=hub_root, packs_dir=packs_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
