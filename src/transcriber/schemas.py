"""Schemas Pydantic para o serviço de Transcrição Whisper."""

from typing import List, Optional
from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    """Segmento de fala com marcação temporal."""

    id: int
    start: float = Field(..., description="Tempo de início do segmento em segundos")
    end: float = Field(..., description="Tempo de término do segmento em segundos")
    text: str = Field(..., description="Texto falado no segmento")


class TranscriptionResponse(BaseModel):
    """Resposta da transcrição de áudio."""

    audio_id: str = Field(..., description="Identificador único da mídia ou arquivo")
    language: str = Field(..., description="Idioma detectado (ex: pt, en)")
    language_probability: float = Field(..., description="Probabilidade do idioma detectado")
    duration: float = Field(..., description="Duração total do áudio em segundos")
    text: str = Field(..., description="Transcrição completa concatenada")
    segments: Optional[List[TranscriptionSegment]] = Field(
        default=None,
        description="Segmentos detalhados de áudio com timestamps",
    )
    processing_time_ms: float = Field(..., description="Tempo de processamento em milissegundos")


class TranscriptionBase64Request(BaseModel):
    """Requisição de transcrição com áudio em base64 (Ideal para Webhooks n8n e WhatsApp)."""

    base64: str = Field(..., description="Conteúdo do arquivo de áudio codificado em base64")
    language: Optional[str] = Field(default="pt", description="Código do idioma (ex: pt, en)")
    audio_id: Optional[str] = Field(default=None, description="Identificador único opcional")
    speaker: Optional[str] = Field(default=None, description="Nome ou telefone do locutor para Dynamic Prompt Priming")
    prompt: Optional[str] = Field(default=None, description="Contexto ou termos adicionais para orientar o Whisper")

