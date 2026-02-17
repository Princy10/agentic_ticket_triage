from __future__ import annotations

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class Category(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: Optional[str] = None


class Ticket(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    title: str
    description: str

    status: str = Field(default="OPEN", index=True)
    priority: str = Field(default="MEDIUM", index=True)

    category_id: Optional[int] = Field(default=None, foreign_key="category.id", index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)
