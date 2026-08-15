"""Motor de Consolidação e Formatação do Resumo Diário (18:00)."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from src.ai_gateway.agent import hermes_agent_service
from src.ai_gateway.schemas import DailyActionItem, DailySummaryResponse
from src.memory.database import SessionLocal
from src.memory.models import MessageRecord, TaskRecord


def format_daily_whatsapp_message(
    date_str: str,
    executive_summary: str,
    key_events: list[str],
    decisions: list[str],
    issues: list[str],
    completed_tasks: list[str],
    pending_tasks: list[str],
    plan: list[DailyActionItem],
) -> str:
    """Formata o Resumo Diário em texto elegante e legível para o WhatsApp."""
    # Converte data para formato amigável (DD/MM/YYYY)
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        friendly_date = dt.strftime("%d/%m/%Y")
    except Exception:
        friendly_date = date_str

    lines = [
        f"📅 *RESUMO DIÁRIO — {friendly_date}*",
        f"_{executive_summary}_\n",
    ]

    if key_events:
        lines.append("🚀 *Principais Acontecimentos:*")
        for ev in key_events:
            lines.append(f"• {ev}")
        lines.append("")

    if decisions:
        lines.append("💡 *Decisões & Acordos:*")
        for dec in decisions:
            lines.append(f"• {dec}")
        lines.append("")

    if issues:
        lines.append("⚠️ *Pontos de Atenção / Bloqueios:*")
        for iss in issues:
            lines.append(f"• {iss}")
        lines.append("")

    if completed_tasks:
        lines.append(f"✅ *Concluídas Hoje ({len(completed_tasks)}):*")
        for t in completed_tasks[:5]:
            lines.append(f"• {t}")
        lines.append("")

    if pending_tasks:
        lines.append(f"⏳ *Pendências Ativas ({len(pending_tasks)}):*")
        for t in pending_tasks[:5]:
            lines.append(f"• {t}")
        lines.append("")

    lines.append("🎯 *PLANO PARA AMANHÃ:*")
    if plan:
        for idx, item in enumerate(plan, start=1):
            assignee_str = f" ({item.assignee})" if item.assignee else ""
            priority_icon = "🔴" if item.priority in ["HIGH", "URGENT"] else "🔵"
            lines.append(f"{idx}. {priority_icon} *{item.title}*{assignee_str}")
    else:
        lines.append("• Nenhuma ação prioritária cadastrada para amanhã.")

    lines.append("\n_Enviado pelo Hermes Voice Memory_ 🧠")
    return "\n".join(lines)


class DailyReportService:
    """Serviço de geração e consulta do Resumo Diário."""

    async def generate_daily_report(
        self,
        target_date: Optional[str] = None,
        speaker_filter: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> DailySummaryResponse:
        """Coleta as memórias do dia e orquestra a geração do Resumo Diário."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        if not target_date:
            target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        try:
            # Busca mensagens do dia
            msg_query = db.query(MessageRecord)
            if speaker_filter:
                msg_query = msg_query.filter(MessageRecord.speaker == speaker_filter)

            all_msgs = msg_query.all()
            day_msgs = [
                {
                    "id": m.id,
                    "speaker": m.speaker,
                    "intent": m.intent,
                    "summary": m.summary,
                    "revised_text": m.revised_text,
                    "created_at": m.created_at.strftime("%Y-%m-%d %H:%M"),
                }
                for m in all_msgs
                if m.created_at and m.created_at.strftime("%Y-%m-%d") == target_date
            ]

            # Busca tarefas do dia ou tarefas pendentes gerais
            all_tasks = db.query(TaskRecord).all()
            tasks_list = [
                {
                    "id": t.id,
                    "title": t.title,
                    "assignee": t.assignee,
                    "due_date": t.due_date,
                    "priority": t.priority,
                    "status": t.status,
                    "created_at": t.created_at.strftime("%Y-%m-%d") if t.created_at else None,
                }
                for t in all_tasks
                if (t.created_at and t.created_at.strftime("%Y-%m-%d") == target_date) or t.status == "PENDING"
            ]

            return await hermes_agent_service.generate_daily_summary(
                target_date=target_date,
                messages=day_msgs,
                tasks=tasks_list,
            )
        finally:
            if should_close:
                db.close()


daily_report_service = DailyReportService()
