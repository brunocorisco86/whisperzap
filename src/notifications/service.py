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
        self.topic = settings.ntfy_general_topic
        self.family_topic = settings.ntfy_family_topic
        self.enabled = bool(getattr(settings, "NTFY_ENABLED", True) and (self.topic or self.family_topic))

    def get_target_topic(self, is_family: bool = False) -> str:
        """Retorna o tópico correspondente (família ou geral) a partir das variáveis de ambiente."""
        if is_family and self.family_topic:
            return self.family_topic
        return self.topic

    async def send_notification(
        self,
        message: str,
        title: str = "Hermes Voice Memory 🎙️",
        priority: int = 3,
        tags: Optional[List[str]] = None,
        click_url: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> bool:
        """Envia mensagem formatada em Markdown para o tópico ntfy configurado via ambiente."""
        target_topic = topic or self.topic
        if not self.enabled or not target_topic:
            logger.debug("Notificação ntfy ignorada (desativado ou sem tópico configurado).")
            return False

        target_url = self.url
        payload: Dict[str, Any] = {
            "topic": target_topic,
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
                    logger.info(f"📢 [ntfy] Notificação enviada para '{target_topic}': '{title}'")
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
        topic: Optional[str] = None,
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
        return await self.send_notification(message=body, title=title, priority=prio, tags=tags, topic=topic)

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
        topic: Optional[str] = None,
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
            topic=topic,
        )

    async def notify_family_message(
        self,
        speaker: str,
        text: str,
        message_type: str = "text",  # "audio", "text", "pdf"
        is_wife: bool = False,
        relationship: str = "Família",
        contact_phone: Optional[str] = None,
        duration_s: float = 0.0,
        prosody: Optional[Dict[str, Any]] = None,
        sentiment: Optional[Dict[str, Any]] = None,
        tasks: Optional[List[Any]] = None,
        raw_text: Optional[str] = None,
        model_name: Optional[str] = None,
        filename: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> bool:
        """Envia notificação de alta visibilidade e prioridade para o tópico exclusivo da Família."""
        target_topic = self.family_topic or self.topic
        tasks = tasks or []

        # Título, Prioridade e Tags específicos
        if is_wife:
            prio = 4
            if message_type == "audio":
                title = "❤️ Débora (Esposa) 🎙️ Áudio"
                tags = ["heart", "ring", "microphone"]
            elif message_type == "pdf":
                title = f"❤️ Débora (Esposa) 📄 {filename or 'Documento'}"
                tags = ["heart", "ring", "page_facing_up"]
            else:
                title = "❤️ Débora (Esposa) 💬 Mensagem"
                tags = ["heart", "ring", "speech_balloon"]
        else:
            rel_label = f" ({relationship})" if relationship else ""
            prio = 4
            if message_type == "audio":
                title = f"👨‍👩‍👧‍👦 {speaker}{rel_label} 🎙️ Áudio"
                tags = ["family", "microphone", "speech_balloon"]
            elif message_type == "pdf":
                title = f"👨‍👩‍👧‍👦 {speaker}{rel_label} 📄 {filename or 'Documento'}"
                tags = ["family", "page_facing_up", "file_folder"]
            else:
                title = f"👨‍👩‍👧‍👦 {speaker}{rel_label} 💬 Mensagem"
                tags = ["family", "speech_balloon"]

        # Se houver tarefas com alta urgência, eleva a prioridade para o nível máximo
        has_urgent = any(str(getattr(t, "priority", "")).upper() in ["URGENT", "HIGH"] for t in tasks)
        if has_urgent:
            prio = 5
            tags.append("rotating_light")

        lines = []

        # 1. Metadados do Remetente
        speaker_line = f"**Remetente:** `{speaker}`"
        if contact_phone and contact_phone != speaker:
            speaker_line += f" (`{contact_phone}`)"
        if relationship:
            speaker_line += f" • Relação: *{relationship}*"
        lines.append(speaker_line)

        meta_parts = []
        if message_type == "audio":
            if duration_s > 0:
                meta_parts.append(f"⏱️ `{duration_s:.1f}s`")
            if prosody:
                wpm = prosody.get("wpm")
                pauses = prosody.get("pauses_duration_s")
                if wpm:
                    meta_parts.append(f"⚡ `{wpm:.0f} WPM`")
                if pauses:
                    meta_parts.append(f"⏸️ `{pauses:.1f}s pausas`")
            if model_name:
                meta_parts.append(f"🤖 `{model_name}`")
        elif message_type == "pdf" and filename:
            meta_parts.append(f"📁 `{filename}`")
        if meta_parts:
            lines.append(" • ".join(meta_parts))

        # 2. Conteúdo Principal
        lines.append("")
        if message_type == "audio":
            lines.append("### 📝 Transcrição:")
            lines.append(f"> {text.strip()}")
            if raw_text and raw_text.strip() != text.strip():
                lines.append("")
                lines.append(f"<details><summary>🔍 Ver texto bruto STT</summary>\n\n> {raw_text.strip()}\n</details>")
        elif message_type == "pdf":
            lines.append("### 📄 Resumo do Documento:")
            lines.append(f"> {(summary or text).strip()}")
        else:
            lines.append("### 💬 Mensagem:")
            lines.append(f"> {text.strip()}")

        # 3. Sentimento
        if sentiment:
            pol = sentiment.get("polarity", "NEUTRAL")
            score = sentiment.get("sentiment_score", 0.0)
            pol_icon = "🟢" if pol == "POSITIVE" else ("🔴" if pol == "NEGATIVE" else "⚪")
            lines.append("")
            lines.append(f"**Sentimento:** {pol_icon} `{pol}` (`{score:+.2f}`)")

        # 4. Tarefas Terpsícore
        if tasks:
            lines.append("")
            lines.append(f"### 📋 Tarefas Capturadas ({len(tasks)}):")
            for t in tasks:
                t_prio = (getattr(t, "priority", "") or "MEDIUM").upper()
                p_icon = "🔴" if t_prio == "URGENT" else ("🟠" if t_prio == "HIGH" else "🔵")
                due = f" • 📅 `{t.due_date}`" if getattr(t, "due_date", None) else ""
                lines.append(f"- {p_icon} **[{t_prio}]** {t.title}{due}")

        body = "\n".join(lines)
        return await self.send_notification(
            message=body,
            title=title,
            priority=prio,
            tags=tags,
            topic=target_topic,
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
    async def notify_image_processed(
        self,
        speaker: str,
        summary: str,
        is_document: bool = False,
        detected_objects: Optional[List[Any]] = None,
        caption: Optional[str] = None,
        contact_phone: Optional[str] = None,
        is_self_memo: bool = False,
        topic: Optional[str] = None,
    ) -> bool:
        """Formata e envia notificação de foto/imagem processada localmente com zero tokens."""
        # Sanitiza speaker para evitar duplicação de "(Nota Pessoal)"
        speaker_clean = speaker.replace(" (Nota Pessoal)", "").strip()
        title = f"Foto Pessoal: {speaker_clean}" if is_self_memo else f"Foto Recebida: {speaker_clean}"
        tags = ["camera", "page_facing_up"] if is_document else ["camera", "package"]
        prio = 3

        lines = []
        if is_self_memo:
            lines.append(f"👤 **Remetente:** `{speaker_clean}` *(Nota Pessoal)*")
        else:
            spk_line = f"👤 **Remetente:** `{speaker_clean}`"
            if contact_phone and contact_phone != speaker_clean:
                spk_line += f" (`{contact_phone}`)"
            lines.append(spk_line)

        lines.append("⚡ **Motor:** `YOLO11n ONNX Local (Zero-Token)`")
        lines.append("")

        if caption and caption.strip():
            lines.append(f"📝 **Legenda do Remetente:**\n_{caption.strip()}_")
            lines.append("")

        if is_document:
            lines.append("📄 **Classificação:** `Nota Fiscal / Documento Impresso`")

        if detected_objects:
            obj_labels = []
            for obj in detected_objects:
                label = getattr(obj, "label", str(obj))
                conf = getattr(obj, "confidence", None)
                conf_str = f" ({int(conf * 100)}%)" if conf else ""
                obj_labels.append(f"`{label}{conf_str}`")
            lines.append(f"🔍 **Objetos Identificados:**\n• " + ", ".join(obj_labels))
        elif summary:
            lines.append(f"🔍 **Análise Visual:** _{summary}_")

        lines.append("")
        lines.append("🔗 **Grafo & Memória:** Registrado no histórico com zero custo de tokens.")

        body = "\n".join(lines)
        return await self.send_notification(
            message=body,
            title=title,
            priority=prio,
            tags=tags,
            topic=topic,
        )


ntfy_service = NtfyNotificationService()
