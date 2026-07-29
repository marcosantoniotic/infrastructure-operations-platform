# Observabilidade

## Modelo de responsabilidades

### Zabbix

- disponibilidade de infraestrutura e aplicações;
- triggers e severidades;
- mapa do ecossistema;
- eventos e futura notificação;
- monitoramento do host pelo Agent 2;
- sincronização de ativos selecionados pelo NetBox.

### Prometheus

- métricas do RHEL por Node Exporter;
- métricas de containers por cAdvisor;
- disponibilidade e certificados por Blackbox Exporter;
- métricas do Traefik;
- telemetria de rede por SNMP Exporter;
- telemetria UniFi por UniFi Poller.

### Grafana

- visão consolidada do SRV01;
- dashboards de host, containers, Traefik, HTTP e certificados;
- dashboards de UDM/UniFi e MikroTik;
- correlação visual sem assumir a responsabilidade pela coleta.

## Mapa do ecossistema no Zabbix

O mapa lógico contém:

- Internet;
- Cloudflare;
- UDM;
- SRV01-RHEL9;
- Traefik;
- Zabbix e MySQL;
- NetBox, PostgreSQL e Valkey/Redis;
- Grafana e Prometheus;
- Portainer;
- Cockpit.

Cada elemento possui trigger real. Os vínculos mudam de estado conforme a trigger do componente dependente.

## Dashboards do Grafana

| Dashboard | Objetivo |
|---|---|
| SRV01-RHEL9 — Ecossistema | visão executiva do host e aplicações |
| Node Exporter Full | CPU, memória, disco e rede do RHEL |
| Docker Monitoring | consumo e comportamento dos containers |
| Traefik Official | requisições, latência e respostas |
| Blackbox HTTP | disponibilidade e tempo de resposta |
| SSL Certificate Monitor | validade dos certificados |
| Application & TLS Health | disponibilidade, HTTP, latência e validade TLS |
| UniFi/UDM | gateway, clientes e dispositivos |
| MikroTik | interfaces, CPU, memória e tráfego |

## Sinais mínimos

| Categoria | Sinal |
|---|---|
| Host | uptime, CPU, memória, swap e filesystem |
| Docker | estado, reinícios, CPU e memória |
| Aplicação | disponibilidade, latência e status HTTP |
| Banco/cache | disponibilidade TCP e uso de recursos |
| Proxy | requisições, erros e latência |
| Certificado | dias até expiração |
| Rede | perda, latência, interfaces e tráfego |

## Inventário de probes HTTP

O ambiente de validação comprova probes para:

- Prometheus e Grafana na rede interna de métricas;
- NetBox com cabeçalho `Host` específico;
- Zabbix frontend;
- Portainer;
- endpoint interno de métricas do Traefik.

Cada alvo gera um módulo Blackbox próprio e pode declarar URL, cabeçalho
`Host`, códigos HTTP aceitos e política TLS. O Cockpit utiliza o endpoint
`/ping` do serviço nativo e também participa dos probes HTTP centralizados.

## Alertas recomendados

- host indisponível;
- aplicação indisponível por três coletas;
- filesystem acima de 80% e 90%;
- memória acima de 90% por período sustentado;
- container reiniciando repetidamente;
- certificado com menos de 30 e 15 dias;
- falha de backup ou ausência de arquivo recente;

## Saúde dos backups

As rotinas de backup do NetBox e Zabbix publicam métricas no textfile collector
do Node Exporter. O dashboard `Infrastructure Operations — Backup Health`
apresenta o resultado da última execução e a idade do último backup válido.

Os alertas `PlatformBackupFailed` e `PlatformBackupStale` sinalizam,
respectivamente, uma execução malsucedida e a ausência de backup válido nas
últimas 26 horas. As métricas contêm apenas nome lógico, estado e timestamp;
arquivos, conteúdo e credenciais de backup não são expostos.
- Prometheus target down;
- sincronização NetBox-Zabbix sem execução recente.

## Retenção atual

Prometheus está configurado para retenção limitada por tempo e tamanho. A retenção do Zabbix deve ser documentada junto ao housekeeping após a primeira revisão de capacidade.
