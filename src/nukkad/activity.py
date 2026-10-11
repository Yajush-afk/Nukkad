"""Read-only Dashboard activity: planned routes and self-reported place visits."""

import json
from collections import Counter

from fastapi import APIRouter, Request

from nukkad.identities import canonical_id

router = APIRouter(prefix="/api")


@router.get("/activity")
def activity(request: Request):
    store = request.app.state.store
    # One SQLite read keeps aliases, outcomes and photo counts mutually consistent.
    with store.connect() as connection:
        rows = connection.execute(
            "SELECT kind,id,data FROM records WHERE kind IN "
            "('quest','outcome','experience','photo','place_alias')"
        ).fetchall()
    records = {}
    for kind, key, data in rows:
        records.setdefault(kind, {})[key] = json.loads(data)
    outcomes = {value["quest_id"]: value for value in records.get("outcome", {}).values()}
    photos = Counter(
        value["experience_id"]
        for value in records.get("photo", {}).values()
        if value.get("active", True)
    )
    entries = [
        {
            "id": "walk:" + quest["id"],
            "kind": "planned_walk",
            "recorded_at": quest["created_at"],
            "quest": quest,
            "outcome": outcomes.get(quest["id"]),
        }
        for quest in records.get("quest", {}).values()
    ]
    planned_walks = len(entries)
    for visit in records.get("experience", {}).values():
        if not (
            visit.get("source_kind") == "place"
            and visit.get("outcome_id") is None
            and visit.get("active", False)
        ):
            continue
        entries.append(
            {
                "id": "visit:" + visit["id"],
                "kind": "place_visit",
                "recorded_at": visit["visit_date"],
                "experience_id": visit["id"],
                "place_id": canonical_id(store, visit["place_id"], records.get("place_alias", {})),
                "place_name": visit["place_name"],
                "timezone": visit.get("timezone", "UTC"),
                "note": visit["note"],
                "photo_count": photos[visit["id"]],
            }
        )
    entries.sort(key=lambda entry: (entry["recorded_at"], entry["id"]), reverse=True)
    return {
        "entries": entries,
        "planned_walk_count": planned_walks,
        "place_visit_count": len(entries) - planned_walks,
    }
