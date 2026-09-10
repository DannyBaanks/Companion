"""Deterministic local asset-pack discovery."""

from pathlib import Path

from ..pack import AssetPack
from .models import PackRecord


def discover_packs(packs_dir: Path) -> list[PackRecord]:
    """Discover valid and invalid packs one directory level below *packs_dir*."""
    if not packs_dir.is_dir():
        return []
    records: list[PackRecord] = []
    for candidate in packs_dir.iterdir():
        if not candidate.is_dir() or not (candidate / "manifest.json").is_file():
            continue
        try:
            pack = AssetPack.load(candidate)
        except Exception as exc:
            records.append(PackRecord(candidate.name, candidate.name, candidate.resolve(), None, str(exc)))
        else:
            records.append(
                PackRecord(
                    pack.pack_id,
                    pack.name,
                    pack.root,
                    pack.animation_for(state="idle"),
                    None,
                )
            )
    # Usable packs are presented first, while both groups remain deterministic.
    return sorted(records, key=lambda record: (record.error is not None, record.name.casefold(), record.pack_id))
