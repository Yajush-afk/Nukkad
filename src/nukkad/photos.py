"""Validated local photo storage. Originals are private; derived images have no metadata."""

import hashlib
import io
import re
import shutil
import threading

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from nukkad.storage import identity, now

router = APIRouter(prefix="/api")
MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def file_info(path, root):
    return {
        "path": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def safe_media_path(root, relative):
    if not isinstance(relative, str) or not re.fullmatch(
        r"(?:media/[0-9a-f]{32}/(?:original\.(?:jpg|png|webp)|display\.jpg|thumbnail\.jpg|inference\.jpg)|cards/location-[0-9a-f]{32}\.png)",
        relative,
    ):
        raise ValueError("Invalid media file identity")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("Unsafe media path")
    return path


def verified_media_path(root, metadata):
    path = safe_media_path(root, metadata["path"])
    if not path.is_file() or path.stat().st_size != metadata["size"]:
        raise ValueError("Saved media is missing or damaged; restore its backup")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != metadata["sha256"]:
        raise ValueError("Saved media is damaged; restore its backup")
    return path


def decode_photo(content):
    if not content or len(content) > MAX_BYTES:
        raise ValueError("Each photo must be at most 20 MiB")
    try:
        with Image.open(io.BytesIO(content)) as source:
            extension = FORMATS.get(source.format)
            if not extension:
                raise ValueError("Use JPEG, PNG or WebP photos")
            if source.width * source.height > MAX_PIXELS:
                raise ValueError("Each photo must be at most 40 megapixels")
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError("Animated images are not supported")
            source.load()
            oriented = ImageOps.exif_transpose(source).convert("RGBA")
            image = Image.new("RGB", oriented.size, "white")
            image.paste(oriented, mask=oriented.getchannel("A"))
            return image, extension
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("Photo is corrupted, unsupported or exceeds decoding limits") from error


def save_photo(config, store, key, content):
    experience = store.get("experience", key)
    if not experience or not experience["active"]:
        raise ValueError("Save a reached place visit before adding photos")
    digest = hashlib.sha256(content).hexdigest()
    photos = [
        item for item in store.list("photo") if item["experience_id"] == key and item["active"]
    ]
    duplicate = next((item for item in photos if item["original_sha256"] == digest), None)
    if duplicate:
        return duplicate
    if len(photos) >= 5:
        raise ValueError("A place visit can contain at most five active photos")
    image, extension = decode_photo(content)
    photo_id = identity()
    staging = config.data_dir / "staging" / photo_id
    final = config.data_dir / "media" / photo_id
    staging.mkdir(mode=0o700)
    published = False
    try:
        original = staging / f"original.{extension}"
        original.write_bytes(content)
        for variant, bound in (("display", 2048), ("thumbnail", 480), ("inference", 1024)):
            derived = image.copy()
            derived.thumbnail((bound, bound), Image.Resampling.LANCZOS)
            derived.save(staging / f"{variant}.jpg", "JPEG", quality=88)
        for path in staging.iterdir():
            path.chmod(0o600)
        staging.rename(final)
        item = {
            "id": photo_id,
            "record_version": 1,
            "experience_id": key,
            "place_id": experience["place_id"],
            "original_sha256": digest,
            "active": True,
            "width": image.width,
            "height": image.height,
            "created_at": now(),
            "files": {
                "original" if path.name.startswith("original") else path.stem: file_info(
                    path, config.data_dir
                )
                for path in final.iterdir()
            },
        }
        store.atomic(
            [
                *invalidation_records(store, key),
                ("photo", photo_id, item),
                ("experience", key, {**experience, "revision": identity(), "updated_at": now()}),
            ],
            [("experience", key, experience)],
        )
        published = True
        return item
    finally:
        image.close()
        if staging.exists():
            shutil.rmtree(staging)
        if not published and final.exists():
            shutil.rmtree(final)


def invalidation_records(store, key):
    return [
        ("location_card_version", card["id"], {**card, "stale": True})
        for card in store.list("location_card_version")
        if card["experience_id"] == key and not card.get("stale")
    ]


def media_inventory(store):
    files = {}
    for photo in store.list("photo"):
        for value in photo["files"].values():
            if value["path"] in files and files[value["path"]] != value:
                raise ValueError("Conflicting media metadata")
            files[value["path"]] = value
    for card in store.list("location_card_version"):
        if card.get("file"):
            files[card["file"]["path"]] = card["file"]
    return files


def media_recovery(config, store):
    live = media_inventory(store)
    missing = [name for name in live if not safe_media_path(config.data_dir, name).is_file()]
    staged = [path.name for path in (config.data_dir / "staging").iterdir()]
    orphans = [
        path.relative_to(config.data_dir).as_posix()
        for path in (config.data_dir / "media").glob("*/*")
        if path.relative_to(config.data_dir).as_posix() not in live
    ]
    orphans += [
        path.relative_to(config.data_dir).as_posix()
        for path in (config.data_dir / "cards").glob("location-*.png")
        if path.relative_to(config.data_dir).as_posix() not in live
    ]
    return {
        "missing_files": missing,
        "staged_entries": staged,
        "unreferenced_files": orphans,
        "action": "Inspect interrupted files before removal; live media is never deleted automatically",
    }


@router.post("/experiences/{key}/photos", status_code=201)
def upload_photo(key: str, request: Request, photo: UploadFile):
    content = photo.file.read(MAX_BYTES + 1)
    with request.app.state.media_lock:
        return save_photo(request.app.state.config, request.app.state.store, key, content)


@router.get("/experiences/{key}/photos")
def experience_photos(key: str, request: Request):
    return [
        item
        for item in request.app.state.store.list("photo")
        if item["experience_id"] == key and item["active"]
    ]


@router.delete("/photos/{key}")
def remove_photo(key: str, request: Request):
    store = request.app.state.store
    with request.app.state.media_lock:
        item = store.get("photo", key)
        if not item:
            raise HTTPException(404, "Unknown photo")
        if not item["active"]:
            return item
        experience = store.get("experience", item["experience_id"])
        updated = {**item, "active": False, "removed_at": now()}
        records = [
            ("photo", key, updated),
            (
                "experience",
                experience["id"],
                {**experience, "revision": identity(), "updated_at": now()},
            ),
        ]
        store.atomic(
            [*records, *invalidation_records(store, experience["id"])],
            [("photo", key, item), ("experience", experience["id"], experience)],
        )
        return updated


@router.get("/photos/{key}/{variant}")
def photo_file(key: str, variant: str, request: Request):
    item = request.app.state.store.get("photo", key)
    # Originals are deliberately excluded from the web interface.
    if not item or variant not in {"display", "thumbnail", "inference"}:
        raise HTTPException(404, "Unknown display photo")
    path = verified_media_path(request.app.state.config.data_dir, item["files"][variant])
    if not path.is_file():
        raise HTTPException(404, "Saved image is missing; restore its backup")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/media/recovery")
def recovery(request: Request):
    return media_recovery(request.app.state.config, request.app.state.store)


def install_media(app):
    app.state.media_lock = threading.RLock()
    app.include_router(router)
