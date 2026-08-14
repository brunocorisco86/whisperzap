# 📐 Arquitetura do Sistema — Hermes Voice Memory

Este documento especifica a arquitetura técnica completa do **Hermes Voice Memory**, abrangendo os microsserviços, o pipeline semântico de áudio e a infraestrutura em nuvem/local.

---

## 💡 Pilares e Princípio Fundamental

O objetivo do sistema é **Transformar comunicação não estruturada em memória estruturada e inteligência acionável**.

```text
VOICE ──► TRANSCRIPTION ──► CONTEXT ──► REVISION ──► MEMORY ──► RELATIONSHIPS ──► INTELLIGENCE ──► ACTION
```

### Os 3 Pilares Fundamentais:
1. **Comunicação Eficiente (Plataforma Centralizada)**:
   - WhatsApp como interface única de voz/texto.
   - n8n como orquestrador transparente de eventos e mensagens.
2. **Processos Otimizados (Redesenho do Fluxo Operacional)**:
   - Resposta imediata apenas com o **texto limpo e revisado** no WhatsApp.
   - Processamento silencioso no backend para extração de entidades, tarefas e intenções sem sobrecarregar o usuário.
3. **Tecnologia Habilitadora**:
   - **AI Gateway (FastAPI)**: Roteamento inteligente de LLMs por custo/tarefa.
   - **Speech-to-Text**: Engine `faster-whisper` em contêiner dedicado.
   - **Memória Tripla**: PostgreSQL (fonte da verdade) + pgvector (busca vetorial) + NetworkX (grafo relacional).
   - **Ambientes Alpine Linux**: VPS de produção e Raspberry Pi 3B (n8n).

---

## 🏗️ Diagrama de Microsserviços e Rede

```text
                               INTERNET
                                  │
                                  ▼
                              WhatsApp
                                  │
                                  ▼
                            WhatsApp API
                                  │
                                  ▼
  ┌───────────────────────────────────────────────────────────────┐
  │                 REDE PRIVADA TAILSCALE                        │
  │                                                               │
  │   ┌────────────────────────┐      ┌───────────────────────┐   │
  │   │  Raspberry Pi 3B       │      │  VPS (Alpine Linux)   │   │
  │   │  (Alpine Linux)        │      │                       │   │
  │   │                        │      │  Caddy Reverse Proxy  │   │
  │   │   n8n Workflow Engine  ├─────►│    ├─ AI Gateway      │   │
  │   │                        │      │    ├─ Whisper API     │   │
  │   └────────────────────────┘      │    ├─ Memory API      │   │
  │                                   │    ├─ PostgreSQL      │   │
  │                                   │    ├─ pgvector        │   │
  │                                   │    └─ NetworkX Graph  │   │
  │                                   └───────────────────────┘   │
  └───────────────────────────────────────────────────────────────┘
```

### 📡 Ambientes Verificados e Aliases SSH:
- **`ssh peixe` (Raspberry Pi 3B na LAN)**: Alpine Linux aarch64 (`piscicultura`), Docker ativo, PostgreSQL 15 rodando, Tailscale instalado, 382 MB de RAM livres.
- **`ssh hostinger` (VPS Hostinger na Nuvem)**: Alpine Linux x86_64 (`srv1828523`), Docker ativo, 2.4 GB de RAM livres, Caddy HTTPS.

---


## 🚪 AI Gateway & Model Router

O **AI Gateway** abstrai os provedores de inteligência artificial para evitar acoplamento direto do n8n com APIs específicas.

### Endpoints Principais:
- `POST /ai/revise`: Transcrição bruta ➔ Texto revisado com pontuação e correção contextual sem inventar fatos.
- `POST /ai/extract`: Texto revisado ➔ Extração JSON de intenções, entidades, tarefas e prioridades.
- `POST /ai/summarize`: Agrupamento de dados do dia ➔ Resumo diário e plano de ação.
- `POST /ai/query`: Consulta semântica à memória com referências gravadas.

### Roteamento por Custo / Tarefa (Model Router):
| Tarefa | Provedor / Modelo Recomendado |
| :--- | :--- |
| Revisão de Transcrição | Gemini Flash-Lite / Modelo Rápido |
| Extração Semântica | Gemini Flash-Lite / Modelo Rápido |
| Resumo Diário | Gemini Flash |
| Análise & Plano Semanal | Modelo Avançado / Robust |
| Consultas Hermes | Roteamento Dinâmico |

---

## 🧠 Memória em Camadas

A informação evolui em 5 níveis de maturidade:

1. **RAW**: Transcrição bruta vinda do Whisper.
2. **REVISED**: Texto corrigido mantendo nomes, números e contexto.
3. **STRUCTURED**: Extração JSON de intenção (`TASK`, `IDEA`, `DECISION`, `PROBLEM`), entidades e prazos.
4. **SEMANTIC**: Embeddings gravados via `pgvector` no PostgreSQL para busca por similaridade.
5. **RELATIONAL**: Grafo em `NetworkX` vinculando Pessoas ➔ Projetos ➔ Equipamentos ➔ Acontecimentos.

---

## 🔒 Segurança e Resiliência
- **Tailscale**: Todo o tráfego entre o Raspberry Pi 3B (n8n) e a VPS ocorre dentro de uma VPN WireGuard criptografada.
- **Variáveis de Ambiente**: Chaves de API de LLMs e credenciais de banco permanecem isoladas no `.env`.
- **Silêncio de Erros no WhatsApp**: Caso ocorra falha de extração semântica, o usuário continua recebendo a transcrição revisada, enquanto o erro é registrado no log interno para reprocessamento.

---

## 📊 Dimensionamento de Recursos & Benchmarks de Produção

A arquitetura foi planejada para operar de forma ultra-eficiente em VPS de entrada (Hostinger Alpine Linux com 4 GB RAM, 1-2 vCPUs) em coabitação com o homelab.

### ⏱️ Benchmarks Observados em CPU (modelo `base`, `int8`):
- **Áudio de 10s**: Transcrito em `~1.7s` (RTF ~0.17x) — Confiança: 100%.
- **Áudio de 37s (Jargões complexos)**: Transcrito em `~4.48s` (RTF ~0.12x) — Confiança: 100%.
- **Áudio de 14s**: Transcrito em `~3.48s` (RTF ~0.24x) — Confiança: 100%.

### 💾 Pegada de Memória (RAM):
| Microsserviço | Estado Ocioso (Idle) | Pico de Execução |
| :--- | :--- | :--- |
| **FastAPI Core + Routers** | ~50 MB | ~70 MB |
| **faster-whisper (CTranslate2)** | ~150 MB | ~350 MB a 450 MB |
| **PostgreSQL + pgvector** | ~60 MB | ~100 MB |
| **Caddy Reverse Proxy** | ~15 MB | ~25 MB |
| **Total Stack Hermes** | **~275 MB** | **~550 MB a 650 MB** |

> **Margem Operacional**: Em uma VPS com 1.600 MB livres, a stack opera com mais de 1.000 MB de margem de segurança.

