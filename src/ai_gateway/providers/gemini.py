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
            return "gemini-3.5-flash-lite"
        # Se for modelo legado ou descontinuado conhecido, mapeia para geração ativa suportada
        if "3.1-flash-lite" in n or "1.5-flash" in n or "1.5-pro" in n or "1.5" in n:
            return "gemini-3.5-flash-lite"
        if "2.5-flash" in n:
            return "gemini-2.5-flash"
        if "2.5-pro" in n:
            return "gemini-2.5-pro"
        # Se for um nome direto da API (ex: gemini-3.5-flash-lite, gemini-3.7-flash), usa direto
        return name.strip()

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> str:
        """Chama a API do Gemini para gerar resposta, com cascata automática de fallback."""
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

        # Modelos candidatos prioritários para fallback caso o target esteja sobrecarregado (503/429) ou inexistente (404)
        fallback_order = ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-2.5-flash"]
        fallback_candidates = [m for m in fallback_order if m != target_model]

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, json=payload)
            except Exception as req_exc:
                logger.warning(f"Erro de rede ao chamar {target_model}: {req_exc}. Iniciando fallback...")
                response = None

            # Se der 503 (alta demanda), 429 (rate limit), 404 (inexistente) ou 5xx, aciona cascata de fallback
            if response is None or response.status_code in (404, 429, 500, 502, 503, 504):
                status_code = response.status_code if response is not None else "NETWORK_ERR"
                resp_snippet = response.text[:120] if response is not None else "Sem resposta"
                logger.warning(
                    f"⚠️ Modelo {target_model} falhou com status {status_code} ({resp_snippet}). "
                    f"Tentando cascata de fallback em: {fallback_candidates}"
                )
                for alt_model in fallback_candidates:
                    fallback_url = f"{self.BASE_URL}/{alt_model}:generateContent?key={self.api_key}"
                    try:
                        logger.info(f"🔄 Testando fallback no modelo {alt_model}...")
                        fb_resp = await client.post(fallback_url, json=payload, timeout=35.0)
                        if fb_resp.status_code == 200:
                            logger.info(f"✅ Fallback bem-sucedido com o modelo {alt_model}!")
                            response = fb_resp
                            break
                        else:
                            logger.warning(f"Fallback {alt_model} retornou status {fb_resp.status_code}: {fb_resp.text[:100]}")
                    except Exception as fb_exc:
                        logger.warning(f"Exceção no fallback {alt_model}: {fb_exc}")

            if response is None or response.status_code != 200:
                err_msg = f"Erro na API do Gemini: {response.status_code} - {response.text}" if response is not None else "Todas as tentativas de fallback falharam"
                logger.error(err_msg)
                if response is not None:
                    response.raise_for_status()
                raise RuntimeError(err_msg)

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
                },
                "outputDimensionality": 768,
            }

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        values = data["embedding"]["values"]
                        if len(values) == 768:
                            return values
                        if len(values) > 768:
                            return values[:768]
                        # Se vier menor que 768 por algum motivo, completa com 0.0
                        return values + [0.0] * (768 - len(values))
                    logger.warning(f"Embedding model {model_cand} retornou status {response.status_code}: {response.text[:120]}")
            except Exception as e:
                logger.error(f"Exceção ao chamar embedding Gemini ({model_cand}): {e}")

        # Fallback determinístico
        fb = await super().generate_embedding(text)
        if len(fb) == 768:
            return fb
        if len(fb) > 768:
            return fb[:768]
        return fb + [0.0] * (768 - len(fb))

