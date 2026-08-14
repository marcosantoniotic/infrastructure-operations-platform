#!/usr/bin/env bash
set -Eeuo pipefail

readonly artifact_dir="${CI_ARTIFACT_DIR:?CI_ARTIFACT_DIR is required}"

for service in traefik cloudflare_tunnel zabbix netbox netbox_zabbix_sync portainer observability; do
  docker compose \
    --project-directory "${artifact_dir}/${service}" \
    --file "${artifact_dir}/${service}/compose.yaml" \
    config --quiet
done

docker run --rm \
  --entrypoint /bin/promtool \
  --volume "${artifact_dir}/observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  --volume "${artifact_dir}/observability/alerts.yml:/etc/prometheus/alerts.yml:ro" \
  prom/prometheus:v3.13.1 \
  check config /etc/prometheus/prometheus.yml

docker run --rm \
  --entrypoint /bin/blackbox_exporter \
  --volume "${artifact_dir}/observability/blackbox.yml:/etc/blackbox_exporter/config.yml:ro" \
  prom/blackbox-exporter:v0.28.0 \
  --config.file=/etc/blackbox_exporter/config.yml \
  --config.check
