# Infrastructure Operations Platform

> **Production-grade reference architecture for infrastructure operations, observability, service exposure, asset management and operational governance.**

![Platform](https://img.shields.io/badge/platform-RHEL%209-EE0000?logo=redhat&logoColor=white)
![Runtime](https://img.shields.io/badge/runtime-Docker-2496ED?logo=docker&logoColor=white)
![Observability](https://img.shields.io/badge/observability-Zabbix%20%7C%20Prometheus%20%7C%20Grafana-F46800)
![Ingress](https://img.shields.io/badge/ingress-Traefik-24A1C1?logo=traefikproxy&logoColor=white)
![Security](https://img.shields.io/badge/security-Zero%20Trust-0F9D58)
![Evidence](https://img.shields.io/badge/portfolio_evidence-verified-2EA44F)
![Release](https://img.shields.io/badge/release-v1.0.0-6f42c1)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Validation](https://github.com/marcosantoniotic/infrastructure-operations-platform/actions/workflows/validation.yml/badge.svg)](https://github.com/marcosantoniotic/infrastructure-operations-platform/actions/workflows/validation.yml)

Plataforma profissional de operações de infraestrutura criada para demonstrar, validar e documentar práticas aplicáveis a ambientes corporativos. O projeto integra inventário técnico, proxy reverso, Zero Trust, observabilidade, monitoramento, gestão de containers, automação e governança operacional em uma arquitetura coesa.

A implementação autoral funciona como ambiente controlado de validação técnica contínua, inspirado em desafios e padrões encontrados ao longo da experiência profissional. O foco do projeto é a qualidade de engenharia: isolamento, segurança, rastreabilidade, recuperação, documentação e decisões arquiteturais reproduzíveis.

> Este repositório foi preparado para publicação. Endereços, domínios, identificadores de conta, credenciais e tokens reais não fazem parte do conteúdo versionado.

![Arquitetura sanitizada da plataforma](docs/evidence/assets/architecture-overview.svg)

## Leitura em dois minutos

1. Consulte os [resultados e evidências](docs/evidence/README.md).
2. Relacione competências, implementação e prova na [matriz de comprovação](docs/evidence/evidence-matrix.md).
3. Entenda contexto, decisões e resultados no [estudo de caso](docs/portfolio-case-study.md).
4. Verifique a automação nos workflows de [validação](.github/workflows/validation.yml) e [segurança de imagens](.github/workflows/image-security.yml).
5. Examine os procedimentos de [backup e restauração](docs/runbooks/backup-restore.md) e os [objetivos de confiabilidade](docs/reliability-objectives.md).

As capturas operacionais foram revisadas e sanitizadas antes da inclusão. O repositório não utiliza imagens simuladas como evidência.

## Executive overview

O projeto resolve cinco desafios comuns de operações:

1. consolidar a fonte de verdade de ativos e endereçamento;
2. publicar aplicações com TLS, identidade e políticas uniformes;
3. combinar monitoramento orientado a eventos com métricas de alta resolução;
4. operar workloads containerizados sem expor bancos e caches;
5. transformar conhecimento operacional em documentação, runbooks e decisões auditáveis.

## Competências demonstradas

- arquitetura Linux e administração RHEL;
- Docker, Compose, redes, volumes e ciclo de vida;
- reverse proxy, TLS, DNS e Cloudflare Zero Trust;
- Zabbix, Prometheus, Grafana e exporters;
- NetBox como fonte de verdade DCIM/IPAM;
- integração NetBox–Zabbix;
- monitoração de UniFi/UDM e MikroTik;
- hardening, gestão de segredos e segmentação;
- backup, disaster recovery e resposta a incidentes;
- documentação arquitetural, ADRs e gestão de mudanças.

## Technology stack

| Camada | Solução | Função |
|---|---|---|
| Sistema operacional | Red Hat Enterprise Linux 9 | Host da plataforma |
| Runtime | Docker Engine + Compose | Execução e ciclo de vida dos serviços |
| Entrada | Traefik | Proxy reverso, TLS e middlewares |
| Borda | Cloudflare Tunnel + Access | Publicação e controle de identidade |
| Inventário | NetBox | DCIM, IPAM e fonte de verdade |
| Monitoramento | Zabbix + Agent 2 | Eventos, triggers, mapas e disponibilidade |
| Métricas | Prometheus | Coleta e retenção de séries temporais |
| Visualização | Grafana | Dashboards consolidados |
| Administração | Portainer + Cockpit | Containers e sistema operacional |
| Rede | UniFi/UDM + MikroTik | Gateway e roteamento monitorados |

## Architecture at a glance

```mermaid
flowchart LR
    Internet["Internet"] --> Edge["Cloudflare<br/>Tunnel + Access"]
    Edge --> Gateway["UDM / Gateway"]
    Gateway --> Host["SRV01-RHEL9"]
    Host --> Proxy["Traefik"]

    Proxy --> Zabbix["Zabbix"]
    Zabbix --> ZabbixDB["MySQL"]

    Proxy --> NetBox["NetBox"]
    NetBox --> PostgreSQL["PostgreSQL"]
    NetBox --> Redis["Valkey/Redis<br/>principal + cache"]

    Proxy --> Grafana["Grafana"]
    Grafana --> Prometheus["Prometheus"]
    Prometheus --> Exporters["Node Exporter<br/>cAdvisor<br/>Blackbox<br/>SNMP Exporter<br/>UniFi Poller"]
    Gateway -. "telemetria somente leitura" .-> UniFiPoller["UniFi Poller"]
    UniFiPoller --> Prometheus

    Proxy --> Portainer["Portainer"]
    Proxy --> Cockpit["Cockpit"]
    NetBox -. "sincronização" .-> Zabbix
```

## Engineering principles

- NetBox é a fonte de verdade para ativos e endereçamento.
- Zabbix é responsável por estado, eventos, triggers e mapas.
- Prometheus armazena métricas de alta cardinalidade e séries temporais.
- Grafana entrega a visão operacional consolidada.
- Traefik é o único ponto de entrada HTTP/HTTPS no host.
- Cloudflare Access protege aplicações publicadas.
- Bancos, caches e exporters permanecem em redes internas.
- Segredos são fornecidos por arquivos ou variáveis externas ao Git.
- Mudanças preservam rollback e são validadas antes da promoção.

## Technical highlights

- cinco projetos Compose independentes por domínio funcional;
- 19 containers em execução na baseline documentada;
- entrada HTTP/HTTPS centralizada no Traefik;
- Docker Socket protegido por proxy restrito;
- acesso externo condicionado por identidade;
- acesso local preservado por DNS dividido;
- bancos e caches isolados em redes internas;
- monitoramento de host, containers, aplicações, certificados e rede;
- mapa Zabbix completo com triggers reais;
- dashboard executivo do ecossistema no Grafana;
- sincronização controlada entre NetBox e Zabbix;
- exemplos públicos completamente sanitizados.

## Resultados e evidências

| Resultado | Implementação | Evidência verificável |
|---|---|---|
| ambiente reproduzível | Packer, Vagrant e Ansible | [automação](automation/) e [guia do ambiente](docs/testing/validation-environment.md) |
| exposição segura | Traefik, TLS, middlewares e Docker Socket Proxy | [arquitetura](docs/architecture/overview.md) e [segurança](docs/security.md) |
| observabilidade integrada | Zabbix, Prometheus, Grafana e Alertmanager | [documentação](docs/observability.md) e [role versionada](roles/observability/) |
| continuidade validada | backups consistentes, réplica criptografada e restauração isolada | [runbook](docs/runbooks/backup-restore.md) |
| qualidade automatizada | validações de código, configuração, imagens e segurança | [GitHub Actions](.github/workflows/validation.yml) |
| governança técnica | ADRs, runbooks, inventário e catálogo de credenciais | [decisões](docs/decisions/) e [matriz de provas](docs/evidence/evidence-matrix.md) |

O [pacote de evidências](docs/evidence/README.md) reúne artefatos verificáveis e capturas operacionais revisadas, todos vinculados à [matriz de comprovação](docs/evidence/evidence-matrix.md).

### Visão operacional comprovada

As imagens abaixo foram capturadas no ambiente funcional de validação e sanitizadas para publicação. Clique em uma evidência para examiná-la em resolução integral.

| Recursos do host e containers | Disponibilidade das aplicações e TLS |
|---|---|
| [![Dashboard Grafana com recursos do host e containers](docs/evidence/grafana-platform-overview.png)](docs/evidence/grafana-platform-overview.png) | [![Dashboard Grafana com disponibilidade, latência e validade TLS](docs/evidence/grafana-application-tls-health.png)](docs/evidence/grafana-application-tls-health.png) |
| **Topologia operacional no Zabbix** | **Inventário demonstrativo no NetBox** |
| [![Mapa do ecossistema monitorado pelo Zabbix](docs/evidence/zabbix-ecosystem-map.png)](docs/evidence/zabbix-ecosystem-map.png) | [![Inventário de máquinas virtuais no NetBox](docs/evidence/netbox-inventory.png)](docs/evidence/netbox-inventory.png) |

Consulte também as provas de [stacks no Portainer](docs/evidence/portainer-stacks.png), [backup e recuperação](docs/evidence/backup-restore-validation.png) e [execuções do GitHub Actions](docs/evidence/github-actions-validation.png).

## Documentation map

- [Visão geral da arquitetura](docs/architecture/overview.md)
- [Estudo de caso para portfólio](docs/portfolio-case-study.md)
- [Resultados e evidências](docs/evidence/README.md)
- [Matriz requisito–implementação–prova](docs/evidence/evidence-matrix.md)
- [Dependências dos serviços](docs/architecture/service-dependencies.md)
- [Redes e fluxos](docs/architecture/networking.md)
- [Inventário atual](docs/inventory/current-state.md)
- [Referência de configuração](docs/configuration-reference.md)
- [Catálogo de módulos executáveis](docs/modules.md)
- [Inventários e gestão de segredos](docs/secrets-and-inventories.md)
- [Gestão de mudanças](docs/change-management.md)
- [Ambiente de validação como código](docs/testing/validation-environment.md)
- [Checklist de reprodução do zero](docs/deployment/from-zero-checklist.md)
- [Implantação reproduzível do ambiente operacional](docs/deployment/operational-environment.md)
- [Migração controlada para o IOP](docs/migration/legacy-to-iop.md)
- [Matriz de migração de dados](docs/migration/data-migration-matrix.md)
- [Observabilidade](docs/observability.md)
- [Segurança](docs/security.md)
- [Operação diária](docs/runbooks/daily-operations.md)
- [Inicialização e desligamento](docs/runbooks/startup-shutdown.md)
- [Backup e restauração](docs/runbooks/backup-restore.md)
- [Objetivos de confiabilidade, RPO, RTO e retenção](docs/reliability-objectives.md)
- [Criticidade e estratégia de continuidade](docs/service-criticality.md)
- [Resposta a incidentes](docs/runbooks/incident-response.md)
- [Contingência de DNS e proxy](docs/runbooks/dns-proxy-contingency.md)
- [Gestão de mudanças](docs/runbooks/change-management.md)
- [Adoção segura de IaC para Cloudflare](docs/runbooks/cloudflare-iac-adoption.md)
- [Módulo Cloudflare Tunnel](roles/cloudflare_tunnel/README.md)
- [Publicação segura](docs/publishing-checklist.md)
- [Changelog](CHANGELOG.md)
- [Baseline da release v1.0.0](docs/releases/v1.0.0.md)
- [Roadmap](docs/roadmap.md)
- [Fase futura: GLPI](docs/glpi-phase.md)

## Repository structure

```text
.
├── inventories/         # exemplos públicos e ambientes ignorados
├── automation/          # Packer, Kickstart, Vagrant e scripts de validação
├── playbooks/           # pontos de entrada independentes
├── roles/               # módulos Ansible idempotentes
├── config/              # exemplos sanitizados e convenções
├── docs/
│   ├── architecture/    # arquitetura e fluxos
│   ├── deployment/      # implantação reproduzível por ambiente
│   ├── decisions/       # registros de decisão arquitetural
│   ├── inventory/       # estado conhecido da plataforma
│   ├── migration/       # carga de dados, cutover e rollback
│   └── runbooks/        # procedimentos operacionais
├── inventory/           # catálogo legível por máquinas
└── scripts/             # validações sem segredos
```

## Modular deployment

A plataforma pode ser implantada integralmente ou por componente:

```bash
# Pré-requisitos
ansible-galaxy collection install -r requirements.yml

# Validação do host
ansible-playbook -i inventories/validation/hosts.yml playbooks/preflight.yml

# Baseline RHEL
ansible-playbook -i inventories/validation/hosts.yml playbooks/bootstrap-rhel.yml

# Docker Engine
ansible-playbook -i inventories/validation/hosts.yml playbooks/docker.yml

# Somente NetBox e suas dependências
ansible-playbook -i inventories/validation/hosts.yml playbooks/netbox.yml

# Somente Zabbix Server, frontend e MySQL
ansible-playbook -i inventories/validation/hosts.yml playbooks/zabbix.yml

# Backup consistente e restauração isolada do Zabbix
ansible-playbook -i inventories/validation/hosts.yml playbooks/zabbix-backup.yml

# Somente Portainer
ansible-playbook -i inventories/validation/hosts.yml playbooks/portainer.yml

# Prometheus, Grafana e exporters do host
ansible-playbook -i inventories/validation/hosts.yml playbooks/observability.yml

# Identidade técnica e métricas operacionais do AdGuard
ansible-playbook -i inventories/validation/hosts.yml playbooks/adguard-metrics.yml
ansible-playbook -i inventories/validation/hosts.yml playbooks/cockpit.yml

# Baseline inicial completa
ansible-playbook -i inventories/validation/hosts.yml playbooks/platform.yml
```

Consulte o [catálogo de módulos](docs/modules.md), o [guia do módulo NetBox](roles/netbox/README.md), a [gestão de segredos](docs/secrets-and-inventories.md) e o [plano de validação do ambiente](docs/testing/environment-validation-plan.md).

## Project evolution

O marco `v1.0.0` consolida a arquitetura de referência reproduzível, os controles
de segurança, a observabilidade, os backups, a recuperação e as evidências
operacionais. Consulte a [baseline da release](docs/releases/v1.0.0.md) e o
[changelog](CHANGELOG.md).

O GLPI será tratado como fase própria. Sua inclusão deverá respeitar o mesmo
modelo de proxy, identidade, observabilidade, backup e isolamento de dados, sem
sobrepor o papel do NetBox. Consulte [Fase futura: GLPI](docs/glpi-phase.md).

As próximas evoluções concentram-se em integrações ITSM, exercícios periódicos
de recuperação, módulos opcionais de telemetria de rede e resiliência
multi-nó orientada por requisitos mensuráveis.

## Professional positioning

Este repositório apresenta uma implementação autoral, funcional e reproduzível em ambiente de validação, não apenas um diagrama conceitual. A arquitetura é orientada à produção e baseada em desafios e padrões profissionais reais. O conteúdo documenta decisões, dependências, riscos conhecidos, controles implantados e lacunas ainda em tratamento, sem caracterizar o laboratório como ambiente corporativo de terceiros.

## License

Distribuído sob a [Apache License 2.0](LICENSE).
