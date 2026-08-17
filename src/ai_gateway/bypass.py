"""Módulo de detecção de Bypass de IA, mensagens triviais, filtros de grupos e identificação de proprietário."""

import re
import unicodedata
from typing import Any, Dict, Optional, Tuple
from src.config import settings


def normalize_text(text: str) -> str:
    """Remove acentuação, caracteres especiais extras e normaliza espaços."""
    if not text:
        return ""
    # Normaliza unicode
    nfkd = unicodedata.normalize("NFKD", text)
    clean_ascii = "".join([c for c in nfkd if not unicodedata.combining(c)])
    # Remove pontuações desnecessárias mantendo alfanuméricos e espaços
    clean = re.sub(r"[^\w\s]", " ", clean_ascii.lower())
    return re.sub(r"\s+", " ", clean).strip()


def is_group_message(meta_info: Optional[Dict[str, Any]] = None) -> bool:
    """Verifica se a mensagem é proveniente de um grupo ou lista de transmissão do WhatsApp."""
    if not meta_info or not isinstance(meta_info, dict):
        return False

    remote_jid = str(meta_info.get("remoteJid") or meta_info.get("remote_jid") or "").strip()
    if remote_jid.endswith("@g.us") or "@g.us" in remote_jid:
        return True
    if remote_jid.endswith("@broadcast") or "broadcast" in remote_jid:
        return True

    if meta_info.get("isGroup") is True or meta_info.get("is_group") is True:
        return True

    if meta_info.get("participant") or meta_info.get("participantJid"):
        return True

    return False


def get_owner_identifiers() -> set[str]:
    """Retorna o conjunto de identificadores associados ao dono do sistema (Bruno Conter)."""
    identifiers = {"bruno", "bruno conter", "bruno conter 🐔🇧🇷", "corisco", "brunao", "brunão", "você", "voce", "eu", "me", "admin"}
    if settings.USER_PHONE_NUMBER:
        digits = re.sub(r"\D", "", settings.USER_PHONE_NUMBER)
        if digits:
            identifiers.add(digits)
            if len(digits) >= 8:
                identifiers.add(digits[-8:])  # Últimos 8 dígitos para matching sem DDI/DDD/9º dígito

    if settings.USER_NAME:
        identifiers.add(settings.USER_NAME.strip().lower())
        identifiers.add(normalize_text(settings.USER_NAME))

    if settings.USER_ALIASES:
        for alias in settings.USER_ALIASES.split(","):
            cleaned = alias.strip().lower()
            if cleaned:
                identifiers.add(cleaned)
                identifiers.add(normalize_text(cleaned))
                digits = re.sub(r"\D", "", cleaned)
                if digits and len(digits) >= 8:
                    identifiers.add(digits)
                    identifiers.add(digits[-8:])

    return identifiers


def is_owner_interaction(speaker: Optional[str] = None, meta_info: Optional[Dict[str, Any]] = None) -> bool:
    """Verifica com alta precisão se uma mensagem/áudio foi gerada pelo próprio Bruno (notas pessoais ou mensagens enviadas)."""
    owner_ids = get_owner_identifiers()
    owner_suffix = re.sub(r"\D", "", settings.USER_PHONE_NUMBER)[-8:] if settings.USER_PHONE_NUMBER else "97604925"

    # 1. Verifica flag fromMe do WhatsApp
    if meta_info and isinstance(meta_info, dict):
        if meta_info.get("fromMe") is True or meta_info.get("fromMe") == 1 or meta_info.get("from_me") is True:
            return True

        remote_jid = str(meta_info.get("remoteJid") or meta_info.get("remote_jid") or "")
        sender_phone = str(meta_info.get("phone") or meta_info.get("sender_phone") or "")
        push_name = str(meta_info.get("pushName") or "").strip().lower()

        remote_digits = re.sub(r"\D", "", remote_jid.split("@")[0])
        sender_digits = re.sub(r"\D", "", sender_phone)

        if remote_digits and (remote_digits in owner_ids or remote_digits.endswith(owner_suffix)):
            return True
        if sender_digits and (sender_digits in owner_ids or sender_digits.endswith(owner_suffix)):
            return True
        if push_name and (push_name in owner_ids or "bruno" in push_name or "corisco" in push_name):
            return True

    # 2. Verifica speaker
    if speaker:
        speaker_clean = speaker.strip().lower()
        speaker_normalized = normalize_text(speaker)
        speaker_digits = re.sub(r"\D", "", speaker)

        if speaker_clean in owner_ids or speaker_normalized in owner_ids:
            return True
        if "bruno conter" in speaker_clean or "bruno" in speaker_clean.split():
            return True
        if speaker_digits and (speaker_digits in owner_ids or speaker_digits.endswith(owner_suffix)):
            return True

    return False


TRIVIAL_SOCIAL_PHRASES = {
    "bom dia", "boa tarde", "boa noite", "oi", "ola", "olá", "opa", "tudo bem", "como vai", "fala ai", "e ai", "eae",
    "valeu", "obrigado", "obrigada", "de nada", "por nada", "beleza", "blz", "show", "top", "combinado", "fechado",
    "ta bom", "tá bom", "ok", "certo", "falou", "tchau", "ate mais", "até mais", "partiu", "maravilha", "muito bom",
    "perfeito", "bacana", "que bacana", "dai tudo azul", "que lindo", "vai ter baile", "pilchado", "e os guri ne",
    "sim", "nao", "não", "aham", "uhum", "ta", "tá", "ok ok", "blz entao", "beleza entao", "fechou entao",
    "frango sentado", "paaaaa", "vai sair quando",
}

