from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field

from nukkad.domain import Record, validate_ids
from nukkad.quests_api import quest_by_id
from nukkad.storage import now

router = APIRouter(prefix="/api")


class StopOutcome(Record):
    id: str
    status: Literal["reached", "skipped", "unresolved"]


class Outcome(Record):
    status: Literal["completed", "turned_back", "not_taken"]
    stops: list[StopOutcome] = Field(max_length=3)
    note: str = Field(default="", max_length=8000)
    reason: str = Field(default="", max_length=500)
    actual_minutes: int | None = Field(default=None, ge=0, le=1440)
    screen_minutes: float | None = Field(default=None, ge=0, le=1440)


def save_outcome(store, quest, value: Outcome):
    if quest["status"] != "accepted":
        raise ValueError("Accept a quest before recording its outcome")
    validate_ids([stop.id for stop in value.stops], [stop["id"] for stop in quest["stops"]])
    reached = [stop.id for stop in value.stops if stop.status == "reached"]
    if value.status == "not_taken" and reached:
        raise ValueError("A not-taken outing cannot report reached stops")
    previous = store.get("outcome", quest["id"])
    revisions = previous.get("revisions", []) if previous else []
    if previous:
        revisions = [*revisions, {"note": previous["note"], "saved_at": previous["updated_at"]}]
    result = {
        **value.model_dump(),
        "id": quest["id"],
        "quest_id": quest["id"],
        "snapshot_id": quest["snapshot_id"],
        "reached_ids": reached,
        "original_note": previous["original_note"] if previous else value.note,
        "created_at": previous["created_at"] if previous else now(),
        "updated_at": now(),
        "revisions": revisions,
        "reporting": "self-reported",
    }
    records = [("outcome", result["id"], result)]
    # Any note edit invalidates derived work; reviewed interpretations must be reviewed again.
    if previous and previous["note"] != value.note:
        for item in store.list("interest"):
            if item.get("source_note_id") == result["id"]:
                records.append(("interest", item["id"], {**item, "status": "invalidated"}))
        journal = store.get("journal", result["id"])
        if journal:
            records.append(("journal", result["id"], {**journal, "status": "invalidated"}))
    store.atomic(records)
    return result


@router.put("/quests/{key}/outcome")
def record_outcome(key: str, value: Outcome, request: Request):
    return save_outcome(request.app.state.store, quest_by_id(key, request), value)


@router.get("/quests/{key}/outcome")
def get_outcome(key: str, request: Request):
    quest_by_id(key, request)
    return request.app.state.store.get("outcome", key)


@router.get("/outcomes")
def all_outcomes(request: Request):
    return request.app.state.store.list("outcome")
