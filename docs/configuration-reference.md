# Referência de configuração

## Layout no host

| Projeto | Diretório | Arquivo principal |
|---|---|---|
| Traefik | `/opt/traefik` | `compose.yaml`, `traefik.yml`, `dynamic/` |
| Zabbix | `/opt/zabbix` | `compose.yaml`, `secrets/` |
| NetBox | `/opt/netbox` | `docker-compose.yml`, `docker-compose.override.yml` |
| Observabilidade | `/opt/observability` | `compose.yaml`, `prometheus/`, `grafana/`, `blackbox/`, `snmp/` |
| Portainer | `/opt/portainer` | `compose.yaml` |

## Traefik

Configuração estática esperada:

- API e dashboard habilitados sem modo inseguro;
- entrypoints web e websecure;
- entrypoint interno de métricas;
- provider Docker apontando para Socket Proxy;
- `exposedByDefault=false`;
- provider de arquivos dinâmicos;
- ACME por DNS challenge;
- access log habilitado.

Configuração dinâmica:

- redirecionamento HTTP para HTTPS conforme política;
- cadeia de headers de segurança;
- configuração TLS;
- middlewares reutilizáveis;
- roteadores de serviços não-Docker quando necessários.

Consulte [exemplo sanitizado](../config/examples/traefik-static.yml).

## Zabbix

- frontend e servidor na mesma versão;
- MySQL dedicado;
- credenciais em arquivos read-only com relabel privado do SELinux;
- Agent 2 instalado diretamente no RHEL;
- mapa do ecossistema com triggers reais;
- integração NetBox-Zabbix com token restrito;
- banco conectado somente ao backend interno;
- tráfego de agentes separado em rede dedicada;
- frontend publicado pelo Traefik, com fallback limitado ao loopback.

### Backup do Zabbix

- dump MySQL consistente com transação única, rotinas, triggers e eventos;
- dados operacionais de scripts, exportações e traps em arquivo separado;
- manifesto SHA-256 e metadados sem segredos;
- timer `systemd` persistente com retenção configurável;
- restauração validada em MySQL temporário e isolado;
- banco ativo preservado durante backup e verificação.

## NetBox

- imagem local customizada e versionada;
- PostgreSQL dedicado;
- Valkey principal e cache;
- worker em processo separado;
- sincronização Zabbix em serviço separado;
- plugins de topologia, QR code e cálculo IP;
- frontend publicado somente pelo Traefik.

## Portainer

- Community Edition em versão LTS fixada;
- volume nomeado dedicado para o banco interno;
- credencial administrativa fornecida por Ansible Vault;
- endpoint Docker local pelo socket Unix;
- porta HTTP de fallback limitada ao loopback;
- frontend publicado pelo Traefik com TLS e headers padronizados;
- porta Edge não publicada enquanto o recurso não estiver em uso;
- Ansible e Compose permanecem como fonte oficial da configuração.

## Observabilidade

Prometheus:

- scrape global em intervalo controlado;
- retenção limitada por tempo e tamanho;
- lifecycle habilitado;
- endpoint no host limitado a loopback;
- jobs separados por origem.

Grafana:

- cadastro público desabilitado;
- datasource Prometheus provisionado;
- dashboards provisionados por arquivo;
- frontend publicado pelo Traefik.

Núcleo implementado:

- Prometheus com retenção simultânea por tempo e tamanho;
- Grafana com credencial administrativa em Ansible Vault;
- Node Exporter para métricas do RHEL;
- cAdvisor isolado para métricas de containers;
- Blackbox Exporter para disponibilidade HTTP, latência e certificados;
- dashboard `Infrastructure Operations — Host & Containers`;
- dashboard `Infrastructure Operations — Application & TLS Health`;
- portas de fallback limitadas ao loopback;
- exporters acessíveis apenas na rede interna de métricas.

Exporters:

- Node Exporter com filesystems do host em somente leitura;
- cAdvisor com acesso necessário ao runtime;
- Blackbox com alvos por hostname;
- SNMP Exporter para equipamentos de rede;
- UniFi Poller para UDM/UniFi.

Consulte os exemplos de [Prometheus](../config/examples/prometheus.yml) e [Blackbox](../config/examples/blackbox.yml).

## Segredos

| Segredo | Forma esperada |
|---|---|
| Cloudflare API token | arquivo em diretório `secrets/` |
| MySQL do Zabbix | Docker secret |
| PostgreSQL do NetBox | arquivo/variável externa ao Git |
| token Zabbix API | arquivo `.env` restrito |
| credencial UniFi | arquivo `.env` restrito |
| senha administrativa Portainer | Ansible Vault + arquivo read-only |
| senha administrativa Grafana | Ansible Vault + arquivo read-only |

O valor nunca é documentado ou versionado.
