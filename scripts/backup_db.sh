#!/bin/bash
# ==============================================================================
# Script de Backup Automatizado do PostgreSQL e Grafo — Hermes Voice Memory
# ==============================================================================

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

echo "💾 [$(date)] Iniciando rotina de backup do Hermes Voice Memory..."

# 1. Backup do Banco PostgreSQL
DB_CONTAINER="hermes-db"
DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-hermes_voice_memory}"
DUMP_FILE="$BACKUP_DIR/hermes_db_$TIMESTAMP.sql.gz"

if docker ps --format '{{.Names}}' | grep -q "^$DB_CONTAINER$"; then
    echo "📦 Extraindo dump do PostgreSQL via Docker ($DB_NAME)..."
    docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$DUMP_FILE"
    echo "✅ Backup do PostgreSQL salvo em: $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))"
else
    echo "⚠️ Container $DB_CONTAINER não está em execução. Verificando fallback SQLite local..."
    if [ -f "data/hermes.db" ]; then
        cp data/hermes.db "$BACKUP_DIR/hermes_sqlite_$TIMESTAMP.db"
        echo "✅ Backup do SQLite local salvo."
    fi
fi

# 2. Backup do Grafo de Conhecimento NetworkX
if [ -f "data/hermes_graph.json" ]; then
    cp data/hermes_graph.json "$BACKUP_DIR/hermes_graph_$TIMESTAMP.json"
    echo "✅ Backup do Grafo salvo em: $BACKUP_DIR/hermes_graph_$TIMESTAMP.json"
fi

# 3. Rotação e limpeza de backups com mais de 7 dias
echo "🧹 Removendo backups com mais de $RETENTION_DAYS dias..."
find "$BACKUP_DIR" -type f \( -name "*.sql.gz" -o -name "*.json" -o -name "*.db" \) -mtime +$RETENTION_DAYS -exec rm -f {} \;

echo "🎉 [$(date)] Rotina de backup concluída com sucesso!"
