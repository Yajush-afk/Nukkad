import json
import time
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from nukkad.context import active_interests, candidate_facts, evidence_catalog, outing_context
from nukkad.domain import Observations, Ranking, validate_ids
from nukkad.grounding import validate_evidence, validate_invitation, validate_rationale
from nukkad.ollama import ModelFailure, Ollama, bounded_schema, observation_prompt, ranking_prompt
from nukkad.places import Place, seek_features
from nukkad.planning import Planner, QuestInput, Settings, baseline
from nukkad.storage import identity, now
from nukkad.tasks import run_task

TEMPLATES = {
    "sound": "Pause and listen. What sounds stand out around you?",
    "shape": "Notice the shapes visible from your public stopping point.",
    "colour": "Look around. Which colours catch your attention?",
    "activity": "Notice public activity around you without photographing people.",
    "detail": "Find a small visible detail you would usually overlook.",
    "compare": "If you have been here before, what seems different today?",
}


def validate_prose(text: str, evidence=""):
    validate_invitation(text, evidence)


def reason_options(candidates, interests):
    from nukkad.planning import INTEREST_KINDS

    tokens = {word.lower() for interest in interests for word in interest.split()}
    options = {}
    for place in candidates:
        choices = [
            "Nearby destination with a mapped entrance.",
            "Previously reached; consider a purposeful revisit."
            if place.visited
            else "Unvisited mapped destination.",
        ]
        choices += [
            f"Interest match: {theme}."
            for theme, kinds in INTEREST_KINDS.items()
            if theme in tokens and place.kind in kinds
        ]
        options[place.id] = choices
    return options


def validate_reasons(value: Ranking, candidates, interests=(), catalogue=None):
    options = reason_options(candidates, interests)
    for item in value.places:
        if not item.evidence_ids and item.reason in options[item.id]:
            continue  # Previously supported controlled responses remain readable.
        evidence = validate_evidence(item.evidence_ids, catalogue or {})
        if any(key.startswith("place:") and key != f"place:{item.id}" for key in item.evidence_ids):
            raise ValueError("Explain this candidate using its own place evidence")
        validate_rationale(item.reason, evidence)


def validated_task(model, response_type, collection, ids, prompt, deadline, validator, schema=None):
    def check(value):
        validate_ids([item.id for item in getattr(value, collection)], ids)
        validator(value)

    return run_task(
        model,
        response_type,
        prompt,
        deadline,
        check,
        schema or bounded_schema(response_type, collection, ids),
        task=collection,
        version=2,
    )


def context(store, request: QuestInput, interests, candidates=()):
    return outing_context(store, request, interests, candidates)


