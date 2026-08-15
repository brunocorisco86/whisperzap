# 🗺️ Roadmap de Desenvolvimento — Hermes Voice Memory

Este documento estabelece o plano de desenvolvimento de **6 meses** para a construção e maturação do **Hermes Voice Memory**.

---

## 🚩 Status Atual: Todas as 6 Fases Concluídas (100% do Roadmap Entregue)

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
FASE 5: API da Memória & Agente Hermes (Resumos Diários/Semanais) [CONCLUÍDO]
   │
   ▼
FASE 6: Deploy em Produção (VPS Alpine Linux + Raspberry Pi 3B) [CONCLUÍDO]
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

### 🟢 Fase 4: Memória em Camadas & Extração Semântica (Concluída)
- [x] Configuração do banco de dados relacional e vetorial (SQLAlchemy com suporte a PostgreSQL/pgvector e fallback SQLite local).
- [x] Modelagem das tabelas de dados (`messages`, `tasks`, `entities`, `embeddings`).
- [x] Construção do pipeline de Extração Semântica silenciosa no AI Gateway (`POST /ai/extract`).
- [x] Implementação da camada de Grafo com NetworkX para mapear relacionamentos entre entidades (Pessoas ➔ Projetos ➔ Equipamentos ➔ Prazos).
- [x] Geração e armazenamento de embeddings para busca semântica em memórias (`POST /api/v1/memory/search`).
- [x] Criação dos endpoints da API de Memória (`/api/v1/memory/messages`, `/api/v1/memory/tasks`, `/api/v1/memory/graph/*`, `/api/v1/memory/stats`).

---

### 🟢 Fase 5: API Memory, Agente Hermes & Automação de Relatórios (Concluída)
- [x] Integração da API de Memória com o agente **Hermes** para consulta contextual semântica com **RAG Híbrido** e citação de fontes (`POST /api/v1/memory/query`).
- [x] Motor de geração de **Resumo Diário** (18:00) com acontecimentos do dia e plano priorizado para o dia seguinte no WhatsApp (`POST /api/v1/memory/daily/generate` e `GET /api/v1/memory/daily`).
- [x] Motor de consolidação de **Inteligência Semanal** e plano estratégico para o domingo à noite (`POST /api/v1/memory/weekly/generate` e `GET /api/v1/memory/weekly`).
- [x] Workflows n8n automatizados com Agendadores Cron e Webhook interativo para WhatsApp (`workflows/n8n_daily_summary_cron.json`, `workflows/n8n_weekly_plan_cron.json`, `workflows/n8n_hermes_qa_whatsapp.json`).
- [x] Documentação técnica completa em `docs/phase5_hermes_and_reports.md` e 53 testes automatizados passando com 100% de sucesso.

---

### 🟢 Fase 6: Deploy em Produção (VPS Alpine Linux & Raspberry Pi 3B) (Concluída)
- [x] Construção de `Dockerfile` multi-estágio otimizado para CPU, `ffmpeg`, `faster-whisper` e usuário não-root.
- [x] Orquestração da stack de produção em `docker-compose.yml` (`hermes-api`, `hermes-db` PostgreSQL 16 com `pgvector`, e `caddy` Reverse Proxy).
- [x] Configuração do `Caddyfile` com cabeçalhos de segurança, compressão e HTTPS automático.
- [x] Criação de scripts operacionais em `scripts/`: deploy automatizado em Alpine Linux (`deploy_vps_alpine.sh`), rotina de backup com retenção de 7 dias (`backup_db.sh`) e health check de produção (`health_check_prod.sh`).
- [x] Guia operacional completo de deploy, topologia Tailscale e disaster recovery em `docs/production_deployment_guide.md`.
- [x] 58 testes automatizados passando com 100% de aprovação.


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

---

## 🚀 Trilha Prática de Go-Live & Ativação Operacional Passo a Passo

### 📍 Etapa 1: Validação Local Interativa (Agora no seu PC) [CONCLUÍDA]
- [x] **1.1** Iniciar o servidor da API localmente (`uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload`).
- [x] **1.2** Abrir o Swagger UI no navegador em `http://localhost:8000/docs`.
- [x] **1.3** Testar o endpoint `POST /transcribe` enviando um arquivo de áudio real de `assets/AudioSample/`.
- [x] **1.4** Testar `POST /api/v1/memory/messages` enviando uma instrução de voz simulada.
- [x] **1.5** Testar `POST /api/v1/memory/query` fazendo uma pergunta em linguagem natural para o Hermes.
- [x] **1.6** Visualizar o Resumo Diário (`/api/v1/memory/daily`) e Relatório Semanal (`/api/v1/memory/weekly`).

### 📍 Etapa 2: Conexão com WhatsApp & n8n (Homelab / Raspberry Pi) [EM ANDAMENTO]
- [x] **2.1** Subir a stack de WhatsApp no homelab (`./scripts/start_homelab_whatsapp.sh` ou Docker Compose).
- [x] **2.2** Conectar o WhatsApp na Evolution API via QR Code (`http://localhost:8080`).
- [x] **2.3** Acessar o n8n (`http://localhost:5678`), criar o usuário admin e importar os 4 fluxos da pasta `workflows/`.
- [x] **2.4** Ativar o fluxo de transcrição (`n8n_whatsapp_voice_transcription.json`) e enviar um áudio de teste no WhatsApp.
- [ ] **2.5** Validar o disparo do Resumo Diário e do comando `? pergunta` para o Agente Hermes.

### 📍 Etapa 3: Deploy em Produção (VPS Alpine Linux & Tailscale)
- [ ] **3.1** Conectar na VPS via SSH e clonar o repositório em `/opt/whisperzap`.
- [ ] **3.2** Configurar o arquivo `.env` de produção com chaves seguras e `GEMINI_API_KEY`.
- [ ] **3.3** Executar o script automatizado `./scripts/deploy_vps_alpine.sh`.
- [ ] **3.4** Conectar o Tailscale na VPS (`tailscale up`) e no Raspberry Pi para criar a rede mesh privada.
- [ ] **3.5** Apontar o n8n para o IP Tailscale da VPS (`http://100.x.y.z:8000`).
- [ ] **3.6** Agendar o Cron de backup diário às 03:00 (`scripts/backup_db.sh`).





