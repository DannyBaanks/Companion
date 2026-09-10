"""Companion Hub catalog and local companion registry."""

from .discovery import discover_packs
from .models import CompanionRecord, PackRecord
from .registry import CompanionRegistry

__all__ = ["CompanionRecord", "CompanionRegistry", "PackRecord", "discover_packs"]
