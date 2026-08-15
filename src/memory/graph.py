"""Camada de Grafo de Conhecimento e Relações com NetworkX."""

import json
import logging
import os
from typing import Any
import networkx as nx
from src.config import settings

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """Gerenciador do Grafo Relacional do Hermes em NetworkX."""

    def __init__(self, persistence_path: str = settings.GRAPH_PERSISTENCE_PATH):
        self.persistence_path = persistence_path
        self.graph = nx.DiGraph()
        self._load()

    def _load(self) -> None:
        """Carrega o grafo salvo do disco ou inicializa novo grafo."""
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.graph = nx.node_link_graph(data, edges="links")
                logger.info(f"Grafo de conhecimento carregado com {self.graph.number_of_nodes()} nós e {self.graph.number_of_edges()} conexões.")
                return
            except Exception as e:
                logger.warning(f"Erro ao carregar grafo de {self.persistence_path}: {e}. Criando novo grafo.")

        self.graph = nx.DiGraph()

    def _save(self) -> None:
        """Serializa o grafo para JSON."""
        try:
            os.makedirs(os.path.dirname(self.persistence_path) or ".", exist_ok=True)
            data = nx.node_link_data(self.graph, edges="links")
            with open(self.persistence_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar grafo de conhecimento: {e}")

    def add_node(self, name: str, category: str = "OTHER", **attrs) -> None:
        """Adiciona ou atualiza um nó no grafo."""
        name_clean = name.strip()
        if not name_clean:
            return
        if not self.graph.has_node(name_clean):
            self.graph.add_node(name_clean, category=category, mentions=1, **attrs)
        else:
            self.graph.nodes[name_clean]["mentions"] = self.graph.nodes[name_clean].get("mentions", 0) + 1
            if category != "OTHER":
                self.graph.nodes[name_clean]["category"] = category
            for k, v in attrs.items():
                self.graph.nodes[name_clean][k] = v
        self._save()

    def remove_node(self, name: str) -> bool:
        """Remove um nó do grafo e persiste."""
        name_clean = name.strip()
        if self.graph.has_node(name_clean):
            self.graph.remove_node(name_clean)
            self._save()
            return True
        return False

    def add_edge(self, source: str, target: str, relation: str = "RELATED_TO", weight: float = 1.0) -> None:
        """Adiciona ou incrementa uma aresta direcionada entre duas entidades."""
        src_clean = source.strip()
        tgt_clean = target.strip()
        if not src_clean or not tgt_clean or src_clean.lower() == tgt_clean.lower():
            return

        if not self.graph.has_node(src_clean):
            self.add_node(src_clean, category="CONCEPT")
        if not self.graph.has_node(tgt_clean):
            self.add_node(tgt_clean, category="CONCEPT")

        if self.graph.has_edge(src_clean, tgt_clean):
            self.graph[src_clean][tgt_clean]["weight"] = self.graph[src_clean][tgt_clean].get("weight", 1.0) + weight
            self.graph[src_clean][tgt_clean]["relation"] = relation
        else:
            self.graph.add_edge(src_clean, tgt_clean, relation=relation, weight=weight)
        self._save()

    def add_interaction(self, speaker: str, entities: list[dict], tasks: list[dict], intent: str) -> None:
        """Vincula entidades, tarefas e locutor em uma única interação de áudio/texto."""
        speaker_node = speaker or "user"
        self.add_node(speaker_node, category="PERSON")

        entity_names = []
        for ent in entities:
            name = ent.get("name", "").strip()
            cat = ent.get("category", "OTHER")
            if name:
                self.add_node(name, category=cat, details=ent.get("details"))
                self.add_edge(speaker_node, name, relation="MENTIONED")
                entity_names.append(name)

        # Conecta entidades mencionadas juntas no mesmo contexto
        for i in range(len(entity_names)):
            for j in range(i + 1, len(entity_names)):
                self.add_edge(entity_names[i], entity_names[j], relation="CO_OCCURRED")

        # Conecta tarefas aos seus responsáveis ou entidades
        for t in tasks:
            assignee = t.get("assignee")
            title = t.get("title", "")
            if assignee:
                self.add_node(assignee, category="PERSON")
                self.add_edge(speaker_node, assignee, relation="DELEGATED_TO")
                for ent_name in entity_names:
                    self.add_edge(assignee, ent_name, relation="ASSIGNED_WITH")

        self._save()

    def get_neighborhood(self, entity_name: str, depth: int = 1) -> dict[str, Any]:
        """Retorna subgrafo vizinho de uma entidade com suas conexões."""
        name_clean = entity_name.strip()
        if not self.graph.has_node(name_clean):
            return {"entity": name_clean, "found": False, "nodes": [], "edges": []}

        # Busca nós até o raio 'depth' (suporta grafo direcionado e reverso)
        sub_nodes = set([name_clean])
        current_layer = set([name_clean])
        undirected = self.graph.to_undirected()

        for _ in range(depth):
            next_layer = set()
            for n in current_layer:
                if undirected.has_node(n):
                    next_layer.update(undirected.neighbors(n))
            sub_nodes.update(next_layer)
            current_layer = next_layer

        nodes_data = []
        for n in sub_nodes:
            attrs = dict(self.graph.nodes[n])
            nodes_data.append({"id": n, **attrs})

        edges_data = []
        subgraph = self.graph.subgraph(sub_nodes)
        for u, v, attrs in subgraph.edges(data=True):
            edges_data.append({"source": u, "target": v, **attrs})

        return {
            "entity": name_clean,
            "found": True,
            "nodes": nodes_data,
            "edges": edges_data,
            "degree": self.graph.degree(name_clean) if self.graph.has_node(name_clean) else 0,
        }

    def list_nodes(self, category: str | None = None) -> list[dict]:
        """Lista todos os nós cadastrados no grafo."""
        results = []
        for n, attrs in self.graph.nodes(data=True):
            if category and attrs.get("category", "").upper() != category.upper():
                continue
            results.append({"name": n, **attrs, "degree": self.graph.degree(n)})
        return sorted(results, key=lambda x: x.get("mentions", 0), reverse=True)

    def stats(self) -> dict[str, int]:
        """Retorna contagem de nós e arestas."""
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
        }


knowledge_graph = KnowledgeGraph()