ACTION_AND_BUSINESS_KEYWORDS = {
    "silo", "silos", "lote", "lotes", "ração", "racao", "sensor", "calibração", "calibracao", "telemetria",
    "c.vale", "cvale", "miratorg", "mtech", "granja", "aviário", "aviario", "aviários", "fal", "fau",
    "relatório", "relatorio", "reunião", "reuniao", "tarefa", "prazo", "agendamento", "entregar", "enviar",
    "verificar", "alinhar", "revisar", "concluir", "fazer", "pagar", "comprar", "preço", "custo",
    "urgente", "amanhã", "amanha", "quinta", "sexta", "segunda", "terça", "terca", "quarta",
    "auditoria", "checklist", "exame", "consulta", "mortalidade", "conversão", "iep", "peso", "placa",
}


def has_business_or_action_intent(text: str) -> bool:
    """Verifica se o texto possui palavras-chave de ação, negócios, operações ou entidades."""
    clean = normalize_text(text)
    words = set(clean.split())
    if words.intersection(ACTION_AND_BUSINESS_KEYWORDS):
        return True
    return False


def is_emoji_only_or_symbols(text: str) -> bool:
    """Verifica se o texto é composto exclusivamente por emojis, pontuação, símbolos ou espaços."""
    if not text or not text.strip():
        return True
    alnum_only = re.sub(r"[^\w]", "", text)
    if len(alnum_only.strip()) == 0:
        return True
    return False


def should_drop_message(
    text: Optional[str],
    message_type: str = "text",
    meta_info: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Determina se a mensagem deve ser COMPLETAMENTE IGNORADA e NÃO SALVA no banco de dados,

    nem enviada para análise de agentes, histórico, embeddings ou word cloud.
    Garante que apenas conversas com real privilégio e densidade informativa sejam processadas.
    """
    # 1. Mensagens de grupo (se configurado para ignorar)
    if settings.IGNORE_GROUP_MESSAGES and is_group_message(meta_info):
        return True, "group_message"

    # 2. Tipos de mídia sem conteúdo textual ou sem suporte de fala
    non_text_types = {
        "sticker", "stickermessage", "sticker_message",
        "reaction", "reactionmessage", "reaction_message",
        "contactmessage", "contact_message", "locationmessage", "location_message",
        "imagemessage", "imagemessage", "videomessage", "video_message",
    }
    msg_type_str = str(message_type).lower().strip()
    if msg_type_str in non_text_types and (not text or not str(text).strip()):
        return True, f"non_text_media_{msg_type_str}"

    # 3. Mensagem sem texto ou nula (ex: áudio inaudível / ruído)
    if not text or not str(text).strip():
        return True, "empty_text"

    raw_clean = str(text).strip()
    clean = normalize_text(raw_clean)

    # 4. Mensagem composta apenas por emojis ou símbolos
    if not clean or is_emoji_only_or_symbols(raw_clean):
        return True, "only_emojis_or_symbols"

    # 5. Lista abrangente de saudações e ruído conversacional social
    if clean in TRIVIAL_SOCIAL_PHRASES:
        return True, "trivial_social_phrase"

    # Se configurado em .env AI_BYPASS_PHRASES adicionais
    if settings.AI_BYPASS_PHRASES:
        custom_phrases = [
            normalize_text(p) for p in settings.AI_BYPASS_PHRASES.split(",") if normalize_text(p)
        ]
        if clean in custom_phrases:
            return True, "custom_trivial_phrase"

    # 6. Avaliação de Densidade Informativa e Privilégio de Memória
    words = clean.split()
    # Se for uma pergunta/comando explícito para o agente
    is_direct_query = raw_clean.startswith("?") or raw_clean.startswith("/") or clean.startswith("hermes")

    # Mensagens muito curtas (< 20 caracteres e <= 3 palavras) sem palavras de negócio/ação e sem ser query
    if len(raw_clean) < 20 and len(words) <= 3 and not is_direct_query:
        if not has_business_or_action_intent(raw_clean):
            return True, "low_density_trivial"

    return False, "privileged_valid_message"


def should_bypass_ai(
    text: Optional[str],
    message_type: str = "text",
    meta_info: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Determina se a mensagem deve fazer bypass do processamento de IA (extração semântica e análise de sentimento).

    Retorna: (should_bypass: bool, reason: str)
    """
    # 1. Se deve ser descartada, automaticamente faz bypass
    should_drop, drop_reason = should_drop_message(text, message_type=message_type, meta_info=meta_info)
    if should_drop:
        return True, drop_reason

    # 2. Bypass explícito no payload
    if meta_info and isinstance(meta_info, dict):
        if meta_info.get("bypass_ai") is True or meta_info.get("bypass") is True:
            return True, "explicit_bypass"

    return False, "process_ai"

