"""Router de voz — captura via mic e transcrição via Groq Whisper. Fase 6b."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config import settings
from app.dependencies import get_current_user
from app.models.user import User
from app.services.groq_voice import GroqTranscriptionError, transcribe_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceTranscriptionResponse(BaseModel):
    transcription: str
    duration_ms: int  # tempo total da chamada (recebimento + Groq)


_ALLOWED_CONTENT_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
}


@router.post("/transcribe", response_model=VoiceTranscriptionResponse)
async def transcribe(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> VoiceTranscriptionResponse:
    """Recebe áudio do mic e retorna transcrição via Groq Whisper.

    Limites:
    - Tamanho máximo: settings.VOICE_MAX_AUDIO_BYTES (5 MB)
    - Content-Type: audio/webm, audio/ogg, audio/mp4, audio/mpeg, audio/wav, audio/flac
    """
    # Chrome envia "audio/webm;codecs=opus" — separar parâmetros antes de validar
    raw_ct = (audio.content_type or "").split(";")[0].strip()
    if raw_ct not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Content-Type não suportado: {audio.content_type}",
        )

    audio_bytes = await audio.read()
    if len(audio_bytes) > settings.VOICE_MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Áudio excede {settings.VOICE_MAX_AUDIO_BYTES} bytes "
                f"(recebido: {len(audio_bytes)})"
            ),
        )

    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Áudio vazio",
        )

    started_at = time.monotonic()
    try:
        text = await transcribe_audio(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
            content_type=raw_ct,
        )
    except GroqTranscriptionError as e:
        logger.warning(
            "Falha na transcrição para user_id=%s: %s",
            user.id,
            e,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Falha ao transcrever áudio",
        )

    elapsed_ms = int((time.monotonic() - started_at) * 1000)

    # Telemetria mínima — sem persistir áudio nem transcrição
    logger.info(
        "voice.transcribe user_id=%s bytes=%d duration_ms=%d",
        user.id,
        len(audio_bytes),
        elapsed_ms,
    )

    return VoiceTranscriptionResponse(
        transcription=text,
        duration_ms=elapsed_ms,
    )
