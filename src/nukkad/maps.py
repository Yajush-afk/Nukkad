import hashlib
import math
import shutil
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree as XML

import httpx
import networkx as nx
import osmnx as ox
from defusedxml import ElementTree

from nukkad.config import Config
from nukkad.domain import Point
from nukkad.identities import canonical_id, identity_records
from nukkad.places import AreaInput, Place, place_kind, prohibited
from nukkad.polygons import multipolygons
from nukkad.storage import Store, identity, now

MAX_EXTRACT_BYTES = 32 * 1024 * 1024
OVERPASS_PROVIDERS = (
    ("Overpass (main)", "https://overpass-api.de/api/interpreter"),
    ("Overpass (Private.coffee)", "https://overpass.private.coffee/api/interpreter"),
)


def neighbourhood_bounds(area: AreaInput) -> tuple[float, float, float, float]:
    radius = area.radius_meters + 700
    delta_lat = radius / 111320
    delta_lon = radius / (111320 * max(0.2, math.cos(math.radians(area.start.lat))))
    return (
        area.start.lat - delta_lat,
        area.start.lon - delta_lon,
        area.start.lat + delta_lat,
        area.start.lon + delta_lon,
    )


def neighbourhood_query(area: AreaInput, bounds=None) -> str:
    bbox = ",".join(str(value) for value in (bounds or neighbourhood_bounds(area)))
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
        f"{kind}{condition}({bbox});"
        for condition in filters
        for kind in ("node", "way", "relation")
    )
    # Recurse to keep referenced way vertices and their access/entrance tags.
    return "[out:xml][timeout:25];(" + "".join(selectors) + ");(._;>;);out body;"


def merge_sections(paths, destination):
    """Retain complete source entities, reject inconsistent edits between sections."""
    entities = {}
    signatures = {}
    root = XML.Element("osm", {"version": "0.6", "generator": "Nukkad map sections"})
    for path in paths:
        for element in ElementTree.parse(path).getroot():
            if element.tag not in {"node", "way", "relation"}:
                continue
            key = (element.tag, element.attrib["id"])
            signature = (
                tuple(sorted(element.attrib.items())),
                tuple(
                    tuple(sorted(child.attrib.items())) for child in element if child.tag != "tag"
                ),
                tuple(
                    sorted(tuple(sorted(child.attrib.items())) for child in element.findall("tag"))
                ),
            )
            if key in signatures and signatures[key] != signature:
                raise ValueError("Map changed between sections; retry to get a consistent map")
            entities[key], signatures[key] = element, signature
    for element in entities.values():
        references = [("node", ref.attrib["ref"]) for ref in element.findall("nd")]
        references += [(ref.attrib["type"], ref.attrib["ref"]) for ref in element.findall("member")]
        if any(key not in entities for key in references):
            raise ValueError("Map section is missing referenced geometry")
    for key in sorted(entities):
        root.append(entities[key])
    XML.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
    if destination.stat().st_size > MAX_EXTRACT_BYTES:
        raise ValueError("Map extract exceeds the neighbourhood size limit")


def distance(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    delta_lat, delta_lon = lat2 - lat1, math.radians(b.lon - a.lon)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 6371000 * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0, 1 - value)))


