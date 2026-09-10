from companion.hub.registry import CompanionRegistry


def test_registry_round_trip_uses_independent_runtime_roots(tmp_path):
    registry = CompanionRegistry(tmp_path / "companions.json", tmp_path / "runtimes")
    a = registry.create("Malbolge", tmp_path / "packs" / "malbolge")
    b = registry.create("Shinji", tmp_path / "packs" / "shinji")

    assert a.runtime_root != b.runtime_root
    assert a.pack_root == (tmp_path / "packs" / "malbolge").resolve()
    assert CompanionRegistry(registry.path, registry.runtimes_dir).get(a.companion_id) == a
    assert [item.companion_id for item in registry.list()] == ["malbolge", "shinji"]


def test_registry_adds_collision_suffix_and_persists_version(tmp_path):
    registry = CompanionRegistry(tmp_path / "companions.json", tmp_path / "runtimes")
    first = registry.create("My Friend", tmp_path / "one")
    second = registry.create("My Friend", tmp_path / "two")

    assert first.companion_id == "my-friend"
    assert second.companion_id == "my-friend-2"
    assert registry.path.exists()
    assert registry.path.read_text(encoding="utf-8").find('"version": 1') >= 0
