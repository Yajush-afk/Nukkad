"""Local vision measurements use generated test scenes, never personal photos."""

import io
import json
import time
from pathlib import Path

from PIL import Image, ImageDraw

from nukkad.config import Config
from nukkad.evaluation import loopback_only
from nukkad.location_cards import active_photos, generate_visit
from nukkad.ollama import ModelFailure, Ollama
from nukkad.photos import save_photo
from nukkad.storage import Store, identity, now


def synthetic_photo(index):
    image = Image.new(
        "RGB", (640, 480), ["#dce8dc", "#e7dfcf", "#d4e1ef", "#efd7d0", "#e5e3ce"][index]
    )
    draw = ImageDraw.Draw(image)
    if index % 2 == 0:
        draw.ellipse((180, 100, 460, 380), fill="#ca724d", outline="#385c44", width=8)
    else:
        draw.rectangle((180, 100, 460, 380), fill="#385c44", outline="#ca724d", width=8)
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def evaluate_vision(config: Config, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    isolated = Config(data_dir=output / "private-data", model=config.model)
    isolated.prepare()
    store = Store(isolated.data_dir)
    experience = {
        "id": identity(),
        "active": True,
        "place_id": "synthetic-place",
        "place_name": "Synthetic scene",
        "note": "I enjoyed noticing the painted circles in this synthetic scene.",
        "provenance": "synthetic fixture; not a physical visit",
        "status": "completed",
        "revision": identity(),
        "updated_at": now(),
    }
    store.put("experience", experience["id"], experience)
    report = {
        "scope": "Synthetic scenes, one note and actual local vision; not photographs of real places or evidence of attendance",
        "model": config.model,
        "cases": [],
        "human_quality_ratings": "pending",
    }
    with loopback_only() as attempts:
        for index in range(5):
            save_photo(isolated, store, experience["id"], synthetic_photo(index))
        experience = store.get("experience", experience["id"])
        photos = active_photos(store, experience["id"])
        for count in (1, 3, 5):
            began = time.monotonic()
            row = {"image_count": count, "validated": False}
            try:
                chosen, writing, metrics = generate_visit(
                    Ollama(isolated),
                    experience,
                    photos[:count],
                    [
                        (isolated.data_dir / photo["files"]["inference"]["path"]).read_bytes()
                        for photo in photos[:count]
                    ],
                    lambda message: print(message, flush=True),
                    began + 180,
                )
                row.update(
                    validated=True,
                    photo_id=chosen.photo_id,
                    reason=chosen.reason,
                    writing=writing.model_dump(),
                    metrics=metrics,
                )
            except ModelFailure as error:
                row.update(failure_category=error.category, metrics=error.diagnostics)
            row["seconds"] = round(time.monotonic() - began, 3)
            report["cases"].append(row)
            report["blocked_non_loopback_attempts"] = list(attempts)
            (output / "vision-diagnostics.json").write_text(json.dumps(report, indent=2))
            print(f"{count} images: {row['seconds']}s; validated={row['validated']}", flush=True)
    return report
