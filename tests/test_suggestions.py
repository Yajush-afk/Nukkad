import time

from fastapi.testclient import TestClient

from nukkad.app import create_app
from nukkad.cache import RevisionCache
from nukkad.suggestions import SuggestInput, local_matches


def test_local_suggestions_need_no_graph_and_resolve_aliases(registry, monkeypatch):
    maps, store, _, _, _ = registry
    monkeypatch.setattr(
        type(maps), "graph", lambda *args: (_ for _ in ()).throw(AssertionError("graph"))
    )
    place = maps.snapshot()["places"][0]
    store.put("place_alias", place["id"], {"canonical_id": "known"})
    store.put("place_alias", "osm-node-999", {"canonical_id": "known"})
    store.put(
        "location_search",
        "cached",
        {
            "expires_at": time.time() + 600,
            "matches": [
                {
                    "name": place["name"],
                    "label": "Old result",
                    "point": place["point"],
                    "source_id": "osm-node-999",
                }
            ],
        },
    )
    matches = local_matches(store, RevisionCache(), SuggestInput(query=place["name"]))
    assert matches[0]["place_id"] == "known"
    assert len(matches) == 1


def test_local_endpoint_is_offline_and_does_not_change_area(registry):
    maps, store, _, _, _ = registry
    original = store.get("area", "active")
    place = maps.snapshot()["places"][0]
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/locations/suggest",
            json={"query": place["name"]},
            headers={"X-Nukkad-Token": token},
        )
        assert response.status_code == 200
        assert response.json()["matches"][0]["group"] == "On your map"
        assert response.json()["online"]["status"] == "not_requested"
        assert (
            client.post(
                "/api/locations/suggest", json={"query": "ab"}, headers={"X-Nukkad-Token": token}
            ).status_code
            == 422
        )
    assert store.get("area", "active") == original


def test_index_invalidation_keeps_nearby_same_names_separate(registry):
    maps, store, _, _, _ = registry
    cache = RevisionCache()
    original = maps.snapshot()["places"][0]
    value = SuggestInput(query=original["name"], scope="place")
    first = local_matches(store, cache, value)
    other = {**original, "id": "custom", "source": "user"}
    store.put("place", "custom", other)
    second = local_matches(store, cache, value)
    assert len(second) == len(first) + 1
    store.put("place", "custom", {**other, "name": "Changed name"})
    assert len(local_matches(store, cache, value)) == len(first)
