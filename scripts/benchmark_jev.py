#!/usr/bin/env python3
"""Script de Benchmark e Calibração do Orquestrador JEV (Judge - Evaluator - Verifier)."""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

# Adiciona a raiz do projeto ao path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.ai_gateway.jev import jev_service, JEVAction, JEVIntent, JEVUrgency


def run_benchmark(dataset_path: str = "data/jev_benchmark_dataset.json") -> Dict[str, Any]:
    full_path = project_root / dataset_path
    if not full_path.exists():
        print(f"❌ Arquivo de dataset não encontrado: {full_path}")
        sys.exit(1)

    with open(full_path, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    total_cases = len(cases)
    action_correct = 0
    intent_correct = 0
    urgency_correct = 0
    date_correct = 0
    date_cases = 0

    latencies_ns = []
    results = []

    today = datetime.now()

    print("\n" + "=" * 90)
    print(f"📊 INICIANDO BENCHMARK JEV — {total_cases} CASOS DE TESTE")
    print("=" * 90)
    print(f"{'ID':<28} | {'ACTION':<15} | {'INTENT':<10} | {'URGENCY':<8} | {'LATÊNCIA':<8} | STATUS")
    print("-" * 90)

    for case in cases:
        cid = case["id"]
        text = case["text"]
        speaker = case.get("speaker", "Bruno Conter")
        is_self_memo = case.get("is_self_memo", False)
        duration_s = float(case.get("duration_s", 0.0))

        # Medição de latência com resolução em nanossegundos
        t0 = time.perf_counter_ns()
        verdict = jev_service.judge(
            text=text,
            speaker=speaker,
            is_self_memo=is_self_memo,
            duration_s=duration_s,
        )
        t1 = time.perf_counter_ns()
        lat_ns = t1 - t0
        latencies_ns.append(lat_ns)
        lat_ms = lat_ns / 1_000_000.0

        # Verificações de conformidade
        act_ok = verdict.action.value == case["expected_action"]
        int_ok = verdict.intent.value == case["expected_intent"]
        urg_ok = verdict.urgency.value == case["expected_urgency"]

        if act_ok:
            action_correct += 1
        if int_ok:
            intent_correct += 1
        if urg_ok:
            urgency_correct += 1

        dt_ok = True
        if "expected_date_offset_days" in case and case["expected_date_offset_days"] is not None:
            date_cases += 1
            expected_date = (today + timedelta(days=case["expected_date_offset_days"])).strftime("%Y-%m-%d")
            dt_ok = verdict.direct_due_date == expected_date
            if dt_ok:
                date_correct += 1

        is_all_ok = act_ok and int_ok and urg_ok and dt_ok
        status_icon = "✅ OK" if is_all_ok else "❌ FAIL"

        results.append({
            "id": cid,
            "all_ok": is_all_ok,
            "action_ok": act_ok,
            "intent_ok": int_ok,
            "urgency_ok": urg_ok,
            "date_ok": dt_ok,
            "latency_ms": lat_ms,
            "verdict": verdict.model_dump(),
        })

        print(
            f"{cid:<28} | {verdict.action.value:<15} | {verdict.intent.value:<10} | "
            f"{verdict.urgency.value:<8} | {lat_ms:6.3f}ms | {status_icon}"
        )
        if not is_all_ok:
            print(f"   ⚠️ Esperado: Action={case['expected_action']}, Intent={case['expected_intent']}, Urgency={case['expected_urgency']}")
            print(f"   ⚠️ Obtido:   Action={verdict.action.value}, Intent={verdict.intent.value}, Urgency={verdict.urgency.value}")
            if not dt_ok:
                print(f"   ⚠️ Data obtida: {verdict.direct_due_date} (esperado offset {case['expected_date_offset_days']}d)")

    # Estatísticas de latência
    latencies_ns.sort()
    p50_ms = latencies_ns[int(len(latencies_ns) * 0.50)] / 1_000_000.0
    p95_ms = latencies_ns[int(len(latencies_ns) * 0.95)] / 1_000_000.0
    p99_ms = latencies_ns[int(len(latencies_ns) * 0.99)] / 1_000_000.0
    mean_ms = (sum(latencies_ns) / len(latencies_ns)) / 1_000_000.0

    action_acc = (action_correct / total_cases) * 100.0
    intent_acc = (intent_correct / total_cases) * 100.0
    urgency_acc = (urgency_correct / total_cases) * 100.0
    date_acc = (date_correct / date_cases * 100.0) if date_cases > 0 else 100.0

    print("=" * 90)
    print("📈 RESULTADOS CONSOLIDADOS DO BENCHMARK:")
    print(f"  • Acurácia de Roteamento de Ação (Action Accuracy) : {action_acc:6.2f}% ({action_correct}/{total_cases})")
    print(f"  • Acurácia de Intenção (Intent Accuracy)           : {intent_acc:6.2f}% ({intent_correct}/{total_cases})")
    print(f"  • Acurácia de Urgência (Urgency Accuracy)          : {urgency_acc:6.2f}% ({urgency_correct}/{total_cases})")
    print(f"  • Acurácia de Datas Relativas (Date Accuracy)      : {date_acc:6.2f}% ({date_correct}/{date_cases})")
    print("-" * 90)
    print(f"  ⏱️ Latência Média : {mean_ms:6.3f} ms")
    print(f"  ⏱️ Latência p50   : {p50_ms:6.3f} ms")
    print(f"  ⏱️ Latência p95   : {p95_ms:6.3f} ms")
    print(f"  ⏱️ Latência p99   : {p99_ms:6.3f} ms")
    print("=" * 90)

    summary = {
        "total_cases": total_cases,
        "action_accuracy": action_acc,
        "intent_accuracy": intent_acc,
        "urgency_accuracy": urgency_acc,
        "date_accuracy": date_acc,
        "latency_mean_ms": mean_ms,
        "latency_p50_ms": p50_ms,
        "latency_p95_ms": p95_ms,
        "latency_p99_ms": p99_ms,
    }

    return summary


if __name__ == "__main__":
    summary = run_benchmark()
    if summary["action_accuracy"] < 95.0 or summary["urgency_accuracy"] < 90.0:
        print("❌ Falha nos critérios mínimos de qualidade do benchmark.")
        sys.exit(1)
    else:
        print("🎉 Benchmark concluído com sucesso dentro dos critérios de excelência!")
        sys.exit(0)
