# 🎙️ Tutorial Prático: Testando a Transcrição e Revisão de Áudio (Hermes MVP 1)

Este guia passo a passo foi preparado para você testar a transcrição e a revisão contextual do **Hermes Voice Memory**, enviando um áudio do seu WhatsApp para si mesmo.

---

## 📋 Pré-requisitos Rápidos

1. **Terminal aberto** na pasta do projeto `/home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant`.
2. **Ambiente Virtual** com as dependências instaladas.
3. Chave de API da IA configurada no arquivo `.env` (ex: `GEMINI_API_KEY=sua_chave` ou usando `AI_PROVIDER=mock` para teste offline).

---

## 🚀 Passo 1: Inicializar a API Hermes

No seu terminal, execute:

```bash
.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

> **Verificação**: Abra no navegador [http://localhost:8000/docs](http://localhost:8000/docs) para confirmar que a documentação interativa Swagger está online.

---

## 🧪 Opção A: Teste Rápido com Arquivo de Áudio Local (cURL ou Swagger)

Se você já tem ou acabou de gravar um áudio no celular/PC:

### 1. Salve o arquivo de áudio
Grave uma mensagem de teste (ex: `teste_voz.ogg`, `teste_voz.m4a`, `teste_voz.mp3` ou `.wav`).

**Sugestão de fala para o teste:**
> *"Olá Hermes, amanhã às oito e meia da manhã preciso verificar o sensor de ração do silo 3 e alinhar com o João as pendências do homelab."*

### 2. Envie para o endpoint de Transcrição (`POST /transcribe`):

```bash
curl -X POST "http://localhost:8000/transcribe?language=pt" \
  -F "file=@teste_voz.ogg"
```

**Exemplo de Retorno (Whisper):**
```json
{
  "audio_id": "audio_a1b2c3d4",
  "language": "pt",
  "language_probability": 0.99,
  "duration": 5.2,
  "text": "ola hermes amanha as oito e meia da manha preciso verificar o sensor de racao do silo tres e alinhar com o joao as pendencias do homelab",
  "processing_time_ms": 380.5
}
```

### 3. Envie para a Revisão Contextual (`POST /ai/revise`):

```bash
curl -X POST "http://localhost:8000/ai/revise" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "ola hermes amanha as oito e meia da manha preciso verificar o sensor de racao do silo tres e alinhar com o joao as pendencias do homelab",
    "context": "Notas e tarefas do usuário Bruno no homelab e avicultura."
  }'
```

**Exemplo de Retorno (AI Gateway):**
```json
{
  "text_revised": "Olá Hermes, amanhã às 08:30 preciso verificar o sensor de ração do silo 3 e alinhar com o João as pendências do homelab.",
  "provider": "gemini",
  "model": "gemini-2.5-flash-lite",
  "processing_time_ms": 412.0
}
```

---

## 📲 Opção B: Teste Automatizado via WhatsApp (n8n + Evolution API / Z-API)

Para enviar um áudio para o seu próprio número de WhatsApp e receber a transcrição limpa de volta:

```text
📱 Seu WhatsApp (Envia Áudio)
       │
       ▼
🌐 WhatsApp Gateway (Evolution API / Z-API)
       │
       ▼
⚙️ n8n Webhook (Recebe evento de áudio)
       │
       ├─► 🎙️ Hermes API (POST /transcribe)
       │
       ├─► 🧠 AI Gateway (POST /ai/revise)
       │
       ▼
💬 Seu WhatsApp (Recebe apenas o texto limpo e pontuado)
```

### Passo a passo no n8n:
1. Acesse o **n8n** (local ou no Raspberry Pi).
2. Clique em **Import from File** e selecione o arquivo:
   [`workflows/n8n_whatsapp_voice_transcription.json`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/workflows/n8n_whatsapp_voice_transcription.json)
3. No nó **Speech-to-Text (POST /transcribe)**, certifique-se de que a URL aponte para a máquina onde a API está rodando:
   - Se for na mesma máquina: `http://localhost:8000/transcribe`
   - Se o n8n estiver no Raspberry Pi e a API no PC/VPS: utilize o IP do **Tailscale** (ex: `http://100.x.y.z:8000/transcribe`).
4. Ative o workflow no n8n (**Active = ON**).
5. Abra seu WhatsApp, vá na sua própria conversa ("Você") ou envie para o número do bot, grave um áudio e envie.
6. Em instantes, você receberá a mensagem de texto com a transcrição perfeita e revisada!

---

## 🛠️ Dicas e Resolução de Problemas

| Situação | Causa Provável | Solução |
| :--- | :--- | :--- |
| **Erro 502 no `/ai/revise`** | `GEMINI_API_KEY` ausente ou inválida no `.env` | Adicione sua chave no `.env` ou configure temporariamente `AI_PROVIDER=mock`. |
| **Áudio em formato desconhecido** | O WhatsApp envia áudio em `.ogg` (codec opus) | O `faster-whisper` suporta nativamente `.ogg`, `.opus`, `.m4a`, `.mp3` e `.wav`. |
| **n8n não alcança a API** | Bloqueio de porta ou rede diferente | Certifique-se de usar `0.0.0.0` no uvicorn e a rede privada **Tailscale** caso estejam em dispositivos diferentes. |
