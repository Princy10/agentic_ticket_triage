from typing import TypedDict, List, Dict, Any

from langgraph.graph import StateGraph, START, END

from app.services.ticket_service import get_ticket
from app.services.category_service import list_categories
from app.agents.triage_agent import suggest_triage
from app.services.triage_policy import apply_guardrails


class TriageState(TypedDict, total=False):
    ticket_id: int

    # données ticket
    ticket: Any
    title: str
    description: str

    # catégories
    cats: List[Any]
    allowed_names: List[str]

    # sortie LLM
    suggestion: Any

    # sortie finale
    patch: Dict[str, Any]
    response: Dict[str, Any]


def build_triage_graph(session):
    # Node 1: fetch ticket + catégories
    def fetch(state: TriageState) -> dict:
        ticket_id = state["ticket_id"]

        ticket = get_ticket(session, ticket_id)
        if not ticket:
            raise ValueError("Ticket introuvable")

        cats = list_categories(session)
        if not cats:
            raise ValueError("Aucune catégorie en base")

        return {
            "ticket": ticket,
            "title": ticket.title,
            "description": ticket.description,
            "cats": cats,
            "allowed_names": [c.name for c in cats],
        }

    # Node 2: appel LLM (agent PydanticAI)
    async def llm_suggest(state: TriageState) -> dict:
        suggestion = await suggest_triage(
            state["title"],
            state["description"],
            state["allowed_names"],
        )
        return {"suggestion": suggestion}

    # Node 3: mapping category + guardrails + build response
    def apply_policy_and_format(state: TriageState) -> dict:
        suggestion = state["suggestion"]
        cats = state["cats"]
        ticket = state["ticket"]

        matched = next((c for c in cats if c.name == suggestion.category_name), None)
        if not matched:
            raise ValueError("category_name hors liste exacte")

        patch = {
            "category_id": matched.id,
            "priority": suggestion.priority.value,
            "status": suggestion.status.value,
        }

        name_to_id = {c.name: c.id for c in cats}
        patch = apply_guardrails(ticket, patch, category_name_to_id=name_to_id)

        response = {
            "ticket_id": state["ticket_id"],
            "suggestion": suggestion.model_dump(),
            "patch_to_apply": patch,
        }
        return {"patch": patch, "response": response}

    g = StateGraph(TriageState)
    g.add_node("fetch", fetch)
    g.add_node("llm_suggest", llm_suggest)
    g.add_node("apply_policy_and_format", apply_policy_and_format)

    g.add_edge(START, "fetch")
    g.add_edge("fetch", "llm_suggest")
    g.add_edge("llm_suggest", "apply_policy_and_format")
    g.add_edge("apply_policy_and_format", END)

    return g.compile()
