"""Serviço de Transcrição usando faster-whisper."""

import os
import asyncio
import logging
from typing import BinaryIO, Optional, Tuple, List
from src.config import settings
from src.transcriber.schemas import TranscriptionSegment

logger = logging.getLogger(__name__)


class WhisperService:
    """Gerenciador e executor do modelo de Speech-to-Text Whisper."""

    _instance: Optional["WhisperService"] = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WhisperService, cls).__new__(cls)
        return cls._instance

    def _load_model(self):
        """Carrega o modelo Whisper de forma lazy."""
        if self._model is None:
            from faster_whisper import WhisperModel

            logger.info(
                f"Carregando modelo faster-whisper '{settings.WHISPER_MODEL}' "
                f"no dispositivo '{settings.WHISPER_DEVICE}' com '{settings.WHISPER_COMPUTE_TYPE}'..."
            )
            self._model = WhisperModel(
                settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
            )
            logger.info("Modelo faster-whisper carregado com sucesso.")
        return self._model

    def _sync_transcribe(
        self,
        audio_path_or_file: str | BinaryIO,
        language: Optional[str] = "pt",
        beam_size: int = 5,
    ) -> Tuple[str, str, float, float, List[TranscriptionSegment]]:
        """Execução síncrona da transcrição."""
        model = self._load_model()
        segments_generator, info = model.transcribe(
            audio_path_or_file,
            language=language,
            beam_size=beam_size,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        segments_list: List[TranscriptionSegment] = []
        full_text_parts: List[str] = []

        for segment in segments_generator:
            clean_text = segment.text.strip()
            if clean_text:
                full_text_parts.append(clean_text)
                segments_list.append(
                    TranscriptionSegment(
                        id=segment.id,
                        start=round(segment.start, 2),
                        end=round(segment.end, 2),
                        text=clean_text,
                    )
                )

        full_text = " ".join(full_text_parts).strip()
        detected_lang = info.language or "pt"
        lang_prob = round(info.language_probability, 4)
        duration = round(info.duration, 2)

        return full_text, detected_lang, lang_prob, duration, segments_list

    _semaphore: Optional[asyncio.Semaphore] = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Garante que o semáforo seja instanciado no event loop ativo."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.WHISPER_MAX_CONCURRENCY)
        return self._semaphore

    async def transcribe_audio(
        self,
        audio_path_or_file: str | BinaryIO,
        language: Optional[str] = "pt",
        beam_size: int = 5,
    ) -> Tuple[str, str, float, float, List[TranscriptionSegment]]:
        """Executa a transcrição em thread pool controlando a concorrência máxima com semáforo."""
        sem = self._get_semaphore()
        async with sem:
            return await asyncio.to_thread(
                self._sync_transcribe,
                audio_path_or_file,
                language=language,
                beam_size=beam_size,
            )


whisper_service = WhisperService()
