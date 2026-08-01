# Observability role

Deploys Prometheus, Alertmanager, Grafana, Node Exporter, cAdvisor and Blackbox
Exporter as an independent Compose project.

## Responsibilities

- Prometheus stores high-resolution time series with bounded retention;
- Alertmanager groups, deduplicates and routes Prometheus alerts by email;
- Node Exporter provides RHEL host metrics;
- cAdvisor provides container resource metrics;
- Blackbox Exporter provides HTTP/TLS and DNS availability and latency probes;
- Grafana provides provisioned, version-controlled visualization.

Zabbix remains the event and topology platform for its monitored assets.
Alertmanager independently routes the metric and probe rules evaluated by
Prometheus; it does not replace Zabbix triggers or maps.

## Security model

- Prometheus and Grafana fallback ports bind to loopback;
- exporter endpoints remain on an internal Docker network;
- Blackbox Exporter has no published host port;
- Grafana public signup, anonymous access and telemetry are disabled;
- the Grafana administrator password is supplied through Ansible Vault;
- the SMTP key is supplied through Ansible Vault and mounted as a read-only
  file visible only to the Alertmanager runtime user;
- only Grafana is optionally published through Traefik;
- Prometheus and Grafana data use independent named volumes;
- cAdvisor receives the host access required for container metrics and is not
  exposed outside the internal metrics network.

## Execution

```bash
ansible-playbook \
  -i inventories/validation/hosts.yml \
  playbooks/observability.yml
```

Provisioned dashboards include host and container resources, application and
TLS health, backup health, and managed DNS service health.

Each item in `observability_blackbox_targets` creates an independent HTTP
probe module. Optional fields include `host_header`, `valid_status_codes`, and
`tls_insecure`, allowing environment-specific behavior without hard-coding
application endpoints in the role.

Each item in `observability_dns_targets` creates an independent DNS probe with
an explicit address, query name and optional query type. These probes require
no AdGuard administrative credential and are suitable for availability alerts.

Set `observability_alertmanager_enabled: true`, provide the SMTP login and
sender/recipient addresses, and store `vault_alertmanager_smtp_password` in the
encrypted inventory vault. Alertmanager binds only to loopback by default.

Critical alerts wait 15 seconds and repeat every four hours while the incident
remains active. Warning alerts are grouped for two minutes and repeat every 12
hours. A critical TLS-expiry alert inhibits the lower-priority warning for the
same service. All routes send a resolved notification when service recovers.
