import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from nukkad.config import Config
from nukkad.storage import Store, identity


def backup(config: Config) -> Path:
    config.prepare()
    store = Store(config.data_dir)
    destination = config.data_dir / "backups" / f"nukkad-{identity()}.zip"
    with tempfile.TemporaryDirectory(dir=config.data_dir) as folder:
        copied = Path(folder) / "nukkad.sqlite3"
        with store.connect() as source, sqlite3.connect(copied) as target:
            source.backup(target)
        with sqlite3.connect(copied) as database:
            snapshots = [
                json.loads(row[0])
                for row in database.execute("SELECT data FROM records WHERE kind='snapshot'")
            ]
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(copied, "nukkad.sqlite3")
            for snapshot in snapshots:
                root = config.data_dir / "snapshots" / snapshot["id"]
                for name in ("source.osm", "walking.graphml"):
                    if not (root / name).is_file():
                        raise ValueError("Snapshot files are missing; repair before backup")
                    archive.write(root / name, f"snapshots/{snapshot['id']}/{name}")
    destination.chmod(0o600)
    return destination


def restore(archive_path: Path, destination: Path) -> Path:
    if destination.exists():
        raise ValueError(
            "Restore requires a new directory; your current data will not be overwritten"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="nukkad-restore-", dir=destination.parent))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            if sum(item.file_size for item in archive.infolist()) > 256 * 1024 * 1024:
                raise ValueError("Backup exceeds the 256 MiB restore limit")
            seen = set()
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                allowed = (
                    item.filename == "nukkad.sqlite3"
                    or len(path.parts) == 3
                    and path.parts[0] == "snapshots"
                    and len(path.parts[1]) == 32
                    and all(c in "0123456789abcdef" for c in path.parts[1])
                    and path.parts[2] in {"source.osm", "walking.graphml"}
                )
                if not allowed or item.filename in seen or path.is_absolute() or ".." in path.parts:
                    raise ValueError("Unexpected or unsafe backup member")
                seen.add(item.filename)
                target = staging.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o600)
        database_path = staging / "nukkad.sqlite3"
        if not database_path.is_file():
            raise ValueError("Backup has no database")
        with sqlite3.connect(database_path) as database:
            if (
                database.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or database.execute("PRAGMA user_version").fetchone()[0] != 1
            ):
                raise ValueError("Backup database integrity or version is unsupported")
            for row in database.execute("SELECT data FROM records WHERE kind='snapshot'"):
                snapshot = json.loads(row[0])
                if (
                    not isinstance(snapshot.get("id"), str)
                    or len(snapshot["id"]) != 32
                    or any(c not in "0123456789abcdef" for c in snapshot["id"])
                ):
                    raise ValueError("Invalid snapshot identity")
                graph = staging / "snapshots" / snapshot["id"] / "walking.graphml"
                if (
                    not graph.is_file()
                    or hashlib.sha256(graph.read_bytes()).hexdigest()
                    != snapshot["graph_fingerprint"]
                ):
                    raise ValueError("Backup snapshot graph is missing or damaged")
        staging.chmod(0o700)
        staging.rename(destination)
        Config(data_dir=destination).prepare()
        return destination
    finally:
        if staging.exists():
            shutil.rmtree(staging)
