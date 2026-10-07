#!/usr/bin/env bash
set -Eeuo pipefail

readonly artifact_dir="${CI_ARTIFACT_DIR:?CI_ARTIFACT_DIR is required}"

grep --fixed-strings --quiet \
  "netbox-qrcode==0.0.21" \
  "${artifact_dir}/netbox/plugin-requirements.txt"
grep --fixed-strings --quiet \
  '"netbox_qrcode"' \
  "${artifact_dir}/netbox/plugins.py"
grep --fixed-strings --quiet \
  "COPY topology-role-unknown.svg" \
  "${artifact_dir}/netbox/Dockerfile"
if grep --fixed-strings --quiet \
  "COPY topology-role-unknown.svg" \
  "${artifact_dir}/netbox/Dockerfile.qrcode-only"; then
  echo "QR-only NetBox Dockerfile must not copy the Topology Views fallback icon." >&2
  exit 1
fi

for service in traefik cloudflare_tunnel zabbix netbox netbox_zabbix_sync portainer glpi zabbix_glpi_bridge observability; do
  docker compose \
    --project-directory "${artifact_dir}/${service}" \
    --file "${artifact_dir}/${service}/compose.yaml" \
    config --quiet
done

docker run --rm \
  --entrypoint /bin/promtool \
  --volume "${artifact_dir}/observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  --volume "${artifact_dir}/observability/alerts.yml:/etc/prometheus/alerts.yml:ro" \
  prom/prometheus:v3.13.3 \
  check config /etc/prometheus/prometheus.yml

docker run --rm \
  --entrypoint /bin/blackbox_exporter \
  --volume "${artifact_dir}/observability/blackbox.yml:/etc/blackbox_exporter/config.yml:ro" \
  prom/blackbox-exporter:v0.28.0 \
  --config.file=/etc/blackbox_exporter/config.yml \
  --config.check
