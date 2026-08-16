"""Serviço de Coleta e Análise de Séries Temporais de Sentimentos por Pessoa."""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from sqlalchemy.orm import Session

from src.contacts.models import ContactRecord
from src.memory.database import SessionLocal
from src.memory.models import (
    DailySentimentCollectionResponse,
    DailySentimentSnapshotRecord,
    DailySentimentSnapshotResponse,
    MessageRecord,
    PersonSentimentTimelineResponse,
    SentimentTimelinePoint,
)

logger = logging.getLogger(__name__)


def compute_dominant_sentiment(pos: int, neu: int, neg: int) -> tuple[str, float]:
    """Calcula o sentimento dominante e o score médio ponderado de -1.0 a +1.0."""
    total = pos + neu + neg
    if total == 0:
        return "NEUTRAL", 0.0

    score = round((pos * 1.0 + neu * 0.0 + neg * (-1.0)) / total, 3)

    if pos > neu and pos > neg:
        dominant = "POSITIVE"
    elif neg > neu and neg > pos:
        dominant = "NEGATIVE"
    elif pos > 0 and neg > 0 and abs(pos - neg) <= 1:
        dominant = "MIXED"
    else:
        dominant = "NEUTRAL"

    return dominant, score


class SentimentTimelineService:
    """Serviço para consolidar snapshots diários e gerar séries temporais de humor/sentimento."""

    def collect_daily_sentiments(
        self,
        target_date: Optional[str] = None,
        db: Session | None = None,
    ) -> DailySentimentCollectionResponse:
        """Consolida as mensagens do dia 'as is', computa a distribuição emocional e persiste no banco SQL."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            if not target_date:
                target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Busca todas as mensagens da data
            messages = (
                db.query(MessageRecord)
                .filter(MessageRecord.created_at.like(f"{target_date}%"))
                .order_by(MessageRecord.created_at.asc())
                .all()
            )

            # Agrupa por speaker
            person_messages = defaultdict(list)
            for m in messages:
                speaker_name = (m.speaker or "Desconhecido").strip()
                if speaker_name:
                    person_messages[speaker_name].append(m)

            snapshots_responses: list[DailySentimentSnapshotResponse] = []
            total_interactions = len(messages)

            from src.ai_gateway.bypass import is_owner_interaction

            for speaker, msgs in person_messages.items():
                # Ignora interações do próprio usuário/proprietário do termômetro de sentimentos de contatos
                sample_meta = msgs[0].meta_info if (msgs and isinstance(msgs[0].meta_info, dict)) else {}
                if is_owner_interaction(speaker, sample_meta):
                    continue

                pos = 0
                neu = 0
                neg = 0
                highlights = []

                for msg in msgs:
                    sent = (msg.sentiment or "NEUTRAL").upper()
                    if sent in ["POSITIVE", "POSITIVO"]:
                        pos += 1
                    elif sent in ["NEGATIVE", "NEGATIVO"]:
                        neg += 1
                    else:
                        neu += 1

                    summary_or_text = msg.summary or (msg.revised_text[:90] if msg.revised_text else "")
                    if summary_or_text and summary_or_text not in highlights:
                        highlights.append(f"[{sent}] {summary_or_text}")

                dominant_sent, avg_score = compute_dominant_sentiment(pos, neu, neg)

                # Busca metadados do contato se existir
                contact = db.query(ContactRecord).filter(
                    (ContactRecord.name.ilike(speaker)) | (ContactRecord.phone_number == speaker)
                ).first()

                role_val = contact.role if contact else "UNKNOWN"
                phone_val = contact.phone_number if contact else None

                # Gera síntese emocional breve
                if dominant_sent == "POSITIVE":
                    mood_summary = f"{len(msgs)} interação(ões) com tom colaborativo e receptivo."
                elif dominant_sent == "NEGATIVE":
                    mood_summary = f"{len(msgs)} interação(ões) com tom de preocupação, atrito ou urgência crítica."
                elif dominant_sent == "MIXED":
                    mood_summary = f"{len(msgs)} interação(ões) com oscilação entre tópicos positivos e pontos de atenção."
                else:
                    mood_summary = f"{len(msgs)} interação(ões) informativas e operacionais neutras."

                # Salva ou atualiza snapshot diário idempotente
                existing_snapshot = db.query(DailySentimentSnapshotRecord).filter(
                    (DailySentimentSnapshotRecord.date == target_date)
                    & (DailySentimentSnapshotRecord.speaker == speaker)
                ).first()

                if existing_snapshot:
                    existing_snapshot.interactions_count = len(msgs)
                    existing_snapshot.dominant_sentiment = dominant_sent
                    existing_snapshot.avg_sentiment_score = avg_score
                    existing_snapshot.positive_count = pos
                    existing_snapshot.neutral_count = neu
                    existing_snapshot.negative_count = neg
                    existing_snapshot.highlights = highlights[:6]
                    existing_snapshot.executive_summary = mood_summary
                    existing_snapshot.role = role_val
                    existing_snapshot.phone_number = phone_val
                    db.commit()
                    db.refresh(existing_snapshot)
                    rec = existing_snapshot
                else:
                    rec_id = str(uuid4())
                    rec = DailySentimentSnapshotRecord(
                        id=rec_id,
                        date=target_date,
                        speaker=speaker,
                        phone_number=phone_val,
                        role=role_val,
                        interactions_count=len(msgs),
                        dominant_sentiment=dominant_sent,
                        avg_sentiment_score=avg_score,
                        positive_count=pos,
                        neutral_count=neu,
                        negative_count=neg,
                        highlights=highlights[:6],
                        executive_summary=mood_summary,
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(rec)
                    db.commit()
                    db.refresh(rec)

                snapshots_responses.append(
                    DailySentimentSnapshotResponse(
                        id=rec.id,
                        date=rec.date,
                        speaker=rec.speaker,
                        phone_number=rec.phone_number,
                        role=rec.role,
                        interactions_count=rec.interactions_count,
                        dominant_sentiment=rec.dominant_sentiment,
                        avg_sentiment_score=rec.avg_sentiment_score,
                        positive_count=rec.positive_count,
                        neutral_count=rec.neutral_count,
                        negative_count=rec.negative_count,
                        highlights=rec.highlights or [],
                        executive_summary=rec.executive_summary,
                        created_at=rec.created_at,
                    )
                )

            return DailySentimentCollectionResponse(
                date=target_date,
                total_people=len(snapshots_responses),
                total_interactions=total_interactions,
                snapshots=snapshots_responses,
            )
        finally:
            if should_close:
                db.close()

    def get_daily_snapshots(
        self,
        target_date: Optional[str] = None,
        db: Session | None = None,
    ) -> list[DailySentimentSnapshotResponse]:
        """Retorna os snapshots gravados para uma data específica."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            if not target_date:
                target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            records = (
                db.query(DailySentimentSnapshotRecord)
                .filter(DailySentimentSnapshotRecord.date == target_date)
                .order_by(DailySentimentSnapshotRecord.interactions_count.desc())
                .all()
            )

            # Se não houver snapshots previamente salvos, realiza a consolidação sob demanda
            if not records:
                collection = self.collect_daily_sentiments(target_date=target_date, db=db)
                return collection.snapshots

            return [
                DailySentimentSnapshotResponse(
                    id=r.id,
                    date=r.date,
                    speaker=r.speaker,
                    phone_number=r.phone_number,
                    role=r.role,
                    interactions_count=r.interactions_count,
                    dominant_sentiment=r.dominant_sentiment,
                    avg_sentiment_score=r.avg_sentiment_score,
                    positive_count=r.positive_count,
                    neutral_count=r.neutral_count,
                    negative_count=r.negative_count,
                    highlights=r.highlights or [],
                    executive_summary=r.executive_summary,
                    created_at=r.created_at,
                )
                for r in records
            ]
        finally:
            if should_close:
                db.close()

    def get_person_timeline(
        self,
        speaker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        db: Session | None = None,
    ) -> PersonSentimentTimelineResponse:
        """Gera a série temporal histórica de sentimentos de uma pessoa específica."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            query = db.query(DailySentimentSnapshotRecord).filter(
                DailySentimentSnapshotRecord.speaker.ilike(f"%{speaker.strip()}%")
            )
            if start_date:
                query = query.filter(DailySentimentSnapshotRecord.date >= start_date)
            if end_date:
                query = query.filter(DailySentimentSnapshotRecord.date <= end_date)

            snapshots = query.order_by(DailySentimentSnapshotRecord.date.asc()).all()

            # Busca dados do contato
            contact = db.query(ContactRecord).filter(
                (ContactRecord.name.ilike(speaker)) | (ContactRecord.phone_number == speaker)
            ).first()

            role_val = contact.role if contact else "UNKNOWN"
            phone_val = contact.phone_number if contact else None

            if not snapshots:
                return PersonSentimentTimelineResponse(
                    speaker=speaker,
                    role=role_val,
                    phone_number=phone_val,
                    total_days_tracked=0,
                    overall_sentiment="NEUTRAL",
                    avg_score=0.0,
                    timeline=[],
                )

            total_score = sum(s.avg_sentiment_score for s in snapshots)
            avg_overall = round(total_score / len(snapshots), 3)

            pos_days = sum(1 for s in snapshots if s.dominant_sentiment == "POSITIVE")
            neg_days = sum(1 for s in snapshots if s.dominant_sentiment == "NEGATIVE")

            if pos_days > neg_days:
                overall_sent = "POSITIVE"
            elif neg_days > pos_days:
                overall_sent = "NEGATIVE"
            else:
                overall_sent = "NEUTRAL"

            timeline_points = [
                SentimentTimelinePoint(
                    date=s.date,
                    dominant_sentiment=s.dominant_sentiment,
                    avg_sentiment_score=s.avg_sentiment_score,
                    interactions_count=s.interactions_count,
                    positive_count=s.positive_count,
                    neutral_count=s.neutral_count,
                    negative_count=s.negative_count,
                    highlights=s.highlights or [],
                )
                for s in snapshots
            ]

            return PersonSentimentTimelineResponse(
                speaker=snapshots[0].speaker,
                role=role_val,
                phone_number=phone_val,
                total_days_tracked=len(snapshots),
                overall_sentiment=overall_sent,
                avg_score=avg_overall,
                timeline=timeline_points,
            )
        finally:
            if should_close:
                db.close()


sentiment_timeline_service = SentimentTimelineService()
