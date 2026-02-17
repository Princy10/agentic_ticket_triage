from fastapi import FastAPI

from app.db.engine import init_db
from app.api.routers.categories import router as categories_router
from app.api.routers.tickets import router as tickets_router


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic Ticket Triage")

    @app.on_event("startup")
    def _startup():
        init_db()

    app.include_router(categories_router)
    app.include_router(tickets_router)

    return app


app = create_app()
