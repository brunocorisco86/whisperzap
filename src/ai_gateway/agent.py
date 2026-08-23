"""Módulo do Agente Hermes & Motores de Síntese e Inteligência."""

import json
import logging
import re
import time
from typing import Any
from src.ai_gateway.prompts import (
    DAILY_SUMMARY_SYSTEM_PROMPT,
    DAILY_SUMMARY_USER_TEMPLATE,
    HERMES_AGENT_SYSTEM_PROMPT,
    HERMES_QUERY_USER_TEMPLATE,
    WEEKLY_ANALYSIS_SYSTEM_PROMPT,
    WEEKLY_ANALYSIS_USER_TEMPLATE,
)
from src.ai_gateway.providers import get_ai_provider
from src.ai_gateway.schemas import (
    DailyActionItem,
    DailySummaryResponse,
    HermesQueryResponse,
    MemorySourceCitation,
    WeeklyReportResponse,
)

logger = logging.getLogger(__name__)


def extract_json_payload(raw_response: str) -> dict[str, Any]:
    """Extrai objeto JSON de respostas de LLM que possam conter blocos markdown."""
    text = raw_response.strip()

    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if json_match:
        text = json_match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise ValueError(f"Não foi possível fazer parsing de JSON na resposta da IA: {raw_response[:200]}")


