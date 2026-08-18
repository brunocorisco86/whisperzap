"""Testes automatizados para o Guardrail de Sanitização, NetworkX Enhancer e Economia de Tokens com spaCy."""

import pytest
import os
import shutil
from src.ai_gateway.entity_sanitizer import entity_sanitizer
from src.memory.graph_enhancer import graph_enhancer
from src.ai_gateway.token_economy import token_economy
from src.ai_gateway.bypass import should_bypass_ai
from src.memory.graph import KnowledgeGraph
from src.memory.janitor import GraphJanitorService


def test_entity_sanitizer_guardrails():
    """Valida a correção de erros ortográficos, casing e alucinações fonéticas."""
    # 1. Correção ortográfica de typos
    name1, cat1, mod1 = entity_sanitizer.sanitize_entity_name("Fihlos", "CONCEPT")
    assert name1 == "Filhos"
    assert mod1 is True

    name2, cat2, mod2 = entity_sanitizer.sanitize_entity_name("abateodouro", "LOCATION")
    assert name2 == "Abatedouro"
    assert mod2 is True

    # 2. Correção de alucinações fonéticas do Whisper
    name3, cat3, mod3 = entity_sanitizer.sanitize_entity_name("Macau", "LOCATION")
    assert name3 == "Call"
    assert cat3 == "CONCEPT"
    assert mod3 is True

    name4, cat4, mod4 = entity_sanitizer.sanitize_entity_name("cvale", "COMPANY")
    assert name4 == "C.Vale"
    assert mod4 is True

    # 3. Lematização de plural para singular em equipamentos
    name5, cat5, mod5 = entity_sanitizer.sanitize_entity_name("Sensores", "EQUIPMENT")
    assert name5 == "Sensor"
    assert mod5 is True


def test_graph_enhancer_compound_and_instances():
    """Valida a simplificação de termos compostos e detecção de instâncias."""
    # 1. Termo composto de equipamento
    can1, parent1 = graph_enhancer.simplify_compound_node("Sensores de Silos")
    assert can1 == "Sensor de Silo"

    # 2. Instância específica com identificador numérico
    can2, parent2 = graph_enhancer.simplify_compound_node("Silo 3")
    assert can2 == "Silo 3"
    assert parent2 == "Silo"

    can3, parent3 = graph_enhancer.simplify_compound_node("Aviário 4")
    assert can3 == "Aviário 4"
    assert parent3 == "Aviário"


def test_token_economy_phatic_bypass_and_disfluencies():
    """Valida a detecção de mensagens fáticas e poda de disfluências."""
    # 1. Mensagens sociais / fáticas (0 tokens gastos)
    assert token_economy.is_phatic_or_trivial("Bom dia")[0] is True
    assert token_economy.is_phatic_or_trivial("Olá, tudo bem?")[0] is True
    assert token_economy.is_phatic_or_trivial("Valeu, obrigado!")[0] is True
    assert token_economy.is_phatic_or_trivial("Ok, beleza")[0] is True

    # Mensagem substantiva não deve fazer bypass
    assert token_economy.is_phatic_or_trivial("Lembrar de calibrar o sensor do silo 3 amanhã")[0] is False

    # 2. Verificação integrada no should_bypass_ai
    bypass_active, bypass_reason = should_bypass_ai("Bom dia")
    assert bypass_active is True
    assert "token_economy" in bypass_reason or "trivial" in bypass_reason

    # 3. Poda de disfluências e repetições de gagueira do áudio
    raw_audio_text = "Então tipo assim né, vamos vamos calibrar o o sensor de temperatura."
    cleaned, words_saved = token_economy.prune_disfluencies(raw_audio_text)
    assert "tipo assim" not in cleaned
    assert "vamos vamos" not in cleaned
    assert "o o" not in cleaned
    assert words_saved > 0


def test_knowledge_graph_sanitized_insertion_and_linking(tmp_path):
    """Valida que o KnowledgeGraph insere apenas nós sanitizados e conecta instâncias."""
    test_graph_file = str(tmp_path / "test_graph.json")
    kg = KnowledgeGraph(persistence_path=test_graph_file)

    # 1. Adiciona nó com erro ortográfico 'Fihlos' (sanitizado para Filhos e lematizado para Filho)
    kg.add_node("Fihlos", category="CONCEPT")
    assert kg.graph.has_node("Filho")
    assert not kg.graph.has_node("Fihlos")

    # 2. Adiciona instância 'Silo 3'
    kg.add_node("Silo 3", category="EQUIPMENT")
    assert kg.graph.has_node("Silo 3")
    assert kg.graph.has_node("Silo")
    assert kg.graph.has_edge("Silo 3", "Silo")
    assert kg.graph["Silo 3"]["Silo"]["relation"] == "INSTANCE_OF"

    # 3. Adiciona aresta entre 'Macau' e 'João'
    kg.add_edge("Macau", "João", relation="PARTICIPATED")
    assert kg.graph.has_node("Call")
    assert kg.graph.has_edge("Call", "João")


def test_graph_janitor_with_spacy_enhancer(tmp_path):
    """Valida que a Zeladora utiliza o spaCy para fundir nós redundantes e corrigir typos históricos."""
    test_graph_file = str(tmp_path / "test_janitor_graph.json")
    kg = KnowledgeGraph(persistence_path=test_graph_file)

    # Popula o grafo diretamente com ruídos e typos antigos
    kg.graph.add_node("Fihlos", category="CONCEPT", mentions=2)
    kg.graph.add_node("Filho", category="CONCEPT", mentions=5)
    kg.graph.add_node("Sensores de Silos", category="EQUIPMENT", mentions=1)
    kg.graph.add_edge("Bruno Conter", "Fihlos", relation="MENTIONED")
    kg.graph.add_edge("Bruno Conter", "Sensores de Silos", relation="MENTIONED")

    janitor = GraphJanitorService(kg=kg, history_path=str(tmp_path / "janitor_history.json"))
    report = janitor.clean_graph(dry_run=False, prune_isolated=False, deduplicate_aliases=True, purge_orphan_messages=False)

    # Verifica fusões
    assert kg.graph.has_node("Filho")
    assert not kg.graph.has_node("Fihlos")
    # Aresta transferida
    assert kg.graph.has_edge("Bruno Conter", "Filho")
    assert report.nodes_merged_count >= 1
