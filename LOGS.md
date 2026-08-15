# 📜 LOGS de Arquitetura e Sessões — Hermes Voice Memory

Este arquivo registra o histórico de decisões técnicas, marcos do projeto e logs de execução de cada sessão de desenvolvimento.

---

## 📌 Registros de Decisões de Arquitetura (ADRs)

### ADR 001 — Estratégia de Desenvolvimento Local e Produção VPS Alpine
- **Data**: 2026-08-12
- **Status**: Aprovado
- **Contexto**: O projeto necessita de desenvolvimento rápido e testes locais antes de ser submetido à infraestrutura final na VPS e no Raspberry Pi 3B (ambos rodando Alpine Linux).
- **Decisão**: 
  1. O projeto iniciará 100% no ambiente local com repositório Git local (`git init`).
  2. O repositório remoto será criado após a validação do MVP 1 (Transcrição de áudio do WhatsApp).
  3. O suporte ao Alpine Linux será garantido através de contêineres Docker e dependências leves.

### ADR 002 — Economia de Tokens com Graphify
- **Data**: 2026-08-12
- **Status**: Aprovado
- **Contexto**: O uso recorrente de LLMs por agentes de IA durante o desenvolvimento pode gerar alto consumo de tokens e perda de contexto.
- **Decisão**: Adotar a ferramenta **Graphify** (Python) para mapeamento AST do código-fonte e extração de conhecimento relacional persistente, permitindo consultas de alta precisão ao contexto com baixo uso de tokens.

### ADR 003 — Abstração de IAs com AI Gateway
- **Data**: 2026-08-12
- **Status**: Aprovado
- **Contexto**: Evitar dependência direta de um único provedor de LLM (ex: Gemini ou OpenAI) na camada de orquestração do n8n.
- **Decisão**: Construir o serviço **AI Gateway** em FastAPI, permitindo roteamento por tarefa (ex: Gemini Flash-Lite para revisão, modelos mais robustos para análise semanal) e fallback automático.

### ADR 004 — Dicionário Léxico & Fine-Tuning de Termos de Negócio (Glossário Hermes)
- **Data**: 2026-08-13
- **Status**: Aprovado
- **Contexto**: Em áudios com ruído ou falas rápidas de campo, termos técnicos e siglas zootécnicas/corporativas (ex: FAU/FAL, eProdutor, C.Vale, mortalidade, vazio sanitário) podem sofrer pequenas variações fonéticas no Speech-to-Text.
- **Decisão**: Criar um módulo de Dicionário Léxico (Sidequest) que permita cadastrar e mapear sinônimos e jargões para injeção no prompt de contexto da IA (`POST /ai/revise`), no vocabulário inicial do Whisper (`initial_prompt`) e persistência na API de Memória do Hermes.

### ADR 005 — Dimensionamento de Hardware e Recursos para VPS de Entrada (Hostinger)
- **Data**: 2026-08-13
- **Status**: Aprovado
- **Contexto**: O deploy em produção utilizará uma VPS Hostinger de baixo custo (4 GB de RAM, 1-2 vCPUs) compartilhada com outros serviços do homelab (atualmente com 2,4 GB de RAM livres e baixa carga).
- **Decisão**:
  1. Manter o modelo Whisper `base` com quantização `int8` (`compute_type=int8`), limitando o consumo de RAM no pico de inferência a ~350-450 MB e tempo de CPU a ~1-4s por áudio (RTF ~0.12x).
  2. Manter a execução de LLMs via APIs externas (Gemini/OpenRouter), evitando carga de modelos locais pesados na VPS.
  3. Descarregar o motor de automação (n8n) no Raspberry Pi 3B+ conectado via Tailscale, economizando 300-500 MB de RAM na VPS.

