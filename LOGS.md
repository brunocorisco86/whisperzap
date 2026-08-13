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
