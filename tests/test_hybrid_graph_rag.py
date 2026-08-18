"""Testes automatizados para o GraphRAG Híbrido (pgvector + NetworkX 2-Hop + spaCy)."""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.memory.hybrid_graph_rag import hybrid_graph_rag
from src.memory.graph import KnowledgeGraph

client = TestClient(app)


def test_extract_query_entities_with_spacy():
    """Valida a extração de entidades e termos centrais da pergunta do usuário."""
    query = "Como está o sensor de pressão do Silo 3 do Valdecir na Granja São José?"
    entities = hybrid_graph_rag.extract_query_entities(query)

    assert len(entities) >= 2
    # Pelo menos Valdecir, Silo 3 ou Granja São José identificados
    entities_lower = [e.lower() for e in entities]
    assert any("valdecir" in e or "silo" in e or "granja" in e or "pressão" in e for e in entities_lower)


def test_2_hop_subgraph_expansion(tmp_path):
    """Garante que a expansão topológica de 2 saltos conecta a cadeia relacional completa."""
    test_graph_file = str(tmp_path / "test_hybrid_graph.json")
    kg = KnowledgeGraph(persistence_path=test_graph_file)

    # Monta a topologia: Valdecir -> Granja São José -> Aviário 4 -> Silo 3
    kg.add_node("Valdecir", category="PERSON", role="Zootecnista", phone="44999991234")
    kg.add_node("Granja São José", category="LOCATION")
    kg.add_node("Aviário 4", category="LOCATION")
    kg.add_node("Silo 3", category="EQUIPMENT")

    kg.add_edge("Valdecir", "Granja São José", relation="SUPERVISIONA")
    kg.add_edge("Granja São José", "Aviário 4", relation="CONTAINS")
    kg.add_edge("Aviário 4", "Silo 3", relation="EQUIPMENT")

    # Injeta o grafo de teste no hybrid_graph_rag
    original_kg = hybrid_graph_rag.kg
    try:
        hybrid_graph_rag.kg = kg

        # Busca por 'Valdecir' com 2 saltos
        result_2_hop = hybrid_graph_rag.expand_subgraph_2_hop(["Valdecir"], max_hops=2)

        assert "Valdecir" in result_2_hop["matched_seeds"]
        assert "Granja São José" in result_2_hop["subgraph_nodes"]
        assert "Aviário 4" in result_2_hop["subgraph_nodes"]
        assert result_2_hop["total_nodes"] >= 3
        assert len(result_2_hop["triples"]) >= 2

        # Valida formato das triplas
        assert any("Valdecir -[SUPERVISIONA]-> Granja São José" in t for t in result_2_hop["triples"])
        assert any("Granja São José -[CONTAINS]-> Aviário 4" in t for t in result_2_hop["triples"])
    finally:
        hybrid_graph_rag.kg = original_kg


def test_fusion_and_vector_graph_boost():
    """Valida o re-ranqueamento semântico com boost de similaridade para fontes correlacionadas ao subgrafo."""
    vector_sources = [
        {"id": "msg_1", "text": "O Valdecir solicitou revisão do silo.", "similarity": 0.75},
        {"id": "msg_2", "text": "Boa tarde pessoal tudo bem?", "similarity": 0.78},
    ]

    subgraph_data = {
        "subgraph_nodes": ["Valdecir", "Silo"],
        "node_details": ["Entidade: Valdecir | Cargo: Zootecnista"],
        "triples": ["Valdecir -[RESPONSIBLE_FOR]-> Silo"],
        "total_nodes": 2,
        "total_edges": 1,
        "matched_seeds": ["Valdecir"],
    }

    fused = hybrid_graph_rag.fuse_vector_and_graph_results(
        vector_sources=vector_sources,
        subgraph_data=subgraph_data,
        pending_tasks=["Calibrar sensor"],
    )

    # msg_1 deve receber boost por citar Valdecir/Silo
    top_source = fused["sources"][0]
    assert top_source["id"] == "msg_1"
    assert top_source["graph_reinforced"] is True
    assert top_source["similarity"] > 0.85


def test_hybrid_search_api_endpoint():
    """Testa o endpoint POST /api/v1/memory/graph/hybrid-search."""
    response = client.post("/api/v1/memory/graph/hybrid-search?query=Como está o Silo do Valdecir?&max_hops=2")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Como está o Silo do Valdecir?"
    assert isinstance(data["extracted_entities"], list)
    assert isinstance(data["subgraph"], dict)
