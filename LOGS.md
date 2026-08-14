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
- **Contexto**: O deploy em produção utilizará uma VPS Hostinger de baixo custo (4 GB de RAM, 1-2 vCPUs) compartilhada com outros serviços do homelab (atualmente com 1,6 GB de RAM livres e 3% de CPU).
- **Decisão**:
  1. Manter o modelo Whisper `base` com quantização `int8` (`compute_type=int8`), limitando o consumo de RAM no pico de inferência a ~350-450 MB e tempo de CPU a ~1-4s por áudio (RTF ~0.12x).
  2. Manter a execução de LLMs via APIs externas (Gemini/OpenRouter), evitando carga de modelos locais pesados na VPS.
  3. Descarregar o motor de automação (n8n) no Raspberry Pi 3B conectado via Tailscale, economizando 300-500 MB de RAM na VPS.
  4. Configurar 2 GB de Swap no disco NVMe da VPS para prevenção de OOM Killer em picos de concorrência.

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


