# 🧠 Hermes Voice Memory

## Sistema pessoal de captura, memória e inteligência operacional por voz

**Versão:** 1.0
**Horizonte inicial:** 6 meses
**Status:** Ideação / Arquitetura
**Objetivo:** Transformar mensagens de voz em informação estruturada, memória contextual e planos de ação.

---

# 1. Visão

O **Hermes Voice Memory** será um sistema pessoal de inteligência baseado em mensagens de voz enviadas pelo WhatsApp.

O usuário poderá simplesmente enviar um áudio durante o dia.

O sistema irá:

1. receber o áudio;
2. transcrevê-lo;
3. revisar a transcrição utilizando contexto;
4. devolver **somente o texto revisado pelo WhatsApp**;
5. interpretar semanticamente o conteúdo;
6. identificar intenções, entidades, tarefas, projetos, problemas, decisões e ideias;
7. armazenar essas informações em uma memória estruturada;
8. gerar um resumo diário;
9. gerar um plano de ação para o dia seguinte;
10. consolidar os acontecimentos semanalmente;
11. analisar relações entre pessoas, projetos, assuntos e acontecimentos;
12. gerar um relatório semanal denso;
13. gerar, no domingo à noite, o plano da semana seguinte;
14. disponibilizar a memória através de uma API para o **Hermes** e futuros agentes de IA.

O WhatsApp será a **interface de captura e comunicação**.

O n8n será a **camada de orquestração**.

A VPS será a **infraestrutura central de processamento, memória e inteligência**.

O AI Gateway será a **camada de abstração dos modelos de IA**.

---

# 2. Princípio fundamental

O projeto não deve ser tratado como um simples sistema de transcrição.

O objetivo final é:

```text
VOICE
  ↓
TRANSCRIPTION
  ↓
CONTEXT
  ↓
UNDERSTANDING
  ↓
MEMORY
  ↓
RELATIONSHIPS
  ↓
INTELLIGENCE
  ↓
ACTION
```

Ou:

> **Transformar comunicação não estruturada em memória estruturada e inteligência acionável.**

---

# 3. Experiência do usuário

A experiência durante o expediente deve ser extremamente simples.

O usuário envia:

```text
🎙️ Áudio
```

O sistema processa.

O usuário recebe:

```text
📝 Texto revisado
```

Nenhuma informação técnica deve ser enviada durante o processamento normal.

Não enviar:

* JSON;
* classificação;
* intenção;
* resumo;
* entidades;
* explicações da IA;
* mensagens técnicas.

Todas essas informações serão armazenadas silenciosamente.

---

# 4. Fluxo principal

```text
                       USUÁRIO
                          │
                          │ 🎙️
                          ▼
                      WHATSAPP
                          │
                          ▼
                   WHATSAPP API
                          │
                          ▼
                        n8n
                          │
                          ▼
                   DOWNLOAD ÁUDIO
                          │
                          ▼
                  WHISPER API
                          │
                          ▼
                 TRANSCRIÇÃO BRUTA
                          │
                          ▼
                    AI GATEWAY
                          │
                          ▼
                REVISÃO CONTEXTUAL
                          │
                          ├──────────────► WHATSAPP
                          │                  │
                          │                  ▼
                          │             TEXTO REVISADO
                          │
                          ▼
                  EXTRAÇÃO SEMÂNTICA
                          │
                          ▼
                       MEMÓRIA
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
          PostgreSQL    pgvector      Graph
              │           │           │
              └───────────┼───────────┘
                          ▼
                     INTELLIGENCE
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
            DIÁRIO      SEMANAL      HERMES
              │           │           │
              ▼           ▼           ▼
          WhatsApp     WhatsApp       API
```

---

# 5. Arquitetura de infraestrutura

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
┌───────────────────────────────────────┐
│              VPS                      │
│                                       │
│  Caddy                                │
│    │                                  │
│    ├── n8n                            │
│    ├── AI Gateway                     │
│    ├── Whisper API                    │
│    ├── Memory API                     │
│    ├── PostgreSQL                     │
│    ├── pgvector                       │
│    └── Storage                        │
│                                       │
└───────────────────────────────────────┘
          │
          │ Tailscale
          ▼
    Raspberry Pi
          │
          ▼
         n8n
