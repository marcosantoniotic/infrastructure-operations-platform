# Visão geral da arquitetura

## Objetivo

A plataforma reúne serviços de operação de infraestrutura em uma arquitetura de referência profissional, mantendo isolamento lógico, persistência independente e pontos claros de integração. A baseline atual executa em nó único como ambiente de validação técnica; seus padrões de segurança, observabilidade e governança foram desenhados para serem reproduzíveis.

## Camadas

### Borda e identidade

Cloudflare fornece publicação externa e autenticação prévia. O conector do túnel é tratado como componente de borda e não é pressuposto como parte do mesmo projeto Compose do host.

### Rede local

O gateway UDM controla roteamento, DNS local e políticas entre redes. O MikroTik permanece equipamento monitorado e pode exercer funções específicas de roteamento, sem integrar o plano de controle do host.

### Entrada da plataforma

Traefik recebe HTTP/HTTPS nos endereços do host, seleciona o serviço pelo nome DNS e aplica middlewares comuns. O painel administrativo também passa pelo próprio proxy e pela camada de identidade.

### Serviços de operação

- NetBox: fonte de verdade para DCIM/IPAM.
- Zabbix: disponibilidade, triggers, mapas e eventos.
- Grafana: visualização operacional.
- Prometheus: métricas.
- Portainer: administração do runtime Docker.
- Cockpit: administração do RHEL.

### Persistência

- NetBox usa PostgreSQL e dois serviços compatíveis com Redis/Valkey.
- Zabbix usa MySQL.
- Prometheus e Grafana usam volumes próprios.
- Configurações vivem sob `/opt/<projeto>`.
- Dados persistentes não são tratados como parte do código-fonte.

## Projetos Compose

| Projeto | Responsabilidade | Quantidade atual |
|---|---|---:|
| `traefik` | entrada, TLS e descoberta Docker | 2 containers |
| `zabbix` | servidor, frontend e banco | 3 containers |
| `netbox` | aplicação, worker, sincronização e dados | 6 containers |
| `observability` | métricas, exporters e dashboards | 7 containers |
| `portainer` | gestão de containers | 1 container |

O Cockpit e o Zabbix Agent 2 são serviços nativos do host.

## Limites de responsabilidade

| Sistema | É autoridade para | Não deve substituir |
|---|---|---|
| NetBox | ativos, IPAM, relações e metadados | monitoramento temporal |
| Zabbix | disponibilidade, eventos e alertas | inventário mestre |
| Prometheus | métricas e séries temporais | gestão de ativos |
| Grafana | visualização e correlação | coleta primária |
| GLPI, futuramente | chamados, atendimento e ativos de service desk | DCIM/IPAM do NetBox |

## Disponibilidade

O desenho atual é de nó único. Redes e volumes isolam falhas lógicas, mas não fornecem alta disponibilidade do host. Uma falha do SRV01 afeta toda a plataforma, e isso deve ser mitigado com backup testado, documentação e capacidade de reconstrução.
