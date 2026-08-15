#!/bin/bash
# ==============================================================================
# Script de Inicialização da Evolution API + n8n para Homelab / WhatsApp
# ==============================================================================

set -e

echo "🚀 ========================================================="
echo "🚀 Subindo Evolution API (WhatsApp) + n8n no seu Homelab"
echo "🚀 ========================================================="

COMPOSE_FILE="docker-compose.homelab-whatsapp.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ Arquivo $COMPOSE_FILE não encontrado na pasta raiz!"
    exit 1
fi

echo "🐳 Inicializando containers (Evolution API, Redis e n8n)..."
docker compose -f "$COMPOSE_FILE" up -d

echo "⏳ Aguardando inicialização dos serviços (10 segundos)..."
sleep 10

echo "\n✅ ========================================================="
echo "✅ SERVIÇOS ONLINE!"
echo "✅ ========================================================="
echo "📱 1. Evolution API (WhatsApp QR Code): http://localhost:8080"
echo "⚙️ 2. n8n (Painel de Automação Visual):  http://localhost:5678"
echo "🧠 3. Hermes Voice Memory API:          http://localhost:8000/docs"
echo "=========================================================\n"
