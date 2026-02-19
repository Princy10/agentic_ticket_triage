import os
import json
import time
import logging
from typing import List, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from app.domain.schemas import TicketPriority, TicketStatus

logger = logging.getLogger("triage_agent")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")  # override possible via env

# Timeouts HTTP vers Ollama (évite les “hang” infinis)
_http_timeout = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
_http_client = httpx.AsyncClient(timeout=_http_timeout)

_provider = OllamaProvider(base_url=OLLAMA_BASE_URL, http_client=_http_client)
_model = OpenAIChatModel(model_name=OLLAMA_MODEL, provider=_provider)


class TriageSuggestion(BaseModel):
    category_name: str = Field(..., description="Doit correspondre EXACTEMENT à une des catégories autorisées.")
    priority: TicketPriority
    status: TicketStatus
    summary: str = Field(..., description="Résumé court (1–2 phrases).")
    rationale: List[str] = Field(default_factory=list, description="2–5 puces factuelles.")
    draft_reply: Optional[str] = Field(default=None, description="Optionnel (réponse support courte).")


class TriageParseError(Exception):
    def __init__(self, message: str, raw_output: str):
        super().__init__(message)
        self.raw_output = raw_output

_agent = Agent(
    _model,
    output_type=str,
    system_prompt=(
        "Tu es un agent de triage de tickets support.\n"
        "Tu DOIS répondre uniquement avec un JSON valide (un objet), sans markdown, sans texte avant/après.\n"
        "Le JSON DOIT contenir exactement ces clés:\n"
        "category_name (string), priority (LOW|MEDIUM|HIGH|URGENT), status (OPEN|IN_PROGRESS|RESOLVED|CLOSED),\n"
        "summary (string), rationale (array of strings), draft_reply (string|null).\n"
        "Règles:\n"
        "1) category_name doit être EXACTEMENT une valeur parmi la liste fournie.\n"
        "2) Évite 'Incident' sauf si panne/indisponibilité globale.\n"
        "3) Status: ne proposer que OPEN ou IN_PROGRESS (jamais RESOLVED/CLOSED au triage).\n"
        "   Si priority est HIGH ou URGENT -> status doit être IN_PROGRESS.\n"
        "   Si 401/403/forbidden/permission/role -> category_name = Access.\n"
        "4) summary: 1–2 phrases max.\n"
        "5) rationale: 2–5 puces factuelles.\n"
    ),
)


def _extract_first_json_object(text: str) -> str:
    s = text.strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("Aucun '{' trouvé, pas de JSON.")
    in_str = False
    escape = False
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    raise ValueError("JSON incomplet: '}' manquant.")


def _build_prompt(title: str, desc: str, allowed_categories: List[str]) -> str:
    allowed = json.dumps(allowed_categories, ensure_ascii=False)

    desc = (desc or "")[:1500]

    schema_hint = {
        "category_name": allowed_categories[0] if allowed_categories else "Bug",
        "priority": "MEDIUM",
        "status": "OPEN",
        "summary": "string",
        "rationale": ["string"],
        "draft_reply": None,
    }

    return (
        f"Catégories autorisées (liste stricte): {allowed}\n\n"
        f"Ticket:\nTitle: {title}\nDescription: {desc}\n\n"
        f"Réponds UNIQUEMENT avec un JSON objet conforme.\n"
        f"Exemple de forme (ne pas copier, juste respecter les clés):\n"
        f"{json.dumps(schema_hint, ensure_ascii=False)}"
    )


async def suggest_triage(title: str, description: str, allowed_categories: List[str]) -> TriageSuggestion:
    prompt = _build_prompt(title, description, allowed_categories)

    t0 = time.perf_counter()
    raw = (await _agent.run(prompt, model_settings={"temperature": 0.2, "max_tokens": 260})).output
    logger.info("LLM raw done in %.2fs", time.perf_counter() - t0)

    # 1ère tentative: parse + validate
    try:
        js = _extract_first_json_object(raw)
        return TriageSuggestion.model_validate_json(js)
    except Exception as e1:
        # 2ème tentative: “repair” guidé
        repair_prompt = (
            "Ton output précédent n'était pas valide/parseable.\n"
            "Corrige et renvoie UNIQUEMENT un JSON objet valide (aucun texte).\n"
            f"Erreur: {str(e1)}\n"
            f"Catégories autorisées: {json.dumps(allowed_categories, ensure_ascii=False)}\n"
            "Output précédent:\n"
            f"{raw}"
        )
        t1 = time.perf_counter()
        raw2 = (await _agent.run(repair_prompt, model_settings={"temperature": 0.0, "max_tokens": 260})).output
        logger.info("LLM repair done in %.2fs", time.perf_counter() - t1)

        try:
            js2 = _extract_first_json_object(raw2)
            return TriageSuggestion.model_validate_json(js2)
        except ValidationError as ve:
            raise TriageParseError(f"Validation Pydantic impossible: {ve}", raw2) from ve
        except Exception as e2:
            raise TriageParseError(f"Parsing JSON impossible: {e2}", raw2) from e2


async def warmup_llm() -> None:
    try:
        logger.info("Warmup LLM (%s)...", OLLAMA_MODEL)
        _ = await _agent.run("Réponds uniquement: {\"ok\": true}", model_settings={"temperature": 0.0, "max_tokens": 20})
        logger.info("Warmup OK")
    except Exception as e:
        logger.warning("Warmup échoué: %s", e)


async def close_llm_clients() -> None:
    await _http_client.aclose()
