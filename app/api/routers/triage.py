import os
import time
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import SessionDep
from app.services.ticket_service import get_ticket
from app.services.category_service import list_categories
from app.agents.triage_agent import suggest_triage, TriageParseError
from app.services.triage_policy import apply_guardrails

logger = logging.getLogger("triage_router")
router = APIRouter(prefix="/triage", tags=["Triage (LLM)"])

LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))


@router.post("/{ticket_id}/suggest")
async def triage_suggest(ticket_id: int, session: Session = Depends(SessionDep)):
    t0 = time.perf_counter()
    logger.info("triage_suggest start ticket_id=%s", ticket_id)

    ticket = get_ticket(session, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket introuvable")

    cats = list_categories(session)
    if not cats:
        raise HTTPException(status_code=400, detail="Aucune catégorie en base. Crée des catégories d'abord.")

    allowed_names = [c.name for c in cats]

    try:
        suggestion = await asyncio.wait_for(
            suggest_triage(ticket.title, ticket.description, allowed_names),
            timeout=LLM_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("LLM timeout after %ss (ticket_id=%s)", LLM_TIMEOUT_SECONDS, ticket_id)
        raise HTTPException(status_code=504, detail=f"Timeout LLM après {LLM_TIMEOUT_SECONDS}s.")
    except TriageParseError as e:
        logger.error("Triage parse error: %s", e)
        # On tronque pour éviter une réponse énorme
        raw = (e.raw_output or "")[:1200]
        raise HTTPException(status_code=422, detail={"message": str(e), "raw_output_preview": raw})
    except Exception as e:
        logger.exception("LLM error: %s", e)
        raise HTTPException(status_code=502, detail=f"Erreur LLM/Ollama: {e}")

    matched = next((c for c in cats if c.name == suggestion.category_name), None)
    if not matched:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "category_name hors liste exacte.",
                "allowed_categories": allowed_names,
                "got": suggestion.category_name,
            },
        )

    patch = {
        "category_id": matched.id,
        "priority": suggestion.priority.value,
        "status": suggestion.status.value,
    }
    name_to_id = {c.name: c.id for c in cats}
    patch = apply_guardrails(ticket, patch, category_name_to_id=name_to_id)

    logger.info("triage_suggest done in %.2fs", time.perf_counter() - t0)
    return {"ticket_id": ticket_id, "suggestion": suggestion.model_dump(), "patch_to_apply": patch}
