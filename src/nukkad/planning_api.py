from fastapi import APIRouter, Request
from pydantic import Field

from nukkad.areas_api import maps
from nukkad.domain import Record
from nukkad.planning import Planner, QuestInput, Settings, baseline

router = APIRouter(prefix="/api")


class Profile(Record):
    interests: list[str] = Field(default_factory=list, max_length=12)


def settings(request: Request) -> Settings:
    return Settings.model_validate(request.app.state.store.get("settings", "active") or {})


@router.get("/settings")
def get_settings(request: Request):
    return settings(request)


@router.put("/settings")
def save_settings(value: Settings, request: Request):
    if value.air_quality_enabled and value.air_quality_threshold is None:
        raise ValueError("Choose an air-quality threshold before enabling this policy")
    return request.app.state.store.put("settings", "active", value.model_dump())


@router.get("/profile")
def get_profile(request: Request):
    return request.app.state.store.get("profile", "active") or {"interests": []}


@router.put("/profile")
def save_profile(value: Profile, request: Request):
    interests = list(dict.fromkeys(item.strip() for item in value.interests if item.strip()))
    if any(len(item) > 100 for item in interests):
        raise ValueError("Each interest must be at most 100 characters")
    return request.app.state.store.put("profile", "active", {"interests": interests})


@router.post("/quests/route-preview")
def route_preview(value: QuestInput, request: Request):
    from nukkad.air_quality import enforce

    enforce(request.app.state.store, maps(request).snapshot(), settings(request))
    planner = Planner(maps(request), settings(request))
    interests = get_profile(request)["interests"]
    candidates = planner.candidates(value, interests)
    quest = planner.build(candidates, baseline(candidates, interests), value)
    return {**quest, "ranking_mode": "deterministic", "prose_mode": "none"}
