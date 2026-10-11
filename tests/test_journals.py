import time

import pytest
from fastapi.testclient import TestClient

from nukkad.app import create_app
from nukkad.journals import JournalNarrative, WrittenJournal, generate_journal, validate_written
from nukkad.ollama import ModelFailure


def draft(text="They enjoyed tree shapes.", quote="I enjoyed tree shapes."):
    return WrittenJournal(passages=[{"text": text, "quote": quote}])


def test_written_journal_requires_third_person_and_source_evidence():
    source = {"note": "I enjoyed tree shapes.", "status": "completed"}
    validate_written(draft(), source)
    for text, quote in (
        ("I enjoyed tree shapes.", source["note"]),
        ("They felt calm.", source["note"]),
        ("They counted 50 trees.", source["note"]),
        ("They enjoyed it.", "A made-up quote"),
    ):
        with pytest.raises(ValueError):
            validate_written(draft(text, quote), source)
    with pytest.raises(ValueError):
        validate_written(
            draft("They enjoyed trees.", "I did not enjoy trees."),
            {"note": "I did not enjoy trees."},
        )


def test_failed_journal_preserves_truthful_extract():
    class Missing:
        def generate(self, *args):
            raise ModelFailure("Unavailable")

    result = generate_journal(
        {"note": "I never left home.", "status": "not_taken"}, Missing(), time.monotonic() + 1
    )
    assert result["text"] == "I never left home."
    assert result["mode"] == "extractive fallback" and result["interests"] == []


def test_journal_versions_and_interest_review_are_separate(registry, monkeypatch):
    maps, store = registry[:2]
    source = {
        "id": "visit",
        "note": "I enjoyed tree shapes.",
        "original_note": "I enjoyed tree shapes.",
        "status": "completed",
        "updated_at": "revision-1",
    }
    store.put("outcome", "visit", source)

    def response(*args):
        return JournalNarrative(
            text="They enjoyed tree shapes.",
            interests=[{"theme": "trees", "quote": source["note"]}],
        ), {}

    monkeypatch.setattr("nukkad.ollama.Ollama.generate", response)
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        for _ in range(2):
            job = client.post("/api/outcomes/visit/reflect").json()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                state = client.get("/api/jobs/" + job["id"]).json()
                if state["status"] == "complete":
                    break
                assert state["status"] != "failed", state
                time.sleep(0.01)
            assert state["status"] == "complete"
            edited = client.patch(
                "/api/outcomes/visit/journal",
                json={"status": "accepted", "text": "Their edited account."},
            )
            assert edited.status_code == 200
        versions = client.get("/api/outcomes/visit/journal/versions").json()
        assert any(item["text"] == "Their edited account." for item in versions)
        assert all(item["status"] != "accepted" for item in client.get("/api/interests").json())
    assert store.get("outcome", "visit") == source


def test_journal_generation_cannot_overwrite_review_during_inference(registry, monkeypatch):
    import threading

    store = registry[1]
    source = {"id": "visit", "note": "I enjoyed tree shapes.", "status": "completed"}
    store.put("outcome", "visit", source)
    old = {
        "id": "visit",
        "text": "Earlier draft",
        "source_note": source["note"],
        "status": "pending",
    }
    store.put("journal", "visit", old)
    entered, release = threading.Event(), threading.Event()

    def response(*args):
        entered.set()
        assert release.wait(3)
        return JournalNarrative(text="They enjoyed tree shapes."), {}

    monkeypatch.setattr("nukkad.ollama.Ollama.generate", response)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        job = client.post("/api/outcomes/visit/reflect").json()
        assert entered.wait(2)
        try:
            assert (
                client.patch(
                    "/api/outcomes/visit/journal",
                    json={"status": "accepted", "text": "Their edited account."},
                ).status_code
                == 200
            )
        finally:
            release.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = client.get("/api/jobs/" + job["id"]).json()
            if state["status"] == "failed":
                break
            time.sleep(0.01)
        assert state["status"] == "failed"
        assert store.get("journal", "visit")["text"] == "Their edited account."


def test_journal_does_not_drop_negative_or_uncertain_source_passages():
    source = {
        "note": "I turned back before the market. I did not enjoy the noise. Maybe I will revisit.",
        "status": "turned_back",
    }
    with pytest.raises(ValueError, match="every negative"):
        validate_written(
            draft("They turned back before the market.", "I turned back before the market."), source
        )


