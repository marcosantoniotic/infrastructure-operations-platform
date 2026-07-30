# Zabbix role

Deploys Zabbix Server 7.4, its Nginx frontend and a dedicated MySQL 8.4 LTS
database as an independent Compose project.

## Security model

- MySQL is reachable only on an internal Docker network;
- agent traffic uses a separate network attached only to Zabbix Server;
- database credentials are read-only bind mounts with private SELinux relabeling;
- the web and server fallback ports bind to loopback by default;
- the server role rejects non-loopback publication of TCP 10051;
- Traefik publication is opt-in and uses the shared security middleware;
- the default Zabbix administrator password is replaced during first deployment;
- persistent database and operational script data use named volumes.

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
