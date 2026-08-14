"""Schemas Pydantic para o AI Gateway."""

from typing import Optional
from pydantic import BaseModel, Field


class ReviseRequest(BaseModel):
    """Requisição para revisão contextual de transcrição."""

    text: str = Field(
        ...,
        description="Texto bruto da transcrição vindo do Whisper",
        examples=["entao amanha preciso fala com joao sobre o sensor de racao do silo 3"],
    )
    context: Optional[str] = Field(
        default=None,
        description="Contexto opcional (ex: mensagens anteriores, projeto ativo, termos frequentes)",
        examples=["Usuário atua com automação de silos e integração avícola."],
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Metadados adicionais da mensagem de áudio",
    )


class ReviseResponse(BaseModel):
    """Resposta com o texto revisado."""

    text_revised: str = Field(
        ...,
        description="Texto limpo e revisado com pontuação sem acréscimo de fatos",
        examples=["Então amanhã preciso falar com João sobre o sensor de ração do silo 3."],
    )
    provider: str = Field(..., description="Provedor de LLM utilizado na revisão")
    model: str = Field(..., description="Modelo utilizado na revisão")
    processing_time_ms: float = Field(..., description="Tempo de processamento em milissegundos")
