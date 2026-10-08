from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from nukkad.domain import Point, Record


class AreaInput(Record):
    name: str = Field(min_length=1, max_length=100)
    start: Point
    radius_meters: int = Field(default=2000, ge=200, le=3000)
    timezone: str = "Asia/Kolkata"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown timezone") from error
        return value


class Place(Record):
    id: str
    name: str = Field(min_length=1, max_length=200)
    kind: str
    point: Point
    entrance: Point | None = None
    entrance_node: int | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    descriptors: list[str] = Field(default_factory=list, max_length=8)
    source: Literal["osm", "user"] = "osm"
    verification: Literal["unverified", "verified"] = "unverified"
    access: Literal["unknown", "mapped", "confirmed", "prohibited"] = "unknown"
    valid: bool = True
    visited: bool = False
    round_trip_meters: float | None = None
    correction: str | None = None
    verified_at: str | None = None


class CustomPlace(Record):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=40)
    entrance: Point
    descriptors: list[str] = Field(default_factory=list, max_length=8)
    public_access_confirmed: bool


class Correction(Record):
    action: Literal["not_there", "closed", "not_accessible", "verify", "entrance"]
    detail: str = Field(min_length=3, max_length=500)
    entrance: Point | None = None


def prohibited(tags: dict) -> bool:
    return (
        tags.get("access") in {"no", "private", "military"}
        or tags.get("foot") in {"no", "private"}
        or tags.get("landuse") in {"military", "construction"}
        or tags.get("highway")
        in {"construction", "proposed", "motorway", "motorway_link", "trunk", "trunk_link"}
        or bool(tags.get("access:conditional"))
        or bool(tags.get("foot:conditional"))
    )


def place_kind(tags: dict) -> str | None:
    if tags.get("leisure") in {"park", "garden", "pitch", "sports_centre"}:
        return "court" if tags["leisure"] == "pitch" else tags["leisure"]
    if tags.get("amenity") in {"marketplace", "place_of_worship", "food_court"}:
        return {"marketplace": "market", "place_of_worship": "landmark", "food_court": "market"}[
            tags["amenity"]
        ]
    if tags.get("tourism") in {"artwork", "attraction"}:
        return tags["tourism"]
    if tags.get("historic") in {"monument", "memorial"}:
        return "landmark"
    if tags.get("natural") == "tree" and tags.get("name"):
        return "tree"
    if tags.get("shop") and tags.get("name"):
        return "market"
    return None
