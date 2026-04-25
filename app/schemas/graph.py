from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class ServiceType(str, Enum):
    CALENDAR = "calendar"
    MAIL = "mail"
    ONENOTE = "onenote"
    ONEDRIVE = "onedrive"


class GraphDataResponse(BaseModel):
    service: ServiceType
    data: dict | list
    from_cache: bool
    cached_at: datetime | None = None


class WebhookNotification(BaseModel):
    subscription_id: str
    client_state: str
    resource: str
    change_type: str


class WebhookSubscriptionResponse(BaseModel):
    id: UUID
    subscription_id: str
    resource: str
    expires_at: datetime
