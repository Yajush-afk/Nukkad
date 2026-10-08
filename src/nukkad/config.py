import os
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_data_path


@dataclass(frozen=True)
class Config:
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("NUKKAD_DATA_DIR", user_data_path("nukkad")))
    )
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "gemma3:4b-it-q4_K_M"

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in ("snapshots", "cards", "benchmarks", "backups"):
            (self.data_dir / name).mkdir(exist_ok=True, mode=0o700)
