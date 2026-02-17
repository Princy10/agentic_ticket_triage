from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import SessionDep
from app.domain.models import Category
from app.domain.schemas import CategoryCreate
from app.services.category_service import create_category, list_categories

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post("", response_model=Category)
def post_category(payload: CategoryCreate, session: Session = Depends(SessionDep)):
    try:
        return create_category(session, name=payload.name, description=payload.description)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Création catégorie impossible: {e}")


@router.get("", response_model=list[Category])
def get_categories(session: Session = Depends(SessionDep)):
    return list_categories(session)
