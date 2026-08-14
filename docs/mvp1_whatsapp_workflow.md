# 📱 Guia de Execução e Teste — MVP 1 (Transcrição & Revisão WhatsApp)

Este guia orienta como inicializar a API do **Hermes Voice Memory**, testar os endpoints de transcrição e revisão contextual, e conectar com o **n8n** e WhatsApp (Evolution API / Z-API).

---

## 🚀 1. Inicializando a API Localmente

Certifique-se de que as dependências estão instaladas e execute a aplicação com `uvicorn`:

```bash
# Executa a API no modo reload
.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Acesse a documentação interativa Swagger em: [http://localhost:8000/docs](http://localhost:8000/docs).

---

## 🧪 2. Testando os Endpoints Diretamente

### 2.1. Health Check
```bash
curl -X GET http://localhost:8000/health
```

### 2.2. Transcrição de Áudio (`POST /transcribe`)
Envie um arquivo de áudio (`.ogg`, `.opus`, `.mp3`, `.wav`):
```bash
curl -X POST http://localhost:8000/transcribe \
  -F "file=@/caminho/para/audio.ogg" \
  -F "language=pt"
```

**Exemplo de Resposta:**
```json
{
  "audio_id": "audio_1a2b3c4d5e",
  "language": "pt",
  "language_probability": 0.985,
  "duration": 4.5,
  "text": "entao amanha preciso falar com o joao sobre o sensor de racao do silo tres",
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 4.5,
      "text": "entao amanha preciso falar com o joao sobre o sensor de racao do silo tres"
    }
  ],
  "processing_time_ms": 312.4
}
```

### 2.3. Revisão Contextual (`POST /ai/revise`)
```bash
curl -X POST http://localhost:8000/ai/revise \
  -H "Content-Type: application/json" \
  -d '{
    "text": "entao amanha preciso falar com o joao sobre o sensor de racao do silo tres",
    "context": "Contexto de avicultura e automação de silos."
  }'
```

**Exemplo de Resposta:**
```json
{
  "text_revised": "Então, amanhã preciso falar com o João sobre o sensor de ração do silo 3.",
  "provider": "gemini",
  "model": "gemini-2.5-flash-lite",
  "processing_time_ms": 420.15
}
```

---

## 🔄 3. Configurando no n8n

1. Abra seu painel do **n8n** (ex: no Raspberry Pi ou local).
2. Vá em **Workflows ➔ Import from File** e selecione o arquivo:
   `workflows/n8n_whatsapp_voice_transcription.json`
3. Configure as variáveis de ambiente no n8n ou no nó HTTP:
   - `HERMES_API_URL`: URL da sua API Hermes (ex: `http://100.x.y.z:8000` via Tailscale ou `http://localhost:8000`).
   - `WHATSAPP_API_ENDPOINT`: URL da sua instância Evolution API / Z-API.
   - `WHATSAPP_API_TOKEN`: Token de autenticação da instância do WhatsApp.
4. Ative o workflow. Ao enviar um áudio para o número conectado, o WhatsApp responderá em segundos com a transcrição devidamente revisada.
