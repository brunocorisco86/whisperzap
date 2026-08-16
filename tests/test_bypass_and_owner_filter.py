"""Testes unitários para Bypass de IA, Filtro de Grupos e Exclusão do Proprietário do Dashboard."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from src.ai_gateway.bypass import (
    is_group_message,
    is_owner_interaction,
    normalize_text,
    should_bypass_ai,
)
from src.analytics.service import analytics_service
from src.config import settings
from src.memory.database import SessionLocal, init_db
from src.memory.models import MessageCreate, MessageRecord
from src.memory.repository import memory_repository
from src.memory.sentiment_timeline import sentiment_timeline_service


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_normalize_text():
    assert normalize_text("Bom dia!!") == "bom dia"
    assert normalize_text("  Olá,   tudo bem?  ") == "ola tudo bem"
    assert normalize_text("123-ABC") == "123 abc"
    assert normalize_text("") == ""


def test_is_group_message():
    assert is_group_message({"remoteJid": "12036302482910@g.us"}) is True
    assert is_group_message({"remoteJid": "status@broadcast"}) is True
    assert is_group_message({"isGroup": True}) is True
    assert is_group_message({"participant": "5544999990001@s.whatsapp.net"}) is True

    # Mensagem privada legítima
    assert is_group_message({"remoteJid": "5544999990001@s.whatsapp.net"}) is False
    assert is_group_message({}) is False
    assert is_group_message(None) is False


def test_is_owner_interaction():
    # Identificação por telefone
    assert is_owner_interaction(speaker="554497604925") is True
    assert is_owner_interaction(meta_info={"remoteJid": "554497604925@s.whatsapp.net"}) is True
    assert is_owner_interaction(meta_info={"fromMe": True}) is True

    # Identificação por nome / alias
    assert is_owner_interaction(speaker="Bruno") is True
    assert is_owner_interaction(speaker="user") is True
    assert is_owner_interaction(meta_info={"pushName": "Bruno"}) is True

    # Interlocutor externo
    assert is_owner_interaction(speaker="Carlos Gestor") is False
    assert is_owner_interaction(speaker="5544999990001") is False
    assert is_owner_interaction(meta_info={"remoteJid": "5544999990001@s.whatsapp.net", "fromMe": False}) is False


def test_should_bypass_ai():
    # Mensagens curtas (<= 15 caracteres)
    bypass, reason = should_bypass_ai("oi")
    assert bypass is True

    bypass, reason = should_bypass_ai("bom dia")
    assert bypass is True

    bypass, reason = should_bypass_ai("meu nome")
    assert bypass is True

    bypass, reason = should_bypass_ai("ok beleza")
    assert bypass is True

    # Mensagens sem texto / emojis
    bypass, reason = should_bypass_ai("👍 🙏")
    assert bypass is True

    bypass, reason = should_bypass_ai("", message_type="stickerMessage")
    assert bypass is True

    bypass, reason = should_bypass_ai("", message_type="reactionMessage")
    assert bypass is True

    # Grupo com flag de ignorar ativo
    bypass, reason = should_bypass_ai("Texto longo para teste com mais de quinze caracteres", meta_info={"remoteJid": "12036302482910@g.us"})
    assert bypass is True
    assert reason == "group_message"

    # Bypass explícito no payload
    bypass, reason = should_bypass_ai("Texto longo com mais de 20 caracteres sem grupo", meta_info={"bypass_ai": True})
    assert bypass is True
    assert reason == "explicit_bypass"

    # Mensagem informativa longa real (NÃO deve fazer bypass)
    bypass, reason = should_bypass_ai("Precisamos revisar o lote 45 e a calibração dos sensores de silo da C.Vale com urgência.")
    assert bypass is False
    assert reason == "process_ai"


@pytest.mark.asyncio
async def test_save_message_with_ai_bypass():
    db = SessionLocal()
    try:
        # Envia saudação curta
        msg_data = MessageCreate(
            speaker="João Silva",
            raw_text="bom dia",
            revised_text="bom dia",
            meta_info={"source": "whatsapp", "message_type": "text"},
        )
        saved = await memory_repository.save_message(msg_data, db=db)
        assert saved.id is not None
        assert saved.intent == "NOTE"
        assert saved.sentiment == "NEUTRAL"
        assert saved.sentiment_score == 0.0
    finally:
        db.close()


def test_analytics_excludes_owner_interactions():
    db = SessionLocal()
    try:
        # Cria mensagens do dono (Bruno) e de interlocutor externo (Carlos)
        msg_owner = MessageRecord(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            speaker="Bruno",
            raw_text="Mensagem enviada pelo dono do sistema com mais de 15 caracteres.",
            revised_text="Mensagem enviada pelo dono do sistema com mais de 15 caracteres.",
            intent="NOTE",
            sentiment="POSITIVE",
            sentiment_score=0.5,
            meta_info={"fromMe": True, "remoteJid": "554497604925@s.whatsapp.net"},
        )
        msg_external = MessageRecord(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            speaker="Carlos Diretor",
            raw_text="Relatório de entrega de ração e níveis de silo pronto para envio.",
            revised_text="Relatório de entrega de ração e níveis de silo pronto para envio.",
            intent="DECISION",
            sentiment="POSITIVE",
            sentiment_score=0.8,
            meta_info={"fromMe": False, "remoteJid": "5544988880000@s.whatsapp.net"},
        )
        db.add(msg_owner)
        db.add(msg_external)
        db.commit()

        metrics = analytics_service.get_dashboard_metrics(period="today", db=db)

        # O dashboard não deve contabilizar a mensagem do Bruno nas pessoas em contato ou total
        # Bruno não deve constar na lista de Top Interlocutores
        top_speakers = [s.speaker for s in metrics.top_senders]
        assert "Bruno" not in top_speakers
        assert "user" not in top_speakers
        assert "Carlos Diretor" in top_speakers
    finally:
        db.close()


def test_sentiment_timeline_excludes_owner():
    db = SessionLocal()
    try:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        msg_owner = MessageRecord(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            speaker="Bruno",
            raw_text="Minha própria mensagem",
            revised_text="Minha própria mensagem",
            intent="NOTE",
            sentiment="POSITIVE",
            sentiment_score=0.5,
            meta_info={"fromMe": True},
        )
        msg_contact = MessageRecord(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            speaker="Lucas Gerente",
            raw_text="Relatório operacional recebido com sucesso.",
            revised_text="Relatório operacional recebido com sucesso.",
            intent="NOTE",
            sentiment="POSITIVE",
            sentiment_score=0.7,
            meta_info={"fromMe": False},
        )
        db.add(msg_owner)
        db.add(msg_contact)
        db.commit()

        collection = sentiment_timeline_service.collect_daily_sentiments(target_date=today_str, db=db)
        snapshot_speakers = [s.speaker for s in collection.snapshots]

        assert "Bruno" not in snapshot_speakers
        assert "user" not in snapshot_speakers
        assert "Lucas Gerente" in snapshot_speakers
    finally:
        db.close()
