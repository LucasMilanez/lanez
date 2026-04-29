"""Testes do cliente Groq Whisper — Fase 6b.

1. test_groq_voice_raises_on_missing_api_key — GROQ_API_KEY="" → GroqTranscriptionError
2. test_groq_voice_raises_on_non_200_status — httpx retorna 500 → GroqTranscriptionError
3. test_groq_voice_raises_on_empty_text — Groq retorna {"text": ""} → GroqTranscriptionError
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.groq_voice import GroqTranscriptionError, transcribe_audio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AUDIO_BYTES = b"\x00\x01\x02\x03"
FILENAME = "audio.webm"
CONTENT_TYPE = "audio/webm"


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Cria um mock de httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = '{"error": "mock"}'
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.groq_voice.settings")
async def test_groq_voice_raises_on_missing_api_key(mock_settings: MagicMock) -> None:
    """GROQ_API_KEY vazio deve levantar GroqTranscriptionError."""
    mock_settings.GROQ_API_KEY = ""

    with pytest.raises(GroqTranscriptionError, match="GROQ_API_KEY não configurado"):
        await transcribe_audio(AUDIO_BYTES, FILENAME, CONTENT_TYPE)


@pytest.mark.asyncio
@patch("app.services.groq_voice.settings")
@patch("app.services.groq_voice.httpx.AsyncClient")
async def test_groq_voice_raises_on_non_200_status(
    mock_client_cls: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """Groq retornando status 500 deve levantar GroqTranscriptionError."""
    mock_settings.GROQ_API_KEY = "test-key"
    mock_settings.GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"

    mock_resp = _mock_response(status_code=500)
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    with pytest.raises(GroqTranscriptionError, match="Groq retornou 500"):
        await transcribe_audio(AUDIO_BYTES, FILENAME, CONTENT_TYPE)


@pytest.mark.asyncio
@patch("app.services.groq_voice.settings")
@patch("app.services.groq_voice.httpx.AsyncClient")
async def test_groq_voice_raises_on_empty_text(
    mock_client_cls: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """Groq retornando {"text": ""} deve levantar GroqTranscriptionError."""
    mock_settings.GROQ_API_KEY = "test-key"
    mock_settings.GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"

    mock_resp = _mock_response(status_code=200, json_data={"text": ""})
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    with pytest.raises(GroqTranscriptionError, match="Groq retornou texto vazio"):
        await transcribe_audio(AUDIO_BYTES, FILENAME, CONTENT_TYPE)
