"""Reported place visits retain stable identity independently of map snapshots."""

import hashlib

from pydantic import Field

from nukkad.domain import Record
from nukkad.identities import canonical_id
from nukkad.storage import identity, now


class ExperienceInput(Record):
    stop_id: str
    note: str = Field(default="", max_length=8000)


def experience_records(store, quest, outcome, inputs, existing_items=None):
    supplied = {item.stop_id: item.note for item in inputs or []}
    allowed = {stop["id"]: stop for stop in quest["stops"]}
    if len(supplied) != len(inputs or []) or not supplied.keys() <= allowed.keys():
        raise ValueError("Place experience IDs must be distinct stops on this accepted walk")
    existing = {
        item["stop_id"]: item
        for item in (existing_items if existing_items is not None else store.list("experience"))
        if item["outcome_id"] == quest["id"]
    }
    records = []
    for stop_id in supplied.keys() | existing.keys() | set(outcome["reached_ids"]):
        old = existing.get(stop_id)
        note = supplied.get(stop_id, old["note"] if old else "")
        active = stop_id in outcome["reached_ids"]
        if (
            old
            and old["note"] == note
            and old["active"] == active
            and old.get("status") == outcome["status"]
        ):
            continue
        key = (
            old["id"]
            if old
            else hashlib.sha256(f"{quest['id']}:{stop_id}".encode()).hexdigest()[:32]
        )
        item = {
            "id": key,
            "record_version": 1,
            "outcome_id": quest["id"],
            "stop_id": stop_id,
            "place_id": canonical_id(store, stop_id),
            "place_name": allowed[stop_id].get("name", stop_id),
            "provenance": "self-reported stop on accepted walk",
            "note": note,
            "original_note": old["original_note"] if old else note,
            "active": active,
            "status": outcome["status"],
            "revision": identity(),
            "visit_date": old["visit_date"] if old else outcome["created_at"],
            "timezone": old.get("timezone", quest.get("timezone", "UTC"))
            if old
            else quest.get("timezone", "UTC"),
            "created_at": old["created_at"] if old else now(),
            "updated_at": now(),
            "revisions": [
                *old.get("revisions", []),
                {"note": old["note"], "active": old["active"], "revision": old["revision"]},
            ]
            if old
            else [],
        }
        records.append(("experience", key, item))
        records.extend(
            ("interest", item["id"], {**item, "status": "invalidated"})
            for item in store.list("interest")
            if item.get("source_note_id") == key
            and item.get("status") not in {"removed", "rejected"}
        )
        journal = store.get("journal", key)
        if journal:
            records.append(("journal", key, {**journal, "status": "invalidated"}))
        for card in store.list("location_card_version"):
            if card["experience_id"] == key and not card.get("stale"):
                records.append(("location_card_version", card["id"], {**card, "stale": True}))
    return records


def outcome_experiences(store, key):
    return [item for item in store.list("experience") if item["outcome_id"] == key]
