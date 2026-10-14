"""Script de Backfill & Cura de Sentimentos 100% Offline (Zero Custo de Tokens / Zero APIs).

Processa mensagens históricas no PostgreSQL utilizando regras heurísticas locais,
atribuindo sentimentos, métricas prosódicas calibradas e gerando os snapshots diários
de Erato para todas as datas passadas sem consumir CPU ou APIs externas.
"""

import sys
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

from src.memory.database import SessionLocal
from src.memory.models import MessageRecord, DailySentimentSnapshotRecord
from src.memory.sentiment_timeline import sentiment_timeline_service
from src.transcriber.prosody_analyzer import prosody_analyzer
from src.ai_gateway.sentiment_analyzer import fast_sentiment_analyzer


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

            # 1. Enriquecimento / Recalibração de Prosódia Acústica para áudios
            if m.audio_duration_s:
                current_prosody = meta.get("prosody") or {}
                # Recalcula se ausente ou se estava marcada como o antigo neutro padrão
                if not current_prosody or current_prosody.get("voice_tone") == "NEUTRO":
                    prosody_obj = prosody_analyzer.analyze_speech_prosody(
                        duration=m.audio_duration_s,
                        segments=[],
                        text=m.revised_text or m.raw_text or "",
                    )
                    meta["prosody"] = prosody_obj.model_dump()
                    m.meta_info = meta
                    flag_modified(m, "meta_info")
                    changed = True
                    prosody_count += 1

            # 2. Recalibra o sentimento de forma consistente através do analisador léxico-prosódico afinado
            prosody_data = meta.get("prosody") or {}
            v_tone = prosody_data.get("voice_tone")
            ac_score = prosody_data.get("acoustic_score")

            res = fast_sentiment_analyzer.analyze(
                text=m.revised_text or m.raw_text or "",
                summary=m.summary or "",
                urgency=m.urgency or "MEDIUM",
                prosody_tone=v_tone,
                acoustic_score=ac_score,
            )
            if res.sentiment != m.sentiment or (res.sentiment_score != m.sentiment_score and res.confidence >= 0.50):
                m.sentiment = res.sentiment
                m.sentiment_score = res.sentiment_score
                changed = True
                updated_count += 1

            if changed:
                db.add(m)

        db.commit()
        print(f"✨ Mensagens atualizadas com novos sentimentos: {updated_count}")
        print(f"🎙️ Mensagens de áudio enriquecidas/recalibradas com Prosódia: {prosody_count}")

        # Limpa snapshots antigos corrompidos ou descalibrados
        deleted_snapshots = db.query(DailySentimentSnapshotRecord).delete()
        db.commit()
        print(f"🧹 Snapshots antigos higienizados do banco: {deleted_snapshots}")

        # Identifica todas as datas presentes nas mensagens
        dates = (
            db.query(func.date(MessageRecord.created_at))
            .distinct()
            .order_by(func.date(MessageRecord.created_at).asc())
            .all()
        )

        print(f"📅 Gerando snapshots diários limpos para {len(dates)} data(s) no Erato...")
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
