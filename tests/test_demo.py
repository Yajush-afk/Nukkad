import pytest

from nukkad.config import Config
from nukkad.demo import prepare_demo
from nukkad.maps import Maps
from nukkad.places import seek_features
from nukkad.storage import Store


def test_demo_is_isolated_and_has_no_fabricated_history(tmp_path, monkeypatch):
    original = tmp_path / "personal"
    original.mkdir()
    sentinel = original / "keep.txt"
    sentinel.write_text("personal data")
    monkeypatch.setenv("NUKKAD_DATA_DIR", str(original))
    destination = tmp_path / "demo"
    assert prepare_demo(destination, "gemma4:e2b") == destination
    store = Store(destination)
    registry = Maps(Config(data_dir=destination), store)
    assert registry.snapshot()["area"]["name"].startswith("Synthetic demo")
    assert registry.snapshot()["synthetic"] is True
    assert len(registry.places()) == 8
    assert sum(bool(seek_features(place)) for place in registry.places()) == 2
    for kind in ("quest", "outcome", "journal", "interest"):
        assert store.list(kind) == []
    assert sentinel.read_text() == "personal data"
    with pytest.raises(ValueError, match="new directory"):
        prepare_demo(destination, "gemma4:e2b")
