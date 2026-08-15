"""Modelos de Banco de Dados e Schemas para a Memória Hermes."""

from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now():
    return datetime.now(timezone.utc)


class MessageRecord(Base):
    """Tabela de registro histórico de mensagens e transcrições."""

    __tablename__ = "messages"

    id = Column(String(36), primary_key=True)
    created_at = Column(DateTime, default=utc_now, index=True)
    speaker = Column(String(100), default="user", index=True)
    raw_text = Column(Text, nullable=True)
    revised_text = Column(Text, nullable=False)
    audio_duration_s = Column(Float, nullable=True)
    audio_filename = Column(String(255), nullable=True)
    intent = Column(String(50), default="NOTE", index=True)
    summary = Column(Text, nullable=True)
    sentiment = Column(String(32), default="NEUTRAL", index=True)
    sentiment_score = Column(Float, default=0.0)
    urgency = Column(String(20), default="MEDIUM")
    meta_info = Column(JSON, default=dict)

    # Relacionamentos
    tasks = relationship("TaskRecord", back_populates="message", cascade="all, delete-orphan")
    entities = relationship("EntityRecord", back_populates="message", cascade="all, delete-orphan")
    embeddings = relationship("EmbeddingRecord", back_populates="message", cascade="all, delete-orphan")


class TaskRecord(Base):
    """Tabela de tarefas extraídas e gerenciadas."""

    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True)
    message_id = Column(String(36), ForeignKey("messages.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=utc_now, index=True)
    title = Column(String(255), nullable=False)
    assignee = Column(String(100), nullable=True, index=True)
    due_date = Column(String(100), nullable=True)
    priority = Column(String(20), default="MEDIUM", index=True)
    status = Column(String(20), default="PENDING", index=True)  # PENDING, IN_PROGRESS, DONE, CANCELLED
    completed_at = Column(DateTime, nullable=True)

    message = relationship("MessageRecord", back_populates="tasks")


class EntityRecord(Base):
    """Tabela de entidades nomeadas persistidas."""

    __tablename__ = "entities"

    id = Column(String(36), primary_key=True)
    message_id = Column(String(36), ForeignKey("messages.id"), nullable=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    category = Column(String(50), default="OTHER", index=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    message = relationship("MessageRecord", back_populates="entities")


class EmbeddingRecord(Base):
    """Tabela de embeddings para busca semântica."""

    __tablename__ = "embeddings"

    id = Column(String(36), primary_key=True)
    message_id = Column(String(36), ForeignKey("messages.id"), nullable=False, index=True)
    text_content = Column(Text, nullable=False)
    embedding_json = Column(JSON, nullable=False)  # Armazenado como JSON float list para compatibilidade SQLite/Postgres
    created_at = Column(DateTime, default=utc_now)


    message = relationship("MessageRecord", back_populates="embeddings")


# ===================== Schemas Pydantic da API =====================


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    message_id: Optional[str] = None
    title: str
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    priority: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None



class TaskUpdate(BaseModel):
    title: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[Literal["LOW", "MEDIUM", "HIGH", "URGENT"]] = None
    status: Optional[Literal["PENDING", "IN_PROGRESS", "DONE", "CANCELLED"]] = None


class MessageCreate(BaseModel):
    speaker: str = "user"
    raw_text: Optional[str] = None
    revised_text: str
    audio_duration_s: Optional[float] = None
    audio_filename: Optional[str] = None
    meta_info: Optional[dict] = None


class SearchQuery(BaseModel):
    query: str = Field(..., description="Texto ou pergunta para busca semântica")
    top_k: int = Field(default=5, ge=1, le=50, description="Quantidade máxima de resultados")
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Similaridade mínima de cosseno")


class SearchResult(BaseModel):
    message_id: str
    text: str
    speaker: str
    intent: str
    summary: Optional[str] = None
    similarity: float
    created_at: datetime


class MemoryStats(BaseModel):
    total_messages: int
    total_tasks: int
    pending_tasks: int
    completed_tasks: int
    total_entities: int
    graph_nodes: int
    graph_edges: int
