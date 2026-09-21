"""Pack Gallery — browse, preview, and validate companion packs.

M14: animated pack previews with author, license, palette, supported states,
Preview and Use-this-pack flows, visual contract documentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any

from .pack import AssetPack, PackError


@dataclass(frozen=True)
class PackInfo:
    """Extended pack metadata beyond the basic manifest."""
    pack: AssetPack
    author: str
    license: str
    description: str
    palette: list[str]  # hex colors
    preview_file: str | None = None  # optional animated preview

    @classmethod
    def load(cls, root: Path) -> "PackInfo":
        """Load a pack with extended gallery metadata."""
        pack = AssetPack.load(root)
        manifest_path = root / "manifest.json"
        try:
            data: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}

        return cls(
            pack=pack,
            author=str(data.get("author", "Unknown")),
            license=str(data.get("license", "Unknown")),
            description=str(data.get("description", "")),
            palette=[str(c) for c in data.get("palette", []) if isinstance(c, str)],
            preview_file=data.get("preview"),
        )

    @property
    def supported_states(self) -> list[str]:
        return sorted(self.pack.animations.keys())


@dataclass
class PackGallery:
    """Collection of discoverable packs."""
    packs: list[PackInfo] = field(default_factory=list)

    @classmethod
    def discover(cls, pack_dirs: list[Path]) -> "PackGallery":
        """Scan directories for valid packs with gallery metadata."""
        packs: list[PackInfo] = []
        for base in pack_dirs:
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir()):
                if child.is_dir() and (child / "manifest.json").exists():
                    try:
                        packs.append(PackInfo.load(child))
                    except (PackError, OSError):
                        continue
        return cls(packs=packs)

    def find(self, pack_id: str) -> PackInfo | None:
        for p in self.packs:
            if p.pack.pack_id == pack_id:
                return p
        return None

    def validate_preview(self, pack_id: str) -> tuple[bool, str]:
        """Validate that a pack's preview file exists and is loadable."""
        info = self.find(pack_id)
        if info is None:
            return False, f"pack not found: {pack_id}"
        if info.preview_file is None:
            return False, "no preview configured"
        preview_path = info.pack.root / info.preview_file
        if not preview_path.is_file():
            return False, f"preview file not found: {info.preview_file}"
        return True, "ok"
