"""Project points onto eligible streets without changing persisted snapshots."""

import hashlib

from pyproj import Transformer
from shapely import transform
from shapely.geometry import LineString
from shapely.geometry import Point as GeometryPoint
from shapely.ops import substring

from nukkad.domain import Point
from nukkad.places import prohibited


def edge_line(graph, u, v, data):
    line = data.get("geometry") or LineString(
        [(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])]
    )
    start = GeometryPoint(graph.nodes[u]["x"], graph.nodes[u]["y"])
    return (
        LineString(list(line.coords)[::-1])
        if start.distance(GeometryPoint(line.coords[-1]))
        < start.distance(GeometryPoint(line.coords[0]))
        else line
    )


def snap_point(graph, point: Point, max_distance=50):
    """Split only the chosen physical edge and its matching reverse, in metres."""
    local = f"+proj=aeqd +lat_0={point.lat} +lon_0={point.lon} +datum=WGS84 +units=m"
    project = Transformer.from_crs("EPSG:4326", local, always_xy=True).transform
    unproject = Transformer.from_crs(local, "EPSG:4326", always_xy=True).transform
    origin = GeometryPoint(*project(point.lon, point.lat))
    choices = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        if prohibited(data) or prohibited(graph.nodes[u]) or prohibited(graph.nodes[v]):
            continue
        if data.get("highway") in {
            "primary",
            "primary_link",
            "secondary",
            "secondary_link",
        } and data.get("foot") not in {"yes", "designated", "permissive"}:
            continue
        line = edge_line(graph, u, v, data)
        metric = transform(line, project, interleaved=False)
        if metric.length:
            choices.append((metric.distance(origin), u, v, key, line, metric))
    if not choices:
        raise ValueError("No eligible mapped walking street is available")
    separation, u, v, key, line, metric = min(choices, key=lambda item: item[:4])
    if separation > max_distance:
        raise ValueError(
            f"Select an entrance within {max_distance} metres of an eligible mapped walking street"
        )
    along = metric.project(origin)
    projected = metric.interpolate(along)
    lon, lat = unproject(projected.x, projected.y)
    metadata = {
        "original": point.model_dump(),
        "projected": {"lat": lat, "lon": lon},
        "edge": [u, v, key],
        "distance_meters": round(separation, 3),
    }
    if along < 0.05:
        return u, metadata
    if metric.length - along < 0.05:
        return v, metadata
    selected = graph[u][v][key]
    marker = f"{sorted((u, v))}:{selected.get('osmid')}:{lon:.9f}:{lat:.9f}"
    node = -int(hashlib.sha256(marker.encode()).hexdigest()[:14], 16)
    graph.add_node(node, x=lon, y=lat, nukkad_snap=True)
    matching = []
    for a, b in ((u, v), (v, u)):
        for k, data in list(graph.get_edge_data(a, b, default={}).items()):
            candidate = edge_line(graph, a, b, data)
            if data.get("osmid") == selected.get("osmid") and candidate.equals(line):
                matching.append((a, b, k, data, transform(candidate, project, interleaved=False)))
    for a, b, k, data, candidate in matching:
        at = candidate.project(projected)
        graph.remove_edge(a, b, k)
        for start, end, low, high in ((a, node, 0, at), (node, b, at, candidate.length)):
            attributes = {
                **data,
                "geometry": transform(
                    substring(candidate, low, high), unproject, interleaved=False
                ),
                "length": data["length"] * (high - low) / candidate.length,
            }
            graph.add_edge(start, end, **attributes)
    return node, metadata
