"""Teste automatizado de regressão do Benchmark JEV."""

import pytest
from scripts.benchmark_jev import run_benchmark


def test_jev_benchmark_quality_and_latency_thresholds():
    """Valida se o JEV atinge os critérios rigorosos de acurácia e latência contínua."""
    summary = run_benchmark("data/jev_benchmark_dataset.json")

    # Guardrails de acurácia
    assert summary["action_accuracy"] >= 95.0, (
        f"Acurácia de roteamento de ação abaixo do esperado: {summary['action_accuracy']}%"
    )
    assert summary["intent_accuracy"] >= 90.0, (
        f"Acurácia de classificação de intenção abaixo do esperado: {summary['intent_accuracy']}%"
    )
    assert summary["urgency_accuracy"] >= 95.0, (
        f"Acurácia de urgência abaixo do esperado: {summary['urgency_accuracy']}%"
    )
    assert summary["date_accuracy"] >= 95.0, (
        f"Acurácia de extração de datas relativas abaixo do esperado: {summary['date_accuracy']}%"
    )

    # Guardrail de latência (deve ser sub-10ms em p95)
    assert summary["latency_p95_ms"] < 10.0, (
        f"Latência p95 superior ao teto de 10ms: {summary['latency_p95_ms']}ms"
    )
