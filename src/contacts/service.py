"""Serviço de Gestão de Contatos, Ponderação de Prioridade e Integração com Grafo."""

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import uuid4
from sqlalchemy.orm import Session
from src.contacts.models import ContactRecord
from src.contacts.parser import contacts_to_markdown_table, parse_contact_batch
from src.contacts.schemas import (
    ROLE_WEIGHTS,
    ContactBatchImportResponse,
    ContactCreate,
    ContactResponse,
    ContactRole,
    ContactUpdate,
)
from src.memory.database import SessionLocal
from src.memory.graph import knowledge_graph
from src.config import settings

import hashlib
import re
from src.ai_gateway.bypass import is_group_message, is_owner_interaction, is_valid_contact_phone, normalize_text

logger = logging.getLogger(__name__)


def generate_contact_id(name: str, phone: str = "") -> Optional[str]:
    """Gera um identificador determinístico único para o contato.
    Se possuir telefone válido (padrão de 10 a 13 dígitos Brasil ou 10-15 internacional), usa 'wa_{digits}'.
    Se o telefone não estiver dentro do padrão ou for grupo, NÃO gera UID (retorna None).
    """
    if is_owner_interaction(name) or is_owner_interaction(phone):
        owner_digits = re.sub(r"\D", "", settings.USER_PHONE_NUMBER or "554497604925")
        return f"wa_{owner_digits}"

    if not is_valid_contact_phone(phone):
        return None

    digits = re.sub(r"\D", "", phone.strip())
    return f"wa_{digits}"


def calculate_effective_weight(contact: ContactRecord | ContactCreate) -> float:
    """Calcula o peso de prioridade efetivo (0.0 a 1.0) para o contato, bonificando favoritos com +10% de peso."""
    if getattr(contact, "custom_weight", None) is not None:
        base = float(contact.custom_weight)
    else:
        role_str = getattr(contact, "role", "UNKNOWN")
        try:
            role_enum = ContactRole(role_str) if isinstance(role_str, str) else role_str
            base = ROLE_WEIGHTS.get(role_enum, 0.40)
        except ValueError:
            base = 0.40

    # Se for marcado como favorito, ganha +10% sobre o peso do seu papel
    if getattr(contact, "is_favorite", False) is True:
        base = round(base * 1.10, 2)

    return min(1.00, max(0.0, base))


