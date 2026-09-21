"""Tests for Pack Gallery (M14), Personality (M15), and Activity Timeline (M16)."""

import json
from pathlib import Path

from companion.gallery import PackGallery, PackInfo
from companion.personality import DEFAULT_PROFILE, PersonalityProfile, PersonalityStore
from companion.timeline import ActivityTimeline, TimelineEntry


# ── M14: Pack Gallery ────────────────────────────────────────────────────────

def _make_pack(root: Path, pack_id: str = "cat", **manifest_extra):
    pack_dir = root / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "idle.png").write_bytes(b"img")
    (pack_dir / "success.png").write_bytes(b"img2")
    manifest = {"id": pack_id, "name": pack_id.title(), "animations": {"idle": "idle.png", "success": "success.png"}}
    manifest.update(manifest_extra)
    (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pack_dir


def test_pack_info_loads_extended_metadata(tmp_path):
    pack_dir = _make_pack(tmp_path, author="Danny", license="MIT", description="A cat",
                          palette=["#ff0000", "#00ff00"], preview="idle.png")
    info = PackInfo.load(pack_dir)
    assert info.author == "Danny"
    assert info.license == "MIT"
    assert info.palette == ["#ff0000", "#00ff00"]
    assert info.supported_states == ["idle", "success"]


def test_pack_info_defaults_when_missing(tmp_path):
    pack_dir = _make_pack(tmp_path)
    info = PackInfo.load(pack_dir)
    assert info.author == "Unknown"
    assert info.license == "Unknown"
    assert info.palette == []


def test_pack_gallery_discover(tmp_path):
    _make_pack(tmp_path, "alpha")
    _make_pack(tmp_path, "beta")
    gallery = PackGallery.discover([tmp_path])
    assert len(gallery.packs) == 2


def test_pack_gallery_find(tmp_path):
    _make_pack(tmp_path, "alpha")
    gallery = PackGallery.discover([tmp_path])
    assert gallery.find("alpha") is not None
    assert gallery.find("nope") is None


def test_pack_gallery_validate_preview(tmp_path):
    pack_dir = _make_pack(tmp_path, "cat", preview="idle.png")
    gallery = PackGallery.discover([tmp_path])
    ok, msg = gallery.validate_preview("cat")
    assert ok is True


def test_pack_gallery_validate_preview_missing(tmp_path):
    _make_pack(tmp_path, "cat", preview="missing.gif")
    gallery = PackGallery.discover([tmp_path])
    ok, msg = gallery.validate_preview("cat")
    assert ok is False
    assert "not found" in msg


def test_pack_gallery_validate_preview_no_preview(tmp_path):
    _make_pack(tmp_path, "cat")
    gallery = PackGallery.discover([tmp_path])
    ok, msg = gallery.validate_preview("cat")
    assert ok is False
    assert "no preview" in msg


def test_pack_gallery_validate_preview_unknown_pack(tmp_path):
    gallery = PackGallery.discover([tmp_path])
    ok, msg = gallery.validate_preview("nope")
    assert ok is False
    assert "not found" in msg


# ── M15: Personality ─────────────────────────────────────────────────────────

def test_personality_profile_defaults():
    p = DEFAULT_PROFILE
    assert p.tone == "friendly"
    assert p.verbosity == "normal"
    assert p.greeting == "Hello!"


def test_personality_message_for_state():
    p = PersonalityProfile(success_message="Great!", error_prefix="Err:")
    assert p.message_for_state("success") == "Great!"
    assert p.message_for_state("error", "boom") == "Err: boom"
    assert p.message_for_state("thinking") == "Thinking..."
    assert p.message_for_state("idle") == "Ready."


def test_personality_roundtrip():
    p = PersonalityProfile(tone="formal", greeting="Greetings.")
    d = p.to_dict()
    restored = PersonalityProfile.load(d)
    assert restored.tone == "formal"
    assert restored.greeting == "Greetings."


def test_personality_store_save_load(tmp_path):
    store = PersonalityStore(tmp_path)
    p = PersonalityProfile(tone="playful")
    store.save(p)
    loaded = store.load()
    assert loaded.tone == "playful"


def test_personality_store_load_defaults_on_missing(tmp_path):
    store = PersonalityStore(tmp_path)
    loaded = store.load()
    assert loaded is DEFAULT_PROFILE


def test_personality_store_load_defaults_on_corrupt(tmp_path):
    (tmp_path / "personality.json").write_text("bad", encoding="utf-8")
    store = PersonalityStore(tmp_path)
    loaded = store.load()
    assert loaded is DEFAULT_PROFILE


# ── M16: Activity Timeline ───────────────────────────────────────────────────

def test_timeline_append_and_read(tmp_path):
    tl = ActivityTimeline(tmp_path)
    tl.append(TimelineEntry(timestamp="2026-01-01T00:00:00Z", event_type="say", agent="cli", detail="hello"))
    entries = tl.entries()
    assert len(entries) == 1
    assert entries[0].event_type == "say"
    assert entries[0].detail == "hello"


def test_timeline_filter_by_agent(tmp_path):
    tl = ActivityTimeline(tmp_path)
    tl.append(TimelineEntry(timestamp="t1", event_type="say", agent="alice"))
    tl.append(TimelineEntry(timestamp="t2", event_type="say", agent="bob"))
    assert len(tl.entries(agent="alice")) == 1
    assert len(tl.entries(agent="bob")) == 1


def test_timeline_filter_by_companion_id(tmp_path):
    tl = ActivityTimeline(tmp_path)
    tl.append(TimelineEntry(timestamp="t1", event_type="state", agent="x", companion_id="alpha"))
    tl.append(TimelineEntry(timestamp="t2", event_type="state", agent="x", companion_id="beta"))
    assert len(tl.entries(companion_id="alpha")) == 1


def test_timeline_filter_by_type(tmp_path):
    tl = ActivityTimeline(tmp_path)
    tl.append(TimelineEntry(timestamp="t1", event_type="say", agent="x"))
    tl.append(TimelineEntry(timestamp="t2", event_type="state", agent="x"))
    assert len(tl.entries(event_type="say")) == 1


def test_timeline_export_jsonl(tmp_path):
    tl = ActivityTimeline(tmp_path)
    tl.append(TimelineEntry(timestamp="t1", event_type="say", agent="cli"))
    tl.append(TimelineEntry(timestamp="t2", event_type="state", agent="cli"))
    dest = tmp_path / "export.jsonl"
    count = tl.export_jsonl(dest, event_type="say")
    assert count == 1
    lines = dest.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event_type"] == "say"


def test_timeline_summary(tmp_path):
    tl = ActivityTimeline(tmp_path)
    tl.append(TimelineEntry(timestamp="t1", event_type="say", agent="cli", source="event"))
    tl.append(TimelineEntry(timestamp="t2", event_type="say", agent="hook", source="adapter"))
    s = tl.summary()
    assert s["total"] == 2
    assert s["by_type"]["say"] == 2
    assert s["by_source"]["adapter"] == 1


def test_timeline_empty(tmp_path):
    tl = ActivityTimeline(tmp_path)
    assert tl.entries() == []
    assert tl.summary()["total"] == 0


def test_timeline_entry_roundtrip():
    e = TimelineEntry(timestamp="t", event_type="x", agent="a", companion_id="c", detail="d", source="adapter")
    d = e.to_dict()
    restored = TimelineEntry.from_dict(d)
    assert restored.companion_id == "c"
    assert restored.source == "adapter"
