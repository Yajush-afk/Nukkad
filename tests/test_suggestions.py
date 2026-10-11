import time

from fastapi.testclient import TestClient
from httpx import Client as RealClient

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


def photon_fixture(store, monkeypatch, payload=None, status=200):
    import httpx

    from nukkad.photon import Photon

    real = RealClient
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, json=payload or {"features": []})

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(respond), **kw)
    )
    return Photon(), calls


def feature(name="Sample place", lon=77.36, lat=28.639):
    return {
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"name": name, "city": "Sample city", "osm_type": "N", "osm_id": 999},
    }


def test_photon_bounds_cache_and_identity(registry, monkeypatch):
    _, store, _, _, _ = registry
    store.put("place_alias", "osm-node-999", {"canonical_id": "known"})
    service, calls = photon_fixture(store, monkeypatch, {"features": [feature(), feature(lon=0)]})
    query = SuggestInput(query="Sample", scope="place", online=True)
    matches, status = service.search(store, query)
    assert len(matches) == 1 and matches[0]["place_id"] == "known"
    assert calls[0].url.params["bbox"]
    assert calls[0].url.params["lang"] == "en"
    assert calls[0].url.params["limit"] == "5"
    assert service.search(store, query)[1]["cached"]
    assert len(calls) == 1
    assert "query" not in store.list("location_suggestion")[0]
    assert all(len(key) == 64 for key in store.keyed("location_suggestion"))


def test_photon_failures_and_cooldown_never_retry(registry, monkeypatch):
    _, store, _, _, _ = registry
    service, calls = photon_fixture(store, monkeypatch, status=429)
    value = SuggestInput(query="Sample", online=True)
    assert service.search(store, value)[1]["cooldown_seconds"] == 60
    assert service.search(store, value)[1]["status"] == "cooldown"
    assert len(calls) == 1 and not store.list("location_suggestion")


def test_photon_malformed_response_and_cache_limit(registry, monkeypatch):
    _, store, _, _, _ = registry
    service, _ = photon_fixture(store, monkeypatch, {"bad": True})
    value = SuggestInput(query="Sample", online=True)
    assert service.search(store, value)[1]["status"] == "unavailable"
    assert not store.list("location_suggestion")
    for index in range(256):
        store.put(
            "location_suggestion", str(index), {"matches": [], "expires_at": time.time() + 600}
        )
    service, _ = photon_fixture(store, monkeypatch)
    assert service.search(store, value)[1]["status"] == "available"
    assert len(store.list("location_suggestion")) == 256


def test_photon_starts_are_spaced_without_nominatim(registry, monkeypatch):
    from nukkad import photon

    _, store, _, _, _ = registry
    service, calls = photon_fixture(store, monkeypatch)
    clock = [10.0]
    monkeypatch.setattr(photon.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(photon.time, "sleep", lambda wait: clock.__setitem__(0, clock[0] + wait))
    service.search(store, SuggestInput(query="First"))
    service.search(store, SuggestInput(query="Second"))
    assert clock[0] >= 11 and len(calls) == 2
    assert all("photon" in str(call.url) for call in calls)


def test_photon_keeps_only_newest_pending_query(registry, monkeypatch):
    import threading

    import httpx

    from nukkad.photon import Photon

    _, store, _, _, _ = registry
    entered, release = threading.Event(), threading.Event()
    calls = []

    def handler(request):
        calls.append(request.url.params["q"])
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return httpx.Response(200, json={"features": []})

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: RealClient(transport=httpx.MockTransport(handler), **kw)
    )
    service = Photon()
    results = {}

    def work(query):
        results[query] = service.search(store, SuggestInput(query=query))[1]["status"]

    first = threading.Thread(target=work, args=("First",))
    first.start()
    assert entered.wait(2)
    second = threading.Thread(target=work, args=("Second",))
    second.start()
    deadline = time.monotonic() + 2
    while service.pending is None and time.monotonic() < deadline:
        time.sleep(0.01)
    third = threading.Thread(target=work, args=("Third",))
    third.start()
    second.join(2)
    release.set()
    first.join(2)
    third.join(3)
    assert results["Second"] == "superseded"
    assert calls == ["First", "Third"]
