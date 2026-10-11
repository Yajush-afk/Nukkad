import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from nukkad.app import create_app
from nukkad.outcomes import Outcome, save_outcome
from nukkad.photos import decode_photo, media_recovery, save_photo


def png(colour="green", size=(30, 20)):
    output = io.BytesIO()
    Image.new("RGB", size, colour).save(output, "PNG")
    return output.getvalue()


def visit(registry, key="walk", note="I enjoyed the tree outlines."):
    maps, store, snapshot = registry[:3]
    quest = {
        "id": key,
        "status": "accepted",
        "snapshot_id": snapshot["id"],
        "stops": [{"id": "osm-way-20", "name": "Sample park"}],
    }
    store.put("quest", key, quest)
    value = Outcome(
        status="completed",
        note="Overall note",
        stops=[{"id": "osm-way-20", "status": "reached"}],
        place_experiences=[{"stop_id": "osm-way-20", "note": note}],
    )
    save_outcome(store, quest, value)
    return store.list("experience")[0], quest, value


def test_place_experience_updates_without_duplicate_visits(registry):
    experience, quest, value = visit(registry)
    store = registry[1]
    save_outcome(store, quest, value)
    assert len(store.list("experience")) == 1
    assert store.list("experience")[0] == experience
    value.place_experiences[0].note = "Edited place note"
    save_outcome(store, quest, value)
    current = store.get("experience", experience["id"])
    assert current["original_note"] == experience["note"]
    assert current["revisions"][0]["note"] == experience["note"]
    value.stops[0].status = "skipped"
    save_outcome(store, quest, value)
    assert not store.get("experience", experience["id"])["active"]
    assert store.get("outcome", quest["id"])["original_note"] == "Overall note"


def test_five_photos_duplicates_and_private_originals(registry):
    experience, _, _ = visit(registry)
    config, store = registry[0].config, registry[1]
    first = save_photo(config, store, experience["id"], png())
    assert save_photo(config, store, experience["id"], png())["id"] == first["id"]
    for colour in ("red", "blue", "yellow", "purple"):
        save_photo(config, store, experience["id"], png(colour))
    with pytest.raises(ValueError, match="five"):
        save_photo(config, store, experience["id"], png("orange"))
    with TestClient(create_app(config), base_url="http://127.0.0.1") as client:
        assert client.get(f"/api/photos/{first['id']}/original").status_code == 404
        assert client.get(f"/api/photos/{first['id']}/display").status_code == 200
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        assert client.delete(f"/api/photos/{first['id']}").status_code == 200
        uploaded = client.post(
            f"/api/experiences/{experience['id']}/photos",
            files={"photo": ("fake.txt", png("orange"), "text/plain")},
        )
        assert uploaded.status_code == 201  # Decoded content, not extension/content-type, decides.
    assert len([item for item in store.list("photo") if item["active"]]) == 5
    assert media_recovery(config, store)["missing_files"] == []


def test_corruption_animation_and_resolution_are_rejected():
    with pytest.raises(ValueError, match="corrupted"):
        decode_photo(b"not an image")
    with pytest.raises(ValueError, match="20 MiB"):
        decode_photo(b"x" * (20 * 1024 * 1024 + 1))
    animation = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(
        animation, "PNG", save_all=True, append_images=[Image.new("RGB", (10, 10), "blue")]
    )
    with pytest.raises(ValueError, match="Animated"):
        decode_photo(animation.getvalue())
    with pytest.raises(ValueError, match="40 megapixels"):
        decode_photo(png(size=(8001, 5000)))


def test_rotation_and_derived_metadata_removal(registry):
    experience, _, _ = visit(registry)
    output = io.BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "private original metadata"
    Image.new("RGB", (30, 20), "red").save(output, "JPEG", exif=exif)
    item = save_photo(registry[0].config, registry[1], experience["id"], output.getvalue())
    root = registry[0].config.data_dir
    assert (item["width"], item["height"]) == (20, 30)
    with Image.open(root / item["files"]["original"]["path"]) as original:
        assert original.getexif()[270] == "private original metadata"
    for variant in ("thumbnail", "display", "inference"):
        with Image.open(root / item["files"][variant]["path"]) as image:
            assert not image.getexif()
            assert (
                max(image.size) <= {"thumbnail": 480, "display": 2048, "inference": 1024}[variant]
            )


def test_interrupted_upload_never_publishes_missing_files(registry, monkeypatch):
    experience, _, _ = visit(registry)
    store, config = registry[1], registry[0].config

    def fail(*args, **kwargs):
        raise ValueError("Source changed")

    monkeypatch.setattr(store, "atomic", fail)
    with pytest.raises(ValueError, match="changed"):
        save_photo(config, store, experience["id"], png())
    assert store.list("photo") == []
    assert list((config.data_dir / "media").iterdir()) == []
    assert list((config.data_dir / "staging").iterdir()) == []


def test_media_backup_restore_manifest_and_size_limits(registry, tmp_path):
    import zipfile

    from nukkad.backups import backup, restore
    from nukkad.storage import Store

    experience, _, _ = visit(registry)
    config, store = registry[0].config, registry[1]
    photo = save_photo(config, store, experience["id"], png())
    archive = backup(config)
    destination = tmp_path / "media-restored"
    restore(archive, destination)
    restored = Store(destination)
    assert restored.get("photo", photo["id"]) == photo
    assert (destination / photo["files"]["original"]["path"]).read_bytes() == png()
    with pytest.raises(ValueError, match="limit"):
        backup(config, max_bytes=10)
    with pytest.raises(ValueError, match="limit"):
        restore(archive, tmp_path / "too-small", max_bytes=10)
    damaged = tmp_path / "damaged.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(damaged, "w") as output:
        for name in source.namelist():
            output.writestr(
                name, b"damaged" if name == photo["files"]["display"]["path"] else source.read(name)
            )
    with pytest.raises(ValueError, match="hash or size"):
        restore(damaged, tmp_path / "damaged-restore")
    assert not (tmp_path / "damaged-restore").exists()
    legacy = tmp_path / "old-backup.zip"
    # Legacy archives without media remain supported.
    empty = registry[0].config.data_dir / "legacy"
    from nukkad.config import Config

    old_config = Config(data_dir=empty)
    fresh = backup(old_config)
    with zipfile.ZipFile(fresh) as source, zipfile.ZipFile(legacy, "w") as output:
        for name in source.namelist():
            if name != "manifest.json":
                output.writestr(name, source.read(name))
    restore(legacy, tmp_path / "old-restored")


def test_repeated_visits_and_aliases_preserve_place_identity(registry):
    from nukkad.identities import canonical_id

    first, _, _ = visit(registry)
    second, _, _ = visit(registry, "walk-2")
    assert first["id"] != second["id"]
    assert first["place_id"] == second["place_id"]
    registry[1].put("place_alias", first["place_id"], {"canonical_id": "reviewed-place"})
    assert {
        canonical_id(registry[1], item["place_id"]) for item in registry[1].list("experience")
    } == {"reviewed-place"}
