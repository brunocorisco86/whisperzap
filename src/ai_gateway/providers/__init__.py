"""Model Router e Factory de Provedores de LLM."""

from src.config import settings
from src.ai_gateway.providers.base import BaseLLMProvider
from src.ai_gateway.providers.gemini import GeminiProvider
from src.ai_gateway.providers.openrouter import OpenRouterProvider
from src.ai_gateway.providers.mock import MockProvider

__all__ = [
    "BaseLLMProvider",
    "GeminiProvider",
    "OpenRouterProvider",
    "MockProvider",
    "get_ai_provider",
]


def get_ai_provider(
    task: str = "revise",
    provider_override: str | None = None,
    model_override: str | None = None,
) -> BaseLLMProvider:
    """Retorna a instância do provedor e modelo adequado conforme a tarefa, com resolução dinâmica via ModelRegistry."""
    from src.ai_gateway.model_registry import model_registry

    provider_name = provider_override or settings.AI_PROVIDER

    # Determina o modelo dinamicamente via ModelRegistry ou settings
    if model_override:
        model_name = model_override
    else:
        model_name = model_registry.get_active_model(task=task, fallback=settings.AI_DEFAULT_MODEL)

    if provider_name == "gemini":
        return GeminiProvider(api_key=settings.GEMINI_API_KEY, model_name=model_name)
    elif provider_name == "openrouter":
        return OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY, model_name=model_name)
    elif provider_name == "mock":
        return MockProvider(model_name=model_name)
    else:
        raise ValueError(f"Provedor desconhecido: '{provider_name}'. Suportados: gemini, openrouter, mock")
