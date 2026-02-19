from enum import Enum
from typing import Any

from pydantic import BaseModel


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class TicketPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None


class TicketCreate(BaseModel):
    title: str
    description: str
    category_id: int | None = None


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category_id: int | None = None

class McpTriageSuggestion(BaseModel):
    category_name: str
    priority: str
    status: str
    summary: str
    rationale: list[str]
    draft_reply: str | None = None

class McpTriageResult(BaseModel):
    ticket_id: int
    suggestion: McpTriageSuggestion
    patch_to_apply: dict[str, Any]