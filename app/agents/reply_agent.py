import os
import json
import httpx
import logging
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from app.domain.schemas import TicketPriority
from app.agents.json_runner import run_json_agent

logger = logging.getLogger("reply_agent")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

_http_client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0))
_provider = OllamaProvider(base_url=OLLAMA_BASE_URL, http_client=_http_client)
_model = OpenAIChatModel(model_name=OLLAMA_MODEL, provider=_provider)


class ReplySuggestion(BaseModel):
    draft_reply: Optional[str] = Field(default=None, description="Réponse courte au client, ou null si inutile.")


_agent = Agent(
    _model,
    output_type=str,
    system_prompt=(
        "Tu es un agent de rédaction de réponse support.\n"
        "Tu renvoies UNIQUEMENT un JSON objet valide.\n"
        "Clé EXACTE: draft_reply.\n"
        "Règles:\n"
        "- draft_reply: 1–3 phrases pro, ton clair.\n"
        "- Si priorité HIGH ou URGENT, essaye de fournir une réponse.\n"
        "- Si ticket purement interne/informatif, tu peux mettre null.\n"
        "- Pas de promesse de délai exact.\n"
    ),
)


async def draft_reply(title: str, description: str, category_name: str, priority: TicketPriority) -> ReplySuggestion:
    desc = (description or "")[:1500]
    prompt = (
        f"Contexte:\n"
        f"- category_name: {json.dumps(category_name, ensure_ascii=False)}\n"
        f"- priority: {priority.value}\n\n"
        f"Ticket:\nTitle: {title}\nDescription: {desc}\n"
    )
    return await run_json_agent(_agent, prompt, ReplySuggestion, temperature=0.2, max_tokens=180)


async def close_client():
    await _http_client.aclose()
