"""Measured local-model feasibility; fixtures contain synthetic public-place descriptions."""

import json
import statistics
import time
from datetime import UTC, datetime

from nukkad.config import Config
from nukkad.domain import Observations, Ranking, validate_ids
from nukkad.ollama import ModelFailure, Ollama, observation_prompt, ranking_prompt

CASES = [
    {"interests": ["trees", "quiet"], "state": "tired", "minutes": 20},
    {"interests": ["architecture"], "state": "curious", "minutes": 40},
    {"interests": ["markets"], "state": "need a change", "minutes": 30},
    {"interests": ["sports"], "state": "energetic", "minutes": 60},
    {"interests": ["art"], "state": "", "minutes": 30},
    {"interests": ["nature"], "state": "all nearby parks visited", "minutes": 45},
    {"interests": ["street details"], "state": "work pending", "minutes": 20},
    {"interests": ["public spaces"], "state": "quiet reflection", "minutes": 30},
    {"interests": ["trees", "markets"], "state": "try something different", "minutes": 40},
    {"interests": ["architecture", "art"], "state": "low energy", "minutes": 25},
]


def fixture_candidates() -> list[dict]:
    kinds = ["park", "market", "court", "artwork", "landmark", "tree", "garden", "square"]
    return [
        {
            "id": f"fixture-{index}",
            "name": f"Sample {kind}",
            "kind": kind,
            "descriptors": [],
            "visited": index % 3 == 0,
            "round_trip_meters": 300 + index * 180,
            "source": "synthetic",
            "verification": "unverified",
        }
        for index, kind in enumerate(kinds)
    ]


def benchmark(config: Config) -> dict:
    config.prepare()
    model = Ollama(config)
    installed = model.models()
    metadata = next((item for item in installed if item["name"] == config.model), None)
    if metadata is None:
        raise ModelFailure("Requested model is not installed")
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "model": config.model,
        "digest": metadata.get("digest"),
        "fixture": "synthetic-eight-places",
        "cases": [],
        "quality_review": "pending",
        "scope": "ranking and observations; excludes routing and export",
    }
    path = config.data_dir / "benchmarks" / f"{config.model.replace(':', '-')}.json"
    candidates = fixture_candidates()
    for index, context in enumerate(CASES):
        started = time.monotonic()
        deadline = started + 120
        result = {"case": index + 1, "context": context, "validated": False, "attempts": 0}
        try:
            for attempt in range(2):
                result["attempts"] += 1
                try:
                    ranked, rank_metrics = model.generate(
                        Ranking, ranking_prompt(candidates, context), deadline
                    )
                    validate_ids(
                        [place.id for place in ranked.places], [place["id"] for place in candidates]
                    )
                    break
                except (ModelFailure, ValueError):
                    if attempt:
                        raise
            lookup = {place["id"]: place for place in candidates}
            stops = [lookup[place.id] for place in ranked.places[:2]]
            for attempt in range(2):
                result["attempts"] += 1
                try:
                    prompts, prompt_metrics = model.generate(
                        Observations, observation_prompt(stops, context), deadline
                    )
                    validate_ids(
                        [stop.id for stop in prompts.stops], [stop["id"] for stop in stops]
                    )
                    break
                except (ModelFailure, ValueError):
                    if attempt:
                        raise
            result.update(
                validated=True,
                ranking=ranked.model_dump(),
                observations=prompts.model_dump(),
                ranking_metrics=rank_metrics,
                observation_metrics=prompt_metrics,
            )
        except (ModelFailure, ValueError) as error:
            result["error"] = str(error)
        result["seconds"] = round(time.monotonic() - started, 3)
        report["cases"].append(result)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(
            f"Case {index + 1}/10: {'validated' if result['validated'] else 'failed'} in {result['seconds']}s",
            flush=True,
        )
    durations = [case["seconds"] for case in report["cases"]]
    report["median_seconds"] = statistics.median(durations)
    report["maximum_seconds"] = max(durations)
    report["runtime_gate"] = (
        all(case["validated"] for case in report["cases"])
        and report["median_seconds"] <= 60
        and max(durations) <= 120
    )
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved measured results to {path}", flush=True)
    return report
