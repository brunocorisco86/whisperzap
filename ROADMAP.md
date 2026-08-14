# 🗺️ Roadmap de Desenvolvimento — Hermes Voice Memory

Este documento estabelece o plano de desenvolvimento de **6 meses** para a construção e maturação do **Hermes Voice Memory**.

---

## 🚩 Status Atual: Fase 3 Concluída (Próximo: Fase 4 — Memória em Camadas)

---

## 🗓️ Fases do Projeto

```text
FASE 1: Setup & Governança (Local) [CONCLUÍDO]
   │
   ▼
FASE 2: MVP 1 — Transcrição de Áudio WhatsApp [CONCLUÍDO]
   │
   ▼
FASE 3: Criação de Repositório Remoto & Sincronização Git Push [CONCLUÍDO]
   │
   ▼
FASE 4: Memória em Camadas (Postgres + pgvector + NetworkX) [EM ANDAMENTO]
   │
   ▼
FASE 5: API da Memória & Agente Hermes (Resumos Diários/Semanais)
   │
   ▼
FASE 6: Deploy em Produção (VPS Alpine Linux + Raspberry Pi 3B)
```

---

### 🟢 Fase 1: Setup de Infraestrutura Local, Governança e Testes (Concluída)
- [x] Leitura e análise profunda do documento de ideação (`idea.md`).
- [x] Inicialização do repositório Git local (`git init`).
- [x] Criação do `.gitignore` para desenvolvimento Python e Graphify.
- [x] Estruturação da documentação inicial (`README.md`, `ROADMAP.md`, `LOGS.md`, `docs/architecture.md`).
- [x] Definição de subagentes especialistas (`arch-specialist`, `cicd-specialist`, `cybersec-specialist`, `hermes-agent-specialist`, `vps-alpine-specialist`, `api-stack-specialist`).
- [x] Definição das variáveis de ambiente (`.env.example`) e dependências (`requirements.txt`).
- [x] Configuração da suite de testes automatizados com `pytest` (`pytest.ini` e testes iniciais de ambiente).
- [x] Configuração e documentação do **Graphify** para economia de tokens no contexto dos agentes.

---

### 🟢 Fase 2: MVP 1 — Transcrição e Revisão Contextual WhatsApp (Concluída nesta sessão)
- [x] Implementação da API de transcrição utilizando `faster-whisper` (`POST /transcribe`).
- [x] Construção do serviço **AI Gateway** em FastAPI com suporte a Gemini API, OpenRouter e MockProvider (`POST /ai/revise`).
- [x] Configuração do webhook e nós no n8n para receber mensagens de áudio do WhatsApp (Evolution API / Z-API) em `workflows/n8n_whatsapp_voice_transcription.json`.
- [x] Orquestração do fluxo n8n: Recebe Áudio ➔ Transcreve (Whisper) ➔ Revisa Contextualmente (AI Gateway) ➔ Retorna apenas o texto limpo no WhatsApp.
- [x] Criação do manual de validação e execução em `docs/mvp1_whatsapp_workflow.md` com suíte de 15 testes automatizados passando.

---

### 🟢 Fase 3: Criação do Repositório Remoto & Sincronização Git (Concluída)
- [x] Criação do repositório remoto no provedor Git (`git@github.com:brunocorisco86/whisperzap.git`).
- [x] Configuração do remoto local (`git remote add origin <URL>`).
- [x] Realização do primeiro `git push` com a versão madura do MVP 1.
- [x] Ativação da regra de sincronização contínua remota (`git push` obrigatório após cada funcionalidade).

---

### 🟣 Fase 4: Memória em Camadas & Extração Semântica
- [ ] Configuração do banco de dados PostgreSQL com a extensão `pgvector`.
- [ ] Modelagem das tabelas de dados (`messages`, `audio_files`, `transcriptions`, `entities`, `tasks`, `projects`, `topics`, `events`, `decisions`, `ideas`).
- [ ] Construção do pipeline de Extração Semântica silenciosa no AI Gateway (`POST /ai/extract`).
- [ ] Implementação da camada de Grafo com NetworkX para mapear relacionamentos entre entidades (Pessoas ➔ Projetos ➔ Equipamentos ➔ Prazos).
- [ ] Geração e armazenamento de embeddings para busca semântica em memórias.

---

### 🟠 Fase 5: API Memory, Agente Hermes & Automação de Relatórios
- [ ] Desenvolvimento da API REST da Memória (`/api/v1/messages`, `/api/v1/tasks`, `/api/v1/memory/search`, `/api/v1/graph/{entity}`).
- [ ] Integração da API de Memória com o agente **Hermes** para consulta contextual semântica.
- [ ] Automação n8n para envio do **Resumo Diário** (18:00) com acontecimentos do dia e plano para o dia seguinte no WhatsApp.
- [ ] Automação n8n para consolidação e envio do **Relatório Semanal** e planejamento estratégico no domingo à noite.

---

### ⚪ Fase 6: Deploy em Produção (VPS Alpine Linux & Raspberry Pi 3B)
- [ ] Preparação da VPS em Alpine Linux (Docker, Docker Compose).
- [ ] Configuração do Caddy como Reverse Proxy HTTPS automático.
- [ ] Ajuste da rede privada Tailscale conectando o Raspberry Pi 3B (n8n local) e a VPS Alpine Linux.
- [ ] Otimização de recursos computacionais para execução leve em Alpine Linux.
- [ ] Execução da suite de testes completa no ambiente de produção VPS.

---

## 🌟 Itens Bônus & Sidequests

### 🎯 Sidequest 1: Dicionário Léxico & Fine-Tuning de Termos de Negócio (Glossário Hermes)
- [ ] **Mapeamento de Jargões & Fonética de Áudio**:
  - `FAU` ➔ `FAL` (Ficha de Acompanhamento de Lote).
  - `produtor` (contextual) ➔ aplicativo `eProdutor` ou cooperado agropecuário.
  - `Sevale` / `Cvale` ➔ `C.Vale`.
  - `mhotilidade` / `hotelidade` ➔ `mortalidade`.
  - `vazio sanitário`, `água medicada`, `rações e silos`.
- [ ] **Estratégia de Implementação**:
  - **Opção A (API & Memória Hermes)**: Endpoint `/api/v1/dictionary` para injeção dinâmica no prompt de contexto do AI Gateway (`POST /ai/revise` e `POST /ai/extract`).
  - **Opção B (Interface Web / Front-End Leve)**: Interface administrativa simples (ex: Vanilla HTML/CSS/JS ou Vite) para cadastro, edição de sinônimos e termos frequentes pelo usuário.
  - **Opção C (Initial Prompt / Whisper Vocabulary)**: Passar o vocabulário no parâmetro `initial_prompt` do `faster-whisper` para guiar a desambiguação fonética diretamente no Speech-to-Text.

