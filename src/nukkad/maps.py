import hashlib
import math
import shutil
from pathlib import Path

import httpx
import networkx as nx
import osmnx as ox
from defusedxml import ElementTree

from nukkad.config import Config
from nukkad.domain import Point
from nukkad.places import AreaInput, Place, place_kind, prohibited
from nukkad.storage import Store, identity, now

MAX_EXTRACT_BYTES = 32 * 1024 * 1024
OVERPASS_PROVIDERS = (
    ("Overpass (main)", "https://overpass-api.de/api/interpreter"),
    ("Overpass (Private.coffee)", "https://overpass.private.coffee/api/interpreter"),
)


def neighbourhood_query(area: AreaInput) -> str:
    radius = area.radius_meters + 700
    delta_lat = radius / 111320
    delta_lon = radius / (111320 * max(0.2, math.cos(math.radians(area.start.lat))))
    bbox = (
        f"{area.start.lat - delta_lat},{area.start.lon - delta_lon},"
        f"{area.start.lat + delta_lat},{area.start.lon + delta_lon}"
    )
    # Download the routing network and supported destinations, not every
    # building and unrelated node. Access filtering still happens in code.
    selectors = [f'way["highway"]({bbox});', f'node["entrance"]({bbox});']
    filters = (
        '["leisure"~"^(park|garden|pitch|sports_centre)$"]',
        '["amenity"~"^(marketplace|place_of_worship|food_court)$"]',
        '["tourism"~"^(artwork|attraction)$"]',
        '["historic"~"^(monument|memorial)$"]',
        '["natural"="tree"]["name"]',
        '["shop"]["name"]',
    )
    selectors.extend(
        f"{kind}{condition}({bbox});" for condition in filters for kind in ("node", "way")
    )
    # Recurse to keep referenced way vertices and their access/entrance tags.
    return "[out:xml][timeout:25];(" + "".join(selectors) + ");(._;>;);out meta;"


def distance(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    delta_lat, delta_lon = lat2 - lat1, math.radians(b.lon - a.lon)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 6371000 * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0, 1 - value)))


def nearest_node(graph: nx.MultiDiGraph, point: Point, max_distance: float = 50) -> int:
    if not graph.nodes:
        raise ValueError("No mapped walking network is available")
    node = min(
        graph.nodes,
        key=lambda item: distance(
            point, Point(lat=graph.nodes[item]["y"], lon=graph.nodes[item]["x"])
        ),
    )
    actual = Point(lat=graph.nodes[node]["y"], lon=graph.nodes[node]["x"])
    if distance(point, actual) > max_distance:
        raise ValueError("Select an entrance on or within 50 metres of a mapped walking street")
    return node


def tags(element) -> dict[str, str]:
    return {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}


