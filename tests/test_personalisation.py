import pytest

from nukkad.context import outing_context
from nukkad.grounding import validate_evidence
from nukkad.planning import QuestInput
from nukkad.quests import validate_prose


def test_relevant_old_note_is_retained_before_recent_unrelated_notes(registry):
    maps, store = registry[:2]
    store.put(
        "outcome",
        "old",
        {"id": "old", "note": "I enjoyed tree outlines", "reached_ids": ["osm-way-20"]},
    )
    for index in range(6):
        store.put(
            "outcome",
            str(index),
            {"id": str(index), "note": "An unrelated observation", "reached_ids": ["elsewhere"]},
        )
    context = outing_context(store, QuestInput(), [], maps.places())
    assert context["notes"][0]["id"] == "old"
    assert len(context["notes"]) <= 4
    assert context["reported_visits"] == ["osm-way-20"]


def test_natural_general_invitation_is_not_rejected_by_a_word_list():
    validate_prose("Try tracing repeating outlines in the scene.")
    with pytest.raises(ValueError):
        validate_prose("Look for a kingfisher.")


def test_unknown_and_duplicate_evidence_ids_are_rejected():
    for ids in (["unknown"], ["request", "request"], []):
        with pytest.raises(ValueError):
            validate_evidence(ids, {"request": "A short walk"})
