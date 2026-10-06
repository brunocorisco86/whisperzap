"""Serviço de Notificações Push via ntfy (Alta Verbosidade e Observabilidade).

Permite despachar notificações ricas em Markdown para tópicos ntfy (ex: 'bruno-casa-dallas')
sem poluir o WhatsApp do usuário, com suporte a metadados completos de tarefas,
prosódia, sentimentos, transcrições e diagnósticos de sistema.
"""

import logging
from typing import Any, Dict, List, Optional
import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class NtfyNotificationService:
    """Despachante de notificações assíncronas via ntfy com formatação rica em Markdown."""

    def __init__(self):
        self.url = (getattr(settings, "NTFY_URL", "https://ntfy.sh") or "https://ntfy.sh").rstrip("/")
        self.topic = getattr(settings, "NTFY_TOPIC", "bruno-casa-dallas") or "bruno-casa-dallas"
        self.enabled = bool(getattr(settings, "NTFY_ENABLED", True) and self.topic)

    async def send_notification(
        self,
        message: str,
        title: str = "Hermes Voice Memory 🎙️",
        priority: int = 3,
        tags: Optional[List[str]] = None,
        click_url: Optional[str] = None,
    ) -> bool:
        """Envia mensagem formatada em Markdown para o tópico ntfy configurado."""
        if not self.enabled or not self.topic:
            logger.debug("Notificação ntfy ignorada (desativado ou sem tópico configurado).")
            return False

        target_url = self.url
        payload: Dict[str, Any] = {
            "topic": self.topic,
            "title": title,
            "message": message,
            "priority": priority,
            "markdown": True,
        }
        if tags:
            payload["tags"] = tags
        if click_url:
            payload["click"] = click_url

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    target_url,
                    json=payload,
                )
                if resp.status_code in (200, 201):
                    logger.info(f"📢 [ntfy] Notificação enviada para '{self.topic}': '{title}'")
                    return True
                logger.warning(f"⚠️ [ntfy] Falha ao enviar notificação ({resp.status_code}): {resp.text}")
        except Exception as exc:
            logger.warning(f"⚠️ [ntfy] Erro de rede ao conectar com ntfy ({self.url}): {exc}")

        return False

    @staticmethod
    def _sanitize_notification_text(revised_text: str, duration_s: float = 0.0) -> str:
        """Remove seções redundantes de destaques executivos em áudios curtos ou concisos."""
        clean = revised_text.strip()
        if "📌" in clean:
            parts = clean.split("📌", 1)
            main_body = parts[0].strip()
            # Se o corpo principal tem menos de 250 caracteres ou o áudio durou <= 25s,
            # os tópicos de destaques são 100% redundantes (repetem a própria frase)
            if len(main_body) < 250 or (0 < duration_s <= 25.0):
                return main_body if main_body else clean
        return clean

    async def notify_audio_processed(
        self,
        speaker: str,
        revised_text: str,
        raw_text: Optional[str] = None,
        is_self_memo: bool = False,
        contact_phone: Optional[str] = None,
        contact_role: Optional[str] = None,
        duration_s: float = 0.0,
        prosody: Optional[Dict[str, Any]] = None,
        sentiment: Optional[Dict[str, Any]] = None,
        intent: Optional[str] = None,
        tasks: Optional[List[Any]] = None,
        model_name: Optional[str] = None,
        message_id: Optional[str] = None,
        include_raw_stt: Optional[bool] = None,
    ) -> bool:
        """Formata e envia notificação de áudio processado com alta clareza e sem redundâncias."""
        title = f"🎙️ Nota Pessoal: {speaker}" if is_self_memo else f"🎙️ Áudio: {speaker}"
        prio = 3
        # Usa apenas tags essenciais para evitar festival de emojis duplicados no card do ntfy
        tags = ["memo"] if is_self_memo else ["speech_balloon"]

        tasks = tasks or []
        has_urgent = any(str(getattr(t, "priority", "")).upper() in ["URGENT", "HIGH"] for t in tasks)
        if has_urgent:
            prio = 4
            tags.append("rotating_light")

        lines = []

        # 1. Cabeçalho de Metadados
        if is_self_memo:
            speaker_line = f"**Remetente:** `{speaker}` *(Nota Pessoal)*"
        else:
            speaker_line = f"**Remetente:** `{speaker}`"
            if contact_phone and contact_phone != speaker:
                speaker_line += f" (`{contact_phone}`)"
            if contact_role:
                speaker_line += f" • Role: *{contact_role}*"
        lines.append(speaker_line)

        meta_parts = []
        if duration_s > 0:
            meta_parts.append(f"⏱️ `{duration_s:.1f}s`")
        if prosody:
            wpm = prosody.get("wpm")
            pauses = prosody.get("pauses_duration_s")
            if wpm and wpm > 0:
                meta_parts.append(f"⚡ `{wpm:.0f} WPM`")
            if pauses and pauses > 0:
                meta_parts.append(f"⏸️ `{pauses:.1f}s pausas`")
        if model_name:
            meta_parts.append(f"🤖 `{model_name}`")
        if meta_parts:
            lines.append(" • ".join(meta_parts))

        # 2. Transcrição Sanitizada
        clean_text = self._sanitize_notification_text(revised_text, duration_s=duration_s)
        lines.append("")
        lines.append("### 📝 Transcrição:")
        lines.append(f"> {clean_text}")

        # Texto bruto só é exibido se explicitamente configurado ou solicitado
        should_include_raw = (
            include_raw_stt if include_raw_stt is not None else getattr(settings, "NTFY_INCLUDE_RAW_STT", False)
        )
        if should_include_raw and raw_text and raw_text.strip() != clean_text:
            lines.append("")
            lines.append(f"<details><summary>🔍 Ver texto bruto STT (Whisper)</summary>\n\n> {raw_text.strip()}\n</details>")

        # 3. Classificação e Sentimento (Filtrando redundâncias e neutros inertes)
        meta_badges = []
        # Não exibir "Intenção: Tarefa" se já listamos a seção de Tarefas abaixo
        if intent and (intent != "TASK" or not tasks):
            intent_icons = {"TASK": "📋 Tarefa", "IDEA": "💡 Ideia", "DECISION": "⚖️ Decisão", "MEMO": "📝 Nota", "QUESTION": "❓ Pergunta"}
            meta_badges.append(f"**Intenção:** `{intent_icons.get(intent, intent)}`")

        if sentiment:
            pol = sentiment.get("polarity", "NEUTRAL")
            score = float(sentiment.get("sentiment_score", 0.0) or 0.0)
            # Só exibe se houver sentimento expressivo (evita ruído com NEUTRAL +0.00)
            if pol not in ("NEUTRAL", None) or abs(score) >= 0.20:
                pol_icon = "🟢" if pol == "POSITIVE" else ("🔴" if pol in ("NEGATIVE", "FRUSTRATED", "ANXIOUS", "URGENT") else "⚪")
                meta_badges.append(f"**Sentimento:** {pol_icon} `{pol}` (`{score:+.2f}`)")

        if meta_badges:
            lines.append("")
            lines.append(" • ".join(meta_badges))

        # 4. Tarefas Terpsícore
        if tasks:
            lines.append("")
            lines.append(f"### 📋 Tarefas Capturadas ({len(tasks)}):")
            for t in tasks:
                t_prio = (getattr(t, "priority", "") or "MEDIUM").upper()
                p_icon = "🔴" if t_prio == "URGENT" else ("🟠" if t_prio == "HIGH" else "🔵")
                due = f" • 📅 `{t.due_date}`" if getattr(t, "due_date", None) else ""
                resp_name = f" • 👤 `{t.assignee}`" if (getattr(t, "assignee", None) and getattr(t, "assignee", "") != speaker) else ""
                vault = " • 🏛️ *[Vault]*" if getattr(t, "in_vault", False) else ""
                lines.append(f"- {p_icon} **[{t_prio}]** {t.title}{due}{resp_name}{vault}")

        body = "\n".join(lines)
        return await self.send_notification(message=body, title=title, priority=prio, tags=tags)

    async def notify_pdf_processed(
        self,
        filename: str,
        speaker: str,
        page_count: int,
        size_bytes: int,
        tier_used: str,
        model_name: str,
        summary: Optional[str] = None,
        tasks: Optional[List[Any]] = None,
        is_self_memo: bool = False,
    ) -> bool:
        """Formata e envia notificação completa de extração de PDF."""
        title = f"📄 Documento Processado: {filename}"
        size_mb = size_bytes / (1024 * 1024) if size_bytes > 0 else 0.0

        lines = [
            f"**Arquivo:** `{filename}` ({page_count} pág{'s' if page_count > 1 else ''} • `{size_mb:.2f} MB`)",
            f"**Origem:** `{speaker}` • Motor: `{tier_used}` (`{model_name}`)",
        ]

        if summary:
            lines.append("")
            lines.append("### 📝 Resumo Executivo:")
            lines.append(f"> {summary.strip()}")

        tasks = tasks or []
        if tasks:
            lines.append("")
            lines.append(f"### 📋 Tarefas Identificadas ({len(tasks)}):")
            for t in tasks:
                t_prio = (getattr(t, "priority", "") or "MEDIUM").upper()
                p_icon = "🔴" if t_prio == "URGENT" else ("🟠" if t_prio == "HIGH" else "🔵")
                due = f" • 📅 `{t.due_date}`" if getattr(t, "due_date", None) else ""
                lines.append(f"- {p_icon} **[{t_prio}]** {t.title}{due}")

        body = "\n".join(lines)
        return await self.send_notification(
            message=body,
            title=title,
            priority=3,
            tags=["page_facing_up", "pdf", "file_folder"],
        )

    async def notify_scheduled_report(
        self,
        title: str,
        report_text: str,
        report_type: str = "daily",
    ) -> bool:
        """Envia relatório diário ou semanal com formatação executiva."""
        tags = ["calendar", "chart_with_upwards_trend"] if report_type == "daily" else ["bar_chart", "clipboard"]
        return await self.send_notification(
            message=report_text,
            title=title,
            priority=4,
            tags=tags,
        )

    async def notify_system_event(
        self,
        title: str,
        details: str,
        level: str = "INFO",
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Envia evento ou alerta de saúde do sistema (watchdog, auto-cura, circuit-breaker)."""
        level_upper = level.upper()
        prio = 5 if level_upper in ["ERROR", "CRITICAL"] else (4 if level_upper == "WARNING" else 2)
        default_tags = ["warning", "robot"] if prio >= 4 else ["white_check_mark", "gear"]
        return await self.send_notification(
            message=details,
            title=title,
            priority=prio,
            tags=tags or default_tags,
        )


ntfy_service = NtfyNotificationService()
