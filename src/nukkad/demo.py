"""An isolated, deliberately artificial area for reproducible UI demonstrations."""

import json
import shutil
import tempfile
from pathlib import Path

from nukkad.config import Config
from nukkad.evaluation import synthetic_map
from nukkad.maps import Maps
from nukkad.places import AreaInput
from nukkad.storage import Store


def prepare_demo(destination: Path, model: str) -> Path:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Demo requires a new directory; existing data will not be overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="nukkad-demo-", dir=destination.parent))
    try:
        config = Config(data_dir=staging, model=model)
        config.prepare()
        source = staging / "synthetic.osm"
        synthetic_map(source)
        source.write_text(
            source.read_text()
            .replace(
                '<tag k="tourism" v="artwork"/>',
                '<tag k="tourism" v="artwork"/><tag k="artwork_type" v="sculpture"/>',
            )
            .replace(
                '<tag k="leisure" v="pitch"/>',
                '<tag k="leisure" v="pitch"/><tag k="sport" v="basketball"/>',
            )
        )
        store = Store(staging)
        snapshot = Maps(config, store).acquire(
            AreaInput(
                name="Synthetic demo — not a real walk",
                start={"lat": 28.6, "lon": 77.3},
                radius_meters=1500,
                public_start_confirmed=True,
            ),
            source,
        )
        store.put("snapshot", snapshot["id"], {**snapshot, "synthetic": True})
        store.put("profile", "active", {"interests": ["nature", "art"]})
        (staging / "demo.json").write_text(
            json.dumps(
                {
                    "scope": "Artificial map, coordinates and features; never use for navigation",
                    "outcomes": "No quests, visits, notes or accepted interests are pre-seeded",
                    "model": model,
                },
                indent=2,
            )
        )
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
