---
name: jev-orchestrator
description: "Diretrizes e comandos para inspeção, calibração, benchmark e testes do orquestrador JEV (Judge - Evaluator - Verifier) do Hermes Voice Memory."
---

# JEV Orchestrator Skill

Esta skill define as diretrizes para interagir, depurar, calibrar e evoluir o motor **JEV (Judge - Evaluator - Verifier)** no ecossistema Hermes Voice Memory.

## Visão Geral da Arquitetura
O JEV atua na triagem em tempo real de mensagens de voz e texto:
1. **[J] Judge**:
   - **Tier 1 (Heurístico / spaCy regex)**: Processa saudações, comandos diretos, datas relativas e emergências agroindustriais em `< 0.3ms`.
   - **Tier 2 (SLM / ONNX / SemanticCentroid)**: Resolve casos ambíguos ou requisições forçadas (`force_tier2=True`) em `< 15ms`.
2. **[E] Evaluator**:
   - `DIRECT_RESOLVE`: Cria tarefas imediatamente sem gastar tokens de nuvem.
   - `BYPASS`: Descarta ruídos sociais e SAC sem registrar ou notificar.
   - `DEEP_ANALYSIS`: Roteia áudios complexos (> 240 caracteres / > 25s) para o Gemini Flash-Lite.
   - `GRAPH_QUERY`: Roteia perguntas sobre entidades e histórico.
3. **[V] Verifier**:
   - Sanitiza e desduplica notificações para o `ntfy`.
   - Remove blocos redundantes de `📌 Destaques do Áudio` em mensagens curtas.

## Comandos Úteis

### 1. Executar Benchmark JEV
```bash
# Executa benchmark padrão (Tier 1 Heurístico)
.venv/bin/python scripts/benchmark_jev.py

# Executa benchmark forçando o Tier 2 (SLM / Semantic)
.venv/bin/python scripts/benchmark_jev.py --tier2
```

### 2. Executar Suíte de Testes Automatizados
```bash
.venv/bin/pytest tests/test_jev_tier2.py tests/test_jev_benchmark.py tests/test_jev_orchestration.py -v
```

### 3. Chamada de Diagnóstico via API
```bash
curl -X POST http://localhost:8000/api/v1/ai/jev/judge \
  -H "Content-Type: application/json" \
  -d '{"text": "Anotar ideia urgente para os silos", "speaker": "Bruno Conter", "is_self_memo": true}'
```

## Arquivos Chave
- Código-fonte: `src/ai_gateway/jev/` (`schemas.py`, `service.py`, `tier2.py`).
- Endpoint REST: `src/ai_gateway/router.py`.
- Dataset de Ground Truth: `data/jev_benchmark_dataset.json`.
- Especificação Completa: `docs/specs/jev_architecture_spec.md`.
- Roadmap de Futuras Fases: `docs/ROADMAP.md`.