```

A arquitetura poderá manter o n8n no Raspberry Pi 3B conforme a infraestrutura existente, enquanto os serviços computacionalmente mais pesados permanecem na VPS.

---

# 6. Componentes principais

| Componente      | Tecnologia            | Função                                 |
| --------------- | --------------------- | -------------------------------------- |
| WhatsApp        | Evolution API / Z-API | Entrada e saída de mensagens           |
| Orquestração    | n8n                   | Workflow e automações                  |
| Transcrição     | faster-whisper        | Speech-to-text                         |
| API de IA       | FastAPI               | AI Gateway                             |
| LLM principal   | Gemini API            | Processamento semântico                |
| LLM alternativo | OpenRouter            | Roteamento/testes/modelos alternativos |
| Banco           | PostgreSQL            | Fonte da verdade                       |
| Vetores         | pgvector              | Memória semântica                      |
| Grafos          | NetworkX inicialmente | Análise de relações                    |
| Proxy           | Caddy                 | HTTPS/reverse proxy                    |
| Rede            | Tailscale             | Comunicação privada                    |
| Backend         | Python/FastAPI        | APIs e serviços                        |
| Automação       | n8n                   | Orquestração                           |

---

# 7. AI Gateway

O sistema **não deverá depender diretamente de um único provedor de LLM**.

Será criado um serviço intermediário:

```text
AI Gateway
```

Responsável por:

* abstrair provedores;
* padronizar requisições;
* padronizar respostas;
* selecionar modelos;
* controlar custos;
* registrar métricas;
* permitir troca de modelos;
* implementar fallback;
* controlar contexto;
* controlar prompts;
* impedir acoplamento do n8n ao fornecedor.

Arquitetura:

```text
                    AI GATEWAY
                        │
             ┌──────────┼──────────┐
             ▼          ▼          ▼
          Gemini    OpenRouter   Local LLM
```

---

# 8. Model Router

O AI Gateway deverá permitir roteamento por tarefa.

Exemplo:

```text
/revise
    → Gemini Flash-Lite

/extract
    → Gemini Flash-Lite

/daily-summary
    → Gemini Flash

/weekly-analysis
    → Gemini Flash / modelo mais robusto

/weekly-plan
    → modelo mais robusto

/hermes
    → modelo selecionado dinamicamente
```

A configuração deverá ser feita por variáveis de ambiente.

Exemplo:

```env
AI_PROVIDER=gemini
AI_MODEL=gemini-2.5-flash-lite

OPENROUTER_API_KEY=
GEMINI_API_KEY=

AI_LOG_PROMPTS=false
AI_LOG_RESPONSES=false
```

O sistema deverá permitir futuramente:

```env
AI_PROVIDER=openrouter
AI_MODEL=<modelo>
```

sem alteração da arquitetura principal.

---

# 9. Estratégia de modelos

Inicialmente:

| Tarefa                 | Estratégia                       |
| ---------------------- | -------------------------------- |
| Revisão de transcrição | modelo rápido/econômico          |
| Extração semântica     | modelo rápido/econômico          |
| Classificação          | modelo rápido/econômico          |
| Resumo diário          | modelo intermediário             |
| Análise semanal        | modelo intermediário/avançado    |
| Planejamento semanal   | modelo avançado                  |
| Hermes                 | roteamento conforme complexidade |

O princípio é:

> **Não utilizar um modelo caro para uma tarefa simples.**

---

# 10. Endpoints do AI Gateway

Estrutura inicial:

```text
POST /ai/revise
POST /ai/extract
POST /ai/summarize
POST /ai/analyze
POST /ai/plan
POST /ai/query
```

Exemplo:

```http
POST /ai/revise
```

Entrada:

```json
{
  "text": "entao amanha preciso fala com joao...",
  "context": "..."
}
```

Saída:

```json
{
  "text_revised": "Então, amanhã preciso falar com João..."
}
```

---

# 11. Transcrição

O serviço Whisper deverá funcionar independentemente do AI Gateway.

```text
POST /transcribe
```

Entrada:

```text
multipart/form-data
file = audio.ogg
```

Saída:

```json
{
  "audio_id": "audio_001",
  "language": "pt",
  "language_probability": 0.98,
  "text": "..."
}
```

Configuração inicial:

```env
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

O modelo poderá posteriormente ser alterado conforme qualidade, velocidade e recursos disponíveis.

---

# 12. Revisão contextual

A revisão deverá utilizar:

```text
TRANSCRIÇÃO BRUTA
+
CONTEXTO RELEVANTE
+
METADADOS
        ↓
      LLM
        ↓
TEXTO REVISADO
```

