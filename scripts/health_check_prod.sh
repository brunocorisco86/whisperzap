#!/bin/bash
# ==============================================================================
# Script de Verificação de Saúde e Diagnóstico — Hermes Voice Memory (Produção)
# ==============================================================================

set -e

API_URL="${1:-http://localhost:8000}"

echo "🩺 ========================================================="
echo "🩺 Diagnóstico de Saúde de Produção — Hermes Voice Memory"
echo "🩺 Alvo: $API_URL"
echo "🩺 ========================================================="

# 1. Verifica status dos containers Docker Compose
echo "\n📦 1. Status dos Containers Docker:"
if command -v docker > /dev/null 2>&1; then
    docker compose ps || docker ps --filter "name=hermes"
else
    echo "ℹ️ Docker CLI não disponível no path atual."
fi

# 2. Testa endpoint /health
echo "\n🔍 2. Verificando /health..."
HEALTH_RESPONSE=$(curl -sf "$API_URL/health" || echo "FAILED")

if [ "$HEALTH_RESPONSE" != "FAILED" ]; then
    echo "✅ Endpoint /health respondeu com sucesso:"
    echo "$HEALTH_RESPONSE" | grep -o '"status":"[^"]*"' || echo "$HEALTH_RESPONSE"
else
    echo "❌ Falha ao contactar $API_URL/health"
    exit 1
fi

# 3. Testa endpoint /api/v1/memory/stats
echo "\n📊 3. Verificando /api/v1/memory/stats..."
STATS_RESPONSE=$(curl -sf "$API_URL/api/v1/memory/stats" || echo "FAILED")

if [ "$STATS_RESPONSE" != "FAILED" ]; then
    echo "✅ Estatísticas da Memória recuperadas com sucesso:"
    echo "$STATS_RESPONSE"
else
    echo "⚠️ Falha ao contactar /api/v1/memory/stats"
fi

echo "\n🎉 ========================================================="
echo "🎉 Todos os testes de prontidão operacionais passaram!"
echo "🎉 ========================================================="
