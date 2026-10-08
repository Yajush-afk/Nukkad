from fastapi import FastAPI

from nukkad.config import Config
from nukkad.ollama import Ollama


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    config.prepare()
    app = FastAPI(title="Nukkad")
    app.state.config = config

    @app.get("/api/readiness")
    def readiness():
        try:
            models = Ollama(config).models()
            model_names = [model["name"] for model in models]
            model_status = "ready" if config.model in model_names else "missing"
        except Exception:
            model_names, model_status = [], "unavailable"
        return {
            "application": "ready",
            "model_status": model_status,
            "models": model_names,
            "selected_model": config.model,
        }

    return app
