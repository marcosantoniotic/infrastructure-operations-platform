# Inventário atual

Data de referência: 2026-07-27.

## Host

| Propriedade | Valor |
|---|---|
| Nome lógico | `SRV01-RHEL9` |
| Sistema | Red Hat Enterprise Linux 9.8 |
| Kernel | 5.14, linha RHEL 9 |
| CPU atribuída | 16 vCPU |
| Memória | 7,5 GiB |
| Swap | 2 GiB |
| Disco principal | 60 GB |
| Filesystem raiz | XFS sobre LVM |
| Uso do filesystem na coleta | 25% |

## Runtime

| Componente | Versão |
|---|---|
| Docker Engine | 29.6.2 |
| Docker Compose | 5.3.1 |
| Zabbix Agent 2 | 7.4.12 |

## Aplicações e imagens

| Componente | Versão/imagem observada |
|---|---|
| Traefik | 3.7.5 |
| Docker Socket Proxy | 0.4.2 |
| Zabbix Server/Web | 7.4.12 |
| MySQL do Zabbix | imagem fixada por digest |
| NetBox | 4.5.10, imagem local customizada |
| PostgreSQL | 18 Alpine |
| Valkey | 9.0 Alpine |
| Grafana OSS | 13.0.2 |
| Prometheus | 3.12.0 |
| Node Exporter | 1.11.1 |
| cAdvisor | 0.55.1 |
| Blackbox Exporter | 0.28.0 |
| SNMP Exporter | 0.30.1 |
| UniFi Poller | 3.3.3 |
| Portainer CE | versão controlada pelo projeto Compose |

## Capacidade Docker

- 5 projetos Compose;
- 19 containers ativos;
- 12 volumes locais ativos;
- aproximadamente 2,1 GB em volumes Docker no momento do inventário;
- aproximadamente 4,7 GB em imagens.

## Serviços nativos

- Docker: habilitado e ativo.
- firewalld: habilitado e ativo.
- Zabbix Agent 2: habilitado e ativo.
- Cockpit: aplicação nativa publicada pelo proxy.

## Persistência

| Projeto | Dados persistentes |
|---|---|
| Zabbix | MySQL, exportações e SNMP traps |
| NetBox | PostgreSQL, mídia e filas/cache |
| Observabilidade | Prometheus e Grafana |
| Traefik | estado ACME |
| Portainer | configuração da instância |

## Situação de backup

Não foram encontrados timers ativos de backup do NetBox ou Zabbix na coleta. Existem artefatos de backup no workspace de administração, mas eles não devem ser considerados cobertura até que:

1. os timers sejam implantados;
2. a execução seja monitorada;
3. a retenção seja definida;
4. uma restauração seja comprovada.

## Dados deliberadamente omitidos

- endereços IP e sub-redes;
- domínio real;
- nomes de usuários;
- IDs de contas e túneis;
- tokens, senhas e hashes;
- conteúdo de bancos, volumes e inventário pessoal.
