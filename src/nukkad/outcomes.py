from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field

from nukkad.domain import Record, validate_ids
from nukkad.experiences import ExperienceInput, experience_records, outcome_experiences
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
    place_experiences: list[ExperienceInput] | None = Field(default=None, max_length=3)
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
    old_experiences = outcome_experiences(store, quest["id"])
    experiences = experience_records(
        store,
        quest,
        {
            "reached_ids": reached,
            "status": value.status,
            "created_at": previous["created_at"] if previous else now(),
        },
        value.place_experiences,
        old_experiences,
    )
    if (
        previous
        and not experiences
        and all(previous.get(key) == item for key, item in value.model_dump().items())
    ):
        return previous
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
    records = [("outcome", result["id"], result), *experiences]
    # Any note edit invalidates derived work; reviewed interpretations must be reviewed again.
    if previous and previous["note"] != value.note:
        for item in store.list("interest"):
            if item.get("source_note_id") == result["id"]:
                records.append(("interest", item["id"], {**item, "status": "invalidated"}))
    if previous and any(
        previous.get(key) != result.get(key) for key in ("note", "status", "stops")
    ):
        journal = store.get("journal", result["id"])
        if journal:
            records.append(("journal", result["id"], {**journal, "status": "invalidated"}))
    expected = [("outcome", quest["id"], previous)]
    expected.extend(
        ("experience", key, next((item for item in old_experiences if item["id"] == key), None))
        for kind, key, _ in experiences
        if kind == "experience"
    )
    store.atomic(records, expected)
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


@router.get("/outcomes/{key}/experiences")
def get_experiences(key: str, request: Request):
    return outcome_experiences(request.app.state.store, key)
