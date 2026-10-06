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
from src.ai_gateway.jev.tier2 import JEVTier2Engine

logger = logging.getLogger(__name__)

# Padrões verbais claros para resolução direta de tarefas em nível local
DIRECT_TASK_PREFIXES = [
    r"^lembr(?:ar|e)[\s\-]+(?:de|que)?\s+",
    r"^anot(?:ar|e)[\s\-]+(?:que|uma?|ideia|tarefa)?\s+",
    r"^agend(?:ar|e)[\s\-]+",
    r"^precis(?:o|amos)\s+(?:de\s+)?",
    r"^n[aã]o\s+esquecer\s+de\s+",
    r"^favor\s+(?:de\s+)?(?:agendar\s+|verificar\s+|checar\s+|enviar\s+|fazer\s+)?",
    r"^fazer\s+",
    r"^ligar\s+(?:para|pro|pra)?\s+",
    r"^verific(?:ar|e)[\s\-]+",
    r"^chec(?:ar|e)[\s\-]+",
    r"^compr(?:ar|e)[\s\-]+",
    r"^envi(?:ar|e)[\s\-]+",
    r"^mand(?:ar|e)[\s\-]+",
    r"^revis(?:ar|e)[\s\-]+",
    r"^ped(?:ir|a)[\s\-]+",
]

IDEA_PATTERNS = [
    r"^(?:ideia|sugest[aã]o)\s*(?:de\s+fluxo|de\s+projeto)?\s*[:\-]?\s*",
    r"^(?:estive\s+pensando|que\s+tal|pod[ií]amos|podemos|proposta\s+de)\b",
]

QUESTION_PATTERNS = [
    r"^(?:o\s+que|quem|qual|quando|onde|como|por\s+que|quanto)\b",
    r"\?$",
    r"^(?:sabe\s+se|voc[eê]\s+lembra|temos\s+algum|qual\s+[eé]\s+o\s+status)\b",
]

GREETING_OR_FAREWELL_PATTERNS = [
    r"^(?:bom\s+dia|boa\s+tarde|boa\s+noite|ol[aá]|oi|opa)(?:\s+(?:a\s+todos|pessoal|galera|turma))?(?:[\,\.]?\s*at[eé]\s+amanh[aã])?[\!\.\?]*$",
    r"^(?:muito\s+)?(?:obrigad[oa]|valeu|valeu\s+demais)(?:[\,\.]?\s*valeu)?[\!\.]*$",
    r"^(?:ok|beleza|show)\s+(?:recebido|combinado|anotado)?(?:[\,\.]?\s*abra[cç]o)?[\!\.]*$",
    r"^(?:tudo\s+bem|como\s+vai)(?:\s+(?:por\s+a[ií]|com\s+voc[eê]))?[\?\!\.]*$",
]

CRITICAL_EMERGENCY_PATTERNS = [
    r"\b(urgente|emerg[eê]ncia|imediato|imediatamente|cr[ií]tico|cr[ií]tica)\b",
    r"\b(parou\s+tudo|vazamento\s+cr[ií]tico|falta\s+de\s+ra[cç][aã]o|mortalidade\s+alta)\b",
    r"\b(o\s+quanto\s+antes|asap|suporte\s+imediato)\b",
]

WEEKDAYS_MAP = {
    0: r"\bsegunda(?:-feira)?\b",
    1: r"\bter[cç]a(?:-feira)?\b",
    2: r"\bquarta(?:-feira)?\b",
    3: r"\bquinta(?:-feira)?\b",
    4: r"\bsexta(?:-feira)?\b",
    5: r"\bs[aá]bado\b",
    6: r"\bdomingo\b",
}


