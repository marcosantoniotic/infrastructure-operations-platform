# Operação diária

## Saúde geral

```bash
hostnamectl
free -h
df -hT /
docker compose ls
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
systemctl --failed
```

## Consumo de containers

```bash
docker stats --no-stream
docker system df
```

## Projetos

```bash
cd /opt/traefik && docker compose ps
cd /opt/zabbix && docker compose ps
cd /opt/netbox && docker compose ps
cd /opt/observability && docker compose ps
cd /opt/portainer && docker compose ps
```

## Logs

```bash
docker logs --since 30m <container>
journalctl -u zabbix-agent2 --since '30 minutes ago'
journalctl -u docker --since '30 minutes ago'
```

Não publique logs sem remover tokens, cookies, nomes pessoais, endereços e cabeçalhos de autenticação.

## Validação de configuração

```bash
docker compose config --quiet
```

Para Prometheus:

```bash
docker exec <prometheus-container> promtool check config /etc/prometheus/prometheus.yml
```

## Critérios de saúde

- todos os projetos Compose em execução;
- containers críticos `healthy` quando healthcheck existir;
- todos os targets esperados do Prometheus em `UP`;
- mapa Zabbix sem problemas inesperados;
- acesso local e externo funcional;
- filesystem abaixo dos limites definidos;
- backup recente e verificável.
