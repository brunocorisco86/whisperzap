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


def is_group_message(meta_info: Optional[Dict[str, Any]] = None, speaker: Optional[str] = None) -> bool:
    """Verifica se a mensagem ou contato é proveniente de um grupo ou lista de transmissão."""
    if speaker:
        speaker_str = str(speaker).strip()
        if speaker_str.endswith("@g.us") or "@g.us" in speaker_str or "broadcast" in speaker_str:
            return True

    if not meta_info or not isinstance(meta_info, dict):
        return False

    remote_jid = str(meta_info.get("remoteJid") or meta_info.get("remote_jid") or "").strip()
    if remote_jid.endswith("@g.us") or "@g.us" in remote_jid:
        return True
    if remote_jid.endswith("@broadcast") or "broadcast" in remote_jid or "newsletter" in remote_jid:
        return True

    if meta_info.get("isGroup") is True or meta_info.get("is_group") is True:
        return True

    if meta_info.get("participant") or meta_info.get("participantJid"):
        return True

    return False


def is_valid_contact_phone(phone: Optional[str]) -> bool:
    """Valida se o número de telefone possui a quantidade padrão de dígitos e formato válido.
    
    Números fora do padrão NÃO recebem UID e NÃO viram cartão de contato.
    - Padrão Nacional Brasil:
        - 10 dígitos: DDD (2) + Fixo (8) (ex: 4432001122)
        - 11 dígitos: DDD (2) + Celular (9) (ex: 44999214934)
        - 12 dígitos: DDI (55) + DDD (2) + 8 dígitos (ex: 554497604925)
        - 13 dígitos: DDI (55) + DDD (2) + 9 dígitos (ex: 5544999214934)
    - Padrão Internacional E.164: entre 10 e 15 dígitos numéricos sem caracteres de grupo.
    """
    if not phone or not isinstance(phone, (str, int)):
        return False

    raw = str(phone).strip()
    # Bloqueia identificadores de grupos ou canais
    if "@g.us" in raw or "broadcast" in raw or "newsletter" in raw:
        return False

    digits = re.sub(r"\D", "", raw.split("@")[0])
    num_len = len(digits)

    # Rejeita números com menos de 10 ou mais de 15 dígitos
    if num_len < 10 or num_len > 15:
        return False

    # Validação específica para números que começam com DDI 55 (Brasil)
    if digits.startswith("55"):
        # No Brasil com 55: deve ter EXATAMENTE 12 dígitos (55 + DDD + 8) ou 13 dígitos (55 + DDD + 9)
        if num_len not in (12, 13):
            return False
    elif not digits.startswith("55") and num_len in (10, 11):
        # Sem 55: DDD válido (11 a 99)
        ddd = int(digits[:2])
        if ddd < 11 or ddd > 99:
            return False
    elif num_len > 13:
        # Números com 14 dígitos começando com 55 são ruídos/inválidos
        if digits.startswith("55"):
            return False

    # Rejeita repetições óbvias de dígitos (ex: 0000000000, 99999999999)
    if len(set(digits)) <= 2:
        return False

    return True


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


AUTOMATED_SERVICE_PATTERNS = [
    r"fila\s+de\s+espera",
    r"n[uú]mero\s+\d+\s+na\s+fila",
    r"posi[cç][aã]o\s+na\s+fila",
    r"transferi[uo]\s+o\s+atendimento",
    r"transferindo\s+para\s+a\s+equipe",
    r"canal\s+de\s+atendimento\s+.*via\s+whatsapp",
    r"assistente\s+de\s+ia\s+d[aoe]",
    r"como\s+posso\s+te\s+ajudar\s+hoje\?",
    r"digite\s+\d+\s+para",
    r"escolha\s+(uma\s+das\s+)?op[cç][oõ]es",
    r"qual\s+[eé]\s+a\s+sua\s+modalidade",
    r"protocolo\s+de\s+atendimento",
    r"c[oó]digo\s+de\s+verifica[cç][aã]o",
    r"c[oó]digo\s+de\s+seguran[cç]a",
    r"token\s+de\s+acesso",
    r"segunda\s+via\s*[/e]?\s*boletos?",
    r"renegocia[cç][aã]o\s+de\s+d[eé]bitos",
]


def is_automated_service_message(text: str) -> bool:
    """Detecta de forma universal se uma mensagem é originada por robô de atendimento, SAC ou notificação transacional."""
    if not text or not text.strip():
        return False

    clean = text.lower().strip()
    for pattern in AUTOMATED_SERVICE_PATTERNS:
        if re.search(pattern, clean, re.IGNORECASE):
            return True

    return False



