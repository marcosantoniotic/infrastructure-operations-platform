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

# Config rendering must preserve legacy storage and opt into existing external
# storage explicitly. This does not create volumes or start any containers.
docker compose --project-directory "${artifact_dir}/zabbix" \
  --file "${artifact_dir}/zabbix/compose.yaml" config --format json |
  python3 -c 'import json,sys; v=json.load(sys.stdin)["volumes"]["mysql_data"]; assert not v.get("external", False)'
docker compose --project-directory "${artifact_dir}/zabbix" \
  --file "${artifact_dir}/zabbix/compose.external-volume.yaml" config --format json |
  python3 -c 'import json,sys; v=json.load(sys.stdin)["volumes"]["mysql_data"]; assert v["external"] is True and v["name"] == "ci-existing-mysql-volume"'

docker compose --project-directory "${artifact_dir}/glpi" \
  --file "${artifact_dir}/glpi/compose.php-security.yaml" config --format json |
  python3 -c 'import json,sys; v=json.load(sys.stdin)["services"]["glpi"]["volumes"]; assert any(x["target"] == "/usr/local/etc/php/conf.d/zzz-iop-security.ini" and x.get("read_only") for x in v)'
grep --fixed-strings --quiet 'session.upload_progress.enabled=0' "${artifact_dir}/glpi/php-security.ini"
grep --fixed-strings --quiet 'fatal_error_backtraces=0' "${artifact_dir}/glpi/php-security.ini"

for service in glpi netbox zabbix traefik netbox_zabbix_sync zabbix_glpi_bridge; do
  docker compose --project-directory "${artifact_dir}/${service}" \
    --file "${artifact_dir}/${service}/compose.https.yaml" config --quiet
done
python3 -m py_compile "${artifact_dir}/netbox/cookie-security.py"
grep --fixed-strings --quiet 'SESSION_COOKIE_SECURE = True' "${artifact_dir}/netbox/cookie-security.py"
grep --fixed-strings --quiet 'CSRF_COOKIE_SECURE = True' "${artifact_dir}/netbox/cookie-security.py"
grep --fixed-strings --quiet 'session.cookie_secure=On' "${artifact_dir}/glpi/php-security.https.ini"
grep --fixed-strings --quiet '192.0.2.0/24' "${artifact_dir}/glpi/proxy-https.conf"
grep --fixed-strings --quiet '"1:https" on;' "${artifact_dir}/zabbix/proxy-cookie-context.conf"
grep --extended-regexp --quiet 'fastcgi_param[[:space:]]+HTTPS[[:space:]]+\$iop_cookie_https if_not_empty;' "${artifact_dir}/zabbix/fastcgi-cookie-params"

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
