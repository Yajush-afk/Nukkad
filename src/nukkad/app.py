from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nukkad.air_quality import router as air_router
from nukkad.areas_api import router as areas_router
from nukkad.cards import router as cards_router
from nukkad.config import Config
from nukkad.geocoding import router as geocoding_router
from nukkad.jobs import Busy, Jobs
from nukkad.location_cards import router as location_router
from nukkad.memory import router as memory_router
from nukkad.outcomes import router as outcomes_router
from nukkad.photos import install_media
from nukkad.planning_api import router as planning_router
from nukkad.quests_api import router as quests_router
from nukkad.runtime_lock import RuntimeLock
from nukkad.security import install_security
from nukkad.storage import SourceChanged, Store
from nukkad.suggestions import install as install_suggestions


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    config.prepare()
    store = Store(config.data_dir)
    runtime = RuntimeLock(config.data_dir)

    @asynccontextmanager
    async def lifespan(app):
        runtime.acquire()
        app.state.jobs = Jobs(store)
        try:
            yield
        finally:
            app.state.jobs.close()
            runtime.release()

    app = FastAPI(title="Nukkad", lifespan=lifespan)
    app.state.config = config
    app.state.store = store
    app.include_router(areas_router)
    app.include_router(geocoding_router)
    install_suggestions(app)
    app.include_router(planning_router)
    app.include_router(quests_router)
    app.include_router(cards_router)
    app.include_router(outcomes_router)
    app.include_router(memory_router)
    app.include_router(location_router)
    app.include_router(air_router)
    install_media(app)
    install_security(app)
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def home():
        return FileResponse(static / "index.html")

    @app.exception_handler(SourceChanged)
    async def stale_source(request: Request, error: SourceChanged):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid_input(request: Request, error: ValueError):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.exception_handler(Busy)
    async def busy(request: Request, error: Busy):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.get("/api/readiness")
    def readiness():
        from nukkad.readiness import check_readiness

        return check_readiness(app)

    return app
