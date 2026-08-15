"""Testes para o Agente Pescador Léxico (Active Learning Harvester)."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from src.main import app
from src.dictionary.harvester import lexical_harvester
from src.dictionary.schemas import DictionaryTermCreate
from src.dictionary.service import dictionary_service
from src.memory.database import SessionLocal
from src.memory.models import LexicalCandidateRecord, MessageCreate
from src.memory.repository import memory_repository


@pytest.fixture
def client():
    return TestClient(app)


def test_lexical_candidate_persistence_and_harvest(client):
    """Testa o ciclo de vida de um candidato léxico: detecção, buffer e colheita."""
    db = SessionLocal()
    try:
        # 1. Cria candidato no buffer simulando termo difícil ouvido no áudio
        cand_id = str(uuid4())
        cand = LexicalCandidateRecord(
            id=cand_id,
            raw_term="sensores de silo io te",
            suggested_term="Silos IoT",
            context="Estamos instalando sensores de silo io te na granja 04",
            speaker="Bruno",
            category="LOGISTICA",
            reason="Erro fonético do Whisper para Silos IoT",
            status="PENDING",
            occurrence_count=2,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(cand)
        db.commit()

        # 2. Testa endpoint GET /api/v1/dictionary/candidates
        res_cand = client.get("/api/v1/dictionary/candidates?status=PENDING")
        assert res_cand.status_code == 200
        candidates = res_cand.json()
        assert any(c["id"] == cand_id for c in candidates)

        # 3. Testa promoção manual de candidato
        res_promote = client.patch(
            f"/api/v1/dictionary/candidates/{cand_id}/promote?term_override=Silos%20IoT&category=LOGISTICA"
        )
        assert res_promote.status_code == 200
        promoted = res_promote.json()
        assert promoted["term"] == "Silos IoT"
        assert "sensores de silo io te" in promoted.get("phonetic_variations", [])

        # 4. Verifica se o status mudou para HARVESTED
        db.refresh(cand)
        assert cand.status == "HARVESTED"

    finally:
        db.close()


@pytest.mark.asyncio
async def test_lexical_harvester_service_execution():
    """Testa a execução direta do serviço do Harvester."""
    db = SessionLocal()
    try:
        # Cria termo com recorrência alta para auto-promoção
        cand_id = str(uuid4())
        cand = LexicalCandidateRecord(
            id=cand_id,
            raw_term="têmessi",
            suggested_term="TMS",
            context="O têmessi alocou as cargas de ração",
            speaker="Bruno",
            category="LOGISTICA",
            reason="Variação fonética de TMS",
            status="PENDING",
            occurrence_count=3,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(cand)
        db.commit()

        result = await lexical_harvester.harvest_pending_candidates(db=db)
        assert result.total_candidates_analyzed >= 1
        assert result.promoted_terms_count >= 1

        db.refresh(cand)
        assert cand.status in ["HARVESTED", "REJECTED"]
    finally:
        db.close()


def test_harvest_endpoint_post(client):
    """Testa o endpoint POST /api/v1/dictionary/harvest."""
    res = client.post("/api/v1/dictionary/harvest")
    assert res.status_code == 200
    data = res.json()
    assert "harvested_at" in data
    assert "total_candidates_analyzed" in data
    assert "promoted_terms_count" in data
