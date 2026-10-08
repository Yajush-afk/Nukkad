from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Point(Record):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RankedPlace(Record):
    id: str
    reason: str = Field(min_length=1, max_length=240)


class Ranking(Record):
    places: list[RankedPlace] = Field(min_length=1, max_length=15)


class Observation(Record):
    id: str
    activity: str = Field(pattern="^(sound|shape|colour|activity|detail|compare)$")
    text: str = Field(min_length=5, max_length=180)


class Observations(Record):
    stops: list[Observation] = Field(min_length=1, max_length=3)


def validate_ids(actual: list[str], expected: list[str]) -> None:
    if len(actual) != len(set(actual)):
        raise ValueError("Duplicate place IDs")
    if set(actual) != set(expected):
        raise ValueError("Place IDs must match the supplied list exactly")
