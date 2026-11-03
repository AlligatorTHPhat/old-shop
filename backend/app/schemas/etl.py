"""Dead-letter document contract, shared by ETL validation and index field checks."""

from typing import Literal

from pydantic import AwareDatetime, Field

from app.schemas.documents import DocumentModel, Identifier


class ErrorKey(DocumentModel):
    id: Identifier
    created_at: str | None = None


class ETLError(DocumentModel):
    id: str = Field(alias="_id")
    event_id: int
    run_id: str
    entity_type: Literal["product", "order", "review", "system_log", "violation_log", "contact"]
    entity_key: ErrorKey
    code: str = Field(max_length=80)
    attempts: int = Field(ge=1)
    last_at: AwareDatetime
    resolved: bool = False
