"""Provedor Google Gemini para o AI Gateway."""

import logging
from typing import Any
import httpx
from src.ai_gateway.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Provedor de LLM utilizando a API do Google Gemini."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model_name: str = "gemini-3.1-flash-lite"):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _get_api_model_name(self, name: str) -> str:
        """Mapeia nomes de modelo para as tags suportadas na API pública do Gemini."""
        n = (name or "").lower().strip()
        if "3.1" in n or "flash-lite" in n or "2.5" in n:
            return "gemini-2.5-flash"
        if "2.0" in n:
            return "gemini-2.0-flash"
        if "1.5" in n:
            return "gemini-1.5-flash"
        return name

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> str:
        """Chama a API do Gemini para gerar resposta."""
        if not self.api_key or self.api_key.startswith("sua_chave"):
            raise ValueError("GEMINI_API_KEY não configurada ou inválida.")

        target_model = self._get_api_model_name(self.model_name)
        url = f"{self.BASE_URL}/{target_model}:generateContent?key={self.api_key}"

        gen_config: dict[str, Any] = {
            "temperature": temperature,
        }
        if max_output_tokens:
            gen_config["maxOutputTokens"] = max_output_tokens

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": gen_config,
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            # Se der 404 no modelo, tenta fallback para gemini-1.5-flash
            if response.status_code == 404 and target_model != "gemini-1.5-flash":
                fallback_url = f"{self.BASE_URL}/gemini-1.5-flash:generateContent?key={self.api_key}"
                logger.warning(f"Modelo {target_model} retornou 404. Tentando fallback para gemini-1.5-flash.")
                response = await client.post(fallback_url, json=payload)

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

    async def generate_embedding(self, text: str) -> list[float]:
        """Gera embedding vetorial usando a API do Gemini text-embedding-004."""
        if not self.api_key or self.api_key.startswith("sua_chave"):
            return await super().generate_embedding(text)

        url = f"{self.BASE_URL}/text-embedding-004:embedContent?key={self.api_key}"
        payload = {
            "model": "models/text-embedding-004",
            "content": {
                "parts": [{"text": text}]
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return data["embedding"]["values"]
                logger.warning(f"Erro ao gerar embedding no Gemini ({response.status_code}): {response.text}")
        except Exception as e:
            logger.error(f"Exceção ao chamar embedding Gemini: {e}")

        # Fallback determinístico
        return await super().generate_embedding(text)