def record_to_response(
    rec: ContactRecord,
    latest_sentiment: str = "NEUTRAL",
    recent_sentiments: list[dict] | None = None,
) -> ContactResponse:
    """Converte ContactRecord para ContactResponse enriquecido."""
    role_val = ContactRole(rec.role) if rec.role in ContactRole._value2member_map_ else ContactRole.UNKNOWN
    projects = rec.projects_json if isinstance(rec.projects_json, list) else []

    return ContactResponse(
        id=rec.id,
        phone_number=rec.phone_number or "",
        name=rec.name,
        nickname=rec.nickname,
        role=role_val,
        company=rec.company,
        projects=projects,
        avatar_url=rec.avatar_url,
        custom_weight=rec.custom_weight,
        is_favorite=bool(rec.is_favorite),
        can_generate_tasks=bool(getattr(rec, "can_generate_tasks", False)),
        notes=rec.notes,
        effective_weight=calculate_effective_weight(rec),
        latest_sentiment=latest_sentiment,
        recent_sentiments=recent_sentiments or [],
        last_interaction_at=rec.last_interaction_at,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


_cached_working_proxy: Optional[str] = None
_proxy_checked_at: float = 0.0
_PROXY_CACHE_TTL_SECONDS = 300.0  # 5 minutos


def invalidate_evolution_proxy_cache() -> None:
    """Invalida o cache de proxy para forçar nova sondagem no próximo acesso."""
    global _cached_working_proxy, _proxy_checked_at
    _cached_working_proxy = None
    _proxy_checked_at = 0.0


async def get_evolution_working_proxy(force_refresh: bool = False) -> Optional[str]:
    """Descobre e armazena em cache o proxy funcional para conexão com a Evolution API com TTL auto-renovável."""
    global _cached_working_proxy, _proxy_checked_at
    import time
    import httpx
    from src.config import settings

    now_ts = time.time()
    if not force_refresh and (now_ts - _proxy_checked_at) < _PROXY_CACHE_TTL_SECONDS and _proxy_checked_at > 0:
        return _cached_working_proxy

    headers = {
        "apikey": settings.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }
    candidates = []
    if settings.EVOLUTION_PROXY_URL:
        candidates.append(settings.EVOLUTION_PROXY_URL)
    candidates.extend([None, "http://172.17.0.1:1055", "http://127.0.0.1:1055", "http://172.18.0.1:1055", "http://172.19.0.1:1055", "http://host.docker.internal:1055"])

    test_url = f"{settings.EVOLUTION_API_URL.rstrip('/')}/instance/connectionState/{settings.EVOLUTION_INSTANCE}"

    for proxy in candidates:
        try:
            async with httpx.AsyncClient(proxy=proxy, timeout=2.0) as client:
                res = await client.get(test_url, headers=headers)
                if res.status_code in (200, 201, 401, 403, 404):
                    _cached_working_proxy = proxy
                    _proxy_checked_at = now_ts
                    return proxy
        except Exception:
            continue

    _cached_working_proxy = None
    _proxy_checked_at = now_ts
    return None


class ContactService:
    """Serviço unificado de gestão de contatos e motor de priorização."""

    def list_contacts(
        self,
        role: Optional[str] = None,
        company: Optional[str] = None,
        only_unknown: bool = False,
        interaction_period: Optional[str] = None,
        db: Session | None = None,
    ) -> list[ContactResponse]:
        """Lista contatos com filtros opcionais de papel, empresa e período da última interação."""
        return self.get_contacts(
            role=role,
            company=company,
            only_unknown=only_unknown,
            interaction_period=interaction_period,
            db=db,
        )

    def deduplicate_and_merge_contacts(self, db: Session) -> None:
        """Deduplica, funde e expurga contatos de grupos, inválidos ou fora do padrão de telefone."""
        try:
            all_recs = db.query(ContactRecord).all()
            if not all_recs:
                return

            # 0. Remove contatos de grupos ou transmissões
            for c in all_recs:
                if is_group_message(speaker=c.name) or (c.phone_number and "@g.us" in c.phone_number):
                    db.delete(c)
            db.commit()

            # 1. Consolida o contato do proprietário (Bruno Conter) como OWNER
            all_recs = db.query(ContactRecord).all()
            owner_contacts = [c for c in all_recs if is_owner_interaction(c.name) or is_owner_interaction(c.phone_number)]
            if owner_contacts:
                primary_owner = next((c for c in owner_contacts if c.phone_number and is_valid_contact_phone(c.phone_number)), owner_contacts[0])
                primary_owner.name = "Bruno Conter"
                primary_owner.phone_number = settings.USER_PHONE_NUMBER or "554497604925"
                primary_owner.role = "OWNER"
                primary_owner.nickname = "Bruno Conter (Proprietário / Arquiteto)"
                primary_owner.company = "Hermes Memory / Homelab"
                primary_owner.notes = "Criador, Proprietário e Arquiteto Supremo do sistema Hermes Voice Memory."
                primary_owner.updated_at = datetime.now(timezone.utc)

                for dup in owner_contacts:
                    if dup.id != primary_owner.id:
                        db.delete(dup)
                db.commit()

            # 2. Expurga contatos com telefone fora do padrão (que não sejam o proprietário)
            all_recs = db.query(ContactRecord).all()
            for c in all_recs:
                if not is_owner_interaction(c.name) and not is_owner_interaction(c.phone_number):
                    if not is_valid_contact_phone(c.phone_number):
                        db.delete(c)
            db.commit()

            # 3. Funde contatos com mesmo número de telefone (últimos 8 dígitos)
            remaining = db.query(ContactRecord).all()
            phone_groups: Dict[str, List[ContactRecord]] = defaultdict(list)
            for c in remaining:
                digits = re.sub(r"\D", "", c.phone_number or "")
                if len(digits) >= 8:
                    suffix = digits[-8:]
                    phone_groups[suffix].append(c)

            for suffix, group in phone_groups.items():
                if len(group) > 1:
                    # Escolhe o mais completo como primário
                    primary = max(group, key=lambda x: (x.role != "UNKNOWN", len(x.name or ""), len(x.notes or "")))
                    for dup in group:
                        if dup.id != primary.id:
                            if dup.nickname and not primary.nickname:
                                primary.nickname = dup.nickname
                            if dup.company and not primary.company:
                                primary.company = dup.company
                            db.delete(dup)
                    db.commit()

        except Exception as e:
            logger.warning(f"Erro na deduplicação de contatos: {e}")
            db.rollback()

    def get_contacts(
        self,
        role: str | None = None,
        company: str | None = None,
        only_unknown: bool = False,
        interaction_period: str | None = None,
        db: Session | None = None,
    ) -> List[ContactResponse]:
        """Retorna lista de contatos enriquecida com filtros temporais de interação ('today', '7d', '30d', 'all')."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            # 1. Busca contatos com filtros diretamente do banco
            query = db.query(ContactRecord)
            if only_unknown:
                query = query.filter(ContactRecord.role == "UNKNOWN")
            elif role:
                query = query.filter(ContactRecord.role == role.upper())

            if company:
                query = query.filter(ContactRecord.company.ilike(f"%{company}%"))

            # 1.1 Filtro por período da última interação
            now = datetime.now(timezone.utc)
            if interaction_period == "today":
                start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                query = query.filter(ContactRecord.last_interaction_at >= start_of_today)
            elif interaction_period in ("7d", "week", "7_days"):
                start_7d = now - timedelta(days=7)
                query = query.filter(ContactRecord.last_interaction_at >= start_7d)
            elif interaction_period in ("30d", "month", "30_days"):
                start_30d = now - timedelta(days=30)
                query = query.filter(ContactRecord.last_interaction_at >= start_30d)

            # Ordena por última interação mais recente (se filtrado), favoritos no topo, depois nome
            if interaction_period in ("today", "7d", "30d", "week", "month"):
                records = query.order_by(
                    ContactRecord.last_interaction_at.desc().nullslast(),
                    ContactRecord.is_favorite.desc(),
                    ContactRecord.name.asc(),
                ).all()
            else:
                records = query.order_by(ContactRecord.is_favorite.desc(), ContactRecord.name.asc()).all()

            if not records:
                return []

            # Consolidação inteligente e instantânea de duplicatas em memória (0ms overhead)
            from src.ai_gateway.bypass import is_owner_interaction
            dedup_records = []
            seen_phones = {}
            seen_names = {}
            seen_owner = False

            for r in records:
                if is_owner_interaction(r.name) or is_owner_interaction(r.phone_number):
                    if not seen_owner:
                        seen_owner = True
                        r.name = "Bruno Conter"
                        r.role = "OWNER"
                        if not r.phone_number:
                            r.phone_number = settings.USER_PHONE_NUMBER or "554497604925"
                        dedup_records.append(r)
                    continue

                dig = re.sub(r"\D", "", r.phone_number or "")
                norm_name = r.name.lower().strip()

                if len(dig) >= 8:
                    suffix = dig[-8:]
                    if suffix in seen_phones:
                        existing = seen_phones[suffix]
                        if (existing.role == "UNKNOWN" or not existing.role) and r.role and r.role != "UNKNOWN":
                            existing.role = r.role
                        if not existing.nickname and r.nickname:
                            existing.nickname = r.nickname
                        continue
                    seen_phones[suffix] = r

                if norm_name:
                    if norm_name in seen_names:
                        existing = seen_names[norm_name]
                        if not existing.phone_number and r.phone_number:
                            existing.phone_number = r.phone_number
                        if (existing.role == "UNKNOWN" or not existing.role) and r.role and r.role != "UNKNOWN":
                            existing.role = r.role
                        continue
                    seen_names[norm_name] = r

                dedup_records.append(r)

            records = dedup_records

            # 2. Enriquece com as últimas mensagens em BATCH de alta performance (1 única query)
            from src.memory.models import MessageRecord
            from src.ai_gateway.bypass import normalize_text

            recent_messages = (
                db.query(MessageRecord)
                .order_by(MessageRecord.created_at.desc())
                .limit(400)
                .all()
            )

            # Agrupa mensagens recentes por chaves de busca normalizadas
            msgs_by_key = defaultdict(list)
            for m in recent_messages:
                spk = (m.speaker or "").strip()
                if spk:
                    msgs_by_key[spk.lower()].append(m)
                    norm_spk = normalize_text(spk)
                    if norm_spk:
                        msgs_by_key[norm_spk].append(m)
                    dig = re.sub(r"\D", "", spk)
                    if dig:
                        msgs_by_key[dig].append(m)
                        if len(dig) >= 8:
                            msgs_by_key[dig[-8:]].append(m)

                meta = m.meta_info or {}
                meta_phone = str(meta.get("phone") or meta.get("remoteJid") or "")
                dig_meta = re.sub(r"\D", "", meta_phone)
                if dig_meta:
                    msgs_by_key[dig_meta].append(m)
                    if len(dig_meta) >= 8:
                        msgs_by_key[dig_meta[-8:]].append(m)

                push = str(meta.get("pushName") or "")
                if push:
                    msgs_by_key[push.lower()].append(m)
                    norm_p = normalize_text(push)
                    if norm_p:
                        msgs_by_key[norm_p].append(m)

            responses = []
            for r in records:
                matched_msgs = []
                seen_msg_ids = set()

                candidates_keys = []
                if r.name:
                    candidates_keys.append(r.name.lower())
                    norm_n = normalize_text(r.name)
                    if norm_n:
                        candidates_keys.append(norm_n)
                    first = r.name.split()[0]
                    if len(first) >= 4:
                        candidates_keys.append(first.lower())
                if r.nickname:
                    candidates_keys.append(r.nickname.lower())
                    norm_nick = normalize_text(r.nickname)
                    if norm_nick:
                        candidates_keys.append(norm_nick)
                if r.phone_number:
                    dig = re.sub(r"\D", "", r.phone_number)
                    if dig:
                        candidates_keys.append(dig)
                        if len(dig) >= 8:
                            candidates_keys.append(dig[-8:])

                for k in candidates_keys:
                    if k in msgs_by_key:
                        for m in msgs_by_key[k]:
                            if m.id not in seen_msg_ids:
                                seen_msg_ids.add(m.id)
                                matched_msgs.append(m)

                matched_msgs.sort(key=lambda m: m.created_at or datetime.min, reverse=True)
                top_msgs = matched_msgs[:3]

                recent_sentiments = [
                    {
                        "sentiment": m.sentiment or "NEUTRAL",
                        "sentiment_score": m.sentiment_score or 0.0,
                        "summary": m.summary or (m.revised_text[:60] if m.revised_text else ""),
                        "created_at": m.created_at.strftime("%d/%m %H:%M") if m.created_at else "",
                        "urgency": m.urgency or "MEDIUM",
                    }
                    for m in top_msgs
                ]
                latest_sentiment = recent_sentiments[0]["sentiment"] if recent_sentiments else "NEUTRAL"
                responses.append(record_to_response(r, latest_sentiment=latest_sentiment, recent_sentiments=recent_sentiments))

            return responses
        finally:
            if should_close:
                db.close()

    def get_contact_by_phone(self, phone: str, db: Session | None = None) -> ContactRecord | None:
        """Busca contato por número de telefone de forma segura e flexível."""
        if not phone or not isinstance(phone, str):
            return None

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            import re
            digits = re.sub(r"\D", "", phone.strip())
            if len(digits) < 8:
                return None

            # 1. Busca por correspondência exata de dígitos ou string
            exact = db.query(ContactRecord).filter(
                (ContactRecord.phone_number == digits) | (ContactRecord.phone_number == phone.strip())
            ).first()
            if exact:
                return exact

            # 2. Busca por sufixo dos últimos 8 dígitos (evitando inconsistência de DDD/DDI)
            suffix = digits[-8:]
            return db.query(ContactRecord).filter(
                ContactRecord.phone_number.like(f"%{suffix}%")
            ).first()
        finally:
            if should_close:
                db.close()

    def get_contact_by_name(self, name: str, db: Session | None = None) -> ContactRecord | None:
        """Busca contato por nome ou apelido com suporte a variações e correspondência parcial."""
        if not name or not isinstance(name, str):
            return None

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            name_clean = name.strip()
            if not name_clean:
                return None

            # 1. Limpa títulos honoríficos e saudações comuns (Dona, Seu, etc.)
            clean_search = re.sub(r"^(dona|seu|sr\.?|sra\.?|dr\.?|dra\.?|eng\.?|prof\.?)\s+", "", name_clean, flags=re.IGNORECASE).strip()
            if not clean_search:
                clean_search = name_clean

            # 2. Correspondência exata case-insensitive
            match = db.query(ContactRecord).filter(
                (ContactRecord.name.ilike(clean_search)) | (ContactRecord.nickname.ilike(clean_search))
            ).first()
            if match:
                return match

            # 3. Substring direta (ex: "Larissa Batista" contido em "Larissa Ajala Batista" ou vice-versa)
            match = db.query(ContactRecord).filter(
                (ContactRecord.name.ilike(f"%{clean_search}%")) | (ContactRecord.nickname.ilike(f"%{clean_search}%"))
            ).first()
            if match:
                return match

            # 4. Correspondência por primeiro nome (ex: "Joceli" -> "Joceli Patel")
            first_token = clean_search.split()[0] if clean_search else ""
            if len(first_token) >= 3:
                match = db.query(ContactRecord).filter(
                    ContactRecord.name.ilike(f"{first_token}%")
                ).first()
                if match:
                    return match

            # 5. Correspondência por tokens de nome (ex: primeiro + último nome)
            tokens = [t for t in re.findall(r"\w+", clean_search.lower()) if len(t) >= 3]
            if len(tokens) >= 2:
                all_contacts = db.query(ContactRecord).all()
                for c in all_contacts:
                    c_name_lower = (c.name or "").lower()
                    c_nick_lower = (c.nickname or "").lower()
                    if all(t in c_name_lower or t in c_nick_lower for t in tokens[:2]):
                        return c

            return None
        finally:
            if should_close:
                db.close()

    def create_or_update_contact(self, data: ContactCreate, db: Session | None = None) -> ContactResponse:
        """Cria ou atualiza um contato deduplicando por telefone ou nome."""
        phone_clean = (data.phone_number or "").strip()
        is_owner = is_owner_interaction(data.name, {"phone": phone_clean})

        if not is_owner and not is_valid_contact_phone(phone_clean):
            raise ValueError(
                f"Número de telefone inválido ou fora do padrão ('{phone_clean}'). "
                "Contatos necessitam de telefone válido (10 a 13 dígitos para o Brasil) para receber UID e virar cartão."
            )

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            import re
            digits = re.sub(r"\D", "", phone_clean)

            existing = None
            if digits and len(digits) >= 8:
                existing = self.get_contact_by_phone(digits, db=db)

            if not existing and data.name:
                existing = self.get_contact_by_name(data.name, db=db)

            if existing:
                if data.name:
                    existing.name = data.name
                if phone_clean:
                    existing.phone_number = digits if len(digits) >= 8 else phone_clean
                if data.nickname:
                    existing.nickname = data.nickname
                if data.role:
                    existing.role = data.role.value if isinstance(data.role, ContactRole) else str(data.role)
                if data.company is not None:
                    existing.company = data.company
                if data.projects is not None:
                    existing.projects_json = data.projects
                if data.is_favorite is not None:
                    existing.is_favorite = data.is_favorite
                if data.can_generate_tasks is not None:
                    existing.can_generate_tasks = data.can_generate_tasks
                if data.avatar_url is not None:
                    existing.avatar_url = data.avatar_url
                if data.custom_weight is not None:
                    existing.custom_weight = data.custom_weight
                if data.notes:
                    existing.notes = data.notes
                if data.last_interaction_at is not None:
                    existing.last_interaction_at = data.last_interaction_at
                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(existing)
                rec = existing
            else:
                contact_id = generate_contact_id(data.name, digits or phone_clean)
                if not contact_id:
                    raise ValueError("Falha ao gerar UID: número de telefone fora do padrão.")
                rec = ContactRecord(
                    id=contact_id,
                    phone_number=digits if len(digits) >= 8 else phone_clean,
                    name=data.name,
                    nickname=data.nickname,
                    role=data.role.value if isinstance(data.role, ContactRole) else str(data.role),
                    company=data.company,
                    projects_json=data.projects,
                    avatar_url=data.avatar_url,
                    custom_weight=data.custom_weight,
                    is_favorite=bool(data.is_favorite),
                    can_generate_tasks=bool(data.can_generate_tasks),
                    notes=data.notes,
                    last_interaction_at=data.last_interaction_at,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(rec)
                db.commit()
                db.refresh(rec)

            # Sincroniza nó no Grafo NetworkX
            self._sync_contact_to_graph(rec)

            return record_to_response(rec)
        finally:
            if should_close:
                db.close()

    def toggle_favorite(
        self, contact_id: str, is_favorite: Optional[bool] = None, db: Session | None = None
    ) -> ContactResponse:
        """Alterna ou define o status de favorito do contato (+10% de peso de prioridade)."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            rec = db.query(ContactRecord).filter(
                (ContactRecord.id == contact_id)
                | (ContactRecord.name == contact_id)
                | (ContactRecord.phone_number == contact_id)
            ).first()
            if not rec:
                raise ValueError(f"Contato '{contact_id}' não encontrado.")

            if is_favorite is not None:
                rec.is_favorite = is_favorite
            else:
                rec.is_favorite = not bool(rec.is_favorite)

            rec.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(rec)
            self._sync_contact_to_graph(rec)
            return record_to_response(rec)
        finally:
            if should_close:
                db.close()

    def toggle_can_generate_tasks(
        self, contact_id: str, can_generate_tasks: Optional[bool] = None, db: Session | None = None
    ) -> ContactResponse:
        """Alterna ou define se o contato possui permissão para gerar tarefas acionáveis."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            rec = db.query(ContactRecord).filter(
                (ContactRecord.id == contact_id)
                | (ContactRecord.name == contact_id)
                | (ContactRecord.phone_number == contact_id)
            ).first()
            if not rec:
                raise ValueError(f"Contato '{contact_id}' não encontrado.")

            if can_generate_tasks is not None:
                rec.can_generate_tasks = can_generate_tasks
            else:
                rec.can_generate_tasks = not bool(rec.can_generate_tasks)

            rec.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(rec)
            self._sync_contact_to_graph(rec)
            return record_to_response(rec)
        finally:
            if should_close:
                db.close()

    def _sync_contact_to_graph(self, contact: ContactRecord) -> None:
        """Cria/atualiza conexões ricas no Grafo NetworkX para o contato."""
        try:
            knowledge_graph.add_node(
                contact.name,
                category="PERSON",
                role=contact.role,
                phone=contact.phone_number,
                company=contact.company,
                weight=calculate_effective_weight(contact),
                can_generate_tasks=bool(getattr(contact, "can_generate_tasks", False)),
                last_interaction_at=contact.last_interaction_at.isoformat() if contact.last_interaction_at else None,
            )

            if contact.company:
                knowledge_graph.add_node(contact.company, category="LOCATION")
                knowledge_graph.add_edge(contact.name, contact.company, relation=f"AFFILIATED_AS_{contact.role}")

            if contact.projects_json:
                for proj in contact.projects_json:
                    knowledge_graph.add_node(proj, category="PROJECT")
                    knowledge_graph.add_edge(contact.name, proj, relation="WORKS_ON")
        except Exception as e:
            logger.warning(f"Erro ao sincronizar contato {contact.name} com o grafo: {e}")

    def import_batch_from_text(self, raw_text: str, db: Session | None = None) -> ContactBatchImportResponse:
        """Importa contatos em lote a partir de uma Tabela Markdown (.md) ou Array JSON (.json)."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            parsed_items = parse_contact_batch(raw_text)
            imported = 0
            updated = 0
            errors = []
            results: list[ContactResponse] = []

            for item in parsed_items:
                try:
                    existing = self.get_contact_by_phone(item.phone_number, db=db)
                    is_update = existing is not None
                    saved = self.create_or_update_contact(item, db=db)
                    results.append(saved)
                    if is_update:
                        updated += 1
                    else:
                        imported += 1
                except Exception as e:
                    errors.append(f"Erro no contato {item.name} ({item.phone_number}): {str(e)}")

            return ContactBatchImportResponse(
                imported_count=imported,
                updated_count=updated,
                errors=errors,
                contacts=results,
            )
        finally:
            if should_close:
                db.close()

    def export_markdown_table(self, only_unknown: bool = False, db: Session | None = None) -> str:
        """Exporta lista de contatos em formato de Tabela Markdown (.md)."""
        contacts = self.list_contacts(only_unknown=only_unknown, db=db)
        return contacts_to_markdown_table(contacts)

    def calculate_priority_for_message(
        self,
        sender_phone_or_name: str,
        raw_urgency: str = "MEDIUM",
        db: Session | None = None,
    ) -> Literal["LOW", "MEDIUM", "HIGH", "URGENT"]:
        """Calcula a prioridade final ponderando o papel hierárquico do remetente."""
        contact = self.get_contact_by_phone(sender_phone_or_name, db=db)
        if not contact:
            contact = self.get_contact_by_name(sender_phone_or_name, db=db)

        # Peso do contato (0.40 a 1.00)
        contact_weight = calculate_effective_weight(contact) if contact else 0.40

        # Peso base da urgência inferida pela IA
        raw_urgency_weights = {
            "URGENT": 1.0,
            "HIGH": 0.80,
            "MEDIUM": 0.50,
            "LOW": 0.20,
        }
        urgency_weight = raw_urgency_weights.get(raw_urgency.upper(), 0.50)

        # Score combinado
        # Ex: Executive (1.0) + Medium (0.50) -> Score ~ 0.75 -> HIGH!
        # Ex: Executive (1.0) + High (0.80) -> Score ~ 0.90 -> URGENT!
        # Ex: Unknown (0.40) + High (0.80) -> Score ~ 0.60 -> MEDIUM
        combined_score = (contact_weight * 0.6) + (urgency_weight * 0.4)

        if combined_score >= 0.85:
            return "URGENT"
        elif combined_score >= 0.65:
            return "HIGH"
        elif combined_score >= 0.40:
            return "MEDIUM"
        else:
            return "LOW"


    def deduplicate_contacts(self, dry_run: bool = False, db: Session | None = None) -> Dict[str, Any]:
        """Identifica e mescla cartões de contatos duplicados (por telefone ou variações de nome).

        - Escolhe o cartão canônico com base em: Dono > Favorito > Peso do Papel > Completude dos dados.
        - Transfere histórico de mensagens e tarefas para o cartão canônico.
        - Redireciona arestas e nós no Grafo MUSA (NetworkX).
        - Remove o cartão duplicado secundário.
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        merged_pairs = []
        contacts_merged_count = 0

        try:
            from src.memory.models import MessageRecord, TaskRecord

            all_contacts = db.query(ContactRecord).all()
            if not all_contacts:
                return {"contacts_merged_count": 0, "merged_pairs": []}

            # Agrupa contatos por chave de telefone normalizada e por nome normalizado
            groups: Dict[str, List[ContactRecord]] = defaultdict(list)
            for c in all_contacts:
                phone_digits = re.sub(r"\D", "", c.phone_number or "")
                # Se tiver 8 ou mais dígitos, agrupa pelo sufixo de 8 dígitos
                if len(phone_digits) >= 8:
                    groups[f"phone_{phone_digits[-8:]}"].append(c)
                elif c.phone_number:
                    groups[f"phone_{phone_digits}"].append(c)

                # Agrupa por nome normalizado
                if c.name:
                    name_norm = normalize_text(c.name)
                    if name_norm:
                        groups[f"name_{name_norm}"].append(c)

            processed_ids = set()

            for group_key, candidates in groups.items():
                # Filtra duplicatas reais dentro do grupo
                unique_candidates = [c for c in candidates if c.id not in processed_ids]
                if len(unique_candidates) <= 1:
                    continue

                # Identifica o contato Canônico:
                # 1. Dono (OWNER)
                # 2. is_favorite == True
                # 3. Maior peso efetivo
                # 4. Mais campos preenchidos
                canonical = max(
                    unique_candidates,
                    key=lambda c: (
                        1000 if c.role == "OWNER" else 0,
                        500 if c.is_favorite else 0,
                        calculate_effective_weight(c),
                        len(c.company or "") + len(c.notes or "") + len(c.nickname or "") + len(c.name or ""),
                    ),
                )

                for duplicate in unique_candidates:
                    if duplicate.id == canonical.id:
                        continue

                    # Mescla dados no Canônico se estiverem vazios
                    if not canonical.company and duplicate.company:
                        canonical.company = duplicate.company
                    if not canonical.nickname and duplicate.nickname:
                        canonical.nickname = duplicate.nickname
                    if not canonical.avatar_url and duplicate.avatar_url:
                        canonical.avatar_url = duplicate.avatar_url
                    if not canonical.notes and duplicate.notes:
                        canonical.notes = duplicate.notes
                    elif duplicate.notes and duplicate.notes not in (canonical.notes or ""):
                        canonical.notes = f"{canonical.notes or ''}\n[Nota Importada]: {duplicate.notes}".strip()

                    # Mescla projetos
                    canon_proj = set(canonical.projects_json or [])
                    dup_proj = set(duplicate.projects_json or [])
                    canonical.projects_json = list(canon_proj | dup_proj)

                    if duplicate.is_favorite:
                        canonical.is_favorite = True

                    if not dry_run:
                        # 1. Transfere mensagens associadas
                        db.query(MessageRecord).filter(MessageRecord.speaker == duplicate.name).update(
                            {"speaker": canonical.name}, synchronize_session=False
                        )

                        # 2. Transfere tarefas associadas
                        db.query(TaskRecord).filter(TaskRecord.assignee == duplicate.name).update(
                            {"assignee": canonical.name}, synchronize_session=False
                        )

                        # 3. Redireciona arestas e nós no Grafo MUSA
                        with knowledge_graph._lock:
                            g = knowledge_graph.graph
                            if g.has_node(duplicate.name) and g.has_node(canonical.name):
                                # Arestas de entrada
                                for u, _, edge_data in list(g.in_edges(duplicate.name, data=True)):
                                    if u != canonical.name:
                                        knowledge_graph.add_edge(
                                            source=u,
                                            target=canonical.name,
                                            relation=edge_data.get("relation", "RELATED_TO"),
                                            weight=edge_data.get("weight", 1.0),
                                        )
                                # Arestas de saída
                                for _, v, edge_data in list(g.out_edges(duplicate.name, data=True)):
                                    if v != canonical.name:
                                        knowledge_graph.add_edge(
                                            source=canonical.name,
                                            target=v,
                                            relation=edge_data.get("relation", "RELATED_TO"),
                                            weight=edge_data.get("weight", 1.0),
                                        )
                                knowledge_graph.graph.nodes[canonical.name]["mentions"] = (
                                    knowledge_graph.graph.nodes[canonical.name].get("mentions", 1)
                                    + knowledge_graph.graph.nodes[duplicate.name].get("mentions", 1)
                                )
                                knowledge_graph.graph.remove_node(duplicate.name)
                                knowledge_graph._save()
                            elif g.has_node(duplicate.name) and not g.has_node(canonical.name):
                                # Renomeia o nó
                                knowledge_graph.add_node(canonical.name, category="PERSON")
                                for u, _, edge_data in list(g.in_edges(duplicate.name, data=True)):
                                    knowledge_graph.add_edge(u, canonical.name, edge_data.get("relation", "RELATED_TO"))
                                for _, v, edge_data in list(g.out_edges(duplicate.name, data=True)):
                                    knowledge_graph.add_edge(canonical.name, v, edge_data.get("relation", "RELATED_TO"))
                                knowledge_graph.graph.remove_node(duplicate.name)
                                knowledge_graph._save()

                        # 4. Remove o registro duplicado
                        db.delete(duplicate)

                    processed_ids.add(duplicate.id)
                    contacts_merged_count += 1
                    merged_pairs.append({
                        "canonical_id": canonical.id,
                        "canonical_name": canonical.name,
                        "merged_id": duplicate.id,
                        "merged_name": duplicate.name,
                    })

            if not dry_run and contacts_merged_count > 0:
                db.commit()

            return {
                "contacts_merged_count": contacts_merged_count,
                "merged_pairs": merged_pairs,
            }
        except Exception as e:
            logger.error(f"Erro na deduplicação de cartões de contatos: {e}")
            if not dry_run:
                db.rollback()
            return {"contacts_merged_count": 0, "merged_pairs": []}
        finally:
            if should_close:
                db.close()

    def import_vcards_from_text(self, vcard_text: str, source_label: str = "upload", db: Session | None = None) -> Dict[str, Any]:
        """Faz parsing de vCard e importa/atualiza contatos no banco e grafo."""
        from src.contacts.parser import parse_vcard_text
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        logs: List[str] = []
        logs.append(f"🔍 Iniciando parsing de vCard ({source_label})...")

        try:
            contacts_list = parse_vcard_text(vcard_text)
            total_parsed = len(contacts_list)
            logs.append(f"📋 Encontrados {total_parsed} registros válidos no arquivo vCard.")

            if total_parsed == 0:
                return {
                    "total_parsed": 0,
                    "imported_count": 0,
                    "updated_count": 0,
                    "skipped_count": 0,
                    "details": logs,
                }

            existing_by_phone = {
                c.phone_number: c for c in db.query(ContactRecord).filter(ContactRecord.phone_number.isnot(None)).all() if c.phone_number
            }
            existing_by_id = {c.id: c for c in db.query(ContactRecord).all()}

            inserted = 0
            updated = 0
            skipped = 0

            for item in contacts_list:
                phone = (item.phone_number or "").strip()
                name = (item.name or "").strip()

                if not phone:
                    if name and len(name) > 1:
                        knowledge_graph.add_node(name, category="PERSON", details=item.notes or "Contato vCard (sem tel)")
                        skipped += 1
                    continue

                c_id = generate_contact_id(name, phone)
                if not c_id:
                    skipped += 1
                    continue

                existing = existing_by_phone.get(phone) or existing_by_id.get(c_id)

                if existing:
                    if existing.name.isdigit() or (len(name) > len(existing.name) and not existing.name.startswith("wa_")):
                        existing.name = name
                    if item.company and not existing.company:
                        existing.company = item.company
                    if item.nickname and not existing.nickname:
                        existing.nickname = item.nickname
                    if item.notes and "Importado" not in (existing.notes or ""):
                        existing.notes = f"{existing.notes} | {item.notes}" if existing.notes else item.notes
                    if item.avatar_url and not existing.avatar_url:
                        existing.avatar_url = item.avatar_url
                    existing.updated_at = datetime.now(timezone.utc)
                    self._sync_contact_to_graph(existing)
                    updated += 1
                else:
                    new_rec = ContactRecord(
                        id=c_id,
                        phone_number=phone,
                        name=name,
                        nickname=item.nickname,
                        role=item.role.value if hasattr(item.role, "value") else str(item.role),
                        company=item.company,
                        projects_json=item.projects or [],
                        avatar_url=item.avatar_url,
                        custom_weight=item.custom_weight,
                        is_favorite=item.is_favorite,
                        can_generate_tasks=item.can_generate_tasks,
                        notes=item.notes or f"Importado via vCard ({source_label})",
                        last_interaction_at=item.last_interaction_at,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    db.add(new_rec)
                    existing_by_phone[phone] = new_rec
                    existing_by_id[c_id] = new_rec
                    self._sync_contact_to_graph(new_rec)
                    inserted += 1

            db.commit()
            knowledge_graph._save()
            logs.append(f"✅ Sucesso: +{inserted} novos contatos inseridos, {updated} atualizados, {skipped} ignorados.")
            return {
                "total_parsed": total_parsed,
                "imported_count": inserted,
                "updated_count": updated,
                "skipped_count": skipped,
                "details": logs,
            }
        except Exception as e:
            logger.error(f"Erro ao importar vCards: {e}")
            db.rollback()
            logs.append(f"❌ Erro na importação de vCards: {e}")
            return {
                "total_parsed": 0,
                "imported_count": 0,
                "updated_count": 0,
                "skipped_count": 0,
                "details": logs,
                "error": str(e),
            }
        finally:
            if should_close:
                db.close()

    def import_vcards_from_directory(self, dir_path: str = "data/vcards", db: Session | None = None) -> Dict[str, Any]:
        """Lê todos os arquivos .vcf na pasta e importa para o banco."""
        import glob
        import os

        logs: List[str] = []
        logs.append(f"📂 Varrendo diretório '{dir_path}' em busca de arquivos vCard...")

        vcf_files = sorted(glob.glob(os.path.join(dir_path, "*.vcf")) + glob.glob(os.path.join(dir_path, "*.vcard")))
        if not vcf_files:
            logs.append(f"⚠️ Nenhum arquivo .vcf/.vcard encontrado em '{dir_path}'.")
            return {
                "total_parsed": 0,
                "imported_count": 0,
                "updated_count": 0,
                "skipped_count": 0,
                "details": logs,
            }

        total_p = 0
        total_i = 0
        total_u = 0
        total_s = 0

        for fpath in vcf_files:
            fname = os.path.basename(fpath)
            fsize_kb = round(os.path.getsize(fpath) / 1024, 1)
            logs.append(f"📄 Processando '{fname}' ({fsize_kb} KB)...")
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                res = self.import_vcards_from_text(content, source_label=fname, db=db)
                total_p += res.get("total_parsed", 0)
                total_i += res.get("imported_count", 0)
                total_u += res.get("updated_count", 0)
                total_s += res.get("skipped_count", 0)
                logs.extend(res.get("details", []))
            except Exception as fe:
                logs.append(f"❌ Erro ao ler '{fname}': {fe}")

        logs.append(f"🏁 Total Diretório: {total_p} lidos, +{total_i} novos, {total_u} atualizados.")
        return {
            "total_parsed": total_p,
            "imported_count": total_i,
            "updated_count": total_u,
            "skipped_count": total_s,
            "details": logs,
        }

    async def sync_all_avatars_from_evolution(self, force_all: bool = False, db: Session | None = None) -> Dict[str, Any]:
        """Varre os contatos e sincroniza fotos de perfil (profilePicUrl) e pushName via Evolution API."""
        import asyncio
        import httpx
        from src.config import settings

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        logs: List[str] = []
        logs.append(f"📡 Conectando à Evolution API ({settings.EVOLUTION_API_URL})...")

        try:
            query = db.query(ContactRecord).filter(ContactRecord.phone_number.isnot(None))
            if not force_all:
                query = query.filter(ContactRecord.avatar_url.is_(None))
            contacts = query.all()

            logs.append(f"👥 Encontrados {len(contacts)} contatos elegíveis para sincronização de avatar.")

            if not contacts:
                logs.append("✨ Todos os contatos elegíveis já possuem foto de perfil sincronizada.")
                return {
                    "total_checked": 0,
                    "updated_avatars": 0,
                    "updated_names": 0,
                    "failed_count": 0,
                    "details": logs,
                }

            proxy = await get_evolution_working_proxy()
            headers = {
                "apikey": settings.EVOLUTION_API_KEY,
                "Content-Type": "application/json",
            }

            # Valida conectividade com a instância
            test_url = f"{settings.EVOLUTION_API_URL.rstrip('/')}/instance/connectionState/{settings.EVOLUTION_INSTANCE}"
            async with httpx.AsyncClient(proxy=proxy, timeout=3.0) as check_client:
                try:
                    res_state = await check_client.get(test_url, headers=headers)
                    if res_state.status_code != 200:
                        logs.append(f"⚠️ Instância '{settings.EVOLUTION_INSTANCE}' retornou status {res_state.status_code}.")
                except Exception as ce:
                    logs.append(f"⚠️ Evolution API indisponível no momento ({settings.EVOLUTION_API_URL}): {ce}")
                    return {
                        "total_checked": len(contacts),
                        "updated_avatars": 0,
                        "updated_names": 0,
                        "failed_count": len(contacts),
                        "details": logs,
                    }

            updated_pics = 0
            updated_names = 0
            failed = 0

            sem = asyncio.Semaphore(15)

            async def process_contact(c: ContactRecord, client: httpx.AsyncClient) -> tuple[Optional[str], Optional[str]]:
                digits = re.sub(r"\D", "", c.phone_number or "")
                if len(digits) in (10, 11) and not digits.startswith("55"):
                    digits = f"55{digits}"
                if not digits or len(digits) < 10:
                    return None, None

                pic_url = None
                push_name = None

                async with sem:
                    # 1. Foto de perfil
                    try:
                        url_pic = f"{settings.EVOLUTION_API_URL.rstrip('/')}/chat/fetchProfilePictureUrl/{settings.EVOLUTION_INSTANCE}"
                        res_pic = await client.post(url_pic, headers=headers, json={"number": digits})
                        if res_pic.status_code == 200:
                            data_pic = res_pic.json()
                            pic_url = data_pic.get("profilePictureUrl") or data_pic.get("url")
                    except Exception:
                        pass

                    # 2. PushName
                    try:
                        url_contacts = f"{settings.EVOLUTION_API_URL.rstrip('/')}/chat/findContacts/{settings.EVOLUTION_INSTANCE}"
                        res_contacts = await client.post(url_contacts, headers=headers, json={"where": {"remoteJid": f"{digits}@s.whatsapp.net"}})
                        if res_contacts.status_code == 200:
                            data_contacts = res_contacts.json()
                            if isinstance(data_contacts, list) and len(data_contacts) > 0:
                                push_name = data_contacts[0].get("pushName")
                                if not pic_url:
                                    pic_url = data_contacts[0].get("profilePicUrl")
                    except Exception:
                        pass

                return pic_url, push_name

            async with httpx.AsyncClient(proxy=proxy, timeout=6.0) as client:
                tasks = [process_contact(c, client) for c in contacts]
                results = await asyncio.gather(*tasks, return_exceptions=True)

            for idx, (c, res) in enumerate(zip(contacts, results), 1):
                if isinstance(res, Exception):
                    failed += 1
                    continue
                pic_url, push_name = res
                changed = False
                if pic_url and pic_url != c.avatar_url:
                    c.avatar_url = pic_url
                    updated_pics += 1
                    changed = True
                if push_name and (c.name.isdigit() or c.name.startswith("55") or c.name.startswith("wa_") or not c.nickname):
                    if not c.nickname:
                        c.nickname = push_name
                    changed = True
                    updated_names += 1

                if changed:
                    c.updated_at = datetime.now(timezone.utc)
                    if updated_pics <= 30 or updated_pics % 50 == 0:
                        logs.append(f"[{idx}/{len(contacts)}] 📸 {c.name}: avatar/nome atualizado.")

            db.commit()
            logs.append(f"🎉 Concluído: {updated_pics} fotos sincronizadas, {updated_names} nomes atualizados.")
            return {
                "total_checked": len(contacts),
                "updated_avatars": updated_pics,
                "updated_names": updated_names,
                "failed_count": failed,
                "details": logs,
            }

        except Exception as e:
            logger.error(f"Erro ao sincronizar avatares da Evolution API: {e}")
            logs.append(f"❌ Erro ao conectar na Evolution API: {e}")
            return {
                "total_checked": 0,
                "updated_avatars": 0,
                "updated_names": 0,
                "failed_count": 0,
                "details": logs,
                "error": str(e),
            }
        finally:
            if should_close:
                db.close()

    async def run_full_contacts_pipeline(self, vcard_content: str | None = None, vcards_dir: str = "data/vcards", db: Session | None = None) -> Dict[str, Any]:
        """Executa a esteira completa: Importação vCard + Deduplicação/Merge + Sincronização de Avatares + Grafo MUSA."""
        logs: List[str] = []
        logs.append("================================================================")
        logs.append("🚀 INICIANDO PIPELINE MESTRE DE SINCRONIZAÇÃO DE CONTATOS")
        logs.append("================================================================")

        # Passo 1: Importação de vCards
        logs.append("📦 [ETAPA 1/4] Importação e Normalização de vCards...")
        if vcard_content:
            res_import = self.import_vcards_from_text(vcard_content, source_label="upload", db=db)
        else:
            res_import = self.import_vcards_from_directory(dir_path=vcards_dir, db=db)
        logs.extend(res_import.get("details", []))

        # Passo 2: Deduplicação e Limpeza
        logs.append("🧹 [ETAPA 2/4] Executando Deduplicação Profunda e Consolidação...")
        self.deduplicate_and_merge_contacts(db=db or SessionLocal())
        res_dedup = self.deduplicate_contacts(dry_run=False, db=db)
        merged_count = res_dedup.get("contacts_merged_count", 0)
        logs.append(f"✨ Deduplicação: {merged_count} contatos duplicados fundidos e consolidados.")

        # Passo 3: Sincronização de Avatares
        logs.append("📸 [ETAPA 3/4] Sincronização de Fotos de Perfil e PushNames (Evolution API)...")
        res_avatars = await self.sync_all_avatars_from_evolution(force_all=False, db=db)
        logs.extend(res_avatars.get("details", []))

        # Passo 4: Sincronização no Grafo
        logs.append("🧠 [ETAPA 4/4] Atualizando Topologia Relacional no Grafo de Conhecimento...")
        knowledge_graph._save()
        total_nodes = knowledge_graph.graph.number_of_nodes()
        total_edges = knowledge_graph.graph.number_of_edges()
        logs.append(f"✨ Grafo MUSA atualizado: {total_nodes} entidades, {total_edges} conexões relacionais.")

        logs.append("================================================================")
        logs.append("🎉 PIPELINE MESTRE CONCLUÍDO COM SUCESSO!")
        logs.append("================================================================")

        return {
            "status": "success",
            "import_stats": res_import,
            "dedup_stats": res_dedup,
            "avatar_stats": res_avatars,
            "graph_stats": {"nodes": total_nodes, "edges": total_edges},
            "details": logs,
        }


contact_service = ContactService()

