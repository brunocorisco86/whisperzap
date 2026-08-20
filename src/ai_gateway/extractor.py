"""Módulo de Extração Semântica Estruturada para o AI Gateway."""

import json
import logging
import re
import time
from typing import Any
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

        from src.ai_gateway.task_learner import task_learner_engine
        pruning_hint = task_learner_engine.get_pruning_rules_prompt_hint()
        if pruning_hint:
            context_parts.append(pruning_hint)

        context_block = "\n\n".join(context_parts)
        if context_block:
            context_block = f"Contexto de Apoio & Regras:\n{context_block}\n"

        # 1. Poda de disfluências e compressão extrativa de contexto com spaCy para economia de tokens
        from src.ai_gateway.token_economy import token_economy
        from src.ai_gateway.context_compressor import extractive_context_compressor
        
        cleaned_text, _ = token_economy.prune_disfluencies(request.text)
        if len(cleaned_text.split()) >= 40:
            cleaned_text, _ = extractive_context_compressor.compress_text(cleaned_text)

        prompt = EXTRACT_USER_TEMPLATE.format(
            text=cleaned_text,
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

        # 2. Guardrail de Sanitização e Correção Ortográfica de Entidades (spaCy)
        from src.ai_gateway.entity_sanitizer import entity_sanitizer
        raw_entities = parsed_data.get("entities", [])
        sanitized_entities_list = entity_sanitizer.sanitize_extracted_entities(raw_entities)

        # Normaliza tarefas, entidades, triplas semânticas e termos dúbios
        tasks = [ExtractedTask(**t) if isinstance(t, dict) else t for t in parsed_data.get("tasks", [])]
        entities = [ExtractedEntity(**e) if isinstance(e, dict) else e for e in sanitized_entities_list]
        raw_triples = parsed_data.get("triples", [])
        from src.ai_gateway.schemas import ExtractedTriple, UnclearTerm
        triples = [ExtractedTriple(**tr) if isinstance(tr, dict) else tr for tr in raw_triples if isinstance(tr, (dict, ExtractedTriple))]
        raw_unclear = parsed_data.get("unclear_terms", [])
        unclear_terms = [UnclearTerm(**u) if isinstance(u, dict) else u for u in raw_unclear if isinstance(u, (dict, UnclearTerm))]

        # Normaliza strings de decisions, ideas e topics caso a LLM retorne dicts
        def _to_string_list(items: Any) -> list[str]:
            if not isinstance(items, list):
                return []
            result: list[str] = []
            for item in items:
                if isinstance(item, str):
                    s = item.strip()
                    if s:
                        result.append(s)
                elif isinstance(item, dict):
                    # Se vier {"description": "...", "date": "..."}, extrai a descrição ou valores
                    desc = item.get("description") or item.get("title") or item.get("text") or item.get("decision") or item.get("idea")
                    if desc:
                        result.append(str(desc).strip())
                    else:
                        result.append(", ".join(f"{k}: {v}" for k, v in item.items() if v))
                elif item is not None:
                    result.append(str(item).strip())
            return result

        decisions = _to_string_list(parsed_data.get("decisions", []))
        ideas = _to_string_list(parsed_data.get("ideas", []))
        topics = _to_string_list(parsed_data.get("topics", []))

        return SemanticExtractionResponse(
            intent=parsed_data.get("intent", "NOTE"),
            summary=parsed_data.get("summary", request.text[:100]),
            sentiment=parsed_data.get("sentiment", "NEUTRAL"),
            sentiment_score=float(parsed_data.get("sentiment_score", 0.0) or 0.0),
            tasks=tasks,
            entities=entities,
            triples=triples,
            unclear_terms=unclear_terms,
            decisions=decisions,
            ideas=ideas,
            topics=topics,
            urgency=parsed_data.get("urgency", "MEDIUM"),
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            processing_time_ms=elapsed_ms,
        )


semantic_extractor = SemanticExtractor()
