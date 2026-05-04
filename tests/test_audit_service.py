"""Testes do service helper app/services/audit.py — Fase 7.

Verifica criação de entrada, truncamento de error_message e resiliência
a falhas de flush (audit não pode derrubar request).

Os dois primeiros testes usam mock de AsyncSession para verificar que
log_event chama db.add e db.flush com os argumentos corretos, sem
depender de banco real (JSONB incompatível com SQLite).
O terceiro teste verifica resiliência a falhas de flush.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.models.audit import AuditLog
from app.services.audit import AuditEventType, log_event


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_event_creates_audit_log_entry():
    """Chama log_event com campos válidos; verifica que db.add recebe
    AuditLog com campos corretos e db.flush é chamado."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    user_id = uuid.uuid4()
    await log_event(
        mock_db,
        user_id=user_id,
        event_type=AuditEventType.MCP_CALL,
        event_data={"tool_name": "search_emails", "success": True},
        success=True,
        latency_ms=150,
    )

    # Verificar que db.add foi chamado com um AuditLog
    mock_db.add.assert_called_once()
    entry = mock_db.add.call_args[0][0]
    assert isinstance(entry, AuditLog)
    assert entry.user_id == user_id
    assert entry.event_type == "mcp.call"
    assert entry.event_data == {"tool_name": "search_emails", "success": True}
    assert entry.success is True
    assert entry.latency_ms == 150
    assert entry.error_message is None
    assert isinstance(entry.created_at, datetime)

    # Verificar que flush foi chamado (não commit)
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_event_truncates_long_error_message():
    """Passa error_message de 600 chars; verifica truncamento a 500 com '...'."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    long_msg = "x" * 600
    await log_event(
        mock_db,
        user_id=uuid.uuid4(),
        event_type=AuditEventType.MCP_CALL,
        event_data={"tool_name": "test"},
        success=False,
        error_message=long_msg,
    )

    entry = mock_db.add.call_args[0][0]
    assert isinstance(entry, AuditLog)
    assert len(entry.error_message) == 500
    assert entry.error_message.endswith("...")
    assert entry.success is False


@pytest.mark.asyncio
async def test_log_event_does_not_raise_on_flush_failure():
    """Mock db.flush levantando exceção; verifica que log_event não propaga."""
    mock_db = AsyncMock()
    mock_db.flush = AsyncMock(side_effect=Exception("db down"))
    mock_db.add = MagicMock()

    # Não deve levantar — audit não pode derrubar request
    await log_event(
        mock_db,
        user_id=uuid.uuid4(),
        event_type=AuditEventType.AUTH_LOGIN,
        event_data={"method": "oauth_callback"},
        success=True,
    )

    # Verificar que add e flush foram chamados
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()
