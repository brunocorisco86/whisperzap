"""Testes automatizados para Circuit Breaker, Auto-Remediação Dinâmica e Governança de Tokens."""

import time
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from src.main import app
from src.config import mask_token
from src.ai_gateway.model_registry import ModelRegistry, CircuitState
from src.ai_gateway.providers.gemini import GeminiProvider

client = TestClient(app)


def test_mask_token_utility():
    """Testa a função de mascaramento seguro de tokens para auditoria."""
    assert mask_token("") == "NOT_CONFIGURED"
    assert mask_token("sua_chave_aqui") == "NOT_CONFIGURED"
    assert mask_token("short") == "NOT_CONFIGURED"
    assert mask_token("AIzaSyB1234567890XYZW") == "AIza...XYZW"


def test_model_circuit_breaker_transitions(tmp_path):
    """Testa transições de estado CLOSED -> OPEN -> HALF_OPEN -> CLOSED no Circuit Breaker."""
    reg = ModelRegistry(persistence_path=str(tmp_path / "cb_test.json"))
    cb = reg.circuit_breaker

    model = "gemini-3.7-flash"
    assert cb.is_available(model) is True

    # 1ª falha: continua CLOSED
    cb.report_failure(model, status_code=503)
    assert cb.is_available(model) is True

    # 2ª falha: atinge threshold (2) e vai para OPEN
    tripped = cb.report_failure(model, status_code=503)
    assert tripped is True
    assert cb.is_available(model) is False

    # Status consolidado reflete o estado OPEN
    st = cb.get_status()
    assert st[model]["state"] == CircuitState.OPEN
    assert st[model]["failure_count"] == 2

    # Simula cooldown expirado alterando o timestamp da última falha
    cb.last_failure_time[model] = time.time() - 100.0
    assert cb.is_available(model) is True  # Transiciona para HALF_OPEN
    assert cb.circuit_state[model] == CircuitState.HALF_OPEN

    # Sucesso restabelece o circuito para CLOSED
    cb.report_success(model)
    assert cb.circuit_state[model] == CircuitState.CLOSED
    assert cb.is_available(model) is True


@pytest.mark.asyncio
async def test_handle_runtime_failure_auto_remediation(tmp_path):
    """Garante que a falha de um modelo em produção aciona auto-remediação autônoma."""
    reg = ModelRegistry(persistence_path=str(tmp_path / "remediation_test.json"))
    reg.set_active_model("revise", "gemini-3.7-flash")

    # Adiciona modelos descobertos no pool
    from src.ai_gateway.model_registry import DiscoveredModel
    reg.data.discovered_models = [
        DiscoveredModel(name="gemini-3.7-flash", tier="FLASH", cost_efficiency_score=8.5),
        DiscoveredModel(name="gemini-3.5-flash-lite", tier="LITE", cost_efficiency_score=9.5),
    ]

    # Simula falha 503 no modelo atual
    new_model = await reg.handle_runtime_failure("gemini-3.7-flash", task="revise", status_code=503)
    assert new_model == "gemini-3.5-flash-lite"
    assert reg.get_active_model("revise") == "gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_gemini_provider_fast_path_when_model_is_open(tmp_path):
    """Testa que o GeminiProvider desvia a requisição direto via Fast-Path se o modelo estiver em OPEN."""
    from src.ai_gateway.model_registry import model_registry

    # Coloca gemini-3.7-flash em OPEN
    model_registry.circuit_breaker.report_failure("gemini-3.7-flash", 503)
    model_registry.circuit_breaker.report_failure("gemini-3.7-flash", 503)
    assert model_registry.circuit_breaker.is_available("gemini-3.7-flash") is False

    provider = GeminiProvider(api_key="fake-key-12345678", model_name="gemini-3.7-flash")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {
            "candidates": [{"content": {"parts": [{"text": "texto revisado com sucesso"}]}}]
        }
        mock_post.return_value = mock_resp

        result = await provider.generate_text(prompt="teste")
        assert result == "texto revisado com sucesso"

        called_url = mock_post.call_args[0][0]
        assert "gemini-3.7-flash" not in called_url
        assert "gemini-3.5-flash-lite" in called_url or "gemini-flash-latest" in called_url

    # Limpa estado
    model_registry.circuit_breaker.report_success("gemini-3.7-flash")


def test_health_tokens_endpoint():
    """Testa o endpoint GET /health/tokens e mascaramento das credenciais."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {"instance": {"state": "open"}}
        mock_get.return_value = mock_resp

        resp = client.get("/health/tokens")
        assert resp.status_code == 200
        data = resp.json()
        assert "tokens" in data
        assert "gemini" in data["tokens"]
        assert "evolution_api" in data["tokens"]
        assert "masked_key" in data["tokens"]["gemini"]
