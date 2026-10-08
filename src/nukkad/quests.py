import re
import time
from dataclasses import replace
from datetime import datetime

from nukkad.domain import Observations, Ranking, validate_ids
from nukkad.ollama import ModelFailure, Ollama, bounded_schema, observation_prompt, ranking_prompt
from nukkad.planning import Planner, QuestInput, Settings, baseline
from nukkad.storage import identity, now

TEMPLATES = {
    "sound": "Pause and listen. What sounds stand out around you?",
    "shape": "Notice the shapes visible from your public stopping point.",
    "colour": "Look around. Which colours catch your attention?",
    "activity": "Notice public activity around you without photographing people.",
    "detail": "Find a small visible detail you would usually overlook.",
    "compare": "If you have been here before, what seems different today?",
}
# Restrict prose to observation language. Facts are rendered separately from registry data.
PROSE_WORDS = set(
    "pause and listen what sounds stand out around you notice the shapes visible from your public stopping point look which colours colors catch attention activity without photographing people find a small detail would usually overlook if have been here before seems different today take moment to compare surroundings textures patterns light shadow changes near at this stop explore observe how feel sound color shape rhythm contrast movement choose one describe it quietly focus on something new familiar with or that is in nearby scene environment spend time be curious about try spotting seeing hearing looking listening an interesting subtle gently simply for can do as then also there first together enjoy reflecting eyes close up distant soft loud repeating natural urban overall its between more less same usual now along a few surface lines use think of any details place perspective remember than last visit noticed earlier stay outside visible side do not enter restricted areas".split()
)


def validate_prose(text: str):
    words = set(re.findall(r"[a-z]+", text.lower()))
    if re.search(r"\d", text) or not words <= PROSE_WORDS:
        raise ValueError("Use only general observation vocabulary; do not invent features or facts")
    if not text.lower().startswith(
        (
            "notice",
            "look",
            "listen",
            "pause",
            "find",
            "take",
            "if",
            "compare",
            "observe",
            "try",
            "focus",
            "choose",
            "what",
            "which",
        )
    ):
        raise ValueError("Write an observation invitation")


def validate_reasons(value: Ranking, candidates):
    facts = " ".join(
        str(item) for place in candidates for item in [place.name, place.kind, *place.descriptors]
    )
    allowed = set(re.findall(r"[a-z]+", facts.lower())) | set(
        "a an the and or for of to with your interests interest matches fit variety novelty new unvisited visited revisit nearby closest closer overlooked different familiar nature trees quiet art architecture markets food sports history short walk mapped entrance destination public outside observation stop explore worth considering previously reached reported balance offers adds supports this place kind route candidate distance less more than preference preferences return useful purposeful change context notes note aligns local location park garden landmark artwork attraction tree market court sports centre walking time budget".split()
    )
    for item in value.places:
        if (
            len(item.reason.split()) > 12
            or re.search(r"\d", item.reason)
            or not set(re.findall(r"[a-z]+", item.reason.lower())) <= allowed
        ):
            raise ValueError(
                "Reasons must use supplied place facts and ranking language, without numbers"
            )


def validated_task(model, response_type, collection, ids, prompt, deadline, validator):
    error = ""
    for _ in range(2):
        try:
            value, metrics = model.generate(
                response_type,
                prompt + error,
                deadline,
                bounded_schema(response_type, collection, ids),
            )
            validate_ids([item.id for item in getattr(value, collection)], ids)
            validator(value)
            return value, metrics
        except (ModelFailure, ValueError) as failure:
            error = "\nPrevious response was rejected: " + str(failure) + ". Correct it."
    raise ModelFailure("Local model output failed validation after one corrective retry")


def context(store, request: QuestInput, interests):
    outcomes = store.list("outcome")[:4]
    notes = [
        {"id": item["id"], "text": item.get("note", "")[:600]}
        for item in outcomes
        if item.get("note")
    ]
    return {
        "minutes": request.minutes,
        "state": request.state,
        "mode": request.mode,
        "interests": interests,
        "notes": notes,
        "reported_visits": [key for item in outcomes for key in item.get("reached_ids", [])],
    }


def active_interests(store):
    explicit = (store.get("profile", "active") or {}).get("interests", [])
    accepted = [
        item["theme"] for item in store.list("interest") if item.get("status") == "accepted"
    ]
    return list(dict.fromkeys([*explicit, *accepted]))[:20]


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
    data = context(store, request, interests)
    data["tone"] = settings.tone
    ranked = baseline(candidates, interests)
    ranking_mode, prose_mode = "local AI", "local AI"
    metrics, reasons = {}, {}
    stage("Ranking eligible places with local AI")
    try:
        value, metrics["ranking"] = validated_task(
            model,
            Ranking,
            "places",
            [place.id for place in candidates],
            ranking_prompt([place.model_dump() for place in candidates], data),
            deadline,
            lambda value: validate_reasons(value, candidates),
        )
        ranked = [item.id for item in value.places]
        reasons = {item.id: item.reason for item in value.places}
    except ModelFailure:
        ranking_mode = "deterministic fallback"
    stage("Checking full walking route and daylight")
    quest = planner.build(candidates, ranked, request)
    ids = [place["id"] for place in quest["stops"]]
    stage("Writing observation prompts for the fixed route")
    try:

        def validate(value):
            for item in value.stops:
                validate_prose(item.text)
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
            observation_prompt(quest["stops"], data)
            + "\nUse general observation words only, without named objects.",
            deadline,
            validate,
        )
        prompts = {item.id: item.model_dump() for item in value.stops}
    except ModelFailure:
        prose_mode = "template fallback"
        prompts = {
            key: {"id": key, "activity": "detail", "text": TEMPLATES["detail"]} for key in ids
        }
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
        for place in planner.candidates(QuestInput.model_validate(quest["input"]), [])
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
    if datetime.fromisoformat(quest["generated_at"]).date() != planner.clock().date():
        raise ValueError("Saved cards are dated; generate a fresh quest today")
    if current["legs"] != quest["legs"] or current["settings"] != quest["settings"]:
        raise ValueError("Route settings changed; generate a fresh quest")
    return {**quest, "status": "accepted", "accepted_at": now()}
