"""Provedor Mock para testes e desenvolvimento offline."""

from src.ai_gateway.providers.base import BaseLLMProvider


class MockProvider(BaseLLMProvider):
    """Provedor simulado para testes sem consumo de APIs externas."""

    def __init__(self, model_name: str = "mock-model"):
        super().__init__(model_name=model_name)

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Retorna uma resposta simulada formatada."""
        # Se for um prompt de revisão contendo "Transcrição Bruta:", simula texto limpo
        if "Transcrição Bruta:" in prompt:
            lines = prompt.splitlines()
            raw_lines = []
            capture = False
            for line in lines:
                if line.startswith("Transcrição Bruta:"):
                    capture = True
                    continue
                if line.startswith("Contexto:") or line.startswith("Texto revisado:"):
                    break
                if capture and line.strip():
                    raw_lines.append(line.strip())

            raw_text = " ".join(raw_lines) if raw_lines else "Texto de teste simulado."
            # Capitaliza primeira letra e garante ponto final
            cleaned = raw_text.strip()
            if cleaned and not cleaned.endswith((".", "!", "?")):
                cleaned = cleaned + "."
            return cleaned.capitalize()

        return "Resposta simulada pelo MockProvider."
