"""Cache Semântico Local de Respostas para o Agente Hermes e RAG."""

import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


class CachedQueryItem(BaseModel):
    """Item armazenado no cache semântico."""
    query: str
    normalized_query: str
    response_data: Dict[str, Any]
    created_at: float
    ttl_seconds: float = 900.0  # 15 minutos padrão
    tokens_saved: int = 450


class SemanticResponseCache:
    """Cache semântico rápido em memória com expiração por TTL e correspondência fuzzy."""

    def __init__(self, default_ttl_seconds: float = 900.0, similarity_threshold: float = 94.0):
        self.default_ttl = default_ttl_seconds
        self.similarity_threshold = similarity_threshold
        self._cache: Dict[str, CachedQueryItem] = {}
        self.hits_count = 0
        self.misses_count = 0
        self.total_tokens_saved = 0

    def _normalize(self, text: str) -> str:
        """Normaliza espaços, caixa baixa e pontuação da consulta."""
        if not text:
            return ""
        clean = text.lower().strip().strip("\"'“”`.,;:?!")
        return " ".join(clean.split())

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        """Busca uma resposta em cache para a query utilizando similaridade fuzzy."""
        now = time.time()
        norm_query = self._normalize(query)
        if not norm_query or len(norm_query) < 4:
            self.misses_count += 1
            return None

        # 1. Checagem exata O(1)
        if norm_query in self._cache:
            item = self._cache[norm_query]
            if now - item.created_at <= item.ttl_seconds:
                self.hits_count += 1
                self.total_tokens_saved += item.tokens_saved
                logger.info(f"⚡ [Semantic Cache] Hit exato para: '{query}' ({item.tokens_saved} tokens poupados).")
                return item.response_data
            else:
                del self._cache[norm_query]

        # 2. Busca fuzzy de alta similaridade nos itens válidos
        expired_keys = []
        best_match_item = None
        highest_score = 0.0

        for key, item in self._cache.items():
            if now - item.created_at > item.ttl_seconds:
                expired_keys.append(key)
                continue

            score = fuzz.ratio(norm_query, item.normalized_query)
            if score >= self.similarity_threshold and score > highest_score:
                highest_score = score
                best_match_item = item

        # Limpa expirados
        for k in expired_keys:
            self._cache.pop(k, None)

        if best_match_item:
            self.hits_count += 1
            self.total_tokens_saved += best_match_item.tokens_saved
            logger.info(f"⚡ [Semantic Cache] Hit fuzzy ({highest_score:.1f}%) para: '{query}' -> '{best_match_item.query}' ({best_match_item.tokens_saved} tokens poupados).")
            return best_match_item.response_data

        self.misses_count += 1
        return None

    def set(self, query: str, response_data: Dict[str, Any], tokens_saved: int = 450, ttl_seconds: Optional[float] = None) -> None:
        """Armazena a resposta no cache semântico."""
        norm_query = self._normalize(query)
        if not norm_query or len(norm_query) < 4:
            return

        ttl = ttl_seconds or self.default_ttl
        self._cache[norm_query] = CachedQueryItem(
            query=query,
            normalized_query=norm_query,
            response_data=response_data,
            created_at=time.time(),
            ttl_seconds=ttl,
            tokens_saved=tokens_saved,
        )

    def clear(self) -> None:
        """Limpa todo o cache."""
        self._cache.clear()

    def get_metrics(self) -> Dict[str, Any]:
        """Retorna métricas de performance do cache e economia de tokens."""
        total_requests = self.hits_count + self.misses_count
        hit_ratio = (self.hits_count / total_requests) if total_requests > 0 else 0.0
        return {
            "cached_entries_count": len(self._cache),
            "hits_count": self.hits_count,
            "misses_count": self.misses_count,
            "hit_ratio_percent": round(hit_ratio * 100, 2),
            "total_tokens_saved": self.total_tokens_saved,
        }


semantic_cache = SemanticResponseCache()
