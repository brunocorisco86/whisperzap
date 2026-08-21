"""Schemas Pydantic para o Dicionário Léxico e Glossário Hermes."""

from typing import Optional
from pydantic import BaseModel, Field


class DictionaryTermBase(BaseModel):
    """Modelo base para um termo do dicionário léxico."""

    term: str = Field(..., description="Termo correto ou sigla canônica", examples=["FAL"])
    phonetic_variations: list[str] = Field(
        default_factory=list,
        description="Variações fonéticas ou erros comuns de transcrição do Whisper",
        examples=[["FAU", "fao", "fal"]],
    )
    expansion: Optional[str] = Field(
        default=None,
        description="Expansão do termo ou significado completo",
        examples=["Ficha de Acompanhamento de Lote"],
    )
    category: str = Field(
        default="GERAL",
        description="Categoria temática (ex: ZOOTECNIA, AGRONEGOCIO, SISTEMAS, EQUIPAMENTOS)",
        examples=["ZOOTECNIA"],
    )
    description: Optional[str] = Field(
        default=None,
        description="Explicação ou contexto de negócio adicional",
    )


class DictionaryTermCreate(DictionaryTermBase):
    """Schema de criação de um novo termo."""

    pass


class DictionaryTerm(DictionaryTermBase):
    """Schema completo do termo persistido."""

    id: str = Field(..., description="Identificador único do termo")
    created_at: str = Field(..., description="Data de criação ISO 8601")


class DictionaryHintResponse(BaseModel):
    """Dicas de contexto e vocabulário para injeção nos prompts e no Whisper."""

    whisper_initial_prompt: str = Field(
        ...,
        description="String de palavras-chave formatada para o parâmetro initial_prompt do faster-whisper",
    )
    prompt_context_hint: str = Field(
        ...,
        description="Bloco de texto com glossário para injeção no prompt de contexto do AI Gateway",
    )
    total_terms: int = Field(..., description="Total de termos cadastrados")


class DictionaryMergeCluster(BaseModel):
    """Detalhes de um cluster de termos unificados no dicionário."""

    canonical_term: str
    merged_terms: list[str] = []
    phonetic_variations_total: int = 0
    category: str = "GERAL"


class DictionaryMergeResponse(BaseModel):
    """Resposta estruturada da operação de mesclagem do Dicionário Léxico com spaCy."""

    status: str = "success"
    merged_terms_count: int = 0
    merged_clusters_count: int = 0
    candidates_merged_count: int = 0
    clusters: list[DictionaryMergeCluster] = []
    message: str
