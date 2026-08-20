# Zabbix to GLPI bridge operations

This runbook covers the internal, idempotent event bridge managed by
`roles/zabbix_glpi_bridge`. The webhook endpoint is reachable only from its
Docker networks; Prometheus uses the private `iop_integration_metrics` network.

## Routine checks

1. Confirm `up{job="zabbix-glpi-bridge"} == 1` in Prometheus.
2. Open the Grafana dashboard `Infrastructure Operations — Zabbix to GLPI Bridge`.
3. Check `docker compose --project-directory /opt/zabbix-glpi-bridge ps`.
4. Inspect `docker compose --project-directory /opt/zabbix-glpi-bridge logs --since 30m zabbix-glpi-bridge`.
5. Confirm that `zabbix_glpi_bridge_failures_total` is not increasing.

## Alert response

- `ZabbixGLPIBridgeUnavailable`: verify the container and private metrics
  network, then rerun the role. Do not publish port 8080 on the host.
- `ZabbixGLPIBridgeProcessingFailure`: preserve logs, identify the Zabbix event
  ID, and verify the GLPI API and credentials.
- `ZabbixGLPIBridgeSuccessStale`: first confirm eligible events occurred. Quiet
  periods are valid and do not justify synthetic production tickets.
- `ZabbixGLPIBridgeDuplicateBurst`: inspect the Zabbix action delivery policy.
  The bridge has already suppressed duplicate tickets.

## Safe reprocessing and state recovery

Never delete `/var/lib/zabbix-glpi-bridge/correlation.sqlite3` to force a retry.
Before reprocessing, search GLPI for the event reference and query the database.
Re-send only when no ticket or recovery update exists.

For recovery, stop the bridge, copy the SQLite database and its `-wal`/`-shm`
files when present, restore them with owner/group `65532:65532`, and start the
bridge. Run the role, confirm `/healthz`, then repeat a processed event to prove
idempotency. Preserve the damaged database separately for analysis.

## Credential rotation and rollback

Rotate secrets in Ansible Vault and converge once. For the GLPI password, set
`zabbix_glpi_bridge_glpi_rotate_password: true` for exactly one run and return it
to `false`. Validate problem, duplicate, recovery and duplicate recovery flows.
Rollback by deploying the previous reviewed revision while preserving the
SQLite state. To disable the integration, disable the managed Zabbix action
first and then set `zabbix_glpi_bridge_enabled: false`.
