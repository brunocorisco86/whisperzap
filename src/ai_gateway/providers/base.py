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
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> str:
        """Gera texto assincronamente a partir do prompt."""
        pass

    async def generate_embedding(self, text: str) -> list[float]:
        """Gera vetor de embedding para o texto fornecido (padrão 768 dimensões)."""
        import hashlib
        import math

        dim = 768
        vec = [0.0] * dim
        words = text.lower().split()
        if not words:
            return vec

        for word in words:
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            val = ((h >> 8) % 100) / 100.0 + 0.5
            vec[idx] += val

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec


