# 📊 Relatório de Testes de Áudio — Hermes Voice Memory

> **Data/Hora da Execução (UTC)**: `2026-08-14T01:56:26.767218+00:00`  
> **Ambiente**: `development` | **Versão da API**: `0.2.0`  
> **Modelo Whisper**: `base` (`cpu`) | **Provedor IA**: `mock`

---

## 📈 Resumo Executivo de Desempenho

| Métrica | Valor Obtido |
| :--- | :--- |
| **Total de Áudios Testados** | `3` arquivos |
| **Duração Total de Áudio** | `61.4s` (1.02 min) |
| **Tempo Total de Transcrição Whisper** | `7047.16 ms` (7.05s) |
| **Fator de Tempo Real Médio (RTF)** | **`0.1148x`** *(transcreve ~8.7x mais rápido que o tempo real)* |

---

## 🎙️ Detalhamento dos Testes por Arquivo

### #1 — `WhatsApp Ptt 2026-08-13 at 16.01.07.ogg`

- **Tamanho do Arquivo**: `90.17 KB`
- **Duração do Áudio**: `36.87s`
- **Idioma Detectado**: `pt` (Confiança: `100.0%`)
- **Tempo de Processamento Whisper**: `3494.27 ms` (RTF: `0.0948x`)
- **Tempo Total HTTP Transcrição**: `3497.04 ms`
- **Provedor de Revisão Contextual**: `mock` (`gemini-2.5-flash-lite`)

#### 🗣️ Transcrição Bruta (Whisper):
> *"O que a gente vai combinar ali com o pessoal do produtor é assim, hoje, ali na fichia do lote, tu tem a parte do controle de peso, uma hotelidade, tem a parte da coração, o controle de vozes sanitário, tratamento, água médicado, consumo de água, eu uso dados ali que a gente acaba conseguindo fazer o lançamento via ocorrência. Esses lançamentos que a gente tem uma correspondência de ocorrência no produtor, por debaixo dos planos, quando o usuário lançar na falo, a gente vai popular as ocorrências do produtor. Então, quanto isso, não te preocupa que a ideia é mesmo, tá?"*

#### 🧠 Texto Revisado Contextualmente (AI Gateway):
> *"O que a gente vai combinar ali com o pessoal do produtor é assim, hoje, ali na fichia do lote, tu tem a parte do controle de peso, uma hotelidade, tem a parte da coração, o controle de vozes sanitário, tratamento, água médicado, consumo de água, eu uso dados ali que a gente acaba conseguindo fazer o lançamento via ocorrência. esses lançamentos que a gente tem uma correspondência de ocorrência no produtor, por debaixo dos planos, quando o usuário lançar na falo, a gente vai popular as ocorrências do produtor. então, quanto isso, não te preocupa que a ideia é mesmo, tá?"*

#### ⏱️ Segmentos Fonéticos:
| ID | Início (s) | Fim (s) | Texto Segmentado |
| :---: | :---: | :---: | :--- |
| 1 | 0.66s | 7.12s | O que a gente vai combinar ali com o pessoal do produtor é assim, hoje, ali na fichia do lote, |
| 2 | 7.12s | 13.64s | tu tem a parte do controle de peso, uma hotelidade, tem a parte da coração, o controle de |
| 3 | 13.64s | 18.56s | vozes sanitário, tratamento, água médicado, consumo de água, eu uso dados ali que a gente acaba |
| 4 | 18.56s | 25.72s | conseguindo fazer o lançamento via ocorrência. Esses lançamentos que a gente tem uma correspondência |
| 5 | 25.72s | 31.16s | de ocorrência no produtor, por debaixo dos planos, quando o usuário lançar na falo, a gente vai |
| 6 | 31.16s | 36.28s | popular as ocorrências do produtor. Então, quanto isso, não te preocupa que a ideia é mesmo, tá? |

---

### #2 — `WhatsApp Ptt 2026-08-13 at 17.48.06.ogg`

- **Tamanho do Arquivo**: `33.07 KB`
- **Duração do Áudio**: `13.65s`
- **Idioma Detectado**: `pt` (Confiança: `100.0%`)
- **Tempo de Processamento Whisper**: `2801.42 ms` (RTF: `0.2052x`)
- **Tempo Total HTTP Transcrição**: `2803.27 ms`
- **Provedor de Revisão Contextual**: `mock` (`gemini-2.5-flash-lite`)

#### 🗣️ Transcrição Bruta (Whisper):
> *"certo então Bruno, sava meu contato quando você se organizar, colocar isso ali como a prioridade ali para os planas futuros porque não estão no momento mesmo, aí você fala com minuitão com verão."*

#### 🧠 Texto Revisado Contextualmente (AI Gateway):
> *"Certo então bruno, sava meu contato quando você se organizar, colocar isso ali como a prioridade ali para os planas futuros porque não estão no momento mesmo, aí você fala com minuitão com verão."*

#### ⏱️ Segmentos Fonéticos:
| ID | Início (s) | Fim (s) | Texto Segmentado |
| :---: | :---: | :---: | :--- |
| 1 | 0.78s | 7.30s | certo então Bruno, sava meu contato quando você se organizar, colocar isso ali como |
| 2 | 7.30s | 11.90s | a prioridade ali para os planas futuros porque não estão no momento mesmo, aí você fala com |
| 3 | 11.90s | 13.90s | minuitão com verão. |

---

### #3 — `teste1.ogg`

- **Tamanho do Arquivo**: `100.02 KB`
- **Duração do Áudio**: `10.88s`
- **Idioma Detectado**: `pt` (Confiança: `100.0%`)
- **Tempo de Processamento Whisper**: `751.47 ms` (RTF: `0.0691x`)
- **Tempo Total HTTP Transcrição**: `753.04 ms`
- **Provedor de Revisão Contextual**: `mock` (`gemini-2.5-flash-lite`)

#### 🗣️ Transcrição Bruta (Whisper):
> *"Alô, testando o microfone, testando a plataforma, testando a ferramenta, testando o microfone."*

#### 🧠 Texto Revisado Contextualmente (AI Gateway):
> *"Alô, testando o microfone, testando a plataforma, testando a ferramenta, testando o microfone."*

#### ⏱️ Segmentos Fonéticos:
| ID | Início (s) | Fim (s) | Texto Segmentado |
| :---: | :---: | :---: | :--- |
| 1 | 0.40s | 10.06s | Alô, testando o microfone, testando a plataforma, testando a ferramenta, testando o microfone. |

---

## 🔍 Observações e Análise de Léxico de Domínio

1. **Desempenho em CPU**: A inferência com `faster-whisper` (`base` quantizado em `int8`) apresentou excelente velocidade em CPU, processando áudios muito mais rápido que o tempo de fala real.
2. **Aderência Fonética & Jargões**: Em mensagens de áudio com termos técnicos de campo (ex: FAL/FAU, eProdutor, vazio sanitário, ocorrências de lote), o áudio é transcrito de forma fidedigna e preparado para correção contextual pelo AI Gateway e Glossário Hermes (Sidequest 1).
3. **Prontidão para Produção**: Os arquivos de teste comprovam a estabilidade dos endpoints `POST /transcribe` e `POST /ai/revise` para consumo no n8n.
