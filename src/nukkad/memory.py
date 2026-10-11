import time
from dataclasses import replace
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from nukkad.domain import Record
from nukkad.jobs import Result
from nukkad.journals import generate_journal, validate_preferences
from nukkad.ollama import Ollama
from nukkad.planning_api import settings
from nukkad.storage import identity, now

router = APIRouter(prefix="/api")


class Proposal(Record):
    theme: str = Field(min_length=2, max_length=100)
    quote: str = Field(min_length=5, max_length=500)


class Reflection(Record):
    excerpt: str = Field(min_length=1, max_length=1000)
    interests: list[Proposal] = Field(default_factory=list, max_length=3)


class Review(Record):
    status: Literal["accepted", "rejected", "removed"]
    text: str | None = Field(default=None, max_length=2000)


def validate_reflection(value: Reflection, note: str):
    if not value.excerpt.strip() or value.excerpt not in note:
        raise ValueError("Journal excerpt must be copied exactly from the original note")
    validate_preferences(value.interests, note)


@router.post("/outcomes/{key}/reflect")
def reflect(key: str, request: Request):
    store = request.app.state.store
    outcome = store.get("outcome", key)
    if not outcome:
        raise HTTPException(404, "Unknown outcome")
    if not outcome["note"].strip():
        raise ValueError("Add your own return note before generating a reflection")

    previous = store.get("journal", key)

    def action(stage):
        stage("Writing a grounded journal and tentative interests locally")
        model = Ollama(replace(request.app.state.config, model=settings(request).model))
        generated = generate_journal(outcome, model, time.monotonic() + 120)
        journal = {
            "id": key,
            "source_note_id": key,
            "source_note": outcome["note"],
            "text": generated["text"],
            "passages": generated["passages"],
            "record_version": 2,
            "version_id": identity(),
            "source_revision": outcome.get("updated_at"),
            "status": "pending",
            "mode": generated["mode"],
            "metrics": generated["metrics"],
            "created_at": now(),
        }
        records = [("journal", key, journal), ("journal_version", journal["version_id"], journal)]
        if previous:
            previous_id = previous.get("version_id") or identity()
            records.append(
                ("journal_version", previous_id, {**previous, "version_id": previous_id})
            )
        # Replace pending proposals from earlier generations, without erasing reviewed history.
        for old in store.list("interest"):
            if old.get("source_note_id") == key and old.get("status") == "pending":
                records.append(("interest", old["id"], {**old, "status": "superseded"}))
        existing = {
            (item["theme"], item["quote"])
            for item in store.list("interest")
            if item.get("source_note_id") == key and item.get("status") == "accepted"
        }
        for proposal in generated["interests"]:
            if (proposal.theme, proposal.quote) in existing:
                continue
            item = {
                **proposal.model_dump(),
                "id": identity(),
                "source_note_id": key,
                "source_note": outcome["note"],
                "status": "pending",
                "created_at": now(),
            }
            records.append(("interest", item["id"], item))
        stage("Saving reviewable drafts")
        return Result(
            {"outcome_id": key}, records, [("outcome", key, outcome), ("journal", key, previous)]
        )

    return request.app.state.jobs.submit("Reflect on return note", action)


@router.get("/interests")
def interests(request: Request):
    return request.app.state.store.list("interest")


@router.patch("/interests/{key}")
def review_interest(key: str, value: Review, request: Request):
    store = request.app.state.store
    item = store.get("interest", key)
    if not item:
        raise HTTPException(404, "Unknown interest")
    outcome = store.get("outcome", item["source_note_id"])
    if value.status == "accepted" and (
        not outcome
        or outcome["note"] != item["source_note"]
        or item["quote"] not in outcome["note"]
    ):
        raise ValueError("Source note changed; generate and review a fresh proposal")
    if value.text is not None and not 2 <= len(value.text.strip()) <= 100:
        raise ValueError("Interest theme must contain 2–100 characters")
    updated = store.atomic_review(
        "interest",
        key,
        {
            **item,
            "status": value.status,
            "theme": value.text.strip() if value.text is not None else item["theme"],
            "reviewed_at": now(),
        },
        source=("outcome", item["source_note_id"], outcome),
        previous=item,
    )
    return updated


@router.get("/outcomes/{key}/journal")
def journal(key: str, request: Request):
    return request.app.state.store.get("journal", key)


@router.patch("/outcomes/{key}/journal")
def review_journal(key: str, value: Review, request: Request):
    store = request.app.state.store
    item = store.get("journal", key)
    if not item:
        raise HTTPException(404, "Unknown draft")
    outcome = store.get("outcome", key)
    if value.status == "accepted" and (not outcome or outcome["note"] != item["source_note"]):
        raise ValueError("Source note changed; regenerate this draft")
    updated = {
        **item,
        "status": value.status,
        "text": value.text if value.text is not None else item["text"],
        "reviewed_at": now(),
        "version_id": identity(),
    }
    previous_id = item.get("version_id") or identity()
    store.atomic(
        [
            ("journal", key, updated),
            ("journal_version", previous_id, {**item, "version_id": previous_id}),
            ("journal_version", updated["version_id"], updated),
        ],
        [("outcome", key, outcome), ("journal", key, item)],
    )
    return updated


@router.get("/outcomes/{key}/journal/versions")
def journal_versions(key: str, request: Request):
    return [
        item
        for item in request.app.state.store.list("journal_version")
        if item["source_note_id"] == key
    ]
