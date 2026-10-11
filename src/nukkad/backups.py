"""Consistent, bounded backups with a versioned manifest for local media."""

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from nukkad.config import Config
from nukkad.photos import media_inventory, safe_media_path
from nukkad.storage import Store, identity

DEFAULT_LIMIT = 4 * 1024**3


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_member(name):
    path = PurePosixPath(name)
    return (
        len(path.parts) == 3
        and path.parts[0] == "snapshots"
        and len(path.parts[1]) == 32
        and all(c in "0123456789abcdef" for c in path.parts[1])
        and path.parts[2] in {"source.osm", "walking.graphml"}
    )


def validate_references(store):
    experiences = {item["id"]: item for item in store.list("experience")}
    photos = {item["id"]: item for item in store.list("photo")}
    for item in experiences.values():
        outcome = store.get("outcome", item["outcome_id"])
        if not outcome or item["stop_id"] not in {stop["id"] for stop in outcome["stops"]}:
            raise ValueError("Backup place experience has an invalid outcome reference")
    for item in photos.values():
        if item["experience_id"] not in experiences or item.get("record_version") != 1:
            raise ValueError("Backup photo has an invalid experience or record version")
        if set(item["files"]) != {"original", "display", "thumbnail", "inference"}:
            raise ValueError("Backup photo is missing a required variant")
        if any(
            not value["path"].startswith(f"media/{item['id']}/") for value in item["files"].values()
        ):
            raise ValueError("Backup photo files belong to another identity")
        if item["files"]["original"]["sha256"] != item["original_sha256"]:
            raise ValueError("Backup original photo fingerprint is inconsistent")
    versions = {item["id"]: item for item in store.list("location_card_version")}
    for item in versions.values():
        if (
            item["experience_id"] not in experiences
            or item.get("photo_id") not in photos
            or photos[item["photo_id"]]["experience_id"] != item["experience_id"]
        ):
            raise ValueError("Backup card has an invalid source or cover photo")
    for pointer in store.list("location_card"):
        if pointer["version_id"] not in versions:
            raise ValueError("Backup card pointer has no saved version")


def backup(config: Config, max_bytes=None) -> Path:
    limit = max_bytes if max_bytes is not None else config.backup_limit_bytes
    if limit <= 0:
        raise ValueError("Backup limit must be positive")
    config.prepare()
    store = Store(config.data_dir)
    destination = config.data_dir / "backups" / f"nukkad-{identity()}.zip"
    try:
        with tempfile.TemporaryDirectory(dir=config.data_dir) as folder:
            copied = Path(folder) / "nukkad.sqlite3"
            with store.connect() as source, sqlite3.connect(copied) as target:
                source.backup(target)
            frozen = Store(Path(folder))
            validate_references(frozen)
            files = {"nukkad.sqlite3": copied}
            for snapshot in frozen.list("snapshot"):
                for name in ("source.osm", "walking.graphml"):
                    member = f"snapshots/{snapshot['id']}/{name}"
                    if not snapshot_member(member):
                        raise ValueError("Invalid snapshot identity")
                    files[member] = config.data_dir / member
            media = media_inventory(frozen)
            for relative, expected in media.items():
                path = safe_media_path(config.data_dir, relative)
                if (
                    not path.is_file()
                    or path.stat().st_size != expected["size"]
                    or digest_file(path) != expected["sha256"]
                ):
                    raise ValueError("Saved media is missing or damaged; repair before backup")
                files[relative] = path
            if any(not path.is_file() for path in files.values()):
                raise ValueError("Snapshot files are missing; repair before backup")
            manifest = {
                "version": 2,
                "files": {
                    name: {"size": path.stat().st_size, "sha256": digest_file(path)}
                    for name, path in files.items()
                },
            }
            encoded = json.dumps(manifest, sort_keys=True).encode()
            if sum(path.stat().st_size for path in files.values()) + len(encoded) > limit:
                raise ValueError(
                    "Backup exceeds configured uncompressed size limit; explicitly increase the same limit for backup and restore"
                )
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", encoded)
                for name, path in files.items():
                    archive.write(path, name)
        destination.chmod(0o600)
        return destination
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def restore(archive_path: Path, destination: Path, max_bytes=DEFAULT_LIMIT) -> Path:
    if max_bytes <= 0:
        raise ValueError("Restore limit must be positive")
    if destination.exists():
        raise ValueError(
            "Restore requires a new directory; your current data will not be overwritten"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="nukkad-restore-", dir=destination.parent))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if sum(item.file_size for item in entries) > max_bytes:
                raise ValueError("Backup exceeds configured uncompressed size limit")
            seen = set()
            for item in entries:
                path = PurePosixPath(item.filename)
                allowed = item.filename in {"nukkad.sqlite3", "manifest.json"} or snapshot_member(
                    item.filename
                )
                if not allowed:
                    try:
                        safe_media_path(staging, item.filename)
                        allowed = True
                    except ValueError:
                        pass
                if (
                    not allowed
                    or item.filename in seen
                    or path.is_absolute()
                    or ".." in path.parts
                    or item.external_attr >> 16 & 0o170000 == 0o120000
                ):
                    raise ValueError("Unexpected or unsafe backup member")
                seen.add(item.filename)
                target = staging.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with archive.open(item) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o600)
        manifest_path = staging / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("version") != 2 or set(manifest.get("files", {})) != seen - {
                "manifest.json"
            }:
                raise ValueError("Backup manifest version or declared files do not match")
            for name, expected in manifest["files"].items():
                path = staging / name
                if (
                    path.stat().st_size != expected["size"]
                    or digest_file(path) != expected["sha256"]
                ):
                    raise ValueError("Backup file hash or size does not match manifest")
        elif any(name.startswith(("media/", "cards/")) for name in seen):
            raise ValueError("Media backups require a versioned manifest")
        database_path = staging / "nukkad.sqlite3"
        if not database_path.is_file():
            raise ValueError("Backup has no database")
        with sqlite3.connect(database_path) as database:
            if (
                database.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or database.execute("PRAGMA user_version").fetchone()[0] != 1
            ):
                raise ValueError("Backup database integrity or version is unsupported")
        frozen = Store(staging)
        validate_references(frozen)
        for snapshot in frozen.list("snapshot"):
            graph_name = f"snapshots/{snapshot['id']}/walking.graphml"
            source_name = f"snapshots/{snapshot['id']}/source.osm"
            if (
                not snapshot_member(graph_name)
                or graph_name not in seen
                or source_name not in seen
                or digest_file(staging / graph_name) != snapshot["graph_fingerprint"]
            ):
                raise ValueError("Backup snapshot graph or source is missing or damaged")
        referenced = media_inventory(frozen)
        declared_media = {name for name in seen if name.startswith(("media/", "cards/"))}
        if set(referenced) != declared_media:
            raise ValueError("Backup media files and database references do not match")
        for name, expected in referenced.items():
            path = safe_media_path(staging, name)
            if path.stat().st_size != expected["size"] or digest_file(path) != expected["sha256"]:
                raise ValueError("Backup media fingerprint is invalid")
        manifest_path.unlink(missing_ok=True)
        staging.chmod(0o700)
        staging.rename(destination)
        Config(data_dir=destination).prepare()
        return destination
    except (KeyError, TypeError, json.JSONDecodeError, sqlite3.Error) as error:
        raise ValueError("Backup manifest or records are invalid") from error
    finally:
        if staging.exists():
            shutil.rmtree(staging)
