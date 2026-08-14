"""Repositório Unificado de Memória (Relacional, Vetorial e Grafo)."""

import json
import logging
import math
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session
from src.ai_gateway.extractor import semantic_extractor
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
            extracted = await semantic_extractor.extract(extraction_req)

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
                urgency=extracted.urgency,
                meta_info=data.meta_info or {},
            )
            db.add(message)

            # 3. Salva Tarefas extraídas
            extracted_tasks_dicts = []
            for t in extracted.tasks:
                task_id = str(uuid4())
                task_rec = TaskRecord(
                    id=task_id,
                    message_id=msg_id,
                    created_at=datetime.now(timezone.utc),
                    title=t.title,
                    assignee=t.assignee,
                    due_date=t.due_date,
                    priority=t.priority,
                    status="PENDING",
                )
                db.add(task_rec)
                extracted_tasks_dicts.append(t.model_dump())

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

            # 6. Atualiza o Grafo Relacional de Conhecimento
            knowledge_graph.add_interaction(
                speaker=data.speaker,
                entities=extracted_entities_dicts,
                tasks=extracted_tasks_dicts,
                intent=extracted.intent,
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

    def list_tasks(
        self,
        status: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        db: Session | None = None,
    ) -> list[TaskRecord]:
        """Lista tarefas filtradas por status, prioridade ou responsável."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            query = db.query(TaskRecord)
            if status:
                query = query.filter(TaskRecord.status == status.upper())
            if priority:
                query = query.filter(TaskRecord.priority == priority.upper())
            if assignee:
                query = query.filter(TaskRecord.assignee.ilike(f"%{assignee}%"))

            return query.order_by(TaskRecord.created_at.desc()).all()
        finally:
            if should_close:
                db.close()

    def update_task(self, task_id: str, updates: TaskUpdate, db: Session | None = None) -> TaskRecord | None:
        """Atualiza dados e status de uma tarefa."""
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
            if updates.status is not None:
                task.status = updates.status
                if updates.status == "DONE":
                    task.completed_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(task)
            return task
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
