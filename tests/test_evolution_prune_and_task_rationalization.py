"""Testes unitários e de integração para o Pruning da Evolution API e Racionalização de Tarefas (Terpsícore + spaCy + Polímnia)."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from src.whatsapp.evolution_pruner import evolution_history_pruner
from src.memory.task_sentiment_analyzer import task_sentiment_analyzer
from src.memory.models import TaskRecord
from src.memory.timezone_utils import get_now_brt


def test_evolution_pruner_calculate_cutoff():
    """Testa o cálculo do corte temporal D-2 no fuso de Brasília (00:00:00 BRT)."""
    cutoff_dt, cutoff_epoch = evolution_history_pruner.calculate_cutoff(days_to_keep=2)
    now_brt = get_now_brt()
    
    # Deve ser exatamente 2 dias atrás à meia-noite
    expected_day = (now_brt - timedelta(days=2)).day
    assert cutoff_dt.day == expected_day
    assert cutoff_dt.hour == 0
    assert cutoff_dt.minute == 0
    assert cutoff_dt.second == 0
    assert cutoff_epoch > 0
    assert cutoff_epoch < int(now_brt.timestamp())


def test_evolution_pruner_database_url_isolation():
    """Testa se a URL de conexão do pruner aponta estritamente para evolution_db e não hermes_voice_memory."""
    url = evolution_history_pruner.get_evolution_db_url()
    assert "evolution_db" in url
    assert "hermes_voice_memory" not in url


def test_polimnia_terms_extraction():
    """Testa se os termos canônicos de agronegócio/sistemas de Polímnia são extraídos com precisão."""
    text = "Alinhar com Sandra da Agrisolus sobre os sensores nos silos e a integração com e-Aware"
    terms = task_sentiment_analyzer.extract_polimnia_terms(text)
    
    assert "agrisolus" in terms
    assert "silos" in terms or "silo" in terms
    assert "e-aware" in terms or "eaware" in terms


def test_task_similarity_with_spacy_and_polimnia():
    """Testa se o score de similaridade híbrido spaCy + Polímnia detecta redundâncias reais."""
    title_a = "Realizar cadastros das tags"
    title_b = "Realizar os cadastros das tags após receber instruções do Rafa"
    
    score = task_sentiment_analyzer.compute_task_similarity(
        title_a=title_a, notes_a="", title_b=title_b, notes_b=""
    )
    assert score >= 0.48, f"Score esperado >= 0.48, obtido: {score}"

    title_c = "Criar documento para Sandra (Agrisolus) detalhando ações operacionais"
    title_d = "Criar documento para a Sandra (Agrisolus) definindo ações na granja"
    score_cd = task_sentiment_analyzer.compute_task_similarity(
        title_a=title_c, notes_a="", title_b=title_d, notes_b=""
    )
    assert score_cd >= 0.50, f"Score esperado >= 0.50, obtido: {score_cd}"


def test_rationalize_pending_tasks_in_memory():
    """Testa a fusão e cancelamento de tarefas duplicadas pelo motor de racionalização."""
    mock_db = MagicMock()

    task1 = TaskRecord(
        id="task-111",
        title="Realizar cadastros das tags",
        priority="HIGH",
        status="PENDING",
        notes="Aguardando confirmação",
    )
    task2 = TaskRecord(
        id="task-222",
        title="Realizar os cadastros das tags após receber instruções do Rafa",
        priority="URGENT",
        status="PENDING",
        notes="Rafa passou o link do firmware",
    )
    task3 = TaskRecord(
        id="task-333",
        title="Comprar peças de trator para o sítio",
        priority="LOW",
        status="PENDING",
        notes="Totalmente não relacionada",
    )

    # Retorna as 3 tarefas
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        task1, task2, task3
    ]

    result = task_sentiment_analyzer.rationalize_pending_tasks(mock_db, similarity_threshold=0.48)

    assert result["status"] == "SUCCESS"
    assert result["total_scanned"] == 3
    assert result["merged_count"] == 1
    assert result["remaining_pending"] == 2

    # task2 tinha prioridade URGENT, então deve ser mantida como primária
    # ou task1 foi consolidada em task2
    cancelled_tasks = [t for t in [task1, task2, task3] if t.status == "CANCELLED"]
    assert len(cancelled_tasks) == 1
    assert "Racionalizado por Terpsícore & Polímnia" in cancelled_tasks[0].reassessment_notes

    active_tasks = [t for t in [task1, task2, task3] if t.status == "PENDING"]
    assert len(active_tasks) == 2
    mock_db.commit.assert_called_once()
