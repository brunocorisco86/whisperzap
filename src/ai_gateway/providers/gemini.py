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
        """Mapeia nomes de modelo para as tags ativas suportadas na API pública do Gemini."""
        n = (name or "").lower().strip()
        if not n:
            return "gemini-3.1-flash-lite"
        # Se for modelo legado conhecido, mapeia para geração suportada
        if "2.5-flash" in n:
            return "gemini-3.6-flash"
        if "1.5-flash" in n or "1.5-pro" in n or "1.5" in n:
            return "gemini-3.1-flash-lite"
        # Se for um nome direto da API (ex: gemini-3.5-flash-lite, gemini-3.7-flash, gemini-3.1-flash-lite), usa direto
        return name.strip()

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

        fallback_candidates = [
            m for m in ["gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-flash-latest"]
            if m != target_model
        ]

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            # Se der 404 no modelo, tenta fallback para modelos estáveis conhecidos
            if response.status_code == 404:
                for alt_model in fallback_candidates:
                    fallback_url = f"{self.BASE_URL}/{alt_model}:generateContent?key={self.api_key}"
                    logger.warning(f"Modelo {target_model} retornou 404. Tentando fallback para {alt_model}.")
                    response = await client.post(fallback_url, json=payload)
                    if response.status_code == 200:
                        break

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
        """Gera embedding vetorial usando a API do Gemini (gemini-embedding-001 ou fallback)."""
        if not self.api_key or self.api_key.startswith("sua_chave"):
            return await super().generate_embedding(text)

        for model_cand in ["gemini-embedding-001", "gemini-embedding-2", "text-embedding-004"]:
            url = f"{self.BASE_URL}/{model_cand}:embedContent?key={self.api_key}"
            payload = {
                "model": f"models/{model_cand}",
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
                    logger.warning(f"Embedding model {model_cand} retornou status {response.status_code}: {response.text[:120]}")
            except Exception as e:
                logger.error(f"Exceção ao chamar embedding Gemini ({model_cand}): {e}")

        # Fallback determinístico
        return await super().generate_embedding(text)

