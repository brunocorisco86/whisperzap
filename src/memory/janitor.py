"""Agente 'Zeladora' (Graph Janitor) — Faxina e Higienização Semanal do Grafo de Conhecimento.

Responsável por:
1. Proteger nós sagrados (contatos cadastrados, projetos, empresas e nós com alta conectividade);
2. Podar termos temporais efêmeros e ruídos conversacionais extraídos indevidamente;
3. Podar nós órfãos/isolados de baixo valor (grau 0 e menções <= 1);
4. Desambiguar e fundir variações quase-idênticas (aliases) transferindo arestas;
5. Registrar relatórios de auditoria e métricas de saúde do grafo.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel

from src.config import settings
from src.contacts.models import ContactRecord
from src.dictionary.service import dictionary_service
from src.memory.database import SessionLocal
from src.memory.graph import KnowledgeGraph, knowledge_graph

logger = logging.getLogger(__name__)

# Termos efêmeros que nunca devem ser nós permanentes de conhecimento no grafo
EPHEMERAL_TERMS = {
    "hoje", "amanhã", "amanha", "ontem", "segunda", "segunda-feira", "terça", "terca",
    "terça-feira", "quarta", "quarta-feira", "quinta", "quinta-feira", "sexta",
    "sexta-feira", "sábado", "sabado", "domingo", "semana", "semana passada",
    "semana que vem", "próxima semana", "proxima semana", "mês", "mes", "mês que vem",
    "cedo", "tarde", "noite", "madrugada", "áudio", "audio", "mensagem", "mensagens",
    "bom dia", "boa tarde", "boa noite", "olá", "ola", "conversa", "número", "numero",
    "favor", "obrigado", "obrigada", "valeu", "falou", "ok", "tá bom", "ta bom", "blz",
    "beleza", "sim", "não", "nao", "coisa", "algo", "isso", "aquilo", "teste", "áudios",
}

# Categorias nobres que nunca devem ser excluídas
SACRED_CATEGORIES = {"PERSON", "COMPANY", "PROJECT", "EQUIPMENT", "FACILITY", "CONTACT"}


class GraphJanitorReport(BaseModel):
    """Relatório estruturado da faxina executada pela Zeladora."""
    timestamp: str
    execution_time_ms: float
    dry_run: bool
    nodes_before: int
    nodes_after: int
    nodes_pruned_count: int
    edges_before: int
    edges_after: int
    edges_pruned_count: int
    nodes_merged_count: int
    pruned_nodes: List[str]
    merged_nodes: List[Dict[str, Any]]
    summary: str


class GraphJanitorService:
    """Motor analítico e executor da rotina de faxina da Zeladora."""

    def __init__(
        self,
        kg: KnowledgeGraph = knowledge_graph,
        history_path: str = "data/graph_janitor_history.json",
    ):
        self.kg = kg
        self.history_path = history_path

    def clean_graph(
        self,
        dry_run: bool = False,
        min_edge_weight: float = 1.0,
        prune_isolated: bool = True,
        deduplicate_aliases: bool = True,
    ) -> GraphJanitorReport:
        """Executa a faxina no Grafo de Conhecimento com proteção estrita aos nós sagrados."""
        start_time = time.time()
        logger.info(f"🧹 [Zeladora] Iniciando faxina no grafo (dry_run={dry_run})...")

        with self.kg._lock:
            g = self.kg.graph
            nodes_before = g.number_of_nodes()
            edges_before = g.number_of_edges()

            # 1. Constrói a Whitelist de Nós Sagrados
            sacred_nodes = self._build_sacred_whitelist()

            pruned_nodes: List[str] = []
            merged_nodes: List[Dict[str, Any]] = []

            # 2. Desambiguação e Fusão de Aliases Quase-Idênticos
            if deduplicate_aliases:
                merged_nodes = self._merge_alias_nodes(sacred_nodes, dry_run=dry_run)

            # 3. Identifica Nós Efêmeros e Ruídos
            nodes_to_remove: Set[str] = set()
            for node, attrs in list(g.nodes(data=True)):
                node_lower = node.strip().lower()
                category = (attrs.get("category") or "OTHER").upper()

                # Ignora se for nó sagrado
                if node in sacred_nodes or node_lower in sacred_nodes or category in SACRED_CATEGORIES:
                    continue

                # Regra de Termos Efêmeros
                if node_lower in EPHEMERAL_TERMS:
                    nodes_to_remove.add(node)
                    continue

                # Regra de Nós Isolados de Baixo Valor (grau 0 e mentions <= 1)
                if prune_isolated:
                    degree = g.degree(node)
                    mentions = attrs.get("mentions", 1)
                    if degree == 0 and mentions <= 1:
                        nodes_to_remove.add(node)

            # 4. Remove os nós identificados
            pruned_nodes = sorted(list(nodes_to_remove))
            if not dry_run:
                for node in pruned_nodes:
                    if g.has_node(node):
                        g.remove_node(node)

            # 5. Remove arestas com peso abaixo do mínimo ou auto-loops
            edges_pruned_count = 0
            if not dry_run:
                edges_to_remove = []
                for u, v, attrs in list(g.edges(data=True)):
                    if u == v:  # Auto-loop
                        edges_to_remove.append((u, v))
                    elif attrs.get("weight", 1.0) < min_edge_weight:
                        edges_to_remove.append((u, v))

                for u, v in edges_to_remove:
                    if g.has_edge(u, v):
                        g.remove_edge(u, v)
                edges_pruned_count = len(edges_to_remove)

                # Salva o grafo higienizado no disco
                self.kg._save()

            nodes_after = g.number_of_nodes() if not dry_run else (nodes_before - len(pruned_nodes))
            edges_after = g.number_of_edges() if not dry_run else (edges_before - edges_pruned_count)

            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            now_iso = datetime.now(timezone.utc).isoformat()

            summary = (
                f"A Zeladora realizou a faxina: {len(pruned_nodes)} nós efêmeros/órfãos podados, "
                f"{len(merged_nodes)} aliases mesclados e {edges_pruned_count} arestas otimizadas em {elapsed_ms}ms."
            )

            report = GraphJanitorReport(
                timestamp=now_iso,
                execution_time_ms=elapsed_ms,
                dry_run=dry_run,
                nodes_before=nodes_before,
                nodes_after=nodes_after,
                nodes_pruned_count=len(pruned_nodes),
                edges_before=edges_before,
                edges_after=edges_after,
                edges_pruned_count=edges_pruned_count,
                nodes_merged_count=len(merged_nodes),
                pruned_nodes=pruned_nodes[:50],  # Primeiros 50 para o relatório
                merged_nodes=merged_nodes,
                summary=summary,
            )

            if not dry_run:
                self._save_history(report)

            logger.info(f"✅ [Zeladora] Faxina concluída com sucesso: {summary}")
            return report

    def _build_sacred_whitelist(self) -> Set[str]:
        """Monta a lista de nós que NUNCA podem ser removidos."""
        sacred = set()

        # 1. Contatos da Tabela contacts
        db = SessionLocal()
        try:
            contacts = db.query(ContactRecord).all()
            for c in contacts:
                if c.name:
                    sacred.add(c.name)
                    sacred.add(c.name.lower())
                if c.role:
                    sacred.add(c.role)
                    sacred.add(c.role.lower())
        except Exception as e:
            logger.warning(f"Aviso ao carregar contatos para a whitelist da Zeladora: {e}")
        finally:
            db.close()

        # 2. Termos do Dicionário Léxico Oficial
        try:
            terms = dictionary_service.list_terms()
            for term in terms:
                if term.term:
                    sacred.add(term.term)
                    sacred.add(term.term.lower())
                if term.expansion:
                    sacred.add(term.expansion)
                    sacred.add(term.expansion.lower())
        except Exception as e:
            logger.warning(f"Aviso ao carregar dicionário para a whitelist da Zeladora: {e}")

        # 3. Nós com Alta Conectividade (degree >= 3 ou mentions >= 3)
        g = self.kg.graph
        for node, attrs in g.nodes(data=True):
            if g.degree(node) >= 3 or attrs.get("mentions", 0) >= 3:
                sacred.add(node)
                sacred.add(node.lower())

        return sacred

    def _merge_alias_nodes(self, sacred_nodes: Set[str], dry_run: bool = False) -> List[Dict[str, Any]]:
        """Identifica e mescla nós com pequenas variações de grafia / maiúsculas e minúsculas."""
        g = self.kg.graph
        merged_list = []
        normalized_map: Dict[str, List[str]] = {}

        for node in list(g.nodes()):
            key = node.strip().lower()
            if key not in normalized_map:
                normalized_map[key] = []
            normalized_map[key].append(node)

        for key, variations in normalized_map.items():
            if len(variations) > 1:
                # Escolhe o nó canônico (o que tem mais conexões/menções ou o que está na whitelist)
                canonical = max(
                    variations,
                    key=lambda n: (
                        100 if n in sacred_nodes else 0,
                        g.nodes[n].get("mentions", 1),
                        g.degree(n),
                        len(n),  # Prefere versões completas/capitalizadas
                    ),
                )

                for var in variations:
                    if var == canonical:
                        continue

                    if not dry_run:
                        # Transfere arestas de entrada
                        for u, _, edge_data in list(g.in_edges(var, data=True)):
                            if u != canonical:
                                self.kg.add_edge(
                                    source=u,
                                    target=canonical,
                                    relation=edge_data.get("relation", "RELATED_TO"),
                                    weight=edge_data.get("weight", 1.0),
                                )
                        # Transfere arestas de saída
                        for _, v, edge_data in list(g.out_edges(var, data=True)):
                            if v != canonical:
                                self.kg.add_edge(
                                    source=canonical,
                                    target=v,
                                    relation=edge_data.get("relation", "RELATED_TO"),
                                    weight=edge_data.get("weight", 1.0),
                                )

                        # Soma menções
                        g.nodes[canonical]["mentions"] = (
                            g.nodes[canonical].get("mentions", 1) + g.nodes[var].get("mentions", 1)
                        )
                        # Remove a variação secundária
                        g.remove_node(var)

                    merged_list.append({
                        "canonical": canonical,
                        "merged_from": var,
                    })

        return merged_list

    def _save_history(self, report: GraphJanitorReport) -> None:
        """Persiste o relatório no histórico JSON."""
        try:
            os.makedirs(os.path.dirname(self.history_path) or ".", exist_ok=True)
            history = self.get_history()
            history.insert(0, report.model_dump())
            # Mantém as últimas 50 faxinas
            history = history[:50]
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar histórico da Zeladora: {e}")

    def get_history(self) -> List[Dict[str, Any]]:
        """Retorna o histórico das faxinas realizadas."""
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Erro ao ler histórico da Zeladora: {e}")
        return []


graph_janitor_service = GraphJanitorService()
