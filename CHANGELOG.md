# 📜 Changelog — Hermes Voice Memory & WhisperZap

Todas as mudanças notáveis, refatorações arquiteturais, motores de IA e otimizações de performance deste projeto são documentadas neste arquivo.

---

## [v2.6.0] — 2026-08-20 — Release: Long Audio Resilience & Executive Post-Processing

### 🎙️ 1. Resiliência de Áudios Longos & Fallback Gracioso (Zero 502)
- **Fallback Gracioso no AI Gateway (`POST /ai/revise`)**: Qualquer falha, oscilação ou timeout na API externa de LLM agora retorna status `200 OK` com o texto bruto transcrito pelo Whisper e `is_fallback = True`, garantindo que o WhatsApp **nunca** fique sem resposta.
- **Detecção de Áudio em Documentos no n8n**: O nó `É Mensagem de Áudio?` foi aprimorado para reconhecer áudios encaminhados ou gravados por aplicativos externos transmitidos como `documentMessage` com mimetype de áudio.
- **Tolerância a Falhas nos Workflows**: Configuração de `continueOnFail: true` e timeout estendido de 300s nos nós de transcrição e IA do n8n.

### 📋 2. Pós-Processamento Inteligente de Conversas Extensas
- **Destaques Executivos (*Key Points* e Ações)**: Mensagens extensas (> 350 caracteres ou > 45s) recebem automaticamente, além da transcrição revisada limpa, uma seção de **Destaques do Áudio** e **Ações Identificadas** para leitura dinâmica no WhatsApp.
- **Prompt Especializado**: Inclusão de regras de estruturação em tópicos preservando termos técnicos zootécnicos e nomes operacionais.

### ⚙️ 3. Otimização de Infraestrutura e Schemas
- **Aumento de Timeout HTTP**: Cliente assíncrono do Gemini configurado com timeout de 60s.
- **Normalização de Decisões no Extractor Semântico**: Conversão automática de objetos heterogêneos (`dict`) retornados pela LLM em `list[str]`, eliminando erros de validação Pydantic.
- **Ajuste de Heap Node.js na Evolution API**: Memória alocada ajustada para 380MB no ambiente Alpine (`peixe`).

### 📜 4. Integração Calíope ➔ Clio: Cadastro Instantâneo de Contatos Não Reconhecidos
- **Botão de Cadastro Direto**: Mensagens recebidas de números ou remetentes não cadastrados no banco de dados de Clio agora exibem a badge `⚠️ Não Cadastrado` e os botões `📜 + Cadastrar em Clio` no cabeçalho e rodapé do card.
- **Pré-Preenchimento Automático**: Ao clicar no botão, o modal de contato de Clio é aberto com o número de WhatsApp formatado, o nome do remetente (ou *pushName* do WhatsApp) e nota contextual da mensagem preenchidos automaticamente.
- **Sincronização Reativa em Tempo Real**: Ao salvar o contato, a memória e o feed de Calíope são atualizados imediatamente na interface sem necessidade de recarregar a página.

### 🏛️ 5. Euterpe: Central de Operações de Contatos & Miniterminal de Execução ao Vivo
- **Ingestão de vCards (.vcf / .vcard)**: Suporte a upload direto de arquivos vCard locais e importação em lote dos arquivos contidos em `data/vcards/` na VPS com sanitização profunda e normalização telefônica.
- **Deduplicação & Mesclagem Canônica**: Expurgo automático de grupos e números fora do padrão, consolidação do Proprietário (*Owner*) e unificação de cartões duplicados com transferência de mensagens e nós no grafo.
- **Sincronização de Avatares (Evolution API)**: Varredura de fotos de perfil e nomes públicos do WhatsApp para enriquecer a base de contatos.
- **Pipeline Mestre Unificado**: Execução encadeada de 4 etapas (vCard + Deduplicação + Avatares + Grafo MUSA) com status ao vivo.
- **Miniterminal Retrô ao Vivo**: Console integrado na aba Euterpe com feedback em tempo real das etapas de execução, logs com timestamps, botão de cópia e limpeza.




---

## [v2.5.0] — 2026-08-19 / 2026-08-20 — Release: Mnemosine Auth, Calíope Filters & Ultra-Minimalist Latency

### 🔒 1. Autenticação & Proteção do Dashboard
- **Sessão Persistente (30 dias)**: Token HMAC e cookie `HttpOnly` com persistência no `localStorage`, imune a recarregamentos de página (F5).
- **Interface Mnemosine "Never Forget"**: Modal temático com a imagem clássica de Mnemosine, tipografia *Cinzel* e botão de encerramento rápido de sessão.
- **Configuração Simples**: Senha gerenciável via `.env` (`DASHBOARD_PASSWORD=blurbang`).

### 🎙️ 2. Filtros de Mídia e Prosódia em Calíope
- **Filtro de Origem**: Segmentação instantânea entre notas de voz (`🎙️ Áudios`) e mensagens de texto diretas (`💬 Textos`).
- **Filtro de Prosódia Acústica**: Seletores de tom de voz (⚡ *Acelerado & Tenso*, 🚀 *Enérgico*, 🌿 *Calmo*, 🤔 *Hesitante*, 💬 *Neutro*).
- **Badges de Identificação**: Cards de mensagens enriquecidos com badges de mídia e métricas de fala ativa.

### ⚡ 3. Resposta Ultra-Minimalista & Latência Otimizada
- **Remoção de Personas de Bots**: WhatsApp devolve exclusivamente o texto revisado limpo e pontuado, eliminando títulos lúdicos (*James/Calíope*).
- **Greedy Decoding no Gemini (`temperature=0.0`)**: Maior velocidade de resposta, zero alucinações e zero custo adicional de tokens.
- **Comunicação Direta Docker**: Tráfego de áudio otimizado na rede interna do homelab (`hermes_homelab_network`).

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
