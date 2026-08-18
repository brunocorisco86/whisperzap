"""Motor de GraphRAG Híbrido: Fusão de Busca Vetorial (pgvector) com Topologia Relacional (NetworkX 2-Hop) e spaCy."""

import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict
import networkx as nx

from src.memory.graph import knowledge_graph
from src.memory.task_sentiment_analyzer import get_spacy_nlp

logger = logging.getLogger(__name__)


class HybridGraphRAGService:
    """Serviço de Recuperação Híbrida em Grafo e Vetores (GraphRAG)."""

    def __init__(self):
        self.nlp = get_spacy_nlp()
        self.kg = knowledge_graph

    def extract_query_entities(self, query: str) -> List[str]:
        """Extrai entidades nomeadas, siglas e sintagmas nominais da pergunta usando spaCy."""
        if not query or not self.nlp:
            return []

        doc = self.nlp(query)
        entities: Set[str] = set()

        # 1. Entidades nomeadas formais
        for ent in doc.ents:
            clean = ent.text.strip().strip("\"'“”`.,;:")
            if len(clean) > 2 and clean.lower() not in ("como", "qual", "quem", "onde", "quando", "porque", "sobre"):
                entities.add(clean)

        # 2. Sintagmas nominais relevantes
        for chunk in doc.noun_chunks:
            chunk_clean = chunk.text.strip().strip("\"'“”`.,;:")
            words = chunk_clean.split()
            # Ignora pronomes interrogativos e artigos puros
            if len(chunk_clean) > 3 and not any(w.lower() in ("o", "a", "os", "as", "um", "uma", "esse", "esta", "isso") and len(words) == 1 for w in words):
                entities.add(chunk_clean)

        # 3. Siglas e termos em maiúsculas (ex: TMS, FAL, BRIM, FMIM, Silo 3)
        for token in doc:
            t = token.text.strip()
            if (t.isupper() and len(t) in (2, 3, 4, 5)) or (t.istitle() and len(t) > 3):
                entities.add(t)

        return list(entities)

    def expand_subgraph_2_hop(self, seed_entities: List[str], max_hops: int = 2) -> Dict[str, Any]:
        """Realiza a expansão topológica de 2 saltos no NetworkX a partir das entidades semente."""
        g = self.kg.graph
        if not g or g.number_of_nodes() == 0 or not seed_entities:
            return {
                "matched_nodes": [],
                "subgraph_nodes": [],
                "triples": [],
                "node_details": [],
                "total_nodes": 0,
                "total_edges": 0,
            }

        matched_seeds: Set[str] = set()
        subgraph_nodes: Set[str] = set()
        subgraph_edges: List[Tuple[str, str, Dict[str, Any]]] = []

        all_nodes_lower = {str(n).lower(): n for n in g.nodes()}

        # 1. Encontra nós correspondentes às entidades semente
        for seed in seed_entities:
            s_lower = seed.lower()
            if s_lower in all_nodes_lower:
                canonical_node = all_nodes_lower[s_lower]
                matched_seeds.add(canonical_node)
                subgraph_nodes.add(canonical_node)
            else:
                # Busca parcial / substring
                for n_low, n_orig in all_nodes_lower.items():
                    if s_lower in n_low or n_low in s_lower:
                        matched_seeds.add(n_orig)
                        subgraph_nodes.add(n_orig)

        # 2. Expansão em BFS até max_hops (padrão: 2 graus de distância)
        current_frontier = set(matched_seeds)
        visited = set(matched_seeds)

        for hop in range(max_hops):
            next_frontier = set()
            for node in current_frontier:
                # Vizinhos de saída e entrada (grafo direcionado)
                neighbors = set(g.successors(node)).union(set(g.predecessors(node)))
                for neighbor in neighbors:
                    subgraph_nodes.add(neighbor)
                    if neighbor not in visited:
                        next_frontier.add(neighbor)
                        visited.add(neighbor)
            current_frontier = next_frontier
            if not current_frontier:
                break

        # 3. Coleta arestas e triplas semânticas do subgrafo induzido
        triples_formatted: List[str] = []
        node_details_formatted: List[str] = []

        subgraph_view = g.subgraph(subgraph_nodes)
        for u, v, data in subgraph_view.edges(data=True):
            relation = data.get("relation", "RELATED_TO")
            weight = data.get("weight", 1.0)
            triples_formatted.append(f"{u} -[{relation}]-> {v}")

        # 4. Formata metadados ricos dos nós do subgrafo
        for node in subgraph_nodes:
            attrs = g.nodes[node]
            parts = [f"Entidade: {node}"]
            if attrs.get("category"):
                parts.append(f"Categoria: {attrs['category']}")
            if attrs.get("role"):
                parts.append(f"Cargo: {attrs['role']}")
            if attrs.get("phone"):
                parts.append(f"Telefone: {attrs['phone']}")
            if attrs.get("company"):
                parts.append(f"Empresa: {attrs['company']}")
            if attrs.get("details"):
                parts.append(f"Info: {attrs['details']}")
            node_details_formatted.append(" | ".join(parts))

        return {
            "matched_seeds": list(matched_seeds),
            "subgraph_nodes": list(subgraph_nodes),
            "triples": triples_formatted,
            "node_details": node_details_formatted,
            "total_nodes": len(subgraph_nodes),
            "total_edges": len(triples_formatted),
        }

    def fuse_vector_and_graph_results(
        self,
        vector_sources: List[Dict[str, Any]],
        subgraph_data: Dict[str, Any],
        pending_tasks: List[str],
    ) -> Dict[str, Any]:
        """Funde fontes vetoriais, subgrafo de 2 saltos e tarefas com re-ranqueamento semântico."""
        subgraph_nodes_lower = {str(n).lower() for n in subgraph_data.get("subgraph_nodes", [])}

        # Aplica boost de relevância em fontes vetoriais que citam nós do subgrafo
        boosted_sources = []
        for src in vector_sources:
            if isinstance(src, dict):
                text = src.get("text") or src.get("text_snippet") or ""
                sim = src.get("similarity", 0.70)
            else:
                text = getattr(src, "text_snippet", "") or getattr(src, "text", "") or ""
                sim = getattr(src, "similarity", 0.70)

            text_lower = str(text).lower()
            matches_graph = any(n in text_lower for n in subgraph_nodes_lower if len(n) > 2)
            
            if isinstance(src, dict):
                src_copy = dict(src)
                if matches_graph:
                    src_copy["similarity"] = min(0.99, sim + 0.15)
                    src_copy["graph_reinforced"] = True
                else:
                    src_copy["graph_reinforced"] = False
                boosted_sources.append(src_copy)
            else:
                if matches_graph:
                    src.similarity = min(0.99, sim + 0.15)
                boosted_sources.append(src)

        # Ordena fontes com boost
        boosted_sources.sort(
            key=lambda s: s.get("similarity", 0) if isinstance(s, dict) else getattr(s, "similarity", 0),
            reverse=True,
        )

        return {
            "sources": boosted_sources,
            "related_entities": subgraph_data.get("node_details", []),
            "triples": subgraph_data.get("triples", []),
            "pending_tasks": pending_tasks,
            "subgraph_summary": {
                "nodes_count": subgraph_data.get("total_nodes", 0),
                "edges_count": subgraph_data.get("total_edges", 0),
                "matched_seeds": subgraph_data.get("matched_seeds", []),
            },
        }


hybrid_graph_rag = HybridGraphRAGService()
