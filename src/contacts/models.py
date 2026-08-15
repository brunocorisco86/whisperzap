"""Modelo de Banco de Dados para Contatos e Papéis."""

from datetime import datetime, timezone
from sqlalchemy import JSON, Column, DateTime, Float, String, Text
from src.memory.models import Base


def utc_now():
    return datetime.now(timezone.utc)


class ContactRecord(Base):
    """Tabela de contatos, papéis hierárquicos e vínculos organizacionais."""

    __tablename__ = "contacts"

    id = Column(String(36), primary_key=True)
    phone_number = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    nickname = Column(String(100), nullable=True)
    role = Column(String(50), default="UNKNOWN", index=True)
    company = Column(String(150), nullable=True, index=True)
    projects_json = Column(JSON, default=list)  # Lista de strings com projetos vinculados
    avatar_url = Column(String(500), nullable=True)  # URL da foto de perfil do WhatsApp
    custom_weight = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
