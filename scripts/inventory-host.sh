#!/usr/bin/env bash
set -euo pipefail

# Produz inventário técnico sem ler arquivos de segredo e sem imprimir
# endereços, portas publicadas, variáveis de ambiente ou conteúdo de volumes.

echo "SYSTEM"
hostnamectl --static
. /etc/os-release
echo "$PRETTY_NAME"
uname -r

echo "RESOURCES"
nproc
free -h
df -hT /

echo "RUNTIME"
docker version --format 'Docker Engine {{.Server.Version}}'
docker compose version

echo "PROJECTS"
docker compose ls --format json |
  jq -r '.[] | [.Name,.Status] | @tsv'

echo "CONTAINERS"
docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}' |
  sort

echo "STORAGE"
docker system df

echo "NATIVE_SERVICES"
for service_name in docker firewalld zabbix-agent2; do
  enabled="$(systemctl is-enabled "$service_name" 2>/dev/null || true)"
  active="$(systemctl is-active "$service_name" 2>/dev/null || true)"
  printf '%s|%s|%s\n' "$service_name" "$enabled" "$active"
done
