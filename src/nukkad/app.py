from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nukkad.air_quality import router as air_router
from nukkad.areas_api import router as areas_router
from nukkad.cards import router as cards_router
from nukkad.config import Config
from nukkad.jobs import Busy, Jobs
from nukkad.memory import router as memory_router
from nukkad.ollama import Ollama
from nukkad.outcomes import router as outcomes_router
from nukkad.planning import Settings
from nukkad.planning_api import router as planning_router
from nukkad.quests_api import router as quests_router
from nukkad.security import install_security
from nukkad.storage import Store


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    config.prepare()
    store = Store(config.data_dir)
    jobs = Jobs(store)

    @asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()

    app = FastAPI(title="Nukkad", lifespan=lifespan)
    app.state.config = config
    app.state.store = store
    app.state.jobs = jobs
    app.include_router(areas_router)
    app.include_router(planning_router)
    app.include_router(quests_router)
    app.include_router(cards_router)
    app.include_router(outcomes_router)
    app.include_router(memory_router)
    app.include_router(air_router)
    install_security(app)
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def home():
        return FileResponse(static / "index.html")

    @app.exception_handler(ValueError)
    async def invalid_input(request: Request, error: ValueError):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.exception_handler(Busy)
    async def busy(request: Request, error: Busy):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.get("/api/readiness")
    def readiness():
        selected = Settings.model_validate(
            store.get("settings", "active") or {"model": config.model}
        ).model
        try:
            models = Ollama(replace(config, model=selected)).models()
            model_names = [model["name"] for model in models]
            model_status = "ready" if selected in model_names else "missing"
        except Exception:
            model_names, model_status = [], "unavailable"
        return {
            "application": "ready",
            "model_status": model_status,
            "models": model_names,
            "selected_model": selected,
            "database": "ready",
            "area_ready": store.get("area", "active") is not None,
        }

    return app
