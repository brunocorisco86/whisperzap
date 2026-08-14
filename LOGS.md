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

### Sessão 002 — Implementação do MVP 1 (Transcrição & Revisão Contextual WhatsApp)
- **Data**: 2026-08-13
- **Objetivo**: Implementar o primeiro marco funcional (Fase 2) contendo o serviço de Speech-to-Text Whisper (`POST /transcribe`), o serviço AI Gateway (`POST /ai/revise`), fluxo n8n para WhatsApp e suite completa de testes automatizados.
- **Ações Realizadas**:
  - Criação do módulo de configuração com Pydantic Settings (`src/config.py`).
  - Implementação do microsserviço de transcrição Whisper com `faster-whisper` (`src/transcriber/`).
  - Implementação do AI Gateway com arquitetura desacoplada (Model Router, prompts contextuais estritos e provedores Gemini, OpenRouter e Mock) em `src/ai_gateway/`.
  - Integração dos roteadores na aplicação unificada FastAPI (`src/main.py`).
  - Criação do workflow exportável para n8n (`workflows/n8n_whatsapp_voice_transcription.json`).
  - Criação do guia completo de execução e testes (`docs/mvp1_whatsapp_workflow.md`).
  - Criação e execução da suíte de testes unitários e de integração HTTP com `pytest` (15 testes passando).
  - Atualização do mapa de conhecimento AST via `graphify`.
- **Resultado**: MVP 1 concluído com sucesso e pronto para deploy/integração.

