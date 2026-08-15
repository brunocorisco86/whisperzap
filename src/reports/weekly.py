"""Motor de Inteligência Semanal e Plano de Domingo (20:00)."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from src.ai_gateway.agent import hermes_agent_service
from src.ai_gateway.schemas import DailyActionItem, WeeklyReportResponse
from src.memory.database import SessionLocal
from src.memory.graph import knowledge_graph
from src.memory.models import MessageRecord, TaskRecord


def format_weekly_whatsapp_message(
    period_str: str,
    executive_summary: str,
    active_projects: list[str],
    top_contacts: list[str],
    bottlenecks: list[str],
    tasks_metrics: dict,
    plan: list[DailyActionItem],
) -> str:
    """Formata o Relatório Semanal em texto estruturado e executivo para o WhatsApp."""
    lines = [
        f"📊 *RELATÓRIO SEMANAL & PLANO DE DOMINGO*",
        f"🗓️ _Período: {period_str}_\n",
        f"_{executive_summary}_\n",
    ]

    total_t = tasks_metrics.get("total", 0)
    done_t = tasks_metrics.get("completed", 0)
    pending_t = tasks_metrics.get("pending", 0)
    pct = round((done_t / total_t) * 100) if total_t > 0 else 0

    lines.append(f"📈 *Métricas de Execução:*")
    lines.append(f"• Concluídas: {done_t}/{total_t} ({pct}%) | Pendentes: {pending_t}")
    lines.append("")

    if active_projects:
        lines.append("🚀 *Projetos com Maior Tração:*")
        for proj in active_projects:
            lines.append(f"• {proj}")
        lines.append("")

    if top_contacts:
        lines.append("👥 *Pessoas & Articulações Principais:*")
        for c in top_contacts:
            lines.append(f"• {c}")
        lines.append("")

    if bottlenecks:
        lines.append("⚠️ *Gargalos & Riscos Identificados:*")
        for b in bottlenecks:
            lines.append(f"• {b}")
        lines.append("")

    lines.append("🏆 *PLANO ESTRATÉGICO PARA A PRÓXIMA SEMANA:*")
    if plan:
        for idx, item in enumerate(plan, start=1):
            assignee_str = f" ({item.assignee})" if item.assignee else ""
            due_str = f" [Prazo: {item.due_date}]" if item.due_date else ""
            lines.append(f"{idx}. 📌 *{item.title}*{assignee_str}{due_str}")
    else:
        lines.append("• Alinhamento geral de rotina.")

    lines.append("\n_Hermes Voice Memory — Inteligência Operacional_ 🧠")
    return "\n".join(lines)


class WeeklyReportService:
    """Serviço de geração e consulta do Relatório Semanal."""

    async def generate_weekly_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> WeeklyReportResponse:
        """Agrega memórias dos últimos 7 dias e orquestra a geração da Análise Semanal."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        now = datetime.now(timezone.utc)
        if not end_date:
            end_date = now.strftime("%Y-%m-%d")
        if not start_date:
            start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        period_str = f"{start_date} a {end_date}"

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

            all_msgs = db.query(MessageRecord).all()
            weekly_msgs = [
                {
                    "id": m.id,
                    "speaker": m.speaker,
                    "intent": m.intent,
                    "summary": m.summary,
                    "revised_text": m.revised_text,
                    "created_at": m.created_at.strftime("%Y-%m-%d") if m.created_at else "",
                }
                for m in all_msgs
                if m.created_at and start_dt <= m.created_at.replace(tzinfo=timezone.utc) <= end_dt
            ]

            all_tasks = db.query(TaskRecord).all()
            tasks_list = [
                {
                    "id": t.id,
                    "title": t.title,
                    "assignee": t.assignee,
                    "due_date": t.due_date,
                    "priority": t.priority,
                    "status": t.status,
                }
                for t in all_tasks
            ]

            total_tasks = len(tasks_list)
            completed_tasks = len([t for t in tasks_list if t["status"] == "DONE"])
            pending_tasks = len([t for t in tasks_list if t["status"] == "PENDING"])

            graph_stats = knowledge_graph.stats()

            metrics = {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "pending_tasks": pending_tasks,
                "graph_entities_count": graph_stats["nodes"],
                "graph_relationships_count": graph_stats["edges"],
            }

            return await hermes_agent_service.generate_weekly_report(
                period_str=period_str,
                messages=weekly_msgs,
                tasks=tasks_list,
                metrics=metrics,
            )
        finally:
            if should_close:
                db.close()


weekly_report_service = WeeklyReportService()