def nearest_node(graph: nx.MultiDiGraph, point: Point, max_distance: float = 50) -> int:
    from nukkad.snapping import snap_point

    return snap_point(graph, point, max_distance)[0]


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
    relations, suppressed = multipolygons(root, points)
    places = []
    backgrounds = []
    elements = (
        list(root.findall("node"))
        + [way for way in root.findall("way") if way.attrib["id"] not in suppressed]
        + list(root.findall("relation"))
    )
    for element in elements:
        raw_tags = tags(element)
        kind = place_kind(raw_tags)
        node_ids = [int(ref.attrib["ref"]) for ref in element.findall("nd")]
        coordinates = [points[key] for key in node_ids if key in points]
        is_node = element.tag == "node"
        relation = relations.get(element.attrib["id"]) if element.tag == "relation" else None
        if element.tag == "relation" and relation is None:
            continue
        if relation:
            node_ids = relation["nodes"]
            coordinates = [points[key] for key in node_ids]
            point = Point(lat=relation["point"].y, lon=relation["point"].x)
            backgrounds.append(
                {
                    "type": "Feature",
                    "properties": {
                        "kind": kind,
                        "name": raw_tags.get("name", ""),
                        "source_id": f"osm-relation-{element.attrib['id']}",
                    },
                    "geometry": relation["geometry"],
                }
            )
        elif is_node:
            point = points[int(element.attrib["id"])]
        elif coordinates:
            point = Point(
                lat=sum(item.lat for item in coordinates) / len(coordinates),
                lon=sum(item.lon for item in coordinates) / len(coordinates),
            )
        else:
            continue
        if (
            not relation
            and coordinates
            and (raw_tags.get("building") or raw_tags.get("leisure") in {"park", "garden"})
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
                source_ids=[
                    f"osm-{element.tag}-{element.attrib['id']}",
                    *(relation["aliases"] if relation else []),
                ],
                member_ids=relation["members"] if relation else [],
                geometry=relation["geometry"] if relation else None,
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
        progress=None,
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
                source = self.download(area, raw_path, progress)
            if progress:
                progress("Processing saved streets and places")
            graph, places, geometry = parse_extract(raw_path, area)
            synthetic = synthetic or graph.graph.get("nukkad_synthetic", False)
            if synthetic:
                source = "Synthetic fixture XML; not real-world OpenStreetMap data"
            from nukkad.planning import pedestrian_graph

            walking = pedestrian_graph(graph)
            try:
                from nukkad.snapping import snap_point

                start_node, start_snap = snap_point(walking, area.start)
            except ValueError:
                if area.public_start_confirmed:
                    raise
                # A geocoded building/locality centre is enough to download a map,
                # but is never silently promoted to a confirmed walking entrance.
                start_node, start_snap = None, None
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
                "start_snap": start_snap,
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
                        *identity_records(self.store, places),
                    ]
                )
            return snapshot
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def download(self, area: AreaInput, destination: Path, progress=None) -> str:
        failures, recoverable = [], []
        deadline = time.monotonic() + 180
        last_error = None

        def fetch(url, query, path):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("Map download time limit reached")
            with httpx.Client(
                timeout=httpx.Timeout(min(35, remaining), connect=min(5, remaining)),
                headers={"User-Agent": "Nukkad/0.1 (https://github.com/Yajush-afk/Nukkad)"},
                follow_redirects=True,
                trust_env=False,
            ) as client:
                with client.stream("POST", url, data={"data": query}) as response:
                    response.raise_for_status()
                    size = 0
                    with path.open("wb") as output:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > MAX_EXTRACT_BYTES:
                                raise ValueError("Map extract exceeds the neighbourhood size limit")
                            if time.monotonic() > deadline:
                                raise ValueError("Map download time limit reached")
                            output.write(chunk)
            root = ElementTree.parse(path).getroot()
            if root.tag != "osm":
                raise ValueError("provider did not return map XML")
            if root.find("remark") is not None:
                raise ValueError("provider returned an incomplete query result")

        def failed(provider, error):
            if isinstance(error, httpx.HTTPStatusError):
                status = error.response.status_code
                reason = f"HTTP {status}"
                reason += {
                    429: " (rate limit; retry later)",
                    504: " (provider query timed out)",
                }.get(status, "")
            elif isinstance(error, httpx.TimeoutException):
                reason = "connection or response timed out"
            elif isinstance(error, httpx.HTTPError):
                reason = "network connection failed"
            elif isinstance(error, ElementTree.ParseError):
                reason = "invalid map XML"
            else:
                reason = str(error)
            failures.append(f"{provider}: {reason}")

        errors = (httpx.HTTPError, ElementTree.ParseError, ValueError)
        with tempfile.TemporaryDirectory(prefix=".download-", dir=destination.parent) as folder:
            candidate = Path(folder) / "complete.osm"
            for provider, url in OVERPASS_PROVIDERS:
                try:
                    if progress:
                        progress("Downloading neighbourhood map")
                    fetch(url, neighbourhood_query(area), candidate)
                    if progress:
                        progress("Processing saved streets and places")
                    candidate.replace(destination)
                    return f"OpenStreetMap via {provider}"
                except errors as error:
                    last_error = error
                    failed(provider, error)
                    if isinstance(error, httpx.TimeoutException) or (
                        isinstance(error, httpx.HTTPStatusError)
                        and error.response.status_code in {500, 502, 503, 504}
                    ):
                        recoverable.append((provider, url))
            # One sequential, all-or-nothing sectional attempt. Never retry a
            # rate-limited provider or shrink the user's requested neighbourhood.
            if recoverable and time.monotonic() < deadline:
                provider, url = recoverable[0]
                south, west, north, east = neighbourhood_bounds(area)
                mid_lat, mid_lon = (south + north) / 2, (west + east) / 2
                bounds = [
                    (s, w, n, e)
                    for s, n in ((south, mid_lat), (mid_lat, north))
                    for w, e in ((west, mid_lon), (mid_lon, east))
                ]
                try:
                    sections, total = [], 0
                    for index, box in enumerate(bounds):
                        if progress:
                            progress(
                                f"Map services are busy. Downloading smaller section {index + 1} of 4"
                            )
                        section = Path(folder) / f"section-{index}.osm"
                        fetch(url, neighbourhood_query(area, box), section)
                        total += section.stat().st_size
                        if total > MAX_EXTRACT_BYTES:
                            raise ValueError("Map sections exceed the neighbourhood size limit")
                        sections.append(section)
                    merge_sections(sections, candidate)
                    if progress:
                        progress("Processing saved streets and places")
                    candidate.replace(destination)
                    return f"OpenStreetMap via {provider}, four smaller sections"
                except errors as error:
                    last_error = error
                    failed(f"{provider} smaller sections", error)
        raise ValueError(
            "Could not download this neighbourhood. "
            + "; ".join(failures)
            + ". Map services may be busy or unreachable; retry later. Your saved neighbourhood is unchanged."
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

        def load():
            graph = ox.load_graphml(path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != snapshot["graph_fingerprint"]:
                raise ValueError("Saved walking graph changed while loading")
            return graph

        return self.store.cache.get("graph", (str(path), snapshot["graph_fingerprint"]), load)

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
                    "last_report",
                    "valid",
                    "entrance",
                    "entrance_node",
                    "snap",
                    "correction",
                    "verified_at",
                    "access",
                ):
                    data[key] = corrected.get(key)
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
                    from nukkad.snapping import snap_point

                    node, snap = snap_point(
                        walking,
                        Point.model_validate(place.snap["original"])
                        if place.snap
                        else place.entrance,
                    )
                    entrance = Point(lat=walking.nodes[node]["y"], lon=walking.nodes[node]["x"])
                except ValueError:
                    node, entrance, snap = None, None, None
                result[index] = place.model_copy(
                    update={"entrance_node": node, "entrance": entrance, "snap": snap}
                )
        aliases = self.store.keyed("place_alias")
        visited = {
            canonical_id(self.store, key, aliases)
            for outcome in self.store.list("outcome")
            for key in outcome.get("reached_ids", [])
        }
        visited.update(
            canonical_id(self.store, item["place_id"], aliases)
            for item in self.store.list("experience")
            if item.get("active")
        )
        grouped = {}
        for place in result:
            root = canonical_id(self.store, place.id, aliases)
            correction = corrections.get(root)
            if correction and root != place.id:
                place = place.model_copy(
                    update={
                        key: correction[key]
                        for key in ("verification", "valid", "access", "correction", "last_report")
                        if key in correction
                    }
                )
            if prohibited(place.tags):
                place = place.model_copy(update={"valid": False, "access": "prohibited"})
            old = grouped.get(root)
            sources = sorted(
                set([*(old.source_ids if old else []), *(place.source_ids or [place.id])])
            )
            grouped[root] = place.model_copy(
                update={
                    "id": root,
                    "canonical_id": root,
                    "source_ids": sources,
                    "visited": root in visited,
                    "valid": place.valid and (old.valid if old else True),
                }
            )
        return list(grouped.values())
