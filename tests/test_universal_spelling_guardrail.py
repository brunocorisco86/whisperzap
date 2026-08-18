"""Testes automatizados para o Guardrail Universal de Ortografia e Bloqueio de Nós com Erros."""

import pytest
from src.ai_gateway.entity_sanitizer import entity_sanitizer
from src.memory.graph import KnowledgeGraph
from src.memory.janitor import GraphJanitorService


def test_universal_fuzzy_typo_correction():
    """Valida a correção fuzzy universal de qualquer erro de digitação com correspondência no léxico."""
    # 1. Erro de digitação em 'sensor'
    valid1, reason1, fixed1 = entity_sanitizer.is_valid_node_entity("senosr", "EQUIPMENT")
    assert valid1 is True
    assert fixed1 == "Sensor"

    # 2. Erro de digitação em 'relatório'
    valid2, reason2, fixed2 = entity_sanitizer.is_valid_node_entity("realtorio", "CONCEPT")
    assert valid2 is True
    assert fixed2 == "Relatório"

    # 3. Erro com dígrafo invertido 'fihlos'
    valid3, reason3, fixed3 = entity_sanitizer.is_valid_node_entity("fihlos", "CONCEPT")
    assert valid3 is True
    assert fixed3 == "Filhos"

    # 4. Erro de digitação em 'abatedouro'
    valid4, reason4, fixed4 = entity_sanitizer.is_valid_node_entity("abateodouro", "LOCATION")
    assert valid4 is True
    assert fixed4 == "Abatedouro"


def test_strict_node_blocking_on_unresolvable_errors(tmp_path):
    """Garante que qualquer palavra com erro não resolvível ou lixo léxico NÃO cria nó no grafo."""
    test_graph_file = str(tmp_path / "test_strict_graph.json")
    kg = KnowledgeGraph(persistence_path=test_graph_file)

    # 1. Tenta adicionar sequências inválidas/sem vogal/keyboard mash
    kg.add_node("xyzt", category="CONCEPT")
    kg.add_node("asdfgh", category="CONCEPT")
    kg.add_node("fihlx", category="CONCEPT")
    kg.add_node("bbbb_quebrado", category="OTHER")

    # Grafo deve continuar vazio (0 nós criados)
    assert kg.graph.number_of_nodes() == 0
    assert not kg.graph.has_node("xyzt")
    assert not kg.graph.has_node("asdfgh")
    assert not kg.graph.has_node("fihlx")

    # 2. Tenta criar aresta com nó inválido
    kg.add_edge("Bruno Conter", "asdfgh", relation="TESTED")
    assert not kg.graph.has_node("asdfgh")

    # 3. Adiciona termo legítimo com typo resolvível (deve criar nó corrigido)
    kg.add_node("senosr", category="EQUIPMENT")
    assert kg.graph.has_node("Sensor")
    assert not kg.graph.has_node("senosr")


def test_janitor_purges_legacy_orthographic_errors(tmp_path):
    """Garante que a Zeladora remove nós pré-existentes que contenham erros ortográficos não resolvíveis."""
    test_graph_file = str(tmp_path / "test_janitor_errors.json")
    kg = KnowledgeGraph(persistence_path=test_graph_file)

    # Insere diretamente ruídos brutos legados
    kg.graph.add_node("asdfgh", category="CONCEPT", mentions=1)
    kg.graph.add_node("xyzt", category="CONCEPT", mentions=1)
    kg.graph.add_node("Silo", category="EQUIPMENT", mentions=5)

    janitor = GraphJanitorService(kg=kg, history_path=str(tmp_path / "history.json"))
    report = janitor.clean_graph(dry_run=False, prune_isolated=False, deduplicate_aliases=False, purge_orphan_messages=False)

    # Nós com erro foram podados
    assert not kg.graph.has_node("asdfgh")
    assert not kg.graph.has_node("xyzt")
    # Nó legítimo preservado
    assert kg.graph.has_node("Silo")
    assert "asdfgh" in report.pruned_nodes or report.nodes_pruned_count >= 2
