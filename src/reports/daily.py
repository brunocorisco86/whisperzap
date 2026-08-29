"""Motor de Consolidação e Formatação do Resumo Diário (18:00)."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from src.ai_gateway.agent import hermes_agent_service
from src.ai_gateway.schemas import DailyActionItem, DailySummaryResponse
from src.memory.database import SessionLocal
from src.memory.models import MessageRecord, TaskRecord
from src.memory.timezone_utils import get_now_brt, to_local_tz, format_brt


def deduplicate_list(items: list[str]) -> list[str]:
    """Remove repetições mantendo a ordem original e ignorando strings vazias."""
    seen = set()
    result = []
    for item in items:
        cleaned = item.strip() if isinstance(item, str) else str(item)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


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

    # Deduplica seções para evitar repetições
    unique_key_events = deduplicate_list(key_events)
    unique_decisions = deduplicate_list(decisions)
    unique_issues = deduplicate_list(issues)
    unique_completed = deduplicate_list(completed_tasks)
    unique_pending = deduplicate_list(pending_tasks)

    # Deduplica plano de ação por título
    unique_plan = []
    seen_plan = set()
    for item in plan:
        if item.title.strip() not in seen_plan:
            seen_plan.add(item.title.strip())
            unique_plan.append(item)

    lines = [
        f"📅 *RESUMO DIÁRIO — {friendly_date}*",
        f"_{executive_summary}_\n",
    ]

    if unique_key_events:
        lines.append("🚀 *Principais Acontecimentos:*")
        for ev in unique_key_events[:5]:
            lines.append(f"• {ev}")
        lines.append("")

    if unique_decisions:
        lines.append("💡 *Decisões & Acordos:*")
        for dec in unique_decisions[:5]:
            lines.append(f"• {dec}")
        lines.append("")

    if unique_issues:
        lines.append("⚠️ *Pontos de Atenção / Bloqueios:*")
        for iss in unique_issues[:5]:
            lines.append(f"• {iss}")
        lines.append("")

    if unique_completed:
        lines.append(f"✅ *Concluídas Hoje ({len(unique_completed)}):*")
        for t in unique_completed[:5]:
            lines.append(f"• {t}")
        lines.append("")

    if unique_pending:
        lines.append(f"⏳ *Pendências Ativas ({len(unique_pending)}):*")
        for t in unique_pending[:5]:
            lines.append(f"• {t}")
        lines.append("")

    lines.append("🎯 *PLANO PARA AMANHÃ:*")
    if unique_plan:
        for idx, item in enumerate(unique_plan, start=1):
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
            target_date = get_now_brt().strftime("%Y-%m-%d")

        try:
            # Busca mensagens do dia considerando o fuso horário de Brasília
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
                    "created_at": format_brt(m.created_at),
                }
                for m in all_msgs
                if m.created_at and to_local_tz(m.created_at) and to_local_tz(m.created_at).strftime("%Y-%m-%d") == target_date
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
                    "created_at": format_brt(t.created_at, "%Y-%m-%d") if t.created_at else None,
                }
                for t in all_tasks
                if (t.created_at and to_local_tz(t.created_at) and to_local_tz(t.created_at).strftime("%Y-%m-%d") == target_date) or t.status == "PENDING"
            ]

            # Executa a coleta e consolidação dos sentimentos 'as is' para a série temporal
            try:
                from src.memory.sentiment_timeline import sentiment_timeline_service
                sentiment_timeline_service.collect_daily_sentiments(target_date=target_date, db=db)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(f"Aviso ao consolidar sentimentos diários: {exc}")

            return await hermes_agent_service.generate_daily_summary(
                target_date=target_date,
                messages=day_msgs,
                tasks=tasks_list,
            )
        finally:
            if should_close:
                db.close()

    async def generate_serenity_closing(
        self,
        target_date: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> str:
        """Gera a mensagem de Fechamento Sereno das 21:00 BRT com foco em descompressão e calma."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        if not target_date:
            target_date = get_now_brt().strftime("%Y-%m-%d")

        try:
            from src.memory.repository import memory_repository
            try:
                dt = datetime.strptime(target_date, "%Y-%m-%d")
                friendly_date = dt.strftime("%d/%m/%Y")
            except Exception:
                friendly_date = target_date

            all_tasks = db.query(TaskRecord).all()
            today_completed = [
                t for t in all_tasks
                if t.status == "DONE" and t.completed_at and to_local_tz(t.completed_at) and to_local_tz(t.completed_at).strftime("%Y-%m-%d") == target_date
            ]

            active_tasks = memory_repository.list_tasks(view_mode="active", status="PENDING", db=db)
            vault_tasks = memory_repository.list_tasks(view_mode="vault", status="PENDING", db=db)

            # Seleciona no máximo 3 prioridades para amanhã
            top_tomorrow = active_tasks[:3]

            lines = [
                f"🌙 *FECHAMENTO SERENO — {friendly_date} (21:00)*",
                f"_Descanse com a certeza de que seu dia foi produtivo e sua mente está livre de pendências soltas._\n",
            ]

            if today_completed:
                lines.append(f"✨ *Conquistas de Hoje ({len(today_completed)}):*")
                for t in today_completed[:4]:
                    is_idea_badge = " 💡" if t.is_idea else ""
                    lines.append(f"• ✅ {t.title}{is_idea_badge}")
                lines.append("")
            else:
                lines.append("✨ *O dia de hoje foi de reflexão, alinhamentos e planejamento.*\n")

            lines.append("🎯 *FOCO ESSENCIAL PARA AMANHÃ (Apenas o Vital):*")
            if top_tomorrow:
                for idx, t in enumerate(top_tomorrow, start=1):
                    p_icon = "🔴" if t.priority in ["HIGH", "URGENT"] else "🔵"
                    assignee_str = f" ({t.assignee})" if t.assignee else ""
                    fav_icon = " ⭐" if t.is_favorite else ""
                    epic_icon = " 🏛️" if t.is_epic else ""
                    lines.append(f"{idx}. {p_icon} *{t.title}*{fav_icon}{epic_icon}{assignee_str}")
            else:
                lines.append("• Nenhuma tarefa urgente. O fluxo está calmo e livre para novos projetos.")

            lines.append("")
            vault_count = len(vault_tasks)
            if vault_count > 0:
                lines.append(
                    f"🗝️ *No Baú de Espera (Vault):*\n"
                    f"_{vault_count} tarefas de prazo estendido estão guardadas com segurança no seu Baú. "
                    f"Você não precisa se preocupar com elas esta noite._"
                )
            else:
                lines.append("🗝️ *Baú de Espera (Vault):* Todas as suas ideias e tarefas estão sincronizadas.")

            lines.append("\n🌿 _\"A serenidade vem de saber que o essencial está organizado e o restante seguro no Baú.\"_")
            lines.append("_Tenha uma ótima noite de descanso e serenidade!_ 😴✨")

            return "\n".join(lines)
        finally:
            if should_close:
                db.close()


daily_report_service = DailyReportService()
