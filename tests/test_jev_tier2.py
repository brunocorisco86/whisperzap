"""Testes unitários para o Motor Tier 2 (SLM / Local Model) do JEV."""

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.ai_gateway.jev import (
    jev_service,
    JEVAction,
    JEVIntent,
    JEVUrgency,
    JEVTier2Engine,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_tier2_direct_invocation():
    """Valida se o parâmetro force_tier2 força a execução pelo Tier 2 SLM."""
    text = "Acho que podíamos criar um dashboard para os silos"
    verdict = jev_service.judge(text, force_tier2=True)

    assert verdict.tier_used == "tier2_slm"
    assert verdict.intent in (JEVIntent.IDEA, JEVIntent.TASK)
    assert verdict.action == JEVAction.DIRECT_RESOLVE
    assert verdict.confidence >= 0.80


def test_tier2_noise_classification():
    """Valida se o Tier 2 classifica saudações sociais como BYPASS/NOISE."""
    verdict = jev_service.judge("Valeu, obrigado pessoal, abraço!", force_tier2=True)

    assert verdict.tier_used == "tier2_slm"
    assert verdict.action == JEVAction.BYPASS
    assert verdict.intent == JEVIntent.NOISE
    assert verdict.urgency == JEVUrgency.LOW


def test_tier2_question_classification():
    """Valida se o Tier 2 classifica dúvidas como GRAPH_QUERY/QUESTION."""
    verdict = jev_service.judge("Qual o status e leitura dos sensores dos silos?", force_tier2=True)

    assert verdict.tier_used == "tier2_slm"
    assert verdict.action == JEVAction.GRAPH_QUERY
    assert verdict.intent == JEVIntent.QUESTION


def test_tier2_urgent_classification():
    """Valida se termos de emergência elevam a urgência no Tier 2."""
    verdict = jev_service.judge("Emergência falta de ração no aviário 2 urgente", force_tier2=True)

    assert verdict.tier_used == "tier2_slm"
    assert verdict.urgency == JEVUrgency.URGENT
    assert verdict.action == JEVAction.DIRECT_RESOLVE


def test_tier2_fallback_missing_onnx_resilience():
    """Valida se o Tier 2 opera perfeitamente mesmo quando o caminho ONNX não existe."""
    engine = JEVTier2Engine()
    engine.model_path = "/tmp/modelo_inexistente_12345.onnx"
    engine._initialize_onnx()

    assert engine.session is None  # Sem sessão ONNX

    verdict = engine.judge("Verificar rota do TMS e entrega de ração")
    assert verdict.tier_used == "tier2_slm"
    assert verdict.action == JEVAction.DIRECT_RESOLVE
    assert verdict.intent == JEVIntent.TASK
    assert "tms" in verdict.direct_task_title.lower() or "verificar" in verdict.direct_task_title.lower()


def test_tier2_api_endpoint_force_tier2(client):
    """Valida o endpoint POST /api/v1/ai/jev/judge com a flag force_tier2."""
    payload = {
        "text": "Acho que podíamos rever a rota do caminhão do TMS",
        "speaker": "Bruno Conter",
        "force_tier2": True,
    }
    response = client.post("/api/v1/ai/jev/judge", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["tier_used"] == "tier2_slm"
    assert data["action"] == "DIRECT_RESOLVE"
    assert data["intent"] in ("IDEA", "TASK")
