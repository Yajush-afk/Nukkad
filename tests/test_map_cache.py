from fastapi.testclient import TestClient

from nukkad.app import create_app


def test_repeated_graph_loads_reuse_parsing_without_sharing_mutations(registry, monkeypatch):
    import nukkad.maps as module

    maps, _, snapshot = registry[:3]
    parse = module.ox.load_graphml
    calls = []

    def load(*args, **kwargs):
        calls.append(1)
        return parse(*args, **kwargs)

    monkeypatch.setattr(module.ox, "load_graphml", load)
    first = maps.graph(snapshot)
    first.remove_node(next(iter(first)))
    second = maps.graph(snapshot)
    assert len(calls) == 1
    assert second.number_of_nodes() > first.number_of_nodes()


def test_area_status_does_not_compute_places_or_read_the_graph(registry, monkeypatch):
    def unwanted(*args, **kwargs):
        raise AssertionError("Lightweight status must not prepare a map")

    monkeypatch.setattr("nukkad.maps.Maps.places", unwanted)
    monkeypatch.setattr("nukkad.maps.Maps.graph", unwanted)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        response = client.get("/api/area/status")
        assert response.status_code == 200
        assert response.json()["area"]["public_start_confirmed"]


def test_area_results_cache_and_invalidate_for_reported_visits(registry, monkeypatch):
    from nukkad.maps import Maps

    places = Maps.places
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return places(*args, **kwargs)

    monkeypatch.setattr(Maps, "places", counted)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        first = client.get("/api/area").json()
        assert client.get("/api/area").json() == first
        assert len(calls) == 1
        registry[1].put("outcome", "reported", {"id": "reported", "reached_ids": ["osm-way-20"]})
        assert client.get("/api/area").json()["progress"]["mapped_visited"] == 1
        assert len(calls) == 2


def test_cached_graph_still_rejects_damaged_files(registry):
    import pytest

    maps, _, snapshot = registry[:3]
    maps.graph(snapshot)
    path = maps.config.data_dir / "snapshots" / snapshot["id"] / "walking.graphml"
    content = bytearray(path.read_bytes())
    content[-1] ^= 1
    path.write_bytes(content)
    with pytest.raises(ValueError, match="integrity"):
        maps.graph(snapshot)


def test_duplicate_cache_invalidates_after_review(registry, monkeypatch):
    import nukkad.areas_api as module

    place = registry[0].places()[0].model_dump()
    registry[1].put("place", "custom-test", {**place, "id": "custom-test", "source": "user"})
    candidates = module.duplicate_candidates
    calls = []

    def counted(*args):
        calls.append(1)
        return candidates(*args)

    monkeypatch.setattr(module, "duplicate_candidates", counted)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        pairs = client.get("/api/places/duplicates").json()
        assert len(pairs) == 1
        assert client.get("/api/places/duplicates").json() == pairs
        assert len(calls) == 1
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        assert (
            client.patch(
                "/api/places/duplicates/" + pairs[0]["id"], json={"decision": "separate"}
            ).status_code
            == 200
        )
        assert client.get("/api/places/duplicates").json() == []
        assert len(calls) == 2


def test_bulk_alias_lookup_supports_legacy_records_without_embedded_id(registry):
    registry[1].put("place_alias", "osm-way-20", {"canonical_id": "reviewed-place"})
    assert registry[0].places()[0].id == "reviewed-place"


def test_area_cache_invalidates_for_corrections_aliases_and_new_snapshots(registry, monkeypatch):
    from nukkad.maps import Maps

    original = Maps.places
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(Maps, "places", counted)
    store = registry[1]
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        client.get("/api/area").raise_for_status()
        place = registry[0].places()[0].model_dump()
        calls.clear()
        store.put("place", place["id"], {**place, "valid": False})
        assert client.get("/api/area").json()["places"][0]["valid"] is False
        assert len(calls) == 1
        store.put("place_alias", place["id"], {"canonical_id": "reviewed-place"})
        assert client.get("/api/area").json()["places"][0]["id"] == "reviewed-place"
        assert len(calls) == 2
        snapshot = store.get("snapshot", registry[2]["id"])
        store.put("snapshot", snapshot["id"], {**snapshot, "source": "reviewed fixture"})
        assert client.get("/api/area").json()["source"] == "reviewed fixture"
        assert len(calls) == 3


def test_revision_cache_is_bounded_and_does_not_cache_failures():
    import pytest

    from nukkad.cache import RevisionCache

    cache = RevisionCache(capacity=2)
    calls = []

    def build():
        calls.append(1)
        return {"items": []}

    value = cache.get("test", 1, build)
    value["items"].append("Caller mutation")
    assert cache.get("test", 1, build) == {"items": []}
    cache.get("test", 2, build)
    cache.get("test", 3, build)
    assert len(cache.values) == 2
    cache.get("test", 1, build)
    assert len(calls) == 4
    with pytest.raises(ValueError):
        cache.get("broken", 1, lambda: (_ for _ in ()).throw(ValueError()))
    assert cache.get("broken", 1, build) == {"items": []}
