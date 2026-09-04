"""Repositório Unificado de Memória (Relacional, Vetorial e Grafo)."""

import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional, List
from uuid import uuid4

from sqlalchemy.orm import Session, joinedload
from src.ai_gateway.providers import get_ai_provider
from src.ai_gateway.schemas import SemanticExtractionRequest
from src.config import settings
from src.memory.database import SessionLocal
from src.memory.graph import knowledge_graph
from src.memory.models import (
    EmbeddingRecord,
    EntityRecord,
    MemoryStats,
    MessageCreate,
    MessageRecord,
    SearchResult,
    TaskRecord,
    TaskUpdate,
)

logger = logging.getLogger(__name__)


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calcula a similaridade de cosseno entre dois vetores numéricos."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class MemoryRepository:
    """Repositório de persistência e recuperação de memórias."""

    def __init__(self):
        self.embedding_provider = get_ai_provider(
            provider_override=settings.EMBEDDING_PROVIDER,
            model_override=settings.EMBEDDING_MODEL,
        )


    async def generate_embedding(self, text: str) -> list[float]:
        """Gera embedding para o texto utilizando o provedor configurado."""
        try:
            return await self.embedding_provider.generate_embedding(text)
        except Exception as e:
            logger.error(f"Erro ao gerar embedding: {e}")
            # Fallback determinístico
            import hashlib, random
            seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (10**8)
            rng = random.Random(seed)
            return [rng.uniform(-1.0, 1.0) for _ in range(768)]

    async def save_message(self, data: MessageCreate, db: Session | None = None) -> MessageRecord | None:
        """Salva a mensagem, executa extração semântica silenciosa, salva entidades/tarefas, embedding e atualiza o grafo.

        Se a mensagem for vazia, ruído, sticker ou apenas emojis, é completamente descartada e retorna None.
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            # 1. Verificação de Descarte de Mensagem (Vazio, apenas emojis, stickers, ruídos)
            from src.ai_gateway.bypass import should_drop_message, should_bypass_ai, is_owner_interaction
            msg_type = (data.meta_info or {}).get("message_type", "text") if isinstance(data.meta_info, dict) else "text"
            text_to_check = data.revised_text or data.raw_text or ""
            
            drop_active, drop_reason = should_drop_message(
                text_to_check,
                message_type=msg_type,
                meta_info=data.meta_info,
                speaker=data.speaker,
                db=db,
            )
            if drop_active:
                logger.info(f"🛡️ [Privilégio] Mensagem DESCARTADA (não salva na MUSA): remetente='{data.speaker}', motivo='{drop_reason}', texto='{text_to_check[:40]}'")
                return None

            msg_id = str(uuid4())

            # 2. Verificação de Bypass de IA para extração semântica
            bypass_active, bypass_reason = should_bypass_ai(
                text_to_check,
                message_type=msg_type,
                meta_info=data.meta_info,
                speaker=data.speaker,
                db=db,
            )

            if bypass_active:
                logger.info(f"⚡ [AI Gateway] Bypass de IA ativado para remetente='{data.speaker}': motivo='{bypass_reason}'")
                from src.ai_gateway.schemas import SemanticExtractionResponse
                extracted = SemanticExtractionResponse(
                    intent="NOTE",
                    summary=text_to_check[:120] if text_to_check else "",
                    sentiment="NEUTRAL",
                    sentiment_score=0.0,
                    tasks=[],
                    entities=[],
                    triples=[],
                    decisions=[],
                    ideas=[],
                    topics=[],
                    urgency="LOW",
                    provider="bypass",
                    model="bypass",
                    processing_time_ms=0.0,
                )
            else:
                # Extração Semântica estruturada com IA
                extraction_req = SemanticExtractionRequest(
                    text=data.revised_text,
                    speaker=data.speaker,
                    context=str(data.meta_info) if data.meta_info else None,
                    include_dictionary=True,
                )
                try:
                    from src.ai_gateway.extractor import semantic_extractor
                    extracted = await semantic_extractor.extract(extraction_req)
                except Exception as extract_err:
                    logger.warning(f"Extração semântica com IA falhou ({extract_err}). Usando fallback heurístico.")
                    from src.ai_gateway.schemas import SemanticExtractionResponse
                    extracted = SemanticExtractionResponse(
                        intent="NOTE",
                        summary=data.revised_text[:120] if data.revised_text else "",
                        sentiment="NEUTRAL",
                        sentiment_score=0.0,
                        tasks=[],
                        entities=[],
                        triples=[],
                        decisions=[],
                        ideas=[],
                        topics=[],
                        urgency="MEDIUM",
                        provider="fallback",
                        model="fallback",
                        processing_time_ms=0.0,
                    )

            # Importa dinamicamente contact_service para evitar circular import
            from src.contacts.service import contact_service

            weighted_message_urgency = contact_service.calculate_priority_for_message(
                sender_phone_or_name=data.speaker,
                raw_urgency=extracted.urgency,
                db=db,
            )

            # 2. Computa prosódia acústica se houver áudio e meta_info não contiver
            final_meta = dict(data.meta_info or {})
            if data.audio_duration_s and "prosody" not in final_meta:
                from src.transcriber.prosody_analyzer import prosody_analyzer
                prosody_obj = prosody_analyzer.analyze_speech_prosody(
                    duration=data.audio_duration_s,
                    segments=[],
                    text=data.revised_text or data.raw_text or "",
                )
                final_meta["prosody"] = prosody_obj.model_dump()

            # 3. Cria registro da mensagem
            msg_created_at = data.created_at or datetime.now(timezone.utc)
            if msg_created_at.tzinfo is not None:
                msg_created_at = msg_created_at.astimezone(timezone.utc).replace(tzinfo=None)

            message = MessageRecord(
                id=msg_id,
                created_at=msg_created_at,
                speaker=data.speaker,
                raw_text=data.raw_text,
                revised_text=data.revised_text,
                audio_duration_s=data.audio_duration_s,
                audio_filename=data.audio_filename,
                intent=extracted.intent,
                summary=extracted.summary,
                sentiment=extracted.sentiment or "NEUTRAL",
                sentiment_score=extracted.sentiment_score or 0.0,
                urgency=weighted_message_urgency,
                meta_info=final_meta,
            )
            db.add(message)

            # 3. Salva Tarefas extraídas SOMENTE se permitido para o remetente (Proprietário ou contato com toggle ativo)
            extracted_tasks_dicts = []
            allow_tasks_for_speaker = False

            if is_owner_interaction(data.speaker, data.meta_info):
                allow_tasks_for_speaker = True
            else:
                from src.contacts.service import contact_service
                speaker_val = (data.speaker or "").strip()
                phone_val = ""
                if data.meta_info and isinstance(data.meta_info, dict):
                    phone_val = data.meta_info.get("remoteJid") or data.meta_info.get("phone_number") or ""
                contact_match = None
                if phone_val:
                    contact_match = contact_service.get_contact_by_phone(phone_val, db=db)
                if not contact_match and speaker_val:
                    contact_match = contact_service.get_contact_by_name(speaker_val, db=db)

                if contact_match and bool(getattr(contact_match, "can_generate_tasks", False)):
                    allow_tasks_for_speaker = True

            if allow_tasks_for_speaker:
                from src.memory.task_sentiment_analyzer import task_sentiment_analyzer
                source_msg_text = data.revised_text or data.raw_text or ""

                # Carrega tarefas PENDENTES ativas para deduplicação semântica com spaCy
                active_pending_tasks = db.query(TaskRecord).filter(TaskRecord.status == "PENDING").all()

                for t in extracted.tasks:
                    is_actionable = task_sentiment_analyzer.is_actionable_task(
                        title=t.title,
                        source_text=source_msg_text,
                    )
                    if not is_actionable:
                        logger.info(f"🚫 [Tarefas] Candidata a tarefa '{t.title}' descartada pelo filtro spaCy NLP anti-ruído.")
                        continue

                    # Deduplicação Semântica com spaCy NLP e Polímnia contra tarefas pendentes existentes
                    similar_match = task_sentiment_analyzer.find_similar_existing_task(
                        candidate_title=t.title,
                        candidate_context=source_msg_text,
                        existing_tasks=active_pending_tasks,
                        similarity_threshold=0.48,
                    )
                    if similar_match:
                        existing_task, sim_score = similar_match
                        logger.info(
                            f"🤝 [Tarefas Terpsícore] Tarefa semelhante detectada com spaCy (sim={sim_score:.2f}): "
                            f"'{t.title}' unificada com existente id={existing_task.id} ('{existing_task.title}')"
                        )
                        # Consolida a nova menção nas anotações da tarefa existente
                        now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
                        mention_note = f"\n🔄 [Menção adicional em {now_str} por {data.speaker}]: {t.title} (Contexto: \"{source_msg_text[:120]}\")"
                        if existing_task.notes:
                            existing_task.notes = f"{existing_task.notes.strip()}{mention_note}"
                        else:
                            existing_task.notes = mention_note.strip()

                        # Atualiza prioridade se a nova menção for de maior urgência
                        p_weights = {"URGENT": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
                        current_p_weight = p_weights.get(str(existing_task.priority or "").upper(), 2)
                        new_p_weight = p_weights.get(str(t.priority or "").upper(), 2)
                        if new_p_weight > current_p_weight:
                            existing_task.priority = t.priority

                        # Atualiza data limite se a nova trouxer especificação
                        if t.due_date and not existing_task.due_date:
                            existing_task.due_date = t.due_date

                        t_dict = t.model_dump()
                        t_dict["id"] = existing_task.id
                        t_dict["priority"] = existing_task.priority
                        t_dict["is_merged"] = True
                        extracted_tasks_dicts.append(t_dict)
                        continue

                    task_id = str(uuid4())
                    weighted_task_priority = contact_service.calculate_priority_for_message(
                        sender_phone_or_name=data.speaker,
                        raw_urgency=t.priority,
                        db=db,
                    )

                    # Inferência de atributos estratégicos do módulo Terpsícore
                    task_context_lower = f"{t.title} {source_msg_text}".lower()
                    is_idea_flag = any(w in task_context_lower for w in ["ideia", "semente", "insight", "pensar em", "sugestão", "brainstorm", "talvez criar"])
                    is_epic_flag = any(w in task_context_lower for w in ["épico", "epico", "projeto", "meta anual", "iniciativa", "reestruturação", "longo prazo"])
                    is_fav_flag = any(w in task_context_lower for w in ["favorito", "favorita", "destaque", "importante", "estrela"])
                    if any(w in task_context_lower for w in ["urgente", "crítico", "critico", "prioridade máxima", "urgência", "asap"]):
                        weighted_task_priority = "URGENT"

                    task_rec = TaskRecord(
                        id=task_id,
                        message_id=msg_id,
                        created_at=msg_created_at,
                        title=t.title,
                        assignee=t.assignee,
                        due_date=t.due_date,
                        priority=weighted_task_priority,
                        status="PENDING",
                        is_idea=is_idea_flag,
                        is_epic=is_epic_flag,
                        is_favorite=is_fav_flag,
                        in_vault=False,
                    )
                    # Verifica se o horizonte temporal segrega para o Baú (Vault > 7 dias)
                    if self.is_task_in_vault(task_rec):
                        task_rec.in_vault = True
                        task_rec.vault_reason = "Horizonte superior a 7 dias detectado automaticamente"

                    db.add(task_rec)
                    active_pending_tasks.append(task_rec)
                    t_dict = t.model_dump()
                    t_dict["priority"] = weighted_task_priority
                    t_dict["is_idea"] = is_idea_flag
                    t_dict["is_epic"] = is_epic_flag
                    t_dict["is_favorite"] = is_fav_flag
                    t_dict["in_vault"] = task_rec.in_vault
                    extracted_tasks_dicts.append(t_dict)
            else:
                logger.info(f"📋 [Tarefas] Geração de tarefas ignorada para '{data.speaker}' (toggle de tarefas desativado no cartão).")


            # 4. Salva Entidades extraídas
            extracted_entities_dicts = []
            for e in extracted.entities:
                ent_id = str(uuid4())
                ent_rec = EntityRecord(
                    id=ent_id,
                    message_id=msg_id,
                    name=e.name,
                    category=e.category,
                    details=e.details,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(ent_rec)
                extracted_entities_dicts.append(e.model_dump())

            # 5. Gera e Salva Embedding Semântico
            embedding_vector = await self.generate_embedding(data.revised_text)
            emb_id = str(uuid4())
            emb_rec = EmbeddingRecord(
                id=emb_id,
                message_id=msg_id,
                text_content=data.revised_text,
                embedding_json=embedding_vector,
                created_at=datetime.now(timezone.utc),
            )
            db.add(emb_rec)
            db.commit()
            db.refresh(message)

            # 6. Auto-criação / Sincronização Inteligente de Contatos no Banco SQL e Grafo
            try:
                from src.contacts.models import ContactRecord
                from src.contacts.service import contact_service, generate_contact_id
                from src.ai_gateway.bypass import is_group_message, is_owner_interaction, is_valid_contact_phone, normalize_text
                import re

                # Se for mensagem de grupo ou transmissão, NUNCA cria cartão de contato
                meta = data.meta_info if isinstance(data.meta_info, dict) else {}
                speaker_val = (data.speaker or "").strip()

                if not is_group_message(meta, speaker_val) and speaker_val:
                    raw_phone = meta.get("remoteJid", "") or meta.get("phone", "") or speaker_val
                    digits = re.sub(r"\D", "", str(raw_phone).split("@")[0])
                    push_name = meta.get("pushName")

                    if is_owner_interaction(speaker_val, meta):
                        # Garante apenas o contato único do proprietário
                        owner_rec = db.query(ContactRecord).filter(
                            (ContactRecord.name.ilike("%Bruno%Conter%")) | (ContactRecord.phone_number.like("%97604925%"))
                        ).first()
                        if not owner_rec:
                            c_id = generate_contact_id("Bruno Conter", settings.USER_PHONE_NUMBER)
                            if c_id:
                                owner_rec = ContactRecord(
                                    id=c_id,
                                    name="Bruno Conter",
                                    phone_number=settings.USER_PHONE_NUMBER or "554497604925",
                                    nickname="Bruno Conter (Proprietário / Arquiteto)",
                                    role="OWNER",
                                    company="Hermes Memory / Homelab",
                                    projects_json=[],
                                    notes="Criador, Proprietário e Arquiteto Supremo do sistema Hermes Voice Memory.",
                                    created_at=datetime.now(timezone.utc),
                                    updated_at=datetime.now(timezone.utc),
                                )
                                db.add(owner_rec)
                                db.commit()
                        else:
                            owner_rec.name = "Bruno Conter"
                            owner_rec.phone_number = settings.USER_PHONE_NUMBER or "554497604925"
                            owner_rec.role = "OWNER"
                            owner_rec.nickname = "Bruno Conter (Proprietário / Arquiteto)"
                            owner_rec.company = "Hermes Memory / Homelab"
                            owner_rec.notes = "Criador, Proprietário e Arquiteto Supremo do sistema Hermes Voice Memory."
                            owner_rec.last_interaction_at = message.created_at
                            db.commit()
                        if owner_rec:
                            contact_service._sync_contact_to_graph(owner_rec)
                    elif is_valid_contact_phone(digits):
                        # Só cria ou atualiza cartão para contatos que possuam telefone padrão válido
                        existing_contact = db.query(ContactRecord).filter(
                            (ContactRecord.phone_number == digits) | (ContactRecord.phone_number.like(f"%{digits[-8:]}%"))
                        ).first()

                        if not existing_contact:
                            clean_speaker = normalize_text(speaker_val)
                            for c in db.query(ContactRecord).all():
                                c_clean = normalize_text(c.name)
                                if c_clean and (c_clean in clean_speaker or clean_speaker in c_clean):
                                    existing_contact = c
                                    break

                        if not existing_contact:
                            contact_name = push_name if (push_name and speaker_val.isdigit()) else speaker_val
                            c_id = generate_contact_id(contact_name, digits)
                            if c_id:
                                new_contact = ContactRecord(
                                    id=c_id,
                                    name=contact_name,
                                    phone_number=digits,
                                    role="UNKNOWN",
                                    company="",
                                    projects_json=[],
                                    notes="Contato identificado via mensagem recebida.",
                                    last_interaction_at=message.created_at,
                                    created_at=datetime.now(timezone.utc),
                                    updated_at=datetime.now(timezone.utc),
                                )
                                db.add(new_contact)
                                db.commit()
                                contact_service._sync_contact_to_graph(new_contact)
                        else:
                            if push_name and existing_contact.name.isdigit():
                                existing_contact.name = push_name
                            existing_contact.last_interaction_at = message.created_at
                            db.commit()
                            contact_service._sync_contact_to_graph(existing_contact)

                # 6.2 Entidades do tipo PERSON são enriquecidas no Grafo, mas NÃO criam cartões sem telefone
                for e in extracted.entities:
                    if e.category and e.category.upper() == "PERSON" and e.name:
                        person_name = e.name.strip()
                        if len(person_name) > 1 and not is_owner_interaction(person_name) and not is_group_message(speaker=person_name):
                            knowledge_graph.add_node(person_name, category="PERSON", details=e.details or "Entidade mencionada")

                # 6.3 Processa Termos Dúbios / Esforço de Adaptação (Buffer de Aprendizado Ativo)
                if hasattr(extracted, "unclear_terms") and extracted.unclear_terms:
                    from src.memory.models import LexicalCandidateRecord
                    for ut in extracted.unclear_terms:
                        raw = getattr(ut, "raw_snippet", "") or ""
                        if raw and len(raw.strip()) > 1:
                            raw_clean = raw.strip()
                            cand = db.query(LexicalCandidateRecord).filter(
                                LexicalCandidateRecord.raw_term.ilike(raw_clean),
                                LexicalCandidateRecord.status == "PENDING"
                            ).first()
                            if cand:
                                cand.occurrence_count = (cand.occurrence_count or 1) + 1
                                cand.updated_at = datetime.now(timezone.utc)
                                if getattr(ut, "suggested_meaning", None):
                                    cand.suggested_term = getattr(ut, "suggested_meaning", None)
                            else:
                                new_cand = LexicalCandidateRecord(
                                    id=str(uuid4()),
                                    raw_term=raw_clean,
                                    suggested_term=getattr(ut, "suggested_meaning", None),
                                    context=data.revised_text[:300] if data.revised_text else "",
                                    speaker=data.speaker,
                                    category=getattr(ut, "category", "GERAL") or "GERAL",
                                    reason=getattr(ut, "reason", None) or "Termo ambíguo identificado no áudio/texto",
                                    status="PENDING",
                                    occurrence_count=1,
                                    created_at=datetime.now(timezone.utc),
                                    updated_at=datetime.now(timezone.utc),
                                )
                                db.add(new_cand)
                    db.commit()
            except Exception as exc:
                logger.warning(f"Aviso ao auto-cadastrar contatos ou termos léxicos na mensagem: {exc}")
                db.rollback()

            # 7. Atualiza o Grafo Relacional de Conhecimento e Triplas Semânticas
            knowledge_graph.add_interaction(
                speaker=data.speaker,
                entities=extracted_entities_dicts,
                tasks=extracted_tasks_dicts,
                intent=extracted.intent,
            )
            if hasattr(extracted, "triples") and extracted.triples:
                knowledge_graph.link_triples(
                    triples=extracted.triples,
                    speaker=data.speaker,
                )

            return message
        except Exception as e:
            db.rollback()
            logger.error(f"Erro ao salvar mensagem na memória: {e}")
            raise
        finally:
            if should_close:
                db.close()

    async def search_memories(
        self, query: str, top_k: int = 5, min_similarity: float = 0.0, db: Session | None = None
    ) -> list[SearchResult]:
        """Realiza busca vetorial semântica calculando similaridade de cosseno."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            query_vector = await self.generate_embedding(query)
            all_embeddings = db.query(EmbeddingRecord).all()

            results: list[SearchResult] = []
            for emb in all_embeddings:
                stored_vector = emb.embedding_json
                if not isinstance(stored_vector, list):
                    continue

                sim = cosine_similarity(query_vector, stored_vector)
                if sim >= min_similarity:
                    msg = db.query(MessageRecord).filter(MessageRecord.id == emb.message_id).first()
                    if msg:
                        results.append(
                            SearchResult(
                                message_id=msg.id,
                                text=msg.revised_text,
                                speaker=msg.speaker,
                                intent=msg.intent,
                                summary=msg.summary,
                                similarity=round(sim, 4),
                                created_at=msg.created_at,
                            )
                        )

            # Ordena decrescente por similaridade
            results.sort(key=lambda x: x.similarity, reverse=True)
            return results[:top_k]
        finally:
            if should_close:
                db.close()

    async def query_hermes_rag(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.0,
        include_graph: bool = True,
        db: Session | None = None,
    ):
        """Executa consulta com RAG Híbrido ao Agente Hermes combinando busca vetorial, grafo e tarefas."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            from src.ai_gateway.agent import hermes_agent_service
            from src.ai_gateway.schemas import MemorySourceCitation, HermesQueryResponse
            from src.memory.semantic_cache import semantic_cache
            from src.memory.query_understanding import hermes_query_understanding
            from src.memory.timezone_utils import BRASILIA_TZ, format_brt, get_now_brt, to_local_tz
            import re
            from datetime import datetime, time, timedelta, timezone
            from sqlalchemy import or_

            # Checagem de Cache Semântico Local (Zero Tokens)
            cached_res = semantic_cache.get(query)
            if cached_res:
                return HermesQueryResponse(**cached_res)

            # 1. Análise Semântica e Morfossintática com spaCy + Polímnia
            parsed = hermes_query_understanding.analyze_query(query, db=db)

            # Janelas temporais em horário oficial de Brasília (UTC-3)
            now_brt = get_now_brt()
            today_date = now_brt.date()
            start_of_today = datetime.combine(today_date, time.min, tzinfo=BRASILIA_TZ).astimezone(timezone.utc)
            end_of_today = datetime.combine(today_date, time.max, tzinfo=BRASILIA_TZ).astimezone(timezone.utc)

            yesterday_date = today_date - timedelta(days=1)
            start_of_yesterday = datetime.combine(yesterday_date, time.min, tzinfo=BRASILIA_TZ).astimezone(timezone.utc)
            end_of_yesterday = datetime.combine(yesterday_date, time.max, tzinfo=BRASILIA_TZ).astimezone(timezone.utc)

            seen_ids = set()
            sources: list[MemorySourceCitation] = []
            temporal_notes: list[str] = []

            # 2. Priorização por Interlocutor Identificado Dinamicamente
            if parsed.target_speaker_full_name or parsed.target_speaker:
                spk_name_label = parsed.target_speaker_full_name or parsed.target_speaker
                parts = set()
                if parsed.target_speaker:
                    parts.add(parsed.target_speaker.strip())
                if parsed.target_speaker_full_name:
                    for p in re.findall(r"\w+", parsed.target_speaker_full_name):
                        if len(p) >= 3 and p.lower() not in ("de", "da", "do", "dos", "das"):
                            parts.add(p)

                speaker_clauses = [MessageRecord.speaker.ilike(f"%{p}%") for p in parts]
                speaker_cond = or_(*speaker_clauses) if speaker_clauses else MessageRecord.speaker.ilike(f"%{spk_name_label}%")

                if parsed.is_today:
                    # Filtra estritamente o dia de hoje
                    target_messages = (
                        db.query(MessageRecord)
                        .filter(
                            speaker_cond,
                            MessageRecord.created_at >= start_of_today,
                            MessageRecord.created_at <= end_of_today,
                        )
                        .order_by(MessageRecord.created_at.desc())
                        .all()
                    )
                    if not target_messages:
                        # Busca a última mensagem do histórico geral para contextualização
                        last_msg = (
                            db.query(MessageRecord)
                            .filter(speaker_cond)
                            .order_by(MessageRecord.created_at.desc())
                            .first()
                        )
                        if last_msg:
                            last_date_str = format_brt(last_msg.created_at)
                            last_text = (last_msg.revised_text or last_msg.summary or "")[:120]
                            temporal_notes.append(
                                f"Nota Temporal: Nenhuma mensagem registrada com {spk_name_label} hoje ({format_brt(now_brt, '%d/%m/%Y')}). "
                                f"Última conversa registrada no histórico ocorreu em {last_date_str}: \"{last_text}\""
                            )
                elif parsed.is_yesterday:
                    # Filtra estritamente o dia de ontem
                    target_messages = (
                        db.query(MessageRecord)
                        .filter(
                            speaker_cond,
                            MessageRecord.created_at >= start_of_yesterday,
                            MessageRecord.created_at <= end_of_yesterday,
                        )
                        .order_by(MessageRecord.created_at.desc())
                        .all()
                    )
                    if not target_messages:
                        last_msg = (
                            db.query(MessageRecord)
                            .filter(speaker_cond)
                            .order_by(MessageRecord.created_at.desc())
                            .first()
                        )
                        if last_msg:
                            last_date_str = format_brt(last_msg.created_at)
                            last_text = (last_msg.revised_text or last_msg.summary or "")[:120]
                            temporal_notes.append(
                                f"Nota Temporal: Nenhuma mensagem registrada com {spk_name_label} ontem ({format_brt(start_of_yesterday, '%d/%m/%Y')}). "
                                f"Última conversa registrada no histórico ocorreu em {last_date_str}: \"{last_text}\""
                            )
                else:
                    # Sem restrição de dia específico: pega as mensagens mais recentes
                    target_messages = (
                        db.query(MessageRecord)
                        .filter(speaker_cond)
                        .order_by(MessageRecord.created_at.desc())
                        .limit(10)
                        .all()
                    )

                for tm in target_messages:
                    seen_ids.add(tm.id)
                    snippet = tm.revised_text or tm.raw_text or tm.summary or ""
                    sources.append(
                        MemorySourceCitation(
                            message_id=tm.id,
                            speaker=tm.speaker or spk_name_label,
                            text_snippet=snippet,
                            similarity=0.98,
                            created_at=format_brt(tm.created_at) if tm.created_at else None,
                        )
                    )

            # 3. Busca Semântica Vetorial (se necessário complementar)
            # Se for diálogo de interlocutor com filtro de hoje/ontem e sem mensagens encontradas, não puxa mensagens vetoriais de terceiros
            skip_vector = (parsed.intent == "INTERLOCUTOR_DIALOGUE" and (parsed.is_today or parsed.is_yesterday) and len(sources) == 0)

            if len(sources) < top_k and not skip_vector:
                search_results = await self.search_memories(
                    query=query,
                    top_k=top_k * 2 if (parsed.is_today or parsed.is_yesterday) else top_k,
                    min_similarity=min_similarity,
                    db=db,
                )

                for sr in search_results:
                    if sr.message_id not in seen_ids:
                        if parsed.intent == "INTERLOCUTOR_DIALOGUE" and (parsed.target_speaker_full_name or parsed.target_speaker):
                            spk_norm = (sr.speaker or "").lower()
                            first_norm = (parsed.target_speaker_full_name or parsed.target_speaker).split()[0].lower()
                            if first_norm not in spk_norm and first_norm not in (sr.text or "").lower():
                                continue

                        # Aplica filtro de data se for today ou yesterday
                        if parsed.is_today and sr.created_at:
                            sr_utc = sr.created_at if getattr(sr.created_at, "tzinfo", None) else sr.created_at.replace(tzinfo=timezone.utc)
                            if not (start_of_today <= sr_utc <= end_of_today):
                                continue
                        elif parsed.is_yesterday and sr.created_at:
                            sr_utc = sr.created_at if getattr(sr.created_at, "tzinfo", None) else sr.created_at.replace(tzinfo=timezone.utc)
                            if not (start_of_yesterday <= sr_utc <= end_of_yesterday):
                                continue

                        seen_ids.add(sr.message_id)
                        sources.append(
                            MemorySourceCitation(
                                message_id=sr.message_id,
                                speaker=sr.speaker,
                                text_snippet=sr.summary or sr.text[:140],
                                similarity=sr.similarity,
                                created_at=format_brt(sr.created_at) if sr.created_at else None,
                            )
                        )
                        if len(sources) >= top_k:
                            break

            # Se a busca envolve temporalidade recente ou diálogo, ordena por ordem cronológica recente
            if parsed.is_recent or parsed.intent == "INTERLOCUTOR_DIALOGUE":
                sources.sort(key=lambda s: s.created_at or "", reverse=True)

            # 4. GraphRAG Híbrido com Sementes Higienizadas e Termos de Polímnia
            related_entities = []
            subgraph_data = {}
            if include_graph:
                from src.memory.hybrid_graph_rag import hybrid_graph_rag

                # 4.1 Injeta termos mapeados em Polímnia
                for dt in parsed.domain_terms:
                    exp_str = f" ({dt['expansion']})" if dt.get('expansion') else ""
                    desc_str = f" — {dt['description']}" if dt.get('description') else ""
                    related_entities.append(f"Glossário Polímnia: {dt['term']}{exp_str}{desc_str}")

                # 4.2 Expande subgrafo NetworkX
                if parsed.clean_seed_entities:
                    subgraph_data = hybrid_graph_rag.expand_subgraph_2_hop(parsed.clean_seed_entities[:5], max_hops=2)
                    related_entities.extend(subgraph_data.get("node_details", [])[:6])
                    related_entities.extend(subgraph_data.get("triples", [])[:6])

                # 4.3 Dados oficiais de contato se identificados
                if parsed.target_speaker_full_name:
                    from src.contacts.models import ContactRecord
                    matched_c = db.query(ContactRecord).filter(ContactRecord.name == parsed.target_speaker_full_name).first()
                    if matched_c:
                        c_parts = [f"Contato Oficial: {matched_c.name}"]
                        if matched_c.role:
                            c_parts.append(f"Cargo: {matched_c.role}")
                        if matched_c.company:
                            c_parts.append(f"Empresa: {matched_c.company}")
                        related_entities.append(" | ".join(c_parts))

            # 4.4 Adiciona notas de temporalidade
            if temporal_notes:
                related_entities.extend(temporal_notes)

            # 5. Busca de tarefas pendentes relacionadas
            pending_tasks_objs = self.list_tasks(status="PENDING", db=db)
            related_tasks = []
            target_spk_raw = (parsed.target_speaker_full_name or parsed.target_speaker or "").strip()
            target_spk_first = target_spk_raw.split()[0].lower() if target_spk_raw else ""

            for t in pending_tasks_objs:
                spk = (t.speaker or "").lower()
                asg = (t.assignee or "").lower()
                title_lower = t.title.lower()

                matches_task = (
                    (target_spk_first and (target_spk_first in spk or target_spk_first in asg or target_spk_first in title_lower))
                    or any(tok.lower() in title_lower for tok in parsed.clean_seed_entities)
                    or (t.message_id in seen_ids)
                )

                if matches_task:
                    speaker_info = f"[Solicitante: {t.speaker}] " if t.speaker else ""
                    assignee = f" (Resp: {t.assignee})" if t.assignee else ""
                    due = f" [Prazo: {t.due_date}]" if t.due_date else ""
                    notes = f" (Notas: {t.notes})" if t.notes else ""
                    related_tasks.append(f"{speaker_info}{t.title}{assignee}{due}{notes} [Prioridade: {t.priority}]")

            # 6. Fusão e Re-ranqueamento com Boost de Subgrafo
            if include_graph and parsed.clean_seed_entities and subgraph_data:
                from src.memory.hybrid_graph_rag import hybrid_graph_rag
                fused = hybrid_graph_rag.fuse_vector_and_graph_results(
                    vector_sources=sources,
                    subgraph_data=subgraph_data,
                    pending_tasks=related_tasks,
                )
                final_sources = fused["sources"]
            else:
                final_sources = sources

            # 7. Chama o Agente Hermes para inferência e resposta estrita com humanização
            result = await hermes_agent_service.answer_hermes_query(
                query=query,
                sources=final_sources[:10],
                related_entities=list(set(related_entities))[:8],
                pending_tasks=related_tasks[:5],
                parsed_query=parsed,
            )
            # Armazena no cache semântico para consultas subsequentes (0 tokens)
            semantic_cache.set(query, result.model_dump())
            return result
        finally:
            if should_close:
                db.close()

    def is_task_in_vault(self, task: TaskRecord, now_dt: datetime | None = None) -> bool:
        """Determina com precisão se uma tarefa pertence ao Baú (Vault / Stage).
        
        REGRA ESTRITA: O Baú só pode conter tarefas com horizonte temporal superior a 1 semana (> 7 dias).
        Qualquer tarefa com prazo ou adiamento <= 7 dias pertence estritamente ao Fluxo Normal (Imediato).
        Quando o tempo passa e faltam 7 dias ou menos para o prazo, ela retorna automaticamente ao Fluxo Normal.
        """
        from datetime import timedelta

        if now_dt is None:
            now_dt = datetime.now(timezone.utc)

        one_week_ahead = now_dt + timedelta(days=7)

        # 1. Adiamento explícito ativo (postponed_until)
        if task.postponed_until:
            post_dt = task.postponed_until
            if post_dt.tzinfo is None:
                post_dt = post_dt.replace(tzinfo=timezone.utc)
            # Se adiada para mais de 1 semana à frente, permanece no Baú
            if post_dt > one_week_ahead:
                return True
            # Se faltam 7 dias ou menos (ou já expirou), RETORNA ao fluxo normal
            return False

        # 2. Análise do prazo informado (due_date)
        if task.due_date:
            due_str = str(task.due_date).strip().lower()
            if any(term in due_str for term in ["mês", "mes", "ano", "30 dias", "15 dias", "2 semanas", "3 semanas", "sem prazo"]):
                return True
            try:
                import re
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})|(\d{2}/\d{2}/\d{4})", due_str)
                if date_match:
                    d_raw = date_match.group(0)
                    if "-" in d_raw:
                        d_dt = datetime.strptime(d_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    else:
                        d_dt = datetime.strptime(d_raw, "%d/%m/%Y").replace(tzinfo=timezone.utc)
                    
                    if d_dt > one_week_ahead:
                        return True
                    # Se o prazo for de até 7 dias, pertence ao Fluxo Normal
                    return False
            except Exception:
                pass

        # 3. Marcada manualmente como in_vault sem data específica (considera pendência de longo prazo)
        if task.in_vault:
            return True

        return False

    def list_tasks(
        self,
        status: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        speaker: str | None = None,
        view_mode: str = "active",  # active, vault, garden, all
        is_idea: bool | None = None,
        is_epic: bool | None = None,
        is_favorite: bool | None = None,
        db: Session | None = None,
    ) -> list[Any]:
        """Lista tarefas filtradas com segregação estrita entre Fluxo Normal, Vault e Jardim."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            from src.contacts.models import ContactRecord
            from src.memory.models import TaskResponse
            from src.memory.task_sentiment_analyzer import task_sentiment_analyzer

            now_dt = datetime.now(timezone.utc)
            contacts_map = {c.name.lower(): c for c in db.query(ContactRecord).all()}

            query = db.query(TaskRecord)
            if status:
                query = query.filter(TaskRecord.status == status.upper())
            if priority:
                query = query.filter(TaskRecord.priority == priority.upper())
            if assignee:
                query = query.filter(TaskRecord.assignee.ilike(f"%{assignee}%"))
            if is_idea is not None:
                query = query.filter(TaskRecord.is_idea == is_idea)
            if is_epic is not None:
                query = query.filter(TaskRecord.is_epic == is_epic)
            if is_favorite is not None:
                query = query.filter(TaskRecord.is_favorite == is_favorite)

            records = query.all()
            filtered_records = []
            
            for r in records:
                in_v = self.is_task_in_vault(r, now_dt)
                if view_mode == "active":
                    # Apenas tarefas que NÃO estão no Vault
                    if in_v:
                        continue
                elif view_mode == "vault":
                    # Apenas tarefas do Vault (> 1 semana / arquivadas)
                    if not in_v:
                        continue
                elif view_mode == "garden":
                    # Apenas ideias ou conquistas realizadas
                    if not (r.is_idea or r.status == "DONE"):
                        continue
                # Se view_mode == "all", inclui tudo

                # Filtro por remetente/origem se especificado
                msg = r.message
                speaker_name = msg.speaker if msg else "user"
                if speaker:
                    spk_clean = speaker.strip().lower()
                    if spk_clean and spk_clean != "all" and spk_clean not in speaker_name.lower():
                        continue

                filtered_records.append((r, in_v))

            # Ordenação com prioridade: Favoritos > Épicos > Urgência > Data
            priority_weight = {"URGENT": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
            filtered_records.sort(
                key=lambda item: (
                    1 if item[0].is_favorite else 0,
                    1 if item[0].is_epic else 0,
                    priority_weight.get(item[0].priority, 1),
                    item[0].created_at or now_dt,
                ),
                reverse=True,
            )

            responses = []
            for r, in_v in filtered_records:
                msg = r.message
                speaker_name = msg.speaker if msg else "user"
                contact_match = contacts_map.get(speaker_name.lower()) if speaker_name else None

                sender_phone = ""
                if contact_match and contact_match.phone_number:
                    sender_phone = contact_match.phone_number
                elif msg and isinstance(msg.meta_info, dict) and msg.meta_info.get("remoteJid"):
                    sender_phone = msg.meta_info.get("remoteJid", "").split("@")[0]
                elif speaker_name and speaker_name.replace("+", "").isdigit():
                    sender_phone = speaker_name

                sender_role = contact_match.role if contact_match else (contact_match.category if contact_match else None)
                msg_summary = msg.summary if msg else None
                source_snippet = (msg.revised_text[:140] + "...") if msg and len(msg.revised_text) > 140 else (msg.revised_text if msg else None)

                # Extrai tags via spaCy sem custo de tokens de API
                msg_entities = [e.name for e in msg.entities] if (msg and msg.entities) else []
                source_full = (msg.revised_text or msg.raw_text or "") if msg else ""
                tags = task_sentiment_analyzer.extract_task_tags(
                    title=r.title,
                    source_text=source_full,
                    existing_entities=msg_entities,
                    priority=r.priority,
                )

                responses.append(
                    TaskResponse(
                        id=r.id,
                        message_id=r.message_id,
                        title=r.title,
                        assignee=r.assignee,
                        due_date=r.due_date,
                        priority=r.priority,
                        status=r.status,
                        notes=r.notes,
                        created_at=r.created_at,
                        completed_at=r.completed_at,
                        is_idea=bool(r.is_idea),
                        is_epic=bool(r.is_epic),
                        is_favorite=bool(r.is_favorite),
                        in_vault=in_v,
                        postponed_until=r.postponed_until,
                        reminder_scheduled_at=r.reminder_scheduled_at,
                        vault_reason=r.vault_reason,
                        procrastination_factor=r.procrastination_factor,
                        stakeholder_link=r.stakeholder_link,
                        project_link=r.project_link,
                        reassessment_notes=r.reassessment_notes,
                        speaker=speaker_name,
                        sender_phone=sender_phone,
                        sender_role=sender_role,
                        message_time=msg.created_at.strftime("%d/%m/%Y %H:%M") if msg and msg.created_at else None,
                        audio_duration_s=msg.audio_duration_s if msg else None,
                        revised_text=msg.revised_text if msg else None,
                        raw_text=msg.raw_text if msg else None,
                        message_summary=msg_summary,
                        source_text_snippet=source_snippet,
                        tags=tags,
                    )
                )
            return responses
        finally:
            if should_close:
                db.close()

    def toggle_task_favorite(self, task_id: str, db: Session | None = None) -> Any | None:
        """Alterna status de favorito / pin de uma tarefa."""
        return self._toggle_task_field(task_id, "is_favorite", db)

    def toggle_task_epic(self, task_id: str, db: Session | None = None) -> Any | None:
        """Alterna status de Objetivo Épico de uma tarefa."""
        return self._toggle_task_field(task_id, "is_epic", db)

    def toggle_task_idea(self, task_id: str, db: Session | None = None) -> Any | None:
        """Alterna status de Ideia / Semente de uma tarefa."""
        return self._toggle_task_field(task_id, "is_idea", db)

    def _toggle_task_field(self, task_id: str, field_name: str, db: Session | None = None) -> Any | None:
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            from src.memory.models import TaskResponse
            task = db.query(TaskRecord).filter(TaskRecord.id == task_id).first()
            if not task:
                return None
            current_val = getattr(task, field_name, False)
            setattr(task, field_name, not current_val)
            db.commit()
            db.refresh(task)
            return self.get_task_response(task, db)
        finally:
            if should_close:
                db.close()

    def move_task_to_vault(self, task_id: str, payload: Any, db: Session | None = None) -> Any | None:
        """Envia tarefa para o Baú aplicando delay, agendamento de lembrete e reavaliação."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            from datetime import timedelta
            task = db.query(TaskRecord).filter(TaskRecord.id == task_id).first()
            if not task:
                return None

            task.in_vault = True
            now_dt = datetime.now(timezone.utc)

            # Cálculo de delay (mínimo de 8 dias para pertencer ao Baú)
            if hasattr(payload, "postpone_days") and payload.postpone_days:
                days = max(int(payload.postpone_days), 8)
                task.postponed_until = now_dt + timedelta(days=days)
            elif hasattr(payload, "custom_postpone_date") and payload.custom_postpone_date:
                try:
                    custom_dt = datetime.strptime(payload.custom_postpone_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    task.postponed_until = custom_dt
                except Exception:
                    task.postponed_until = now_dt + timedelta(days=8)
            else:
                # Default de 8 dias para horizonte > 1 semana
                task.postponed_until = now_dt + timedelta(days=8)

            # Agendamento de lembrete
            if hasattr(payload, "reminder_datetime") and payload.reminder_datetime:
                try:
                    fmt = "%Y-%m-%d %H:%M" if len(payload.reminder_datetime) > 10 else "%Y-%m-%d"
                    task.reminder_scheduled_at = datetime.strptime(payload.reminder_datetime, fmt).replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            if hasattr(payload, "vault_reason") and payload.vault_reason:
                task.vault_reason = payload.vault_reason
            if hasattr(payload, "procrastination_factor") and payload.procrastination_factor:
                task.procrastination_factor = payload.procrastination_factor
            if hasattr(payload, "stakeholder_link") and payload.stakeholder_link:
                task.stakeholder_link = payload.stakeholder_link
            if hasattr(payload, "project_link") and payload.project_link:
                task.project_link = payload.project_link
            if hasattr(payload, "reassessment_notes") and payload.reassessment_notes:
                task.reassessment_notes = payload.reassessment_notes
            if hasattr(payload, "priority") and payload.priority:
                task.priority = payload.priority

            db.commit()
            db.refresh(task)
            return self.get_task_response(task, db)
        finally:
            if should_close:
                db.close()

    def restore_task_from_vault(self, task_id: str, db: Session | None = None) -> Any | None:
        """Resgata uma tarefa do Baú de volta ao fluxo de execução normal."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            task = db.query(TaskRecord).filter(TaskRecord.id == task_id).first()
            if not task:
                return None
            task.in_vault = False
            task.postponed_until = None
            task.vault_reason = None
            db.commit()
            db.refresh(task)
            return self.get_task_response(task, db)
        finally:
            if should_close:
                db.close()

    def get_task_response(self, task: TaskRecord, db: Session) -> Any:
        """Converte TaskRecord em TaskResponse estruturado."""
        from src.contacts.models import ContactRecord
        from src.memory.models import TaskResponse
        from src.memory.task_sentiment_analyzer import task_sentiment_analyzer

        msg = task.message
        speaker_name = msg.speaker if msg else "user"
        contact_match = db.query(ContactRecord).filter(ContactRecord.name.ilike(speaker_name)).first() if speaker_name else None

        sender_phone = ""
        if contact_match and contact_match.phone_number:
            sender_phone = contact_match.phone_number
        elif msg and isinstance(msg.meta_info, dict) and msg.meta_info.get("remoteJid"):
            sender_phone = msg.meta_info.get("remoteJid", "").split("@")[0]

        msg_entities = [e.name for e in msg.entities] if (msg and msg.entities) else []
        source_full = (msg.revised_text or msg.raw_text or "") if msg else ""
        tags = task_sentiment_analyzer.extract_task_tags(
            title=task.title,
            source_text=source_full,
            existing_entities=msg_entities,
            priority=task.priority,
        )

        return TaskResponse(
            id=task.id,
            message_id=task.message_id,
            title=task.title,
            assignee=task.assignee,
            due_date=task.due_date,
            priority=task.priority,
            status=task.status,
            notes=task.notes,
            created_at=task.created_at,
            completed_at=task.completed_at,
            is_idea=bool(task.is_idea),
            is_epic=bool(task.is_epic),
            is_favorite=bool(task.is_favorite),
            in_vault=self.is_task_in_vault(task),
            postponed_until=task.postponed_until,
            reminder_scheduled_at=task.reminder_scheduled_at,
            vault_reason=task.vault_reason,
            procrastination_factor=task.procrastination_factor,
            stakeholder_link=task.stakeholder_link,
            project_link=task.project_link,
            reassessment_notes=task.reassessment_notes,
            speaker=speaker_name,
            sender_phone=sender_phone,
            sender_role=contact_match.role if contact_match else None,
            message_time=msg.created_at.strftime("%d/%m/%Y %H:%M") if msg and msg.created_at else None,
            audio_duration_s=msg.audio_duration_s if msg else None,
            revised_text=msg.revised_text if msg else None,
            raw_text=msg.raw_text if msg else None,
            message_summary=msg.summary if msg else None,
            source_text_snippet=msg.revised_text[:140] if msg and msg.revised_text else None,
            tags=tags,
        )

    def merge_vault_tasks_by_embeddings(
        self,
        similarity_threshold: float = 0.55,
        db: Session | None = None,
    ) -> dict:
        """Mescla tarefas do Baú por similaridade semântica vetorial (embeddings) e lemas."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            from src.memory.models import TaskMergeCluster, MergeTasksResponse
            from src.memory.task_sentiment_analyzer import task_sentiment_analyzer
            from collections import defaultdict

            all_tasks = db.query(TaskRecord).filter(TaskRecord.status != "DONE").all()
            vault_tasks = [t for t in all_tasks if self.is_task_in_vault(t)]

            if len(vault_tasks) < 2:
                return MergeTasksResponse(
                    status="success",
                    merged_groups_count=0,
                    tasks_merged_count=0,
                    clusters=[],
                    message="Menos de 2 tarefas no Baú para mesclagem semântica.",
                ).model_dump()

            # Mapeamento de embeddings salvos
            emb_map = {}
            for t in vault_tasks:
                if t.message and t.message.embeddings:
                    emb_map[t.id] = t.message.embeddings[0].embedding_json

            visited = set()
            merged_clusters = []
            total_merged = 0

            for i, t1 in enumerate(vault_tasks):
                if t1.id in visited:
                    continue
                cluster = [t1]
                vec1 = emb_map.get(t1.id)

                for j, t2 in enumerate(vault_tasks):
                    if i == j or t2.id in visited:
                        continue
                    vec2 = emb_map.get(t2.id)

                    sim = 0.0
                    if vec1 and vec2:
                        # Similaridade de cosseno vetorial
                        sim = self._cosine_similarity(vec1, vec2)
                    else:
                        # Fallback léxico
                        sim = task_sentiment_analyzer.compute_task_similarity(
                            t1.title, t1.notes or "", t2.title, t2.notes or ""
                        )

                    if sim >= similarity_threshold:
                        cluster.append(t2)
                        visited.add(t2.id)

                if len(cluster) > 1:
                    visited.add(t1.id)
                    primary = cluster[0]
                    merged_ids = []
                    merged_titles = []
                    additional_notes = []

                    for other in cluster[1:]:
                        merged_ids.append(other.id)
                        merged_titles.append(other.title)
                        note_text = (other.notes or other.vault_reason or "").strip()
                        additional_notes.append(f"📌 [Mesclado do Baú: \"{other.title}\"]:\n{note_text}")
                        other.status = "CANCELLED"
                        other.notes = f"[Mesclada no Baú na tarefa {primary.id}]\n{other.notes or ''}"

                    orig = (primary.notes or "").strip()
                    primary.notes = (orig + "\n\n" + "\n\n".join(additional_notes)).strip()
                    total_merged += len(merged_ids)

                    spk = primary.message.speaker if primary.message and primary.message.speaker else "user"
                    merged_clusters.append(
                        TaskMergeCluster(
                            speaker=spk,
                            primary_task_id=primary.id,
                            primary_title=primary.title,
                            merged_task_ids=merged_ids,
                            merged_titles=merged_titles,
                            notes_consolidated_preview=primary.notes[:200] if primary.notes else None,
                        )
                    )

            db.commit()
            return MergeTasksResponse(
                status="success",
                merged_groups_count=len(merged_clusters),
                tasks_merged_count=total_merged,
                clusters=merged_clusters,
                message=f"{len(merged_clusters)} grupo(s) mesclados por embeddings ({total_merged} tarefas unificadas no Baú).",
            ).model_dump()
        finally:
            if should_close:
                db.close()

    def merge_similar_pending_tasks(self, similarity_threshold: float = 0.60, db: Session | None = None) -> dict:
        """Analisa todas as tarefas PENDING agrupadas por pessoa de origem e mescla semelhantes."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            from src.memory.task_sentiment_analyzer import task_sentiment_analyzer
            from src.memory.models import MergeTasksResponse, TaskMergeCluster

            # Busca todas as tarefas PENDENTES
            pending_tasks = (
                db.query(TaskRecord)
                .options(joinedload(TaskRecord.message))
                .filter(TaskRecord.status == "PENDING")
                .all()
            )

            # Agrupa tarefas por interlocutor / solicitante de origem
            grouped: dict[str, list[TaskRecord]] = {}
            for t in pending_tasks:
                speaker_key = (t.message.speaker if t.message and t.message.speaker else "user").strip().lower()
                if speaker_key not in grouped:
                    grouped[speaker_key] = []
                grouped[speaker_key].append(t)

            merged_clusters: list[TaskMergeCluster] = []
            total_merged_tasks = 0

            for speaker, tasks in grouped.items():
                if len(tasks) < 2:
                    continue

                visited = set()
                for i, t1 in enumerate(tasks):
                    if t1.id in visited:
                        continue

                    cluster = [t1]
                    for j, t2 in enumerate(tasks):
                        if i == j or t2.id in visited:
                            continue

                        sim = task_sentiment_analyzer.compute_task_similarity(
                            t1.title, t1.notes or "", t2.title, t2.notes or ""
                        )
                        if sim >= similarity_threshold:
                            cluster.append(t2)
                            visited.add(t2.id)

                    if len(cluster) > 1:
                        visited.add(t1.id)
                        # A tarefa primária é a primeira (mais antiga ou principal)
                        primary_task = cluster[0]
                        merged_ids = []
                        merged_titles = []
                        additional_notes = []

                        for other_task in cluster[1:]:
                            merged_ids.append(other_task.id)
                            merged_titles.append(other_task.title)
                            note_text = (other_task.notes or "").strip()
                            additional_notes.append(f"📌 [Mesclado da tarefa \"{other_task.title}\"]:\n{note_text}")
                            # Marca como CANCELLED/IGNORADA e anota referência
                            other_task.status = "CANCELLED"
                            other_task.notes = f"[Mesclada na tarefa {primary_task.id}]\n{other_task.notes or ''}"

                        # Consolida anotações na tarefa principal
                        existing_notes = (primary_task.notes or "").strip()
                        new_notes_section = "\n\n".join(additional_notes)
                        if existing_notes:
                            primary_task.notes = f"{existing_notes}\n\n{new_notes_section}"
                        else:
                            primary_task.notes = new_notes_section

                        # Herda a prioridade mais alta do cluster
                        p_weights = {"URGENT": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
                        best_p = max(cluster, key=lambda x: p_weights.get(x.priority or "MEDIUM", 2)).priority
                        if best_p:
                            primary_task.priority = best_p

                        total_merged_tasks += len(merged_ids)

                        spk_display = primary_task.message.speaker if primary_task.message and primary_task.message.speaker else speaker
                        merged_clusters.append(
                            TaskMergeCluster(
                                speaker=spk_display,
                                primary_task_id=primary_task.id,
                                primary_title=primary_task.title,
                                merged_task_ids=merged_ids,
                                merged_titles=merged_titles,
                                notes_consolidated_preview=primary_task.notes[:200] if primary_task.notes else None,
                            )
                        )

            db.commit()

            msg = (
                f"{len(merged_clusters)} grupo(s) de tarefas mesclados ({total_merged_tasks} tarefas unificadas com sucesso)."
                if merged_clusters
                else "Nenhuma tarefa semelhante encontrada para mesclagem."
            )

            resp = MergeTasksResponse(
                status="success",
                merged_groups_count=len(merged_clusters),
                tasks_merged_count=total_merged_tasks,
                clusters=merged_clusters,
                message=msg,
            )
            return resp.model_dump()
        finally:
            if should_close:
                db.close()

    def get_procrastination_radar_metrics(self, db: Session | None = None) -> dict:
        """Calcula métricas dos 6 vetores de procrastinação para o Radar Chart."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            from src.memory.models import ProcrastinationRadarMetrics
            all_tasks = db.query(TaskRecord).all()
            vault_tasks = [t for t in all_tasks if self.is_task_in_vault(t) and t.status != "DONE"]

            factors = {
                "SCOPE_CLARITY": 0,       # Falta de clareza de escopo
                "DEPENDENCY": 0,          # Dependência de terceiros / stakeholders
                "OVERLOAD_ANXIETY": 0,    # Sobrecarga cognitiva / ansiedade
                "PERFECTIONISM": 0,       # Perfeccionismo / complexidade
                "LOW_URGENCY": 0,         # Baixo senso de urgência (> 1 semana)
                "LACK_OF_RESOURCES": 0,   # Recursos insuficientes / alinhamento
            }

            now_dt = datetime.now(timezone.utc)
            total_delay_days = 0

            for t in vault_tasks:
                factor = t.procrastination_factor or "LOW_URGENCY"
                if factor not in factors:
                    factor = "LOW_URGENCY"
                factors[factor] += 1

                if t.postponed_until:
                    post_dt = t.postponed_until if t.postponed_until.tzinfo else t.postponed_until.replace(tzinfo=timezone.utc)
                    days = max(1, (post_dt - now_dt).days)
                    total_delay_days += days
                else:
                    total_delay_days += 7

            total_v = len(vault_tasks)
            avg_delay = round(total_delay_days / total_v, 1) if total_v > 0 else 0.0

            # Normalização de 0 a 100 para o gráfico radar
            dimensions = {}
            for k, count in factors.items():
                score = round((count / max(1, total_v)) * 100, 1) if total_v > 0 else 20.0
                dimensions[k] = min(100.0, max(15.0, score if total_v > 0 else 25.0))

            top_factors = sorted(
                [{"factor": k, "count": v, "pct": round((v / max(1, total_v)) * 100, 1) if total_v > 0 else 0} for k, v in factors.items()],
                key=lambda x: x["count"],
                reverse=True,
            )

            insights = []
            if top_factors and top_factors[0]["count"] > 0:
                lead = top_factors[0]["factor"]
                if lead == "DEPENDENCY":
                    insights.append("🤝 A principal causa de espera é a dependência de stakeholders. Agende cobranças objetivas.")
                elif lead == "SCOPE_CLARITY":
                    insights.append("🔍 Muitas tarefas estão travadas por falta de clareza. Quebre em subtarefas menores de 15 minutos.")
                elif lead == "OVERLOAD_ANXIETY":
                    insights.append("🧘 Há sobrecarga perceptível. Mantenha o fluxo diário com no máximo 3 tarefas prioritárias.")
                elif lead == "LOW_URGENCY":
                    insights.append("⏳ Prazos longos estão acumulando. Use lembretes programados para não esquecer.")
                elif lead == "PERFECTIONISM":
                    insights.append("✨ Entregue uma versão simples primeiro (MVP) para destravar o progresso.")
                elif lead == "LACK_OF_RESOURCES":
                    insights.append("📦 Alinhe recursos e decisões com a diretoria para desbloquear o fluxo.")
            else:
                insights.append("🌟 Baú equilibrado! Suas pendências de longo prazo estão organizadas e sem sobrecarga.")

            return ProcrastinationRadarMetrics(
                total_vault_tasks=total_v,
                avg_delay_days=avg_delay,
                dimensions=dimensions,
                top_factors=top_factors,
                insights=insights,
            ).model_dump()
        finally:
            if should_close:
                db.close()

    def get_garden_metamorphosis_metrics(self, db: Session | None = None) -> dict:
        """Calcula a jornada e métricas do Jardim de Realizações (Sonho ➔ Ação ➔ Resultado)."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            from src.memory.models import GardenMetamorphosisMetrics, GardenHarvestItem
            now_dt = datetime.now(timezone.utc)

            all_tasks = db.query(TaskRecord).all()
            ideas = [t for t in all_tasks if t.is_idea]
            total_seeds = len(ideas)

            in_germ_active = len([t for t in all_tasks if t.status == "PENDING" and not self.is_task_in_vault(t, now_dt)])
            in_germ_vault = len([t for t in all_tasks if self.is_task_in_vault(t, now_dt) and t.status != "DONE"])
            harvested_tasks = [t for t in all_tasks if t.status == "DONE"]
            total_harvested = len(harvested_tasks)

            total_creations = max(1, total_seeds + len(all_tasks))
            conversion_rate = round((total_harvested / total_creations) * 100, 1) if all_tasks else 0.0

            # Maturação média das tarefas concluídas
            maturation_days_list = []
            recent_harvests = []

            for t in sorted(harvested_tasks, key=lambda x: x.completed_at or x.created_at or now_dt, reverse=True)[:10]:
                c_at = t.created_at or now_dt
                d_at = t.completed_at or now_dt
                if c_at.tzinfo is None:
                    c_at = c_at.replace(tzinfo=timezone.utc)
                if d_at.tzinfo is None:
                    d_at = d_at.replace(tzinfo=timezone.utc)

                diff_days = max(1, (d_at - c_at).days)
                maturation_days_list.append(diff_days)

                spk = t.message.speaker if t.message and t.message.speaker else "user"
                recent_harvests.append(
                    GardenHarvestItem(
                        task_id=t.id,
                        title=t.title,
                        speaker=spk,
                        conceived_at=c_at.strftime("%d/%m/%Y"),
                        realized_at=d_at.strftime("%d/%m/%Y"),
                        maturation_days=diff_days,
                        is_idea=bool(t.is_idea),
                        is_epic=bool(t.is_epic),
                        stakeholder=t.stakeholder_link,
                        project=t.project_link,
                    )
                )

            avg_mat = round(sum(maturation_days_list) / len(maturation_days_list), 1) if maturation_days_list else 0.0

            # Agrupamento em Constelações de Ideias ativas
            constellations_map = defaultdict(list)
            for t in all_tasks:
                if t.is_idea and t.status != "DONE":
                    proj = t.project_link or "Ideias & Inovações Gerais"
                    constellations_map[proj].append(t.title)

            constellations_list = [
                {"theme": k, "ideas_count": len(v), "sample_ideas": v[:3]}
                for k, v in constellations_map.items()
            ]

            return GardenMetamorphosisMetrics(
                total_seeds=total_seeds,
                in_germination_active=in_germ_active,
                in_germination_vault=in_germ_vault,
                total_harvested=total_harvested,
                conversion_rate_pct=conversion_rate,
                avg_maturation_days=avg_mat,
                recent_harvests=recent_harvests,
                active_constellations=constellations_list,
            ).model_dump()
        finally:
            if should_close:
                db.close()

    def update_task(self, task_id: str, updates: TaskUpdate, db: Session | None = None) -> Any | None:
        """Atualiza dados, status, dimensões e anotações de uma tarefa."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            task = db.query(TaskRecord).filter(TaskRecord.id == task_id).first()
            if not task:
                return None

            if updates.title is not None:
                task.title = updates.title
            if updates.assignee is not None:
                task.assignee = updates.assignee
            if updates.due_date is not None:
                task.due_date = updates.due_date
            if updates.priority is not None:
                task.priority = updates.priority
            if updates.notes is not None:
                task.notes = updates.notes
            if updates.is_idea is not None:
                task.is_idea = updates.is_idea
            if updates.is_epic is not None:
                task.is_epic = updates.is_epic
            if updates.is_favorite is not None:
                task.is_favorite = updates.is_favorite
            if updates.in_vault is not None:
                task.in_vault = updates.in_vault
            if updates.postponed_until is not None:
                task.postponed_until = updates.postponed_until
            if updates.reminder_scheduled_at is not None:
                task.reminder_scheduled_at = updates.reminder_scheduled_at
            if updates.vault_reason is not None:
                task.vault_reason = updates.vault_reason
            if updates.procrastination_factor is not None:
                task.procrastination_factor = updates.procrastination_factor
            if updates.stakeholder_link is not None:
                task.stakeholder_link = updates.stakeholder_link
            if updates.project_link is not None:
                task.project_link = updates.project_link
            if updates.reassessment_notes is not None:
                task.reassessment_notes = updates.reassessment_notes
            if updates.status is not None:
                task.status = updates.status
                if updates.status == "DONE":
                    task.completed_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(task)
            return self.get_task_response(task, db)
        finally:
            if should_close:
                db.close()

    def _cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        """Calcula similaridade de cosseno entre dois vetores."""
        import math
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return max(0.0, min(1.0, dot / (norm_a * norm_b)))

    def get_stats(self, db: Session | None = None) -> MemoryStats:
        """Coleta métricas globais de uso da memória."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            total_messages = db.query(MessageRecord).count()
            total_tasks = db.query(TaskRecord).count()
            pending_tasks = db.query(TaskRecord).filter(TaskRecord.status == "PENDING").count()
            completed_tasks = db.query(TaskRecord).filter(TaskRecord.status == "DONE").count()
            total_entities = db.query(EntityRecord).count()
            graph_stats = knowledge_graph.stats()

            return MemoryStats(
                total_messages=total_messages,
                total_tasks=total_tasks,
                pending_tasks=pending_tasks,
                completed_tasks=completed_tasks,
                total_entities=total_entities,
                graph_nodes=graph_stats["nodes"],
                graph_edges=graph_stats["edges"],
            )
        finally:
            if should_close:
                db.close()


memory_repository = MemoryRepository()
