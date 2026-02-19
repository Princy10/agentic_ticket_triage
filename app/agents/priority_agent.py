import os
import json
import httpx
import logging
from typing import List

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from app.domain.schemas import TicketPriority, TicketStatus
from app.agents.json_runner import run_json_agent

logger = logging.getLogger("priority_agent")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

_http_client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0))
_provider = OllamaProvider(base_url=OLLAMA_BASE_URL, http_client=_http_client)
_model = OpenAIChatModel(model_name=OLLAMA_MODEL, provider=_provider)


class PrioritySuggestion(BaseModel):
    priority: TicketPriority
    status: TicketStatus
    rationale: List[str] = Field(default_factory=list, description="2–4 raisons factuelles.")


_agent = Agent(
    _model,
    output_type=str,
    system_prompt=(
        "Tu es un agent de priorisation.\n"
        "Tu renvoies UNIQUEMENT un JSON objet valide.\n"
        "Clés EXACTES: priority, status, rationale.\n"
        "Règles:\n"
        "- priority ∈ LOW|MEDIUM|HIGH|URGENT.\n"
        "- status: ne proposer que OPEN ou IN_PROGRESS (jamais RESOLVED/CLOSED).\n"
        "- Si priority est HIGH ou URGENT -> status doit être IN_PROGRESS.\n"
        "- Si panne multi-utilisateurs/indisponibilité -> URGENT + IN_PROGRESS.\n"
        "- Si finance (double débit, remboursement) -> souvent URGENT + IN_PROGRESS.\n"
        "- rationale: 2–4 puces factuelles.\n"
    ),
)


async def prioritize_ticket(title: str, description: str, category_name: str) -> PrioritySuggestion:
    desc = (description or "")[:1500]
    prompt = (
        f"Catégorie déjà choisie: {json.dumps(category_name, ensure_ascii=False)}\n\n"
        f"Ticket:\nTitle: {title}\nDescription: {desc}\n"
    )
    return await run_json_agent(_agent, prompt, PrioritySuggestion, temperature=0.2, max_tokens=200)


async def close_client():
    await _http_client.aclose()
