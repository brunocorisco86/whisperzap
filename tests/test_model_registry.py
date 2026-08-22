"""Testes automatizados para o ModelRegistry e Gerenciamento Dinâmico de Modelos de IA."""

import os
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from src.main import app
from src.ai_gateway.model_registry import ModelRegistry, model_registry
from src.ai_gateway.providers import get_ai_provider

client = TestClient(app)


@pytest.fixture
def temp_registry(tmp_path):
    """Cria uma instância isolada do ModelRegistry em arquivo temporário."""
    file_path = str(tmp_path / "test_ai_model_registry.json")
    reg = ModelRegistry(persistence_path=file_path)
    return reg


def test_model_registry_defaults_and_persistence(temp_registry):
    """Garante que o registro carrega modelos padrão e persiste alterações."""
    assert temp_registry.get_active_model("revise") == "gemini-3.1-flash-lite"
    assert temp_registry.get_active_model("extract") == "gemini-3.1-flash-lite"

    # Altera modelo dinamicamente
    temp_registry.set_active_model("revise", "gemini-3.6-flash")
    assert temp_registry.get_active_model("revise") == "gemini-3.6-flash"

    # Recarrega do arquivo
    reloaded = ModelRegistry(persistence_path=temp_registry.persistence_path)
    assert reloaded.get_active_model("revise") == "gemini-3.6-flash"


def test_model_registry_update_in_batch(temp_registry):
    """Testa atualização de múltiplos modelos em lote."""
    updates = {
        "revise": "gemini-3.5-flash-lite",
        "extract": "gemini-3.5-flash-lite",
        "summarize": "gemini-3.7-flash",
    }
    updated = temp_registry.update_active_models(updates, auto_adopt=False)
    assert updated["revise"] == "gemini-3.5-flash-lite"
    assert updated["summarize"] == "gemini-3.7-flash"
    assert temp_registry.data.auto_adopt_best_lite is False


@pytest.mark.asyncio
async def test_discover_gemini_models_mocked(temp_registry):
    """Testa a descoberta e ranqueamento de modelos a partir do payload da API do Gemini."""
    mock_gemini_response = {
        "models": [
            {
                "name": "models/gemini-3.1-flash-lite",
                "displayName": "Gemini 3.1 Flash-Lite",
                "description": "Modelo ultra-rápido econômico",
                "supportedGenerationMethods": ["generateContent", "countTokens"],
            },
            {
                "name": "models/gemini-3.7-flash",
                "displayName": "Gemini 3.7 Flash",
                "description": "Modelo flash avançado",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-embedding-001",
                "displayName": "Gemini Embedding 001",
                "description": "Embeddings vetoriais",
                "supportedGenerationMethods": ["embedContent"],
            },
            {
                "name": "models/gemini-1.5-flash",
                "displayName": "Gemini 1.5 Flash (Legado)",
                "supportedGenerationMethods": ["generateContent"],
            },
        ]
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: mock_gemini_response
        mock_get.return_value = mock_response

        report = await temp_registry.discover_gemini_models(api_key="valid_test_key", auto_adopt=True)

        assert report["status"] == "success"
        assert report["discovered_count"] >= 3
        assert report["best_lite_model"]["name"] == "gemini-3.1-flash-lite"
        assert report["best_flash_model"]["name"] == "gemini-3.7-flash"
        assert report["best_embedding_model"]["name"] == "gemini-embedding-001"

        # Verifica se o modelo ativo foi adotado
        assert temp_registry.get_active_model("extract") == "gemini-3.1-flash-lite"
        assert temp_registry.get_active_model("embedding") == "gemini-embedding-001"


def test_ai_models_api_endpoints():
    """Testa as rotas GET /ai/models, POST /ai/models/discover e PUT /ai/models/active."""
    # 1. GET /ai/models
    res_get = client.get("/ai/models")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["status"] == "success"
    assert "active_models" in data
    assert "auto_adopt_best_lite" in data

    # 2. PUT /ai/models/active
    res_put = client.put("/ai/models/active", json={"revise": "gemini-3.1-flash-lite"})
    assert res_put.status_code == 200
    put_data = res_put.json()
    assert put_data["status"] == "success"
    assert put_data["active_models"]["revise"] == "gemini-3.1-flash-lite"


def test_get_ai_provider_dynamic_resolution():
    """Garante que get_ai_provider resolve o modelo dinamicamente a partir do registry."""
    model_registry.set_active_model("extract", "gemini-3.1-flash-lite")
    provider = get_ai_provider(task="extract")
    assert provider.model_name == "gemini-3.1-flash-lite"
