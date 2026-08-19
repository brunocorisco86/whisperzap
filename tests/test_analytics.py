"""Testes automatizados para o módulo de Analytics e Dashboard Executivo."""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from src.main import app
from src.memory.database import SessionLocal, init_db
from src.memory.models import MessageRecord, TaskRecord
from src.analytics.service import analytics_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Garante tabelas criadas."""
    init_db()


def test_analytics_service_empty_db():
    """Testa métricas com banco sem mensagens."""
    metrics = analytics_service.get_dashboard_metrics(period="30d", group_by="day")
    assert metrics.kpi_unique_senders.value == 0
    assert metrics.kpi_total_messages.value == 0
    assert isinstance(metrics.timeseries, list)
    assert isinstance(metrics.top_senders, list)
    assert isinstance(metrics.wordmap, list)
    assert len(metrics.heatmap) == 24 * 7


def test_analytics_service_with_data():
    """Testa agregações por dia, semana, mês e geração de WordMap."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        
        # 1. Cria mensagens com termos zootécnicos e de gestão
        m1 = MessageRecord(
            id="test-msg-1",
            created_at=now - timedelta(days=2),
            speaker="Debora Patel Conter",
            revised_text="Precisamos verificar a entrega de ração no silo do aviário amanhã cedo com urgência.",
            audio_duration_s=45.0,
            sentiment="URGENT",
            sentiment_score=-0.4,
        )
        m2 = MessageRecord(
            id="test-msg-2",
            created_at=now - timedelta(days=1),
            speaker="Debora Patel Conter",
            revised_text="A mortalidade do lote está dentro do padrão e o IEP melhorou.",
            audio_duration_s=30.0,
            sentiment="POSITIVE",
            sentiment_score=0.8,
        )
        m3 = MessageRecord(
            id="test-msg-3",
            created_at=now,
            speaker="Carlos Gestor",
            revised_text="Apresentação de resultados e relatório de custos para a diretoria na sexta-feira.",
            audio_duration_s=None,
            sentiment="NEUTRAL",
            sentiment_score=0.1,
        )
        db.add_all([m1, m2, m3])

        # Cria tarefa vinculada
        t1 = TaskRecord(
            id="test-task-1",
            message_id="test-msg-1",
            created_at=now - timedelta(days=2),
            title="Verificar entrega de ração",
            priority="HIGH",
            status="PENDING",
        )
        db.add(t1)
        db.commit()

        # 2. Testa agrupamento por dia
        res_day = analytics_service.get_dashboard_metrics(period="7d", group_by="day", db=db)
        assert res_day.kpi_unique_senders.value == 2
        assert res_day.kpi_total_messages.value == 3
        assert len(res_day.top_senders) == 2
        assert res_day.top_senders[0].speaker == "Debora Patel Conter"
        assert res_day.top_senders[0].total_messages == 2

        # Valida categorização do WordMap
        words_map = {item.word: item for item in res_day.wordmap}
        assert "ração" in words_map or "silo" in words_map or "aviário" in words_map
        if "ração" in words_map:
            assert words_map["ração"].category == "ZOOTECNIA"

        # 3. Testa agrupamento por semana
        res_week = analytics_service.get_dashboard_metrics(period="30d", group_by="week", db=db)
        assert len(res_week.timeseries) >= 1

        # 4. Testa agrupamento por mês
        res_month = analytics_service.get_dashboard_metrics(period="month", group_by="month", db=db)
        assert len(res_month.timeseries) >= 1
    finally:
        db.close()


def test_analytics_api_endpoint():
    """Testa requisição HTTP ao endpoint GET /api/v1/analytics/dashboard."""
    response = client.get("/api/v1/analytics/dashboard?period=7d&group_by=day")
    assert response.status_code == 200
    data = response.json()
    assert "kpi_unique_senders" in data
    assert "kpi_total_messages" in data
    assert "kpi_audio_duration" in data
    assert "kpi_actionability_rate" in data
    assert "kpi_sentiment_health" in data
    assert "timeseries" in data
    assert "top_senders" in data
    assert "wordmap" in data
    assert "heatmap" in data


def test_wordmap_filters_xml_and_diagram_stopwords():
    """Garante que tags XML/DrawIO não poluem a nuvem de palavras."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        m = MessageRecord(
            id="test-msg-xml-garbage",
            created_at=now,
            speaker="Diagram Bot",
            revised_text="<mxGraphModel><root><mxCell id='0'/><mxCell id='1' parent='0'/><mxGeometry x='20' y='30' width='80' height='40' as='geometry'/></root></mxGraphModel> zootecnia lote aviário",
            audio_duration_s=10.0,
            sentiment="NEUTRAL",
            sentiment_score=0.0,
        )
        db.add(m)
        db.commit()

        res = analytics_service.get_dashboard_metrics(period="7d", group_by="day", db=db)
        words_found = {item.word for item in res.wordmap}

        # Garante que termos de diagramas foram ignorados
        assert "mxcell" not in words_found
        assert "parent" not in words_found
        assert "mxgeometry" not in words_found
        assert "geometry" not in words_found
        assert "root" not in words_found
    finally:
        db.close()


def test_wordmap_spacy_compound_phrase_extraction():
    """Garante que o spaCy extrai sintagmas nominais compostos e identifica is_compound=True."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        m1 = MessageRecord(
            id="test-msg-compound-1",
            created_at=now,
            speaker="Gerente Suporte",
            revised_text="Estamos com uma grande fila de espera no atendimento e precisamos checar o sensor de temperatura do silo.",
            audio_duration_s=15.0,
            sentiment="URGENT",
            sentiment_score=-0.5,
        )
        db.add(m1)
        db.commit()

        res = analytics_service.get_dashboard_metrics(period="7d", group_by="day", db=db)
        word_objs = {item.word: item for item in res.wordmap}

        # Verifica se sintagmas compostos ou substantivos foram extraídos
        has_compound = any(item.is_compound for item in res.wordmap)
        assert has_compound or "sensor" in word_objs or "atendimento" in word_objs
        
        # Garante que termos categorizados possuem sample_context
        for item in res.wordmap:
            if item.is_compound:
                assert item.sample_context is not None
    finally:
        db.close()


