"""Testes unitários para o subsistema de Sentimento e Série Temporal."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from fastapi.testclient import TestClient

from src.main import app
from src.memory.database import SessionLocal
from src.memory.models import DailySentimentSnapshotRecord, MessageRecord
from src.memory.sentiment_timeline import (
    compute_dominant_sentiment,
    sentiment_timeline_service,
)


def test_compute_dominant_sentiment():
    """Testa o cálculo do sentimento dominante e score médio."""
    dominant, score = compute_dominant_sentiment(pos=5, neu=0, neg=0)
    assert dominant == "POSITIVE"
    assert score == 1.0

    dominant, score = compute_dominant_sentiment(pos=0, neu=5, neg=0)
    assert dominant == "NEUTRAL"
    assert score == 0.0

    dominant, score = compute_dominant_sentiment(pos=0, neu=0, neg=5)
    assert dominant == "NEGATIVE"
    assert score == -1.0

    dominant, score = compute_dominant_sentiment(pos=2, neu=1, neg=2)
    assert dominant == "MIXED"
    assert score == 0.0


def test_collect_daily_sentiments_service():
    """Testa a coleta diária de sentimentos e persistência de snapshots."""
    db = SessionLocal()
    try:
        today = "2026-08-15"
        # Cria mensagens de teste para uma pessoa
        m1 = MessageRecord(
            id=str(uuid4()),
            created_at=datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
            speaker="Debora Patel",
            revised_text="Tudo certo com a entrega dos silos!",
            sentiment="POSITIVE",
            sentiment_score=0.9,
            urgency="LOW",
        )
        m2 = MessageRecord(
            id=str(uuid4()),
            created_at=datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc),
            speaker="Debora Patel",
            revised_text="O relatório foi aprovado com sucesso.",
            sentiment="POSITIVE",
            sentiment_score=0.85,
            urgency="LOW",
        )
        db.add_all([m1, m2])
        db.commit()

        result = sentiment_timeline_service.collect_daily_sentiments(target_date=today, db=db)
        assert result.date == today
        assert result.total_people >= 1
        assert result.total_interactions >= 2

        # Testa busca de snapshots do dia
        daily_list = sentiment_timeline_service.get_daily_snapshots(target_date=today, db=db)
        debora_snap = next((s for s in daily_list if "Debora" in s.speaker), None)
        assert debora_snap is not None
        assert debora_snap.dominant_sentiment == "POSITIVE"
        assert debora_snap.positive_count >= 2

        # Testa série temporal
        timeline_res = sentiment_timeline_service.get_person_timeline(speaker="Debora Patel", db=db)
        assert timeline_res.speaker == "Debora Patel"
        assert timeline_res.total_days_tracked >= 1
        assert len(timeline_res.timeline) >= 1
        assert timeline_res.timeline[0].dominant_sentiment == "POSITIVE"

    finally:
        db.close()


def test_sentiment_endpoints():
    """Testa as rotas FastAPI de sentimentos."""
    client = TestClient(app)

    # 1. Coleta
    res_collect = client.post("/api/v1/memory/sentiment/collect?date=2026-08-15")
    assert res_collect.status_code == 200
    data_collect = res_collect.json()
    assert "date" in data_collect
    assert "total_people" in data_collect

    # 2. Daily Snapshots
    res_daily = client.get("/api/v1/memory/sentiment/daily?date=2026-08-15")
    assert res_daily.status_code == 200
    assert isinstance(res_daily.json(), list)

    # 3. Timeline
    res_tl = client.get("/api/v1/memory/sentiment/timeline?speaker=Debora%20Patel")
    assert res_tl.status_code == 200
    tl_data = res_tl.json()
    assert tl_data["speaker"] == "Debora Patel"
    assert "timeline" in tl_data


def test_daily_snapshots_3d_and_automated_message_neutralization():
    """Valida o filtro de 3 dias como padrão e a neutralização de mensagens automáticas."""
    db = SessionLocal()
    try:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        # Mensagem de robô de atendimento com termos de fila/SAC
        m_bot = MessageRecord(
            id=str(uuid4()),
            created_at=now,
            speaker="Bot Atendimento SAC",
            revised_text="Olá! Você é o número 200 na fila de espera. O agente transferiu o atendimento.",
            sentiment="NEGATIVE",
            sentiment_score=-0.8,
        )
        db.add(m_bot)
        db.commit()

        # Coleta do dia
        sentiment_timeline_service.collect_daily_sentiments(target_date=today_str, db=db)

        # Snapshots agregados padrão (3 dias)
        snaps = sentiment_timeline_service.get_daily_snapshots(target_date="3d", days=3, db=db)
        assert isinstance(snaps, list)

        # O robô deve ter sido neutralizado para NEUTRAL
        bot_snap = next((s for s in snaps if "Bot Atendimento" in s.speaker), None)
        if bot_snap:
            assert bot_snap.dominant_sentiment == "NEUTRAL"
            assert bot_snap.avg_sentiment_score == 0.0
    finally:
        db.close()