def generate(
    maps, store, config, settings: Settings, request: QuestInput, stage, model=None, planner=None
):
    began = time.monotonic()
    deadline = began + 120
    from nukkad.air_quality import enforce

    environment = enforce(store, maps.snapshot(), settings)
    planner = planner or Planner(maps, settings)
    interests = active_interests(store)
    candidates = planner.candidates(request, interests)
    if not candidates:
        planner.build([], [], request)
    if model is None:
        model = Ollama(replace(config, model=settings.model))
    data = context(store, request, interests, candidates)
    catalogue = evidence_catalog(data, candidates)
    data["evidence_catalog"] = catalogue
    data["tone"] = settings.tone
    ranked = baseline(candidates, interests)
    ranking_mode, prose_mode = "local AI", "local AI"
    metrics, reasons, reasoning_evidence = {}, {}, {}
    stage("Ranking eligible places with local AI")
    rank_schema = bounded_schema(Ranking, "places", [place.id for place in candidates])
    rank_schema["$defs"]["RankedPlace"]["properties"]["evidence_ids"].update(
        minItems=1, items={"type": "string", "enum": list(catalogue)}
    )
    rank_schema["$defs"]["RankedPlace"]["required"].append("evidence_ids")
    rank_schema["$defs"]["RankedPlace"]["properties"]["reason"].update(
        maxLength=90, pattern="^(Suggestion:|Idea:) "
    )
    try:
        value, metrics["ranking"] = validated_task(
            model,
            Ranking,
            "places",
            [place.id for place in candidates],
            ranking_prompt(
                [
                    candidate_facts(place)
                    for place in sorted(candidates, key=lambda place: place.id)
                ],
                data,
            ),
            deadline,
            lambda value: validate_reasons(value, candidates, interests, catalogue),
            schema=rank_schema,
        )
        ranked = [item.id for item in value.places]
        reasons = {item.id: item.reason for item in value.places}
        reasoning_evidence = {item.id: item.evidence_ids for item in value.places}
    except ModelFailure as error:
        metrics["ranking"] = {**error.diagnostics, "mode": "deterministic fallback"}
        ranking_mode = "deterministic fallback"
    stage("Checking full walking route and daylight")
    quest = planner.build(candidates, ranked, request)
    ids = [place["id"] for place in quest["stops"]]
    features = (
        {place["id"]: seek_features(place) for place in quest["stops"]}
        if request.mode == "seek"
        else {}
    )
    prose_schema = bounded_schema(Observations, "stops", ids)
    prose_schema["$defs"]["Observation"]["properties"]["feature_id"] = {
        "type": ["string", "null"],
        "enum": [None, *[key for options in features.values() for key in options]],
    }
    prose_schema["$defs"]["Observation"]["properties"]["evidence_ids"].update(
        minItems=1, items={"type": "string", "enum": list(catalogue)}
    )
    prose_schema["$defs"]["Observation"]["required"].append("evidence_ids")
    prose_schema["$defs"]["Observation"]["properties"]["text"].update(maxLength=85)
    stage("Writing observation prompts for the fixed route")
    try:

        def validate(value):
            for item in value.stops:
                evidence = (
                    validate_evidence(item.evidence_ids, catalogue) if item.evidence_ids else ""
                )
                if any(
                    key.startswith("place:") and key != f"place:{item.id}"
                    for key in item.evidence_ids
                ):
                    raise ValueError("Use this stop's own place evidence")
                for key in item.evidence_ids:
                    if key.startswith("note:"):
                        note = next(note for note in data["notes"] if key == f"note:{note['id']}")
                        if note["place_ids"] and item.id not in note["place_ids"]:
                            raise ValueError(
                                "Do not attach another place's reported experience to this stop"
                            )
                validate_prose(item.text, evidence)
                if request.mode == "seek" and item.feature_id not in features[item.id]:
                    raise ValueError("Choose a recorded feature ID belonging to this stop")
                if request.mode == "wander" and item.feature_id is not None:
                    raise ValueError("Wander prompts do not select recorded features")
                if (
                    item.activity == "compare"
                    and not next(place for place in quest["stops"] if place["id"] == item.id)[
                        "visited"
                    ]
                ):
                    raise ValueError("Comparison requires a reported previous visit")

        value, metrics["prose"] = validated_task(
            model,
            Observations,
            "stops",
            ids,
            observation_prompt(
                [candidate_facts(Place.model_validate(place)) for place in quest["stops"]], data
            )
            + (
                "\nFor seek mode select one feature_id for each stop from these recorded options: "
                + json.dumps(features)
                if features
                else "\nSet feature_id to null."
            ),
            deadline,
            validate,
            schema=prose_schema,
        )
        prompts = {item.id: item.model_dump() for item in value.stops}
    except ModelFailure as error:
        metrics["prose"] = {**error.diagnostics, "mode": "template fallback"}
        prose_mode = "template fallback"
        prompts = {
            key: {"id": key, "activity": "detail", "text": TEMPLATES["detail"]} for key in ids
        }
    if request.mode == "seek":
        for key, prompt in prompts.items():
            feature_id = prompt.get("feature_id") or next(iter(features[key]))
            prompt["evidence"] = {"id": feature_id, **features[key][feature_id]}
    stage("Saving quest preview")
    return {
        **quest,
        "environment": environment,
        "id": identity(),
        "status": "draft",
        "ranking_mode": ranking_mode,
        "prose_mode": prose_mode,
        "prompts": prompts,
        "reasons": reasons,
        "reasoning_evidence": reasoning_evidence,
        "model": settings.model,
        "metrics": metrics,
        "generation_seconds": round(time.monotonic() - began, 2),
        "context_note_ids": [note["id"] for note in data["notes"]],
        "created_at": now(),
    }


def accept(quest, maps, settings):
    from nukkad.air_quality import enforce

    enforce(maps.store, maps.snapshot(), settings)
    if quest["snapshot_id"] != maps.snapshot()["id"]:
        raise ValueError("The neighbourhood map changed; generate a fresh quest")
    planner = Planner(maps, settings)
    available = {
        place.id: place
        for place in planner.candidates(
            QuestInput.model_validate(quest["input"]), [], shortlist=False
        )
    }
    ids = [place["id"] for place in quest["stops"]]
    if not set(ids) <= set(available):
        raise ValueError("A stop is no longer eligible; generate a fresh quest")
    # Fixed destinations must remain feasible; recheck current settings, paths and departure.
    current = planner.build(
        [available[key] for key in ids], ids, QuestInput.model_validate(quest["input"])
    )
    if {place["id"] for place in current["stops"]} != set(ids):
        raise ValueError("The complete quest no longer fits; generate a fresh quest")
    zone = ZoneInfo(quest["timezone"])
    if (
        datetime.fromisoformat(quest["generated_at"]).astimezone(zone).date()
        != planner.clock().astimezone(zone).date()
    ):
        raise ValueError("Saved cards are dated; generate a fresh quest today")
    if current["legs"] != quest["legs"] or current["settings"] != quest["settings"]:
        raise ValueError("Route settings changed; generate a fresh quest")
    return {**quest, "status": "accepted", "accepted_at": now()}
