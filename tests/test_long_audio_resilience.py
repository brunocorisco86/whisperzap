"""Testes de resiliência e formatação de áudios longos no Hermes Voice Memory."""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from src.main import app
from src.ai_gateway.schemas import (
    ReviseRequest,
    ReviseResponse,
    SemanticExtractionRequest,
)
from src.ai_gateway.extractor import semantic_extractor

client = TestClient(app)


def test_ai_revise_graceful_fallback_on_llm_exception():
    """Valida que uma falha/timeout na LLM não gera HTTP 502, mas retorna 200 OK com o texto bruto."""
    long_raw_text = (
        "Fala Brunão, Luíza, certo, viu? Deixa eu tirar uma dúvida aqui contigo, "
        "que lá no Alisson Chá, ele tem balança de silo e estava batendo o beleza, "
        "sim, é igual que é a maliação ali que pode dar a diferença que não os 500 kg "
        "eu vou te mostrar a porta aqui de diferença, que veio lá dar lar, você acha que pode ter uma diferença?"
    )

    with patch("src.ai_gateway.router.get_ai_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.provider_name = "gemini"
        mock_provider.model_name = "gemini-3.1-flash-lite"
        mock_provider.generate_text.side_effect = Exception("Google Generative AI Timeout / 503 Service Unavailable")
        mock_get_provider.return_value = mock_provider

        response = client.post(
            "/ai/revise",
            json={"text": long_raw_text, "context": "Mensagem de voz via WhatsApp do usuário."},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_fallback"] is True
        assert data["text_revised"] == long_raw_text
        assert data["provider"] == "fallback-whisper-raw"


def test_ai_revise_success_with_mock_provider():
    """Valida fluxo normal de revisão sem erros."""
    raw_text = "preciso agendar a entrega de racao para o silo 3 da granja amanha"
    expected_revised = "Preciso agendar a entrega de ração para o silo 3 da granja amanhã."

    with patch("src.ai_gateway.router.get_ai_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.provider_name = "gemini"
        mock_provider.model_name = "gemini-3.1-flash-lite"
        mock_provider.generate_text.return_value = expected_revised
        mock_get_provider.return_value = mock_provider

        response = client.post(
            "/ai/revise",
            json={"text": raw_text},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_fallback"] is False
        assert data["text_revised"] == expected_revised
        assert data["provider"] == "gemini"


@pytest.mark.asyncio
async def test_semantic_extractor_handles_dict_decisions_gracefully():
    """Valida que o Extractor Semântico aceita decisões como dicts sem estourar ValidationError."""
    sample_text = "Ficou decidido que o lote 45 será abatido na quinta-feira."

    mock_llm_json_response = """
    {
      "intent": "DECISION",
      "summary": "Decidido abate do lote 45 para quinta-feira.",
      "sentiment": "CONFIDENT",
      "sentiment_score": 0.8,
      "tasks": [],
      "entities": [{"name": "Lote 45", "category": "PROJECT", "details": "Frangos de corte"}],
      "triples": [],
      "unclear_terms": [],
      "decisions": [
        {"description": "Abate do lote 45 confirmado para quinta-feira", "date": "2026-08-20"}
      ],
      "ideas": [{"idea": "Automatizar pesagem diária com sensor"}],
      "topics": ["abate", "lote 45", "programacao"],
      "urgency": "HIGH"
    }
    """

    with patch.object(semantic_extractor.provider, "generate_text", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_llm_json_response

        req = SemanticExtractionRequest(text=sample_text)
        result = await semantic_extractor.extract(req)

        assert result.intent == "DECISION"
        assert len(result.decisions) == 1
        assert "Abate do lote 45" in result.decisions[0]
        assert isinstance(result.decisions[0], str)
        assert len(result.ideas) == 1
        assert "Automatizar pesagem" in result.ideas[0]
        assert isinstance(result.ideas[0], str)
