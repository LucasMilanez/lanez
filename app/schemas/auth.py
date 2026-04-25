from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuthRedirectResponse(BaseModel):
    authorization_url: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    email: str
    token_expires_at: datetime


class ErrorResponse(BaseModel):
    detail: str
