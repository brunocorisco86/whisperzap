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
    """Retorna o conjunto de identificadores associados ao dono do sistema."""
    identifiers = set()
    if settings.USER_PHONE_NUMBER:
        digits = re.sub(r"\D", "", settings.USER_PHONE_NUMBER)
        if digits:
            identifiers.add(digits)

    if settings.USER_NAME:
        identifiers.add(settings.USER_NAME.strip().lower())

    if settings.USER_ALIASES:
        for alias in settings.USER_ALIASES.split(","):
            cleaned = alias.strip().lower()
            if cleaned:
                identifiers.add(cleaned)
                digits = re.sub(r"\D", "", cleaned)
                if digits and len(digits) >= 8:
                    identifiers.add(digits)

    return identifiers


def is_owner_interaction(speaker: Optional[str] = None, meta_info: Optional[Dict[str, Any]] = None) -> bool:
    """Verifica se uma interação/mensagem foi gerada pelo próprio usuário proprietário."""
    owner_ids = get_owner_identifiers()

    # Verifica speaker
    if speaker:
        speaker_clean = speaker.strip().lower()
        speaker_digits = re.sub(r"\D", "", speaker)
        if speaker_clean in owner_ids:
            return True
        if speaker_digits and speaker_digits in owner_ids:
            return True

    # Verifica meta_info
    if meta_info and isinstance(meta_info, dict):
        if meta_info.get("fromMe") is True or meta_info.get("fromMe") == 1 or meta_info.get("from_me") is True:
            return True

        remote_jid = str(meta_info.get("remoteJid") or meta_info.get("remote_jid") or "")
        sender_phone = str(meta_info.get("phone") or meta_info.get("sender_phone") or "")
        push_name = str(meta_info.get("pushName") or "").strip().lower()

        remote_digits = re.sub(r"\D", "", remote_jid.split("@")[0])
        sender_digits = re.sub(r"\D", "", sender_phone)

        if remote_digits and remote_digits in owner_ids:
            return True
        if sender_digits and sender_digits in owner_ids:
            return True
        if push_name and push_name in owner_ids:
            return True

    return False


def should_bypass_ai(
    text: Optional[str],
    message_type: str = "text",
    meta_info: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Determina se a mensagem deve fazer bypass do processamento de IA (extração semântica e análise de sentimento).

    Retorna: (should_bypass: bool, reason: str)
    """
    # 1. Bypass explícito no payload
    if meta_info and isinstance(meta_info, dict):
        if meta_info.get("bypass_ai") is True or meta_info.get("bypass") is True:
            return True, "explicit_bypass"

    # 2. Mensagens de grupo (se configurado para ignorar)
    if settings.IGNORE_GROUP_MESSAGES and is_group_message(meta_info):
        return True, "group_message"

    # 3. Tipos de mídia sem conteúdo textual ou sem suporte de fala (stickers, reações, etc.)
    non_text_types = {
        "sticker", "stickermessage", "sticker_message",
        "reaction", "reactionmessage", "reaction_message",
        "contactmessage", "contact_message", "locationmessage", "location_message",
    }
    if str(message_type).lower() in non_text_types:
        return True, "non_text_media_type"

    # 4. Mensagem sem texto ou nula
    if not text or not str(text).strip():
        return True, "empty_text"

    clean = normalize_text(str(text))
    raw_clean = str(text).strip()

    # Se após limpeza restou nada (ex: apenas emojis ou pontuação)
    if not clean:
        return True, "only_emojis_or_punctuation"

    # 5. Threshold de número de caracteres (ex: <= 15 caracteres)
    if len(raw_clean) <= settings.AI_BYPASS_CHAR_THRESHOLD:
        return True, f"char_threshold_under_{settings.AI_BYPASS_CHAR_THRESHOLD}"

    # 6. Threshold de número de palavras (ex: <= 3 palavras)
    words = clean.split()
    if len(words) <= settings.AI_BYPASS_WORD_THRESHOLD:
        return True, f"word_threshold_under_{settings.AI_BYPASS_WORD_THRESHOLD}"

    # 7. Frases ou saudações triviais configuradas
    if settings.AI_BYPASS_PHRASES:
        bypass_phrases = [
            normalize_text(p) for p in settings.AI_BYPASS_PHRASES.split(",") if normalize_text(p)
        ]
        if clean in bypass_phrases:
            return True, "trivial_phrase_match"

    return False, "process_ai"
