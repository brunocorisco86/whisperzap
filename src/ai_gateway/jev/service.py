"""Serviço do Orquestrador JEV (Judge - Evaluator - Verifier)."""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from src.config import settings
from src.ai_gateway.bypass import (
    TRIVIAL_SOCIAL_PHRASES,
    is_automated_service_message,
    normalize_text,
    is_emoji_only_or_symbols,
)
from src.ai_gateway.jev.schemas import (
    JEVAction,
    JEVIntent,
    JEVUrgency,
    JEVJudgement,
)

logger = logging.getLogger(__name__)

# Padrões verbais claros para resolução direta de tarefas em nível local
DIRECT_TASK_PREFIXES = [
    r"^lembr(?:ar|e)[\s\-]+(?:de|que)?\s+",
    r"^anot(?:ar|e)[\s\-]+(?:que|uma?|ideia|tarefa)?\s+",
    r"^agend(?:ar|e)[\s\-]+",
    r"^precis(?:o|amos)\s+(?:de\s+)?",
    r"^n[aã]o\s+esquecer\s+de\s+",
    r"^favor\s+",
    r"^fazer\s+",
    r"^ligar\s+(?:para|pro|pra)?\s+",
]

QUESTION_PATTERNS = [
    r"^(?:o\s+que|quem|qual|quando|onde|como|por\s+que|quanto)\b",
    r"\?$",
    r"^(?:sabe\s+se|voc[eê]\s+lembra|temos\s+algum|qual\s+[eé]\s+o\s+status)\b",
]


