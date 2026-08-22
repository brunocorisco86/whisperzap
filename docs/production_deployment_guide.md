# 🚀 Manual de Deploy em Produção — Cloud-Native & Kubernetes Ready

Este guia orienta o provisionamento, configuração e sustentação em produção do **Hermes Voice Memory** em qualquer **VPS Linux (Ubuntu, Debian, Alpine, Arch)** ou cluster **Kubernetes (K3s/K8s)**.

---

## 🏛️ 1. Arquitetura da Infraestrutura (Cloud-Agnostic)

```text
┌─────────────────────────────────────────────────────────────┐
│               QUALQUER SERVIDOR LINUX / VPS                 │
│                                                             │
│  - Reverse Proxy (Caddy / Nginx / Ingress HTTPS)            │
│  - Rede Bridge Interna: hermes_mesh_network (Latência < 1ms)│
│  - Stack Docker Compose:                                    │
│      ├── hermes-api (FastAPI, Faster-Whisper, AI Gateway)   │
│      ├── hermes-db (PostgreSQL 16 + pgvector)               │
│      ├── hermes-evolution-api (WhatsApp Baileys v2)         │
│      ├── hermes-n8n (Motor de Orquestração)                 │
│      ├── hermes-evolution-postgres (Persistência WhatsApp)  │
│      └── hermes-evolution-redis (Fila de Mensagens)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 2. Requisitos Mínimos Recomendados

- **CPU**: 1 a 2 vCPUs (x86_64 ou ARM64)
- **Memória RAM**: 2 GB a 4 GB RAM (stack completa opera em ~700MB)
- **Armazenamento**: 20 GB SSD
- **Docker**: Engine 24.0+ e Docker Compose v2 (ou K3s/Kubernetes)

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