### ADR 006 — Seleção de Nó de Borda LAN (Raspberry Pi 3B+ `peixe` vs `alpine-dns`)
- **Data**: 2026-08-14
- **Status**: Aprovado
- **Contexto**: O homelab possui dois nós Raspberry Pi: `ssh peixe` (Raspberry Pi 3B+ Rev 1.3 @ 1.4 GHz) e `ssh alpine` (Raspberry Pi 3B Rev 1.2 @ 1.2 GHz, rodando Pi-hole DNS, Unbound e Mosquitto MQTT).
- **Decisão**: 
  1. Selecionar o nó `ssh peixe` (3B+) para hospedar a automação de borda (n8n + WhatsApp Evolution API), devido à sua CPU 16.7% mais veloz e conexão Gigabit Ethernet.
  2. Preservar o nó `ssh alpine` estritamente dedicado à infraestrutura crítica de rede (DNS/Pi-hole), evitando que picos de automação afetem a latência de resolução de nomes da casa.

### ADR 007 — Gestão de Contatos, Roles e Parser Polimórfico de Tabela Markdown/JSON
- **Data**: 2026-08-14
- **Status**: Aprovado
- **Contexto**: O sistema precisa classificar mensagens e tarefas com prioridades diferenciadas dependendo de quem fala (gestores, diretoria, cônjuge, família, colegas, fornecedores), além de permitir edição rápida e em lote direto no celular via WhatsApp.
- **Decisão**:
  1. Criar o módulo de Contatos com papéis hierárquicos (`EXECUTIVE` 1.0, `FAMILY_CORE` 0.95, `STAKEHOLDER` 0.85, `COLLEAGUE` 0.70, `FAMILY_EXTENDED` 0.60, `SERVICE_VENDOR` 0.50, `UNKNOWN` 0.40).
  2. Implementar o Parser Polimórfico com suporte a Tabela Markdown (`.md`) e JSON (`.json`) para exportação e importação em lote (`POST /api/v1/contacts/batch-import`).
  3. Ponderar dinamicamente a urgência das tarefas no momento do salvamento na memória e enriquecer o Grafo NetworkX com conexões `(Pessoa) -[ROLE]-> (Empresa)` e `(Pessoa) -[WORKS_ON]-> (Projeto)`.

---


## 📝 Histórico de Sessões de Desenvolvimento

### Sessão 001 — Setup Inicial de Governança, Testes e Documentação
- **Data**: 2026-08-12
- **Objetivo**: Organizar a documentação base (`README.md`, `ROADMAP.md`, `LOGS.md`, `docs/architecture.md`), definir subagentes especialistas, criar o template de variáveis de ambiente (`.env.example`), configurar dependências (`requirements.txt`), preparar o ambiente `pytest` e documentar o uso do `graphify`.
- **Ações Realizadas**:
  - Inicialização do repositório Git local (`git init` + `.gitignore`).
  - Criação do `README.md` ressaltando os 3 pilares da solução e a arquitetura.
  - Definição do `ROADMAP.md` em 6 fases (destacando a criação do repositório remoto pós-MVP 1).
  - Criação dos manuais e especificações dos subagentes em `docs/subagents/`.
  - Configuração do `pytest.ini` e escrita do teste de integridade `tests/test_environment.py`.
- **Resultado**: Ambiente de desenvolvimento local 100% estruturado, validado com testes automatizados passando.

### Sessão 002 — Implementação e Validação do MVP 1 (Transcrição & Revisão Contextual WhatsApp)
- **Data**: 2026-08-13
- **Objetivo**: Implementar o primeiro marco funcional (Fase 2) contendo o serviço de Speech-to-Text Whisper (`POST /transcribe`), o serviço AI Gateway (`POST /ai/revise`), fluxo n8n para WhatsApp, tutorial de testes e validação com áudios reais.
- **Ações Realizadas**:
  - Criação do módulo de configuração com Pydantic Settings (`src/config.py`).
  - Implementação do microsserviço de transcrição Whisper com `faster-whisper` (`src/transcriber/`).
  - Implementação do AI Gateway com arquitetura desacoplada (Model Router, prompts contextuais estritos e provedores Gemini, OpenRouter e Mock) em `src/ai_gateway/`.
  - Integração dos roteadores na aplicação unificada FastAPI (`src/main.py`).
  - Criação do workflow exportável para n8n (`workflows/n8n_whatsapp_voice_transcription.json`).
  - Criação do tutorial prático e passo a passo em `docs/tutorial_teste_audio.md` e guia em `docs/mvp1_whatsapp_workflow.md`.
  - Criação e execução da suíte de testes automatizados com `pytest` (15 testes passando com 100% de cobertura nos componentes chave).
  - Validação ponta a ponta com 3 arquivos de áudio reais do WhatsApp em `assets/AudioSample/` (`teste1.ogg`, áudio de 37s e áudio de 14s).
  - Inclusão da Sidequest 1 (Dicionário Léxico & Fine-Tuning de Termos de Negócio) e ADR 004 no Roadmap.
  - Mapeamento e estimativa de consumo de hardware para VPS Hostinger de entrada (ADR 005).
  - Atualização do grafo de conhecimento AST via `graphify`.