A IA deverá:

* corrigir pontuação;
* corrigir erros evidentes;
* melhorar legibilidade;
* interpretar contexto;
* preservar nomes;
* preservar números;
* preservar termos técnicos;
* preservar o significado.

Regra crítica:

> **REVISAR ≠ INVENTAR**

A IA não deverá adicionar fatos que não estejam presentes no áudio ou no contexto disponível.

---

# 13. Memória em camadas

Cada informação deverá ser preservada em diferentes níveis:

```text
RAW
 ↓
REVISED
 ↓
STRUCTURED
 ↓
SEMANTIC
 ↓
RELATIONAL
```

Exemplo:

```text
RAW
"fala com o joao sobre aquele sensor..."

REVISED
"Falar com João sobre aquele sensor."

STRUCTURED
intent = TASK
person = João
subject = sensor

SEMANTIC
embedding = [...]

RELATIONAL
TASK → João
TASK → Sensor
TASK → Projeto X
```

---

# 14. Banco de dados

PostgreSQL será a fonte oficial dos dados.

Entidades iniciais:

```text
users
messages
audio_files
transcriptions
interpretations
entities
entity_mentions
tasks
projects
topics
events
decisions
problems
ideas
daily_summaries
weekly_summaries
relationships
```

---

# 15. Estrutura de uma mensagem

Conceitualmente:

```json
{
  "id": "...",
  "timestamp": "...",
  "source": "whatsapp",
  "chat_id": "...",
  "audio_id": "...",

  "transcription": {
    "raw": "...",
    "language": "pt"
  },

  "interpretation": {
    "revised": "...",
    "summary": "...",
    "intent": "TASK",
    "importance": 4
  },

  "entities": [],
  "topics": [],
  "actions": [],
  "projects": []
}
```

---

# 16. Taxonomia inicial de intenções

Inicialmente:

```text
IDEA
TASK
REMINDER
DECISION
NOTE
EVENT
PROBLEM
REPORT
QUESTION
REFERENCE
MEETING
PROJECT_UPDATE
OTHER
```

A taxonomia deverá permanecer pequena inicialmente e evoluir conforme dados reais.

---

# 17. Entidades

O sistema deverá identificar entidades relevantes.

Exemplos:

```text
PERSON
COMPANY
PROJECT
PLACE
EQUIPMENT
PRODUCT
UNIT
TOPIC
DATE
DEADLINE
EVENT
PROBLEM
```

Exemplo:

```text
"João precisa verificar o sensor do silo 3 amanhã."

PERSON
→ João

EQUIPMENT
→ sensor

PLACE
→ silo 3

DATE
→ amanhã

TASK
→ verificar sensor
```

---

# 18. Contexto

A IA não deverá trabalhar apenas com o áudio atual.

Quando necessário, poderá recuperar:

```text
Áudio atual
+
Mensagens anteriores
+
Entidades relacionadas
+
Projetos relacionados
+
Memórias relevantes
```

Fluxo:

```text
Mensagem atual
      ↓
Retriever
      ↓
Memórias relevantes
      ↓
Context Window
      ↓
LLM
```

Nunca enviar a memória inteira indiscriminadamente para o modelo.

---

# 19. Memória vetorial

Utilizar inicialmente:

```text
PostgreSQL
+
pgvector
```

Cada memória relevante poderá possuir um embedding.

Isso permitirá consultas semânticas:

```text
"O que falei sobre sensores de silo?"
```

mesmo quando o texto original utilizar outras palavras.

---

# 20. API da Memória

A VPS deverá disponibilizar uma API própria.

Base:

```text
/api/v1/
```

Endpoints iniciais:

```text
GET  /api/v1/messages
GET  /api/v1/tasks
GET  /api/v1/projects
GET  /api/v1/topics
GET  /api/v1/entities/{entity}
GET  /api/v1/daily/{date}
GET  /api/v1/weekly/{week}

GET  /api/v1/memory/search
POST /api/v1/memory/query
GET  /api/v1/graph/{entity}
```

---

# 21. Integração com Hermes

O Hermes será consumidor da memória.

Arquitetura:

```text
                  HERMES
                    │
                    │ HTTPS/Tailscale
                    ▼
              MEMORY API
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
      PostgreSQL  pgvector   Graph
```

Exemplo:

```json
POST /api/v1/memory/query

{
  "query": "Quais foram os problemas relacionados aos sensores de silo nas últimas três semanas?"
}
```

