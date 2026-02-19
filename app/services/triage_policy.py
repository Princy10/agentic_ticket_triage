STATUS_RANK = {"OPEN": 0, "IN_PROGRESS": 1, "RESOLVED": 2, "CLOSED": 3}
PRIORITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "URGENT": 3}

ACCESS_KEYWORDS = (
    "403", "401", "forbidden", "unauthorized",
    "permission", "permissions",
    "role", "roles", "rôle", "rôles",
    "auth", "token", "jwt",
    "access denied", "denied", "droit", "droits",
)

DATA_KEYWORDS = (
    "csv", "export", "exports",
    "colonne", "colonnes",
    "separator", "séparateur", "separateur",
    "encoding", "encodage",
    "delimiter", "délimiteur", "delimiteur",
    "import", "importer",
    "rapport", "rapports",
    "montant",
)

ALLOWED_TRIAGE_STATUSES = {"OPEN", "IN_PROGRESS"}  # on bloque RESOLVED/CLOSED au triage


def _is_access_issue(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ACCESS_KEYWORDS)

def _is_data_issue(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in DATA_KEYWORDS)

def apply_guardrails(ticket, patch: dict, category_name_to_id: dict | None = None) -> dict:
    """
    Guardrails métier pour rendre le triage fiable.
    - No downgrade status/priority
    - HIGH/URGENT -> IN_PROGRESS (minimum)
    - Triages ne propose pas RESOLVED/CLOSED (sauf si déjà en base)
    - 401/403/permission/role -> catégorie Access
    """
    out = dict(patch)

    current_status = (getattr(ticket, "status", None) or "OPEN").upper()
    current_priority = (getattr(ticket, "priority", None) or "MEDIUM").upper()

    proposed_status = (out.get("status") or current_status).upper()
    proposed_priority = (out.get("priority") or current_priority).upper()

    if category_name_to_id and "Access" in category_name_to_id:
        full_text = f"{getattr(ticket, 'title', '')} {getattr(ticket, 'description', '')}"
        if _is_access_issue(full_text):
            out["category_id"] = category_name_to_id["Access"]

    if category_name_to_id and "Data" in category_name_to_id:
        full_text = f"{getattr(ticket, 'title', '')} {getattr(ticket, 'description', '')}"
        if _is_data_issue(full_text):
            out["category_id"] = category_name_to_id["Data"]

    # Si le ticket est déjà RESOLVED/CLOSED en base, on respecte (pas de downgrade).
    if current_status in {"RESOLVED", "CLOSED"}:
        out["status"] = current_status
    else:
        # Sinon, triage ne doit pas appliquer RESOLVED/CLOSED.
        if proposed_status not in ALLOWED_TRIAGE_STATUSES:
            # on ramène vers OPEN/IN_PROGRESS selon la priorité
            proposed_status = "IN_PROGRESS" if proposed_priority in {"HIGH", "URGENT"} else "OPEN"
        out["status"] = proposed_status

    if current_status not in {"RESOLVED", "CLOSED"}:
        pr = (out.get("priority") or proposed_priority).upper()
        if pr in {"HIGH", "URGENT"}:
            if out.get("status", "OPEN").upper() == "OPEN":
                out["status"] = "IN_PROGRESS"

    final_status = (out.get("status") or current_status).upper()
    if STATUS_RANK.get(current_status, 0) > STATUS_RANK.get(final_status, 0):
        out["status"] = current_status

    final_priority = (out.get("priority") or current_priority).upper()
    if PRIORITY_RANK.get(current_priority, 0) > PRIORITY_RANK.get(final_priority, 0):
        out["priority"] = current_priority

    # Normalisation finale
    out["status"] = (out.get("status") or "OPEN").upper()
    out["priority"] = (out.get("priority") or "MEDIUM").upper()

    return out