def test_journal_review_rejects_client_edit_for_an_earlier_version(registry):
    store = registry[1]
    source = {"id": "visit", "note": "I noticed tree outlines.", "status": "completed"}
    store.put("outcome", "visit", source)
    journal = {
        "id": "visit",
        "version_id": "new-version",
        "source_note": source["note"],
        "text": "They noticed tree outlines.",
        "status": "pending",
    }
    store.put("journal", "visit", journal)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        result = client.patch(
            "/api/outcomes/visit/journal",
            json={
                "status": "accepted",
                "text": "Their older client edit.",
                "version_id": "old-version",
            },
        )
        assert result.status_code == 409
        assert store.get("journal", "visit") == journal


def test_positive_discovery_can_be_written_without_becoming_negative():
    note = "Loved the place. I never knew I had a place like that nearby."
    source = {"note": note, "status": "completed"}
    validate_written(draft("They loved this previously unknown nearby place.", note), source)


def test_evidence_allows_grounded_paraphrase_and_sentence_initial_pronouns():
    source = {
        "note": "I found some guys working out. Some ladies were doing yoga.",
        "status": "completed",
    }
    validate_written(
        draft("They discovered people working out. They saw ladies doing yoga.", source["note"]),
        source,
    )


def test_invalid_interest_does_not_discard_a_valid_written_journal():
    class Response:
        def generate(self, *args):
            return JournalNarrative(
                text="They noticed people working out.",
                interests=[{"theme": "workouts", "quote": "I saw people working out."}],
            ), {}

    result = generate_journal(
        {"note": "I saw people working out.", "status": "completed"},
        Response(),
        time.monotonic() + 1,
    )
    assert result["mode"] == "local AI journal"
    assert result["text"] == "They noticed people working out."
    assert result["interests"] == []
    assert result["metrics"]["interest_validation"]["rejected"] == 1


def test_journal_prose_rejects_editorial_placeholders():
    with pytest.raises(ValueError, match="placeholders"):
        validate_written(
            draft(
                "They had a preference for [no explicit preference mentioned].",
                "I enjoyed tree shapes.",
            ),
            {"note": "I enjoyed tree shapes."},
        )


def test_short_note_uses_broad_evidence_and_bounded_narrative_schema():
    note = "I enjoyed tree shapes."

    class Response:
        def generate(self, response_type, prompt, deadline, schema):
            assert "text" in schema["properties"]
            assert schema["properties"]["interests"]["maxItems"] == 0
            return JournalNarrative(text="They enjoyed tree shapes."), {}

    result = generate_journal(
        {"note": note}, Response(), time.monotonic() + 1, propose_interests=False
    )
    assert result["mode"] == "local AI journal"


def test_visit_story_retains_reported_appreciation_and_person():
    source = {"note": "I loved this place and saw people doing yoga."}
    with pytest.raises(ValueError, match="positive experience"):
        validate_written(draft("They saw people doing yoga.", source["note"]), source)
    with pytest.raises(ValueError, match="generic scene"):
        validate_written(draft("People were doing yoga in the place.", source["note"]), source)


def test_corrective_retry_repairs_the_rejected_narrative_instead_of_blind_regeneration():
    class Response:
        def __init__(self):
            self.calls = 0

        def generate(self, response_type, prompt, deadline, schema):
            self.calls += 1
            if self.calls == 1:
                return JournalNarrative(text="They noticed tree shapes."), {}
            assert "Previous structured response to repair" in prompt
            assert "They noticed tree shapes." in prompt
            assert "Retain the reported positive experience" in prompt
            return JournalNarrative(text="They enjoyed noticing tree shapes."), {}

    model = Response()
    result = generate_journal(
        {"note": "I enjoyed noticing tree shapes."}, model, time.monotonic() + 1
    )
    assert result["mode"] == "local AI journal" and model.calls == 2


def test_failed_generation_keeps_the_current_reviewed_story():
    from nukkad.journals import versioned_journal

    source = {"id": "visit", "note": "I enjoyed tree shapes.", "revision": "r1"}
    previous = {
        "id": "visit",
        "version_id": "edited",
        "source_note": source["note"],
        "mode": "local AI journal",
        "status": "accepted",
        "text": "They kept their own carefully edited account.",
    }
    generated = {
        "mode": "extractive fallback",
        "text": source["note"],
        "passages": [],
        "metrics": {},
    }
    _, records = versioned_journal(source, generated, previous)
    assert not any(kind == "journal" for kind, _, _ in records)
    assert any(value["text"] == previous["text"] for _, _, value in records)
    source["note"] = "I did not enjoy tree shapes."
    _, changed = versioned_journal(source, generated, previous)
    assert any(kind == "journal" for kind, _, _ in changed)
