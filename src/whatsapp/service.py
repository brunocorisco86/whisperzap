"""Serviço Nativo de Integração e Webhooks do WhatsApp / Evolution API.

Permite que o Hermes Voice Memory processe diretamente eventos da Evolution API
(áudios, transcrições, revisões contextuais, comandos '?' do Hermes Agent,
captura inteligente de notas e tarefas pessoais e persistência no Grafo)
eliminando a necessidade de intermediários como o n8n no Monólito.
"""

import os
import re
import uuid
import time
import base64
import logging
import tempfile
from threading import Lock
from typing import Any, Dict, Optional, Tuple
import httpx
from sqlalchemy.orm import Session

from src.config import settings
from src.transcriber.service import whisper_service
from src.ai_gateway.providers import get_ai_provider
from src.ai_gateway.prompts import REVISE_USER_TEMPLATE, REVISE_SYSTEM_PROMPT
from src.ai_gateway.bypass import is_owner_interaction
from src.memory.repository import memory_repository
from src.memory.models import MessageCreate, TaskRecord
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


def format_terpsicore_task_verbose(task: TaskRecord) -> str:
    """Gera representação detalhada e verbosa de uma tarefa com todos os atributos estratégicos de Terpsícore."""
    prio = (task.priority or "MEDIUM").upper()
    prio_map = {
        "URGENT": "🔴 *[URGENTE]*",
        "HIGH": "🟠 *[ALTA]*",
        "MEDIUM": "🔵 *[MÉDIA]*",
        "LOW": "⚪ *[BAIXA]*",
    }
    prio_label = prio_map.get(prio, f"📌 *[{prio}]*")

    lines = [f"• {prio_label} *{task.title}*"]

    # Marcadores estratégicos
    badges = []
    if getattr(task, "is_favorite", False):
        badges.append("⭐ *Favorito*")
    if getattr(task, "is_epic", False):
        badges.append("🏛️ *Objetivo Épico*")
    if getattr(task, "is_idea", False):
        badges.append("💡 *Ideia/Semente*")

    if badges:
        lines.append(f"  └ {' │ '.join(badges)}")

    # Segregação Baú (Vault) vs Fluxo Ativo Imediato
    details = []
    if getattr(task, "in_vault", False):
        vault_reason_str = f" ({task.vault_reason})" if getattr(task, "vault_reason", None) else ""
        details.append(f"🗝️ *No Baú (Vault)*{vault_reason_str}")
    else:
        details.append("⚡ *Fluxo Imediato*")

    if task.due_date:
        details.append(f"📅 Prazo: {task.due_date}")

    if task.assignee:
        details.append(f"👤 Resp: {task.assignee}")

    if getattr(task, "procrastination_factor", None):
        details.append(f"⏱️ Radar: {task.procrastination_factor}")

    if details:
        lines.append(f"  └ {' • '.join(details)}")

    return "\n".join(lines)


