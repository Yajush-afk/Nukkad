from fastapi import APIRouter, HTTPException, Request

from nukkad.areas_api import maps
from nukkad.jobs import Result
from nukkad.planning import QuestInput
from nukkad.planning_api import settings
from nukkad.quests import accept, generate

router = APIRouter(prefix="/api/quests")


@router.post("")
def create_quest(value: QuestInput, request: Request):
    def action(stage):
        quest = generate(
            maps(request),
            request.app.state.store,
            request.app.state.config,
            settings(request),
            value,
            stage,
        )
        return Result({"quest_id": quest["id"]}, [("quest", quest["id"], quest)])

    return request.app.state.jobs.submit("Create walking quest", action)


@router.get("")
def history(request: Request):
    return request.app.state.store.list("quest")


def quest_by_id(key: str, request: Request):
    quest = request.app.state.store.get("quest", key)
    if not quest:
        raise HTTPException(404, "Unknown quest")
    return quest


@router.get("/{key}")
def get_quest(key: str, request: Request):
    return quest_by_id(key, request)


@router.post("/{key}/accept")
def accept_quest(key: str, request: Request):
    quest = accept(quest_by_id(key, request), maps(request), settings(request))
    return request.app.state.store.put("quest", key, quest)
