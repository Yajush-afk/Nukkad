import itertools
import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import networkx as nx
from astral import Observer
from astral.sun import sun
from pydantic import Field

from nukkad.domain import Point, Record
from nukkad.maps import Maps
from nukkad.places import Place, prohibited


class Settings(Record):
    model: str = Field(default="gemma4:e2b", min_length=1, max_length=100)
    walking_kmh: float = Field(default=4, ge=2, le=6)
    stop_minutes: int = Field(default=4, ge=1, le=10)
    reserve_minutes: int = Field(default=5, ge=5, le=15)
    max_distance_meters: int = Field(default=4000, ge=200, le=10000)
    max_stops: int = Field(default=3, ge=1, le=3)
    daylight_required: bool = True
    sunset_margin_minutes: int = Field(default=15, ge=15, le=60)
    tone: str = Field(default="friendly and observational", max_length=100)
    air_quality_enabled: bool = False
    air_quality_threshold: int | None = Field(default=None, ge=0, le=500)


class QuestInput(Record):
    minutes: int = Field(default=30, ge=20, le=60)
    state: str = Field(default="", max_length=500)
    mode: str = Field(default="wander", pattern="^(wander|seek)$")


class NoQuest(ValueError):
    pass


def pedestrian_graph(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    result = graph.copy()
    blocked_nodes = {node for node, data in result.nodes(data=True) if prohibited(data)}
    result.remove_nodes_from(blocked_nodes)
    remove = []
    for u, v, key, data in result.edges(keys=True, data=True):
        if (
            prohibited(data)
            or data.get("highway") in {"primary", "primary_link", "secondary", "secondary_link"}
            and data.get("foot") not in {"yes", "designated", "permissive"}
        ):
            remove.append((u, v, key))
        elif data.get("oneway:foot") == "yes" and data.get("reversed"):
            remove.append((u, v, key))
    result.remove_edges_from(remove)
    return result


INTEREST_KINDS = {
    "nature": {"park", "garden", "tree"},
    "trees": {"tree", "park", "garden"},
    "quiet": {"park", "garden"},
    "art": {"artwork", "landmark"},
    "architecture": {"landmark", "artwork", "attraction"},
    "markets": {"market"},
    "food": {"market"},
    "sports": {"court", "sports_centre"},
    "history": {"landmark"},
}


def interest_score(place: Place, interests: list[str]) -> float:
    tokens = {word.strip(".,!?:;").lower() for theme in interests for word in theme.split()}
    matches = sum(place.kind in kinds for theme, kinds in INTEREST_KINDS.items() if theme in tokens)
    return matches + int(not place.visited) - (place.round_trip_meters or 0) / 1000


def baseline(candidates: list[Place], interests: list[str], mode: str = "interests") -> list[str]:
    if mode == "nearest":
        ordered = sorted(
            candidates,
            key=lambda place: (place.visited, place.round_trip_meters or math.inf, place.id),
        )
    else:
        ordered = sorted(
            candidates,
            key=lambda place: (
                -interest_score(place, interests),
                place.round_trip_meters or math.inf,
                place.id,
            ),
        )
    return [place.id for place in ordered]


class Planner:
    def __init__(self, maps: Maps, settings: Settings, clock=None):
        self.maps, self.settings = maps, settings
        self.clock = clock or (lambda: datetime.now(UTC))
        self.snapshot = maps.snapshot()
        if not self.snapshot["area"].get("public_start_confirmed", False):
            raise NoQuest(
                "Choose and confirm a public starting point on your neighbourhood map first"
            )
        self.graph = pedestrian_graph(maps.graph(self.snapshot))
        self.start_node = self.snapshot["start_node"]
        if self.start_node not in self.graph:
            raise NoQuest(
                "Starting point is not on an eligible walking street; choose a public start"
            )
        self.paths: dict[tuple[int, int], tuple[list[int], float]] = {}

    def path(self, start: int, end: int) -> tuple[list[int], float]:
        key = (start, end)
        if key not in self.paths:
            try:
                nodes = nx.shortest_path(self.graph, start, end, weight="length")
                length = sum(
                    min(data["length"] for data in self.graph[u][v].values())
                    for u, v in zip(nodes, nodes[1:], strict=False)
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound) as error:
                raise NoQuest("No eligible mapped walking connection") from error
            self.paths[key] = nodes, length
        return self.paths[key]

    def turns(self, path: list[int]) -> int:
        bearings = []
        for a, b in zip(path, path[1:], strict=False):
            first, second = self.graph.nodes[a], self.graph.nodes[b]
            bearings.append(
                math.degrees(
                    math.atan2(
                        (second["x"] - first["x"]) * math.cos(math.radians(first["y"])),
                        second["y"] - first["y"],
                    )
                )
            )
        return sum(
            abs((b - a + 180) % 360 - 180) > 35
            for a, b in zip(bearings, bearings[1:], strict=False)
        )

    def candidates(self, request: QuestInput, interests: list[str]) -> list[Place]:
        result = []
        for place in self.maps.places(self.snapshot):
            if (
                not place.valid
                or prohibited(place.tags)
                or place.entrance_node is None
                or place.entrance_node == self.start_node
            ):
                continue
            if request.mode == "seek" and not place.descriptors:
                continue
            try:
                _, outbound = self.path(self.start_node, place.entrance_node)
                _, inbound = self.path(place.entrance_node, self.start_node)
            except NoQuest:
                continue
            total = outbound + inbound
            if (
                self.duration(total, 1) > request.minutes
                or total > self.settings.max_distance_meters
            ):
                continue
            result.append(place.model_copy(update={"round_trip_meters": total}))
        # Interleave interest fit and proximity so a shortlist retains variety.
        interest_order = baseline(result, interests)
        near_order = baseline(result, interests, "nearest")
        lookup = {place.id: place for place in result}
        selected = []
        for pair in zip(interest_order, near_order, strict=True):
            for key in pair:
                if key not in selected:
                    selected.append(key)
        return [lookup[key] for key in selected[:15]]

    def duration(self, meters: float, stops: int) -> float:
        return (
            meters / (self.settings.walking_kmh * 1000 / 60)
            + stops * self.settings.stop_minutes
            + self.settings.reserve_minutes
        )

    def daylight(self, moment: datetime) -> dict:
        area = self.snapshot["area"]
        point = Point.model_validate(area["start"])
        timezone = ZoneInfo(area["timezone"])
        try:
            times = sun(
                Observer(point.lat, point.lon),
                date=moment.astimezone(timezone).date(),
                tzinfo=timezone,
            )
        except ValueError as error:
            raise NoQuest("Daylight could not be established for this date and location") from error
        return times

    def build(self, candidates: list[Place], ranked_ids: list[str], request: QuestInput) -> dict:
        if not candidates:
            raise NoQuest(
                "No destinations with usable entrances and return paths fit this time budget. Review places or add a public pin."
            )
        if set(ranked_ids) != {place.id for place in candidates} or len(set(ranked_ids)) != len(
            ranked_ids
        ):
            raise ValueError("Ranked IDs must match eligible candidates exactly")
        started = self.clock()
        daylight = self.daylight(started)
        if self.settings.daylight_required and started < daylight["sunrise"]:
            raise NoQuest("Wait until daylight to start this quest")
        lookup = {place.id: place for place in candidates}
        points = {key: len(ranked_ids) - index for index, key in enumerate(ranked_ids)}
        best = None
        for count in range(1, min(len(candidates), self.settings.max_stops) + 1):
            for order in itertools.permutations(ranked_ids, count):
                nodes = [
                    self.start_node,
                    *[lookup[key].entrance_node for key in order],
                    self.start_node,
                ]
                try:
                    paths = [self.path(a, b) for a, b in zip(nodes, nodes[1:], strict=False)]
                except NoQuest:
                    continue
                meters = sum(length for _, length in paths)
                minutes = self.duration(meters, count)
                if minutes > request.minutes or meters > self.settings.max_distance_meters:
                    continue
                if (
                    self.settings.daylight_required
                    and started + timedelta(minutes=minutes + self.settings.sunset_margin_minutes)
                    > daylight["sunset"]
                ):
                    continue
                turns = sum(self.turns(path) for path, _ in paths)
                score = (-sum(points[key] for key in order), minutes, turns, order)
                if best is None or score < best[0]:
                    best = score, order, paths, meters, minutes
        if best is None:
            raise NoQuest(
                "No complete return walk fits the current time, distance and daylight limits"
            )
        _, order, paths, meters, minutes = best
        departure = daylight["sunset"] - timedelta(
            minutes=minutes + self.settings.sunset_margin_minutes
        )
        legs = []
        for index, (path, length) in enumerate(paths):
            streets = []
            for u, v in zip(path, path[1:], strict=False):
                data = min(self.graph[u][v].values(), key=lambda value: value["length"])
                name = data.get("name", "Unnamed mapped path")
                if isinstance(name, list):
                    name = " / ".join(name)
                if not streets or streets[-1] != name:
                    streets.append(name)
            legs.append(
                {
                    "number": index + 1,
                    "meters": round(length, 1),
                    "coordinates": [
                        [self.graph.nodes[node]["x"], self.graph.nodes[node]["y"]] for node in path
                    ],
                    "streets": streets,
                }
            )
        return {
            "snapshot_id": self.snapshot["id"],
            "start": self.snapshot["area"]["start"],
            "start_node": self.start_node,
            "timezone": self.snapshot["area"]["timezone"],
            "generated_at": started.isoformat(),
            "latest_departure": departure.isoformat()
            if self.settings.daylight_required
            else (started + timedelta(minutes=30)).isoformat(),
            "sunset": daylight["sunset"].isoformat(),
            "meters": round(meters, 1),
            "estimated_minutes": round(minutes, 1),
            "stops": [lookup[key].model_dump() for key in order],
            "legs": legs,
            "input": request.model_dump(),
            "settings": self.settings.model_dump(),
            "ranked_ids": ranked_ids,
            "candidate_ids": [place.id for place in candidates],
        }
