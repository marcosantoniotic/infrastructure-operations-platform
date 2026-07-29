# Observability role

Deploys Prometheus, Grafana, Node Exporter, cAdvisor and Blackbox Exporter as
an independent Compose project.

## Responsibilities

- Prometheus stores high-resolution time series with bounded retention;
- Node Exporter provides RHEL host metrics;
- cAdvisor provides container resource metrics;
- Blackbox Exporter provides HTTP/TLS availability and latency probes;
- Grafana provides provisioned, version-controlled visualization.

Zabbix remains responsible for operational triggers, events and maps. This
module does not duplicate that responsibility.

## Security model

- Prometheus and Grafana fallback ports bind to loopback;
- exporter endpoints remain on an internal Docker network;
- Blackbox Exporter has no published host port;
- Grafana public signup, anonymous access and telemetry are disabled;
- the Grafana administrator password is supplied through Ansible Vault;
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

The initial dashboard is
`Infrastructure Operations — Host & Containers`. Network monitoring exporters
are intentionally implemented as later extensions.

Each item in `observability_blackbox_targets` creates an independent probe
module. Optional fields include `host_header`, `valid_status_codes`, and
`tls_insecure`, allowing environment-specific behavior without hard-coding
application endpoints in the role.