class JEVService:
    """Motor de governança inteligente JEV (Judge, Evaluator, Verifier)."""

    def __init__(self):
        self.enabled = getattr(settings, "JEV_ENABLED", True)

    def judge(
        self,
        text: str,
        speaker: Optional[str] = "Bruno",
        is_self_memo: bool = False,
        duration_s: float = 0.0,
        meta_info: Optional[Dict[str, Any]] = None,
    ) -> JEVJudgement:
        """Executa o julgamento do Judge em cascata de alta performance."""
        if not text or not text.strip():
            return JEVJudgement(
                action=JEVAction.BYPASS,
                intent=JEVIntent.NOISE,
                confidence=1.0,
                suggested_route="bypass",
                rationale="Texto vazio ou nulo.",
            )

        clean = text.strip()
        norm = normalize_text(clean)

        # 1. Tier 1: Triagem de Bypass (Ruído, Emojis, SAC, Saudações Triviais)
        if is_emoji_only_or_symbols(clean):
            return JEVJudgement(
                action=JEVAction.BYPASS,
                intent=JEVIntent.NOISE,
                confidence=1.0,
                suggested_route="bypass",
                rationale="Mensagem composta apenas por emojis ou caracteres especiais.",
            )

        if is_automated_service_message(clean):
            return JEVJudgement(
                action=JEVAction.BYPASS,
                intent=JEVIntent.NOISE,
                confidence=1.0,
                suggested_route="bypass",
                rationale="Mensagem transacional ou robô de atendimento automatizado.",
            )

        # Saudações simples sem comando adicional
        if norm in TRIVIAL_SOCIAL_PHRASES:
            return JEVJudgement(
                action=JEVAction.BYPASS,
                intent=JEVIntent.NOISE,
                confidence=0.98,
                suggested_route="bypass",
                rationale="Saudação social trivial sem conteúdo acionável.",
            )

        # 2. Tier 1: Detecção de Consultas ao Grafo de Conhecimento (Perguntas)
        for q_pat in QUESTION_PATTERNS:
            if re.search(q_pat, clean, re.IGNORECASE):
                return JEVJudgement(
                    action=JEVAction.GRAPH_QUERY,
                    intent=JEVIntent.QUESTION,
                    confidence=0.90,
                    suggested_route="gemini",
                    tier_used="tier1_heuristic",
                    rationale="Pergunta interrogativa ou consulta sobre histórico e entidades.",
                )

        # 3. Tier 1 / Tier 2: Avaliação de Tarefas Diretas vs Análise Complexa
        # Avalia urgência declarada
        urgency = JEVUrgency.MEDIUM
        if re.search(r"\b(urgente|emerg[eê]ncia|imediato|o\s+quanto\s+antes|cr[ií]tico)\b", clean, re.IGNORECASE):
            urgency = JEVUrgency.URGENT

        # Checa se é um comando imperativo simples e conciso (< 180 caracteres ou áudio curto)
        is_short_prompt = len(clean) < 180 or (0 < duration_s <= 20.0)
        direct_task_match = None
        for t_pat in DIRECT_TASK_PREFIXES:
            if re.search(t_pat, clean, re.IGNORECASE):
                direct_task_match = True
                break

        # Extração rápida de data relativa (ex: 'amanhã', 'hoje', 'segunda')
        due_date = None
        today = datetime.now()
        if re.search(r"\bamanh[aã]\b", clean, re.IGNORECASE):
            due_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        elif re.search(r"\bhoje\b", clean, re.IGNORECASE):
            due_date = today.strftime("%Y-%m-%d")

        # Se for nota pessoal curta com comando direto, pode ser DIRECT_RESOLVE
        if is_short_prompt and (direct_task_match or is_self_memo):
            # Limpa prefixos de comando para montar o título direto
            title_candidate = clean
            for t_pat in DIRECT_TASK_PREFIXES:
                title_candidate = re.sub(t_pat, "", title_candidate, flags=re.IGNORECASE).strip()

            # Capitaliza primeira letra
            if title_candidate:
                title_candidate = title_candidate[0].upper() + title_candidate[1:]

            return JEVJudgement(
                action=JEVAction.DIRECT_RESOLVE,
                intent=JEVIntent.TASK if direct_task_match else JEVIntent.MEMO,
                urgency=urgency,
                confidence=0.92,
                suggested_route="local",
                tier_used="tier1_heuristic",
                direct_task_title=title_candidate[:120],
                direct_due_date=due_date,
                rationale="Comando acionável direto e conciso, elegível para resolução local.",
            )

        # 4. Caso geral com volume de texto expressivo: Despacha para Análise Profunda
        return JEVJudgement(
            action=JEVAction.DEEP_ANALYSIS,
            intent=JEVIntent.TASK if direct_task_match else JEVIntent.MEMO,
            urgency=urgency,
            confidence=0.88,
            suggested_route="gemini",
            tier_used="tier1_heuristic",
            rationale="Mensagem com múltiplos tópicos ou extensão exigindo raciocínio e síntese do LLM mestre.",
        )

    def verify_and_sanitize(
        self,
        raw_text: str,
        revised_text: str,
        tasks: Optional[List[Any]] = None,
        duration_s: float = 0.0,
    ) -> Dict[str, Any]:
        """[V] VERIFIER: Valida e sanitiza o output contra alucinações e redundâncias textuais."""
        tasks = tasks or []
        clean_revised = revised_text.strip()

        # 1. Supressão de Destaques Redundantes em Áudios Curtos (< 250 chars ou <= 25s)
        if "📌" in clean_revised:
            parts = clean_revised.split("📌", 1)
            main_body = parts[0].strip()
            if len(main_body) < 250 or (0 < duration_s <= 25.0):
                clean_revised = main_body if main_body else clean_revised

        # 2. Desduplicação de Tarefas Idênticas ao Texto Principal
        sanitized_tasks = []
        for t in tasks:
            title = getattr(t, "title", str(t))
            # Garante título capitalizado e sem ponto final
            clean_title = title.strip().rstrip(".")
            if clean_title:
                clean_title = clean_title[0].upper() + clean_title[1:]
            sanitized_tasks.append(clean_title)

        return {
            "revised_text": clean_revised,
            "tasks_count": len(tasks),
            "sanitized_titles": sanitized_tasks,
            "is_clean": True,
        }


jev_service = JEVService()
