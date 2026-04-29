"""Cliente Groq Whisper para transcrição de áudio — Fase 6b.

Envia áudio multipart para a API da Groq e retorna a transcrição.
Não persiste o áudio. Não armazena a transcrição.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_HTTP_TIMEOUT = 60.0


class GroqTranscriptionError(Exception):
    """Falha ao transcrever via Groq (rede, autenticação, payload)."""


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
) -> str:
    """Transcreve áudio via Groq Whisper.

    Retorna o texto cru. Levanta GroqTranscriptionError em caso de falha.
    """
    if not settings.GROQ_API_KEY:
        raise GroqTranscriptionError("GROQ_API_KEY não configurado")

    files = {"file": (filename, audio_bytes, content_type)}
    data = {
        "model": settings.GROQ_WHISPER_MODEL,
        "language": "pt",
        "response_format": "json",
    }
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            resp = await client.post(
                GROQ_TRANSCRIPTION_URL,
                files=files,
                data=data,
                headers=headers,
            )
        except httpx.HTTPError as e:
            logger.exception("Falha de rede ao chamar Groq Whisper")
            raise GroqTranscriptionError(f"Erro de rede: {e}") from e

    if resp.status_code != 200:
        logger.error(
            "Groq Whisper retornou %d — body=%s",
            resp.status_code,
            resp.text[:500],
        )
        raise GroqTranscriptionError(
            f"Groq retornou {resp.status_code}"
        )

    payload = resp.json()
    text = (payload.get("text") or "").strip()
    if not text:
        raise GroqTranscriptionError("Groq retornou texto vazio")

    return text
