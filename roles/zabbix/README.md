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

## Existing or recovered MySQL storage

By default `zabbix_mysql_external_volume: ""` retains the original
Compose-managed `mysql_data` behavior. To reuse a separately restored and
validated volume, set its name **only in the intended environment's private
inventory**:

```yaml
zabbix_mysql_external_volume: existing-validated-mysql-volume
```

The role requires that external volume to exist, even in check mode. It never
creates an empty fallback, repairs data, or deletes the previous volume. Before
any deployment changes, it also refuses to replace an external volume selected
by the installed Compose definition with an empty/default or different name.
Treat volume migration as a separate backup-and-restore operation. The previous
Compose file is backed up when rendering changes.

For local validation, keep this selection in the ignored
`.validation/ansible/group_vars/all/20-storage.yml`, outside the generated
Zabbix section of `main.yml`. `Run-ValidationZabbix.ps1` stages that file when
present. Other inventories must not inherit it. These safeguards address storage
selection only; review other private runtime customizations before a full deploy.

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

## HTTPS cookies behind a trusted proxy

`zabbix_trusted_https_proxy_enabled` defaults to false. For a tested Alpine nginx
frontend, it mounts a restricted HTTPS map and FastCGI parameters so Zabbix can
emit Secure cookies when TLS terminates at the proxy. Configure the explicit
`zabbix_trusted_https_proxy_subnet`; never trust arbitrary forwarded headers.
Test against the pinned image, its nginx include paths and both ingress paths
before enabling. Only recreate the web frontend for this change; do not rebuild
or replace database volumes. This does not add an explicit SameSite attribute
to Zabbix's application-managed cookie.
