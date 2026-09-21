"""Companion Forge — guided onboarding with declarative recipes.

M17: Create Companion as primary onboarding, intention-first choices,
portable declarative recipes with lifecycle:
  detect -> propose -> confirm -> execute -> verify -> receipt.

M18: Recipe ecosystem — capability contracts, provenance policies,
rollback/uninstall, import/export.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import json
import platform
import shutil
from typing import Any


class ForgeExecutionError(RuntimeError):
    """Raised when Forge cannot honestly execute a recipe step."""


# ── Recipe lifecycle states ──────────────────────────────────────────────────

class RecipeStage(str, Enum):
    DETECT = "detect"
    PROPOSE = "propose"
    CONFIRM = "confirm"
    EXECUTE = "execute"
    VERIFY = "verify"
    RECEIPT = "receipt"
    ROLLBACK = "rollback"


# ── Recipe definition ────────────────────────────────────────────────────────

@dataclass
class RecipeStep:
    """One atomic step in a recipe."""
    name: str
    action: str  # install | configure | symlink | download | verify | custom
    command: list[str] | None = None
    source: str | None = None      # URL or path
    checksum: str | None = None    # sha256 of downloaded artifact
    target: str | None = None      # installation target
    description: str = ""
    requires_elevation: bool = False
    rollback_action: list[str] | None = None


@dataclass
class Recipe:
    """A portable declarative recipe for creating a companion."""
    id: str
    name: str
    description: str
    author: str = ""
    license: str = ""
    version: str = "1.0.0"
    platform: list[str] = field(default_factory=lambda: ["any"])  # windows, linux, macos, any
    steps: list[RecipeStep] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)  # chat, notifications, status, actions
    source_url: str | None = None
    checksum: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Recipe":
        steps = []
        for s in data.get("steps", []):
            steps.append(RecipeStep(
                name=s.get("name", ""),
                action=s.get("action", "custom"),
                command=s.get("command"),
                source=s.get("source"),
                checksum=s.get("checksum"),
                target=s.get("target"),
                description=s.get("description", ""),
                requires_elevation=bool(s.get("requires_elevation", False)),
                rollback_action=s.get("rollback_action"),
            ))
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            author=str(data.get("author", "")),
            license=str(data.get("license", "")),
            version=str(data.get("version", "1.0.0")),
            platform=[str(p) for p in data.get("platform", ["any"])],
            steps=steps,
            capabilities=[str(c) for c in data.get("capabilities", [])],
            source_url=data.get("source_url"),
            checksum=data.get("checksum"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "version": self.version,
            "platform": self.platform,
            "steps": [
                {
                    "name": s.name,
                    "action": s.action,
                    **({"command": s.command} if s.command else {}),
                    **({"source": s.source} if s.source else {}),
                    **({"checksum": s.checksum} if s.checksum else {}),
                    **({"target": s.target} if s.target else {}),
                    **({"description": s.description} if s.description else {}),
                    **({"requires_elevation": True} if s.requires_elevation else {}),
                    **({"rollback_action": s.rollback_action} if s.rollback_action else {}),
                }
                for s in self.steps
            ],
            "capabilities": self.capabilities,
            **({"source_url": self.source_url} if self.source_url else {}),
            **({"checksum": self.checksum} if self.checksum else {}),
        }


# ── Recipe execution receipt ─────────────────────────────────────────────────

@dataclass
class RecipeReceipt:
    """Verifiable receipt after recipe execution."""
    recipe_id: str
    recipe_version: str
    executed_at: str
    platform: str
    steps_completed: list[str]
    steps_failed: list[str]
    rollback_performed: bool = False
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "recipe_version": self.recipe_version,
            "executed_at": self.executed_at,
            "platform": self.platform,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "rollback_performed": self.rollback_performed,
            "verified": self.verified,
        }


# ── Platform detection ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class PlatformInfo:
    os: str
    arch: str
    python_version: str

    @classmethod
    def detect(cls) -> "PlatformInfo":
        return cls(
            os=platform.system().lower(),
            arch=platform.machine().lower(),
            python_version=platform.python_version(),
        )

    def matches(self, requirements: list[str]) -> bool:
        if "any" in requirements:
            return True
        return self.os in requirements


# ── Recipe store ─────────────────────────────────────────────────────────────

class RecipeStore:
    """Persistent recipe collection."""

    def __init__(self, root: Path):
        self.root = root
        self.recipes_dir = root / "recipes"

    def save(self, recipe: Recipe) -> Path:
        self.recipes_dir.mkdir(parents=True, exist_ok=True)
        path = self.recipes_dir / f"{recipe.id}.json"
        path.write_text(json.dumps(recipe.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def load(self, recipe_id: str) -> Recipe | None:
        path = self.recipes_dir / f"{recipe_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Recipe.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None

    def list_recipes(self) -> list[Recipe]:
        if not self.recipes_dir.is_dir():
            return []
        recipes: list[Recipe] = []
        for p in sorted(self.recipes_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                recipes.append(Recipe.from_dict(data))
            except (json.JSONDecodeError, OSError):
                continue
        return recipes

    def remove(self, recipe_id: str) -> bool:
        path = self.recipes_dir / f"{recipe_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def export(self, recipe_id: str, dest: Path) -> bool:
        recipe = self.load(recipe_id)
        if recipe is None:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(recipe.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return True

    def import_recipe(self, source: Path) -> Recipe | None:
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
            recipe = Recipe.from_dict(data)
            if recipe.id:
                self.save(recipe)
                return recipe
        except (json.JSONDecodeError, OSError):
            pass
        return None


# ── Forge engine ─────────────────────────────────────────────────────────────

class Forge:
    """Guided onboarding engine: detect, propose, confirm, execute, verify."""

    def __init__(self, data_root: Path, *, dry_run: bool = True):
        self.data_root = data_root
        self.dry_run = dry_run
        self.platform = PlatformInfo.detect()

    def detect(self, recipe: Recipe) -> tuple[bool, str]:
        """Check if the recipe can run on this platform."""
        if not self.platform.matches(recipe.platform):
            return False, f"platform mismatch: need {recipe.platform}, have {self.platform.os}"
        return True, "platform compatible"

    def propose(self, recipe: Recipe) -> dict[str, Any]:
        """Generate a human-readable proposal for the recipe."""
        steps_info = []
        for i, step in enumerate(recipe.steps, 1):
            steps_info.append({
                "step": i,
                "name": step.name,
                "action": step.action,
                "description": step.description,
                "requires_elevation": step.requires_elevation,
                "has_rollback": step.rollback_action is not None,
            })
        return {
            "recipe": recipe.name,
            "version": recipe.version,
            "author": recipe.author,
            "license": recipe.license,
            "description": recipe.description,
            "capabilities": recipe.capabilities,
            "total_steps": len(recipe.steps),
            "steps": steps_info,
            "platform": self.platform.os,
            "dry_run": self.dry_run,
        }

    def execute(self, recipe: Recipe) -> RecipeReceipt:
        """Execute the recipe steps (or simulate in dry_run mode)."""
        if not self.dry_run:
            raise ForgeExecutionError(
                "recipe execution is not implemented; use dry_run=True until "
                "a constrained executor is available"
            )
        completed: list[str] = []
        failed: list[str] = []

        for step in recipe.steps:
            completed.append(step.name)

        return RecipeReceipt(
            recipe_id=recipe.id,
            recipe_version=recipe.version,
            executed_at=datetime.now(timezone.utc).isoformat(),
            platform=self.platform.os,
            steps_completed=completed,
            steps_failed=failed,
        )

    def verify(self, recipe: Recipe, receipt: RecipeReceipt) -> tuple[bool, str]:
        """Verify that the recipe was applied correctly."""
        if receipt.steps_failed:
            return False, f"failed steps: {', '.join(receipt.steps_failed)}"
        if len(receipt.steps_completed) != len(recipe.steps):
            return False, "not all steps completed"
        return True, "all steps verified"
