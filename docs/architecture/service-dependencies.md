# Dependências dos serviços

## Grafo de dependências

```mermaid
flowchart TD
    RHEL["RHEL + Docker"] --> Traefik
    RHEL --> Cockpit
    RHEL --> Agent["Zabbix Agent 2"]

    Traefik --> ZWeb["Zabbix Web"]
    ZWeb --> ZServer["Zabbix Server"]
    ZServer --> MySQL

    Traefik --> NetBox
    NetBox --> PostgreSQL
    NetBox --> Redis
    NetBox --> RedisCache["Redis/Valkey Cache"]
    NetBox --> Worker
    Sync["NetBox-Zabbix Sync"] --> NetBox
    Sync --> ZServer

    Traefik --> Grafana
    Grafana --> Prometheus
    Prometheus --> NodeExporter["Node Exporter"]
    Prometheus --> cAdvisor
    Prometheus --> Blackbox
    Prometheus --> SNMPExporter["SNMP Exporter"]
    Prometheus --> UniFiPoller["UniFi Poller"]

    Traefik --> Portainer
    Traefik --> SocketProxy["Docker Socket Proxy"]
```

## Ordem recomendada de recuperação

1. RHEL, armazenamento, rede e Docker.
2. Traefik e Docker Socket Proxy.
3. Bancos e caches.
4. Zabbix e NetBox.
5. Prometheus e Grafana.
6. Portainer e integrações auxiliares.
7. Validação de Cloudflare, DNS e acesso local.

## Falhas em cascata

| Falha | Impacto esperado |
|---|---|
| Traefik | aplicações indisponíveis por nome, mesmo com containers ativos |
| MySQL | Zabbix sem persistência operacional |
| PostgreSQL | NetBox indisponível |
| Valkey/Redis | filas, cache ou worker do NetBox degradados |
| Prometheus | dashboards de métricas sem dados novos |
| Grafana | métricas continuam coletadas, mas sem visualização |
| Cloudflare | acesso externo indisponível; acesso local deve permanecer |
| UDM | indisponibilidade de rede e DNS local |
| SRV01 | indisponibilidade total da plataforma |
