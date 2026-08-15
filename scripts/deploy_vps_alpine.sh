#!/bin/sh
# ==============================================================================
# Script de Deploy e Inicialização em VPS Alpine Linux — Hermes Voice Memory
# ==============================================================================

set -e

echo "🚀 ========================================================="
echo "🚀 Iniciando Deploy do Hermes Voice Memory em Alpine Linux"
echo "🚀 ========================================================="

# 1. Verifica se está executando em Alpine Linux e instala pacotes necessários
if [ -f /etc/alpine-release ]; then
    echo "📦 Detectado Alpine Linux $(cat /etc/alpine-release). Atualizando repositórios..."
    apk update
    apk add --no-cache docker docker-cli-compose curl bash tailscale
    rc-update add docker boot || true
    service docker start || true
else
    echo "ℹ️ Sistema não é Alpine Linux. Prosseguindo com ambiente Docker padrão..."
fi

# 2. Verifica se o arquivo .env existe
if [ ! -f .env ]; then
    echo "⚠️ Arquivo .env não encontrado! Criando a partir de .env.example..."
    cp .env.example .env
    echo "❗ Por favor, revise as chaves de API no arquivo .env antes de usar em produção!"
fi

# 3. Cria diretórios de dados locais caso necessários
mkdir -p data assets test_results backups
chmod -R 755 data assets

# 4. Constrói e inicializa a stack com Docker Compose
echo "🐳 Construindo imagens e iniciando containers..."
docker compose down || true
docker compose up -d --build

echo "⏳ Aguardando inicialização dos serviços (15 segundos)..."
sleep 15

# 5. Executa teste de conectividade e health check
echo "🔍 Validando saúde da API..."
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Hermes Voice Memory API está ONLINE e saudável!"
    curl -s http://localhost:8000/health | grep "status" || true
else
    echo "⚠️ Falha no health check inicial. Verificando logs dos containers:"
    docker compose logs --tail=50 hermes-api
fi

echo "🎉 ========================================================="
echo "🎉 Deploy concluído com sucesso!"
echo "🎉 ========================================================="