class HermesAgentService:
    """Serviço do Agente Hermes para Q&A RAG e Geração de Relatórios."""

    def __init__(self):
        self.provider = get_ai_provider(task="hermes")

    async def answer_hermes_query(
        self,
        query: str,
        sources: list[MemorySourceCitation],
        related_entities: list[str],
        pending_tasks: list[str],
        parsed_query: Any = None,
    ) -> HermesQueryResponse:
        """Gera resposta contextual com o Agente Hermes citando fontes estritas e humanizando o texto final."""
        start_time = time.perf_counter()

        # Monta blocos textuais de contexto
        if sources:
            memories_lines = []
            for s in sources:
                created = f" em {s.created_at}" if s.created_at else ""
                memories_lines.append(f"- [ID: {s.message_id}] De: {s.speaker}{created} | Conteúdo: \"{s.text_snippet}\"")
            retrieved_context = "\n".join(memories_lines)
        else:
            retrieved_context = "Nenhuma memória diretamente relacionada encontrada no banco."

        graph_context = (
            ", ".join(related_entities) if related_entities else "Nenhuma entidade conectada mapeada para este termo."
        )
        tasks_context = (
            "\n".join([f"- {t}" for t in pending_tasks]) if pending_tasks else "Nenhuma tarefa pendente relacionada."
        )

        from src.memory.timezone_utils import get_now_brt
        current_datetime_brt = get_now_brt().strftime("%d/%m/%Y %H:%M:%S (%A)")

        user_prompt = HERMES_QUERY_USER_TEMPLATE.format(
            current_datetime=current_datetime_brt,
            query=query,
            retrieved_context=retrieved_context,
            graph_context=graph_context,
            tasks_context=tasks_context,
        )

        try:
            llm_response = await self.provider.generate_text(
                prompt=user_prompt,
                system_instruction=HERMES_AGENT_SYSTEM_PROMPT,
                temperature=0.2,
            )
            answer_text = llm_response.strip()
        except Exception as exc:
            logger.warning(f"Chamada LLM para consulta Hermes falhou ({exc}). Gerando síntese cognitiva local com spaCy.")
            from src.ai_gateway.cognitive_synthesizer import local_cognitive_synthesizer
            answer_text = local_cognitive_synthesizer.synthesize_general(
                query=query,
                sources=sources,
                pending_tasks=pending_tasks,
                related_entities=related_entities,
                parsed_query=parsed_query,
            )

        # Humanização e Sanitização Anti-Lixo Técnico com spaCy e Polímnia
        from src.ai_gateway.humanizer import hermes_response_humanizer
        humanized_answer = hermes_response_humanizer.humanize(answer_text, parsed=parsed_query)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return HermesQueryResponse(
            query=query,
            answer=humanized_answer,
            sources=sources,
            related_entities=related_entities,
            pending_tasks_mentioned=pending_tasks,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            processing_time_ms=elapsed_ms,
        )

    @staticmethod
    def _normalize_action_item(item: dict | Any) -> dict | Any:
        if not isinstance(item, dict):
            return item
        d = dict(item)
        p = str(d.get("priority", "MEDIUM")).upper().strip()
        if p in ("CRITICAL", "ALTA", "URGENTE", "IMMEDIATE", "URGENT"):
            d["priority"] = "URGENT"
        elif p in ("HIGH", "ALTA"):
            d["priority"] = "HIGH"
        elif p in ("LOW", "BAIXA"):
            d["priority"] = "LOW"
        else:
            d["priority"] = "MEDIUM"
        return d

    async def generate_daily_summary(
        self,
        target_date: str,
        messages: list[dict],
        tasks: list[dict],
    ) -> DailySummaryResponse:
        """Gera o resumo executivo diário e o plano de ação para o dia seguinte."""
        start_time = time.perf_counter()

        # Extração de pendências reais
        pending_tasks = [t for t in tasks if t.get("status") == "PENDING"]
        unique_pending = list({t["title"]: t for t in pending_tasks}.keys())

        # Monta prompt estruturado
        messages_block = "\n".join(
            [f"- [{m.get('speaker', 'Desconhecido')}]: {m.get('revised_text', m.get('raw_text', ''))}" for m in messages]
        ) if messages else "Nenhuma mensagem gravada hoje."

        tasks_block = "\n".join(
            [f"- [{t.get('priority', 'MEDIUM')}] {t.get('title')} (Resp: {t.get('assignee', 'Não atribuído')})" for t in tasks]
        ) if tasks else "Nenhuma tarefa registrada hoje."

        prompt = DAILY_SUMMARY_USER_TEMPLATE.format(
            target_date=target_date,
            messages_block=messages_block,
            tasks_block=tasks_block,
        )

        try:
            raw_response = await self.provider.generate_text(
                prompt=prompt,
                system_instruction=DAILY_SUMMARY_SYSTEM_PROMPT,
                temperature=0.2,
            )
            parsed = extract_json_payload(raw_response)
        except Exception as e:
            logger.warning(f"Fallback no Resumo Diário devido a erro no LLM: {e}")
            parsed = {
                "executive_summary": f"Resumo automático das atividades do dia {target_date}. Total de {len(messages)} mensagens registradas.",
                "key_events": [],
                "decisions": [],
                "issues_and_blockers": [],
                "completed_tasks": [t["title"] for t in tasks if t.get("status") == "DONE"][:5],
                "pending_tasks": unique_pending[:5],
                "plan_for_tomorrow": [
                    {
                        "title": title,
                        "assignee": None,
                        "priority": "HIGH",
                        "due_date": "Amanhã",
                        "related_project": None,
                    }
                    for title in unique_pending[:5]
                ],
            }

        plan_items = [
            DailyActionItem(**self._normalize_action_item(item)) if isinstance(item, dict) else item
            for item in parsed.get("plan_for_tomorrow", [])
        ]

        # Constrói texto limpo formatado para WhatsApp
        from src.reports.daily import format_daily_whatsapp_message

        whatsapp_text = format_daily_whatsapp_message(
            date_str=target_date,
            executive_summary=parsed.get("executive_summary", ""),
            key_events=parsed.get("key_events", []),
            decisions=parsed.get("decisions", []),
            issues=parsed.get("issues_and_blockers", []),
            completed_tasks=parsed.get("completed_tasks", []),
            pending_tasks=parsed.get("pending_tasks", []),
            plan=plan_items,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return DailySummaryResponse(
            date=target_date,
            executive_summary=parsed.get("executive_summary", ""),
            key_events=parsed.get("key_events", []),
            decisions=parsed.get("decisions", []),
            issues_and_blockers=parsed.get("issues_and_blockers", []),
            completed_tasks=parsed.get("completed_tasks", []),
            pending_tasks=parsed.get("pending_tasks", []),
            plan_for_tomorrow=plan_items,
            whatsapp_text=whatsapp_text,
            messages_analyzed=len(messages),
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            processing_time_ms=elapsed_ms,
        )

    async def generate_weekly_report(
        self,
        period_str: str,
        messages: list[dict],
        tasks: list[dict],
        metrics: dict,
    ) -> WeeklyReportResponse:
        """Gera a inteligência semanal consolidada e o plano de domingo."""
        start_time = time.perf_counter()

        # Resumo das mensagens da semana
        if messages:
            msg_lines = [f"- [{m.get('speaker')}]: {m.get('summary', m.get('revised_text', ''))}" for m in messages[:30]]
            weekly_messages_block = "\n".join(msg_lines)
        else:
            weekly_messages_block = "Sem mensagens registradas na semana."

        weekly_metrics_block = (
            f"Tarefas Totais: {metrics.get('total_tasks', len(tasks))}\n"
            f"Tarefas Concluídas: {metrics.get('completed_tasks', 0)}\n"
            f"Tarefas Pendentes: {metrics.get('pending_tasks', 0)}\n"
            f"Entidades no Grafo: {metrics.get('graph_entities_count', 0)}"
        )

        prompt = WEEKLY_ANALYSIS_USER_TEMPLATE.format(
            period_str=period_str,
            weekly_messages_block=weekly_messages_block,
            weekly_metrics_block=weekly_metrics_block,
        )

        try:
            raw_response = await self.provider.generate_text(
                prompt=prompt,
                system_instruction=WEEKLY_ANALYSIS_SYSTEM_PROMPT,
                temperature=0.2,
            )
            parsed = extract_json_payload(raw_response)
        except Exception as e:
            logger.warning(f"Aviso no Relatório Semanal da IA ({e}). Gerando síntese estruturada resiliente.")
            parsed = {
                "executive_summary": f"Relatório semanal para o período {period_str}.",
                "active_projects": ["Operações e Homelab", "Automação WhatsApp"],
                "top_contacts": ["Equipe Operacional"],
                "bottlenecks": ["Prazos curtos e pendências acumuladas"],
                "tasks_metrics": {
                    "total": metrics.get("total_tasks", len(tasks)),
                    "completed": metrics.get("completed_tasks", 0),
                    "pending": metrics.get("pending_tasks", 0),
                },
                "sunday_strategic_plan": [
                    {
                        "title": "Alinhar prioridades da semana",
                        "assignee": "Usuário",
                        "priority": "HIGH",
                        "due_date": "Segunda-feira 08:00",
                        "related_project": "Geral",
                    }
                ],
            }

        sunday_plan = [
            DailyActionItem(**self._normalize_action_item(item)) if isinstance(item, dict) else item
            for item in parsed.get("sunday_strategic_plan", [])
        ]

        from src.reports.weekly import format_weekly_whatsapp_message

        whatsapp_text = format_weekly_whatsapp_message(
            period_str=period_str,
            executive_summary=parsed.get("executive_summary", ""),
            active_projects=parsed.get("active_projects", []),
            top_contacts=parsed.get("top_contacts", []),
            bottlenecks=parsed.get("bottlenecks", []),
            tasks_metrics=parsed.get("tasks_metrics", {}),
            plan=sunday_plan,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return WeeklyReportResponse(
            period=period_str,
            executive_summary=parsed.get("executive_summary", ""),
            active_projects=parsed.get("active_projects", []),
            top_contacts=parsed.get("top_contacts", []),
            bottlenecks=parsed.get("bottlenecks", []),
            tasks_metrics=parsed.get("tasks_metrics", {}),
            sunday_strategic_plan=sunday_plan,
            whatsapp_text=whatsapp_text,
            messages_analyzed=len(messages),
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            processing_time_ms=elapsed_ms,
        )


hermes_agent_service = HermesAgentService()
