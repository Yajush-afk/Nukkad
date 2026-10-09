import pytest

from nukkad.memory import Reflection, validate_reflection
from nukkad.outcomes import Outcome, save_outcome
from nukkad.quests import active_interests


def test_quotes_and_preference_evidence_are_required():
    note = "I enjoyed noticing tree shapes. Passed a shrine."
    validate_reflection(
        Reflection(
            excerpt="Passed a shrine.",
            interests=[{"theme": "trees", "quote": "I enjoyed noticing tree shapes."}],
        ),
        note,
    )
    for quote in ["I loved birds.", "Passed a shrine."]:
        with pytest.raises(ValueError):
            validate_reflection(
                Reflection(
                    excerpt="Passed a shrine.", interests=[{"theme": "shrines", "quote": quote}]
                ),
                note,
            )
    with pytest.raises(ValueError):
        validate_reflection(Reflection(excerpt="I had a wonderful walk."), note)


def test_empty_journal_extract_is_rejected():
    for value in ({}, {"excerpt": ""}):
        with pytest.raises(ValueError):
            Reflection.model_validate(value)
    with pytest.raises(ValueError):
        validate_reflection(Reflection(excerpt="   "), "   I enjoyed trees.")


def test_only_reviewed_memory_is_active_and_note_edits_invalidate(registry):
    _, store, snapshot, _, _ = registry
    quest = {
        "id": "outing",
        "status": "accepted",
        "snapshot_id": snapshot["id"],
        "stops": [{"id": "osm-way-20"}],
    }
    value = Outcome(
        status="completed",
        note="I enjoyed trees",
        stops=[{"id": "osm-way-20", "status": "reached"}],
    )
    save_outcome(store, quest, value)
    for status in ["pending", "rejected", "accepted"]:
        store.put(
            "interest",
            status,
            {"id": status, "theme": status, "status": status, "source_note_id": "outing"},
        )
    assert active_interests(store) == ["accepted"]
    value.note = "An edited note"
    save_outcome(store, quest, value)
    assert active_interests(store) == []


def test_optimistic_publication_rejects_changed_notes(registry):
    store = registry[1]
    store.put("outcome", "note", {"note": "new"})
    with pytest.raises(ValueError, match="changed"):
        store.atomic(
            [("interest", "late", {"status": "pending"})], [("outcome", "note", {"note": "old"})]
        )
    assert store.get("interest", "late") is None
