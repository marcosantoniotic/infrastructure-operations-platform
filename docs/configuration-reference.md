# Referência de configuração

## Layout no host

| Projeto | Diretório | Arquivo principal |
|---|---|---|
| Traefik | `/opt/traefik` | `compose.yaml`, `traefik.yml`, `dynamic/` |
| Zabbix | `/opt/zabbix` | `compose.yaml`, `secrets/` |
| NetBox | `/opt/netbox` | `docker-compose.yml`, `docker-compose.override.yml` |
| Observabilidade | `/opt/observability` | `compose.yaml`, `prometheus/`, `alertmanager/`, `grafana/`, `blackbox/`, `secrets/` |
| Portainer | `/opt/portainer` | `compose.yaml` |

## Cockpit

O Cockpit é instalado como serviço nativo do RHEL e publicado pelo Traefik.
Como a porta `9090` é reservada ao fallback local do Prometheus, o socket do
Cockpit utiliza `9091`. A automação aplica o rótulo SELinux `websm_port_t` à
porta sem desabilitar o modo enforcing.

| Variável | Padrão | Finalidade |
|---|---|---|
| `cockpit_hostname` | `cockpit.<BASE_DOMAIN>` | nome DNS publicado |
| `cockpit_listen_port` | `9091` | porta HTTPS nativa |
| `cockpit_enable_traefik` | `false` | publica o serviço no proxy |
| `cockpit_direct_firewall_access` | `false` | permite acesso direto pela rede |
| `cockpit_login_title` | `Infrastructure Operations Platform` | identificação da tela de login |

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
- Agent 2 instalado diretamente no RHEL, em modo ativo, com listener passivo
  restrito a loopback e template `Linux by Zabbix agent active`;
- mapa do ecossistema provisionado pela API, com dez checks e sete triggers reais;
- integração NetBox-Zabbix com token restrito;

### Sincronização NetBox-Zabbix

`netbox_zabbix_sync_enabled` ativa a role dedicada executada depois das roles
NetBox e Zabbix. O segredo `vault_netbox_zabbix_sync_api_token` deve ser um token
Zabbix restrito às operações de leitura e manutenção dos hosts gerenciados.

Somente dispositivos NetBox com a tag `zabbix` e IP primário são reconciliados.
Grupo e template são configurados por nome em `netbox_zabbix_sync_group` e
`netbox_zabbix_sync_template`; IDs específicos de um ambiente não são aceitos.
O campo personalizado `zabbix_hostid` é criado de forma idempotente. A remoção
da tag desabilita o host gerenciado no Zabbix, sem apagá-lo.

Tokens de API pertencem à instância Zabbix que os emitiu. Em uma migração ou
reconstrução do banco, gere um token novo no destino e atualize o Vault; copiar
o valor usado pela instância de origem resulta em `Not authorized`.
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
- inventário demonstrativo opcional e idempotente, limitado ao ambiente de
  validação e composto exclusivamente por nomes fictícios e prefixos RFC 5737.

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
- Alertmanager com agrupamento, deduplicação, avisos de resolução e entrega
  SMTP autenticada por segredo armazenado no Ansible Vault;
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
