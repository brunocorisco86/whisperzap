"""Módulo de Extração Semântica Estruturada para o AI Gateway."""

import json
import logging
import re
import time
from src.ai_gateway.prompts import EXTRACT_SYSTEM_PROMPT, EXTRACT_USER_TEMPLATE
from src.ai_gateway.providers import get_ai_provider
from src.ai_gateway.schemas import (
    ExtractedEntity,
    ExtractedTask,
    SemanticExtractionRequest,
    SemanticExtractionResponse,
)
from src.config import settings
from src.dictionary.service import dictionary_service

logger = logging.getLogger(__name__)


class SemanticExtractor:
    """Orquestrador de Extração Semântica e Intenções com LLM."""

    def __init__(self):
        self.provider = get_ai_provider(task="extract")


    def _extract_json_from_text(self, raw_response: str) -> dict:
        """Extrai e faz parsing do bloco JSON mesmo se a LLM retornar marcação Markdown."""
        text = raw_response.strip()

        # Tenta remover blocos ```json ... ```
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if json_match:
            text = json_match.group(1).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSONDecodeError direto: {e}. Tentando encontrar primeiro '{{' e último '}}'.")
            # Tenta encontrar primeiro { e último }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise ValueError(f"Não foi possível extrair JSON válido da resposta da IA: {raw_response[:200]}") from e

    async def extract(self, request: SemanticExtractionRequest) -> SemanticExtractionResponse:
        """Executa a extração semântica de uma mensagem."""
        start_time = time.perf_counter()

        # Constrói bloco de contexto
        context_parts = []
        if request.speaker:
            context_parts.append(f"Remetente: {request.speaker}")
        if request.context:
            context_parts.append(f"Contexto prévio: {request.context}")

        if request.include_dictionary:
            dict_hint = dictionary_service.get_prompt_context_hint()
            if dict_hint:
                context_parts.append(dict_hint)

        context_block = "\n".join(context_parts)
        if context_block:
            context_block = f"Contexto de Apoio:\n{context_block}\n"

        prompt = EXTRACT_USER_TEMPLATE.format(
            text=request.text,
            context_block=context_block,
        )

        raw_llm_response = await self.provider.generate_text(
            prompt=prompt,
            system_instruction=EXTRACT_SYSTEM_PROMPT,
            temperature=0.1,
        )

        try:
            parsed_data = self._extract_json_from_text(raw_llm_response)
        except Exception as e:
            logger.error(f"Erro ao analisar extração da LLM: {e}")
            # Fallback seguro estruturado
            parsed_data = {
                "intent": "NOTE",
                "summary": request.text[:100] + ("..." if len(request.text) > 100 else ""),
                "tasks": [],
                "entities": [],
                "decisions": [],
                "ideas": [],
                "topics": [],
                "urgency": "MEDIUM",
            }

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Normaliza tarefas e entidades
        tasks = [ExtractedTask(**t) if isinstance(t, dict) else t for t in parsed_data.get("tasks", [])]
        entities = [ExtractedEntity(**e) if isinstance(e, dict) else e for e in parsed_data.get("entities", [])]

        return SemanticExtractionResponse(
            intent=parsed_data.get("intent", "NOTE"),
            summary=parsed_data.get("summary", request.text[:100]),
            tasks=tasks,
            entities=entities,
            decisions=parsed_data.get("decisions", []),
            ideas=parsed_data.get("ideas", []),
            topics=parsed_data.get("topics", []),
            urgency=parsed_data.get("urgency", "MEDIUM"),
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            processing_time_ms=elapsed_ms,
        )


semantic_extractor = SemanticExtractor()
