"""Serviço de Coleta e Análise de Séries Temporais de Sentimentos por Pessoa."""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from sqlalchemy.orm import Session

from src.contacts.models import ContactRecord
from src.config import settings
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
        """Consolida as mensagens do dia, computa a distribuição emocional e persiste no banco SQL."""
        import re
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            if not target_date:
                target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Busca todas as mensagens da data de forma compatível com PostgreSQL e SQLite
            from sqlalchemy import cast, String
            messages = (
                db.query(MessageRecord)
                .filter(cast(MessageRecord.created_at, String).like(f"{target_date}%"))
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

            # Carrega catálogo de contatos para resolução flexível
            all_contacts = db.query(ContactRecord).all()

            for speaker, msgs in person_messages.items():
                # Ignora interações do próprio usuário/proprietário
                sample_meta = msgs[0].meta_info if (msgs and isinstance(msgs[0].meta_info, dict)) else {}
                if is_owner_interaction(speaker, sample_meta):
                    continue

                pos = 0
                neu = 0
                neg = 0
                highlights = []

                for msg in msgs:
                    sent = (msg.sentiment or "NEUTRAL").upper()
                    if sent in ["POSITIVE", "POSITIVO", "CONFIDENT", "CONFIANTE"]:
                        pos += 1
                    elif sent in ["NEGATIVE", "NEGATIVO", "URGENT", "URGENTE", "ANXIOUS", "ANSIOSO", "FRUSTRATED", "FRUSTRADO"]:
                        neg += 1
                    else:
                        neu += 1

                    summary_or_text = msg.summary or (msg.revised_text[:90] if msg.revised_text else "")
                    if summary_or_text and summary_or_text not in highlights:
                        highlights.append(f"[{sent}] {summary_or_text}")

                dominant_sent, avg_score = compute_dominant_sentiment(pos, neu, neg)

                # Resolução estrita do contato cadastrado (evita colisões de substring)
                speaker_clean = speaker.strip().lower()
                speaker_digits = re.sub(r"\D", "", speaker)
                matched_contact = None

                for c in all_contacts:
                    c_name = (c.name or "").strip().lower()
                    c_nick = (c.nickname or "").strip().lower()
                    c_phone = re.sub(r"\D", "", c.phone_number or "")

                    # 1. Match estrito por telefone
                    if speaker_digits and c_phone:
                        if speaker_digits == c_phone or (len(speaker_digits) >= 8 and len(c_phone) >= 8 and speaker_digits[-8:] == c_phone[-8:]):
                            matched_contact = c
                            break

                    # 2. Match estrito por igualdade exata
                    if c_name and speaker_clean == c_name:
                        matched_contact = c
                        break

                    if c_nick and speaker_clean == c_nick:
                        matched_contact = c
                        break

                    # 3. Match por limite de palavra (somente se nome tiver 5+ caracteres)
                    if c_name and len(c_name) >= 5 and re.search(rf"\b{re.escape(c_name)}\b", speaker_clean):
                        matched_contact = c
                        break

                role_val = matched_contact.role if matched_contact else "OTHER"
                phone_val = matched_contact.phone_number if matched_contact else (speaker if speaker_digits else None)
                
                # Se o speaker já for um nome real (não apenas dígitos), SEMPRE preserva o speaker original!
                if re.search(r"[a-zA-Z]", speaker):
                    display_speaker = speaker.strip()
                elif matched_contact:
                    display_speaker = matched_contact.name
                else:
                    display_speaker = speaker.strip()

                # Gera síntese emocional breve
                if dominant_sent == "POSITIVE":
                    mood_summary = f"{len(msgs)} interação(ões) com tom positivo, confiante e colaborativo."
                elif dominant_sent == "NEGATIVE":
                    mood_summary = f"{len(msgs)} interação(ões) com tom de preocupação, urgência ou atrito."
                elif dominant_sent == "MIXED":
                    mood_summary = f"{len(msgs)} interação(ões) com oscilação entre momentos positivos e alertas críticos."
                else:
                    mood_summary = f"{len(msgs)} interação(ões) objetivas e operacionais neutras."

                # Salva ou atualiza snapshot diário idempotente
                existing_snapshot = db.query(DailySentimentSnapshotRecord).filter(
                    (DailySentimentSnapshotRecord.date == target_date)
                    & (DailySentimentSnapshotRecord.speaker == display_speaker)
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
                        speaker=display_speaker,
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

            # Ordena decrescente por interações
            snapshots_responses.sort(key=lambda x: x.interactions_count, reverse=True)

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
        days: int = 30,
        db: Session | None = None,
    ) -> list[DailySentimentSnapshotResponse]:
        """Retorna os snapshots gravados para uma data específica ou agregados dos últimos N dias."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            is_all = not target_date or target_date.lower() in ("all", "todos", "")

            if is_all:
                from datetime import timedelta
                start_dt = datetime.now(timezone.utc) - timedelta(days=days)
                start_date_str = start_dt.strftime("%Y-%m-%d")

                records = (
                    db.query(DailySentimentSnapshotRecord)
                    .filter(DailySentimentSnapshotRecord.date >= start_date_str)
                    .all()
                )

                if not records:
                    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    self.collect_daily_sentiments(target_date=today_str, db=db)
                    records = db.query(DailySentimentSnapshotRecord).all()

                # Agrupa por speaker único
                speaker_groups = defaultdict(list)
                for r in records:
                    speaker_groups[r.speaker].append(r)

                aggregated: list[DailySentimentSnapshotResponse] = []
                for spk, group in speaker_groups.items():
                    total_interactions = sum(g.interactions_count for g in group)
                    total_pos = sum(g.positive_count for g in group)
                    total_neu = sum(g.neutral_count for g in group)
                    total_neg = sum(g.negative_count for g in group)
                    dominant_sent, avg_score = compute_dominant_sentiment(total_pos, total_neu, total_neg)

                    all_highlights = []
                    for g in group:
                        for h in (g.highlights or []):
                            if h not in all_highlights:
                                all_highlights.append(h)

                    last_rec = max(group, key=lambda x: x.date or "")

                    if dominant_sent == "POSITIVE":
                        mood_summary = f"{total_interactions} interação(ões) nos últimos {days} dias com tom colaborativo e positivo."
                    elif dominant_sent == "NEGATIVE":
                        mood_summary = f"{total_interactions} interação(ões) com tom de preocupação, urgência ou atrito."
                    elif dominant_sent == "MIXED":
                        mood_summary = f"{total_interactions} interação(ões) com oscilação entre momentos positivos e alertas."
                    else:
                        mood_summary = f"{total_interactions} interação(ões) objetivas e operacionais neutras."

                    aggregated.append(
                        DailySentimentSnapshotResponse(
                            id=last_rec.id,
                            date=f"Últimos {days} dias",
                            speaker=spk,
                            phone_number=last_rec.phone_number,
                            role=last_rec.role,
                            interactions_count=total_interactions,
                            dominant_sentiment=dominant_sent,
                            avg_sentiment_score=avg_score,
                            positive_count=total_pos,
                            neutral_count=total_neu,
                            negative_count=total_neg,
                            highlights=all_highlights[:6],
                            executive_summary=mood_summary,
                            created_at=last_rec.created_at,
                        )
                    )

                aggregated.sort(key=lambda x: x.interactions_count, reverse=True)
                return aggregated

            records = (
                db.query(DailySentimentSnapshotRecord)
                .filter(DailySentimentSnapshotRecord.date == target_date)
                .order_by(DailySentimentSnapshotRecord.interactions_count.desc())
                .all()
            )

            # Se não houver snapshots previamente salvos, realiza a consolidação sob demanda
            if not records:
                collection = self.collect_daily_sentiments(target_date=target_date, db=db)
                snapshots_res = collection.snapshots
                snapshots_res.sort(key=lambda x: x.interactions_count, reverse=True)
                return snapshots_res

            res = [
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
            res.sort(key=lambda x: x.interactions_count, reverse=True)
            return res
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
            # Busca dados do contato cadastrado (se houver)
            contact = db.query(ContactRecord).filter(
                (ContactRecord.name.ilike(f"%{speaker.strip()}%")) | (ContactRecord.phone_number == speaker)
            ).first()

            role_val = contact.role if contact else "OTHER"
            phone_val = contact.phone_number if contact else None

            query = db.query(DailySentimentSnapshotRecord).filter(
                DailySentimentSnapshotRecord.speaker.ilike(f"%{speaker.strip()}%")
            )
            if start_date:
                query = query.filter(DailySentimentSnapshotRecord.date >= start_date)
            if end_date:
                query = query.filter(DailySentimentSnapshotRecord.date <= end_date)

            snapshots = query.order_by(DailySentimentSnapshotRecord.date.asc()).all()

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
