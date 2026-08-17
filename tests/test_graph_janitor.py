"""Testes automatizados para o Agente Zeladora (Graph Janitor) e Faxina no Grafo."""

import pytest
import os
from fastapi.testclient import TestClient

from src.main import app
from src.memory.graph import KnowledgeGraph
from src.memory.janitor import GraphJanitorService
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.memory.models import Base
from src.contacts.models import ContactRecord

client = TestClient(app)


@pytest.fixture
def test_db():
    """Cria uma base SQLite isolada em memória para testes."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def temp_graph(tmp_path):
    """Cria uma instância isolada do KnowledgeGraph em diretório temporário."""
    path = str(tmp_path / "test_janitor_graph.json")
    history_path = str(tmp_path / "test_janitor_history.json")
    kg = KnowledgeGraph(persistence_path=path)
    janitor = GraphJanitorService(kg=kg, history_path=history_path)
    return kg, janitor


def test_janitor_protects_sacred_nodes_and_contacts(temp_graph, test_db):
    """Garante que contatos oficiais e nós de alta relevância nunca são excluídos."""
    kg, janitor = temp_graph

    # Cria contato no banco isolado
    c = ContactRecord(id="c-test-1", name="Debora Patel", role="Produtora Rural", company="Granja Patel")
    test_db.add(c)
    test_db.commit()

    # Adiciona nós sagrados e ruídos
    kg.add_node("Debora Patel", category="PERSON")
    kg.add_node("C.Vale", category="COMPANY")
    kg.add_node("Projeto Silos IoT", category="PROJECT")
    kg.add_node("amanhã", category="OTHER")  # Ruído efêmero
    kg.add_node("áudio", category="OTHER")   # Ruído efêmero
    kg.add_node("órfão sem conexões", category="OTHER")  # Isolado

    report = janitor.clean_graph(dry_run=False, db=test_db)

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


def test_janitor_purges_orphan_messages_and_audios(temp_graph, test_db):
    """Garante que a Zeladora purga mensagens e áudios de contatos sem cartão salvo na tabela contacts."""
    kg, janitor = temp_graph

    from src.memory.models import MessageRecord
    from src.contacts.models import ContactRecord

    # 1. Cria contatos com cartão
    c1 = ContactRecord(id="c-bruno-test", name="Bruno Conter", phone_number="554497604925", role="OWNER")
    c2 = ContactRecord(id="c-debora-test", name="Debora Patel Conter", phone_number="5544999214934", role="FAMILY_CORE")
    test_db.add_all([c1, c2])
    test_db.commit()

    # 2. Cria mensagens de contatos com cartão e mensagens de contatos sem cartão (órfãos)
    m_owner = MessageRecord(id="m-1", speaker="Bruno Conter", raw_text="Nota pessoal", revised_text="Nota pessoal")
    m_debora = MessageRecord(id="m-2", speaker="Debora Patel Conter", raw_text="Oi amor", revised_text="Oi amor")
    m_orphan1 = MessageRecord(id="m-3", speaker="Desconhecido Sem Card", raw_text="Spam ou teste", revised_text="Spam ou teste")
    m_orphan2 = MessageRecord(id="m-4", speaker="Gueguis Lanches", raw_text="Cardápio", revised_text="Cardápio")

    test_db.add_all([m_owner, m_debora, m_orphan1, m_orphan2])
    test_db.commit()

    # 3. Executa a purga da Zeladora
    res = janitor.purge_orphan_messages_and_audios(dry_run=False, db=test_db)
    assert res["purged_messages_count"] == 2
    assert "Desconhecido Sem Card" in res["purged_speakers"]
    assert "Gueguis Lanches" in res["purged_speakers"]

    # 4. Verifica que apenas mensagens de contatos com cartão e do dono foram mantidas
    remaining = test_db.query(MessageRecord).filter(MessageRecord.id.in_(["m-1", "m-2", "m-3", "m-4"])).all()
    rem_speakers = {r.speaker for r in remaining}
    assert len(remaining) == 2
    assert "Bruno Conter" in rem_speakers
    assert "Debora Patel Conter" in rem_speakers
    assert "Desconhecido Sem Card" not in rem_speakers
    assert "Gueguis Lanches" not in rem_speakers