def parse_extract(path: Path, area: AreaInput) -> tuple[nx.MultiDiGraph, list[Place], dict]:
    if path.stat().st_size > MAX_EXTRACT_BYTES:
        raise ValueError("Map extract exceeds the 32 MiB neighbourhood limit")
    root = ElementTree.parse(path).getroot()
    if root.tag != "osm":
        raise ValueError("Expected an OpenStreetMap XML extract")
    original_tags = ox.settings.useful_tags_way
    original_node_tags = ox.settings.useful_tags_node
    ox.settings.useful_tags_way = list(
        set(
            original_tags
            + [
                "access",
                "foot",
                "access:conditional",
                "foot:conditional",
                "surface",
                "construction",
                "oneway:foot",
            ]
        )
    )
    ox.settings.useful_tags_node = list(
        set(
            original_node_tags
            + ["access", "foot", "access:conditional", "foot:conditional", "entrance", "barrier"]
        )
    )
    try:
        graph = ox.graph_from_xml(path, simplify=False, retain_all=True, bidirectional=True)
    finally:
        ox.settings.useful_tags_way = original_tags
        ox.settings.useful_tags_node = original_node_tags
    graph.graph["nukkad_synthetic"] = root.attrib.get("nukkad_synthetic") == "true"
    graph.remove_edges_from(
        [
            (u, v, key)
            for u, v, key, data in graph.edges(keys=True, data=True)
            if not data.get("highway")
        ]
    )
    graph.remove_nodes_from(list(nx.isolates(graph)))
    if not graph.nodes:
        raise ValueError("The extract contains no street network")
    nodes = {int(element.attrib["id"]): element for element in root.findall("node")}
    points = {
        key: Point(lat=float(element.attrib["lat"]), lon=float(element.attrib["lon"]))
        for key, element in nodes.items()
    }
    places = []
    backgrounds = []
    elements = list(root.findall("node")) + list(root.findall("way"))
    for element in elements:
        raw_tags = tags(element)
        kind = place_kind(raw_tags)
        node_ids = [int(ref.attrib["ref"]) for ref in element.findall("nd")]
        coordinates = [points[key] for key in node_ids if key in points]
        is_node = element.tag == "node"
        if is_node:
            point = points[int(element.attrib["id"])]
        elif coordinates:
            point = Point(
                lat=sum(item.lat for item in coordinates) / len(coordinates),
                lon=sum(item.lon for item in coordinates) / len(coordinates),
            )
        else:
            continue
        if coordinates and (
            raw_tags.get("building") or raw_tags.get("leisure") in {"park", "garden"}
        ):
            if coordinates[0] == coordinates[-1] and len(coordinates) >= 4:
                backgrounds.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "kind": "park" if raw_tags.get("leisure") else "building",
                            "name": raw_tags.get("name", ""),
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[p.lon, p.lat] for p in coordinates]],
                        },
                    }
                )
        if not kind or distance(area.start, point) > area.radius_meters:
            continue
        entrance_node = None
        if is_node and int(element.attrib["id"]) in graph:
            entrance_node = int(element.attrib["id"])
        elif not is_node:
            entrance_node = next(
                (
                    key
                    for key in node_ids
                    if key in graph
                    and (
                        tags(nodes[key]).get("entrance")
                        or tags(nodes[key]).get("barrier") == "gate"
                    )
                    and not prohibited(tags(nodes[key]))
                ),
                None,
            )
        elif kind in {"market", "artwork", "landmark", "tree", "attraction"}:
            try:
                entrance_node = nearest_node(graph, point, max_distance=30)
            except ValueError:
                pass
        entrance = (
            Point(lat=graph.nodes[entrance_node]["y"], lon=graph.nodes[entrance_node]["x"])
            if entrance_node is not None
            else None
        )
        descriptors = [
            f"{key}: {raw_tags[key]}"
            for key in ("artwork_type", "sport", "species", "denomination", "description")
            if raw_tags.get(key)
        ]
        if is_node and entrance and distance(point, entrance) > 1:
            descriptors.append(
                "Observe from the mapped street frontage; interior access is unknown"
            )
        places.append(
            Place(
                id=f"osm-{element.tag}-{element.attrib['id']}",
                name=raw_tags.get("name", f"Unnamed {kind}"),
                kind=kind,
                point=point,
                entrance=entrance,
                entrance_node=entrance_node,
                tags=raw_tags,
                descriptors=[value[:180] for value in descriptors[:8]],
                access="prohibited"
                if prohibited(raw_tags)
                else (
                    "mapped"
                    if raw_tags.get("access") in {"yes", "permissive", "public"}
                    else "unknown"
                ),
                valid=not prohibited(raw_tags),
            )
        )
    for u, v, data in graph.edges(data=True):
        if u > v and graph.has_edge(v, u):
            continue
        backgrounds.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "street",
                    "name": data.get("name", ""),
                    "access": data.get("access", "unknown"),
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [graph.nodes[u]["x"], graph.nodes[u]["y"]],
                        [graph.nodes[v]["x"], graph.nodes[v]["y"]],
                    ],
                },
            }
        )
    return graph, places, {"type": "FeatureCollection", "features": backgrounds}


