"""Data records used by Companion Hub."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PackRecord:
    pack_id: str
    name: str
    root: Path
    preview: Path | None
    error: str | None


@dataclass(frozen=True)
class CompanionRecord:
    companion_id: str
    name: str
    pack_root: Path
    runtime_root: Path
