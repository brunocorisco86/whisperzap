"""Rotas FastAPI para o serviço AI Gateway."""

import time
import logging
from fastapi import APIRouter, HTTPException, status
from src.ai_gateway.schemas import (
    ReviseRequest,
    ReviseResponse,
    SemanticExtractionRequest,
    SemanticExtractionResponse,
)

from src.ai_gateway.prompts import REVISE_SYSTEM_PROMPT, REVISE_USER_TEMPLATE
from src.ai_gateway.providers import get_ai_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Gateway"])


@router.post(
    "/revise",
    response_model=ReviseResponse,
    status_code=status.HTTP_200_OK,
    summary="Revisão contextual de transcrição de voz",
    description="Recebe a transcrição bruta do Whisper e retorna o texto limpo, pontuado e profissional sem inventar dados.",
)
async def revise_transcription(request: ReviseRequest) -> ReviseResponse:
    """Endpoint para revisão contextual de transcrições de voz."""
    start_time = time.perf_counter()

    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=422,
            detail="O campo 'text' não pode estar vazio.",
        )

    context_block = f"Contexto: {request.context}" if request.context else "Contexto: Nenhum contexto adicional."
    prompt = REVISE_USER_TEMPLATE.format(
        raw_text=request.text.strip(),
        context_block=context_block,
    )

    try:
        provider = get_ai_provider(task="revise")
        revised_text = await provider.generate_text(
            prompt=prompt,
            system_instruction=REVISE_SYSTEM_PROMPT,
            temperature=0.0,
        )
    except Exception as exc:
        logger.error(f"Erro ao processar revisão com {provider.provider_name if 'provider' in locals() else 'unknown'}: {exc}")
        # Fallback gracioso caso haja falha externa: se der erro de API, não trava o usuário, retorna o texto original limpo
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha na comunicação com o provedor de IA: {str(exc)}",
        )

    duration_ms = (time.perf_counter() - start_time) * 1000

    return ReviseResponse(
        text_revised=revised_text,
        provider=provider.provider_name,
        model=provider.model_name,
        processing_time_ms=round(duration_ms, 2),
    )


@router.post(
    "/extract",
    response_model=SemanticExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extração semântica de intenções, tarefas e entidades",
    description="Analisa a mensagem revisada e retorna estrutura JSON com intenção primária, tarefas, entidades, decisões e urgência.",
)
async def extract_semantics(request: SemanticExtractionRequest) -> SemanticExtractionResponse:
    """Endpoint para extração semântica estruturada."""
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=422,
            detail="O campo 'text' não pode estar vazio.",
        )

    try:
        from src.ai_gateway.extractor import semantic_extractor

        return await semantic_extractor.extract(request)
    except Exception as exc:
        logger.error(f"Erro ao processar extração semântica: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha ao executar extração semântica: {str(exc)}",
        )

