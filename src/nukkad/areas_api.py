import json
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from nukkad.domain import Record
from nukkad.identities import canonical_id, duplicate_candidates, identity_records
from nukkad.jobs import Result
from nukkad.maps import MAX_EXTRACT_BYTES, Maps, distance
from nukkad.places import AreaInput, Correction, CustomPlace, Place, prohibited
from nukkad.snapping import snap_point
from nukkad.storage import identity, now

router = APIRouter(prefix="/api")


def maps(request: Request) -> Maps:
    return Maps(request.app.state.config, request.app.state.store)


def start_acquisition(request: Request, area: AreaInput, source: Path | None = None):
    def action(stage):
        try:
            stage("Downloading and processing neighbourhood map")
            snapshot = maps(request).acquire(area, source, activate=False, progress=stage)
            stage("Saving immutable snapshot")
            records = [
                ("snapshot", snapshot["id"], snapshot),
                ("area", "active", {**area.model_dump(), "snapshot_id": snapshot["id"]}),
                *identity_records(
                    request.app.state.store,
                    [Place.model_validate(place) for place in snapshot["places"]],
                ),
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


def map_revision(request, *, duplicates=False):
    store = request.app.state.store
    kinds = ["area", "snapshot", "place", "place_alias", "outcome", "experience"]
    if duplicates:
        kinds.append("place_duplicate")
    area = store.get("area", "active")
    path = (
        request.app.state.config.data_dir
        / "snapshots"
        / (area["snapshot_id"] if area else "missing")
        / "walking.graphml"
    )
    stat = path.stat() if path.is_file() else None
    stamp = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size) if stat else None
    return store.revision_key(kinds), stamp


@router.get("/area/status")
def area_status(request: Request):
    area = request.app.state.store.get("area", "active")
    return {
        "area": {key: value for key, value in area.items() if key != "snapshot_id"}
        if area
        else None,
        "snapshot_id": area["snapshot_id"] if area else None,
    }


@router.get("/area")
def active_area(request: Request):
    return request.app.state.store.cache.get(
        "area", map_revision(request), lambda: build_active_area(request)
    )


def build_active_area(request: Request):
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
    aliases = request.app.state.store.keyed("place_alias")
    visited = {place.id for place in places if place.visited}
    return {
        "area": snapshot["area"],
        "snapshot_id": snapshot["id"],
        "acquired_at": snapshot["acquired_at"],
        "source": snapshot["source"],
        "geometry": snapshot["geometry"],
        "places": [place.model_dump() for place in places],
        "progress": {
            "mapped_visited": sum(
                canonical_id(request.app.state.store, key, aliases) in visited for key in eligible
            ),
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
            "source": value.get("source", "Saved OpenStreetMap extract"),
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
    from nukkad.suggestions import within_area

    active = request.app.state.store.get("area", "active")
    if not within_area(value.entrance.model_dump(), active):
        raise ValueError("Choose an entrance inside your saved neighbourhood")
    graph = pedestrian_graph(registry.graph())
    node, snap = snap_point(graph, value.entrance)
    point = {"lat": graph.nodes[node]["y"], "lon": graph.nodes[node]["x"]}
    if not within_area(point, active):
        raise ValueError("The eligible walking entrance is outside your saved neighbourhood")
    place = Place(
        id=f"user-{identity()}",
        name=value.name,
        kind=value.kind,
        point=value.entrance,
        entrance=point,
        entrance_node=node,
        snap=snap,
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
        raise ValueError("Choose a corrected entrance on the map")
    data = place.model_dump()
    data["last_report"] = value.action
    if value.action in {"not_there", "closed", "not_accessible"}:
        data["valid"] = False
    else:
        if prohibited(place.tags):
            raise ValueError("A verification cannot override explicit prohibited access tags")
        data.update(verification="verified", access="confirmed", valid=True, verified_at=now())
        if value.entrance:
            from nukkad.planning import pedestrian_graph

            graph = pedestrian_graph(registry.graph())
            node, snap = snap_point(graph, value.entrance)
            data.update(
                entrance_node=node,
                snap=snap,
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
        snapshot = registry.acquire(
            area, source, activate=False, synthetic=old.get("synthetic", False)
        )
        return Result(
            {"snapshot_id": snapshot["id"]},
            [
                ("snapshot", snapshot["id"], snapshot),
                ("area", "active", {**area.model_dump(), "snapshot_id": snapshot["id"]}),
                *identity_records(
                    request.app.state.store,
                    [Place.model_validate(place) for place in snapshot["places"]],
                ),
            ],
        )

    return request.app.state.jobs.submit("Update public starting point", action)


@router.get("/snapshots/{key}/map")
def snapshot_map(key: str, request: Request):
    snapshot = request.app.state.store.get("snapshot", key)
    if snapshot is None:
        raise HTTPException(404, "Unknown map snapshot")
    return {"snapshot_id": key, "area": snapshot["area"], "geometry": snapshot["geometry"]}


class DuplicateReview(Record):
    decision: Literal["merge", "separate"]
    target_id: str | None = None


@router.get("/places/duplicates")
def duplicates(request: Request):
    registry = maps(request)
    return request.app.state.store.cache.get(
        "duplicates",
        map_revision(request, duplicates=True),
        lambda: duplicate_candidates(request.app.state.store, registry.places(), distance),
    )


@router.patch("/places/duplicates/{key}")
def review_duplicate(key: str, value: DuplicateReview, request: Request):
    store = request.app.state.store
    pair = next((item for item in duplicates(request) if item["id"] == key), None)
    if pair is None:
        raise HTTPException(404, "Unknown or already resolved duplicate")
    records = [("place_duplicate", key, {**pair, **value.model_dump(), "reviewed_at": now()})]
    if value.decision == "merge":
        if value.target_id not in pair["place_ids"]:
            raise ValueError("Choose one of these places as the retained identity")
        for source in pair["place_ids"]:
            records.append(
                (
                    "place_alias",
                    source,
                    {"id": source, "canonical_id": value.target_id, "record_version": 1},
                )
            )
        sources = set(pair["place_ids"])
        for root in pair["place_ids"]:
            sources.update((store.get("place_identity", root) or {}).get("source_ids", []))
        records.append(
            (
                "place_identity",
                value.target_id,
                {
                    "id": value.target_id,
                    "record_version": 1,
                    "source_ids": sorted(sources),
                    "created_at": now(),
                },
            )
        )
    store.atomic(records)
    return records[0][2]
