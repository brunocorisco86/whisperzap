"""Provedor Google Gemini para o AI Gateway."""

import logging
import httpx
from src.ai_gateway.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Provedor de LLM utilizando a API do Google Gemini."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash-lite"):
        super().__init__(model_name=model_name)
        self.api_key = api_key

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Chama a API do Gemini para gerar resposta."""
        if not self.api_key or self.api_key.startswith("sua_chave"):
            raise ValueError("GEMINI_API_KEY não configurada ou inválida.")

        url = f"{self.BASE_URL}/{self.model_name}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                logger.error(f"Erro na API do Gemini: {response.status_code} - {response.text}")
                response.raise_for_status()

            data = response.json()
            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text
            except (KeyError, IndexError) as exc:
                logger.error(f"Formato inesperado na resposta do Gemini: {data}")
                raise ValueError("Resposta vazia ou inválida retornada pelo Gemini.") from exc
