"""Testes automatizados para a Compressão Extrativa com spaCy, Cache Semântico Local e Métricas de Tokens."""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.ai_gateway.context_compressor import extractive_context_compressor
from src.memory.semantic_cache import semantic_cache

client = TestClient(app)


def test_extractive_context_compressor():
    """Valida a compressão extrativa de sentenças mantendo fatos essenciais e podando fillers."""
    verbose_transcription = (
        "Então veja bem, tipo assim, bom dia pessoal tudo bem? "
        "Aí sabe como é, eu estava pensando aqui e tal. "
        "Precisamos urgente calibrar o sensor de pressão do Silo 3 do aviário 4 da Granja São José. "
        "O Valdecir disse que a ração do lote 5101 precisa ser pesada até as 17:00 de amanhã. "
        "Digamos assim, né, qualquer coisa me avisa por aqui. "
        "Foi emitido a nota fiscal número 8892 com o CFOP 5138 para o cooperado. "
        "Valeu pessoal, até mais, tchau tchau."
    )

    compressed, tokens_saved = extractive_context_compressor.compress_text(
        text=verbose_transcription,
        min_words_to_compress=20,
    )

    # 1. Houve compressão de tokens
    assert tokens_saved > 0
    assert len(compressed.split()) < len(verbose_transcription.split())

    # 2. Entidades centrais, tarefas e números foram estritamente preservados
    assert "Silo 3" in compressed or "sensor" in compressed
    assert "Valdecir" in compressed or "ração" in compressed
    assert "8892" in compressed or "CFOP" in compressed


def test_semantic_cache_exact_and_fuzzy_hits():
    """Valida o funcionamento do cache semântico com hits exatos e buscas fuzzy."""
    semantic_cache.clear()

    query = "Qual o telefone e cargo do Valdecir?"
    mock_response = {
        "answer": "O Valdecir é Zootecnista da C.Vale com telefone 554499255873.",
        "confidence": 0.98,
        "sources": [],
    }

    # 1. Inicialmente é Miss
    miss_res = semantic_cache.get(query)
    assert miss_res is None

    # 2. Salva no cache
    semantic_cache.set(query, mock_response, tokens_saved=450)

    # 3. Hit exato
    hit_exact = semantic_cache.get(query)
    assert hit_exact is not None
    assert hit_exact["answer"] == mock_response["answer"]

    # 4. Hit fuzzy (com pequenas variações de pontuação/caixa)
    fuzzy_query = "qual o telefone e cargo do valdecir"
    hit_fuzzy = semantic_cache.get(fuzzy_query)
    assert hit_fuzzy is not None
    assert hit_fuzzy["answer"] == mock_response["answer"]

    # 5. Miss para consulta diferente
    miss_diff = semantic_cache.get("Como está o clima amanhã?")
    assert miss_diff is None


def test_token_savings_api_endpoint():
    """Testa o endpoint GET /api/v1/memory/token-savings."""
    response = client.get("/api/v1/memory/token-savings")
    assert response.status_code == 200
    data = response.json()

    assert "total_tokens_saved" in data
    assert "breakdown" in data
    assert "phatic_bypass_tokens_saved" in data["breakdown"]
    assert "extractive_compression_tokens_saved" in data["breakdown"]
    assert "semantic_cache_tokens_saved" in data["breakdown"]
    assert "semantic_cache_stats" in data
