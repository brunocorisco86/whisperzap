# 🧠 Hermes Voice Memory

> **Sistema pessoal de captura, memória e inteligência operacional por voz**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Framework FastAPI](https://img.shields.io/badge/framework-FastAPI-green.svg)](https://fastapi.tiangolo.com/)
[![Tests Pytest](https://img.shields.io/badge/tests-pytest-orange.svg)](https://docs.pytest.org/)
[![Graphify Context](https://img.shields.io/badge/context-Graphify-purple.svg)](https://github.com/safishamsi/graphify)

O **Hermes Voice Memory** transforma mensagens de voz enviadas pelo WhatsApp em informação estruturada, memória contextual, grafos de relacionamento e planos de ação automatizados.

---

## 🎯 Pilares da Solução

O projeto é construído sob **três pilares fundamentais**:

1. **📢 Comunicação Eficiente (Plataforma Centralizada)**
   - WhatsApp como interface única e transparente de captura e comunicação no dia a dia.
   - n8n atua como a camada de orquestração de workflows e integração.

2. **⚙️ Processos Otimizados (Redesenho do Fluxo Operacional)**
   - O usuário envia um áudio ➔ o sistema transcreve ➔ revisa silenciosamente com contexto sem expor JSONs ou ruído técnico ➔ retorna o **texto limpo e revisado** no WhatsApp.
   - Gravação silenciosa em memória de intenções, tarefas, decisões, problemas e ideias.
   - Geração automática de resumos diários, planos para o dia seguinte, consolidações semanais e planejamento estratégico aos domingos.

3. **🛠️ Tecnologia Habilitadora**
   - **AI Gateway (FastAPI)**: Abstração de modelos (Gemini, OpenRouter, LLMs locais) com roteamento inteligente por custo/tarefa.
   - **Speech-to-Text**: `faster-whisper` dedicado para transcrição local/API.
   - **Armazenamento de Memória**: PostgreSQL (fonte da verdade) + `pgvector` (memória semântica) + NetworkX (análise relacional de grafos).
   - **Infraestrutura**: Alpine Linux (rodando em VPS de produção e no Raspberry Pi 3B com n8n), conteinerização Docker e segurança de rede com Tailscale.

---

## 🏗️ Arquitetura do Sistema

```text
                                USUÁRIO
                                   │
                                   │ 🎙️ Áudio
                                   ▼
                               WHATSAPP
                                   │
                                   ▼
                              WHATSAPP API
                                   │
                                   ▼
                                  n8n (Raspberry Pi 3B / Alpine)
                                   │
                                   ▼
                           DOWNLOAD DE ÁUDIO
                                   │
                                   ▼
                              WHISPER API
                                   │
                                   ▼
                            AI GATEWAY (FastAPI / VPS Alpine)
                                   │
                                   ├──────────────► WHATSAPP (Texto Revisado)
                                   │
                                   ▼
                           EXTRAÇÃO SEMÂNTICA
                                   │
                                   ▼
                                MEMÓRIA
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
                PostgreSQL      pgvector        Graph (NetworkX)
                    │              │              │
                    └──────────────┼──────────────┘
                                   ▼
                             HERMES / API
```

---

## 💻 Ambiente de Desenvolvimento vs Produção

- **Ambiente de Desenvolvimento (Local)**:
  - Desenvolvimento e testes locais em Python 3.10+.
  - Utilização do **Graphify** para mapeamento do código/documentação e economia de tokens dos agentes IA.
  - Execução de testes automatizados com `pytest`.
- **Ambiente de Produção (VPS / Alpine Linux)**:
  - Deploy conteinerizado (Docker em Alpine Linux).
  - Reverse Proxy via Caddy com suporte a HTTPS automático.
  - Comunicação privada via Tailscale VPN.
  - n8n rodando no Raspberry Pi 3B (Alpine Linux).

---

## 🚀 Como Iniciar no Desenvolvimento Local

### 1. Clonar e configurar o ambiente
```bash
git clone <repository_url> # (Após criação do remoto pós-MVP 1)
cd 9_Voice_Assistant

# Criar e ativar ambiente virtual Python
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

### 2. Configurar Variáveis de Ambiente
```bash
cp .env.example .env
# Edite o arquivo .env com suas chaves de API locais/desenvolvimento
```

### 3. Executar a Suite de Testes
```bash
pytest -v
```

### 4. Executar o Servidor FastAPI
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```
Acesse a documentação Swagger em: [http://localhost:8000/docs](http://localhost:8000/docs).

---

## 🕸️ Uso do Graphify no Desenvolvimento

Para garantir que os agentes de IA tenham acesso a contexto profundo do código sem desperdício de tokens, utilizamos o **Graphify**:

```bash
# Gerar/atualizar o grafo de conhecimento AST
graphify extract . --code-only

# Listar os principais nós arquiteturais (god nodes)
graphify god-nodes
```

Consulte o documento [`docs/graphify_guide.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/graphify_guide.md) para detalhes.

---

## 📚 Documentação do Projeto

- 🗺️ [`ROADMAP.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/ROADMAP.md): Planejamento e fases de desenvolvimento (inclui Sidequests).
- 📜 [`LOGS.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/LOGS.md): Histórico de decisões de arquitetura (ADRs 001 a 005) e sessões.
- 📐 [`docs/architecture.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/architecture.md): Detalhamento da arquitetura técnica e dimensionamento de hardware.
- 🎙️ [`docs/tutorial_teste_audio.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/tutorial_teste_audio.md): Tutorial passo a passo para envio e teste de áudio WhatsApp.
- 🔄 [`docs/mvp1_whatsapp_workflow.md`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/mvp1_whatsapp_workflow.md): Guia de importação e configuração do fluxo n8n.
- 🤖 [`docs/subagents/`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/docs/subagents/): Definição dos subagentes especialistas.

