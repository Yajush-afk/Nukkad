import io

from fastapi.testclient import TestClient
from PIL import Image

from nukkad.app import create_app
from nukkad.backups import backup, restore
from nukkad.storage import Store


def test_map_visit_is_idempotent_personal_memory_without_a_quest(registry, tmp_path):
    maps, store, snapshot, _, _ = registry
    source = snapshot["places"][0]["id"]
    key = "a" * 32
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        endpoint = f"/api/places/{source}/experiences/{key}"
        value = {"note": "I noticed the leaves and listened to the birds."}
        first = client.put(endpoint, json=value)
        assert first.status_code == 200, first.text
        experience = first.json()
        assert experience["outcome_id"] is None
        assert experience["provenance"] == "self-reported visit from saved map"
        assert client.put(endpoint, json=value).json()["revision"] == experience["revision"]
        assert not store.list("quest") and not store.list("outcome")
        assert len(store.list("experience")) == 1
        assert client.get("/api/collection").json()["folders"][0]["visits"] == 1
        assert next(p for p in client.get("/api/area").json()["places"] if p["id"] == source)[
            "visited"
        ]
        assert client.put(endpoint, json={"note": "A changed note"}).status_code == 409
        assert (
            client.put(
                endpoint, json={"note": "A changed note", "source_revision": experience["revision"]}
            ).status_code
            == 200
        )
        picture = io.BytesIO()
        Image.new("RGB", (48, 48), "green").save(picture, "PNG")
        assert (
            client.post(
                f"/api/experiences/{key}/photos",
                files={"photo": ("sample.png", picture.getvalue(), "image/png")},
            ).status_code
            == 201
        )
        assert (
            client.put("/api/places/missing/experiences/" + "b" * 32, json=value).status_code == 404
        )
        assert (
            client.put(
                "/api/places/" + source + "/experiences/" + "b" * 32,
                json={"note": "A future visit", "visit_date": "2999-01-01"},
            ).status_code
            == 422
        )
    archive = backup(maps.config)
    restored = tmp_path / "restored"
    restore(archive, restored)
    assert Store(restored).get("experience", key)["note"] == "A changed note"
    assert len(Store(restored).list("photo")) == 1
    assert Store(restored).get("snapshot", snapshot["id"]) == snapshot
