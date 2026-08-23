"""Serviço Nativo de Integração e Webhooks do WhatsApp / Evolution API.

Permite que o Hermes Voice Memory processe diretamente eventos da Evolution API
(áudios, transcrições, revisões contextuais, comandos '?' do Hermes Agent e persistência)
eliminando a necessidade de intermediários como o n8n no Monólito.
"""

import os
import re
import uuid
import base64
import logging
import tempfile
from typing import Any, Dict, Optional, Tuple
import httpx
from sqlalchemy.orm import Session

from src.config import settings
from src.contacts.service import get_evolution_working_proxy, invalidate_evolution_proxy_cache
from src.transcriber.service import whisper_service
from src.ai_gateway.providers import get_ai_provider
from src.ai_gateway.prompts import REVISE_USER_TEMPLATE
from src.memory.repository import memory_repository
from src.memory.models import MessageCreate
from src.ai_gateway.agent import hermes_agent_service
from src.memory.database import SessionLocal

logger = logging.getLogger(__name__)

# Padrões triviais / saudações para bypass de IA em textos curtos
TRIVIAL_GREETINGS = {
    "bom dia", "boa tarde", "boa noite", "oi", "ola", "olá",
    "ok", "beleza", "valeu", "obrigado", "obrigada", "sim", "não", "nao", "tchau", "opa", "blz"
}


def sanitize_phone_number(jid_or_number: str) -> str:
    """Extrai apenas os dígitos do número de telefone WhatsApp."""
    if not jid_or_number:
        return ""
    clean = jid_or_number.split("@")[0].split(":")[0]
    return re.sub(r"\D", "", clean)


