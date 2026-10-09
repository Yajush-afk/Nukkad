"""Serve the offline interface and keep its form contracts intact."""

import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from nukkad.app import create_app
from nukkad.config import Config


class Interface(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.form = None
        self.fields = {}
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "form":
            self.form = attrs["id"]
            self.fields[self.form] = set()
        if tag in {"input", "select", "textarea"} and self.form and "name" in attrs:
            self.fields[self.form].add(attrs["name"])
        if tag == "img":
            self.images.append(attrs)

    def handle_endtag(self, tag):
        if tag == "form":
            self.form = None


def test_interface_serves_both_local_logos_and_script_targets(tmp_path):
    with TestClient(create_app(Config(data_dir=tmp_path)), base_url="http://127.0.0.1") as client:
        response = client.get("/")
        assert response.status_code == 200
        page = Interface()
        page.feed(response.text)
        assert len(page.ids) == len(set(page.ids))
        script = client.get("/static/app.js")
        assert script.status_code == 200
        assert set(re.findall(r'\$\("([\w-]+)"\)', script.text)) <= set(page.ids)
        logos = [item for item in page.images if "/brand/" in item.get("src", "")]
        assert {item["src"] for item in logos} == {
            "/static/brand/nukkad-light.png",
            "/static/brand/nukkad-dark.png",
        }
        for logo in logos:
            assert logo["alt"]
            assert logo["width"] and logo["height"]
            asset = client.get(logo["src"])
            assert asset.status_code == 200
            assert asset.headers["content-type"] == "image/png"
            assert asset.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert 'href="#main"' in response.text
        assert 'aria-label="Main navigation"' in response.text
        assert not re.search(r'(?:src|href)="https?://', response.text)


def test_grouped_forms_keep_existing_api_fields():
    page = Interface()
    static = Path(__file__).parents[1] / "src" / "nukkad" / "static"
    page.feed((static / "index.html").read_text())
    assert page.fields["area-form"] == {
        "name",
        "lat",
        "lon",
        "timezone",
        "radius_meters",
        "public_start_confirmed",
        "extract",
    }
    assert page.fields["pin-form"] == {"name", "kind", "lat", "lon", "descriptor", "confirmed"}
    assert page.fields["quest-form"] == {"minutes", "mode", "state"}
    assert page.fields["settings-form"] == {
        "model",
        "walking_kmh",
        "stop_minutes",
        "reserve_minutes",
        "max_distance_meters",
        "max_stops",
        "sunset_margin_minutes",
        "daylight_required",
        "tone",
        "air_quality_enabled",
        "air_quality_threshold",
    }
    assert page.fields["outcome-form"] == {
        "status",
        "actual_minutes",
        "screen_minutes",
        "note",
        "reason",
    }