Resposta:

```json
{
  "answer": "...",
  "sources": [
    "message_123",
    "message_456"
  ]
}
```

As respostas deverão preservar referências às memórias utilizadas.

---

# 22. Resumo diário

Ao final do expediente:

```text
18:00
 ↓
n8n Cron
 ↓
Buscar dados do dia
 ↓
Agrupar por assunto/projeto
 ↓
Recuperar contexto
 ↓
LLM
 ↓
Resumo diário
 ↓
Plano amanhã
 ↓
WhatsApp
```

O relatório deverá conter:

```text
RESUMO DO DIA

Principais acontecimentos

Projetos movimentados

Decisões

Problemas

Pendências

Ideias

Tarefas

Pontos de atenção

PLANO PARA AMANHÃ
```

---

# 23. Plano diário

O plano não deverá ser simplesmente uma cópia do resumo.

Deverá transformar:

```text
acontecimentos
+
pendências
+
decisões
+
projetos
+
prioridades
```

em:

```text
AÇÕES
```

Cada ação poderá possuir:

```text
description
priority
deadline
project
people
status
source
```

---

# 24. Inteligência semanal

Uma vez por semana:

```text
Segunda ─┐
Terça    │
Quarta   │
Quinta   │
Sexta    ├──► WEEKLY INTELLIGENCE
Sábado   │
Domingo ─┘
```

O sistema deverá analisar:

* acontecimentos;
* projetos;
* tarefas;
* problemas;
* decisões;
* ideias;
* pessoas;
* tópicos;
* prioridades;
* recorrências;
* gargalos;
* mudanças;
* padrões.

---

# 25. Grafo de conhecimento

As informações serão transformadas em relações.

Exemplo:

```text
                 João
                  │
             trabalha em
                  ▼
             Manutenção
                  │
               resolve
                  ▼
              Sensor 3
                  │
              pertence
                  ▼
                Silo 3
                  │
             relacionado
                  ▼
            Projeto Silos
```

Relações possíveis:

```text
MENTIONS
RELATES_TO
BELONGS_TO
DEPENDS_ON
WORKS_WITH
CREATES
UPDATES
BLOCKS
SOLVES
PART_OF
FOLLOWED_BY
```

---

# 26. Graph Analytics

Inicialmente utilizar:

```text
PostgreSQL
      ↓
NetworkX
      ↓
Graph Analytics
```

Métricas:

* entidades mais citadas;
* entidades centrais;
* assuntos mais conectados;
* projetos mais ativos;
* problemas recorrentes;
* relações novas;
* relações persistentes;
* tópicos emergentes;
* pessoas associadas a múltiplos projetos;
* problemas associados a múltiplos contextos.

Neo4j somente deverá ser considerado quando a complexidade justificar.

---

# 27. Relatório semanal

Estrutura:

```text
WEEKLY INTELLIGENCE REPORT

1. RESUMO EXECUTIVO

2. PRINCIPAIS ACONTECIMENTOS

3. PROJETOS

4. PROBLEMAS RECORRENTES

5. DECISÕES

6. IDEIAS

7. TAREFAS

8. PESSOAS E RELACIONAMENTOS

9. TÓPICOS DOMINANTES

10. ANÁLISE DO GRAFO

11. PADRÕES

12. RISCOS

13. OPORTUNIDADES

14. PLANO DA PRÓXIMA SEMANA
```

O relatório deve ser **denso e analítico**, e não apenas um resumo cronológico.

---

# 28. Plano semanal

Domingo à noite:

```text
MEMÓRIA DA SEMANA
        +
PROJETOS
        +
PENDÊNCIAS
        +
PADRÕES
        +
PRIORIDADES
        +
OBJETIVOS
        ↓
       LLM
        ↓
PLANO SEMANAL
```

Resultado:

```text
PRIORIDADES

FOCO PRINCIPAL

PROJETOS

PENDÊNCIAS

AÇÕES

IDEIAS

RISCOS

OPORTUNIDADES

SUGESTÃO DE DISTRIBUIÇÃO DA SEMANA
```

---

# 29. Roadmap de 6 meses

## MÊS 1 — MVP

### Objetivo

Construir:

```text
WhatsApp
 ↓
n8n
 ↓
Whisper
 ↓
AI Gateway
 ↓
texto revisado
 ↓
WhatsApp
```

### Entregáveis

