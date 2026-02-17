from sqlmodel import Session, select
from app.domain.models import Category


def create_category(session: Session, name: str, description: str | None = None) -> Category:
    category = Category(name=name, description=description)
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def list_categories(session: Session) -> list[Category]:
    return session.exec(select(Category).order_by(Category.name)).all()
