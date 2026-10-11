"""Reported place visits retain stable identity independently of map snapshots."""

import hashlib
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import Field

from nukkad.domain import Record
from nukkad.identities import canonical_id
from nukkad.storage import SourceChanged, identity, now

router = APIRouter(prefix="/api")


class PlaceVisit(Record):
    note: str = Field(min_length=3, max_length=8000)
    visit_date: date | None = None
    source_revision: str | None = None


@router.put("/places/{source}/experiences/{key}")
def record_place_visit(
    source: str,
    value: PlaceVisit,
    request: Request,
    key: str = Path(pattern=r"^[a-f0-9]{32}$"),
):
    """A map selection is not a quest, an access check or proof of attendance."""
    from nukkad.areas_api import maps

    store = request.app.state.store
    root = canonical_id(store, source)
    previous = store.get("experience", key)
    if previous:
        if (
            previous.get("source_kind") != "place"
            or canonical_id(store, previous["place_id"]) != root
        ):
            raise SourceChanged("This visit belongs to a different place")
        snapshot = store.get("snapshot", previous["snapshot_id"])
        if not snapshot:
            raise HTTPException(404, "This saved visit's map is missing; restore its backup")
        place_name, stop_id = previous["place_name"], previous["stop_id"]
    else:
        registry = maps(request)
        snapshot = registry.snapshot()
        place = next((item for item in registry.places(snapshot) if item.id == root), None)
        if place is None:
            raise HTTPException(404, "Choose a place on your saved map")
        place_name, stop_id = place.name, place.id
    note = value.note.strip()
    if len(note) < 3:
        raise ValueError("Write a short experience before saving")
    timezone = (
        previous.get("timezone", snapshot["area"]["timezone"])
        if previous
        else snapshot["area"]["timezone"]
    )
    today = datetime.now(ZoneInfo(timezone)).date()
    day = value.visit_date or (
        datetime.fromisoformat(previous["visit_date"]).astimezone(ZoneInfo(timezone)).date()
        if previous
        else today
    )
    if day > today:
        raise ValueError("Choose today or an earlier visit date")
    visited_at = (
        datetime.combine(day, datetime.min.time().replace(hour=12), ZoneInfo(timezone))
        .astimezone(UTC)
        .isoformat()
    )
    if previous:
        if (
            previous.get("source_kind") != "place"
            or canonical_id(store, previous["place_id"]) != root
        ):
            raise SourceChanged("This visit belongs to a different place")
        if previous["note"] == note and previous["visit_date"] == visited_at:
            return previous
        if value.source_revision != previous["revision"]:
            raise SourceChanged("This experience changed. Reopen it before saving")
    item = {
        "id": key,
        "record_version": 1,
        "source_kind": "place",
        "outcome_id": None,
        "snapshot_id": snapshot["id"],
        "stop_id": stop_id,
        "place_id": root,
        "place_name": place_name,
        "provenance": "self-reported visit from saved map",
        "note": note,
        "original_note": previous["original_note"] if previous else note,
        "active": True,
        "status": "completed",
        "revision": identity(),
        "visit_date": visited_at,
        "timezone": timezone,
        "created_at": previous["created_at"] if previous else now(),
        "updated_at": now(),
        "revisions": [
            *previous.get("revisions", []),
            {
                "note": previous["note"],
                "revision": previous["revision"],
                "visit_date": previous["visit_date"],
            },
        ]
        if previous
        else [],
    }
    records = [("experience", key, item)]
    if previous:
        from nukkad.photos import invalidation_records

        records.extend(invalidation_records(store, key))
        records.extend(
            ("interest", proposal["id"], {**proposal, "status": "invalidated"})
            for proposal in store.list("interest")
            if proposal.get("source_note_id") == key
            and proposal.get("status") not in {"removed", "rejected"}
        )
        journal = store.get("journal", key)
        if journal:
            records.append(("journal", key, {**journal, "status": "invalidated"}))
    store.atomic(
        records,
        [
            ("experience", key, previous),
            *(
                []
                if previous
                else [("area", "active", {**snapshot["area"], "snapshot_id": snapshot["id"]})]
            ),
        ],
    )
    return item


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
