import io

from fastapi.testclient import TestClient
from PIL import Image
from test_location_cards import wait

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
        from nukkad.context import outing_context
        from nukkad.places import Place
        from nukkad.planning import QuestInput

        context = outing_context(
            store, QuestInput(minutes=30), [], [Place.model_validate(snapshot["places"][0])]
        )
        assert context["reported_visits"] == [source]
        assert context["notes"][0]["text"] == value["note"]
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
        generated = client.post(
            f"/api/collection/{source}/generate", json={"experience_id": key, "mode": "manual"}
        )
        assert wait(client, generated.json())["status"] == "complete"
        card = client.get(f"/api/collection/{source}").json()["current_card"]
        assert client.get(f"/api/location-cards/{card['id']}/export.png").status_code == 200
        assert client.get("/api/collection").json()["card_count"] == 1
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
    assert len(Store(restored).list("location_card_version")) == 1
    assert Store(restored).get("snapshot", snapshot["id"]) == snapshot


def test_alias_visits_stay_in_one_folder_and_note_edits_invalidate_dependents(registry):
    maps, store, snapshot, _, _ = registry
    source = snapshot["places"][0]["id"]
    store.put(
        "place_alias",
        "historical-source",
        {"id": "historical-source", "canonical_id": source, "record_version": 1},
    )
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        endpoint = "/api/places/historical-source/experiences/" + "c" * 32
        visit = client.put(endpoint, json={"note": "A personally reported visit."}).json()
        assert visit["place_id"] == source
        store.put("journal", visit["id"], {"id": visit["id"], "status": "accepted"})
        store.put(
            "interest",
            "proposal",
            {"id": "proposal", "source_note_id": visit["id"], "status": "accepted"},
        )
        store.put(
            "location_card_version",
            "card",
            {"id": "card", "experience_id": visit["id"], "stale": False},
        )
        changed = client.put(
            endpoint,
            json={"note": "A revised personal observation.", "source_revision": visit["revision"]},
        )
        assert changed.status_code == 200
        assert changed.json()["original_note"] == "A personally reported visit."
        assert store.get("journal", visit["id"])["status"] == "invalidated"
        assert store.get("interest", "proposal")["status"] == "invalidated"
        assert store.get("location_card_version", "card")["stale"]
        assert (
            client.put(
                "/api/places/" + source + "/experiences/" + "d" * 32,
                json={"note": "Another visit."},
            ).status_code
            == 200
        )
        collection = client.get("/api/collection").json()
        assert len(collection["folders"]) == 1 and collection["folders"][0]["visits"] == 2
        assert collection["card_count"] == 0


def test_saved_visit_preparation_is_revision_bound_and_idempotent(registry, monkeypatch):
    from nukkad.journals import JournalNarrative
    from nukkad.location_cards import CardSummary, CoverChoice

    maps, store, snapshot, _, _ = registry
    source, key = snapshot["places"][0]["id"], "e" * 32
    calls = []

    def response(self, response_type, *args, **kwargs):
        calls.append(response_type)
        if response_type is CoverChoice:
            return CoverChoice(
                photo_id=store.list("photo")[0]["id"], reason="A clear supplied view."
            ), {}
        if response_type is CardSummary:
            return CardSummary(summary="They enjoyed the green shapes.", evidence_ids=["note"]), {}
        return JournalNarrative(text="They enjoyed the green shapes."), {}

    monkeypatch.setattr("nukkad.ollama.Ollama.generate", response)
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        visit = client.put(
            f"/api/places/{source}/experiences/{key}", json={"note": "I enjoyed the green shapes."}
        ).json()
        output = io.BytesIO()
        Image.new("RGB", (48, 48), "green").save(output, "PNG")
        photo = client.post(
            f"/api/experiences/{key}/photos",
            files={"photo": ("sample.png", output.getvalue(), "image/png")},
        ).json()
        assert "experience_revision" in photo
        request = {"source_revision": photo["experience_revision"]}
        job = client.post(f"/api/experiences/{key}/prepare", json=request)
        assert job.status_code == 202, job.text
        assert wait(client, job.json())["status"] == "complete"
        again = client.post(f"/api/experiences/{key}/prepare", json=request).json()
        assert again["id"] == job.json()["id"]
        assert len(calls) == 2 and len(store.list("location_card_version")) == 1
        assert not store.list("quest")
        folder = client.get(f"/api/collection/{source}").json()
        assert folder["visits"][0]["generation"]["status"] == "complete"
        assert folder["visits"][0]["journal"]["mode"] == "local AI journal"
        assert (
            client.post(
                f"/api/experiences/{key}/prepare", json={"source_revision": visit["revision"]}
            ).status_code
            == 409
        )


