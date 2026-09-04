"""Router FastAPI para Webhooks e Operações do WhatsApp (Evolution API)."""

import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, Request, BackgroundTasks, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.memory.database import get_db
from src.whatsapp.service import whatsapp_service
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/whatsapp", tags=["WhatsApp & Webhooks"])


class SendTextMessageRequest(BaseModel):
    number: str = Field(..., description="Número de telefone com DDD (apenas dígitos ou com DDI 55)")
    text: str = Field(..., description="Texto da mensagem a ser enviada")


@router.post(
    "/webhook",
    summary="Webhook Nativo Evolution API",
    description="Recebe eventos em tempo real da Evolution API (áudios, mensagens de texto, comandos '?' do Hermes Agent).",
    status_code=status.HTTP_200_OK,
)
async def evolution_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Recebe e processa eventos do WhatsApp da Evolution API de forma assíncrona, com resposta imediata e deduplicação."""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "error", "message": "JSON body inválido"}

    # 1. Triagem preliminar de metadados
    info = whatsapp_service.extract_message_info(payload)
    if not info:
        return {"status": "ignored", "reason": "unhandled_event_or_invalid_payload"}

    logger.info(
        f"📨 Webhook recebido: key_id={info['key_id']}, from_me={info.get('from_me')}, "
        f"self_memo={info.get('is_self_memo')}, has_audio={info.get('has_audio')}, "
        f"text='{info.get('text')[:60]}'"
    )

    # 2. Descarte rápido de grupos e broadcast
    if info["is_group"]:
        return {"status": "ignored", "reason": "group_or_broadcast"}

    # 3. Descarte de figurinhas e reações sem texto
    if info["is_ignorable"]:
        return {"status": "ignored", "reason": "ignorable_media_type"}

    # 4. Prevenção estrita de loop de eco de respostas do bot
    raw_text = info["text"]
    BOT_PREFIXES = ("🎙️", "📋", "🤖", "💡", "⚖️", "📝", "🌙", "📊", "✅", "Salve,")
    if any(raw_text.startswith(p) for p in BOT_PREFIXES):
        return {"status": "ignored", "reason": "bot_echo_response"}

    # 5. Deduplicação atômica em memória (não bloqueia esperando pool do Postgres)
    key_id = info["key_id"]
    if whatsapp_service.is_key_duplicate_or_processing(key_id=key_id, db=None):
        logger.info(f"⏭️ Webhook duplicado ignorado para key_id={key_id}")
        return {"status": "ignored", "reason": "duplicate_key_id", "key_id": key_id}

    # 6. Agendamento em background (Evolution API recebe 200 OK em <2ms sem timeout)
    background_tasks.add_task(whatsapp_service.process_webhook_event_task, payload=payload, info=info)
    return {"status": "queued", "key_id": key_id}


@router.post(
    "/send-text",
    summary="Envia mensagem de texto via WhatsApp",
    description="Dispara uma mensagem de texto para qualquer número via Evolution API.",
    status_code=status.HTTP_200_OK,
)
async def send_text(
    payload: SendTextMessageRequest,
) -> Dict[str, Any]:
    """Envia mensagem de texto para um número no WhatsApp."""
    success = await whatsapp_service.send_text_message(number=payload.number, text=payload.text)
    return {
        "success": success,
        "number": payload.number,
        "instance": settings.EVOLUTION_INSTANCE,
    }


@router.get(
    "/status",
    summary="Status da Conexão WhatsApp",
    description="Verifica se a instância da Evolution API está conectada e operacional.",
)
async def check_whatsapp_status() -> Dict[str, Any]:
    """Verifica a saúde da conexão do WhatsApp."""
    from src.web.router import get_whatsapp_status
    return await get_whatsapp_status()


@router.post(
    "/restart-instance",
    summary="Reinicia a conexão do WhatsApp na Evolution API",
    description="Força a reinicialização e auto-reconexão do socket do WhatsApp (Baileys) na Evolution API.",
    status_code=status.HTTP_200_OK,
)
async def restart_whatsapp_instance() -> Dict[str, Any]:
    """Reinicia o socket da instância na Evolution API."""
    ok = await whatsapp_service.restart_instance()
    return {
        "status": "success" if ok else "error",
        "instance": settings.EVOLUTION_INSTANCE,
        "restarted": ok,
    }

