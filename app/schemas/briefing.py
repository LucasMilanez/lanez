from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BriefingResponse(BaseModel):
    id: UUID
    event_id: str
    event_subject: str
    event_start: datetime
    event_end: datetime
    attendees: list[str]
    content: str
    generated_at: datetime
    model_used: str
    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int


class BriefingListItem(BaseModel):
    """Item reduzido para listagem — sem content nem telemetria de tokens."""

    id: UUID
    event_id: str
    event_subject: str
    event_start: datetime
    event_end: datetime
    attendees: list[str]
    generated_at: datetime

    model_config = {"from_attributes": True}


class BriefingListResponse(BaseModel):
    items: list[BriefingListItem]
    total: int
    page: int
    page_size: int
