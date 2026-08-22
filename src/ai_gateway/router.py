"""Rotas FastAPI para o serviço AI Gateway."""

import time
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
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

    raw_text = request.text.strip()
    is_long_audio = len(raw_text) >= 300
    extra_instructions = ""
    if is_long_audio:
        extra_instructions = "\n[Instrução Mandatória: Este áudio possui mais de 300 caracteres. Formate o texto revisado e OBRIGATORIAMENTE inclua ao final a seção de destaques executivos: '📌 *Destaques do Áudio:*' em tópicos e '✅ *Ações:*' se houver pendências.]"

    context_block = f"Contexto: {request.context}{extra_instructions}" if request.context else f"Contexto: Mensagem de voz.{extra_instructions}"
    prompt = REVISE_USER_TEMPLATE.format(
        raw_text=raw_text,
        context_block=context_block,
    )

    is_fallback = False
    provider_name = "unknown"
    model_name = "unknown"

    try:
        provider = get_ai_provider(task="revise")
        provider_name = provider.provider_name
        model_name = provider.model_name
        revised_text = await provider.generate_text(
            prompt=prompt,
            system_instruction=REVISE_SYSTEM_PROMPT,
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning(
            f"⚠️ [AI Gateway Revise] Falha ao comunicar com provedor de IA ({provider_name}): {exc}. "
            "Acionando fallback gracioso com texto original do Whisper."
        )
        is_fallback = True
        revised_text = request.text.strip()
        provider_name = "fallback-whisper-raw"
        model_name = "none"

    duration_ms = (time.perf_counter() - start_time) * 1000

    return ReviseResponse(
        text_revised=revised_text,
        provider=provider_name,
        model=model_name,
        processing_time_ms=round(duration_ms, 2),
        is_fallback=is_fallback,
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


@router.get(
    "/models",
    status_code=status.HTTP_200_OK,
    summary="Consulta o registro dinâmico de modelos de IA",
    description="Retorna os modelos ativos por tarefa, histórico de descobertas e recomendações de melhor custo de token.",
)
async def get_models_registry():
    """Consulta os modelos ativos e descobertos pelo ModelRegistry."""
    from src.ai_gateway.model_registry import model_registry
    return {
        "status": "success",
        "active_models": model_registry.get_all_active_models(),
        "auto_adopt_best_lite": model_registry.data.auto_adopt_best_lite,
        "last_discovery_at": model_registry.data.last_discovery_at,
        "discovered_models": [m.model_dump() for m in model_registry.data.discovered_models],
        "history": model_registry.data.history,
    }


@router.post(
    "/models/discover",
    status_code=status.HTTP_200_OK,
    summary="Varre e descobre novos modelos de IA disponíveis",
    description="Consulta a API do Google Gemini, classifica os modelos por custo-benefício e atualiza o registro dinâmico.",
)
async def discover_models(auto_adopt: bool = True):
    """Executa a descoberta de modelos na API do provedor."""
    from src.ai_gateway.model_registry import model_registry
    res = await model_registry.discover_gemini_models(auto_adopt=auto_adopt)
    return res


class UpdateActiveModelsPayload(BaseModel):
    updates: Optional[dict[str, str]] = None
    auto_adopt: Optional[bool] = None


@router.put(
    "/models/active",
    status_code=status.HTTP_200_OK,
    summary="Atualiza dinamicamente os modelos ativos",
    description="Permite alterar o modelo de qualquer tarefa (revise, extract, summarize, weekly, hermes, default, embedding) em tempo de execução sem reiniciar o container.",
)
async def update_active_models(payload: UpdateActiveModelsPayload):
    """Atualiza modelos ativos dinamicamente."""
    from src.ai_gateway.model_registry import model_registry
    target_updates = payload.updates if payload.updates is not None else {}
    updated = model_registry.update_active_models(updates=target_updates, auto_adopt=payload.auto_adopt)
    return {
        "status": "success",
        "active_models": updated,
        "auto_adopt_best_lite": model_registry.data.auto_adopt_best_lite,
    }

