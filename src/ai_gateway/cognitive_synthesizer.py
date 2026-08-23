"""Módulo de Síntese Cognitiva Local Extrativa (spaCy NLP) para o Agente Hermes e Oráculo Melpômene.

Gera resumos executivos fluidos, humanos e estruturados por tópicos a partir de memórias recuperadas,
sem dependência de APIs externas de LLM (0 custo de tokens).
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set

from src.memory.task_sentiment_analyzer import get_spacy_nlp

logger = logging.getLogger(__name__)


class LocalCognitiveSynthesizer:
    """Sintetizador cognitivo baseado em NLP local para geração de respostas ricas."""

    def __init__(self):
        self.nlp = get_spacy_nlp()

    def synthesize_dialogue(
        self,
        speaker_name: str,
        sources: List[Any],
        pending_tasks: List[str],
        related_entities: List[str],
        parsed_query: Optional[Any] = None,
    ) -> str:
        """Sintetiza conversas de um interlocutor específico em tópicos temáticos executivos."""
        is_today = bool(parsed_query and getattr(parsed_query, "is_today", False))
        is_yesterday = bool(parsed_query and getattr(parsed_query, "is_yesterday", False))

        # Procura nota de última interação temporal em related_entities
        temporal_note = next((e for e in related_entities if "Última conversa registrada" in e or "última interação" in e.lower() or "Nota Temporal:" in e), None)

        if not sources:
            if is_today:
                base_msg = f"Você não conversou com **{speaker_name}** hoje."
                if temporal_note:
                    clean_note = temporal_note.replace("Nota Temporal:", "").strip()
                    base_msg += f"\n\nℹ️ {clean_note}"
            elif is_yesterday:
                base_msg = f"Você não conversou com **{speaker_name}** ontem."
                if temporal_note:
                    clean_note = temporal_note.replace("Nota Temporal:", "").strip()
                    base_msg += f"\n\nℹ️ {clean_note}"
            else:
                base_msg = f"Não foram encontradas conversas ou mensagens recentes registradas de **{speaker_name}**."

            if pending_tasks:
                base_msg += "\n\n📋 **Tarefas Relacionadas no Sistema:**\n" + "\n".join(f"• {t}" for t in pending_tasks[:3])
            return base_msg

        # Agrupamento temático de mensagens usando spaCy e palavras-chave
        operation_points = []
        supplier_and_people_points = []
        follow_up_points = []
        other_points = []

        seen_snippets = set()

        for s in sources:
            snippet = (getattr(s, "text_snippet", None) or getattr(s, "summary", None) or str(s)).strip()
            if not snippet or snippet in seen_snippets:
                continue
            seen_snippets.add(snippet)

            s_lower = snippet.lower()

            # 1. Problemas operacionais / equipamentos / peças
            if any(w in s_lower for w in ("peça", "sensor", "silo", "funciona", "quebrou", "estragou", "falha", "granja", "aviário", "devolver")):
                operation_points.append(snippet)
            # 2. Pessoas / Fornecedores / Prazos longos
            elif any(w in s_lower for w in ("empresa", "saiu", "ano", "fornecedor", "técnico", "zotto", "pedro", "ele falou", "ele")):
                supplier_and_people_points.append(snippet)
            # 3. Retorno / Cobrança / Acompanhamento
            elif any(w in s_lower for w in ("responder", "resposta", "retorno", "passo", "cobrei", "cobrar", "deixa ver", "avisar")):
                follow_up_points.append(snippet)
            else:
                other_points.append(snippet)

        if is_today:
            lines = [f"Hoje, **{speaker_name}** conversou com você sobre os seguintes pontos principais:"]
        elif is_yesterday:
            lines = [f"Ontem, **{speaker_name}** conversou com você sobre os seguintes pontos principais:"]
        else:
            lines = [f"Nas conversas registradas, **{speaker_name}** abordou os seguintes pontos principais:"]

        # Tópico 1: Operação e Equipamentos
        if operation_points:
            summary_op = self._summarize_points(operation_points)
            lines.append(f"\n• **Equipamentos e Operação**: {summary_op}")

        # Tópico 2: Situação com Fornecedor / Responsáveis
        if supplier_and_people_points:
            summary_sup = self._summarize_points(supplier_and_people_points)
            lines.append(f"\n• **Contato & Fornecedores**: {summary_sup}")

        # Tópico 3: Próximos Passos e Retorno
        if follow_up_points:
            summary_fol = self._summarize_points(follow_up_points)
            lines.append(f"\n• **Acompanhamento & Retorno**: {summary_fol}")

        # Outros tópicos residuais
        if not operation_points and not supplier_and_people_points and not follow_up_points and other_points:
            summary_oth = self._summarize_points(other_points)
            lines.append(f"\n• **Assuntos Abordados**: {summary_oth}")

        # Tarefas pendentes relacionadas
        if pending_tasks:
            lines.append("\n📋 **Tarefas Relacionadas em Aberto:**")
            for t in pending_tasks[:3]:
                lines.append(f"• {t}")

        return "\n".join(lines)

    def _summarize_points(self, points: List[str]) -> str:
        """Limpa e formata uma lista de fragmentos em uma frase fluida."""
        clean_items = []
        for p in points:
            clean = p.strip().strip("\"'“”`.,;:")
            if clean:
                clean_items.append(clean)

        if not clean_items:
            return "Informações operacionais registradas."

        if len(clean_items) == 1:
            return f'Relatou que "{clean_items[0]}".'
        elif len(clean_items) == 2:
            return f'Destacou que "{clean_items[0]}" e mencionou que "{clean_items[1]}".'
        else:
            first_two = f'"{clean_items[0]}" e "{clean_items[1]}"'
            return f'Abordou {first_two}, além de outros detalhes complementares.'

    def synthesize_general(
        self,
        query: str,
        sources: List[Any],
        pending_tasks: List[str],
        related_entities: List[str],
        parsed_query: Optional[Any] = None,
    ) -> str:
        """Gera síntese cognitiva geral para consultas não restritas a um único diálogo."""
        # Se for diálogo com pessoa identificada
        if parsed_query and parsed_query.target_speaker_full_name:
            return self.synthesize_dialogue(
                speaker_name=parsed_query.target_speaker_full_name,
                sources=sources,
                pending_tasks=pending_tasks,
                related_entities=related_entities,
                parsed_query=parsed_query,
            )
        elif parsed_query and parsed_query.target_speaker:
            return self.synthesize_dialogue(
                speaker_name=parsed_query.target_speaker,
                sources=sources,
                pending_tasks=pending_tasks,
                related_entities=related_entities,
                parsed_query=parsed_query,
            )

        if not sources and not pending_tasks:
            if parsed_query and getattr(parsed_query, "is_today", False):
                return "Não foram localizadas memórias ou conversas registradas hoje no banco de dados."
            if parsed_query and getattr(parsed_query, "is_yesterday", False):
                return "Não foram localizadas memórias ou conversas registradas ontem no banco de dados."
            return "Não foram localizadas memórias ou registros diretamente relacionados a esta consulta no banco de dados."

        lines = ["Com base nas informações consolidadas no assistente Hermes:"]

        if sources:
            lines.append("\n💬 **Destaques das Memórias Registradas:**")
            for s in sources[:5]:
                spk = getattr(s, "speaker", "Registro")
                date = f" ({s.created_at})" if getattr(s, "created_at", None) else ""
                snippet = getattr(s, "text_snippet", None) or getattr(s, "summary", "") or str(s)
                lines.append(f"• **{spk}**{date}: \"{snippet}\"")

        if pending_tasks:
            lines.append("\n📋 **Tarefas & Ações em Aberto:**")
            for t in pending_tasks[:4]:
                lines.append(f"• {t}")

        if related_entities:
            clean_entities = [e for e in related_entities if not e.startswith("Contato Oficial:") and "-[" in e]
            if clean_entities:
                lines.append("\n🔗 **Conexões do Grafo de Conhecimento:**")
                for e in clean_entities[:4]:
                    lines.append(f"• {e}")

        return "\n".join(lines)


# Instância singleton
local_cognitive_synthesizer = LocalCognitiveSynthesizer()
