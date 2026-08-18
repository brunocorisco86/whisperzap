"""Módulo do Agente LLM Crítico e Sintetizador de Regras de Poda de Tarefas.

Analisa as tarefas ignoradas/canceladas pelo usuário, cruza com as métricas
linguísticas do spaCy e sintetiza regras heurísticas dinâmicas e diretrizes
negativas (Negative Few-Shots) para o extrator semântico.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from src.ai_gateway.providers import get_ai_provider
from src.memory.models import TaskRecord, MessageRecord
from src.memory.task_sentiment_analyzer import task_sentiment_analyzer

logger = logging.getLogger(__name__)

RULES_FILE_PATH = os.path.join(os.getcwd(), "data", "task_pruning_rules.json")


class TaskLearnerEngine:
    """Agente de Aprendizado de Feedback e Síntese de Regras Anti-Ruído."""

    def __init__(self, rules_path: str = RULES_FILE_PATH):
        self.rules_path = rules_path
        self._cached_rules: Optional[Dict[str, Any]] = None
        self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        """Carrega regras salvas do arquivo JSON ou retorna padrão seguro."""
        if os.path.exists(self.rules_path):
            try:
                with open(self.rules_path, "r", encoding="utf-8") as f:
                    self._cached_rules = json.load(f)
                    return self._cached_rules
            except Exception as e:
                logger.error(f"Erro ao carregar regras de {self.rules_path}: {e}")

        # Regras padrão iniciais baseadas no histórico
        self._cached_rules = {
            "version": "1.0",
            "last_optimized_at": None,
            "total_cancelled_analyzed": 0,
            "negative_guidelines": [
                "NUNCA crie tarefas para observações de campo ou relatos passivos sem ação explícita (ex: 'Frango sentado', 'Nível de amônia alto'). Registre apenas como tópicos ou notas.",
                "NUNCA crie tarefas para atualizações de status informando espera ou atraso (ex: 'Ainda não me responderam', 'Era pra hoje foi pra terça').",
                "NUNCA crie tarefas para conversas conceituais ou itens de roadmap discutidos informalmente (ex: 'Tá no roadmap', 'Ideia para o futuro').",
                "NUNCA crie tarefas para conselhos ou comentários condicionais hipotéticos (ex: 'A menos que eles exijam, mande o link').",
            ],
            "noise_taxonomies": {
                "FIELD_OBSERVATION": "Frases nominais curtas descrevendo sintomas ou estados sem comando imperativo.",
                "STATUS_UPDATE": "Mensagens relatando progresso, espera ou remarcação passiva de prazos.",
                "ROADMAP_CHAT": "Discussões de ideias futuras ou brainstormings não atribuídos.",
                "HYPOTHETICAL_ADVICE": "Sugestões que dependem de condições incertas não acionáveis no momento.",
            },
            "metrics": {
                "cancelled_count": 0,
                "done_count": 0,
                "actionability_filter_threshold": 0.45,
            },
        }
        return self._cached_rules

    def get_pruning_rules_prompt_hint(self) -> str:
        """Gera o bloco de prompt negativo para ser injetado no AI Gateway."""
        rules = self._cached_rules or self._load_rules()
        guidelines = rules.get("negative_guidelines", [])
        if not guidelines:
            return ""

        lines = [
            "DIRETRIZES ESTRITAS DE FILTRAGEM ANTI-FALSO-POSITIVO (O que NUNCA é tarefa):",
        ]
        for g in guidelines:
            lines.append(f"- {g}")

        lines.append("- Toda tarefa DEVE ter um verbo de ação claro, objetivo concreto e responsável/contexto definido.")
        return "\n".join(lines)

    async def run_feedback_optimization(self, db: Session) -> Dict[str, Any]:
        """Executa o ciclo completo de aprendizado sobre as tarefas canceladas."""
        cancelled_tasks = db.query(TaskRecord).filter(TaskRecord.status == "CANCELLED").all()
        done_tasks = db.query(TaskRecord).filter(TaskRecord.status == "DONE").all()

        cancelled_profiles = []
        for t in cancelled_tasks:
            src_msg = db.query(MessageRecord).filter(MessageRecord.id == t.message_id).first() if t.message_id else None
            src_text = src_msg.revised_text if src_msg else (src_msg.raw_text if src_msg else "")
            analysis = task_sentiment_analyzer.analyze_task_text(t.title, src_text)
            cancelled_profiles.append({
                "task_title": t.title,
                "source_text": src_text[:120],
                "noise_category": analysis.get("noise_category"),
                "sentiment_tone": analysis.get("sentiment_tone"),
                "actionability_score": analysis.get("actionability_score"),
            })

        logger.info(f"Otimizador: Analisando {len(cancelled_profiles)} tarefas canceladas e {len(done_tasks)} tarefas concluídas.")

        # Se houver tarefas canceladas, chama o LLM Critic para refinar as diretrizes
        if cancelled_profiles:
            try:
                provider = get_ai_provider(task="extract")
                prompt = (
                    "Você é o Agente Crítico de Qualidade de Tarefas do WhisperZap.\n"
                    "O usuário cancelou/ignorou as seguintes tarefas geradas pelo sistema porque eram falsos-positivos:\n\n"
                    f"{json.dumps(cancelled_profiles, ensure_ascii=False, indent=2)}\n\n"
                    "Sua missão: sintetizar um conjunto de 4 a 6 DIRETRIZES NEGATIVAS em português claras, concisas e acionáveis "
                    "ensinando a IA a NUNCA mais criar tarefas nesses cenários.\n"
                    "Retorne APENAS um JSON válido no formato:\n"
                    "{\n"
                    '  "negative_guidelines": ["Regra 1...", "Regra 2..."],\n'
                    '  "noise_patterns_summary": "Resumo conciso dos principais motivos de cancelamento"\n'
                    "}"
                )

                raw_resp = await provider.generate_text(
                    prompt=prompt,
                    system_instruction="Você é um engenheiro de prompts e crítico de IA focado em eliminar ruídos e falsos-positivos.",
                    temperature=0.2,
                )

                # Extrai JSON
                clean_json = raw_resp.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()

                parsed = json.loads(clean_json)
                if isinstance(parsed.get("negative_guidelines"), list) and len(parsed["negative_guidelines"]) > 0:
                    self._cached_rules["negative_guidelines"] = parsed["negative_guidelines"]
                    self._cached_rules["noise_taxonomies"]["LLM_SUMMARY"] = parsed.get("noise_patterns_summary", "")
            except Exception as e:
                logger.warning(f"Não foi possível executar síntese com LLM Critic: {e}. Mantendo diretrizes heurísticas.")

        # Atualiza metadados
        self._cached_rules["version"] = "1.1"
        self._cached_rules["last_optimized_at"] = datetime.now(timezone.utc).isoformat()
        self._cached_rules["total_cancelled_analyzed"] = len(cancelled_profiles)
        self._cached_rules["metrics"] = {
            "cancelled_count": len(cancelled_tasks),
            "done_count": len(done_tasks),
            "actionability_filter_threshold": 0.45,
        }

        # Salva em disco
        os.makedirs(os.path.dirname(self.rules_path), exist_ok=True)
        with open(self.rules_path, "w", encoding="utf-8") as f:
            json.dump(self._cached_rules, f, ensure_ascii=False, indent=2)

        logger.info(f"Regras de poda de tarefas salvas com sucesso em {self.rules_path}")
        return self._cached_rules


task_learner_engine = TaskLearnerEngine()