def is_registered_contact(speaker: Optional[str] = None, meta_info: Optional[Dict[str, Any]] = None, db: Optional[Any] = None) -> bool:
    """Verifica se o remetente é o Dono do Sistema ou um Contato previamente cadastrado com cartão válido."""
    # Se não há identificação explícita de speaker nem remetente externo em meta_info, assume a interface do Dono
    if not speaker or str(speaker).lower() in {"user", "bruno", "admin"}:
        if not meta_info or (not meta_info.get("remoteJid") and not meta_info.get("phone") and not meta_info.get("sender_phone")):
            return True

    # 1. Dono sempre é registrado
    if is_owner_interaction(speaker, meta_info):
        return True

    # 2. Verifica se é grupo (grupos nunca são contatos individuais com cartão)
    if is_group_message(meta_info, speaker):
        return False

    phone_to_check = ""
    if meta_info and isinstance(meta_info, dict):
        phone_to_check = str(meta_info.get("phone") or meta_info.get("sender_phone") or meta_info.get("remoteJid") or "")
    if not phone_to_check and speaker:
        phone_to_check = speaker

    # Se tiver telefone, deve ter padrão de caracteres válido
    if phone_to_check and not is_valid_contact_phone(phone_to_check) and not any(c.isalpha() for c in str(speaker or "")):
        return False

    # 3. Consulta no banco de dados se o contato possui cartão cadastrado
    from src.contacts.models import ContactRecord
    from src.memory.database import SessionLocal

    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        speaker_raw = str(speaker or "").strip()
        speaker_norm = normalize_text(speaker_raw)
        speaker_digits = re.sub(r"\D", "", phone_to_check)

        contacts = db.query(ContactRecord).all()
        for c in contacts:
            c_name_norm = normalize_text(c.name)
            c_nick_norm = normalize_text(c.nickname or "")
            c_digits = re.sub(r"\D", "", c.phone_number or "")
            c_id_digits = re.sub(r"\D", "", c.id or "")

            # 1. Match por dígitos de telefone ou ID (exato ou últimos 8 dígitos)
            if speaker_digits and len(speaker_digits) >= 8:
                if c_digits and (speaker_digits == c_digits or (len(c_digits) >= 8 and speaker_digits[-8:] == c_digits[-8:])):
                    return True
                if c_id_digits and (speaker_digits == c_id_digits or (len(c_id_digits) >= 8 and speaker_digits[-8:] == c_id_digits[-8:])):
                    return True

            # 2. Match por nome completo, primeiro nome ou apelido
            if speaker_norm and len(speaker_norm) >= 3:
                # Match exato de nome ou apelido
                if speaker_norm == c_name_norm or (c_nick_norm and speaker_norm == c_nick_norm):
                    return True

                # Match se speaker for o primeiro nome do contato (ex: "Joceli" em "Joceli Patel")
                c_first_name = c_name_norm.split()[0] if c_name_norm else ""
                if c_first_name and speaker_norm == c_first_name:
                    return True

                # Match se speaker estiver contido no nome completo ou vice-versa
                if speaker_norm in c_name_norm or (c_name_norm and c_name_norm in speaker_norm):
                    return True

                # Match com apelido
                if c_nick_norm and (speaker_norm in c_nick_norm or c_nick_norm in speaker_norm):
                    return True

        return False
    except Exception as e:
        logger.warning(f"Erro ao verificar contato registrado: {e}")
        return False
    finally:
        if should_close:
            db.close()