class Maps:
    def __init__(self, config: Config, store: Store):
        self.config, self.store = config, store

    def acquire(
        self,
        area: AreaInput,
        imported: Path | None = None,
        activate: bool = True,
        synthetic: bool = False,
    ) -> dict:
        snapshot_id = identity()
        staging = self.config.data_dir / "snapshots" / f".{snapshot_id}"
        staging.mkdir()
        raw_path = staging / "source.osm"
        try:
            if imported:
                if imported.stat().st_size > MAX_EXTRACT_BYTES:
                    raise ValueError("Map extract exceeds the 32 MiB neighbourhood limit")
                shutil.copyfile(imported, raw_path)
                source = "user-imported OpenStreetMap XML"
            else:
                source = self.download(area, raw_path)
            graph, places, geometry = parse_extract(raw_path, area)
            synthetic = synthetic or graph.graph.get("nukkad_synthetic", False)
            if synthetic:
                source = "Synthetic fixture XML; not real-world OpenStreetMap data"
            from nukkad.planning import pedestrian_graph

            walking = pedestrian_graph(graph)
            try:
                start_node = nearest_node(walking, area.start)
            except ValueError:
                if area.public_start_confirmed:
                    raise
                # A geocoded building/locality centre is enough to download a map,
                # but is never silently promoted to a confirmed walking entrance.
                start_node = None
            connected = (
                (nx.descendants(walking, start_node) & nx.ancestors(walking, start_node))
                | {start_node}
                if start_node is not None
                else set()
            )
            ox.save_graphml(graph, staging / "walking.graphml")
            fingerprint = hashlib.sha256((staging / "walking.graphml").read_bytes()).hexdigest()
            snapshot = {
                "id": snapshot_id,
                "area": area.model_dump(),
                "start_node": start_node,
                "acquired_at": now(),
                "source": source,
                "synthetic": synthetic,
                "graph_fingerprint": fingerprint,
                "places": [place.model_dump() for place in places],
                "eligible_mapped_ids": [
                    place.id for place in places if place.valid and place.entrance_node in connected
                ],
                "geometry": geometry,
            }
            staging.rename(self.config.data_dir / "snapshots" / snapshot_id)
            if activate:
                self.store.atomic(
                    [
                        ("snapshot", snapshot_id, snapshot),
                        ("area", "active", {**area.model_dump(), "snapshot_id": snapshot_id}),
                    ]
                )
            return snapshot
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def download(self, area: AreaInput, destination: Path) -> str:
        query = neighbourhood_query(area)
        failures = []
        last_error = None
        for provider, url in OVERPASS_PROVIDERS:
            try:
                with httpx.Client(
                    timeout=90,
                    headers={"User-Agent": "Nukkad/0.1 (https://github.com/Yajush-afk/Nukkad)"},
                    follow_redirects=True,
                    trust_env=False,
                ) as client:
                    with client.stream("POST", url, data={"data": query}) as response:
                        response.raise_for_status()
                        size = 0
                        with destination.open("wb") as output:
                            for chunk in response.iter_bytes():
                                size += len(chunk)
                                if size > MAX_EXTRACT_BYTES:
                                    raise ValueError(
                                        "Map extract exceeds the neighbourhood size limit"
                                    )
                                output.write(chunk)
                root = ElementTree.parse(destination).getroot()
                if root.tag != "osm":
                    raise ValueError("provider did not return map XML")
                if root.find("remark") is not None:
                    raise ValueError("provider returned an incomplete query result")
                return f"OpenStreetMap via {provider}"
            except (httpx.HTTPError, ElementTree.ParseError, ValueError) as error:
                last_error = error
                if isinstance(error, httpx.HTTPStatusError):
                    status = error.response.status_code
                    reasons = {429: "rate limit; retry later", 504: "provider query timed out"}
                    reason = f"HTTP {status}" + (
                        f" ({reasons[status]})" if status in reasons else ""
                    )
                elif isinstance(error, httpx.TimeoutException):
                    reason = "connection or response timed out"
                elif isinstance(error, httpx.HTTPError):
                    reason = "network connection failed"
                elif isinstance(error, ElementTree.ParseError):
                    reason = "invalid map XML"
                else:
                    reason = str(error)
                failures.append(f"{provider}: {reason}")
        raise ValueError(
            "Could not download this neighbourhood. "
            + "; ".join(failures)
            + ". Check your connection or retry later; your saved neighbourhood is unchanged."
        ) from last_error

    def snapshot(self) -> dict:
        area = self.store.get("area", "active")
        if not area:
            raise ValueError("Set up a neighbourhood first")
        return self.store.get("snapshot", area["snapshot_id"])

    def graph(self, snapshot: dict | None = None) -> nx.MultiDiGraph:
        snapshot = snapshot or self.snapshot()
        path = self.config.data_dir / "snapshots" / snapshot["id"] / "walking.graphml"
        if not path.is_file():
            raise ValueError("Saved walking graph is missing; refresh or restore your snapshot")
        if hashlib.sha256(path.read_bytes()).hexdigest() != snapshot["graph_fingerprint"]:
            raise ValueError("Saved walking graph failed its integrity check")
        return ox.load_graphml(path)

    def places(self, snapshot: dict | None = None) -> list[Place]:
        snapshot = snapshot or self.snapshot()
        area = AreaInput.model_validate(snapshot["area"])
        corrections = {value["id"]: value for value in self.store.list("place")}
        result = []
        for value in snapshot["places"]:
            corrected = corrections.get(value["id"])
            data = dict(value)
            if corrected:
                for key in (
                    "verification",
                    "valid",
                    "entrance",
                    "entrance_node",
                    "correction",
                    "verified_at",
                    "access",
                ):
                    data[key] = corrected[key]
            if prohibited(data["tags"]):
                data.update(valid=False, access="prohibited")
            result.append(Place.model_validate(data))
        result.extend(
            Place.model_validate(value)
            for value in corrections.values()
            if value["source"] == "user"
            and distance(area.start, Point.model_validate(value["point"])) <= area.radius_meters
        )
        if corrections:
            from nukkad.planning import pedestrian_graph

            walking = pedestrian_graph(self.graph(snapshot))
            for index, place in enumerate(result):
                if place.id not in corrections or place.entrance is None:
                    continue
                try:
                    node = nearest_node(walking, place.entrance)
                    entrance = Point(lat=walking.nodes[node]["y"], lon=walking.nodes[node]["x"])
                except ValueError:
                    node, entrance = None, None
                result[index] = place.model_copy(
                    update={"entrance_node": node, "entrance": entrance}
                )
        visited = {
            key for outcome in self.store.list("outcome") for key in outcome.get("reached_ids", [])
        }
        return [place.model_copy(update={"visited": place.id in visited}) for place in result]
