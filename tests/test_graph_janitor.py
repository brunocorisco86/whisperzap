"""Testes automatizados para o Agente Zeladora (Graph Janitor) e Faxina no Grafo."""

import pytest
import os
from fastapi.testclient import TestClient

from src.main import app
from src.memory.graph import KnowledgeGraph
from src.memory.janitor import GraphJanitorService
from src.memory.database import SessionLocal, init_db
from src.contacts.models import ContactRecord

client = TestClient(app)


@pytest.fixture
def temp_graph(tmp_path):
    """Cria uma instância isolada do KnowledgeGraph em diretório temporário."""
    path = str(tmp_path / "test_janitor_graph.json")
    history_path = str(tmp_path / "test_janitor_history.json")
    kg = KnowledgeGraph(persistence_path=path)
    janitor = GraphJanitorService(kg=kg, history_path=history_path)
    return kg, janitor


def test_janitor_protects_sacred_nodes_and_contacts(temp_graph):
    """Garante que contatos oficiais e nós de alta relevância nunca são excluídos."""
    kg, janitor = temp_graph
    init_db()

    # Cria contato no banco
    db = SessionLocal()
    try:
        c = ContactRecord(id="c-test-1", name="Debora Patel", role="Produtora Rural", company="Granja Patel")
        db.merge(c)
        db.commit()
    finally:
        db.close()

    # Adiciona nós sagrados e ruídos
    kg.add_node("Debora Patel", category="PERSON")
    kg.add_node("C.Vale", category="COMPANY")
    kg.add_node("Projeto Silos IoT", category="PROJECT")
    kg.add_node("amanhã", category="OTHER")  # Ruído efêmero
    kg.add_node("áudio", category="OTHER")   # Ruído efêmero
    kg.add_node("órfão sem conexões", category="OTHER")  # Isolado

    report = janitor.clean_graph(dry_run=False)

    # Verifica que ruídos foram podados
    assert not kg.graph.has_node("amanhã")
    assert not kg.graph.has_node("áudio")
    assert not kg.graph.has_node("órfão sem conexões")

    # Verifica que nós sagrados foram preservados
    assert kg.graph.has_node("Debora Patel")
    assert kg.graph.has_node("C.Vale")
    assert kg.graph.has_node("Projeto Silos IoT")
    assert report.nodes_pruned_count >= 3


def test_janitor_merges_alias_nodes(temp_graph):
    """Testa a desambiguação e fusão de variações quase-idênticas transferindo conexões."""
    kg, janitor = temp_graph

    # Cria nós com pequenas diferenças de grafia
    kg.add_node("Silo 3", category="FACILITY")
    kg.add_node("silo 3", category="OTHER")
    kg.add_edge("Bruno Conter", "silo 3", relation="INSPECTED")
    kg.add_edge("Silo 3", "C.Vale", relation="LOCATED_AT")

    report = janitor.clean_graph(dry_run=False, deduplicate_aliases=True)

    # 'silo 3' deve ter sido fundido em 'Silo 3'
    assert kg.graph.has_node("Silo 3")
    assert not kg.graph.has_node("silo 3")
    assert kg.graph.has_edge("Bruno Conter", "Silo 3")
    assert kg.graph.has_edge("Silo 3", "C.Vale")
    assert report.nodes_merged_count >= 1


def test_janitor_dry_run_does_not_modify_graph(temp_graph):
    """Testa se a opção dry_run calcula o relatório sem alterar o grafo no disco."""
    kg, janitor = temp_graph

    kg.add_node("amanhã", category="OTHER")
    kg.add_node("C.Vale", category="COMPANY")

    report = janitor.clean_graph(dry_run=True)

    assert report.dry_run is True
    assert "amanhã" in report.pruned_nodes
    # Grafo não foi alterado
    assert kg.graph.has_node("amanhã")


def test_janitor_api_endpoints():
    """Testa as rotas HTTP POST /api/v1/memory/graph/clean e GET /api/v1/memory/graph/janitor/logs."""
    res_clean = client.post("/api/v1/memory/graph/clean?dry_run=true")
    assert res_clean.status_code == 200
    data = res_clean.json()
    assert "nodes_before" in data
    assert "nodes_pruned_count" in data
    assert "summary" in data

    res_logs = client.get("/api/v1/memory/graph/janitor/logs")
    assert res_logs.status_code == 200
    assert isinstance(res_logs.json(), list)
