# Zabbix-GLPI observability validation evidence

Validation date: 2026-08-20

Environment: isolated VMware laboratory (`srv01-validation`)

Scope: private metrics collection, Prometheus alerts, Grafana dashboard and
idempotent convergence.

## Acceptance results

- the bridge joined the internal `iop_integration_metrics` network without a
  published host port;
- Prometheus loaded the `zabbix-glpi-bridge` job and reported it `up == 1`;
- the metrics endpoint exposed event, duplicate, failure, last-success and
  processing-duration series;
- `promtool check config` accepted the configuration and all four bridge alert
  rules;
- Grafana provisioned dashboard UID `zabbix-glpi-bridge`;
- all 14 active Prometheus targets were healthy;
- existing HTTP and DNS probes passed after the intentionally separate
  `SRV02-STANDBY` DNS target was powered on;
- the observability playbook completed with `ok=50 changed=0 failed=0`;
- the bridge playbook completed with `ok=21 changed=0 failed=0`.

No synthetic production ticket was created during this gate. The previously
accepted problem/duplicate/recovery flow remained unchanged.
