from typing import TypedDict, Any, List, Dict

from langgraph.graph import StateGraph, START, END

from app.services.ticket_service import get_ticket
from app.services.category_service import list_categories
from app.services.triage_policy import apply_guardrails

from app.agents.classify_agent import classify_ticket
from app.agents.priority_agent import prioritize_ticket
from app.agents.reply_agent import draft_reply


class TriageState(TypedDict, total=False):
    ticket_id: int

    ticket: Any
    title: str
    description: str

    cats: List[Any]
    allowed_names: List[str]

    cat_suggestion: Any
    prio_suggestion: Any
    reply_suggestion: Any

    patch: Dict[str, Any]
    response: Dict[str, Any]


def build_triage_graph_multi(session):
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

    async def classify(state: TriageState) -> dict:
        cat_suggestion = await classify_ticket(state["title"], state["description"], state["allowed_names"])
        return {"cat_suggestion": cat_suggestion}

    async def prioritize(state: TriageState) -> dict:
        prio_suggestion = await prioritize_ticket(
            state["title"],
            state["description"],
            state["cat_suggestion"].category_name,
        )
        return {"prio_suggestion": prio_suggestion}

    async def reply(state: TriageState) -> dict:
        reply_suggestion = await draft_reply(
            state["title"],
            state["description"],
            state["cat_suggestion"].category_name,
            state["prio_suggestion"].priority,
        )
        return {"reply_suggestion": reply_suggestion}

    def policy_and_format(state: TriageState) -> dict:
        ticket = state["ticket"]
        cats = state["cats"]

        cat = state["cat_suggestion"]
        pr = state["prio_suggestion"]
        rep = state["reply_suggestion"]

        matched = next((c for c in cats if c.name == cat.category_name), None)
        if not matched:
            raise ValueError("category_name hors liste exacte")

        patch = {
            "category_id": matched.id,
            "priority": pr.priority.value,
            "status": pr.status.value,
        }

        name_to_id = {c.name: c.id for c in cats}
        patch = apply_guardrails(ticket, patch, category_name_to_id=name_to_id)

        # Fusion “suggestion” finale (multi-agents)
        rationale = (cat.rationale or []) + (pr.rationale or [])
        rationale = rationale[:5]

        suggestion = {
            "category_name": cat.category_name,
            "priority": pr.priority.value,
            "status": pr.status.value,
            "summary": cat.summary,
            "rationale": rationale,
            "draft_reply": rep.draft_reply,
        }

        response = {"ticket_id": state["ticket_id"], "suggestion": suggestion, "patch_to_apply": patch}
        return {"patch": patch, "response": response}

    g = StateGraph(TriageState)
    g.add_node("fetch", fetch)
    g.add_node("classify", classify)
    g.add_node("prioritize", prioritize)
    g.add_node("reply", reply)
    g.add_node("policy_and_format", policy_and_format)

    g.add_edge(START, "fetch")
    g.add_edge("fetch", "classify")
    g.add_edge("classify", "prioritize")
    g.add_edge("prioritize", "reply")
    g.add_edge("reply", "policy_and_format")
    g.add_edge("policy_and_format", END)

    return g.compile()
