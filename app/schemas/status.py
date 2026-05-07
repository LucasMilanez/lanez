"""Schemas Pydantic para o endpoint GET /status (dashboard) — Fase 6a."""

from datetime import datetime

from pydantic import BaseModel


class ServiceCount(BaseModel):
    service: str
    count: int


class WebhookInfo(BaseModel):
    resource: str
    expires_at: datetime


class RecentBriefing(BaseModel):
    event_id: str
    event_subject: str
    event_start: datetime


class TokenUsageBucket(BaseModel):
    input: int
    output: int
    cache_read: int
    cache_write: int


class McpActivityBucket(BaseModel):
    total_calls: int
    successful: int
    failed: int
    tools_used: list[ServiceCount]


class StatusConfig(BaseModel):
    briefing_history_window_days: int
    audit_history_window_days: int


class StatusResponse(BaseModel):
    user_email: str
    token_expires_at: datetime
    token_expires_in_seconds: int
    last_sync_at: datetime | None
    webhook_subscriptions: list[WebhookInfo]
    embeddings_by_service: list[ServiceCount]
    memories_count: int
    briefings_count_30d: int
    recent_briefings: list[RecentBriefing]
    tokens_30d: TokenUsageBucket
    mcp_activity_30d: McpActivityBucket
    config: StatusConfig
