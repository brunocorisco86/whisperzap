"""Serviço de Transcrição usando faster-whisper com Dynamic Prompt Priming e Silero-VAD calibrado."""

import os
import asyncio
import logging
from typing import BinaryIO, Optional, Tuple, List
from sqlalchemy.orm import Session

from src.config import settings
from src.transcriber.schemas import TranscriptionSegment
from src.transcriber.prosody_analyzer import prosody_analyzer, ProsodyMetrics
from src.dictionary.service import dictionary_service
from src.memory.database import SessionLocal

logger = logging.getLogger(__name__)


def build_dynamic_initial_prompt(
    speaker: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    db: Optional[Session] = None,
) -> str:
    """Gera o prompt inicial dinâmico (Priming) para condicionar o Whisper e eliminar alucinações.
    
    Combina:
    1. Vocabulário técnico do Dicionário Léxico (C.Vale, eProdutor, Mtech, Agrocenter, Silos, etc.);
    2. Nomes de contatos frequentes / favoritos do sistema;
    3. Custom prompt opcional passado pela requisição.
    """
    prompt_parts: List[str] = []

    # 1. Custom prompt e speaker prioritários
    if custom_prompt and custom_prompt.strip():
        prompt_parts.append(custom_prompt.strip())

    if speaker and speaker.strip() and speaker.strip() not in ("user", "bruno"):
        prompt_parts.append(speaker.strip())

    # 2. Termos canônicos concisos do Dicionário Léxico
    try:
        terms = dictionary_service.list_terms()
        canon_terms = [t.term for t in terms if t.term]
        if canon_terms:
            prompt_parts.append(", ".join(canon_terms[:15]))
    except Exception as e:
        logger.warning(f"Erro ao carregar termos do dicionário para o Whisper: {e}")

    # 3. Contatos relevantes e favoritos do PostgreSQL
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        from src.contacts.models import ContactRecord
        top_contacts = (
            db.query(ContactRecord.name)
            .filter(ContactRecord.name.isnot(None))
            .order_by(ContactRecord.is_favorite.desc(), ContactRecord.updated_at.desc())
            .limit(15)
            .all()
        )
        contact_names = [c[0].strip() for c in top_contacts if c[0] and len(c[0].strip()) > 2]
        if contact_names:
            prompt_parts.append(", ".join(contact_names[:10]))
    except Exception as e:
        logger.warning(f"Aviso ao consultar contatos para o prompt do Whisper: {e}")
    finally:
        if should_close and db:
            db.close()

    final_prompt = ", ".join([p.strip().rstrip(".") for p in prompt_parts if p.strip()])
    return final_prompt[:800]


class WhisperService:
    """Gerenciador e executor do modelo de Speech-to-Text Whisper com Dynamic Priming."""

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
        initial_prompt: Optional[str] = None,
    ) -> Tuple[str, str, float, float, List[TranscriptionSegment]]:
        """Execução síncrona da transcrição com suporte a initial_prompt e VAD calibrado."""
        model = self._load_model()
        
        # Calibração otimizada de Silero VAD para ambientes rurais/ruidosos
        vad_parameters = dict(
            min_silence_duration_ms=400,
            speech_pad_ms=200,
        )

        if initial_prompt:
            logger.info(f"🎙️ [Whisper Priming] Initial prompt ativo: '{initial_prompt[:70]}...'")

        segments_generator, info = model.transcribe(
            audio_path_or_file,
            language=language,
            beam_size=beam_size,
            initial_prompt=initial_prompt,
            vad_filter=True,
            vad_parameters=vad_parameters,
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

        prosody = prosody_analyzer.analyze_speech_prosody(
            duration=duration,
            segments=segments_list,
            text=full_text,
        )

        return full_text, detected_lang, lang_prob, duration, segments_list, prosody

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
        speaker: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Tuple[str, str, float, float, List[TranscriptionSegment], ProsodyMetrics]:
        """Executa a transcrição em thread pool controlando a concorrência máxima com semáforo e prompt dinâmico."""
        # Monta prompt inicial dinâmico para condicionamento de vocabulário
        initial_prompt = build_dynamic_initial_prompt(
            speaker=speaker,
            custom_prompt=custom_prompt,
            db=db,
        )

        sem = self._get_semaphore()
        async with sem:
            return await asyncio.to_thread(
                self._sync_transcribe,
                audio_path_or_file,
                language=language,
                beam_size=beam_size,
                initial_prompt=initial_prompt,
            )


whisper_service = WhisperService()
