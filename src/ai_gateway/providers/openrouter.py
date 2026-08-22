"""Provedor OpenRouter para o AI Gateway."""

import logging
import httpx
from src.ai_gateway.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseLLMProvider):
    """Provedor de LLM utilizando a API do OpenRouter."""

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, model_name: str = "google/gemini-2.0-flash-001"):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = "https://openrouter.ai/api/v1"

    @property
    def provider_name(self) -> str:
        return "openrouter"

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> str:
        """Chama a API do OpenRouter com fallback automático."""
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

        models_to_try = [self.model_name]
        for fallback_m in ["google/gemini-2.0-flash-001", "google/gemini-flash-1.5", "meta-llama/llama-3.3-70b-instruct"]:
            if fallback_m not in models_to_try:
                models_to_try.append(fallback_m)

        last_error = None
        for current_model in models_to_try:
            payload = {
                "model": current_model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_output_tokens:
                payload["max_tokens"] = max_output_tokens

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(self.BASE_URL, headers=headers, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        text = data["choices"][0]["message"]["content"].strip()
                        return text
                    logger.warning(f"OpenRouter modelo {current_model} retornou {response.status_code}: {response.text[:120]}")
            except Exception as e:
                logger.warning(f"Exceção ao chamar OpenRouter com modelo {current_model}: {e}")
                last_error = e

        raise ValueError(f"Falha em todos os modelos OpenRouter testados: {last_error}")
