"""Testes unitários para o Grafo de Conhecimento NetworkX."""

import pytest
from src.memory.graph import KnowledgeGraph


@pytest.fixture
def temp_graph(tmp_path):
    """Cria um KnowledgeGraph temporário para testes."""
    file_path = str(tmp_path / "test_graph.json")
    return KnowledgeGraph(persistence_path=file_path)


def test_add_nodes_and_edges(temp_graph):
    """Testa criação manual de nós e arestas no grafo."""
    temp_graph.add_node("Bruno", category="PERSON")
    temp_graph.add_node("Silo 3", category="EQUIPMENT")
    temp_graph.add_edge("Bruno", "Silo 3", relation="MONITORS")

    stats = temp_graph.stats()
    assert stats["nodes"] == 2
    assert stats["edges"] == 1


def test_add_interaction(temp_graph):
    """Testa vinculação automática de entidades e tarefas em uma interação."""
    entities = [
        {"name": "Silo 3", "category": "EQUIPMENT", "details": "Sensor ração"},
        {"name": "C.Vale", "category": "LOCATION"},
    ]
    tasks = [
        {"title": "Calibrar sensor", "assignee": "João"}
    ]

    temp_graph.add_interaction(
        speaker="Bruno",
        entities=entities,
        tasks=tasks,
        intent="TASK",
    )

    stats = temp_graph.stats()
    assert stats["nodes"] >= 4  # Bruno, Silo 3, C.Vale, João
    assert stats["edges"] >= 3


def test_get_neighborhood(temp_graph):
    """Testa a busca de subgrafo vizinho de uma entidade."""
    temp_graph.add_node("João", category="PERSON")
    temp_graph.add_node("Aviário 1", category="LOCATION")
    temp_graph.add_edge("João", "Aviário 1", relation="MANAGES")

    neighborhood = temp_graph.get_neighborhood("João", depth=1)
    assert neighborhood["found"] is True
    assert neighborhood["entity"] == "João"
    node_ids = [n["id"] for n in neighborhood["nodes"]]
    assert "João" in node_ids
    assert "Aviário 1" in node_ids


def test_get_neighborhood_not_found(temp_graph):
    """Verifica retorno para entidade inexistente."""
    result = temp_graph.get_neighborhood("Inexistente")
    assert result["found"] is False
    assert len(result["nodes"]) == 0
