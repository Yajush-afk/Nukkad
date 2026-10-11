from fastapi.testclient import TestClient
from test_location_cards import prepared, token

from nukkad.app import create_app


def test_direct_visit_appears_without_creating_a_walk_or_running_ai(registry, monkeypatch):
    def forbidden(*args):
        raise AssertionError("Reading activity must not use maps or AI")

    monkeypatch.setattr("nukkad.ollama.Ollama.generate", forbidden)
    maps, store, snapshot = registry[:3]
    key, place = "a" * 32, snapshot["places"][0]["id"]
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        token(client)
        endpoint = f"/api/places/{place}/experiences/{key}"
        visit = client.put(endpoint, json={"note": "I enjoyed noticing the leaves."}).json()
        monkeypatch.setattr("nukkad.areas_api.maps", forbidden)
        before = store.keyed("experience")
        for _ in range(2):
            result = client.get("/api/activity")
            assert result.status_code == 200
            activity = result.json()
            assert activity["planned_walk_count"] == 0
            assert activity["place_visit_count"] == 1
            entry = activity["entries"][0]
            assert entry["id"] == "visit:" + key and entry["kind"] == "place_visit"
            assert entry["note"] == visit["note"] and entry["place_id"] == place
        assert store.keyed("experience") == before
        assert not store.list("quest") and not store.list("job")
        changed = client.put(
            endpoint,
            json={
                "note": "I enjoyed leaves and bird sounds.",
                "source_revision": visit["revision"],
            },
        )
        assert changed.status_code == 200
        updated = client.get("/api/activity").json()
        assert updated["place_visit_count"] == 1
        assert updated["entries"][0]["note"] == changed.json()["note"]


def test_mixed_activity_preserves_walks_and_excludes_their_individual_stops(registry):
    experience, photo, quest, _ = prepared(registry)
    store = registry[1]
    quest.update(created_at="2026-10-10T10:00:00+00:00", timezone="Asia/Kolkata")
    store.put("quest", quest["id"], quest)
    direct = {
        **experience,
        "id": "direct",
        "source_kind": "place",
        "outcome_id": None,
        "place_id": "old-source",
        "visit_date": "2026-10-11T10:00:00+00:00",
    }
    store.put("experience", "direct", direct)
    store.put("experience", "skipped", {**direct, "id": "skipped", "active": False})
    store.put("place_alias", "old-source", {"canonical_id": "osm-way-20"})
    store.put("photo", "direct-photo", {**photo, "experience_id": "direct"})
    store.put("photo", "removed", {**photo, "experience_id": "direct", "active": False})
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        first = client.get("/api/activity").json()
        assert first["planned_walk_count"] == first["place_visit_count"] == 1
        visit, walk = first["entries"]
        assert visit["place_id"] == "osm-way-20" and visit["photo_count"] == 1
        assert walk["quest"] == quest and walk["outcome"]["quest_id"] == quest["id"]
        assert len(first["entries"]) == 2
        assert client.get("/api/activity").json() == first


def test_empty_activity_is_readable_without_setup(registry):
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        assert client.get("/api/activity").json() == {
            "entries": [],
            "planned_walk_count": 0,
            "place_visit_count": 0,
        }
