"""Testes automatizados de precisão temporal (hoje/ontem/histórico) para o Oráculo Melpômene e Hermes Q&A."""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from src.memory.database import SessionLocal, init_db
from src.memory.models import MessageRecord, TaskRecord
from src.contacts.models import ContactRecord
from src.memory.repository import memory_repository
from src.memory.timezone_utils import BRASILIA_TZ, get_now_brt


@pytest.mark.asyncio
async def test_hermes_rag_query_today_with_no_messages_today():
    """Testa que ao perguntar 'o que conversei com Laura hoje?' sem mensagens hoje, o sistema não confunde histórico antigo com hoje."""
    init_db()
    db = SessionLocal()
    try:
        # Cria contato Laura
        laura_contact = db.query(ContactRecord).filter(ContactRecord.name == 'Laura Delai').first()
        if not laura_contact:
            laura_contact = ContactRecord(
                id=str(uuid4()),
                name='Laura Delai',
                nickname='Laura',
                role='Extensionista',
                company='eProdutor',
            )
            db.add(laura_contact)
            db.commit()

        # Cria mensagem antiga de 30 dias atrás
        old_time = datetime.now(timezone.utc) - timedelta(days=30)
        old_msg = MessageRecord(
            id=str(uuid4()),
            created_at=old_time,
            speaker='Laura Delai',
            raw_text='Entendi, hoje o campo da data sugerida não preenche automático',
            revised_text='Entendi, hoje o campo da data sugerida não preenche de maneira automática.',
            summary='Problema no campo de data sugerida',
            intent='NOTE',
        )
        db.add(old_msg)
        db.commit()

        # Pergunta sobre hoje
        res = await memory_repository.query_hermes_rag(
            query='o que conversei com Laura hoje?',
            db=db,
        )

        assert res is not None
        assert res.answer is not None
        answer_lower = res.answer.lower()

        # A resposta deve indicar que NÃO conversou hoje ou que não há mensagens hoje
        assert ('não' in answer_lower and 'hoje' in answer_lower) or ('nenhuma' in answer_lower) or ('não conversou' in answer_lower) or ('não foram encontradas' in answer_lower) or ('não constam' in answer_lower)
        assert len(res.sources) == 0
    finally:
        db.close()


@pytest.mark.asyncio
async def test_hermes_rag_query_today_with_messages_today():
    """Testa que ao perguntar 'o que conversei com Doris hoje?' com mensagem de hoje, o sistema retorna a mensagem de hoje."""
    init_db()
    db = SessionLocal()
    try:
        doris_contact = db.query(ContactRecord).filter(ContactRecord.name == 'Doris Stern').first()
        if not doris_contact:
            doris_contact = ContactRecord(
                id=str(uuid4()),
                name='Doris Stern',
                nickname='Doris',
                role='Diretora',
                company='Westbridge',
            )
            db.add(doris_contact)
            db.commit()

        # Cria mensagem de HOJE
        now_time = datetime.now(timezone.utc)
        today_msg = MessageRecord(
            id=str(uuid4()),
            created_at=now_time,
            speaker='Doris Stern',
            raw_text='Oi Bruno, alinhamos a entrega de ração e os novos sensores de nível',
            revised_text='Oi Bruno, alinhamos a entrega de ração e os novos sensores de nível.',
            summary='Alinhamento de entrega de ração e sensores',
            intent='NOTE',
        )
        db.add(today_msg)
        db.commit()

        # Pergunta sobre hoje
        res = await memory_repository.query_hermes_rag(
            query='O que conversei com Doris hoje?',
            db=db,
        )

        assert res is not None
        assert res.answer is not None
        answer_lower = res.answer.lower()

        # Deve encontrar a conversa de hoje
        assert len(res.sources) >= 1
        assert 'doris' in answer_lower or 'ração' in answer_lower or 'sensores' in answer_lower
    finally:
        db.close()
