# 📋 Especificação Técnica — Orquestrador JEV (Judge - Evaluator - Verifier)

## 1. Visão Geral
O **JEV** é o motor de governança, triagem e orquestração inteligente de modelos do **Hermes Voice Memory**. Ele intercepta todas as transcrições de áudio e mensagens recebidas antes de qualquer chamada a provedores de LLM externos (Google Gemini), garantindo:
1. **Zero Desperdício de Tokens**: Tarefas simples, notas diretas e saudações são resolvidas ou descartadas localmente.
2. **Latência Sub-Milissegundo**: Triagem inicial executada em média em `0.26ms` em hardware CPU modesto.
3. **Segurança e Higienização**: Verificação contra redundâncias visuais, metadados inertes e validação estrita de esquemas.

---

## 2. Componentes

### 2.1 [J] JUDGE — Juiz em Cascata de Alta Performance
- **Tier 1 (Heurístico / spaCy Regex)**:
  - Latência: `< 0.3 ms`.
  - Classifica comandos operacionais diretos (`verificar`, `agendar`, `comprar`, `ligar`, etc.).
  - Extrai datas relativas (`hoje`, `amanhã`, `depois de amanhã`, dias da semana).
  - Detecta emergências agroindustriais (`falta de ração`, `parou tudo`, `vazamento crítico`, `mortalidade alta`).
  - Descarta ruídos sociais (`bom dia`, emojis, mensagens transacionais de SAC).
- **Tier 2 (SLM / Local Model Engine)**:
  - Latência: `< 15 ms`.
  - Suporte a `onnxruntime` com modelos locais ONNX.
  - Classificador semântico baseado em centróides e protótipos de domínio para linguagem ambígua e conversacional.
  - Fallback gracioso automático garantindo 100% de disponibilidade.

### 2.2 [E] EVALUATOR — Avaliador e Roteador de Modelos
- Mapeia o veredito do Judge em uma das quatro ações:
  - `BYPASS`: Descarte silencioso ou arquivamento mínimo (0 tokens).
  - `DIRECT_RESOLVE`: Criação imediata de tarefas no banco sem inferência externa.
  - `DEEP_ANALYSIS`: Roteamento para Gemini 3.5 Flash-Lite para áudios longos (> 240 chars / > 25s) e relatórios complexos.
  - `GRAPH_QUERY`: Consulta estruturada ao grafo de conhecimento NetworkX e banco vetorial.

### 2.3 [V] VERIFIER — Verificador e Sanitizador
- Elimina duplicações de destaques executivos em mensagens curtas.
- Normaliza e capitaliza títulos de tarefas.
- Valida tipagens e esquemas Pydantic.

---

## 3. Endpoints REST
- `POST /api/v1/ai/jev/judge`:
  ```json
  {
    "text": "Anotar ideia urgente para os silos",
    "speaker": "Bruno Conter",
    "is_self_memo": true,
    "duration_s": 8.0,
    "force_tier2": false
  }
  ```
  **Resposta:**
  ```json
  {
    "action": "DIRECT_RESOLVE",
    "intent": "TASK",
    "urgency": "URGENT",
    "confidence": 0.94,
    "suggested_route": "local",
    "tier_used": "tier1_heuristic",
    "direct_task_title": "Urgente para os silos",
    "direct_due_date": null
  }
  ```

---

## 4. Testes e Benchmarks
- Dataset: `data/jev_benchmark_dataset.json` (30 casos de teste com ground truth).
- Runner CLI: `scripts/benchmark_jev.py` (suporte a `--tier2`).
- Testes de Regressão: `tests/test_jev_benchmark.py`, `tests/test_jev_tier2.py`, `tests/test_jev_orchestration.py`.
