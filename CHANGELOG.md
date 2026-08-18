# 📜 Changelog — Hermes Voice Memory & WhisperZap

Todas as mudanças notáveis, refatorações arquiteturais, motores de IA e otimizações de performance deste projeto são documentadas neste arquivo.

---

## [v2.4.0] — 2026-08-17 / 2026-08-18 — Release: Neural Intelligence, GraphRAG & Token Economy

### 🎙️ 1. Speech-to-Text & Whisper Priming
- **Dynamic Prompt Priming**: Condicionamento do modelo `faster-whisper` com termos do Dicionário Léxico (`C.Vale`, `eProdutor`, `Mtech`, `Agrocenter`, `Silo`, `Balança`, etc.) e nomes dos contatos frequentes e favoritos do interlocutor.
- **Silero VAD Tuning**: Calibração de corte de silêncio e preenchimento de fala (`min_silence_duration_ms=400`, `speech_pad_ms=200`) para imunidade a ruídos de aviários e veículos.
- **Endpoints de Transcrição**: Suporte a parâmetros `speaker` e `prompt` em `POST /transcribe` e `POST /transcribe/base64`.

### 🕸️ 2. GraphRAG Híbrido (pgvector + NetworkX 2-Hop + spaCy)
- **Extração de Entidades da Consulta**: Análise semântica da dúvida do usuário com spaCy para identificação de pessoas, sistemas, empresas e equipamentos.
- **Expansão Topológica de 2 Saltos**: Travessia BFS de 2 graus no NetworkX recuperando a cadeia relacional completa de entidades e atributos de contato.
- **Fusão e Re-ranqueamento**: Mensagens que citam nós presentes no subgrafo de 2 saltos recebem boost automático de similaridade semântica.
- **Endpoint de Inspeção**: Criação de `POST /api/v1/memory/graph/hybrid-search`.

### ✂️ 3. Compressão Extrativa & Economia de Tokens (Pre-LLM)
- **Extractive Context Compressor (spaCy TextRank)**: Ranqueamento e seleção das sentenças de maior densidade informacional para áudios longos, reduzindo o consumo de tokens em 30% a 50% sem perda de fatos.
- **Cache Semântico Local**: Armazenamento em memória de perguntas e respostas frequentes com matching fuzzy ($\ge 94\%$) e TTL de 15 minutos (respostas em $< 5\text{ms}$ e $0$ tokens).
- **Bypass Fático/Social**: Detecção de mensagens conversacionais e fáticas com 0 tokens e 0 poluição de banco.
- **Endpoint de Métricas**: `GET /api/v1/memory/token-savings` para acompanhamento de tokens economizados em tempo real.

### 🛡️ 4. Guardrail Universal de Ortografia & Bloqueio Estrito de Nós
- **Validação Fonotática Universal**: Detecção de dígrafos ilegais no português (`hl`, `hn`, `hc`), repetições consonantais inválidas (`bb`, `ff`, `xx`) e sequências sem vogais / keyboard mash.
- **Auto-correção Fuzzy**: Correção inteligente de typos arbitrários (`senosr` ➔ `Sensor`, `fihlos` ➔ `Filho`, `realtorio` ➔ `Relatório`).
- **Bloqueio Estrito no Grafo**: Qualquer termo que contenha erro ortográfico não corrigível é sumariamente impedido de criar nós no NetworkX.
- **Poda na Zeladora**: A Zeladora remove nós legados com problemas ortográficos do grafo.

### ⛏️ 5. Dicionário Léxico & Gerador Fonético com spaCy
- **Mineração Autônoma de Jargões**: Extração de sintagmas técnicos e siglas inéditas a partir das conversas reais no PostgreSQL (`C-Value` / `Termhood`).
- **Gerador Fonético de Variações**: Geração automática de alucinações e variações fonéticas prováveis do Whisper (`Mtech` ➔ `emitech`, `m-tech`, `mtequi`; `CFOP` ➔ `c f o p`, `c-f-o-p`).
- **Novos Endpoints**: `GET /api/v1/dictionary/suggestions` e `POST /api/v1/dictionary/generate-phonetics`.

### 🧠 6. Otimizador Inteligente de Tarefas (Feedback Loop)
- **Classificador de Sentimento e Ruído com spaCy**: Análise de cancelamento de tarefas ignoradas.
- **Agente LLM Learner**: Cronjob diário (03:15 AM) que sintetiza regras anti-ruído no arquivo `data/task_pruning_rules.json`.
- **Filtro Pré-Gravação**: Bloqueio de falsos-positivos antes de persistir no banco de dados.

### 🇧🇷 7. Alinhamento de Fuso Horário de Brasília (America/Sao_Paulo)
- **Utilitário Centralizado (`timezone_utils.py`)**: Conversão precisa de timestamps UTC do PostgreSQL para o Horário de Brasília (UTC-3).
- **Injeção de Cabeçalho Temporal**: O prompt do Agente Hermes recebe a data/hora oficial de Brasília explícita, eliminando alucinações de dias futuros/passados no RAG.

### 🧪 8. Qualidade & Testes
- **52 testes automatizados** cobrindo todas as camadas do sistema com 100% de sucesso.
