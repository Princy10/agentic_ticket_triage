from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db.engine import init_db
from app.api.routers.categories import router as categories_router
from app.api.routers.tickets import router as tickets_router
from app.api.routers.triage import router as triage_router

from app.agents.triage_agent import warmup_llm, close_llm_clients
from app.mcp.server import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    await warmup_llm()

    # MCP session manager
    async with mcp.session_manager.run():
        try:
            yield
        finally:
            # Shutdown
            await close_llm_clients()


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic Ticket Triage", lifespan=lifespan)

    app.include_router(categories_router)
    app.include_router(tickets_router)
    app.include_router(triage_router)

    # MCP accessible sur http://localhost:8000/mcp
    app.mount("/mcp", mcp.streamable_http_app())

    return app


app = create_app()
