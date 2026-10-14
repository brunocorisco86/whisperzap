# 🗺️ Roadmap de Evolução — Hermes Voice Memory & JEV

Este documento registra as fases concluídas e as prioridades planejadas para as próximas sessões de desenvolvimento e engenharia de software do ecossistema **Hermes Voice Memory / WhisperZap**.

---

## ✅ Fases Concluídas

### 1. Otimização de Performance & Hardening da VPS (Hostinger KVM 1)
- [x] Criação de Swapfile persistente de 2 GB (`/swapfile`, `vm.swappiness=10`).
- [x] Ajuste de ordem de boot no OpenRC Alpine Linux (`docker` no runlevel `default`).
- [x] Limites estritos de memória e reserva configurados em todos os contêineres Docker Compose (`hermes-api`: 1.2 GB, `hermes-evolution-api`: 768 MB, `hermes-db`: 512 MB, `hermes-evolution-redis`: 128 MB, `hermes-caddy`: 128 MB).
- [x] Redução do Uvicorn para 1 worker em CPU monocore e Whisper em modo guloso (`beam_size=1`).
- [x] Memória RAM livre no host ampliada de ~500 MB para **~2.45 GB** (redução de 85% para 30% de uso de RAM).

### 2. Desduplicação & Higienização Visual de Notificações (`ntfy`)
- [x] Eliminação de 100% das repetições textuais em alertas (transcrição aparecia até 4 vezes).
- [x] Supressão de emojis duplicados no cabeçalho dos cards.
- [x] Filtragem de metadados neutros/inertes (`NEUTRAL +0.00`, `Intenção: TASK` quando há tarefas).
- [x] Regra negativa em prompt e backend suprimindo `📌 Destaques do Áudio` artificiais em áudios curtos (< 250 caracteres / <= 25s).

### 3. Orquestrador JEV (Judge - Evaluator - Verifier)
- [x] **Fase 1 (Protótipo & Cascata)**: Schemas Pydantic, motor em 3 estágios, integração prévia no pipeline do WhatsApp e endpoint REST `POST /api/v1/ai/jev/judge`.
- [x] **Fase 2 (Benchmark & Calibração)**: Dataset ground truth (`data/jev_benchmark_dataset.json`) com 30 casos reais (silos, ração, TMS, C.Vale, rotinas e SAC), atingindo **100% de acurácia** em roteamento, intenção, urgência e extração de datas relativas com **0.26ms de latência média**.
- [x] **Fase 3 (Tier 2 SLM / ONNX Engine)**: Motor de inferência local com suporte a ONNX Runtime, classificador semântico por centróides (`SemanticCentroidClassifier`) para casos ambíguos, fallback resiliente e flag de diagnóstico `force_tier2`.

### 4. Banco Vetorial Local com Embeddings Orquestrados pelo JEV
- [x] **Provedor Local de Embeddings (`LocalEmbeddingProvider`)**:
  - Geração local em 768 dimensões com normalização $L_2 = 1.0$ e latência sub-milissegundo (`0.097ms` por vetor).
  - Suporte a modelos ONNX em disco (`models/bge-micro-v2.onnx`) e motor de projeção semântica determinística nativo.
  - Eliminação de 100% dos custos e chamadas de API externas para embeddings.
- [x] **Orquestração Inteligente pelo JEV**:
  - Emissão de `should_vectorize: bool` no veredito do JEV.
  - Mensagens classificadas como `BYPASS` (saudações, ruídos, robôs/SAC) pulam completamente a vetorização, economizando ciclos de CPU e espaço no PostgreSQL/SQLite.
- [x] **Validação & Testes**:
  - 6/6 testes aprovados em `tests/test_local_embeddings.py` validados localmente e no contêiner da VPS de produção.

### 5. Redução Agressiva de Tokens & Síntese Neural-Simbólica
- [x] **Injeção Dinâmica de Glossário Scoped**: Redução de mais de 80% dos tokens de sistema filtrando apenas termos presentes na mensagem via matcher léxico local.
- [x] **Short-Circuit JEV em `DIRECT_RESOLVE`**: Tarefas imperativas e notas estruturadas diretamente no backend com 0 tokens de LLM.
- [x] **Bypass de Revisão para Áudios Curtos**: Áudios diretos (< 120 chars) utilizam transcrição local refinada via dicionário léxico, dispensando revisão externa.
- [x] **Cache Semântico Local de 2 Horas**: Respostas reutilizadas em memória para consultas idênticas ou muito próximas.
- [x] **Síntese Neural-Simbólica Local**: Roteamento sobre topologia do Grafo NetworkX e queries do Postgres antes de acionar LLM.

### 6. Motor de Visão Computacional Local 100% Zero-Token
- [x] **YOLO11 Nano em ONNX (`yolo11n.onnx`)**: Inferência local na CPU da VPS Hostinger (~360ms) com 80 classes do COCO Dataset traduzidas para PT-BR.
- [x] **Detector Heurístico de Documentos / Notas Fiscais**: Classificação instantânea de cupons e folhas A4 por aspect ratio e luminosidade sem OCR pesado.
- [x] **Decodificação Universal em Passagem Única**: Pipeline otimizado com streaming FFmpeg nativo sem bibliotecas pesadas de visão.
- [x] **Integração no Grafo de Conhecimento**: Conexão de objetos detectados (ex: `Cachorro`, `Documento`) ao remetente com arestas `TRANSMITTED_PHOTO`.
- [x] **Notificações Push Limpas via ntfy**: Supressão de duplicações de remetente, tags limpas e exibição de confiança percentual.
- [x] **Validação Live em Produção**: Detecção de cachorro (88% de confiança) em 362ms e consumo estável de 178 MB de RAM.

---

## 📌 Prioridades para a Próxima Sessão

### 🎯 [PRÓXIMA SESSÃO] Dashboard & Monitoramento das Métricas do JEV
- [ ] **Métricas em Tempo Real no Dashboard Web**:
  - Exibição de estatísticas consolidadas da triagem JEV: total de requisições, proporção de tarefas resolvidas localmente (`DIRECT_RESOLVE`) vs nuvem (`DEEP_ANALYSIS`), mensagens descartadas silenciosamente (`BYPASS`) e embeddings gerados localmente.
  - Cálculo de tokens de nuvem poupados e latência média das operações.
- [ ] **Fine-Tuning / Destilação de SLM Especializado**:
  - Avaliação de modelo quantizado GGUF/ONNX para domínio zootécnico e agronegócio (C.Vale, TMS, silos, sensores).

---

## 🔮 Futuras Fases do Ecossistema

- [ ] **Dashboard Unificado de Métricas JEV**:
  - Exibição em tempo real na interface web do Hermes da proporção de tarefas resolvidas localmente (`DIRECT_RESOLVE`) vs nuvem (`DEEP_ANALYSIS`) e economia de tokens acumulada.
- [ ] **Fine-Tuning / Destilação de SLM Especializado**:
  - Treinamento ou fine-tuning de um adaptador LoRA em Qwen 2.5 0.5B especializado em termos de agronegócio (C.Vale, ração, silos, TMS, zootecnia avícola).
