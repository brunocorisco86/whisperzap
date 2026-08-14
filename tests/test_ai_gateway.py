"""Testes unitários para o AI Gateway e seus provedores."""

import pytest
from src.ai_gateway.providers import get_ai_provider, MockProvider, GeminiProvider, OpenRouterProvider
from src.ai_gateway.prompts import REVISE_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_mock_provider_revision():
    """Valida o funcionamento do MockProvider para revisão contextual."""
    provider = MockProvider()
    assert provider.provider_name == "mock"

    prompt = (
        "Transcrição Bruta:\n"
        "amanha preciso falar com o joao\n\n"
        "Contexto: Avicultura.\n"
        "Texto revisado:"
    )

    result = await provider.generate_text(
        prompt=prompt,
        system_instruction=REVISE_SYSTEM_PROMPT,
    )
    assert result == "Amanha preciso falar com o joao."


def test_get_ai_provider_factory():
    """Valida a factory get_ai_provider para diferentes provedores."""
    mock_prov = get_ai_provider(task="revise", provider_override="mock")
    assert isinstance(mock_prov, MockProvider)

    gemini_prov = get_ai_provider(task="revise", provider_override="gemini")
    assert isinstance(gemini_prov, GeminiProvider)
    assert gemini_prov.provider_name == "gemini"

    openrouter_prov = get_ai_provider(task="weekly", provider_override="openrouter")
    assert isinstance(openrouter_prov, OpenRouterProvider)
    assert openrouter_prov.provider_name == "openrouter"


def test_get_ai_provider_invalid():
    """Valida exceção para provedor inválido."""
    with pytest.raises(ValueError, match="Provedor desconhecido"):
        get_ai_provider(task="revise", provider_override="invalid_provider")
