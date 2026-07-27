# NetBox role

Implanta NetBox de forma independente com PostgreSQL, Valkey principal, Valkey de cache, worker e housekeeping.

## Dependências

- RHEL compatível;
- Docker Engine e Compose;
- collection `community.docker`;
- segredos fornecidos por Ansible Vault;
- 4 GiB de RAM no mínimo para o ambiente de validação.

## Modos

### Isolado

```yaml
netbox_enable_traefik: false
netbox_bind_address: 127.0.0.1
netbox_http_port: 8000
```

### Publicado pelo Traefik

```yaml
netbox_enable_traefik: true
netbox_traefik_hostname: "netbox.<BASE_DOMAIN>"
netbox_traefik_network: proxy
```

A rede externa do proxy deve existir antes da implantação.

## Execução

```bash
ansible-playbook -i inventories/validation/hosts.yml playbooks/netbox.yml
```

O playbook instala Docker quando necessário, mas não implanta Zabbix, Grafana, Prometheus, Portainer ou Cloudflare.

## Persistência

- PostgreSQL;
- dados persistentes do Valkey principal;
- mídia do NetBox.

O cache não é tratado como dado crítico.

## Validação

- configuração Compose válida;
- containers iniciados;
- healthchecks;
- endpoint `/login/` respondendo com HTTP 200 ou 302.

## Remoção

O role não remove volumes. Uma remoção completa e destrutiva deve ser executada manualmente somente após backup validado.
