import os
import json
import httpx
import logging
from typing import List

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from app.agents.json_runner import run_json_agent

logger = logging.getLogger("classify_agent")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

_http_client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0))
_provider = OllamaProvider(base_url=OLLAMA_BASE_URL, http_client=_http_client)
_model = OpenAIChatModel(model_name=OLLAMA_MODEL, provider=_provider)


class CategorySuggestion(BaseModel):
    category_name: str = Field(..., description="Exactement l'une des catégories autorisées.")
    summary: str = Field(..., description="Résumé court (1–2 phrases).")
    rationale: List[str] = Field(default_factory=list, description="2–4 raisons factuelles.")


_agent = Agent(
    _model,
    output_type=str,
    system_prompt=(
        "Tu es un agent de classification de tickets.\n"
        "Tu renvoies UNIQUEMENT un JSON objet valide.\n"
        "Clés EXACTES: category_name, summary, rationale.\n"
        "Règles:\n"
        "- category_name doit être EXACTEMENT une valeur de la liste fournie.\n"
        "- Évite 'Incident' sauf panne/indisponibilité globale.\n"
        "- Si 401/403/forbidden/permission/role -> Access.\n"
        "- Si CSV/export/encodage/séparateur/colonnes -> Data.\n"
        "- summary: 1–2 phrases.\n"
        "- rationale: 2–4 puces factuelles.\n"
    ),
)


async def classify_ticket(title: str, description: str, allowed_categories: List[str]) -> CategorySuggestion:
    allowed = json.dumps(allowed_categories, ensure_ascii=False)
    desc = (description or "")[:1500]

    prompt = (
        f"Catégories autorisées (liste stricte): {allowed}\n\n"
        f"Ticket:\nTitle: {title}\nDescription: {desc}\n"
    )

    return await run_json_agent(_agent, prompt, CategorySuggestion, temperature=0.2, max_tokens=240)


async def close_client():
    await _http_client.aclose()
