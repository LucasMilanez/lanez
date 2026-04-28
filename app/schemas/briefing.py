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