class WhatsAppService:
    """Motor central de comunicação e processamento de eventos do WhatsApp via Evolution API."""

    def __init__(self):
        self.api_url = settings.EVOLUTION_API_URL.rstrip("/")
        self.api_key = settings.EVOLUTION_API_KEY
        self.instance = settings.EVOLUTION_INSTANCE

    async def send_text_message(self, number: str, text: str) -> bool:
        """Envia mensagem de texto para um número no WhatsApp via Evolution API."""
        if not number or not text:
            logger.warning("Tentativa de envio de mensagem vazia ou sem número.")
            return False

        clean_number = sanitize_phone_number(number)
        if not clean_number:
            logger.warning(f"Número inválido para envio: {number}")
            return False

        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "number": clean_number,
            "text": text.strip(),
        }

        proxy = await get_evolution_working_proxy()
        base_url = proxy.rstrip("/") if proxy else self.api_url
        target_url = f"{base_url}/message/sendText/{self.instance}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(target_url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    logger.info(f"✅ Mensagem enviada com sucesso para {clean_number}.")
                    return True
                logger.error(f"Erro ao enviar mensagem WhatsApp ({resp.status_code}): {resp.text}")
        except Exception as exc:
            invalidate_evolution_proxy_cache()
            logger.error(f"Exceção ao enviar mensagem WhatsApp para {clean_number}: {exc}")

        return False

    async def get_media_base64(
        self,
        message_id: str,
        remote_jid: str,
        from_me: bool = False,
    ) -> Optional[str]:
        """Baixa o arquivo de mídia (áudio/documento) em base64 da Evolution API."""
        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "message": {
                "key": {
                    "id": message_id,
                    "fromMe": from_me,
                    "remoteJid": remote_jid,
                }
            },
            "convertToMp4": False,
        }

        proxy = await get_evolution_working_proxy()
        base_url = proxy.rstrip("/") if proxy else self.api_url
        target_url = f"{base_url}/chat/getBase64FromMediaMessage/{self.instance}"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(target_url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    base64_val = data.get("base64") or (data.get("qrcode") or {}).get("base64") or ""
                    if base64_val:
                        return base64_val
                logger.warning(f"Falha ao obter mídia base64 ({resp.status_code}): {resp.text[:150]}")
        except Exception as exc:
            invalidate_evolution_proxy_cache()
            logger.error(f"Exceção ao baixar mídia base64 ({message_id}): {exc}")

        return None

    def extract_message_info(self, raw_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normaliza os formatos de payload de webhook da Evolution API v1/v2."""
        # Se vier encapsulado em { "body": { ... } }
        payload = raw_payload.get("body") if isinstance(raw_payload.get("body"), dict) else raw_payload

        # Se for evento messages.upsert / messages.update
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

        key = data.get("key") or {}
        remote_jid = key.get("remoteJid") or data.get("remoteJid") or ""
        key_id = key.get("id") or data.get("id") or f"msg_{uuid.uuid4().hex[:8]}"
        from_me = bool(key.get("fromMe", False))
        push_name = data.get("pushName") or payload.get("sender", {}).get("pushName") or "Desconhecido"
        is_group = bool(data.get("isGroup") or key.get("participant") or "@g.us" in remote_jid or "@broadcast" in remote_jid)

        msg_obj = data.get("message") or {}
        msg_type = str(data.get("messageType") or payload.get("messageType") or "").lower()

        # Extrai texto direto se houver
        text_content = (
            msg_obj.get("conversation")
            or (msg_obj.get("extendedTextMessage") or {}).get("text")
            or msg_obj.get("text")
            or data.get("text")
            or ""
        )

        # Detecta se é áudio
        has_audio = (
            "audio" in msg_type
            or bool(msg_obj.get("audioMessage"))
            or (
                "document" in msg_type
                and str((msg_obj.get("documentMessage") or {}).get("mimetype") or "").startswith("audio/")
            )
        )

        # Detecta se é mídia ignorável (sticker, reação, localização)
        is_ignorable = any(ign in msg_type for ign in ["sticker", "reaction", "location", "contact"])

        return {
            "key_id": key_id,
            "remote_jid": remote_jid,
            "phone_number": sanitize_phone_number(remote_jid),
            "from_me": from_me,
            "push_name": push_name,
            "is_group": is_group,
            "has_audio": has_audio,
            "is_ignorable": is_ignorable,
            "text": str(text_content).strip(),
            "raw_data": data,
        }

    async def process_webhook_event(
        self,
        payload: Dict[str, Any],
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Orquestra o fluxo de ponta a ponta nativamente em Python:
        1. Filtra grupos e mídias vazias;
        2. Se áudio: Baixa Base64 -> Whisper -> AI Revise -> Responde WhatsApp -> Salva Memória;
        3. Se texto: Trata perguntas '?' do Hermes Agent ou salva memória com bypass.
        """
        info = self.extract_message_info(payload)
        if not info:
            return {"status": "ignored", "reason": "invalid_payload"}

        # 1. Filtro de Grupos e Broadcasts
        if info["is_group"]:
            logger.debug(f"Mensagem de grupo ou broadcast ignorada ({info['remote_jid']}).")
            return {"status": "ignored", "reason": "group_or_broadcast"}

        # 2. Filtro de Mídias sem Conteúdo Textual (Stickers, Reações)
        if info["is_ignorable"]:
            logger.debug(f"Mídia ignorada ({info['key_id']}).")
            return {"status": "ignored", "reason": "ignorable_media_type"}

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            # ===================== FLUXO DE ÁUDIO =====================
            if info["has_audio"]:
                logger.info(f"🎙️ Processando áudio WhatsApp de {info['push_name']} ({info['phone_number']})...")

                base64_str = await self.get_media_base64(
                    message_id=info["key_id"],
                    remote_jid=info["remote_jid"],
                    from_me=info["from_me"],
                )
                if not base64_str:
                    logger.warning(f"Não foi possível obter áudio base64 para {info['key_id']}.")
                    return {"status": "error", "reason": "base64_download_failed"}

                if "," in base64_str:
                    base64_str = base64_str.split(",", 1)[1]

                try:
                    audio_bytes = base64.b64decode(base64_str)
                except Exception as e:
                    logger.error(f"Erro ao decodificar base64 do áudio: {e}")
                    return {"status": "error", "reason": "base64_decode_error"}

                with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                    tmp_path = tmp.name
                    tmp.write(audio_bytes)

                try:
                    # 1. Transcrição Whisper com priming e prosódia
                    raw_text, lang, prob, duration, segments, prosody = await whisper_service.transcribe_audio(
                        audio_path_or_file=tmp_path,
                        language="pt",
                        speaker=info["push_name"],
                    )
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass

                if not raw_text or not raw_text.strip():
                    logger.warning("Áudio sem fala identificável.")
                    return {"status": "processed", "type": "audio", "text": "", "reason": "empty_transcription"}

                # 2. Revisão Contextual via AI Gateway
                revised_text = raw_text
                try:
                    provider = get_ai_provider(task="revise")
                    prompt = REVISE_USER_TEMPLATE.format(
                        raw_text=raw_text.strip(),
                        context_block=f"Contexto: Mensagem de voz de {info['push_name']}.",
                    )
                    revised_text = await provider.generate_text(
                        prompt=prompt,
                        temperature=0.1,
                    )
                except Exception as e:
                    logger.warning(f"Fallback para texto bruto devido a erro no AI Gateway: {e}")

                # 3. Envia Transcrição de volta no WhatsApp
                # Envia apenas se não foi mensagem enviada pelo próprio bot
                if not info["from_me"]:
                    reply_text = f"🎙️ *Transcrição:* {revised_text.strip()}"
                    await self.send_text_message(number=info["phone_number"], text=reply_text)

                # 4. Salva na Memória e Grafo
                prosody_data = None
                if prosody:
                    prosody_data = prosody.model_dump() if hasattr(prosody, "model_dump") else (prosody.dict() if hasattr(prosody, "dict") else dict(prosody))

                msg_in = MessageCreate(
                    speaker=info["push_name"],
                    raw_text=raw_text,
                    revised_text=revised_text,
                    audio_filename=f"{info['key_id']}.ogg",
                    audio_duration_s=float(duration or 0.0),
                    prosody_metrics=prosody_data,
                    meta_info={
                        "source": "whatsapp",
                        "message_type": "audio",
                        "remoteJid": info["remote_jid"],
                        "pushName": info["push_name"],
                        "key_id": info["key_id"],
                    },
                )
                saved_msg = await memory_repository.save_message(data=msg_in, db=db)

                return {
                    "status": "success",
                    "type": "audio",
                    "message_id": saved_msg.id if saved_msg else None,
                    "text": revised_text,
                    "speaker": info["push_name"],
                }

            # ===================== FLUXO DE TEXTO =====================
            raw_text = info["text"]
            if not raw_text:
                return {"status": "ignored", "reason": "empty_text"}

            # 1. Detecção de Pergunta para o Hermes Agent ('?', '/hermes', 'hermes,')
            hermes_match = re.match(r"^(\?|/hermes|hermes,)\s*(.*)", raw_text, flags=re.IGNORECASE)
            if hermes_match:
                query_str = hermes_match.group(2).strip()
                if not query_str:
                    query_str = "Quais são as tarefas pendentes mais recentes?"

                logger.info(f"🧠 Consulta interativa ao Hermes Agent recebida: '{query_str}'")

                answer_resp = await memory_repository.query_hermes_rag(
                    query=query_str,
                    top_k=5,
                    min_similarity=0.35,
                    db=db,
                )
                answer_text = answer_resp.answer

                if not info["from_me"]:
                    await self.send_text_message(number=info["phone_number"], text=answer_text)

                return {
                    "status": "success",
                    "type": "hermes_query",
                    "query": query_str,
                    "answer": answer_text,
                }

            # 2. Detecção de Saudação / Phatic Bypass
            clean_t = re.sub(r"[^\w\s]", "", raw_text.lower()).strip()
            bypass_ai = (
                len(raw_text) <= 15
                or clean_t in TRIVIAL_GREETINGS
                or len(clean_t.split()) <= 2
            )

            # 3. Salva Mensagem de Texto na Memória
            msg_in = MessageCreate(
                speaker=info["push_name"],
                raw_text=raw_text,
                revised_text=raw_text,
                meta_info={
                    "source": "whatsapp",
                    "message_type": "text",
                    "bypass_ai": bypass_ai,
                    "remoteJid": info["remote_jid"],
                    "pushName": info["push_name"],
                    "key_id": info["key_id"],
                },
            )
            saved_msg = await memory_repository.save_message(data=msg_in, db=db)

            return {
                "status": "success",
                "type": "text",
                "message_id": saved_msg.id if saved_msg else None,
                "bypass_ai": bypass_ai,
            }

        finally:
            if should_close:
                db.close()


whatsapp_service = WhatsAppService()
