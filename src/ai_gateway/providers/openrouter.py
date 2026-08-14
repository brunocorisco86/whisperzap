"""Provedor OpenRouter para o AI Gateway."""

import logging
import httpx
from src.ai_gateway.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseLLMProvider):
    """Provedor de LLM utilizando a API do OpenRouter."""

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, model_name: str = "google/gemini-2.5-flash-lite"):
        super().__init__(model_name=model_name)
        self.api_key = api_key

    @property
    def provider_name(self) -> str:
        return "openrouter"

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Chama a API do OpenRouter."""
        if not self.api_key or self.api_key.startswith("sua_chave"):
            raise ValueError("OPENROUTER_API_KEY não configurada ou inválida.")

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/brunoconter/hermes-voice-memory",
            "X-Title": "Hermes Voice Memory",
        }

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.BASE_URL, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error(f"Erro na API OpenRouter: {response.status_code} - {response.text}")
                response.raise_for_status()

            data = response.json()
            try:
                text = data["choices"][0]["message"]["content"].strip()
                return text
            except (KeyError, IndexError) as exc:
                logger.error(f"Formato inesperado na resposta do OpenRouter: {data}")
                raise ValueError("Resposta vazia ou inválida retornada pelo OpenRouter.") from exc
