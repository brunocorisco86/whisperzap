# 🏛️ Hermes Voice Memory — Enterprise Voice Intelligence & Neural Knowledge Graph

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-pgvector-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Production_Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![NetworkX](https://img.shields.io/badge/NetworkX-Knowledge_Graph-FF6F00?style=for-the-badge)](https://networkx.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-F59E0B?style=for-the-badge)](https://opensource.org/licenses/MIT)

> *"Sua voz não é apenas som: é o centro de comando e inteligência operacional do seu negócio."*

O **Hermes Voice Memory** é um ecossistema de inteligência conversacional, memória de longo prazo e copiloto executivo autônomo. Ele transforma mensagens e áudios do WhatsApp em **grafos relacionais de conhecimento, gestão acionável de tarefas, séries temporais de sentimentos e síntese estratégica** com precisão cirúrgica e **zero desperdício de tokens de IA**.

---

## 🎯 Por Que o Hermes? (O Pitch do Produto)

No agronegócio, na gestão executiva e nas operações de alta velocidade, **90% dos direcionamentos críticos acontecem por mensagens e áudios de WhatsApp**. O resultado? Informações perdidas em conversas dispersas, tarefas esquecidas e sobrecarga cognitiva.

O Hermes é a solução corporativa definitiva:

```
                  ┌────────────────────────────────────────────────────────┐
                  │   🎙️ ÁUDIOS & NOTAS DO WHATSAPP                       │
                  └─────────────────────────┬──────────────────────────────┘
                                            │
                                  ⚡ Transcrição Local
                                  🧠 Funil Semântico
                                            │
                  ┌─────────────────────────┴──────────────────────────────┐
                  ▼                                                        ▼
    ┌───────────────────────────┐                            ┌───────────────────────────┐
    │  🕸️ Grafo de Conhecimento  │                            │  📋 Tarefas & Governança  │
    │  Pessoas, Empresas e Nós  │                            │  Quem pediu, prazo e foco │
    └───────────────────────────┘                            └───────────────────────────┘
                  ▲                                                        ▲
                  └─────────────────────────┬──────────────────────────────┘
                                            │
                  ┌─────────────────────────┴──────────────────────────────┐
                  │  👑 OWNER: Deferência total e prioridade executiva     │
                  │  ⭐ Favoritos: +10% de peso operacional no funil       │
                  │  🌡️ Termômetro Emocional: Monitoramento contínuo      │
                  └────────────────────────────────────────────────────────┘
```

### 💡 Os Diferenciais Competitivos
- 🚀 **Economia Inteligente de Tokens (Funil Semântico)**: Descarta ruídos ("ok", saudações vazias, stickers, "Sem texto disponível") na borda, sem gastar tokens LLM ou poluir o banco.
- 👑 **Reconhecimento Supremo do Proprietário (`OWNER`)**: O sistema reconhece notas pessoais do Criador/Arquiteto (`Bruno Conter`), aplicando tom executivo de deferência, prontidão e lealdade máxima nos relatórios e Q&A.
- ⭐ **Sistema de Favoritos Ponderados**: Contatos marcados como favoritos ganham **+10% de peso de prioridade** imediata no motor de relevância.
- 🕸️ **Knowledge Graph em Tempo Real (NetworkX + Graphify)**: Modela quem fala com quem, projetos cruzados e conexões ocultas entre fazendas, cooperativas e departamentos.
- 🧹 **Agente Zeladora (`GraphJanitor`)**: Faxina autônoma semanal que remove ruídos temporais e funde aliases automaticamente.
- 🔒 **Privacidade & Soberania de Dados**: Deploy em infraestrutura híbrida privada (Homelab no Raspberry Pi + VPS dedicada).

---

## 🏗️ Arquitetura e Stack Tecnológica

O sistema opera em uma arquitetura distribuída resiliente e de baixo acoplamento:

```mermaid
flowchart TD
    subgraph EdgeLayer["1. Borda & Ingestão (Raspberry Pi / Homelab)"]
        WA["📱 WhatsApp / Mensagens de Voz"]
        EVO["⚡ Evolution API v2 (Instância Hermes)"]
        N8N["🔄 n8n Orchestrator (Filtro de Grupos & Media Webhook)"]
    end

    subgraph APILayer["2. Motor de IA & Core Engine (VPS Hostinger)"]
        WHISPER["🎙️ Faster-Whisper (Transcrição em Milissegundos)"]
        BYPASS["🛡️ Funil Semântico & Bypass Lexical (Anti-Poluição)"]
        AIGATEWAY["🧠 AI Gateway (Gemini 2.5 Flash / Flash Lite)"]
        LEXICAL["📖 Glossário Fonético & Dicionário Técnico"]
    end

    subgraph StorageLayer["3. Memória em Camadas & Persistência"]
        PG[("🐘 PostgreSQL 16 + pgvector (Embeddings & SQL)")]
        NX[("🕸️ NetworkX Knowledge Graph (hermes_graph.json)")]
        CONTACTS[("👥 Tabela de Contatos, Papéis & Favoritos")]
    end

    subgraph AutonomousLayer["4. Agentes Autônomos de Background"]
        JANITOR["🧹 Zeladora (Graph Janitor - Faxina Semanal)"]
        HARVESTER["🎣 Pescador Léxico (Harvester Diário)"]
        SENTIMENT["🌡️ Consolidador Emocional (Timeline de Humor)"]
        HERMES_RAG["🧠 Hermes RAG Híbrido (Q&A Contextual)"]
    end

    subgraph Interfaces["5. Interfaces & Visualização Executiva"]
        HUB["🖥️ Hermes Web Control Hub (Glassmorphism UI)"]
        DASH["📊 Analytics & Heatmap 24x7 (Chart.js)"]
        GRAPH_VIZ["🌐 Visualizador Interativo de Grafos (Graphify AST)"]
    end

    WA --> EVO
    EVO --> N8N
    N8N --> WHISPER
    WHISPER --> BYPASS
    BYPASS --> AIGATEWAY
    LEXICAL --> AIGATEWAY
    AIGATEWAY --> StorageLayer
    StorageLayer --> AutonomousLayer
    AutonomousLayer --> Interfaces
```

### 🧩 Stack de Engenharia
| Camada | Tecnologia | Papel no Sistema |
| :--- | :--- | :--- |
| **Linguagem & Runtime** | Python 3.12+ / Linux | Desempenho nativo com suporte a tipagem estrita e asyncio |
| **API Framework** | FastAPI + Uvicorn | Servidor assíncrono de alto throughput com OpenAPI e endpoints RESTful |
| **Transcrição Local** | Faster-Whisper (CTranslate2) | Transcrição ultra-rápida de áudio (OGG/MP3/WAV/Base64) em CPU/GPU |
| **AI Gateway** | Google Gemini 2.5 Flash / Lite | Extração de entidades (`NER`), classificação de intenções e RAG Híbrido |
| **Banco Relacional & Vetorial** | PostgreSQL 16 + pgvector | Persistência de mensagens, contatos, tarefas e busca semântica por cosseno |
| **Grafo Relacional** | NetworkX + Graphify | Modelagem de conexões inter-pessoais, detecção de comunidades e clusterização |
| **Orquestração de Borda** | n8n + Evolution API v2 | Ingestão de webhooks, download de mídia e bloqueio preliminar de grupos |
| **Interface & Analytics** | Vanilla JS + Glassmorphism CSS + Chart.js | Painel executivo responsivo, sem overhead de frameworks pesados |
| **Proxy Reverso & SSL** | Caddy v2 | Terminação TLS automática com HTTP/2 e compressão Gzip/Zstandard |

---

## 💎 Funcionalidades em Destaque

### 1. 👑 Papel `OWNER` (Proprietário Supremo)
- **Hierarquia Inviolável**: Peso $1.00$ com tratamento prioritário em todas as rotinas.
- **Reconhecimento de Notas Pessoais**: Identifica automaticamente áudios enviados para si mesmo (`fromMe: true` ou telefone do Bruno Conter), classificando como direcionamento estratégico.
- **Deferência no Agente Hermes**: O assistente responde com tom refinado, cortês e de alto alinhamento executivo.

### 2. ⭐ Contatos Favoritos com +10% de Peso
- **Priorização Dinâmica**: Qualquer contato favoritado no card web ganha **+10% sobre o peso base do seu papel** ($Effective = Base \times 1.10$).
- **Visual Diferenciado**: Cartões com moldura âmbar suave, tag `⭐ +10% Fav` e estrela interativa para toggle com 1 clique.

### 3. 🛡️ Funil Semântico Anti-Poluição (Economia de Tokens)
- **Bloqueio de Mensagens Triviais**: Expressões de baixa relevância (*"bom dia"*, *"ok"*, *"blz"*, *"valeu"*, *"Sem texto disponível"*) são descartadas antes de chamar a IA.
- **Proteção do Histórico**: Garante que o Word Cloud e o grafo não fiquem poluídos com saudações vazias.

### 4. 🧹 Agente Zeladora do Grafo (`GraphJanitor`)
- **Faxina Semanal Programada**: Roda todo Domingo às 23:00.
- **Poda Segura**: Remove nós órfãos temporais (*amanhã*, *ontem*) enquanto protege 100% dos contatos oficiais, empresas e projetos.

---

## 🚀 Instalação e Inicialização Rápida

### 1. Clonagem e Variáveis de Ambiente
```bash
git clone git@github.com:brunocorisco86/whisperzap.git
cd whisperzap

cp .env.example .env
# Preencha suas chaves no .env (GEMINI_API_KEY, DATABASE_URL, etc.)
```

### 2. Execução Local com Docker Compose
```bash
docker compose up -d --build
```
- **Hermes Control Hub**: `http://localhost:8005/`
- **Swagger API Docs**: `http://localhost:8005/docs`
- **Health Check**: `http://localhost:8005/health`

### 3. Execução de Testes Automatizados
```bash
pytest tests/ -v
```

---

## 📡 Principais Endpoints da API

| Método | Endpoint | Descrição |
| :--- | :--- | :--- |
| `POST` | `/transcribe` | Transcrição de áudio via Faster-Whisper |
| `POST` | `/ai/revise` | Revisão contextual de texto com jargões técnicos via AI Gateway |
| `GET` | `/api/v1/contacts` | Lista contatos reais com pesos calculados, status de favorito e sentimentos |
| `PATCH`| `/api/v1/contacts/{id}/favorite` | Alterna o status de favorito do contato (+10% de peso) |
| `DELETE`| `/api/v1/contacts/{id}` | Remove contato no SQL e purga nós associados no Grafo |
| `POST` | `/api/v1/memory/messages` | Salva mensagem com extração semântica e nós no Grafo |
| `GET` | `/api/v1/memory/tasks` | Lista tarefas com ancoragem de solicitante e anotações |
| `PATCH`| `/api/v1/memory/tasks/{id}` | Atualiza status (`DONE`, `CANCELLED`, `PENDING`) e anotações |
| `GET` | `/api/v1/analytics/dashboard` | KPIs executivos, séries temporais, WordMap e Heatmap 24x7 |
| `POST` | `/api/v1/memory/graph/clean` | Dispara faxina da Zeladora (podas, fusão de aliases, deduplicação de cards e purga de órfãos) |
| `POST` | `/api/v1/memory/query` | Consulta ao Hermes com RAG Híbrido e citação de fontes |

---

## 📐 Modelo de Dados (MER / DER) & Privilégio de Identidade

```
 ┌────────────────────────┐         1:N         ┌─────────────────────────┐
 │        CONTACTS        │────────────────────<│        MESSAGES         │
 ├────────────────────────┤                     ├─────────────────────────┤
 │ id (PK: wa_{digits})   │                     │ id (PK: UUID)           │
 │ phone_number (Unique)  │                     │ speaker (FK -> Contact) │
 │ name, nickname, role   │                     │ raw_text, revised_text  │
 │ company, projects_json │                     │ intent, sentiment       │
 │ custom_weight          │                     │ audio_filename          │
 │ is_favorite (Boolean)  │                     │ meta_info (JSON)        │
 └────────────────────────┘                     └────────────┬────────────┘
             │                                               │
             │                                      1:N      │
             │                                  ┌────────────┴────────────┐
             │                                  │                         │
             ▼ 1:N                              ▼ 1:N                     ▼ 1:N
 ┌────────────────────────┐         ┌────────────────────────┐ ┌────────────────────────┐
 │         TASKS          │         │        ENTITIES        │ │       EMBEDDINGS       │
 ├────────────────────────┤         ├────────────────────────┤ ├────────────────────────┤
 │ id (PK: UUID)          │         │ id (PK: UUID)          │ │ id (PK: UUID)          │
 │ message_id (FK)        │         │ message_id (FK)        │ │ message_id (FK)        │
 │ assignee (FK -> Contact│         │ name, category         │ │ text_content           │
 │ title, due_date, status│         │ details, created_at    │ │ embedding (Vector 768) │
 └────────────────────────┘         └────────────────────────┘ └────────────────────────┘
```

> **Princípio Sagrado da Memória**: *A história é escrita pelos vitoriosos; contatos sem cartão oficial não geram conhecimento nem tarefas.*
> - Nenhuma mensagem entra no **AI Gateway** nem é salva na **Memória MUSA** se o remetente não for o **Proprietário (`Bruno Conter`)** ou um **Contato Oficial com Cartão Cadastrado** (`ContactRecord`).
> - A **Zeladora (`GraphJanitorService`)** realiza deduplicação contínua de cartões (resolvendo variações fonéticas e telefones com/sem DDI) e purga registros órfãos.

---

## 🗺️ Roadmap Estratégico & Ideação de Produto

- [x] **Privilégio Estrito de Identidade**: Bloqueio de grupos e filtro de entrada no AI Gateway baseado na tabela de contatos com cartão.
- [x] **Bonificação de Favoritos**: Multiplicador de +10% de peso sobre o papel para contatos favoritados.
- [x] **Deduplicação de Cards & Purga de Órfãos na Zeladora**: Fusão automática de duplicatas e eliminação de tarefas sem autor.
- [ ] **MUSA Intelligent Profile Enrichment (Edição Cognitiva de Cards via RAG)** *(Ideação Detalhada Abaixo)*
- [ ] **Voice Push Notifications**: Envio de alertas de voz sintetizados para tarefas de alta prioridade.
- [ ] **MUSA Graph Clustering Auto-Tuning**: Detecção automática de novas comunidades temáticas no Grafo Social.

---

### 💡 Ideação Arquitetural: MUSA Intelligent Profile Enrichment

```
 ┌────────────────────────┐
 │   Card do Contato na   │ ──(Usuário clica em "✨ Sugestão RAG")──┐
 │   Interface Web        │                                         │
 └────────────────────────┘                                         ▼
                                                   ┌─────────────────────────────────┐
                                                   │ 1. RAG Longitudinal MUSA        │
                                                   │    - Varredura de 90 dias       │
                                                   │    - Vizinhos no Grafo NetworkX │
                                                   │    - Tarefas & Sentimentos      │
                                                   └────────────────┬────────────────┘
                                                                    │
                                                                    ▼
                                                   ┌─────────────────────────────────┐
                                                   │ 2. Hermes Synthesis Engine      │
                                                   │    - Deduz papel ideal e peso   │
                                                   │    - Identifica novos projetos  │
                                                   │    - Mapeia empresas e fazendas │
                                                   │    - Gera dossiê de notas       │
                                                   └────────────────┬────────────────┘
                                                                    │
                                                                    ▼
 ┌────────────────────────┐                        ┌─────────────────────────────────┐
 │   Card Atualizado e    │ ◄──(Aprovação "1-Clique")│ 3. Painel Diff (Antes vs Depois)│
 │   Grafo Calibrado      │                        │    - Recomendações prontas      │
 └────────────────────────┘                        └─────────────────────────────────┘
```

#### 1. A Oportunidade
Conforme os meses avançam, a **MUSA** acumula dezenas de mensagens, intenções e conexões sobre cada parceiro, produtor rural ou executivo. Manter o perfil dos contatos (cargo, projetos ativos, empresa, notas de comportamento) atualizado manualmente é demorado.

#### 2. Como Funciona a Experiência (UX)
1. **Acionamento Human-in-the-Loop**: Ao abrir o modal de um contato com mais de 10 interações registradas, o botão **`✨ Sugestão Cognitiva (RAG MUSA)`** fica destacado.
2. **Análise Multi-Modal**:
   - **Camada Vetorial (`pgvector`)**: Analisa todas as transcrições e mensagens do interlocutor.
   - **Camada Estrutural (Grafo MUSA)**: Analisa com quem ele se conecta (quais silos, sistemas, fazendas e outras pessoas ele cita).
   - **Série Temporal de Humor**: Analisa a estabilidade emocional e padrões de urgência.
3. **Proposta Estruturada da IA**:
   - **Papel Hierárquico Recomendado**: ex: sugere migrar de `COLLEAGUE` para `EXECUTIVE` devido a decisões de compras e alinhamento de diretoria.
   - **Empresa / Unidade**: Detecta menções a *"C.Vale Palotina"*, *"Fazenda São Bento"*, etc.
   - **Projetos Ativos**: Extrai tags dinâmicas como `["Silo 4", "Auditoria Miratorg", "Calibração Sensores"]`.
   - **Dossiê / Anotações**: Redige um resumo executivo com pontos fortes, estilo de comunicação e preferências operacionais.
4. **Aprovação em 1-Clique**: O usuário vê o comparativo visual do que mudou e aprova com um único clique, atualizando o SQL e rebalanceando os pesos do Grafo de Conhecimento.

---

## 👥 Governança & Créditos

- **Criador, Proprietário & Arquiteto**: Bruno Conter
- **Domínio de Aplicação**: Gestão Operacional, Inteligência de Agronegócio e Homelab Executivo
- **Repositório Oficial**: [github.com/brunocorisco86/whisperzap](https://github.com/brunocorisco86/whisperzap)
- **Licença**: MIT
