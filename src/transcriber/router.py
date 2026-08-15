"""Rotas FastAPI para o serviço de Transcrição Whisper."""

import os
import uuid
import time
import shutil
import tempfile
import logging
from typing import Optional
from fastapi import APIRouter, File, UploadFile, Query, HTTPException, status
from src.transcriber.schemas import TranscriptionBase64Request, TranscriptionResponse
from src.transcriber.service import whisper_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Speech to Text"])


@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Transcreve arquivo de áudio para texto",
    description="Recebe arquivo de áudio (WhatsApp .ogg/.opus, .mp3, .wav, .m4a) e processa via faster-whisper.",
)
async def transcribe_audio_file(
    file: UploadFile = File(..., description="Arquivo de áudio para transcrição"),
    language: Optional[str] = Query(default="pt", description="Código do idioma (ex: pt, en)"),
    audio_id: Optional[str] = Query(default=None, description="Identificador único customizado do áudio"),
) -> TranscriptionResponse:
    """Endpoint para transcrição de áudio."""
    start_time = time.perf_counter()

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo de áudio não fornecido ou inválido.",
        )

    assigned_id = audio_id or f"audio_{uuid.uuid4().hex[:10]}"
    file_extension = os.path.splitext(file.filename)[1] or ".ogg"

    # Salva o arquivo temporariamente para o CTranslate2/faster-whisper processar via libav
    with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as tmp_file:
        tmp_path = tmp_file.name
        shutil.copyfileobj(file.file, tmp_file)

    try:
        text, detected_lang, lang_prob, duration, segments = await whisper_service.transcribe_audio(
            audio_path_or_file=tmp_path,
            language=language,
        )
    except Exception as exc:
        logger.error(f"Erro ao transcrever arquivo de áudio '{file.filename}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no processamento de transcrição: {str(exc)}",
        )
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    duration_ms = (time.perf_counter() - start_time) * 1000

    return TranscriptionResponse(
        audio_id=assigned_id,
        language=detected_lang,
        language_probability=lang_prob,
        duration=duration,
        text=text,
        segments=segments,
        processing_time_ms=round(duration_ms, 2),
    )


@router.post(
    "/transcribe/base64",
    response_model=TranscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Transcreve áudio codificado em base64",
    description="Recebe áudio em base64 (enviado diretamente pelo WhatsApp / Evolution API) e processa via faster-whisper.",
)
async def transcribe_audio_base64(
    payload: TranscriptionBase64Request,
) -> TranscriptionResponse:
    """Endpoint para transcrição de áudio a partir de payload JSON base64."""
    import base64

    start_time = time.perf_counter()
    assigned_id = payload.audio_id or f"audio_{uuid.uuid4().hex[:10]}"

    raw_base64 = payload.base64
    if "," in raw_base64:
        raw_base64 = raw_base64.split(",", 1)[1]

    try:
        audio_bytes = base64.b64decode(raw_base64)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"String base64 inválida: {str(exc)}",
        )

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_file:
        tmp_path = tmp_file.name
        tmp_file.write(audio_bytes)

    try:
        text, detected_lang, lang_prob, duration, segments = await whisper_service.transcribe_audio(
            audio_path_or_file=tmp_path,
            language=payload.language,
        )
    except Exception as exc:
        logger.error(f"Erro ao transcrever áudio base64: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no processamento de transcrição: {str(exc)}",
        )
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    duration_ms = (time.perf_counter() - start_time) * 1000

    return TranscriptionResponse(
        audio_id=assigned_id,
        language=detected_lang,
        language_probability=lang_prob,
        duration=duration,
        text=text,
        segments=segments,
        processing_time_ms=round(duration_ms, 2),
    )

