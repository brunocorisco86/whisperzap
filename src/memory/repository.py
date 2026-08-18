"""Repositório Unificado de Memória (Relacional, Vetorial e Grafo)."""

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional, List
from uuid import uuid4

from sqlalchemy.orm import Session
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

            # 3. Avaliação de Threshold de Peso/Influência para Sentimento
            from src.ai_gateway.bypass import should_analyze_sentiment
            analyze_sent, sent_reason, sent_weight = should_analyze_sentiment(
                speaker=data.speaker,
                meta_info=data.meta_info,
                db=db,
            )
            if not analyze_sent:
                logger.info(f"💡 [Sentimento] Análise emocional dispensada para '{data.speaker}' (peso={sent_weight:.2f} < {settings.SENTIMENT_WEIGHT_THRESHOLD}): motivo='{sent_reason}'")
                extracted.sentiment = "NEUTRAL"
                extracted.sentiment_score = 0.0

            # Importa dinamicamente contact_service para evitar circular import
            from src.contacts.service import contact_service

            weighted_message_urgency = contact_service.calculate_priority_for_message(
                sender_phone_or_name=data.speaker,
                raw_urgency=extracted.urgency,
                db=db,
            )

            # 2. Cria registro da mensagem
            message = MessageRecord(
                id=msg_id,
                created_at=datetime.now(timezone.utc),
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
                meta_info=data.meta_info or {},
            )
            db.add(message)

            # 3. Salva Tarefas extraídas SOMENTE se permitido para o remetente (Proprietário ou contato com toggle ativo)
            extracted_tasks_dicts = []
            allow_tasks_for_speaker = False

            if is_owner_interaction(data.speaker, data.meta_info):
                allow_tasks_for_speaker = True
            else:
                from src.contacts.models import ContactRecord
                speaker_val = (data.speaker or "").strip()
                phone_val = ""
                if isinstance(data.meta_info, dict):
                    phone_val = str(data.meta_info.get("phone") or data.meta_info.get("sender_phone") or data.meta_info.get("remoteJid") or "")
                if not phone_val:
                    phone_val = speaker_val

                import re
                digits = re.sub(r"\D", "", phone_val.split("@")[0]) if phone_val else ""

                contact_match = None
                if digits and len(digits) >= 8:
                    contact_match = db.query(ContactRecord).filter(
                        (ContactRecord.phone_number == digits)
                        | (ContactRecord.phone_number.like(f"%{digits[-8:]}%"))
                    ).first()
                if not contact_match and speaker_val:
                    contact_match = db.query(ContactRecord).filter(
                        (ContactRecord.name.ilike(speaker_val))
                        | (ContactRecord.nickname.ilike(speaker_val))
                    ).first()

                if contact_match and bool(getattr(contact_match, "can_generate_tasks", False)):
                    allow_tasks_for_speaker = True

            if allow_tasks_for_speaker:
                from src.memory.task_sentiment_analyzer import task_sentiment_analyzer
                source_msg_text = data.revised_text or data.raw_text or ""

                for t in extracted.tasks:
                    is_actionable = task_sentiment_analyzer.is_actionable_task(
                        title=t.title,
                        source_text=source_msg_text,
                    )
                    if not is_actionable:
                        logger.info(f"🚫 [Tarefas] Candidata a tarefa '{t.title}' descartada pelo filtro spaCy NLP anti-ruído.")
                        continue

                    task_id = str(uuid4())
                    weighted_task_priority = contact_service.calculate_priority_for_message(
                        sender_phone_or_name=data.speaker,
                        raw_urgency=t.priority,
                        db=db,
                    )
                    task_rec = TaskRecord(
                        id=task_id,
                        message_id=msg_id,
                        created_at=datetime.now(timezone.utc),
                        title=t.title,
                        assignee=t.assignee,
                        due_date=t.due_date,
                        priority=weighted_task_priority,
                        status="PENDING",
                    )
                    db.add(task_rec)
                    t_dict = t.model_dump()
                    t_dict["priority"] = weighted_task_priority
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
            from src.ai_gateway.schemas import MemorySourceCitation
            import re
            from sqlalchemy import or_

            # Extrai tokens limpos sem pontuação
            query_tokens = [w for w in re.findall(r"\w+", query.lower()) if len(w) >= 3]
            is_today = any(t in ("hoje", "atual", "recente") for t in query_tokens)

            # Checagem de Cache Semântico Local (Zero Tokens)
            from src.memory.semantic_cache import semantic_cache
            from src.ai_gateway.schemas import HermesQueryResponse
            cached_res = semantic_cache.get(query)
            if cached_res:
                return HermesQueryResponse(**cached_res)

            # 1. Busca Semântica Vetorial
            search_results = await self.search_memories(
                query=query,
                top_k=top_k,
                min_similarity=min_similarity,
                db=db,
            )

            seen_ids = set()
            sources: list[MemorySourceCitation] = []

            from src.memory.timezone_utils import format_brt

            for sr in search_results:
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

            # 2. Busca Híbrida Direta por Remetente / Pessoa Mencionada na Query
            for tok in query_tokens:
                if tok in ("que", "para", "com", "como", "onde", "qual", "quais", "quem", "hoje", "ontem", "queria", "disse", "pediu", "falou"):
                    continue

                # Busca mensagens enviadas ou que citam o nome da pessoa
                person_messages = (
                    db.query(MessageRecord)
                    .filter(
                        or_(
                            MessageRecord.speaker.ilike(f"%{tok}%"),
                            MessageRecord.revised_text.ilike(f"%{tok}%"),
                            MessageRecord.raw_text.ilike(f"%{tok}%"),
                            MessageRecord.summary.ilike(f"%{tok}%"),
                        )
                    )
                    .order_by(MessageRecord.created_at.desc())
                    .limit(10)
                    .all()
                )

                for pm in person_messages:
                    if pm.id not in seen_ids:
                        seen_ids.add(pm.id)
                        snippet = pm.revised_text or pm.raw_text or pm.summary or ""
                        if len(snippet) > 200:
                            snippet = snippet[:197] + "..."
                        sources.append(
                            MemorySourceCitation(
                                message_id=pm.id,
                                speaker=pm.speaker or "Desconhecido",
                                text_snippet=snippet,
                                similarity=0.95 if (pm.speaker and tok in pm.speaker.lower()) else 0.85,
                                created_at=format_brt(pm.created_at) if pm.created_at else None,
                            )
                        )

            # Se pediu informações de "hoje", ordena priorizando mensagens recentes/do dia
            if is_today:
                sources.sort(key=lambda s: s.created_at or "", reverse=True)

            # 3. GraphRAG Híbrido: Extração de entidades com spaCy e Expansão Topológica de 2 Saltos
            related_entities = []
            if include_graph:
                from src.memory.hybrid_graph_rag import hybrid_graph_rag

                # 3.1 Extrai entidades da query e expande subgrafo de 2 graus no NetworkX
                seed_entities = hybrid_graph_rag.extract_query_entities(query)
                # Inclui também tokens brutos caso o spaCy não tenha pego
                seed_entities.extend([t for t in query_tokens if len(t) > 3])
                
                subgraph_data = hybrid_graph_rag.expand_subgraph_2_hop(seed_entities, max_hops=2)
                related_entities.extend(subgraph_data.get("node_details", []))
                related_entities.extend(subgraph_data.get("triples", []))

                # 3.2 Busca cruzada na tabela SQL de Contatos
                from src.contacts.models import ContactRecord
                sql_contacts = db.query(ContactRecord).all()
                for c in sql_contacts:
                    c_matches = (
                        any(t in c.name.lower() for t in query_tokens)
                        or (c.nickname and any(t in c.nickname.lower() for t in query_tokens))
                        or (c.notes and any(t in c.notes.lower() for t in query_tokens))
                        or (c.company and any(t in c.company.lower() for t in query_tokens))
                    )
                    if c_matches:
                        c_parts = [f"Contato Oficial: {c.name}"]
                        if c.role:
                            c_parts.append(f"Cargo/Role: {c.role}")
                        if c.phone_number:
                            c_parts.append(f"Telefone: {c.phone_number}")
                        if c.company:
                            c_parts.append(f"Empresa: {c.company}")
                        if c.notes:
                            c_parts.append(f"Detalhes: {c.notes}")
                        related_entities.append(" | ".join(c_parts))

            # 4. Busca de tarefas pendentes relacionadas (por Solicitante, Responsável ou Título)
            pending_tasks_objs = self.list_tasks(status="PENDING", db=db)
            related_tasks = []
            for t in pending_tasks_objs:
                t_tokens = [w.lower() for w in t.title.split() if len(w) > 3]
                spk = (t.speaker or "").lower()
                asg = (t.assignee or "").lower()

                matches_task = (
                    any(tok in query.lower() for tok in t_tokens)
                    or any(tok in spk for tok in query_tokens)
                    or any(tok in asg for tok in query_tokens)
                    or (t.message_id in seen_ids)
                )

                if matches_task:
                    speaker_info = f"[Solicitante: {t.speaker}] " if t.speaker else ""
                    assignee = f" (Resp: {t.assignee})" if t.assignee else ""
                    due = f" [Prazo: {t.due_date}]" if t.due_date else ""
                    notes = f" (Notas: {t.notes})" if t.notes else ""
                    related_tasks.append(f"{speaker_info}{t.title}{assignee}{due}{notes} [Prioridade: {t.priority}]")

            # 5. Fusão e Re-ranqueamento com Boost de Subgrafo
            if include_graph:
                from src.memory.hybrid_graph_rag import hybrid_graph_rag
                fused = hybrid_graph_rag.fuse_vector_and_graph_results(
                    vector_sources=sources,
                    subgraph_data=subgraph_data,
                    pending_tasks=related_tasks,
                )
                final_sources = fused["sources"]
            else:
                final_sources = sources

            # 6. Chama o Agente Hermes para inferência e resposta estrita
            result = await hermes_agent_service.answer_hermes_query(
                query=query,
                sources=final_sources[:12],  # Limite confortável de fontes relevantes
                related_entities=list(set(related_entities)),
                pending_tasks=related_tasks,
            )
            # Armazena no cache semântico para consultas subsequentes (0 tokens)
            semantic_cache.set(query, result.model_dump())
            return result
        finally:
            if should_close:
                db.close()

    def list_tasks(
        self,
        status: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        db: Session | None = None,
    ) -> list[Any]:
        """Lista tarefas filtradas por status, prioridade ou responsável com ancoragem do solicitante."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            from src.contacts.models import ContactRecord
            from src.memory.models import TaskResponse

            contacts_map = {c.name.lower(): c for c in db.query(ContactRecord).all()}

            query = db.query(TaskRecord)
            if status:
                query = query.filter(TaskRecord.status == status.upper())
            if priority:
                query = query.filter(TaskRecord.priority == priority.upper())
            if assignee:
                query = query.filter(TaskRecord.assignee.ilike(f"%{assignee}%"))

            records = query.order_by(TaskRecord.created_at.desc()).all()
            responses = []
            for r in records:
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
                        speaker=speaker_name,
                        sender_phone=sender_phone,
                        sender_role=sender_role,
                        message_time=msg.created_at.strftime("%d/%m/%Y %H:%M") if msg and msg.created_at else None,
                        audio_duration_s=msg.audio_duration_s if msg else None,
                        revised_text=msg.revised_text if msg else None,
                        raw_text=msg.raw_text if msg else None,
                        message_summary=msg_summary,
                        source_text_snippet=source_snippet,
                    )
                )
            return responses
        finally:
            if should_close:
                db.close()

    def update_task(self, task_id: str, updates: TaskUpdate, db: Session | None = None) -> Any | None:
        """Atualiza dados, status e anotações de uma tarefa."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            from src.contacts.models import ContactRecord
            from src.memory.models import TaskResponse

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
            if updates.status is not None:
                task.status = updates.status
                if updates.status == "DONE":
                    task.completed_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(task)

            msg = task.message
            speaker_name = msg.speaker if msg else "user"
            contact_match = db.query(ContactRecord).filter(ContactRecord.name.ilike(speaker_name)).first() if speaker_name else None

            sender_phone = ""
            if contact_match and contact_match.phone_number:
                sender_phone = contact_match.phone_number
            elif msg and isinstance(msg.meta_info, dict) and msg.meta_info.get("remoteJid"):
                sender_phone = msg.meta_info.get("remoteJid", "").split("@")[0]

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
                speaker=speaker_name,
                sender_phone=sender_phone,
                sender_role=contact_match.role if contact_match else None,
                message_summary=msg.summary if msg else None,
                source_text_snippet=msg.revised_text[:140] if msg else None,
            )
        finally:
            if should_close:
                db.close()

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
