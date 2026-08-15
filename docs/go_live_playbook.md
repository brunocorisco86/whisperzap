# 🚀 Playbook de Go-Live — Como Começar a Usar o Hermes Voice Memory

Este guia prático foi criado para você começar a usar o **Hermes Voice Memory** imediatamente, validando cada etapa com facilidade.

---

## 🧭 Visão Geral em 3 Passos

```text
Passo 1: Teste Imediato no seu PC (Swagger UI Interativo)
   │
   ▼
Passo 2: Conexão com WhatsApp & n8n (Homelab / Raspberry Pi)
   │
   ▼
Passo 3: Deploy Final na VPS Alpine Linux (Produção 24/7 com Tailscale)
```

---

## ⚡ PASSO 1: Teste Imediato no seu PC (Agora Mesmo)

Você pode ligar a API localmente e testar visualmente pelo navegador em menos de 1 minuto.

### 1.1. Inicie o servidor da API
No terminal do seu computador, execute:
```bash
source .venv/bin/activate
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 1.2. Abra a interface interativa no navegador
Acesse: 👉 **`http://localhost:8000/docs`**

Aqui você verá todos os endpoints prontos para testar com 1 clique ("Try it out"):
- **`POST /transcribe`**: Envie qualquer arquivo de áudio (`.ogg`, `.mp3`, `.wav`) e veja a transcrição instantânea do Whisper.
- **`POST /ai/revise`**: Envie um texto falado e veja a pontuação contextual limpa.
- **`POST /api/v1/memory/messages`**: Envie uma mensagem como se viesse do WhatsApp (o sistema extrai intenções, tarefas e grava no Grafo NetworkX).
- **`POST /api/v1/memory/query`**: Faça uma pergunta em linguagem natural para o Agente Hermes (ex: *"O que temos de pendência sobre silos?"*).
- **`POST /api/v1/memory/daily/generate`**: Veja o Resumo Diário das 18:00 formatado para o WhatsApp.
- **`POST /api/v1/memory/weekly/generate`**: Veja o Relatório Semanal e Plano de Domingo formatados.

---

## 💬 PASSO 2: Conectando com WhatsApp & n8n

O WhatsApp é a interface de comunicação do sistema. O n8n recebe os áudios e despacha os textos.

### 2.1. Conectando a Evolution API / Z-API
1. Tenha uma instância da Evolution API conectada ao seu WhatsApp (pode rodar no Docker local ou no Raspberry Pi).
2. Aponte o Webhook de mensagens recebidas da Evolution API para o nó do n8n:
   - `http://<ip-do-n8n>:5678/webhook/whatsapp-voice-received`

### 2.2. Importando os Workflows no n8n
Na pasta [`workflows/`](file:///home/brunoconter/Documentos/4_HOMELAB/9_Voice_Assistant/workflows), importe os 4 fluxos no seu n8n:

| Workflow | Arquivo | Função |
| :--- | :--- | :--- |
| **1. Transcrição de Voz** | `n8n_whatsapp_voice_transcription.json` | Você manda um áudio no WhatsApp ➔ Recebe de volta o texto limpo e pontuado. |
| **2. Resumo Diário** | `n8n_daily_summary_cron.json` | Dispara automaticamente às 18:00 (Seg-Sex) com o resumo do dia e plano para amanhã. |
| **3. Relatório Semanal** | `n8n_weekly_plan_cron.json` | Dispara no Domingo às 20:00 com métricas da semana e plano estratégico. |
| **4. Q&A Hermes** | `n8n_hermes_qa_whatsapp.json` | Você manda `? Pergunta` ou `/hermes Pergunta` no WhatsApp ➔ O Hermes responde citando fontes. |

---

## 🌐 PASSO 3: Deploy na VPS Alpine Linux (Produção 24/7)

Quando quiser colocar em execução contínua na sua VPS em nuvem com túnel privado Tailscale para o Raspberry Pi:

### 3.1. Conecte na sua VPS via SSH
```bash
ssh root@<ip-da-vps>
```

### 3.2. Clone o repositório e configure o `.env`
```bash
git clone https://github.com/brunocorisco86/whisperzap.git /opt/whisperzap
cd /opt/whisperzap
cp .env.example .env
nano .env # Insira sua GEMINI_API_KEY e senhas desejadas
```

### 3.3. Execute o script de deploy automatizado
```bash
chmod +x scripts/*.sh
./scripts/deploy_vps_alpine.sh
```
O script cuidará de tudo: instala Docker, compila a imagem otimizada, sobe o PostgreSQL com pgvector, sobe a API e ativa o Caddy com HTTPS.

### 3.4. Conecte o Tailscale
```bash
tailscale up
```
Aponte o n8n do Raspberry Pi para o IP do Tailscale da VPS (`http://100.x.y.z:8000`).

---

## ✅ Checklist de Go-Live (10 Pontos de Sucesso)

- [ ] Chave de API de IA configurada no `.env` (`GEMINI_API_KEY` ou `OPENROUTER_API_KEY`).
- [ ] API rodando e respondendo em `/health`.
- [ ] Contatos principais cadastrados com seus papéis em `POST /api/v1/contacts/batch-import`.
- [ ] Dicionário léxico contendo jargões e termos específicos do seu negócio.
- [ ] Webhook do WhatsApp configurado para capturar mensagens de voz.
- [ ] n8n com as 4 automações ativadas (`Active = true`).
- [ ] Resumo diário configurado para o seu número de WhatsApp às 18:00.
- [ ] Relatório semanal configurado para domingo às 20:00.
- [ ] Script de backup diário configurado no Cron (`0 3 * * * /opt/whisperzap/scripts/backup_db.sh`).
- [ ] Teste real: envie um áudio de voz no WhatsApp e confirme o recebimento do texto revisado em segundos!