* WhatsApp API;
* webhook;
* n8n;
* FastAPI;
* faster-whisper;
* Caddy;
* Tailscale;
* HTTPS;
* Gemini API;
* AI Gateway;
* logging;
* tratamento de erros.

### Critério de sucesso

Enviar dezenas de áudios reais durante uma semana com transcrição e revisão confiáveis.

---

# MÊS 2 — MEMÓRIA

### Objetivo

Transformar mensagens em dados.

Implementar:

* PostgreSQL;
* schema;
* transcrição bruta;
* transcrição revisada;
* contexto;
* intenção;
* entidades;
* tópicos;
* tarefas;
* projetos;
* decisões;
* problemas;
* AI Model Router.

Pipeline:

```text
Áudio
 ↓
Whisper
 ↓
AI Gateway
 ↓
Revisão
 ↓
Extração
 ↓
PostgreSQL
```

---

# MÊS 3 — INTELIGÊNCIA DIÁRIA

### Objetivo

Criar o primeiro ciclo de inteligência.

Implementar:

* resumo diário;
* tarefas;
* pendências;
* prioridades;
* plano para amanhã;
* notificações;
* histórico diário.

Resultado:

```text
DURANTE O DIA
→ captura

FINAL DO DIA
→ compreensão

NOITE
→ planejamento
```

---

# MÊS 4 — HERMES + RAG

### Objetivo

Transformar a memória em infraestrutura consultável.

Implementar:

* Memory API;
* autenticação;
* OpenAPI;
* pgvector;
* embeddings;
* busca semântica;
* retrieval;
* integração Hermes;
* respostas com fontes.

Resultado:

```text
Hermes
 ↓
Memory API
 ↓
RAG
 ↓
Memória pessoal
```

---

# MÊS 5 — GRAFO + INTELIGÊNCIA SEMANAL

### Objetivo

Adicionar visão longitudinal.

Implementar:

* entidades;
* relações;
* grafo;
* NetworkX;
* métricas;
* análise de recorrência;
* análise de projetos;
* relatório semanal;
* detecção de padrões.

Resultado:

```text
MEMÓRIA
 ↓
GRAPH
 ↓
PATTERNS
 ↓
WEEKLY INTELLIGENCE
```

---

# MÊS 6 — HERMES VOICE MEMORY v1.0

### Objetivo

Consolidar todo o sistema.

Pipeline final:

```text
                         WHATSAPP
                            │
                            ▼
                         n8n
                            │
                            ▼
                       WHISPER
                            │
                            ▼
                      AI GATEWAY
                            │
                ┌───────────┼───────────┐
                ▼           ▼           ▼
             Gemini     OpenRouter    Local
                │           │           │
                └───────────┼───────────┘
                            ▼
                       MEMÓRIA
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
        PostgreSQL       pgvector        Graph
             │              │              │
             └──────────────┼──────────────┘
                            ▼
                       INTELLIGENCE
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
           DIÁRIO         SEMANAL        HERMES
             │              │              │
             ▼              ▼              ▼
         WhatsApp        WhatsApp         API
```

---

# 30. Versões do produto

## v0.1 — Voice Transcriber

```text
Áudio
→ Whisper
→ texto
```

## v0.2 — Voice Editor

```text
Áudio
→ Whisper
→ LLM
→ texto revisado
```

## v0.3 — Voice Memory

```text
Áudio
→ interpretação
→ PostgreSQL
```

## v0.4 — Daily Intelligence

```text
Memória
→ resumo
→ plano diário
```

## v0.5 — Hermes Memory API

```text
Memória
→ API
→ Hermes
```

## v0.6 — Graph Intelligence

```text
Memória
→ grafo
→ padrões
→ análise semanal
```

## v1.0 — Hermes Voice Memory

```text
VOICE
→ MEMORY
→ GRAPH
→ INTELLIGENCE
→ ACTION
```

---

# 31. Princípios de arquitetura

### 1. WhatsApp é interface

Não é o banco de dados.

### 2. PostgreSQL é a fonte da verdade

LLM não é memória.

### 3. RAW nunca é perdido

Sempre preservar a transcrição original.

### 4. Revisão não pode inventar fatos

A IA deve preservar o conteúdo semântico.

### 5. AI Gateway desacopla o sistema dos modelos

Nenhum componente deve depender diretamente de Gemini, OpenRouter, Claude, GPT etc.

### 6. Model Router controla custo e qualidade

Modelos pequenos para tarefas simples.

Modelos maiores para raciocínio complexo.

