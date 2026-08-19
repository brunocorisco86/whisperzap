"""Script de Backfill & Cura de Sentimentos 100% Offline (Zero Custo de Tokens / Zero APIs).

Processa mensagens históricas no PostgreSQL utilizando regras heurísticas locais e spaCy,
atribuindo sentimentos e scores realistas e gerando os snapshots diários de Erato para todas as datas passadas.
"""

import sys
import re
from datetime import datetime, timezone
from sqlalchemy import func

from src.memory.database import SessionLocal
from src.memory.models import MessageRecord, DailySentimentSnapshotRecord
from src.memory.sentiment_timeline import sentiment_timeline_service

POSITIVE_KEYWORDS = {
    "obrigado", "obrigada", "ótimo", "otimo", "perfeito", "excelente", "parabéns", "parabens",
    "sucesso", "combinado", "certo", "maravilha", "fechado", "confirmado", "beleza", "aprovado",
    "consegui", "tranquilo", "top", "recomendo", "agradeço", "agradeco", "show", "valeu",
}

CONFIDENT_KEYWORDS = {
    "garantido", "resolvido", "concluído", "concluido", "alinhado", "pronto", "finalizado",
    "atualizado", "implantado", "em dia", "certeza", "fechamos",
}

URGENT_KEYWORDS = {
    "urgente", "urgência", "urgencia", "emergência", "emergencia", "socorro", "crítico", "critico",
    "imediatamente", "agora mesmo", "parou", "travou", "quebrou", "apagou", "grave",
}

FRUSTRATED_KEYWORDS = {
    "problema", "problemas", "erro", "erros", "falha", "falhas", "atraso", "atrasos",
    "reclamação", "reclamacao", "estragou", "perda", "perdas", "prejuízo", "prejuizo",
    "complicado", "difícil", "dificil", "ruim", "péssimo", "pessimo", "cobrança", "cobranca",
}

ANXIOUS_KEYWORDS = {
    "dúvida", "duvida", "dúvidas", "duvidas", "quando", "cadê", "cade", "não sei", "nao sei",
    "aguardo", "aguardando", "pendente", "pendência", "pendencia", "resposta", "retorno",
}


def analyze_text_offline(text: str, summary: str = "", urgency: str = "MEDIUM") -> tuple[str, float]:
    """Classifica tom emocional do texto localmente sem nenhuma chamada externa."""
    full_text = ((text or "") + " " + (summary or "")).lower()
    
    # Checa urgência do registro
    if urgency in ("HIGH", "URGENT"):
        return "URGENT", -0.75

    tokens = set(re.findall(r"\b[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{3,}\b", full_text))

    if tokens & URGENT_KEYWORDS:
        return "URGENT", -0.80
    if tokens & FRUSTRATED_KEYWORDS:
        return "FRUSTRATED", -0.60
    if tokens & ANXIOUS_KEYWORDS:
        return "ANXIOUS", -0.35
    if tokens & CONFIDENT_KEYWORDS:
        return "CONFIDENT", 0.80
    if tokens & POSITIVE_KEYWORDS:
        return "POSITIVE", 0.70

    return "NEUTRAL", 0.0


from src.transcriber.prosody_analyzer import prosody_analyzer


def run_backfill():
    """Executa a cura retroativa no banco de dados."""
    db = SessionLocal()
    try:
        messages = db.query(MessageRecord).all()
        print(f"📊 Total de mensagens no banco: {len(messages)}")

        updated_count = 0
        prosody_count = 0
        for m in messages:
            changed = False
            meta = dict(m.meta_info or {})

            # 1. Enriquecimento de Prosódia Acústica para áudios
            if m.audio_duration_s and "prosody" not in meta:
                prosody_obj = prosody_analyzer.analyze_speech_prosody(
                    duration=m.audio_duration_s,
                    segments=[],
                    text=m.revised_text or m.raw_text or "",
                )
                meta["prosody"] = prosody_obj.model_dump()
                m.meta_info = meta
                changed = True
                prosody_count += 1

            # 2. Se a mensagem tiver sentimento neutro com score 0, tenta enriquecer
            if (not m.sentiment or m.sentiment == "NEUTRAL") and (m.sentiment_score is None or m.sentiment_score == 0.0):
                new_sent, new_score = analyze_text_offline(m.revised_text or m.raw_text or "", m.summary or "", m.urgency or "MEDIUM")
                if new_sent != "NEUTRAL":
                    m.sentiment = new_sent
                    m.sentiment_score = new_score
                    changed = True
                    updated_count += 1

        db.commit()
        print(f"✨ Mensagens atualizadas com novos sentimentos: {updated_count}")
        print(f"🎙️ Mensagens de áudio enriquecidas com Prosódia Acústica: {prosody_count}")

        # Identifica todas as datas presentes nas mensagens
        dates = (
            db.query(func.date(MessageRecord.created_at))
            .distinct()
            .order_by(func.date(MessageRecord.created_at).asc())
            .all()
        )

        print(f"📅 Gerando snapshots diários para {len(dates)} data(s) no Erato...")
        total_snaps = 0
        for (d,) in dates:
            if d:
                d_str = str(d)
                res = sentiment_timeline_service.collect_daily_sentiments(target_date=d_str, db=db)
                total_snaps += len(res.snapshots)
                print(f"   ➔ Data {d_str}: {res.total_people} pessoa(s), {res.total_interactions} interações, {len(res.snapshots)} snapshots.")

        print(f"🎉 Backfill concluído com sucesso! Total de {total_snaps} snapshots gerados no Erato.")
    finally:
        db.close()


if __name__ == "__main__":
    run_backfill()