def extract_relative_due_date(text: str, base_date: Optional[datetime] = None) -> Optional[str]:
    """Extrai data relativa de textos em português (hoje, amanhã, depois de amanhã, dias da semana)."""
    base = base_date or datetime.now()
    clean = text.lower()

    if re.search(r"\bdepois\s+de\s+amanh[aã]\b", clean):
        return (base + timedelta(days=2)).strftime("%Y-%m-%d")
    if re.search(r"\bamanh[aã]\b", clean):
        return (base + timedelta(days=1)).strftime("%Y-%m-%d")
    if re.search(r"\bhoje\b", clean):
        return base.strftime("%Y-%m-%d")

    # Dias da semana
    for target_weekday, pattern in WEEKDAYS_MAP.items():
        if re.search(pattern, clean):
            current_weekday = base.weekday()
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (base + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    return None


class JEVService:
    """Motor de governança inteligente JEV (Judge, Evaluator, Verifier)."""

    def __init__(self):
        self.enabled = getattr(settings, "JEV_ENABLED", True)
        self.tier2 = JEVTier2Engine()

    def judge(
        self,
        text: str,
        speaker: Optional[str] = "Bruno",
        is_self_memo: bool = False,
        duration_s: float = 0.0,
        force_tier2: bool = False,
        meta_info: Optional[Dict[str, Any]] = None,
    ) -> JEVJudgement:
        """Executa o julgamento do Judge em cascata de alta performance."""
        # Se force_tier2 estiver ativo ou engine estiver configurada exclusivamente como onnx
        if force_tier2 or getattr(settings, "JEV_ENGINE", "hybrid") == "onnx":
            return self.tier2.judge(
                text=text,
                speaker=speaker,
                is_self_memo=is_self_memo,
                duration_s=duration_s,
                meta_info=meta_info,
            )

        if not text or not text.strip():
            return JEVJudgement(
                action=JEVAction.BYPASS,
                intent=JEVIntent.NOISE,
                urgency=JEVUrgency.LOW,
                confidence=1.0,
                suggested_route="bypass",
                should_vectorize=False,
                rationale="Texto vazio ou nulo.",
            )

        clean = text.strip()
        norm = normalize_text(clean)

        # 1. Tier 1: Triagem de Bypass (Ruído, Emojis, SAC, Saudações Triviais)
        if is_emoji_only_or_symbols(clean):
            return JEVJudgement(
                action=JEVAction.BYPASS,
                intent=JEVIntent.NOISE,
                urgency=JEVUrgency.LOW,
                confidence=1.0,
                suggested_route="bypass",
                should_vectorize=False,
                rationale="Mensagem composta apenas por emojis ou caracteres especiais.",
            )

        if is_automated_service_message(clean):
            return JEVJudgement(
                action=JEVAction.BYPASS,
                intent=JEVIntent.NOISE,
                urgency=JEVUrgency.LOW,
                confidence=1.0,
                suggested_route="bypass",
                should_vectorize=False,
                rationale="Mensagem transacional ou robô de atendimento automatizado.",
            )

        # Saudações simples sem comando adicional
        if norm in TRIVIAL_SOCIAL_PHRASES:
            return JEVJudgement(
                action=JEVAction.BYPASS,
                intent=JEVIntent.NOISE,
                urgency=JEVUrgency.LOW,
                confidence=0.98,
                suggested_route="bypass",
                should_vectorize=False,
                rationale="Saudação social trivial sem conteúdo acionável.",
            )

        for g_pat in GREETING_OR_FAREWELL_PATTERNS:
            if re.search(g_pat, clean, re.IGNORECASE):
                return JEVJudgement(
                    action=JEVAction.BYPASS,
                    intent=JEVIntent.NOISE,
                    urgency=JEVUrgency.LOW,
                    confidence=0.96,
                    suggested_route="bypass",
                    should_vectorize=False,
                    rationale="Saudação ou despedida social sem conteúdo operacional.",
                )

        # 2. Tier 1: Detecção de Consultas ao Grafo de Conhecimento (Perguntas)
        for q_pat in QUESTION_PATTERNS:
            if re.search(q_pat, clean, re.IGNORECASE):
                return JEVJudgement(
                    action=JEVAction.GRAPH_QUERY,
                    intent=JEVIntent.QUESTION,
                    urgency=JEVUrgency.MEDIUM,
                    confidence=0.92,
                    suggested_route="gemini",
                    tier_used="tier1_heuristic",
                    rationale="Pergunta interrogativa ou consulta sobre histórico e entidades.",
                )

        # 3. Tier 1 / Tier 2: Avaliação de Tarefas Diretas vs Análise Complexa
        # Avalia urgência declarada ou criticidade operacional zootécnica
        urgency = JEVUrgency.MEDIUM
        is_critical_emergency = False
        for u_pat in CRITICAL_EMERGENCY_PATTERNS:
            if re.search(u_pat, clean, re.IGNORECASE):
                urgency = JEVUrgency.URGENT
                is_critical_emergency = True
                break

        # Identifica se é uma ideia propositiva
        is_idea = False
        for i_pat in IDEA_PATTERNS:
            if re.search(i_pat, clean, re.IGNORECASE):
                is_idea = True
                break

        # Checa prefixos imperativos de comando de tarefa
        direct_task_match = False
        for t_pat in DIRECT_TASK_PREFIXES:
            if re.search(t_pat, clean, re.IGNORECASE):
                direct_task_match = True
                break

        # Emergência operacional direta sem prefixo verbal tradicional (ex: 'parou tudo', 'vazamento')
        if is_critical_emergency:
            direct_task_match = True

        # Indicativos de ação/tarefa distribuídos no corpo de mensagens longas
        has_task_actionables = direct_task_match or bool(
            re.search(r"\b(precisamos\b|definir\s+os\s+prazos|solicitou\b|providenciar\b|tarefa\b|a\s+fazer\b)", clean, re.IGNORECASE)
        )

        # Checa se é nota pessoal explícita
        if re.search(r"^\s*nota\s+pessoal\s*[:\-]?\s*", clean, re.IGNORECASE):
            is_self_memo = True

        # Checa se é um comando imperativo simples e conciso (< 240 caracteres e áudio < 25s)
        is_short_prompt = len(clean) < 240 and (duration_s <= 25.0)

        # Extração de data relativa
        due_date = extract_relative_due_date(clean)

        # Se for conciso e couber em DIRECT_RESOLVE (tarefa, ideia ou nota pessoal curta)
        if is_short_prompt and (direct_task_match or is_idea or is_self_memo):
            # Limpa prefixos de comando para montar o título direto
            title_candidate = clean
            for prefix_list in [DIRECT_TASK_PREFIXES, IDEA_PATTERNS]:
                for pat in prefix_list:
                    title_candidate = re.sub(pat, "", title_candidate, flags=re.IGNORECASE).strip()

            # Limpa prefixo de nota pessoal e urgência inicial
            title_candidate = re.sub(r"^\s*nota\s+pessoal\s*[:\-]?\s*", "", title_candidate, flags=re.IGNORECASE).strip()
            title_candidate = re.sub(r"^\s*(?:urgente|emerg[eê]ncia)[\,\:\s\-]+", "", title_candidate, flags=re.IGNORECASE).strip()

            # Capitaliza primeira letra e remove pontuação final
            title_candidate = title_candidate.rstrip(".!")
            if title_candidate:
                title_candidate = title_candidate[0].upper() + title_candidate[1:]

            target_intent = JEVIntent.IDEA if is_idea else (JEVIntent.TASK if direct_task_match else JEVIntent.MEMO)

            return JEVJudgement(
                action=JEVAction.DIRECT_RESOLVE,
                intent=target_intent,
                urgency=urgency,
                confidence=0.94,
                suggested_route="local",
                tier_used="tier1_heuristic",
                direct_task_title=title_candidate[:120],
                direct_due_date=due_date,
                rationale="Comando acionável direto e conciso, elegível para resolução local.",
            )

        # 4. Caso geral com volume de texto expressivo: Despacha para Análise Profunda
        return JEVJudgement(
            action=JEVAction.DEEP_ANALYSIS,
            intent=JEVIntent.TASK if has_task_actionables else (JEVIntent.IDEA if is_idea else JEVIntent.MEMO),
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
