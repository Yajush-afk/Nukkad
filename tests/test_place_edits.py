from fastapi.testclient import TestClient

from nukkad.app import create_app


def test_custom_place_boundary_is_checked_before_graph_loading(registry, monkeypatch):
    maps, store, _, _, _ = registry
    monkeypatch.setattr(
        type(maps), "graph", lambda *args: (_ for _ in ()).throw(AssertionError("graph loaded"))
    )
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/places",
            json={
                "name": "Outside",
                "kind": "park",
                "entrance": {"lat": 0, "lon": 0},
                "public_access_confirmed": True,
            },
        )
        assert response.status_code == 422
        assert "inside your saved neighbourhood" in response.json()["detail"]
        assert not store.list("place")


def test_report_status_preserves_canonical_identity_and_history(registry):
    maps, store, _, _, _ = registry
    place = maps.places()[0]
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        response = client.patch(
            "/api/places/" + place.id,
            json={"action": "closed", "detail": "Gate was shut during the reported visit"},
        )
        assert response.status_code == 200
        updated = client.get("/api/area").json()["places"][0]
        assert updated["id"] == place.id and updated["last_report"] == "closed"
        assert store.list("correction")[0]["place_id"] == place.id