def should_drop_message(
    text: Optional[str],
    message_type: str = "text",
    meta_info: Optional[Dict[str, Any]] = None,
    speaker: Optional[str] = None,
    db: Optional[Any] = None,
    require_registered_card: bool = True,
) -> Tuple[bool, str]:
    """Determina se a mensagem deve ser COMPLETAMENTE IGNORADA e NÃO SALVA no banco de dados,

    nem enviada para análise de agentes, histórico, embeddings ou word cloud.
    Garante que apenas conversas com real privilégio, remetentes com cartão oficial e densidade informativa sejam processadas.
    """
    # 1. Mensagens de grupo (sempre ignoradas)
    if is_group_message(meta_info, speaker):
        return True, "group_message"

    # 2. Exigência de Identidade Prévia (Dono ou Contato com Cartão)
    if require_registered_card:
        if not is_registered_contact(speaker=speaker, meta_info=meta_info, db=db):
            return True, "unregistered_contact_no_card"

    # 3. Tipos de mídia sem conteúdo textual ou sem suporte de fala
    non_text_types = {
        "sticker", "stickermessage", "sticker_message",
        "reaction", "reactionmessage", "reaction_message",
        "contactmessage", "contact_message", "locationmessage", "location_message",
        "imagemessage", "imagemessage", "videomessage", "video_message",
    }
    msg_type_str = str(message_type).lower().strip()
    if msg_type_str in non_text_types and (not text or not str(text).strip()):
        return True, f"non_text_media_{msg_type_str}"

    # 4. Mensagem sem texto ou nula (ex: áudio inaudível / ruído)
    if not text or not str(text).strip():
        return True, "empty_text"

    raw_clean = str(text).strip()
    clean = normalize_text(raw_clean)

    # 5. Mensagem composta apenas por emojis ou símbolos
    if not clean or is_emoji_only_or_symbols(raw_clean):
        return True, "only_emojis_or_symbols"

    # 6. Lista abrangente de saudações e ruído conversacional social
    if clean in TRIVIAL_SOCIAL_PHRASES:
        return True, "trivial_social_phrase"

    # Se configurado em .env AI_BYPASS_PHRASES adicionais
    if settings.AI_BYPASS_PHRASES:
        custom_phrases = [
            normalize_text(p) for p in settings.AI_BYPASS_PHRASES.split(",") if normalize_text(p)
        ]
        if clean in custom_phrases:
            return True, "custom_trivial_phrase"

    # 7. Avaliação de Densidade Informativa e Privilégio de Memória
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
    speaker: Optional[str] = None,
    db: Optional[Any] = None,
) -> Tuple[bool, str]:
    """Determina se a mensagem deve fazer bypass do processamento de IA (extração semântica e análise de sentimento).

    Retorna: (should_bypass: bool, reason: str)
    """
    # 1. Se deve ser descartada, automaticamente faz bypass
    should_drop, drop_reason = should_drop_message(
        text,
        message_type=message_type,
        meta_info=meta_info,
        speaker=speaker,
        db=db,
    )
    if should_drop:
        return True, drop_reason

    # 2. Bypass explícito no payload
    if meta_info and isinstance(meta_info, dict):
        if meta_info.get("bypass_ai") is True or meta_info.get("bypass") is True:
            return True, "explicit_bypass"

    # 3. Economia de Tokens com spaCy: Mensagens puramente fáticas / saudações
    from src.ai_gateway.token_economy import token_economy
    is_phatic, phatic_reason = token_economy.is_phatic_or_trivial(text or "")
    if is_phatic:
        return True, f"token_economy_{phatic_reason}"

    return False, "process_ai"


def should_analyze_sentiment(
    speaker: Optional[str] = None,
    meta_info: Optional[Dict[str, Any]] = None,
    db: Optional[Any] = None,
    min_weight: Optional[float] = None,
) -> Tuple[bool, str, float]:
    """Verifica se o contato possui peso/influência hierárquica suficiente para merecer o gasto de token em análise de sentimento.

    Retorna: (should_analyze: bool, reason: str, effective_weight: float)
    """
    threshold = min_weight if min_weight is not None else getattr(settings, "SENTIMENT_WEIGHT_THRESHOLD", 0.70)

    # 1. Dono do sistema
    if is_owner_interaction(speaker, meta_info):
        return True, "owner_interaction", 1.00

    from src.contacts.models import ContactRecord
    from src.contacts.service import calculate_effective_weight
    from src.memory.database import SessionLocal

    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        phone_to_check = ""
        if meta_info and isinstance(meta_info, dict):
            phone_to_check = str(meta_info.get("phone") or meta_info.get("sender_phone") or meta_info.get("remoteJid") or "")
        if not phone_to_check and speaker:
            phone_to_check = speaker

        speaker_raw = str(speaker or "").strip()
        speaker_norm = normalize_text(speaker_raw)
        speaker_digits = re.sub(r"\D", "", phone_to_check)

        contacts = db.query(ContactRecord).all()
        matched_contact = None

        for c in contacts:
            c_name_norm = normalize_text(c.name)
            c_nick_norm = normalize_text(c.nickname or "")
            c_digits = re.sub(r"\D", "", c.phone_number or "")

            if speaker_digits and c_digits:
                if speaker_digits == c_digits or (len(speaker_digits) >= 8 and len(c_digits) >= 8 and speaker_digits[-8:] == c_digits[-8:]):
                    matched_contact = c
                    break

            if speaker_norm and (speaker_norm == c_name_norm or (c_nick_norm and speaker_norm == c_nick_norm)):
                matched_contact = c
                break

        if not matched_contact:
            return False, "unregistered_contact_no_card", 0.00

        effective_weight = calculate_effective_weight(matched_contact)

        if effective_weight >= threshold:
            return True, f"qualified_influence_{effective_weight:.2f}", effective_weight
        else:
            return False, f"below_sentiment_threshold_{effective_weight:.2f}", effective_weight
    except Exception as e:
        logger.error(f"Erro ao verificar threshold de sentimento para '{speaker}': {e}")
        return False, "error_checking_threshold", 0.00
    finally:
        if should_close:
            db.close()

