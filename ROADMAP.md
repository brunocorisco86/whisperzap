# 🗺️ Roadmap de Desenvolvimento — Hermes Voice Memory

Este documento estabelece o plano de desenvolvimento de **6 meses** para a construção e maturação do **Hermes Voice Memory**.

---

## 🚩 Status Atual: Fase 4 Concluída (Próximo: Fase 5 — API da Memória & Agente Hermes)

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
FASE 4: Memória em Camadas (Postgres + pgvector + NetworkX) [CONCLUÍDO]
   │
   ▼
FASE 5: API da Memória & Agente Hermes (Resumos Diários/Semanais) [PRÓXIMO]
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

### 🟢 Fase 2: MVP 1 — Transcrição e Revisão Contextual WhatsApp (Concluída)
- [x] Implementação da API de transcrição utilizando `faster-whisper` (`POST /transcribe`).
- [x] Construção do serviço **AI Gateway** em FastAPI com suporte a Gemini API, OpenRouter e MockProvider (`POST /ai/revise`).
- [x] Configuração do webhook e nós no n8n para receber mensagens de áudio do WhatsApp (Evolution API / Z-API) em `workflows/n8n_whatsapp_voice_transcription.json`.
- [x] Orquestração do fluxo n8n: Recebe Áudio ➔ Transcreve (Whisper) ➔ Revisa Contextualmente (AI Gateway) ➔ Retorna apenas o texto limpo no WhatsApp.
- [x] Criação do manual de validação e execução em `docs/mvp1_whatsapp_workflow.md` com suíte de testes automatizados passando.

---

### 🟢 Fase 3: Criação do Repositório Remoto & Sincronização Git (Concluída)
- [x] Criação do repositório remoto no provedor Git (`git@github.com:brunocorisco86/whisperzap.git`).
- [x] Configuração do remoto local (`git remote add origin <URL>`).
- [x] Realização do primeiro `git push` com a versão madura do MVP 1.
- [x] Ativação da regra de sincronização contínua remota (`git push` obrigatório após cada funcionalidade).

---

### 🟢 Fase 4: Memória em Camadas & Extração Semântica (Concluída nesta sessão)
- [x] Configuração do banco de dados relacional e vetorial (SQLAlchemy com suporte a PostgreSQL/pgvector e fallback SQLite local).
- [x] Modelagem das tabelas de dados (`messages`, `tasks`, `entities`, `embeddings`).
- [x] Construção do pipeline de Extração Semântica silenciosa no AI Gateway (`POST /ai/extract`).
- [x] Implementação da camada de Grafo com NetworkX para mapear relacionamentos entre entidades (Pessoas ➔ Projetos ➔ Equipamentos ➔ Prazos).
- [x] Geração e armazenamento de embeddings para busca semântica em memórias (`POST /api/v1/memory/search`).
- [x] Criação dos endpoints da API de Memória (`/api/v1/memory/messages`, `/api/v1/memory/tasks`, `/api/v1/memory/graph/*`, `/api/v1/memory/stats`).

---

### 🟠 Fase 5: API Memory, Agente Hermes & Automação de Relatórios (Próxima)
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

### 🟢 Sidequest 1: Dicionário Léxico & Fine-Tuning de Termos de Negócio (Glossário Hermes) [CONCLUÍDO]
- [x] **Mapeamento de Jargões & Fonética de Áudio**:
  - `FAU` ➔ `FAL` (Ficha de Acompanhamento de Lote).
  - `produtor` (contextual) ➔ aplicativo `eProdutor` ou cooperado agropecuário.
  - `Sevale` / `Cvale` ➔ `C.Vale`.
  - `mhotilidade` / `hotelidade` ➔ `mortalidade`.
  - `vazio sanitário`, `água medicada`, `rações e silos`.
- [x] **Implementação Entregue**:
  - Endpoint `/api/v1/dictionary` para cadastro e consulta de termos.
  - Injeção dinâmica no prompt de contexto do AI Gateway (`POST /ai/revise` e `POST /ai/extract`).
  - Formatação para vocabulário inicial do Whisper (`initial_prompt`).
  - Suíte de testes unitários e de integração com 100% de sucesso.

### 🟢 Sidequest 2: Gestão de Contatos, Papéis (Roles) & Ponderação de Prioridade [CONCLUÍDO]
- [x] **Modelagem & Classificação de Papéis**:
  - `EXECUTIVE` (Gestores, Diretores — peso 1.0)
  - `FAMILY_CORE` (Cônjuge, Mãe, Pai, Filhos — peso 0.95)
  - `STAKEHOLDER` (Clientes, Sponsors de projetos — peso 0.85)
  - `COLLEAGUE` (Pares, Colegas de squad — peso 0.70)
  - `FAMILY_EXTENDED` (Sogros, Parentes — peso 0.60)
  - `SERVICE_VENDOR` (Fornecedores — peso 0.50)
  - `UNKNOWN` (Não Mapeado — peso 0.40)
- [x] **Parser Polimórfico de Templates**:
  - Exportação e importação em lote via **Tabela Markdown (`.md`)** e **Array JSON (`.json`)**.
  - Reconhecimento de sinônimos em português (ex: `GESTOR`, `ESPOSA`, `FORNECEDOR`).
- [x] **Motor de Prioridade Dinâmica & Grafo**:
  - Ponderação automática de tarefas e mensagens no salvamento (`src/memory/repository.py`).
  - Enriquecimento de nós no Grafo NetworkX com conexões `(Pessoa) -[ROLE]-> (Empresa)` e `(Pessoa) -[WORKS_ON]-> (Projeto)`.
  - Endpoints REST em `/api/v1/contacts/*` com 11 novos testes automatizados passando.




