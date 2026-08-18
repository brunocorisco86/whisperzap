"""Camada de Grafo de Conhecimento e Relações com NetworkX."""

import json
import logging
import os
import threading
from typing import Any
import networkx as nx
from src.config import settings

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """Gerenciador do Grafo Relacional do Hermes em NetworkX (Thread-Safe)."""

    def __init__(self, persistence_path: str = settings.GRAPH_PERSISTENCE_PATH):
        self.persistence_path = persistence_path
        self.graph = nx.DiGraph()
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        """Carrega o grafo salvo do disco ou inicializa novo grafo."""
        with self._lock:
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
        """Serializa o grafo para JSON de forma atômica e thread-safe."""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.persistence_path) or ".", exist_ok=True)
                data = nx.node_link_data(self.graph, edges="links")
                # Escreve via arquivo temporário para escrita atômica no filesystem
                tmp_path = f"{self.persistence_path}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.persistence_path)
            except Exception as e:
                logger.error(f"Erro ao salvar grafo de conhecimento: {e}")

    def add_node(self, name: str, category: str = "OTHER", **attrs) -> None:
        """Adiciona ou atualiza um nó no grafo de forma thread-safe com sanitização e canonicidade."""
        from src.ai_gateway.entity_sanitizer import entity_sanitizer
        from src.memory.graph_enhancer import graph_enhancer

        # 1. Sanitização de erros ortográficos e alucinações
        clean_name, clean_cat, _ = entity_sanitizer.sanitize_entity_name(name, category)
        if not clean_name:
            return

        with self._lock:
            # 2. Simplificação de compostas e busca de canônicos
            existing_node_names = set(self.graph.nodes())
            canonical_name, parent_concept = graph_enhancer.simplify_compound_node(clean_name, existing_node_names)
            final_name = canonical_name or clean_name

            if not self.graph.has_node(final_name):
                self.graph.add_node(final_name, category=clean_cat, mentions=1, **attrs)
            else:
                self.graph.nodes[final_name]["mentions"] = self.graph.nodes[final_name].get("mentions", 0) + 1
                if clean_cat != "OTHER":
                    self.graph.nodes[final_name]["category"] = clean_cat
                for k, v in attrs.items():
                    self.graph.nodes[final_name][k] = v

            # Se for uma instância específica com pai (ex: 'Silo 3' -> 'Silo'), conecta hierarquicamente
            if parent_concept and parent_concept != final_name:
                if not self.graph.has_node(parent_concept):
                    self.graph.add_node(parent_concept, category=clean_cat, mentions=1)
                if not self.graph.has_edge(final_name, parent_concept):
                    self.graph.add_edge(final_name, parent_concept, relation="INSTANCE_OF", weight=1.5)

            self._save()

    def remove_node(self, name: str) -> bool:
        """Remove um nó do grafo e persiste de forma thread-safe."""
        with self._lock:
            name_clean = name.strip()
            if self.graph.has_node(name_clean):
                self.graph.remove_node(name_clean)
                self._save()
                return True
            return False

    def add_edge(self, source: str, target: str, relation: str = "RELATED_TO", weight: float = 1.0) -> None:
        """Adiciona ou incrementa uma aresta direcionada entre duas entidades de forma thread-safe."""
        from src.ai_gateway.entity_sanitizer import entity_sanitizer
        from src.memory.graph_enhancer import graph_enhancer

        src_clean, _, _ = entity_sanitizer.sanitize_entity_name(source)
        tgt_clean, _, _ = entity_sanitizer.sanitize_entity_name(target)
        if not src_clean or not tgt_clean:
            return

        with self._lock:
            existing = set(self.graph.nodes())
            src_canonical, _ = graph_enhancer.simplify_compound_node(src_clean, existing)
            tgt_canonical, _ = graph_enhancer.simplify_compound_node(tgt_clean, existing)
            src_final = src_canonical or src_clean
            tgt_final = tgt_canonical or tgt_clean

            if not src_final or not tgt_final or src_final.lower() == tgt_final.lower():
                return

            if not self.graph.has_node(src_final):
                self.add_node(src_final, category="CONCEPT")
            if not self.graph.has_node(tgt_final):
                self.add_node(tgt_final, category="CONCEPT")

            if self.graph.has_edge(src_final, tgt_final):
                self.graph[src_final][tgt_final]["weight"] = self.graph[src_final][tgt_final].get("weight", 1.0) + weight
                self.graph[src_final][tgt_final]["relation"] = relation
            else:
                self.graph.add_edge(src_final, tgt_final, relation=relation, weight=weight)
            self._save()

    def add_interaction(self, speaker: str, entities: list[dict], tasks: list[dict], intent: str) -> None:
        """Vincula entidades, tarefas e locutor em uma única interação de áudio/texto de forma thread-safe."""
        with self._lock:
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

    def resolve_canonical_node(self, name: str) -> str:
        """Resolve o nome canônico de um nó no grafo por busca exata, aliases ou primeiro nome."""
        with self._lock:
            name_clean = name.strip()
            if not name_clean:
                return ""
            if self.graph.has_node(name_clean):
                return name_clean

            name_lower = name_clean.lower()
            for n, attrs in self.graph.nodes(data=True):
                if n.lower() == name_lower:
                    return n
                aliases = [a.lower() for a in attrs.get("aliases", [])]
                if name_lower in aliases:
                    return n
                # Se for sobrenome ou primeiro nome correspondente a um nome completo (ex: "Varolo" -> "Fernando Varolo")
                parts = n.lower().split()
                if len(parts) > 1 and name_lower in parts:
                    return n

            return name_clean

    def link_triples(self, triples: list[Any], speaker: str | None = None) -> None:
        """Processa e vincula triplas semânticas explícitas extraídas pela LLM de forma thread-safe."""
        with self._lock:
            for tr in triples:
                src = getattr(tr, "source", None) or (tr.get("source") if isinstance(tr, dict) else None)
                rel = getattr(tr, "relation", None) or (tr.get("relation") if isinstance(tr, dict) else "RELATED_TO")
                tgt = getattr(tr, "target", None) or (tr.get("target") if isinstance(tr, dict) else None)

                if not src or not tgt:
                    continue

                src_canon = self.resolve_canonical_node(str(src))
                tgt_canon = self.resolve_canonical_node(str(tgt))

                self.add_edge(src_canon, tgt_canon, relation=str(rel).upper().replace(" ", "_"), weight=1.0)

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
