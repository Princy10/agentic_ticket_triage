from datetime import datetime
from enum import Enum
from sqlmodel import Session, select

from app.domain.models import Ticket


def _normalize(v):
    # Permet de recevoir Enum (schemas) ou str sans bug
    return v.value if isinstance(v, Enum) else v


def create_ticket(session: Session, title: str, description: str, category_id: int | None = None) -> Ticket:
    ticket = Ticket(title=title, description=description, category_id=category_id)
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return ticket


def list_tickets(session: Session) -> list[Ticket]:
    return session.exec(select(Ticket).order_by(Ticket.created_at.desc())).all()


def get_ticket(session: Session, ticket_id: int) -> Ticket | None:
    return session.get(Ticket, ticket_id)


def update_ticket(session: Session, ticket_id: int, **fields) -> Ticket:
    ticket = session.get(Ticket, ticket_id)
    if not ticket:
        raise ValueError("Ticket introuvable")

    for k, v in fields.items():
        if v is None:
            continue
        if hasattr(ticket, k):
            setattr(ticket, k, _normalize(v))

    ticket.updated_at = datetime.utcnow()
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return ticket


def delete_ticket(session: Session, ticket_id: int) -> None:
    ticket = session.get(Ticket, ticket_id)
    if not ticket:
        return
    session.delete(ticket)
    session.commit()
