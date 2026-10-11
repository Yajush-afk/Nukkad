import time

import pytest

from nukkad.config import Config
from nukkad.domain import Record
from nukkad.ollama import ModelFailure


class PhotoChoice(Record):
    photo_id: str
    reason: str


def test_vision_adapter_checks_capability_before_sending_images(monkeypatch):
    import base64

    import httpx

    from nukkad.ollama import Ollama

    client_class = httpx.Client
    requests = []
    capable = False

    def handle(request):
        import json

        requests.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "local", "digest": "hash"}]})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "test-runtime"})
        if request.url.path == "/api/show":
            return httpx.Response(
                200, json={"capabilities": ["completion", "vision"] if capable else ["completion"]}
            )
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert base64.b64decode(payload["messages"][0]["images"][0]) == b"synthetic-image"
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {"photo_id": "photo", "reason": "Selection: A clear supplied scene."}
                    )
                }
            },
        )

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client_class(transport=transport, **kwargs)
    )
    model = Ollama(Config(model="local"))
    with pytest.raises(ModelFailure) as error:
        model.generate(
            PhotoChoice, "Select supplied photo", time.monotonic() + 10, images=[b"synthetic-image"]
        )
    assert error.value.category == "unsupported_capability" and "/api/chat" not in requests
    capable = True
    result, metrics = model.generate(
        PhotoChoice, "Select supplied photo", time.monotonic() + 10, images=[b"synthetic-image"]
    )
    assert result.photo_id == "photo" and metrics["digest"] == "hash"
