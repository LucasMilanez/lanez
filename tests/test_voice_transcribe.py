"""Testes do endpoint POST /voice/transcribe — Fase 6b.

Verifica transcrição de áudio, validações de Content-Type, tamanho,
body vazio, falha Groq e autenticação.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.main import app
from app.services.groq_voice import GroqTranscriptionError


def _make_fake_user() -> MagicMock:
    """Cria User mock para dependency override."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    user.last_sync_at = None
    user.created_at = datetime.now(timezone.utc)
    return user


@pytest.mark.asyncio
async def test_voice_transcribe_returns_text():
    """Mock transcribe_audio retornando 'texto teste' → 200 com transcription e duration_ms."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        with patch(
            "app.routers.voice.transcribe_audio",
            new_callable=AsyncMock,
            return_value="texto teste",
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                audio_bytes = b"\x00\x01\x02\x03" * 100
                resp = await client.post(
                    "/voice/transcribe",
                    files={"audio": ("audio.webm", audio_bytes, "audio/webm")},
                )

            assert resp.status_code == 200
            body = resp.json()
            assert body["transcription"] == "texto teste"
            assert "duration_ms" in body
            assert isinstance(body["duration_ms"], int)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_voice_transcribe_rejects_unsupported_content_type():
    """Content-Type application/json → 415."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/voice/transcribe",
                files={"audio": ("audio.json", b"not audio", "application/json")},
            )

        assert resp.status_code == 415
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_voice_transcribe_rejects_oversized_audio():
    """Body > 5 MB → 413."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            oversized = b"\x00" * (5 * 1024 * 1024 + 1)
            resp = await client.post(
                "/voice/transcribe",
                files={"audio": ("audio.webm", oversized, "audio/webm")},
            )

        assert resp.status_code == 413
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_voice_transcribe_rejects_empty_audio():
    """Body vazio (0 bytes) → 400."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/voice/transcribe",
                files={"audio": ("audio.webm", b"", "audio/webm")},
            )

        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_voice_transcribe_returns_502_on_groq_failure():
    """Mock transcribe_audio levantando GroqTranscriptionError → 502."""
    fake_user = _make_fake_user()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        with patch(
            "app.routers.voice.transcribe_audio",
            new_callable=AsyncMock,
            side_effect=GroqTranscriptionError("falha"),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                audio_bytes = b"\x00\x01\x02\x03" * 100
                resp = await client.post(
                    "/voice/transcribe",
                    files={"audio": ("audio.webm", audio_bytes, "audio/webm")},
                )

            assert resp.status_code == 502
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_voice_transcribe_requires_auth():
    """Sem cookie/Bearer → 401. NÃO define dependency override."""
    # Garantir que NÃO há override para get_current_user
    app.dependency_overrides.pop(get_current_user, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/voice/transcribe",
            files={"audio": ("audio.webm", b"\x00\x01\x02", "audio/webm")},
        )

    assert resp.status_code == 401
