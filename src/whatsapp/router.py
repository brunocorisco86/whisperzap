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
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Recebe e processa eventos do WhatsApp da Evolution API de forma nativa e assíncrona."""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "error", "message": "JSON body inválido"}

    # Processamento direto
    result = await whatsapp_service.process_webhook_event(payload=payload, db=db)
    return result


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
