from fastapi import FastAPI

from app.db.engine import init_db
from app.api.routers.categories import router as categories_router
from app.api.routers.tickets import router as tickets_router
from app.api.routers.triage import router as triage_router

from app.agents.triage_agent import warmup_llm, close_llm_clients


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic Ticket Triage")

    @app.on_event("startup")
    async def _startup():
        init_db()
        await warmup_llm()

    @app.on_event("shutdown")
    async def _shutdown():
        await close_llm_clients()

    app.include_router(categories_router)
    app.include_router(tickets_router)
    app.include_router(triage_router)

    return app


app = create_app()
