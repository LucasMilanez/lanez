"""Schemas Pydantic para memórias REST — Fase 6b."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MemoryCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10_000)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("content")
    @classmethod
    def _strip_and_reject_whitespace(cls, v: str) -> str:
        """min_length=1 sozinho aceita "   " (3 espaços). Rejeitar."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("content não pode ser apenas whitespace")
        return stripped


class MemoryResponse(BaseModel):
    id: UUID
    content: str
    tags: list[str]
    created_at: datetime
