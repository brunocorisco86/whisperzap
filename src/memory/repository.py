"""Repositório Unificado de Memória (Relacional, Vetorial e Grafo)."""

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional, List
from uuid import uuid4

from sqlalchemy.orm import Session
from src.ai_gateway.extractor import semantic_extractor
from src.ai_gateway.providers import get_ai_provider
from src.ai_gateway.schemas import SemanticExtractionRequest
from src.config import settings
from src.contacts.service import contact_service, generate_contact_id
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

    async def save_message(self, data: MessageCreate, db: Session | None = None) -> MessageRecord:
        """Salva a mensagem, executa extração semântica silenciosa, salva entidades/tarefas, embedding e atualiza o grafo."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            msg_id = str(uuid4())

            # 1. Extração Semântica estruturada
            extraction_req = SemanticExtractionRequest(
                text=data.revised_text,
                speaker=data.speaker,
                context=str(data.meta_info) if data.meta_info else None,
                include_dictionary=True,
            )
            try:
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

            # 3. Salva Tarefas extraídas com prioridade ponderada
            extracted_tasks_dicts = []
            for t in extracted.tasks:
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

            # 6. Auto-criação / Sincronização de Contatos no Banco SQL e Grafo
            try:
                from src.contacts.models import ContactRecord
                import re

                # 6.1 Processa o Speaker da mensagem
                speaker_val = (data.speaker or "").strip()
                if speaker_val:
                    meta = data.meta_info if isinstance(data.meta_info, dict) else {}
                    raw_phone = meta.get("remoteJid", "") or meta.get("phone", "") or speaker_val
                    digits = re.sub(r"\D", "", str(raw_phone).split("@")[0])
                    push_name = meta.get("pushName")

                    existing_contact = None
                    if digits and len(digits) >= 8:
                        existing_contact = db.query(ContactRecord).filter(
                            (ContactRecord.phone_number == digits) | (ContactRecord.phone_number.like(f"%{digits[-8:]}%"))
                        ).first()

                    if not existing_contact:
                        existing_contact = db.query(ContactRecord).filter(
                            ContactRecord.name.ilike(speaker_val)
                        ).first()

                    if not existing_contact:
                        contact_name = push_name if (push_name and speaker_val.isdigit()) else speaker_val
                        c_id = generate_contact_id(contact_name, digits)
                        new_contact = ContactRecord(
                            id=c_id,
                            name=contact_name,
                            phone_number=digits if len(digits) >= 8 else "",
                            role="UNKNOWN",
                            company="",
                            projects_json=[],
                            notes="Contato identificado automaticamente via mensagem recebida.",
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
                        )
                        db.add(new_contact)
                        db.commit()
                        contact_service._sync_contact_to_graph(new_contact)
                    elif push_name and existing_contact.name.isdigit():
                        existing_contact.name = push_name
                        db.commit()
                        contact_service._sync_contact_to_graph(existing_contact)

                # 6.2 Processa Entidades do tipo PERSON extraídas da mensagem
                for e in extracted.entities:
                    if e.category and e.category.upper() == "PERSON" and e.name:
                        person_name = e.name.strip()
                        if len(person_name) > 1:
                            existing_person = db.query(ContactRecord).filter(
                                ContactRecord.name.ilike(person_name)
                            ).first()
                            if not existing_person:
                                p_id = generate_contact_id(person_name, "")
                                new_person = ContactRecord(
                                    id=p_id,
                                    name=person_name,
                                    phone_number="",
                                    role="UNKNOWN",
                                    company="",
                                    projects_json=[],
                                    notes=e.details or "Pessoa mencionada em mensagens de áudio/texto.",
                                    created_at=datetime.now(timezone.utc),
                                    updated_at=datetime.now(timezone.utc),
                                )
                                db.add(new_person)
                                db.commit()
                                contact_service._sync_contact_to_graph(new_person)

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

            # 1. Busca Semântica Vetorial
            search_results = await self.search_memories(
                query=query,
                top_k=top_k,
                min_similarity=min_similarity,
                db=db,
            )

            sources: list[MemorySourceCitation] = [
                MemorySourceCitation(
                    message_id=sr.message_id,
                    speaker=sr.speaker,
                    text_snippet=sr.summary or sr.text[:140],
                    similarity=sr.similarity,
                    created_at=sr.created_at.strftime("%Y-%m-%d %H:%M") if sr.created_at else None,
                )
                for sr in search_results
            ]

            # 2. Extração de conexões e metadados no Grafo de Conhecimento e Contatos
            related_entities = []
            if include_graph:
                import re

                # Extrai tokens limpos sem pontuação
                query_tokens = [w for w in re.findall(r"\w+", query.lower()) if len(w) >= 3]

                # Se a pergunta for em 1ª pessoa ("minha", "meu", "eu", "esposa", "família"), expande o nó do usuário (Bruno)
                is_first_person = any(t in ("minha", "meu", "eu", "esposa", "marido", "familia", "família", "minhas", "meus") for t in query_tokens)
                if is_first_person and "bruno" not in query_tokens:
                    query_tokens.extend(["bruno", "user"])

                # Mapeamento de sinônimos de papéis
                role_filter = set()
                if any(t in ("esposa", "marido", "conjuge", "cônjuge", "familia", "família", "filho", "filha", "mãe", "pai") for t in query_tokens):
                    role_filter.add("FAMILY_CORE")
                if any(t in ("produtor", "associado", "cooperado", "integrado", "granjeiro", "avicultor") for t in query_tokens):
                    role_filter.add("PRODUCER_COOPERATED")
                if any(t in ("diretor", "gestor", "chefe", "gerente", "lider", "líder", "executivo") for t in query_tokens):
                    role_filter.add("EXECUTIVE")
                if any(t in ("consultor", "consultoria", "stakeholder", "especialista") for t in query_tokens):
                    role_filter.add("STAKEHOLDER")

                all_nodes = knowledge_graph.list_nodes()
                for node in all_nodes:
                    node_name = node.get("name", "")
                    node_details = str(node.get("details", "")).lower()
                    node_role = str(node.get("role", "")).upper()
                    node_phone = str(node.get("phone", "")).lower()

                    matches = (
                        any(t in node_name.lower() for t in query_tokens)
                        or any(t in node_details for t in query_tokens)
                        or any(t in node_role.lower() for t in query_tokens)
                        or any(t in node_phone for t in query_tokens)
                        or (node_role in role_filter)
                    )

                    if matches:
                        # Adiciona metadados estruturados do próprio nó
                        node_parts = [f"Entidade: {node_name}"]
                        if node.get("role"):
                            node_parts.append(f"Cargo/Role: {node.get('role')}")
                        if node.get("phone"):
                            node_parts.append(f"Telefone: {node.get('phone')}")
                        if node.get("company"):
                            node_parts.append(f"Empresa: {node.get('company')}")
                        if node.get("details"):
                            node_parts.append(f"Detalhes: {node.get('details')}")
                        related_entities.append(" | ".join(node_parts))

                        neighborhood = knowledge_graph.get_neighborhood(node_name, depth=1)
                        if neighborhood.get("found"):
                            for n_node in neighborhood.get("nodes", []):
                                n_id = n_node.get("id")
                                if n_id and n_id != node_name and (n_node.get("phone") or n_node.get("role") or n_node.get("details")):
                                    parts = [f"Contato Vinculado: {n_id}"]
                                    if n_node.get("role"):
                                        parts.append(f"Role: {n_node.get('role')}")
                                    if n_node.get("phone"):
                                        parts.append(f"Telefone: {n_node.get('phone')}")
                                    if n_node.get("company"):
                                        parts.append(f"Empresa: {n_node.get('company')}")
                                    if n_node.get("details"):
                                        parts.append(f"Detalhes: {n_node.get('details')}")
                                    related_entities.append(" | ".join(parts))

                            conn_strs = [
                                f"{edge.get('source')} -[{edge.get('relation')}]-> {edge.get('target')}"
                                for edge in neighborhood.get("edges", [])
                            ]
                            related_entities.extend(conn_strs)

                # Busca cruzada na tabela SQL de Contatos
                from src.contacts.models import ContactRecord
                sql_contacts = db.query(ContactRecord).all()
                for c in sql_contacts:
                    c_role = (c.role or "").upper()
                    c_matches = (
                        any(t in c.name.lower() for t in query_tokens)
                        or (c.nickname and any(t in c.nickname.lower() for t in query_tokens))
                        or (c.notes and any(t in c.notes.lower() for t in query_tokens))
                        or (c.company and any(t in c.company.lower() for t in query_tokens))
                        or (c_role in role_filter)
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

            # 3. Busca de tarefas pendentes relacionadas
            pending_tasks_objs = self.list_tasks(status="PENDING", db=db)
            related_tasks = []
            for t in pending_tasks_objs:
                t_tokens = [w.lower() for w in t.title.split() if len(w) > 3]
                if any(tok in query.lower() for tok in t_tokens) or (t.assignee and t.assignee.lower() in query.lower()):
                    assignee = f" (Resp: {t.assignee})" if t.assignee else ""
                    due = f" [Prazo: {t.due_date}]" if t.due_date else ""
                    related_tasks.append(f"{t.title}{assignee}{due} [Prioridade: {t.priority}]")

            # 4. Chama o Agente Hermes para inferência e resposta estrita
            return await hermes_agent_service.answer_hermes_query(
                query=query,
                sources=sources,
                related_entities=list(set(related_entities)),
                pending_tasks=related_tasks,
            )
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
                        created_at=r.created_at,
                        completed_at=r.completed_at,
                        speaker=speaker_name,
                        sender_phone=sender_phone,
                        sender_role=sender_role,
                        message_summary=msg_summary,
                        source_text_snippet=source_snippet,
                    )
                )
            return responses
        finally:
            if should_close:
                db.close()

    def update_task(self, task_id: str, updates: TaskUpdate, db: Session | None = None) -> Any | None:
        """Atualiza dados e status de uma tarefa."""
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
