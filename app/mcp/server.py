from __future__ import annotations

import json
from typing import Optional, Any, Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from sqlmodel import Session, select

from app.db.engine import engine
from app.domain.schemas import TicketPriority, TicketStatus, McpTriageResult
from app.domain.models import Ticket, Category

from app.agents.triage_agent import suggest_triage
from app.services.triage_policy import apply_guardrails


# Streamable HTTP + stateless + JSON response (scalable)
mcp = FastMCP(
    name="Agentic Ticket Triage",
    stateless_http=True,
    json_response=True,
    instructions=(
        "Serveur MCP exposant des tools CRUD Tickets/Categories et un tool de triage LLM "
        "(Ollama/PydanticAI)."
    ),
)

mcp.settings.streamable_http_path = "/"


def _session() -> Session:
    return Session(engine)


@mcp.tool()
def list_categories() -> list[dict[str, Any]]:
    """Lister les catégories."""
    with _session() as s:
        cats = s.exec(select(Category).order_by(Category.id)).all()
        return [{"id": c.id, "name": c.name, "description": c.description} for c in cats]


@mcp.tool()
def list_tickets(
    limit: int = 20,
    offset: int = 0,
    status: Optional[TicketStatus] = None,
    priority: Optional[TicketPriority] = None,
    category_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Lister les tickets (filtrable)."""
    with _session() as s:
        q = select(Ticket).order_by(Ticket.id).offset(offset).limit(limit)
        if status is not None:
            q = q.where(Ticket.status == status.value)
        if priority is not None:
            q = q.where(Ticket.priority == priority.value)
        if category_id is not None:
            q = q.where(Ticket.category_id == category_id)
        rows = s.exec(q).all()
        return [t.model_dump() for t in rows]


@mcp.tool()
def get_ticket(ticket_id: int) -> dict[str, Any]:
    """Récupérer un ticket par id."""
    with _session() as s:
        t = s.get(Ticket, ticket_id)
        if not t:
            return {"error": "Ticket introuvable", "ticket_id": ticket_id}
        return t.model_dump()


@mcp.tool()
def create_ticket(
    title: str,
    description: str,
    priority: TicketPriority = TicketPriority.MEDIUM,
    status: TicketStatus = TicketStatus.OPEN,
    category_id: Optional[int] = None,
) -> dict[str, Any]:
    """Créer un ticket."""
    with _session() as s:
        t = Ticket(
            title=title,
            description=description,
            priority=priority.value,
            status=status.value,
            category_id=category_id,
        )
        s.add(t)
        s.commit()
        s.refresh(t)
        return t.model_dump()


@mcp.tool()
def update_ticket(
    ticket_id: int,
    priority: Optional[TicketPriority] = None,
    status: Optional[TicketStatus] = None,
    category_id: Optional[int] = None,
) -> dict[str, Any]:
    """Mettre à jour un ticket (patch simple)."""
    with _session() as s:
        t = s.get(Ticket, ticket_id)
        if not t:
            return {"error": "Ticket introuvable", "ticket_id": ticket_id}

        if priority is not None:
            t.priority = priority.value
        if status is not None:
            t.status = status.value
        if category_id is not None:
            t.category_id = category_id

        s.add(t)
        s.commit()
        s.refresh(t)
        return t.model_dump()


@mcp.tool()
async def triage_suggest(ticket_id: int) -> Annotated[CallToolResult, McpTriageResult]:
    with Session(engine) as s:
        t = s.get(Ticket, ticket_id)
        if not t:
            structured = {"ticket_id": ticket_id, "error": "Ticket introuvable"}
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(structured, ensure_ascii=False))],
                structuredContent=structured,
                isError=True,
            )

        cats = s.exec(select(Category).order_by(Category.id)).all()
        allowed_names = [c.name for c in cats]

        suggestion = await suggest_triage(t.title, t.description, allowed_names)

        matched = next((c for c in cats if c.name == suggestion.category_name), None)
        if not matched:
            structured = {
                "ticket_id": ticket_id,
                "error": "category_name hors liste exacte",
                "allowed_categories": allowed_names,
                "got": suggestion.category_name,
            }
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(structured, ensure_ascii=False))],
                structuredContent=structured,
                isError=True,
            )

        patch = {
            "category_id": matched.id,
            "priority": suggestion.priority.value,
            "status": suggestion.status.value,
        }
        name_to_id = {c.name: c.id for c in cats}
        patch = apply_guardrails(t, patch, category_name_to_id=name_to_id)

        structured = {
            "ticket_id": ticket_id,
            "suggestion": suggestion.model_dump(),
            "patch_to_apply": patch,
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(structured, ensure_ascii=False))],
            structuredContent=structured,
        )