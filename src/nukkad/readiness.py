"""Read-only component checks, cached against local data revisions."""

import sqlite3
import time
from dataclasses import replace

import cairosvg
from PIL import ImageFont

from nukkad.context import active_interests
from nukkad.maps import Maps
from nukkad.ollama import ModelFailure, Ollama
from nukkad.planning import Planner, QuestInput, Settings


def _check_readiness(app):
    store, config = app.state.store, app.state.config
    selected = Settings.model_validate(store.get("settings", "active") or {"model": config.model})
    area = store.get("area", "active")
    root = config.data_dir / "snapshots" / (area["snapshot_id"] if area else "missing")
    stamps = tuple(
        (path.name, path.stat().st_mtime_ns, path.stat().st_size)
        for path in root.glob("*")
        if path.is_file()
    )
    with store.connect() as connection:
        revisions = connection.execute(
            "SELECT kind,id,updated FROM records ORDER BY kind,id"
        ).fetchall()
    key = repr((selected.model_dump(), revisions, sorted(stamps)))
    cached = getattr(app.state, "readiness_cache", None)
    if cached and cached[0] == key and time.monotonic() - cached[1] < 10:
        return cached[2]
    checks = {}

    def put(name, status, reason):
        checks[name] = {"status": status, "reason": reason}

    try:
        store.check_record_versions()
        with store.connect() as connection:
            healthy = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        put(
            "database",
            "ready" if healthy and version == 1 else "damaged",
            "Local database integrity and version checked",
        )
    except (sqlite3.Error, ValueError) as error:
        put(
            "database",
            "damaged",
            str(error)
            if isinstance(error, ValueError)
            else "Database could not be checked; restore a backup",
        )
    model_names, model_status, capabilities = [], "unavailable", []
    try:
        model = Ollama(replace(config, model=selected.model))
        inventory = model.models()
        model_names = [item["name"] for item in inventory]
        installed = next((item for item in inventory if item["name"] == selected.model), None)
        model_status = "missing" if not installed else "ready"
        if (
            "cloud" in selected.model.lower()
            or installed
            and (installed.get("remote_host") or installed.get("remote_model"))
        ):
            model_status = "unsupported"
        if model_status == "ready":
            capabilities = model.information()["capabilities"]
        if model_status == "ready" and "completion" not in capabilities:
            model_status = "unsupported"
        put(
            "model",
            model_status,
            "Selected local model is available"
            if model_status == "ready"
            else "Choose an installed local model or start Ollama",
        )
    except ModelFailure as error:
        model_status = "unsupported" if error.category == "unsupported_model" else "unavailable"
        put("model", model_status, "Choose an installed local model; cloud inference is disabled")
    except Exception:
        put(
            "model",
            "unavailable",
            "Local runtime metadata unavailable; history and fallbacks remain usable",
        )
        model_status = "unavailable"
    put(
        "capabilities",
        "ready" if "completion" in capabilities else "unavailable",
        "Text inference supported; vision requires its own capability"
        if "completion" in capabilities
        else "Selected runtime does not report text completion support",
    )
    if not area:
        put("map", "setup_incomplete", "Save a neighbourhood map")
        put("start", "setup_incomplete", "Choose and confirm a public walking start")
        put("destinations", "setup_incomplete", "Prepare a map and walking start")
    else:
        maps = Maps(config, store)
        try:
            snapshot = maps.snapshot()
            if not snapshot or not (root / "source.osm").is_file():
                raise ValueError("Saved map source is missing; restore or refresh the map")
            maps.graph(snapshot)
            put("map", "ready", "Saved map and graph fingerprint checked")
            if not snapshot["area"]["public_start_confirmed"]:
                put("start", "setup_incomplete", "Confirm a public walking start")
                put("destinations", "setup_incomplete", "Confirm the start before checking routes")
            else:
                planner = Planner(maps, selected)
                put("start", "ready", "Start connects to an eligible mapped street")
                candidates = planner.candidates(
                    QuestInput(minutes=60), active_interests(store), shortlist=False
                )
                put(
                    "destinations",
                    "ready" if candidates else "unavailable",
                    f"{len(candidates)} destinations have eligible outbound and return paths within configured limits",
                )
        except ValueError as error:
            if "map" not in checks:
                put("map", "damaged", str(error))
            put("start", "unavailable", "Repair the saved map or choose a connected start")
            put("destinations", "unavailable", "Walking connections could not be checked")
    try:
        ImageFont.truetype("DejaVuSans.ttf", 23)
        ImageFont.truetype("DejaVuSans-Bold.ttf", 42)
        cairosvg.svg2png(
            bytestring=b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><text y="7" font-family="DejaVu Sans">N</text></svg>'
        )
        put("renderer", "ready", "Local SVG-to-PNG render succeeded")
    except Exception:
        put("renderer", "unavailable", "Install Cairo and the documented font dependencies")
    deterministic = all(
        checks[name]["status"] == "ready"
        for name in ("database", "map", "start", "destinations", "renderer")
    )
    result = {
        "application": "ready" if checks["database"]["status"] == "ready" else "saved_data_damaged",
        "database": checks["database"]["status"],
        "area_ready": checks["map"]["status"] == "ready",
        "model_status": model_status,
        "models": model_names,
        "selected_model": selected.model,
        "model_capabilities": capabilities,
        "deterministic_ready": deterministic,
        "local_ai_ready": model_status == "ready",
        "checks": checks,
    }
    app.state.readiness_cache = (key, time.monotonic(), result)
    return result


def check_readiness(app):
    try:
        return _check_readiness(app)
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        checks = {
            name: {
                "status": "unavailable",
                "reason": "Repair saved data or restore a backup before checking this component",
            }
            for name in ("map", "start", "destinations", "renderer", "model")
        }
        checks["database"] = {
            "status": "damaged",
            "reason": "Saved records or database could not be read; restore a backup",
        }
        return {
            "application": "saved_data_damaged",
            "database": "damaged",
            "area_ready": False,
            "model_status": "unavailable",
            "models": [],
            "selected_model": app.state.config.model,
            "model_capabilities": [],
            "deterministic_ready": False,
            "local_ai_ready": False,
            "checks": checks,
        }
