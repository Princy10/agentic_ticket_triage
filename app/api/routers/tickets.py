from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import SessionDep
from app.domain.models import Ticket
from app.domain.schemas import TicketCreate, TicketUpdate
from app.services.ticket_service import (
    create_ticket, list_tickets, get_ticket, update_ticket, delete_ticket
)

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.post("", response_model=Ticket)
def post_ticket(payload: TicketCreate, session: Session = Depends(SessionDep)):
    return create_ticket(
        session,
        title=payload.title,
        description=payload.description,
        category_id=payload.category_id
    )


@router.get("", response_model=list[Ticket])
def get_tickets(session: Session = Depends(SessionDep)):
    return list_tickets(session)


@router.get("/{ticket_id}", response_model=Ticket)
def get_one_ticket(ticket_id: int, session: Session = Depends(SessionDep)):
    t = get_ticket(session, ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail="Ticket introuvable")
    return t


@router.patch("/{ticket_id}", response_model=Ticket)
def patch_ticket(ticket_id: int, payload: TicketUpdate, session: Session = Depends(SessionDep)):
    try:
        return update_ticket(session, ticket_id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{ticket_id}")
def remove_ticket(ticket_id: int, session: Session = Depends(SessionDep)):
    delete_ticket(session, ticket_id)
    return {"message": "Suppression effectuée (si le ticket existait)."}
