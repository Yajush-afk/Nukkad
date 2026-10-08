import math
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Request

from nukkad.areas_api import maps
from nukkad.planning import NoQuest
from nukkad.planning_api import settings
from nukkad.storage import now

router = APIRouter(prefix="/api/air-quality")
SOURCE = "Open-Meteo / CAMS global atmospheric composition forecast"
LIMITATION = "U.S. AQI regional model estimate at approximately 45 km resolution; not a measurement of this street."


def state(store, snapshot, moment=None):
    moment = moment or datetime.now(UTC)
    cached = store.get("air_quality", snapshot["id"])
    result = {"status": "unknown", "label": "U.S. AQI", "source": SOURCE, "limitation": LIMITATION}
    if not cached:
        return result
    try:
        retrieved = datetime.fromisoformat(cached["retrieved_at"])
        valid = datetime.fromisoformat(cached["valid_at"])
        value = cached["value"]
        fresh = (
            0 <= (moment - retrieved).total_seconds() <= 10800
            and abs((moment - valid).total_seconds()) <= 5400
        )
        known = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
        )
    except (KeyError, ValueError, TypeError):
        fresh = known = False
    return {**result, **cached, "status": "known" if fresh and known else "unknown"}


def enforce(store, snapshot, settings, moment=None):
    if not settings.air_quality_enabled:
        return {"status": "disabled"}
    result = state(store, snapshot, moment)
    if result["status"] != "known":
        raise NoQuest(
            "Air-quality policy is enabled but its regional estimate is unknown or stale. Refresh data or review your policy."
        )
    if settings.air_quality_threshold is None or result["value"] > settings.air_quality_threshold:
        raise NoQuest(
            "Regional U.S. AQI exceeds your selected threshold; no outdoor quest under this policy"
        )
    return result


@router.get("")
def get_air(request: Request):
    if not settings(request).air_quality_enabled:
        return {"status": "disabled", "limitation": LIMITATION}
    return state(request.app.state.store, maps(request).snapshot())


@router.post("/refresh")
def refresh(request: Request):
    if not settings(request).air_quality_enabled:
        raise ValueError("Enable the air-quality policy before requesting data")
    snapshot = maps(request).snapshot()
    point = snapshot["area"]["start"]
    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            response = client.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={
                    "latitude": point["lat"],
                    "longitude": point["lon"],
                    "current": "us_aqi",
                    "domains": "cams_global",
                    "timezone": "GMT",
                    "timeformat": "unixtime",
                },
            )
            response.raise_for_status()
            current = response.json()["current"]
        cached = {
            "value": current["us_aqi"],
            "valid_at": datetime.fromtimestamp(current["time"], UTC).isoformat(),
            "retrieved_at": now(),
            "source": SOURCE,
            "limitation": LIMITATION,
            "label": "U.S. AQI",
        }
        request.app.state.store.put("air_quality", snapshot["id"], cached)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise ValueError(
            "Regional estimate unavailable; previous cache preserved and freshness still checked"
        ) from None
    return state(request.app.state.store, snapshot)
