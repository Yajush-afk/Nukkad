import pytest

from nukkad.outcomes import Outcome, save_outcome


def test_upsert_preserves_exact_original_notes_and_progress(registry):
    maps, store, snapshot, _, _ = registry
    quest = {
        "id": "outing",
        "status": "accepted",
        "snapshot_id": snapshot["id"],
        "stops": [{"id": "osm-way-20"}],
    }
    note = "  Looked at a tree.\nKept punctuation!  "
    value = Outcome(
        status="completed", note=note, stops=[{"id": "osm-way-20", "status": "reached"}]
    )
    save_outcome(store, quest, value)
    save_outcome(store, quest, value)
    assert len(store.list("outcome")) == 1
    assert store.get("outcome", "outing")["note"] == note
    assert maps.places()[0].visited
    value.stops[0].status = "skipped"
    value.note = "Edited observation"
    changed = save_outcome(store, quest, value)
    assert changed["original_note"] == note
    assert not maps.places()[0].visited


def test_unknown_outcome_stops_rejected(registry):
    quest = {
        "id": "outing",
        "status": "accepted",
        "snapshot_id": "fixture",
        "stops": [{"id": "known"}],
    }
    with pytest.raises(ValueError, match="IDs"):
        save_outcome(
            registry[1],
            quest,
            Outcome(status="completed", stops=[{"id": "invented", "status": "reached"}]),
        )