def test_note_only_preparation_is_visible_and_explicit_retry_preserves_sources(
    registry, monkeypatch
):
    from nukkad.journals import JournalNarrative
    from nukkad.ollama import ModelFailure

    store = registry[1]
    source = registry[2]["places"][0]["id"]
    key = "f" * 32

    def missing(*args, **kwargs):
        raise ModelFailure("Unavailable", "missing_model")

    monkeypatch.setattr("nukkad.ollama.Ollama.generate", missing)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        visit = client.put(
            f"/api/places/{source}/experiences/{key}", json={"note": "I enjoyed tree shapes."}
        ).json()
        request = {"source_revision": visit["revision"]}
        first = client.post(f"/api/experiences/{key}/prepare", json=request).json()
        state = wait(client, first)
        assert state["result"]["journal_mode"] == "extractive fallback"
        assert (
            client.post(f"/api/experiences/{key}/prepare", json=request).json()["id"] == first["id"]
        )
        monkeypatch.setattr(
            "nukkad.ollama.Ollama.generate",
            lambda *a, **k: (JournalNarrative(text="They enjoyed tree shapes."), {}),
        )
        second = client.post(
            f"/api/experiences/{key}/prepare", json={**request, "retry": True}
        ).json()
        assert second["id"] != first["id"]
        assert wait(client, second)["result"]["journal_mode"] == "local AI journal"
        assert store.get("experience", key) == visit
        assert len(store.list("journal_version")) == 2
        assert not store.list("quest") and not store.list("location_card_version")


def test_automatic_visit_keeps_the_written_story_when_vision_fails(registry, monkeypatch):
    from nukkad.journals import JournalNarrative
    from nukkad.ollama import ModelFailure

    source = registry[2]["places"][0]["id"]
    key = "9" * 32

    def response(self, response_type, *args, **kwargs):
        if response_type is JournalNarrative:
            return JournalNarrative(text="They enjoyed tree shapes."), {}
        raise ModelFailure("Vision unavailable", "unsupported_capability")

    monkeypatch.setattr("nukkad.ollama.Ollama.generate", response)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        client.put(
            f"/api/places/{source}/experiences/{key}", json={"note": "I enjoyed tree shapes."}
        )
        output = io.BytesIO()
        Image.new("RGB", (40, 40), "green").save(output, "PNG")
        photo = client.post(
            f"/api/experiences/{key}/photos",
            files={"photo": ("synthetic.png", output.getvalue(), "image/png")},
        ).json()
        job = client.post(
            f"/api/experiences/{key}/prepare",
            json={"source_revision": photo["experience_revision"]},
        ).json()
        state = wait(client, job)
        assert state["status"] == "complete"
        assert state["result"]["card_error"] == "unsupported_capability"
        assert state["result"]["journal_mode"] == "local AI journal"
        assert registry[1].get("journal", key)["text"] == "They enjoyed tree shapes."
        assert registry[1].list("photo") and not registry[1].list("location_card_version")


def test_saved_direct_visit_remains_editable_when_the_current_map_changes(registry):
    source = registry[2]["places"][0]["id"]
    key = "8" * 32
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        path = f"/api/places/{source}/experiences/{key}"
        visit = client.put(path, json={"note": "I noticed green outlines."}).json()
        registry[1].put("area", "active", {})
        changed = client.put(
            path,
            json={"note": "I enjoyed these green outlines.", "source_revision": visit["revision"]},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["original_note"] == visit["note"]
        assert changed.json()["snapshot_id"] == visit["snapshot_id"]