class WhatsAppService:
    """Motor central de comunicação e processamento de eventos do WhatsApp via Evolution API."""

    def __init__(self):
        self.api_url = settings.EVOLUTION_API_URL.rstrip("/")
        self.api_key = settings.EVOLUTION_API_KEY
        self.instance = settings.EVOLUTION_INSTANCE
        self._processed_keys: Dict[str, float] = {}
        self._keys_lock = Lock()

    def _clean_old_keys(self, ttl_seconds: float = 3600.0) -> None:
        """Remove identificadores de mensagens mais antigos que o TTL."""
        now = time.time()
        with self._keys_lock:
            expired = [k for k, ts in self._processed_keys.items() if now - ts > ttl_seconds]
            for k in expired:
                del self._processed_keys[k]

    def is_key_duplicate_or_processing(self, key_id: str, db: Optional[Session] = None) -> bool:
        """Verifica de forma atômica se uma mensagem/áudio com o mesmo key_id já foi processado ou está em processamento."""
        if not key_id or key_id.startswith("msg_"):
            return False

        self._clean_old_keys()

        # 1. Checagem rápida no cache em memória do processo
        with self._keys_lock:
            if key_id in self._processed_keys:
                return True

        # 2. Persistência e lock atômico no banco de dados (distribuído entre workers/containers)
        if db is not None:
            try:
                from src.memory.models import WebhookKeyRecord, MessageRecord
                # Verifica se já existe em WebhookKeyRecord
                exists_key = db.query(WebhookKeyRecord.key_id).filter(WebhookKeyRecord.key_id == key_id).first()
                if exists_key:
                    with self._keys_lock:
                        self._processed_keys[key_id] = time.time()
                    return True

                # Tenta inserir atomicamente o lock
                lock_rec = WebhookKeyRecord(key_id=key_id, status="PROCESSING")
                db.add(lock_rec)
                db.commit()

                with self._keys_lock:
                    self._processed_keys[key_id] = time.time()
                return False
            except Exception as exc:
                db.rollback()
                logger.debug(f"Chave duplicada ou erro de concorrência detectado no banco ({key_id}): {exc}")
                with self._keys_lock:
                    self._processed_keys[key_id] = time.time()
                return True

        # Fallback apenas em memória caso não haja DB
        with self._keys_lock:
            self._processed_keys[key_id] = time.time()
        return False

    def _is_owner_number(self, phone: str) -> bool:
        """Verifica se o número de telefone pertence estritamente ao proprietário do sistema."""
        owner = sanitize_phone_number(settings.USER_PHONE_NUMBER)
        clean = sanitize_phone_number(phone)
        if not clean or not owner:
            return False
        return clean == owner or clean.endswith(owner[-8:]) or owner.endswith(clean[-8:])

    async def send_text_message(self, number: str, text: str) -> bool:
        """Envia mensagem de texto para o WhatsApp, com trava MANDATÓRIA E INEGOCIÁVEL de envio EXCLUSIVO ao proprietário."""
        if not text or not text.strip():
            return False

        owner_number = sanitize_phone_number(settings.USER_PHONE_NUMBER)
        target_number = sanitize_phone_number(number)

        # 🛡️ TRAVA ABSOLUTA DE PRIVACIDADE: Nunca enviar para contatos de terceiros
        if not self._is_owner_number(target_number):
            logger.error(
                f"🚨 [BLOQUEIO TOTAL DE SEGURANÇA] Tentativa de envio para terceiro ({target_number}) CANCELADA IMEDIATAMENTE. "
                f"Nenhuma mensagem foi disparada."
            )
            return False

        clean_number = owner_number
        if not clean_number:
            logger.error("Número do proprietário não configurado para envio de WhatsApp.")
            return False

        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "number": clean_number,
            "text": text.strip(),
        }

        target_url = f"{self.api_url}/message/sendText/{self.instance}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(target_url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    logger.info(f"✅ Mensagem enviada com sucesso para o proprietário ({clean_number}).")
                    return True
                logger.error(f"Erro ao enviar mensagem WhatsApp ({resp.status_code}): {resp.text}")
        except Exception as exc:
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

        target_url = f"{self.api_url}/chat/getBase64FromMediaMessage/{self.instance}"

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
            logger.error(f"Exceção ao baixar mídia base64 ({message_id}): {exc}")

        return None

    def extract_message_info(self, raw_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normaliza os formatos de payload de webhook da Evolution API v1/v2."""
        # Se vier encapsulado em { "body": { ... } }
        payload = raw_payload.get("body") if isinstance(raw_payload.get("body"), dict) else raw_payload

        # Ignora eventos que não representam nova mensagem (ex: updates de status, presence, etc.)
        event_name = str(raw_payload.get("event") or payload.get("event") or "").strip().lower()
        if event_name and not any(ev in event_name for ev in ["messages.upsert", "messages_upsert", "send.message", "send_message", "message"]):
            logger.debug(f"Evento WhatsApp ignorado ({event_name}).")
            return None

        # Se for evento messages.upsert / messages.update
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

        key = data.get("key") or {}
        remote_jid = key.get("remoteJid") or data.get("remoteJid") or ""
        key_id = key.get("id") or data.get("id") or f"msg_{uuid.uuid4().hex[:8]}"
        from_me = bool(key.get("fromMe", False))

        sender_raw = payload.get("sender")
        sender_push = sender_raw.get("pushName") if isinstance(sender_raw, dict) else None
        push_name = data.get("pushName") or sender_push or "Desconhecido"
        is_group = bool(data.get("isGroup") or key.get("participant") or "@g.us" in remote_jid or "@broadcast" in remote_jid)

        msg_obj = data.get("message") or {}
        msg_type = str(data.get("messageType") or payload.get("messageType") or "").lower()

        # Extrai áudio em base64 direto se fornecido pelo webhook da Evolution API
        direct_base64 = (
            msg_obj.get("base64")
            or (msg_obj.get("audioMessage") or {}).get("base64")
            or (msg_obj.get("documentMessage") or {}).get("base64")
            or data.get("base64")
            or (payload.get("base64") if isinstance(payload, dict) else None)
            or ""
        )

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
            or bool(direct_base64 and "audio" in str(msg_obj))
            or (
                "document" in msg_type
                and str((msg_obj.get("documentMessage") or {}).get("mimetype") or "").startswith("audio/")
            )
        )

        # Detecta se é mídia ignorável (sticker, reação, localização)
        is_ignorable = any(ign in msg_type for ign in ["sticker", "reaction", "location", "contact"])

        # Detecta se é mensagem histórica de sincronização (idade > 60s)
        raw_ts = data.get("messageTimestamp") or payload.get("messageTimestamp") or 0
        try:
            msg_ts = float(raw_ts)
            # Se vier em milissegundos
            if msg_ts > 1000000000000:
                msg_ts = msg_ts / 1000.0
            is_historic = bool(msg_ts > 0 and (time.time() - msg_ts > 60.0))
        except Exception:
            is_historic = False

        # Resolução estrita de Self-Memo (conversa consigo mesmo)
        raw_number = sanitize_phone_number(remote_jid)
        owner_clean = sanitize_phone_number(settings.USER_PHONE_NUMBER)
        is_chat_with_self = bool(
            raw_number and owner_clean and (
                raw_number == owner_clean or raw_number.endswith(owner_clean[-8:]) or owner_clean.endswith(raw_number[-8:])
            )
        )
        is_self_memo = bool(from_me and is_chat_with_self)

        return {
            "key_id": key_id,
            "remote_jid": remote_jid,
            "phone_number": owner_clean if is_self_memo else raw_number,
            "from_me": from_me,
            "push_name": push_name,
            "is_group": is_group,
            "has_audio": has_audio,
            "is_ignorable": is_ignorable,
            "is_historic": is_historic,
            "is_self_memo": is_self_memo,
            "text": str(text_content).strip(),
            "direct_base64": direct_base64.strip() if direct_base64 else "",
            "raw_data": data,
        }

    async def process_webhook_event_task(
        self,
        payload: Dict[str, Any],
        info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Processa evento de webhook em background com sessão própria do banco de dados."""
        db = SessionLocal()
        try:
            await self.process_webhook_event(payload=payload, db=db, pre_extracted_info=info)
        except Exception as exc:
            logger.error(f"Erro no processamento assíncrono do webhook WhatsApp: {exc}", exc_info=True)
        finally:
            db.close()

    async def process_webhook_event(
        self,
        payload: Dict[str, Any],
        db: Optional[Session] = None,
        pre_extracted_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Orquestra o fluxo de ponta a ponta nativamente em Python:
        1. Filtra grupos e mídias vazias;
        2. Bloqueia mensagens históricas de disparar automações de saída;
        3. Se áudio de nota pessoal consigo mesmo: Transcreve -> Revisa -> Salva -> Responde no chat pessoal;
        4. Mensagens de terceiros ou chats normais: Apenas arquiva silenciosamente no Grafo sem NENHUM envio.
        """
        info = pre_extracted_info or self.extract_message_info(payload)
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

        # 3. Prevenção estrita de loop de eco de respostas geradas pelo próprio bot
        raw_text = info["text"]
        BOT_PREFIXES = ("🎙️", "📋", "🤖", "💡", "⚖️", "📝", "🌙", "📊", "✅", "Salve,")
        if any(raw_text.startswith(p) for p in BOT_PREFIXES):
            logger.debug("Mensagem do bot descartada para evitar eco.")
            return {"status": "ignored", "reason": "bot_echo_response"}

        is_self_memo = info.get("is_self_memo", False)
        is_historic = info.get("is_historic", False)
        speaker_label = f"{info['push_name']} (Nota Pessoal)" if is_self_memo else info["push_name"]

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            # ===================== FLUXO DE ÁUDIO =====================
            if info["has_audio"]:
                logger.info(f"🎙️ Processando áudio WhatsApp de {info['push_name']} [Self-Memo: {is_self_memo}, Histórico: {is_historic}]...")

                base64_str = info.get("direct_base64") or await self.get_media_base64(
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
                    raw_text_audio, lang, prob, duration, segments, prosody = await whisper_service.transcribe_audio(
                        audio_path_or_file=tmp_path,
                        language="pt",
                        speaker=speaker_label,
                    )
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass

                if not raw_text_audio or not raw_text_audio.strip():
                    logger.warning("Áudio sem fala identificável.")
                    return {"status": "processed", "type": "audio", "text": "", "reason": "empty_transcription"}

                # 2. Revisão Contextual via AI Gateway
                revised_text = raw_text_audio
                try:
                    provider = get_ai_provider(task="revise")
                    prompt = REVISE_USER_TEMPLATE.format(
                        raw_text=raw_text_audio.strip(),
                        context_block=f"Contexto: Mensagem de voz de {speaker_label}.",
                    )
                    revised_text = await provider.generate_text(
                        prompt=prompt,
                        system_instruction=REVISE_SYSTEM_PROMPT,
                        temperature=0.1,
                    )
                except Exception as e:
                    logger.warning(f"Fallback para texto bruto devido a erro no AI Gateway: {e}")

                # 3. Salva na Memória e Grafo (executa extração de tarefas e entidades)
                prosody_data = None
                if prosody:
                    prosody_data = prosody.model_dump() if hasattr(prosody, "model_dump") else (prosody.dict() if hasattr(prosody, "dict") else dict(prosody))

                msg_in = MessageCreate(
                    speaker=speaker_label,
                    raw_text=raw_text_audio,
                    revised_text=revised_text,
                    audio_filename=f"{info['key_id']}.ogg",
                    audio_duration_s=float(duration or 0.0),
                    prosody_metrics=prosody_data,
                    meta_info={
                        "source": "whatsapp",
                        "message_type": "audio",
                        "is_self_memo": is_self_memo,
                        "remoteJid": info["remote_jid"],
                        "pushName": info["push_name"],
                        "key_id": info["key_id"],
                    },
                )
                saved_msg = await memory_repository.save_message(data=msg_in, db=db)

                # 4. Envia transcrição no WhatsApp EXCLUSIVAMENTE para o proprietário se for áudio recente
                if not is_historic:
                    created_tasks = []
                    if saved_msg:
                        created_tasks = db.query(TaskRecord).filter(TaskRecord.message_id == saved_msg.id).all()

                    if is_self_memo:
                        reply_lines = [f"🎙️ *Nota Pessoal Gravada:*", f'"{revised_text.strip()}"']
                    else:
                        contact_name = info.get("push_name") or "Contato"
                        contact_phone = sanitize_phone_number(info.get("remote_jid", ""))
                        phone_badge = f" ({contact_phone})" if contact_phone and contact_phone != contact_name else ""
                        reply_lines = [f"🎙️ *Áudio Recebido de:* {contact_name}{phone_badge}", f'"{revised_text.strip()}"']

                    if created_tasks:
                        reply_lines.append("")
                        has_signaled = any(
                            getattr(t, "is_favorite", False)
                            or getattr(t, "is_epic", False)
                            or getattr(t, "is_idea", False)
                            or getattr(t, "in_vault", False)
                            or (str(t.priority or "").upper() in ["HIGH", "URGENT"])
                            for t in created_tasks
                        )
                        section_title = "📋 *Tarefas Sinalizadas (Terpsícore):*" if has_signaled else "📋 *Tarefas Capturadas (Terpsícore):*"
                        reply_lines.append(section_title)
                        for t in created_tasks:
                            reply_lines.append(format_terpsicore_task_verbose(t))
                    elif getattr(saved_msg, "intent", None) == "IDEA":
                        reply_lines.append("")
                        reply_lines.append("💡 *Classificação:* 🧠 Ideia / Insight Estratégico (salvo no Grafo)")
                    elif getattr(saved_msg, "intent", None) == "DECISION":
                        reply_lines.append("")
                        reply_lines.append("⚖️ *Classificação:* Decisão Registrada (salvo no Grafo)")
                    elif is_self_memo:
                        reply_lines.append("")
                        reply_lines.append("📝 *Classificação:* Nota Pessoal (Memória & Grafo)")

                    reply_text = "\n".join(reply_lines)
                    await self.send_text_message(number=settings.USER_PHONE_NUMBER, text=reply_text)
                else:
                    logger.info(f"🎧 Áudio histórico arquivado silenciosamente na memória passiva (sem envio de mensagem).")

                return {
                    "status": "success",
                    "type": "audio",
                    "is_self_memo": is_self_memo,
                    "message_id": saved_msg.id if saved_msg else None,
                    "text": revised_text,
                    "speaker": speaker_label,
                }

            # ===================== FLUXO DE TEXTO =====================
            if not raw_text:
                return {"status": "ignored", "reason": "empty_text"}

            # 1. Detecção de Pergunta para o Hermes Agent ('?', '/hermes', 'hermes,') - Apenas em Self-Memo ou mensagem do proprietário
            hermes_match = re.match(r"^(\?|/hermes|hermes,)\s*(.*)", raw_text, flags=re.IGNORECASE)
            is_owner = is_owner_interaction(speaker=speaker_label, meta_info=info.get("raw_data"))
            if hermes_match and (is_self_memo or is_owner) and not is_historic:
                query_str = hermes_match.group(2).strip()
                if not query_str:
                    query_str = "Quais são as tarefas pendentes mais recentes?"

                logger.info(f"🧠 Consulta interativa ao Hermes Agent recebida do proprietário: '{query_str}'")

                answer_resp = await memory_repository.query_hermes_rag(
                    query=query_str,
                    top_k=5,
                    min_similarity=0.35,
                    db=db,
                )
                answer_text = answer_resp.answer

                # Se a consulta for sobre tarefas, anexa bloco enriquecido com tarefas sinalizadas do Terpsícore
                if any(w in query_str.lower() for w in ["tarefa", "tarefas", "pendencia", "pendência", "pendencias", "pendências", "fazer"]):
                    signaled_tasks = (
                        db.query(TaskRecord)
                        .filter(
                            TaskRecord.status == "PENDING",
                            (
                                (TaskRecord.is_favorite == True)
                                | (TaskRecord.is_epic == True)
                                | (TaskRecord.is_idea == True)
                                | (TaskRecord.priority.in_(["HIGH", "URGENT"]))
                            )
                        )
                        .order_by(TaskRecord.created_at.desc())
                        .limit(5)
                        .all()
                    )
                    if signaled_tasks:
                        task_lines = ["\n\n📋 *Tarefas Sinalizadas no Radar (Terpsícore):*"]
                        for st in signaled_tasks:
                            task_lines.append(format_terpsicore_task_verbose(st))
                        answer_text += "\n".join(task_lines)

                # Envia resposta interativa EXCLUSIVAMENTE para o proprietário
                await self.send_text_message(number=settings.USER_PHONE_NUMBER, text=answer_text)

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

            # 3. Salva Mensagem de Texto na Memória e Grafo (SILENCIOSO: NUNCA envia mensagens de WhatsApp para texto comum)
            msg_in = MessageCreate(
                speaker=speaker_label,
                raw_text=raw_text,
                revised_text=raw_text,
                meta_info={
                    "source": "whatsapp",
                    "message_type": "text",
                    "is_self_memo": is_self_memo,
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
                "is_self_memo": is_self_memo,
                "message_id": saved_msg.id if saved_msg else None,
                "bypass_ai": bypass_ai,
            }

        finally:
            if should_close:
                db.close()


whatsapp_service = WhatsAppService()