### 7. Memória deve ser recuperada seletivamente

Nunca enviar toda a base para a LLM.

### 8. Grafo é consequência da memória estruturada

Não construir o grafo antes de existir uma boa estrutura de dados.

### 9. Começar simples

Evitar complexidade prematura.

Não começar com:

* Kubernetes;
* microsserviços excessivos;
* Neo4j;
* múltiplos agentes;
* dezenas de modelos;
* infraestrutura distribuída.

---

# 32. Segurança

Como o sistema armazenará informações pessoais e profissionais, segurança deverá ser considerada desde o início.

Requisitos:

* HTTPS;
* API Keys/JWT;
* Tailscale;
* firewall;
* secrets via `.env`;
* backups;
* logs sem conteúdo sensível;
* controle de acesso;
* rate limiting;
* validação de payload;
* isolamento dos serviços;
* política de retenção de áudios.

Nunca armazenar chaves de API no n8n ou código-fonte.

---

# 33. Observabilidade

O sistema deverá registrar métricas técnicas.

Exemplos:

```text
audio_duration
transcription_time
llm_latency
llm_model
tokens_input
tokens_output
processing_time
error_rate
daily_messages
weekly_messages
```

Não registrar automaticamente o conteúdo integral das mensagens nos logs.

---

# 34. Controle de custos

O projeto deverá possuir métricas de consumo por etapa.

```text
WHISPER
↓
CPU / RAM / tempo

LLM
↓
tokens
↓
custo

EMBEDDINGS
↓
tokens
↓
custo
```

O AI Gateway deverá permitir definir limites.

Exemplo:

```env
MAX_DAILY_AI_COST=
MAX_TOKENS_PER_REQUEST=
MAX_CONTEXT_MESSAGES=
```

---

# 35. Backup

A memória deverá ser considerada um ativo.

Estratégia:

```text
PostgreSQL
   ↓
backup diário
   ↓
backup externo
```

Idealmente:

* backup diário;
* retenção de versões;
* backup semanal;
* teste periódico de restauração.

---

# 36. Critério de sucesso do projeto

O projeto será considerado bem-sucedido quando o usuário puder:

### Durante o dia

```text
🎙️ falar naturalmente
        ↓
📝 receber texto revisado
        ↓
continuar trabalhando
```

### Ao final do dia

```text
📊 receber:
- resumo
- decisões
- pendências
- tarefas
- plano de amanhã
```

### Ao final da semana

```text
🧠 receber:
- análise profunda
- padrões
- problemas recorrentes
- evolução de projetos
- relações
- riscos
- oportunidades
- plano da próxima semana
```

### A qualquer momento

O Hermes poderá perguntar:

```text
"O que eu falei sobre esse projeto?"

"Quando apareceu esse problema pela primeira vez?"

"Quais pendências estão abertas?"

"Quais assuntos estão consumindo mais atenção?"

"Quais projetos ficaram parados?"

"Quais ideias eu mencionei várias vezes?"

"Quem está relacionado a esse projeto?"

"O que eu deveria priorizar?"
```

---

# 37. Visão de longo prazo

O projeto não deve terminar como um sistema de transcrição.

A evolução natural é:

```text
                  VOICE
                    │
                    ▼
              CAPTURE LAYER
                    │
                    ▼
             UNDERSTANDING
                    │
                    ▼
               MEMORY
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
        VECTOR     GRAPH      SQL
          │         │         │
          └─────────┼─────────┘
                    ▼
              INTELLIGENCE
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
        Hermes    Reports    Agents
                    │
                    ▼
                  ACTION
```

O objetivo final é construir uma infraestrutura pessoal na qual:

> **Tudo aquilo que for importante o suficiente para ser falado possa ser capturado, contextualizado, lembrado, relacionado e posteriormente transformado em decisão ou ação.**

O WhatsApp é apenas a porta de entrada.

A verdadeira plataforma é a **memória inteligente**.

---

# 38. Norte arquitetural

```text
VOICE
  ↓
TRANSCRIPTION
  ↓
CONTEXT
  ↓
LLM
  ↓
STRUCTURED MEMORY
  ↓
VECTOR MEMORY
  ↓
GRAPH
  ↓
ANALYTICS
  ↓
INTELLIGENCE
  ↓
PLANNING
  ↓
ACTION
  ↓
HERMES
```

## Hermes Voice Memory

**Uma memória pessoal construída a partir da sua própria voz.**
