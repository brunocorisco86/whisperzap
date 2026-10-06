"""Testes unitários para o Orquestrador JEV (Judge - Evaluator - Verifier)."""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from src.main import app
from src.ai_gateway.jev import (
    jev_service,
    JEVAction,
    JEVIntent,
    JEVUrgency,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_jev_judge_bypass_trivial():
    """Valida se o Judge classifica saudações sociais e emojis como BYPASS."""
    verdict_emoji = jev_service.judge("👍👍🎉", speaker="Bruno")
    assert verdict_emoji.action == JEVAction.BYPASS
    assert verdict_emoji.intent == JEVIntent.NOISE

    verdict_social = jev_service.judge("bom dia", speaker="João")
    assert verdict_social.action == JEVAction.BYPASS
    assert verdict_social.intent == JEVIntent.NOISE
    assert verdict_social.confidence >= 0.95


def test_jev_judge_graph_query():
    """Valida se o Judge detecta perguntas e consultas históricas."""
    verdict = jev_service.judge("Qual foi a última calibragem do sensor do Silo 3?", speaker="Bruno")
    assert verdict.action == JEVAction.GRAPH_QUERY
    assert verdict.intent == JEVIntent.QUESTION
    assert verdict.suggested_route == "gemini"


def test_jev_judge_direct_resolve_task():
    """Valida se tarefas curtas e diretas são encaminhadas para DIRECT_RESOLVE com data relativa."""
    text = "lembrar de ligar para o caseiro amanhã às 8h"
    verdict = jev_service.judge(text, speaker="Bruno", is_self_memo=True, duration_s=6.0)

    assert verdict.action == JEVAction.DIRECT_RESOLVE
    assert verdict.intent == JEVIntent.TASK
    assert verdict.suggested_route == "local"
    assert verdict.direct_task_title is not None
    assert "caseiro" in verdict.direct_task_title.lower()
    assert verdict.direct_due_date is not None  # Extraiu data de 'amanhã'


def test_jev_judge_urgency_detection():
    """Valida se palavras de emergência elevam a urgência para URGENT."""
    verdict = jev_service.judge("urgente verificar o lote do aviário 4", speaker="Bruno", is_self_memo=True)
    assert verdict.urgency == JEVUrgency.URGENT


def test_jev_judge_deep_analysis_long_text():
    """Valida se textos longos com múltiplos assuntos são classificados como DEEP_ANALYSIS."""
    long_text = (
        "Reunião de alinhamento estratégico com a diretoria da C.Vale sobre os silos inteligentes. "
        "Precisamos avaliar a conversão alimentar, o IEP dos lotes de 45 a 58 dias e revisar "
        "o cronograma de instalação dos sensores ultrassônicos em todas as unidades cooperadas até dezembro."
    )
    verdict = jev_service.judge(long_text, speaker="Diretoria", duration_s=45.0)
    assert verdict.action == JEVAction.DEEP_ANALYSIS
    assert verdict.suggested_route == "gemini"
    assert verdict.confidence >= 0.85


def test_jev_verifier_sanitizes_redundant_destaques():
    """Valida se o Verifier remove blocos artificiais de Destaques em áudios curtos."""
    short_revised = (
        "Anotar ideia urgente para os silos.\n\n"
        "📌 *Destaques do Áudio:*\n"
        "• Nota pessoal de anotação urgente."
    )
    mock_task = MagicMock()
    mock_task.title = "Anotar ideia urgente para os silos"

    result = jev_service.verify_and_sanitize(
        raw_text="anotar ideia urgente para os silos",
        revised_text=short_revised,
        tasks=[mock_task],
        duration_s=10.0,
    )

    assert result["is_clean"] is True
    assert "📌" not in result["revised_text"]
    assert "Destaques do Áudio" not in result["revised_text"]
    assert result["tasks_count"] == 1


def test_jev_api_endpoint_judge(client):
    """Valida o endpoint POST /api/v1/ai/jev/judge via TestClient."""
    payload = {
        "text": "Anotar ideia urgente para o projeto dos silos",
        "speaker": "Bruno Conter",
        "is_self_memo": True,
        "duration_s": 8.0,
    }
    response = client.post("/api/v1/ai/jev/judge", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "action" in data
    assert "intent" in data
    assert "confidence" in data
    assert data["action"] == "DIRECT_RESOLVE"
    assert data["urgency"] == "URGENT"
    assert "silos" in data["direct_task_title"].lower()
