#!/bin/bash
# ==============================================================================
# Script de Sanitização e Ajuste de DNS no Raspberry Pi (peixe)
# ==============================================================================

echo "🛑 1. Parando e removendo containers legados do WhatsApp/n8n..."
docker stop hermes-n8n hermes-evolution-api hermes-evolution-postgres hermes-evolution-redis 2>/dev/null || true
docker rm hermes-n8n hermes-evolution-api hermes-evolution-postgres hermes-evolution-redis 2>/dev/null || true

echo "🔒 2. Desativando serviço Tailscale no Raspberry Pi..."
tailscale down 2>/dev/null || true
systemctl stop tailscaled 2>/dev/null || true
systemctl disable tailscaled 2>/dev/null || true

echo "🌐 3. Configurando DNS local para Unbound + Pi-hole (192.168.1.7)..."
echo "nameserver 192.168.1.7" > /etc/resolv.conf

# Se existir dhcpcd.conf, garante a persistência do DNS
if [ -f /etc/dhcpcd.conf ]; then
    sed -i '/static domain_name_servers/d' /etc/dhcpcd.conf
    echo "static domain_name_servers=192.168.1.7" >> /etc/dhcpcd.conf
fi

echo "✅ Limpeza concluída! Raspberry Pi livre para outras funções no Homelab."
