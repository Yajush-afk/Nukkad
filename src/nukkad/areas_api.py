import json
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from nukkad.jobs import Result
from nukkad.maps import MAX_EXTRACT_BYTES, Maps, nearest_node
from nukkad.places import AreaInput, Correction, CustomPlace, Place, prohibited
from nukkad.storage import identity, now

router = APIRouter(prefix="/api")


def maps(request: Request) -> Maps:
    return Maps(request.app.state.config, request.app.state.store)


def start_acquisition(request: Request, area: AreaInput, source: Path | None = None):
    def action(stage):
        try:
            stage("Downloading and processing neighbourhood map")
            snapshot = maps(request).acquire(area, source, activate=False)
            stage("Saving immutable snapshot")
            records = [
                ("snapshot", snapshot["id"], snapshot),
                ("area", "active", {**area.model_dump(), "snapshot_id": snapshot["id"]}),
            ]
            return Result({"snapshot_id": snapshot["id"]}, records)
        finally:
            if source:
                source.unlink(missing_ok=True)

    return request.app.state.jobs.submit("Neighbourhood setup", action)


@router.post("/areas", status_code=202)
def acquire(area: AreaInput, request: Request):
    return start_acquisition(request, area)


@router.post("/areas/import", status_code=202)
async def import_area(
    request: Request, metadata: Annotated[str, Form()], extract: Annotated[UploadFile, File()]
):
    parsed = AreaInput.model_validate(json.loads(metadata))
    with tempfile.NamedTemporaryFile(
        suffix=".osm", dir=request.app.state.config.data_dir, delete=False
    ) as output:
        path = Path(output.name)
        size = 0
        try:
            while chunk := await extract.read(65536):
                size += len(chunk)
                if size > MAX_EXTRACT_BYTES:
                    raise ValueError("Map extract exceeds the 32 MiB neighbourhood limit")
                output.write(chunk)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    try:
        return start_acquisition(request, parsed, path)
    except Exception:
        path.unlink(missing_ok=True)
        raise


@router.get("/area")
def active_area(request: Request):
    registry = maps(request)
    try:
        snapshot = registry.snapshot()
    except ValueError:
        return {
            "area": None,
            "places": [],
            "geometry": {"type": "FeatureCollection", "features": []},
        }
    places = registry.places(snapshot)
    eligible = set(snapshot["eligible_mapped_ids"])
    return {
        "area": snapshot["area"],
        "snapshot_id": snapshot["id"],
        "acquired_at": snapshot["acquired_at"],
        "source": snapshot["source"],
        "geometry": snapshot["geometry"],
        "places": [place.model_dump() for place in places],
        "progress": {
            "mapped_visited": sum(place.visited and place.id in eligible for place in places),
            "mapped_total": len(eligible),
            "custom_visited": sum(place.visited and place.source == "user" for place in places),
        },
    }


@router.get("/snapshots")
def snapshots(request: Request):
    return [
        {
            "id": value["id"],
            "area": value["area"],
            "acquired_at": value["acquired_at"],
            "mapped_total": len(value["eligible_mapped_ids"]),
        }
        for value in request.app.state.store.list("snapshot")
    ]


@router.post("/places", status_code=201)
def add_place(value: CustomPlace, request: Request):
    if not value.public_access_confirmed:
        raise ValueError("Confirm that the destination has a public entrance")
    registry = maps(request)
    from nukkad.planning import pedestrian_graph

    graph = pedestrian_graph(registry.graph())
    node = nearest_node(graph, value.entrance)
    point = {"lat": graph.nodes[node]["y"], "lon": graph.nodes[node]["x"]}
    place = Place(
        id=f"user-{identity()}",
        name=value.name,
        kind=value.kind,
        point=value.entrance,
        entrance=point,
        entrance_node=node,
        descriptors=value.descriptors,
        source="user",
        access="confirmed",
    )
    return request.app.state.store.put("place", place.id, place.model_dump())


@router.patch("/places/{key}")
def correct_place(key: str, value: Correction, request: Request):
    registry = maps(request)
    place = next((place for place in registry.places() if place.id == key), None)
    if place is None:
        raise HTTPException(404, "Unknown place")
    if value.action == "entrance" and value.entrance is None:
        raise ValueError("An entrance correction requires entrance coordinates")
    data = place.model_dump()
    if value.action in {"not_there", "closed", "not_accessible"}:
        data["valid"] = False
    else:
        if prohibited(place.tags):
            raise ValueError("A verification cannot override explicit prohibited access tags")
        data.update(verification="verified", access="confirmed", valid=True, verified_at=now())
        if value.entrance:
            from nukkad.planning import pedestrian_graph

            graph = pedestrian_graph(registry.graph())
            node = nearest_node(graph, value.entrance)
            data.update(
                entrance_node=node,
                entrance={"lat": graph.nodes[node]["y"], "lon": graph.nodes[node]["x"]},
            )
    data["correction"] = value.detail
    event = {
        "id": identity(),
        "place_id": key,
        "action": value.action,
        "detail": value.detail,
        "created_at": now(),
    }
    request.app.state.store.atomic([("place", key, data), ("correction", event["id"], event)])
    return data


@router.get("/jobs/{key}")
def job_status(key: str, request: Request):
    value = request.app.state.store.get("job", key)
    if value is None:
        raise HTTPException(404, "Unknown task")
    return value


@router.post("/jobs/{key}/cancel")
def cancel_job(key: str, request: Request):
    return request.app.state.jobs.cancel(key)


@router.post("/areas/reuse")
def reuse_extract(area: AreaInput, request: Request):
    registry = maps(request)
    old = registry.snapshot()
    source = request.app.state.config.data_dir / "snapshots" / old["id"] / "source.osm"

    def action(stage):
        stage("Processing saved extract with the selected public start")
        snapshot = registry.acquire(area, source, activate=False)
        return Result(
            {"snapshot_id": snapshot["id"]},
            [
                ("snapshot", snapshot["id"], snapshot),
                ("area", "active", {**area.model_dump(), "snapshot_id": snapshot["id"]}),
            ],
        )

    return request.app.state.jobs.submit("Update public starting point", action)
