"""Explicit, cached place search through a configurable Nominatim endpoint."""

import hashlib
import os
import threading
import time
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, ValidationError, field_validator

from nukkad.domain import Point, Record
from nukkad.storage import Store

router = APIRouter(prefix="/api/locations")
_lock = threading.Lock()
_next_request = 0.0
DEFAULT_ENDPOINT = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Nukkad/0.1 (https://github.com/Yajush-afk/Nukkad)"


class SearchInput(Record):
    query: str = Field(min_length=3, max_length=240)

    @field_validator("query", mode="before")
    @classmethod
    def normalize(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


class Location(Record):
    name: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=1000)
    point: Point


class SearchUnavailable(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


def endpoint() -> str:
    url = os.environ.get("NUKKAD_GEOCODING_URL", DEFAULT_ENDPOINT)
    try:
        parsed = urlsplit(url)
        _ = parsed.port  # Validate malformed or out-of-range ports before making a request.
    except ValueError as error:
        raise SearchUnavailable(
            "Place search is not configured with a valid Nominatim endpoint."
        ) from error
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        parsed.scheme != "https"
        and not (local and parsed.scheme == "http")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise SearchUnavailable("Place search is not configured with a valid Nominatim endpoint.")
    return url


def search(store: Store, query: str) -> dict:
    """No autocomplete, retries, background lookups or unbounded request queues."""
    global _next_request
    query = SearchInput(query=query).query
    url = endpoint()
    key = hashlib.sha256((url + "\0" + query.casefold()).encode()).hexdigest()
    cached = store.get("location_search", key)
    if cached and cached["expires_at"] > time.time():
        return {"matches": cached["matches"], "cached": True, "source": "OpenStreetMap / Nominatim"}
    if not _lock.acquire(blocking=False):
        raise SearchUnavailable(
            "A location search is already running. Please wait for it to finish.", 429
        )
    try:
        wait = _next_request - time.monotonic()
        if wait > 1.1:
            raise SearchUnavailable("Location search is cooling down. Try again in a minute.", 429)
        if wait > 0:
            time.sleep(wait)
        _next_request = time.monotonic() + 1.1
        try:
            with httpx.Client(
                timeout=15,
                trust_env=False,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=False,
            ) as client:
                response = client.get(
                    url,
                    params={
                        "q": query,
                        "format": "jsonv2",
                        "limit": 5,
                        "addressdetails": 1,
                        "accept-language": "en",
                    },
                )
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, list):
                raise ValueError("Unexpected search response")
            matches, seen = [], set()
            for item in data[:5]:
                try:
                    label = item["display_name"]
                    location = Location(
                        name=(item.get("name") or label.split(",")[0])[:200],
                        label=label,
                        point={"lat": item["lat"], "lon": item["lon"]},
                    )
                except (KeyError, TypeError, AttributeError, ValidationError):
                    continue
                if location.label in seen:
                    continue
                seen.add(location.label)
                matches.append(location.model_dump())
            if data and not matches:
                raise ValueError("Search returned unusable locations")
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status == 429:
                _next_request = time.monotonic() + 60
            reason = (
                "Search is rate-limited; try again in a minute."
                if status == 429
                else f"Location search returned HTTP {status}. Try again later."
            )
            raise SearchUnavailable(reason, 429 if status == 429 else 503) from error
        except (httpx.HTTPError, ValueError) as error:
            raise SearchUnavailable(
                "Could not reach a usable location search service. Check your connection and try again. Your saved map is unchanged."
            ) from error
        # Cache empty results briefly; successful matches are usable locally for 30 days.
        store.put(
            "location_search",
            key,
            {"matches": matches, "expires_at": time.time() + (30 * 86400 if matches else 600)},
        )
        return {"matches": matches, "cached": False, "source": "OpenStreetMap / Nominatim"}
    finally:
        _lock.release()


@router.post("/search")
def search_location(value: SearchInput, request: Request):
    try:
        return search(request.app.state.store, value.query)
    except SearchUnavailable as error:
        raise HTTPException(error.status, str(error)) from error
