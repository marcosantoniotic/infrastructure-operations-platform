# Zabbix role

Deploys Zabbix Server 7.4, its Nginx frontend and a dedicated MySQL 8.4 LTS
database as an independent Compose project.

The same role installs Zabbix Agent 2 natively on RHEL, links the managed host
to `Linux by Zabbix agent active`, and validates receipt of `system.uptime`.
Active checks reach the loopback-only server publication, so no agent listener
is exposed to the validation network.

## Security model

- MySQL is reachable only on an internal Docker network;
- native Agent 2 collection is active and uses the host loopback interface;
- passive Agent 2 listening is restricted to `127.0.0.1`;
- database credentials are read-only bind mounts with private SELinux relabeling;
- the web and server fallback ports bind to loopback by default;
- the server role rejects non-loopback publication of TCP 10051;
- Traefik publication is opt-in and uses the shared security middleware;
- the default Zabbix administrator password is replaced during first deployment;
- persistent database and operational script data use named volumes.

## Managed operational map

The role provisions an idempotent `Infrastructure Operations Platform` map
through the Zabbix API. Its service-chain elements are backed by real simple
checks and triggers for Traefik, Zabbix/MySQL, NetBox/PostgreSQL/Valkey,
Grafana/Prometheus, Portainer, Cockpit and the RHEL host. The Zabbix Server is
attached to the shared proxy network only when this managed monitoring is
enabled, allowing outbound checks without publishing additional ports.
The host label is derived from `platform_hostname`, preventing names from a
reference or production environment from leaking into validation maps.

## Standalone mode

```yaml
zabbix_enable_traefik: false
zabbix_web_bind_address: 127.0.0.1
zabbix_web_port: 8081
zabbix_server_bind_address: 127.0.0.1
zabbix_server_port: 10051
```

## Traefik mode

```yaml
zabbix_enable_traefik: true
zabbix_traefik_hostname: "zabbix.<BASE_DOMAIN>"
zabbix_traefik_network: proxy
zabbix_traefik_middlewares:
  - security-headers@file
```

The external proxy network and referenced middleware must exist first.

## Execution

```bash
ansible-playbook \
  -i inventories/validation/hosts.yml \
  playbooks/zabbix.yml
```

The native Zabbix Agent 2 on the same host reaches the server through loopback.
SNMP and agentless checks are initiated outbound by Zabbix Server. A future
requirement for remote passive agents must use a separately reviewed Zabbix
Proxy or an explicit Docker forwarding policy; changing the bind address alone
is intentionally rejected.
