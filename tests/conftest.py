import pytest
from test_maps import XML

from nukkad.config import Config
from nukkad.maps import Maps
from nukkad.places import AreaInput
from nukkad.storage import Store


@pytest.fixture
def registry(tmp_path):
    config = Config(data_dir=tmp_path)
    config.prepare()
    store = Store(tmp_path)
    source = tmp_path / "fixture.osm"
    source.write_text(XML)
    maps = Maps(config, store)
    area = AreaInput(
        name="Synthetic area",
        start={"lat": 28.639, "lon": 77.360},
        radius_meters=500,
        public_start_confirmed=True,
    )
    snapshot = maps.acquire(area, source)
    return maps, store, snapshot, area, source
