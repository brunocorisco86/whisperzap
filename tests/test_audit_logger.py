"""Testes Automatizados para o Módulo de Auditoria & Observabilidade."""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.audit.service import log_event, get_audit_logs, get_audit_stats
from src.memory.database import init_db

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()

def test_log_event_and_retrieve():
    """Testa criação de log de evento e recuperação no banco."""
    record = log_event(
        module="TRANSCRIBER",
        action="POST /transcribe/base64",
        speaker="554497604925",
        status="SUCCESS",
        duration_ms=123.45,
        details={"audio_duration_s": 15.2, "model": "base"},
    )
    assert record is not None
    assert record.module == "TRANSCRIBER"
    assert record.action == "POST /transcribe/base64"
    assert record.status == "SUCCESS"
    assert record.duration_ms == 123.45

    # Recupera logs
    logs = get_audit_logs(limit=10, module="TRANSCRIBER")
    assert len(logs) > 0
    assert any(l.id == record.id for l in logs)

def test_audit_stats():
    """Testa agregação de estatísticas de auditoria."""
    log_event(module="AI_GATEWAY", action="POST /ai/revise", status="SUCCESS", duration_ms=450.0)
    log_event(module="AI_GATEWAY", action="POST /ai/extract", status="ERROR", duration_ms=200.0, error_message="Timeout")

    stats = get_audit_stats()
    assert stats["total_events"] >= 2
    assert "by_module" in stats
    assert "AI_GATEWAY" in stats["by_module"]
    assert stats["error_events"] >= 1
    assert len(stats["recent_errors"]) >= 1

def test_audit_api_endpoints():
    """Testa endpoints HTTP da API de auditoria."""
    client = TestClient(app)

    # 1. Consulta logs
    resp = client.get("/api/v1/audit/logs?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

    # 2. Consulta stats
    resp_stats = client.get("/api/v1/audit/stats")
    assert resp_stats.status_code == 200
    stats_data = resp_stats.json()
    assert "total_events" in stats_data
    assert "success_rate_percent" in stats_data