- **Aprendizados Chave**:
  - **Eficiência do `faster-whisper` em CPU**: O modelo `base` com `int8` transcreveu um áudio real de 37s em 4.48s (fator de tempo real ~0.12x), com confiança de idioma em 100% e baixíssimo impacto de CPU.
  - **Léxico de Domínio**: Identificada a necessidade de mapeamento fonético para jargões agropecuários e siglas (ex: FAL/FAU, eProdutor, C.Vale, mortalidade, vazio sanitário) registrado na Sidequest 1.
  - **Footprint Leve**: A stack completa do Hermes na VPS consome em torno de 275 MB em repouso e pico de 550-650 MB durante transcrição, perfeitamente compatível com os 1.6 GB disponíveis na VPS.
- **Resultado**: MVP 1 concluído, testado, validado e documentado.

### Sessão 003 — Automação de Benchmarks e Persistência de Resultados de Áudio (`test_results/`)
- **Data**: 2026-08-13
- **Objetivo**: Inicializar o backend FastAPI, executar a suíte de testes com todos os áudios reais de `assets/AudioSample/` contra a API ao vivo, e persistir os resultados estruturados em uma pasta dedicada (`test_results/`).
- **Ações Realizadas**:
  - Criação da pasta [`test_results/`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/test_results) com README explicativo.
  - Criação do script automatizado de benchmark [`scripts/run_audio_tests.py`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/scripts/run_audio_tests.py).
  - Inicialização do backend FastAPI em segundo plano (`src.main:app`).
  - Execução dos testes ponta a ponta (`GET /health`, `POST /transcribe`, `POST /ai/revise`) nos 3 arquivos de áudio do WhatsApp.
  - Geração dos relatórios [`test_results/audio_test_report.json`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/test_results/audio_test_report.json) e [`test_results/audio_test_report.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/test_results/audio_test_report.md).
- **Métricas Registradas**:
  - Duração total de áudio testada: **61.4s**
  - Tempo total de transcrição Whisper: **7.05s**
  - Real-Time Factor (RTF) médio: **0.1148x** (~8.7x mais rápido que tempo real).
- **Resultado**: Resultados de teste salvos e versionados no repositório com script reprodutível.

### Sessão 004 — Configuração e Sincronização do Repositório Remoto GitHub (Fase 3)
- **Data**: 2026-08-14
- **Objetivo**: Conectar o repositório local ao repositório remoto criado no GitHub (`git@github.com:brunocorisco86/whisperzap.git`) e realizar o primeiro push completo de sincronização.
- **Ações Realizadas**:
  - Configuração do remoto `origin` apontando para `git@github.com:brunocorisco86/whisperzap.git`.
  - Execução bem-sucedida de `git push -u origin main` enviando todo o histórico, código do MVP 1, testes e documentação.
  - Atualização do status do projeto para a Fase 4 (Memória em Camadas & Extração Semântica).
- **Resultado**: Fase 3 concluída com repositório remoto 100% sincronizado.

### Sessão 005 — Implementação da Fase 4 (Memória em Camadas & Grafo NetworkX) e Sidequest 1 (Dicionário Léxico)
- **Data**: 2026-08-14
- **Objetivo**: Desenvolver e validar o pipeline de extração semântica estruturada (`POST /ai/extract`), o repositório de memória relacional e vetorial (`src/memory/`), o grafo de relações em NetworkX (`KnowledgeGraph`) e o módulo de Dicionário Léxico de Domínio (`src/dictionary/`).
- **Ações Realizadas**:
  - Implementação do módulo de Dicionário Léxico (`src/dictionary/`) com persistência, variações fonéticas e geração de hints para Whisper e LLMs.
  - Implementação do Extrator Semântico (`SemanticExtractor`) com classificação de intenções (`TASK`, `IDEA`, `DECISION`, `EVENT`, `PROBLEM`, `NOTE`, `QUESTION`), extração de entidades e tarefas com prazo/responsável.
  - Adição do endpoint `POST /ai/extract` no AI Gateway.
  - Implementação da camada de banco de dados SQLAlchemy (`src/memory/models.py`, `src/memory/database.py`) com modelos `MessageRecord`, `TaskRecord`, `EntityRecord`, `EmbeddingRecord`.
  - Implementação do Grafo de Conhecimento relacional com NetworkX (`src/memory/graph.py`) e consulta de vizinhança relacional.
  - Implementação do repositório unificado `MemoryRepository` com cálculo de similaridade de cosseno para busca vetorial (`POST /api/v1/memory/search`).
  - Criação dos endpoints FastAPI da Memória (`/api/v1/memory/messages`, `/api/v1/memory/tasks`, `/api/v1/memory/graph/*`, `/api/v1/memory/stats`).
  - Criação de suíte de testes com 35 testes automatizados (`pytest`), cobrindo 100% dos novos módulos.
  - Atualização do `ROADMAP.md` e do `main.py` com modern lifespan context manager.
- **Resultado**: Fase 4 e Sidequest 1 concluídas com 100% de sucesso e 35 testes passando.

### Sessão 006 — Implementação da Sidequest 2 (Contatos, Roles, Parser Markdown/JSON & Priorização Dinâmica)
- **Data**: 2026-08-14
- **Objetivo**: Criar o sistema de contatos e papéis (*roles*), permitindo importação e exportação em lote via Tabela Markdown (`.md`) e JSON (`.json`), e integrando o motor de prioridade com o repositório de memória e o Grafo NetworkX.
- **Ações Realizadas**:
  - Modelagem da tabela `ContactRecord` em SQLAlchemy e schemas Pydantic com enum `ContactRole` e mapeamento de pesos (`EXECUTIVE` 1.0, `FAMILY_CORE` 0.95, `STAKEHOLDER` 0.85, `COLLEAGUE` 0.70, `FAMILY_EXTENDED` 0.60, `SERVICE_VENDOR` 0.50, `UNKNOWN` 0.40).
  - Implementação do `Parser Polimórfico` (`src/contacts/parser.py`) com suporte bidirecional para Tabela Markdown (`| Telefone | Nome | Papel | Empresa | Projetos |`) e Arrays JSON.
  - Implementação do `ContactService` (`src/contacts/service.py`) com cálculo de peso efetivo, ponderação de prioridade em mensagens/tarefas e sincronização de conexões no Grafo NetworkX (`AFFILIATED_AS` e `WORKS_ON`).
  - Criação dos endpoints REST FastAPI em `src/contacts/router.py` (`GET /api/v1/contacts`, `GET /api/v1/contacts/markdown-table`, `POST /api/v1/contacts/batch-import`, etc.).
  - Integração no `src/memory/repository.py` para enriquecimento automático de prioridade nas mensagens recebidas.
  - Criação de 11 novos testes automatizados (`tests/test_contact_parser.py`, `tests/test_contacts_service.py`, `tests/test_contacts_api.py`), totalizando 46 testes com 100% de aprovação.
- **Resultado**: Sidequest 2 concluída com sucesso total.

### Sessão 007 — Implementação da Fase 5 (API da Memória, Agente Hermes RAG, Relatórios Diários/Semanais e Automações n8n)
- **Data**: 2026-08-14
- **Objetivo**: Desenvolver o motor RAG Híbrido do Agente Hermes, os serviços de síntese diária e semanal com formatação de alto padrão para WhatsApp, e construir os workflows n8n para agendamento Cron e atendimento interativo.
- **Ações Realizadas**:
  - Implementação do serviço `HermesAgentService` (`src/ai_gateway/agent.py`) com inferência para Q&A com citação de fontes, Resumo Diário e Análise Semanal.
  - Expansão dos schemas Pydantic (`src/ai_gateway/schemas.py`) e dos prompts especializados (`src/ai_gateway/prompts.py`).
  - Implementação do método `query_hermes_rag` no repositório (`src/memory/repository.py`), combinando busca vetorial pgvector/cosseno, conexões de entidades do Grafo NetworkX e tarefas abertas.
  - Implementação do pacote `src/reports/` com `daily_report_service` (`src/reports/daily.py`) e `weekly_report_service` (`src/reports/weekly.py`), incluindo geradores de texto legível e amigável para WhatsApp com emojis e destaques.
  - Adição dos endpoints REST FastAPI em `src/memory/router.py`:
    - `POST /api/v1/memory/query` (Consulta RAG Híbrido ao Hermes)
    - `POST /api/v1/memory/daily/generate` e `GET /api/v1/memory/daily` (Resumo Diário & Plano para Amanhã)
    - `POST /api/v1/memory/weekly/generate` e `GET /api/v1/memory/weekly` (Relatório Semanal & Plano de Domingo)
  - Criação de 3 novos workflows n8n automatizados prontos em `workflows/`:
    - `workflows/n8n_daily_summary_cron.json` (Cron 18:00 Seg-Sex)
    - `workflows/n8n_weekly_plan_cron.json` (Cron 20:00 Domingos)
    - `workflows/n8n_hermes_qa_whatsapp.json` (Webhook de consulta direta por WhatsApp)
  - Criação do manual técnico em `docs/phase5_hermes_and_reports.md`.
  - Adição de 7 novos testes unitários e de integração (`tests/test_hermes_agent.py`, `tests/test_daily_report.py`, `tests/test_weekly_report.py`, `tests/test_workflows_json.py`), atingindo 53 testes passando com 100% de sucesso.
  - Atualização do `ROADMAP.md` marcando a Fase 5 como concluída.
- **Resultado**: Fase 5 entregue com sucesso total e repositório pronto para a Fase 6 (Deploy em Produção).

### Sessão 008 — Implementação da Fase 6 (Deploy em Produção VPS Alpine Linux + Raspberry Pi 3B)
- **Data**: 2026-08-14
- **Objetivo**: Containerizar a solução com Docker multi-estágio, orquestrar os serviços com Docker Compose e Caddy HTTPS reverso, criar scripts operacionais de provisionamento/backup/diagnóstico e documentar a topologia Tailscale homelab.
- **Ações Realizadas**:
  - Criação do `Dockerfile` multi-estágio (`python:3.12-slim`), com suporte a `ffmpeg`, `libpq-dev`, cache enxuto e usuário não-root `hermes`.
  - Criação do `.dockerignore` para isolamento de artefatos temporários e de desenvolvimento.
  - Criação do `docker-compose.yml` orquestrando 3 serviços integrados: `hermes-db` (PostgreSQL 16 com `pgvector`), `hermes-api` (FastAPI com healthcheck nativo) e `caddy` (Reverse Proxy com HTTPS automático e compressão zstd/gzip).
  - Criação do `Caddyfile` com cabeçalhos rigorosos de segurança (HSTS, NoSniff, Deny Frame, Remove Server Header).
  - Desenvolvimento dos scripts operacionais em `scripts/`:
    - `scripts/deploy_vps_alpine.sh` (Bootstrap completo em Alpine Linux)
    - `scripts/backup_db.sh` (Backup automatizado do Postgres e Grafo com retenção de 7 dias)
    - `scripts/health_check_prod.sh` (Diagnóstico e checagem de prontidão em produção)
  - Elaboração do manual completo de infraestrutura em `docs/production_deployment_guide.md`.
  - Criação da suite de testes de manifestos de produção em `tests/test_production_manifests.py`, totalizando **58 testes automatizados** passando com 100% de sucesso.
  - Atualização do `ROADMAP.md` marcando **100% das 6 Fases do projeto concluídas**.
- **Resultado**: Fase 6 e todo o ciclo de desenvolvimento do Hermes Voice Memory concluídos com excelência.








