# 🚀 Manual de Deploy em Produção — VPS Alpine Linux & Raspberry Pi 3B

Este guia orienta o provisionamento, configuração e sustentação em produção do **Hermes Voice Memory** na arquitetura híbrida: **VPS Alpine Linux + Raspberry Pi 3B via Tailscale**.

---

## 🏛️ 1. Arquitetura da Infraestrutura

```text
┌─────────────────────────────────────────────────────────────┐
│                 HOMELAB (Raspberry Pi 3B)                  │
│                                                             │
│  - Evolution API / Z-API (WhatsApp Webhook)                │
│  - n8n Workflows (Orquestração & Crons)                     │
│  - Tailscale Client (IP: 100.64.0.2)                        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               │ 🔒 Túnel Privado Tailscale (WireGuard)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 VPS PRODUÇÃO (Alpine Linux)                 │
│                                                             │
│  - Tailscale Client (IP: 100.64.0.1)                        │
│  - Caddy Reverse Proxy (HTTPS Automático / Let's Encrypt)   │
│  - Docker Compose Stack:                                    │
│      ├── hermes-api (FastAPI, Whisper, AI Gateway, Grafo)   │
│      └── hermes-db (PostgreSQL 16 + pgvector)               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 2. Requisitos Mínimos

- **VPS**: Alpine Linux 3.19+ (1 vCPU, 2GB RAM, 20GB SSD).
- **Homelab**: Raspberry Pi 3B rodando Raspberry Pi OS / Alpine / Debian com Docker & n8n.
- **Rede**: Conta no [Tailscale](https://tailscale.com) (gratuita para homelab).

---

## 🛠️ 3. Passo a Passo de Instalação na VPS Alpine Linux

### 3.1. Conectando na VPS e Clonando o Repositório
```bash
ssh root@sua-vps-ip
git clone https://github.com/brunocorisco86/whisperzap.git /opt/whisperzap
cd /opt/whisperzap
```

### 3.2. Configuração das Variáveis de Ambiente
Copie o modelo de ambiente e configure as chaves de API:
```bash
cp .env.example .env
nano .env
```

Principais variáveis a preencher:
```env
ENVIRONMENT=production
AI_PROVIDER=gemini
GEMINI_API_KEY=sua_chave_gemini_aqui
POSTGRES_USER=hermes_admin
POSTGRES_PASSWORD=gere_uma_senha_forte
POSTGRES_DB=hermes_voice_memory
DATABASE_URL=postgresql://hermes_admin:gere_uma_senha_forte@hermes-db:5432/hermes_voice_memory
HERMES_DOMAIN=api.seudominio.com # ou :80 para responder apenas no IP do Tailscale
```

### 3.3. Configuração do Tailscale na VPS
```bash
# Instala e autentica no Tailscale
apk add tailscale
rc-update add tailscale boot
service tailscale start
tailscale up
```
Anote o IP atribuído pelo Tailscale (ex: `100.64.0.1`).

### 3.4. Execução do Script de Deploy Automatizado
```bash
chmod +x scripts/*.sh
./scripts/deploy_vps_alpine.sh
```

O script realizará:
1. Instalação e verificação do Docker e Docker Compose.
2. Build da imagem otimizada `hermes-api` com multi-stage.
3. Inicialização dos containers `hermes-db`, `hermes-api` e `hermes-caddy`.
4. Validação do endpoint de saúde `GET /health`.

---

## 🍓 4. Configuração do Raspberry Pi 3B (n8n Local)

### 4.1. Conexão ao Tailscale no Raspberry Pi
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

### 4.2. Configuração das Variáveis no n8n
No n8n rodando no Raspberry Pi, configure as variáveis de ambiente do workflow apontando para o IP Tailscale da VPS:

```env
HERMES_API_URL=http://100.64.0.1:8000
WHATSAPP_API_ENDPOINT=http://localhost:8080/message/sendText/default
WHATSAPP_API_TOKEN=seu_token_evolution_api
ADMIN_WHATSAPP_NUMBER=5544999999999
```

Importe os 4 workflows da pasta `workflows/` no n8n:
- `n8n_whatsapp_voice_transcription.json` (MVP 1 Transcrição de Voz)
- `n8n_daily_summary_cron.json` (Resumo Diário 18:00)
- `n8n_weekly_plan_cron.json` (Relatório Semanal Domingo 20:00)
- `n8n_hermes_qa_whatsapp.json` (Q&A Hermes via WhatsApp)

---

## 💾 5. Rotina de Backup Automatizado

Configure uma entrada no Cron da VPS para executar o backup diário às 03:00 da manhã:

```bash
crontab -e
```

Adicione a linha:
```text
0 3 * * * /opt/whisperzap/scripts/backup_db.sh >> /var/log/hermes_backup.log 2>&1
```

---

## 🩺 6. Diagnóstico e Comandos Úteis

```bash
# Checagem de integridade do cluster
./scripts/health_check_prod.sh

# Visualização de logs em tempo real
docker compose logs -f hermes-api

# Reinicialização graciosa
docker compose restart

# Execução manual de backup
./scripts/backup_db.sh
```
