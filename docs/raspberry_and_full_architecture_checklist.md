# 📋 Checklist de Go-Live no Raspberry Pi & Auditoria Global da Stack

Este documento estabelece o **Checklist Operacional de Go-Live no Raspberry Pi 3B (`ssh peixe` - `192.168.1.99`)** e a **Matriz de Verificação End-to-End de Toda a Arquitetura e Stack** (Homelab ⇄ VPS Hostinger).

---

## 🧭 Diagrama de Topologia de Produção

```text
       ┌─────────────────────────────────────────────────────────────┐
       │             WhatsApp (Seu Celular / Grupo)                  │
       └──────────────────────────────┬──────────────────────────────┘
                                      │ Webhook
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                    HOMELAB / RASPBERRY PI 3B (peixe)                       │
│  • IP: 192.168.1.99 / Tailscale: 100.74.64.89                              │
│  • hermes-evolution-api (Porta 8080 - Conector WhatsApp QR)               │
│  • hermes-n8n (Porta 5678 - Master Orchestrator)                           │
│  • hermes-evolution-redis & hermes-evolution-postgres (Dados locais)       │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      │ Chamadas REST (STT / RAG / Memória)
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                     VPS HOSTINGER (Alpine Linux v3.22)                     │
│  • IP Público: 179.197.73.80 / Tailscale: 100.106.3.81                     │
│  • hermes-api (Porta 8005 - FastAPI, Faster-Whisper, Gemini AI Gateway)    │
│  • hermes-db (PostgreSQL 16 com extensão pgvector)                         │
│  • hermes-caddy (Proxy Reverso HTTPS)                                      │
│  • Backup Automatizado (Cron 03:00 com retenção de 7 dias)                 │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 🍓 PARTE 1: Checklist de Go-Live no Raspberry Pi (`peixe`)

| # | Ação | Comando / Procedimento | Status |
| :--- | :--- | :--- | :---: |
| **4.1** | **Download do Código** | `git clone https://github.com/brunocorisco86/whisperzap.git /root/whisperzap && ln -sfn /root/whisperzap /opt/whisperzap` | ⏳ Pendente |
| **4.2** | **Variáveis de Produção** | Configurar `HERMES_API_URL=http://179.197.73.80:8005` (ou `http://100.106.3.81:8005`) no `.env` do Raspberry Pi | ⏳ Pendente |
| **4.3** | **Subir Stack Homelab** | `cd /opt/whisperzap && docker compose -f docker-compose.homelab-whatsapp.yml up -d` | ⏳ Pendente |
| **4.4** | **Parear WhatsApp** | Acessar `http://192.168.1.99:8080`, abrir a instância `hermes` e escanear o QR Code no WhatsApp | ⏳ Pendente |
| **4.5** | **Ativar Master Orchestrator** | Acessar o n8n em `http://192.168.1.99:5678`, importar `workflows/n8n_whatsapp_master_orchestrator.json` e ligar o botão **Active** | ⏳ Pendente |

---

## 🔍 PARTE 2: Matriz de Auditoria e Verificação de Toda a Arquitetura

Após subir a stack no Raspberry Pi, executamos a **Auditoria Global** em 6 etapas para garantir 100% de estabilidade:

### 1. Teste de Conectividade de Rede (Raspberry Pi ➔ VPS)
- **Objetivo**: Confirmar que o n8n no Raspberry Pi alcança a API do Whisper na VPS sem bloqueios de firewall.
- **Teste**:
  ```bash
  ssh peixe "curl -s http://179.197.73.80:8005/health"
  ```
- **Critério de Sucesso**: Retornar `{"status":"healthy", "environment":"production"}`.

### 2. Teste de Sessão do WhatsApp (Evolution API no Raspberry Pi)
- **Objetivo**: Garantir que a instância `hermes` está com status `open`.
- **Teste**:
  ```bash
  curl -s -H "apikey: seu_token_whatsapp_aqui" http://192.168.1.99:8080/instance/fetchInstances
  ```
- **Critério de Sucesso**: `connectionStatus: "open"`.

### 3. Teste do Webhook da Evolution API para o n8n
- **Objetivo**: Garantir que novos eventos de mensagens disparam o n8n local.
- **Teste**:
  ```bash
  curl -s -H "apikey: seu_token_whatsapp_aqui" http://192.168.1.99:8080/webhook/find/hermes
  ```
- **Critério de Sucesso**: URL apontando para `http://n8n:5678/webhook/whatsapp-voice-received`.

### 4. Teste de Transcrição Ponta a Ponta (Áudio WhatsApp ➔ James)
- **Objetivo**: Enviar um áudio real de voz pelo WhatsApp para o número conectado.
- **Critério de Sucesso**: Receber de volta em segundos a mensagem formatada:
  ```text
  🎙️ James (Mordomo Virtual)

  _Transcrição_:
  [Texto falado devidamente pontuado e transcrito pelo Whisper na VPS]
  ```

### 5. Teste de Consulta Interativa RAG (Texto WhatsApp ➔ Hermes)
- **Objetivo**: Enviar um texto iniciando com `?` no WhatsApp (ex: `? quais são as prioridades?`).
- **Critério de Sucesso**: O Hermes consulta a memória na VPS e devolve:
  ```text
  🧠 *Hermes Agent*:

  [Resposta contextual citando fatos ou diretrizes cadastradas]
  ```

### 6. Verificação de Saúde do Banco de Dados e Backups na VPS
- **Objetivo**: Garantir que as tabelas estão sendo persistidas e o cron de backup está ativo.
- **Teste**:
  ```bash
  ssh hostinger "docker exec hermes-db psql -U postgres -d hermes_voice_memory -c 'SELECT count(*) FROM messages;' && crontab -l | grep backup_db.sh"
  ```
- **Critério de Sucesso**: PostgreSQL respondendo consultas e Cron agendado para as 03:00.
