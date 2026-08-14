"""Interface base para provedores de LLM no AI Gateway."""

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Classe base abstrata para provedores de inteligência artificial."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Nome identificador do provedor."""
        pass

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Gera texto assincronamente a partir do prompt."""
        pass
