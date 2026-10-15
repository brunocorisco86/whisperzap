"""Testes automatizados para Governança de RPD, Threshold de Resumo em Calíope e Fechamento Sereno Dinâmico."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from src.config import settings
from src.ai_gateway.jev.service import jev_service, JEVAction, JEVIntent
from src.ai_gateway.extractor import semantic_extractor
from src.ai_gateway.schemas import SemanticExtractionRequest
from src.memory.database import SessionLocal, init_db
from src.memory.models import MessageRecord, TaskRecord, MessageCreate
from src.memory.repository import memory_repository
from src.reports.daily import daily_report_service, SERENITY_REFLECTIONS

# Garante esquema e tabelas criadas no banco de teste
init_db()


@pytest.mark.asyncio
async def test_caliope_summary_threshold_omits_summary_for_short_text():
    """Garante que mensagens abaixo do threshold (< 250 chars) resultem em summary=None."""
    short_text = "Vou enviar o relatório da calibração do Silo 3 amanhã cedo."
    assert len(short_text) < settings.CALIOPE_SUMMARY_MIN_CHARS

    # Mock do provedor de IA retornando JSON com summary
    mock_llm_json = """
    {
        "intent": "TASK",
        "summary": "Resumo desnecessário que não deveria existir",
        "tasks": [{"title": "Enviar relatório da calibração do Silo 3", "due_date": "amanhã cedo", "priority": "MEDIUM"}],
        "entities": [{"name": "Silo 3", "category": "EQUIPMENT"}],
        "triples": [],
        "unclear_terms": [],
        "decisions": [],
        "ideas": [],
        "topics": ["calibração", "silo 3"],
        "sentiment": "NEUTRAL",
        "sentiment_score": 0.0,
        "urgency": "MEDIUM"
    }
    """

    with patch.object(semantic_extractor.provider, "generate_text", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_llm_json

        req = SemanticExtractionRequest(text=short_text, speaker="Bruno")
        res = await semantic_extractor.extract(req)

        # Deve suprimir o resumo por estar abaixo de 250 caracteres
        assert res.summary is None
        assert len(res.tasks) == 1
        assert res.tasks[0].title == "Enviar relatório da calibração do Silo 3"


@pytest.mark.asyncio
async def test_caliope_summary_threshold_allows_summary_for_long_text():
    """Garante que textos extensos (>= 250 chars) continuem gerando resumo executivo."""
    long_text = (
        "Relatório operacional da cooperativa: realizamos a vistoria completa nos silos de armazenagem "
        "e detectamos variações anormais de temperatura no lote 402. O zootecnista Fernando Varolo "
        "solicitou a imediata calibragem dos sensores de umidade e a revisão da esteira transportadora "
        "antes do fechamento do expediente para evitar perdas na matéria-prima."
    )
    assert len(long_text) >= settings.CALIOPE_SUMMARY_MIN_CHARS

    mock_llm_json = """
    {
        "intent": "PROBLEM",
        "summary": "Vistoria nos silos identificou variações anormais no lote 402 com solicitação de calibragem imediata.",
        "tasks": [{"title": "Calibrar sensores de umidade e revisar esteira", "due_date": null, "priority": "HIGH"}],
        "entities": [{"name": "Lote 402", "category": "PROJECT"}, {"name": "Fernando Varolo", "category": "PERSON"}],
        "triples": [],
        "unclear_terms": [],
        "decisions": [],
        "ideas": [],
        "topics": ["silos", "calibragem", "sensores"],
        "sentiment": "URGENT",
        "sentiment_score": -0.6,
        "urgency": "HIGH"
    }
    """

    with patch.object(semantic_extractor.provider, "generate_text", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_llm_json

        req = SemanticExtractionRequest(text=long_text, speaker="Bruno")
        res = await semantic_extractor.extract(req)

        assert res.summary is not None
        assert "Vistoria nos silos" in res.summary


def test_jev_zero_token_notes():
    """Valida que notas informativas e avisos curtos recebem DIRECT_RESOLVE sem consumir IA (Zero-Token Notes)."""
    # 1. Aviso informativo curto
    judgment_note = jev_service.judge("Cheguei no escritório em Maringá.", speaker="Bruno", duration_s=4.0)
    assert judgment_note.action == JEVAction.DIRECT_RESOLVE
    assert judgment_note.intent == JEVIntent.MEMO
    assert judgment_note.direct_task_title is None
    assert judgment_note.suggested_route == "local"

    # 2. Confirmação curta
    judgment_conf = jev_service.judge("Confirmado o alinhamento para amanhã.", speaker="Bruno", duration_s=3.0)
    assert judgment_conf.action == JEVAction.DIRECT_RESOLVE
    assert judgment_conf.intent == JEVIntent.MEMO
    assert judgment_conf.direct_task_title is None

    # 3. Comando explícito de tarefa continua gerando direct_task_title
    judgment_task = jev_service.judge("Agendar reunião com o João amanhã.", speaker="Bruno", duration_s=5.0)
    assert judgment_task.action == JEVAction.DIRECT_RESOLVE
    assert judgment_task.intent == JEVIntent.TASK
    assert "Reunião com o João" in judgment_task.direct_task_title


@pytest.mark.asyncio
async def test_repository_zero_token_note_saves_without_summary():
    """Garante que Zero-Token Note é salva com intent=NOTE, sem tarefa e com summary=None."""
    db = SessionLocal()
    try:
        msg_in = MessageCreate(
            speaker="Bruno",
            raw_text="O caminhão descarregou no silo 2.",
            revised_text="O caminhão descarregou no silo 2.",
            meta_info={
                "jev_verdict": {
                    "action": "DIRECT_RESOLVE",
                    "intent": "MEMO",
                    "direct_task_title": None,
                    "urgency": "LOW",
                }
            },
        )
        saved = await memory_repository.save_message(data=msg_in, db=db)
        assert saved.intent == "NOTE"
        assert saved.summary is None
        assert saved.tasks == []
    finally:
        db.close()


@pytest.mark.asyncio
async def test_serenity_closing_includes_today_topics_and_rotates_quotes():
    """Testa se o Fechamento Sereno captura os assuntos de hoje e varia reflexões estoicas."""
    db = SessionLocal()
    try:
        from src.memory.timezone_utils import get_now_brt
        now_brt = get_now_brt()
        today_str = now_brt.strftime("%Y-%m-%d")

        # 1. Insere mensagem com tópicos hoje
        speaker_name = "Alan (C.Vale)"
        test_msg = MessageRecord(
            id="test-serenity-msg-001",
            created_at=datetime.now(timezone.utc),
            speaker=speaker_name,
            raw_text="Alinhamos os preços dos insumos e a safra de milho.",
            revised_text="Alinhamos os preços dos insumos e a safra de milho.",
            meta_info={"topics": ["Preços dos Insumos", "Safra de Milho"], "message_type": "text"},
        )
        db.add(test_msg)

        # 2. Insere tarefa para amanhã
        tomorrow_str = (now_brt + timedelta(days=1)).strftime("%Y-%m-%d")
        task_tomorrow = TaskRecord(
            id="test-task-tomorrow-001",
            title="Assinar aditivo contratual com a cooperativa",
            due_date=tomorrow_str,
            priority="HIGH",
            status="PENDING",
        )
        db.add(task_tomorrow)
        db.commit()

        # Gera fechamento sereno para hoje
        serenity_msg = await daily_report_service.generate_serenity_closing(target_date=today_str, db=db)

        # Validações
        assert "FECHAMENTO SERENO" in serenity_msg
        assert "Conversas & Registros de Hoje" in serenity_msg
        assert speaker_name in serenity_msg
        assert "Preços dos Insumos" in serenity_msg or "Safra de Milho" in serenity_msg
        assert "FOCO ESSENCIAL PARA AMANHÃ" in serenity_msg
        assert "Assinar aditivo contratual" in serenity_msg
        assert "[Para Amanhã]" in serenity_msg

        # Valida que citação estoica existe e pertence ao catálogo
        has_serene_quote = any(q.split("—")[0].strip() in serenity_msg for q in SERENITY_REFLECTIONS)
        assert has_serene_quote
    finally:
        # Cleanup
        db.query(MessageRecord).filter(MessageRecord.id == "test-serenity-msg-001").delete()
        db.query(TaskRecord).filter(TaskRecord.id == "test-task-tomorrow-001").delete()
        db.commit()
        db.close()
