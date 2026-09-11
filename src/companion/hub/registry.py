"""Atomic persistence for independent local companion runtimes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..storage import atomic_write_json, read_json_with_recovery
from .models import CompanionRecord


_REGISTRY_VERSION = 1


class CompanionRegistry:
    def __init__(self, path: Path, runtimes_dir: Path):
        self.path = Path(path)
        self.runtimes_dir = Path(runtimes_dir)

    def list(self) -> list[CompanionRecord]:
        payload, _ = read_json_with_recovery(self.path, default={"version": _REGISTRY_VERSION, "companions": []})
        if not isinstance(payload, dict) or payload.get("version") != _REGISTRY_VERSION:
            return []
        entries = payload.get("companions", [])
        if not isinstance(entries, list):
            return []
        records: list[CompanionRecord] = []
        for entry in entries:
            try:
                records.append(self._from_json(entry))
            except (TypeError, ValueError, KeyError):
                continue
        return records

    def create(self, name: str, pack_root: Path) -> CompanionRecord:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("companion name must be a non-empty string")
        companion_id = self._new_id(name)
        record = CompanionRecord(
            companion_id=companion_id,
            name=name,
            pack_root=Path(pack_root).resolve(),
            runtime_root=(self.runtimes_dir / companion_id).resolve(),
        )
        record.runtime_root.mkdir(parents=True, exist_ok=False)
        try:
            records = self.list()
            records.append(record)
            self._save(records)
        except Exception:
            try:
                record.runtime_root.rmdir()
            except OSError:
                pass
            raise
        return record

    def get(self, companion_id: str) -> CompanionRecord | None:
        return next((record for record in self.list() if record.companion_id == companion_id), None)

    def _new_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "companion"
        used = {record.companion_id for record in self.list()}
        if base not in used and not (self.runtimes_dir / base).exists():
            return base
        suffix = 2
        while f"{base}-{suffix}" in used or (self.runtimes_dir / f"{base}-{suffix}").exists():
            suffix += 1
        return f"{base}-{suffix}"

    def _save(self, records: list[CompanionRecord]) -> None:
        atomic_write_json(
            self.path,
            {
                "version": _REGISTRY_VERSION,
                "companions": [self._to_json(record) for record in records],
            },
        )

    @staticmethod
    def _to_json(record: CompanionRecord) -> dict[str, str]:
        return {
            "companion_id": record.companion_id,
            "name": record.name,
            "pack_root": str(record.pack_root),
            "runtime_root": str(record.runtime_root),
        }

    @staticmethod
    def _from_json(entry: Any) -> CompanionRecord:
        if not isinstance(entry, dict):
            raise TypeError("companion entry must be an object")
        return CompanionRecord(
            companion_id=str(entry["companion_id"]),
            name=str(entry["name"]),
            pack_root=Path(entry["pack_root"]),
            runtime_root=Path(entry["runtime_root"]),
        )
