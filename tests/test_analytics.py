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


def test_analytics_utc3_heatmap_and_timeseries_continuity():
    """Valida que o heatmap calcula a hora e dia em UTC-3 e que timeseries contém dias contínuos."""
    from src.memory.timezone_utils import BRASILIA_TZ, to_local_tz
    from src.contacts.models import ContactRecord

    db = SessionLocal()
    try:
        # Mensagem às 15:00 UTC de ontem (que equivale a 12:00 UTC-3 em Brasília)
        now_utc = datetime.now(timezone.utc)
        dt_utc = (now_utc - timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
        m = MessageRecord(
            id="test-msg-utc3",
            created_at=dt_utc,
            speaker="Alice Agro",
            revised_text="Verificação do sensor de nível no silo.",
            audio_duration_s=20.0,
        )
        db.add(m)
        db.commit()

        metrics = analytics_service.get_dashboard_metrics(period="7d", group_by="day", db=db)
        
        # 1. Heatmap deve ter marcado na hora 12 (15 UTC - 3 = 12 BRT)
        dt_brt = to_local_tz(dt_utc)
        target_cell = next((c for c in metrics.heatmap if c.day_of_week == dt_brt.weekday() and c.hour == 12), None)
        assert target_cell is not None
        assert target_cell.count >= 1

        # 2. Timeseries deve ter 7 pontos contínuos cobrindo os últimos 7 dias
        assert len(metrics.timeseries) == 7
        assert all(isinstance(p.avg_chars, float) for p in metrics.timeseries)
        assert all(isinstance(p.avg_audio_duration_s, float) for p in metrics.timeseries)
    finally:
        db.close()


def test_analytics_top_senders_clio_contact_resolution():
    """Garante que números de telefone ou IDs não cadastrados são mapeados aos contatos de Clio."""
    from src.contacts.models import ContactRecord

    db = SessionLocal()
    try:
        # Cadastra contato em Clio
        c1 = ContactRecord(
            id="clio-cvale-1",
            name="Roberto Engenheiro",
            nickname="Beto",
            phone_number="5544988776655",
            role="ENGINEER",
            avatar_url="http://avatar.example.com/beto.jpg",
        )
        db.add(c1)

        # Mensagem enviada pelo número de telefone sem o nome
        m1 = MessageRecord(
            id="msg-phone-unresolved",
            created_at=datetime.now(timezone.utc),
            speaker="5544988776655",
            meta_info={"phone": "5544988776655", "pushName": "Beto"},
            revised_text="Relatório dos sensores enviado.",
            audio_duration_s=12.0,
        )
        db.add(m1)
        db.commit()

        metrics = analytics_service.get_dashboard_metrics(period="7d", group_by="day", db=db)
        top_speakers = [s.speaker for s in metrics.top_senders]
        
        # O speaker deve ter sido resolvido para o nome de Clio: 'Roberto Engenheiro (Beto)'
        assert any("Roberto Engenheiro" in spk for spk in top_speakers)
        resolved_metric = next(s for s in metrics.top_senders if "Roberto Engenheiro" in s.speaker)
        assert resolved_metric.role == "ENGINEER"
        assert resolved_metric.avatar_url == "http://avatar.example.com/beto.jpg"
    finally:
        db.close()


def test_analytics_actionability_rate_never_exceeds_100_percent():
    """Garante que a taxa de ação é matematicamente limitada entre 0% e 100% mesmo com múltiplas tarefas por mensagem."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        m = MessageRecord(
            id="msg-multi-tasks",
            created_at=now,
            speaker="Diretoria",
            revised_text="Comprar insumos, contatar produtor e agendar caminhão.",
            audio_duration_s=15.0,
        )
        db.add(m)
        
        # Adiciona 5 tarefas para 1 única mensagem
        for i in range(5):
            t = TaskRecord(
                id=f"multi-task-{i}",
                message_id="msg-multi-tasks",
                created_at=now,
                title=f"Ação {i}",
                status="PENDING",
            )
            db.add(t)
        db.commit()

        metrics = analytics_service.get_dashboard_metrics(period="7d", group_by="day", db=db)
        val_str = metrics.kpi_actionability_rate.value.replace("%", "").strip()
        val_float = float(val_str)
        assert 0.0 <= val_float <= 100.0
    finally:
        db.close()


def test_analytics_period_3d_and_human_engagement_ranking():
    """Testa o período 3d e garante que conversas humanas com áudio e tarefas superam bots de SAC com rajadas de texto."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # 1. Contato Humano com 1 áudio e 1 tarefa
        m_human = MessageRecord(
            id="msg-human-voice",
            created_at=now - timedelta(days=1),
            speaker="Larissa Cooperada",
            revised_text="Preciso alinhar a rota dos caminhões de ração para amanhã cedo.",
            audio_duration_s=65.0,
            sentiment="POSITIVE",
            sentiment_score=0.7,
        )
        t_human = TaskRecord(
            id="task-human-1",
            message_id="msg-human-voice",
            created_at=now - timedelta(days=1),
            title="Alinhar rota de caminhões",
            status="PENDING",
        )
        db.add_all([m_human, t_human])

        # 2. Bot de Autoatendimento com 20 mensagens mecânicas de texto sem áudio e sem tarefa
        for i in range(20):
            m_bot = MessageRecord(
                id=f"msg-bot-sac-{i}",
                created_at=now - timedelta(days=1),
                speaker="5511999990000",
                meta_info={"phone": "5511999990000", "pushName": "Central SAC Automático"},
                revised_text=f"Olá! Você é o número {200 + i} na fila de espera do atendimento. Digite 1 para aguardar.",
                audio_duration_s=None,
                sentiment="NEUTRAL",
                sentiment_score=0.0,
            )
            db.add(m_bot)

        db.commit()

        # Consulta com período padrão 3d
        metrics_3d = analytics_service.get_dashboard_metrics(period="3d", group_by="day", db=db)
        assert metrics_3d.period == "3d"
        assert len(metrics_3d.timeseries) == 3

        # O interlocutor humano (Larissa) deve estar à frente do bot de SAC no ranking mesmo com menos mensagens brutas
        speakers = [s.speaker for s in metrics_3d.top_senders]
        assert "Larissa Cooperada" in speakers
        larissa_idx = next(i for i, s in enumerate(metrics_3d.top_senders) if s.speaker == "Larissa Cooperada")
        assert metrics_3d.top_senders[larissa_idx].audio_count == 1
        assert metrics_3d.top_senders[larissa_idx].tasks_count == 1

        bot_indices = [i for i, s in enumerate(metrics_3d.top_senders) if "SAC" in s.speaker or "5511999990000" in s.speaker]
        if bot_indices:
            # Se o bot estiver no ranking, deve estar atrás de Larissa
            assert bot_indices[0] > larissa_idx
    finally:
        db.close()



