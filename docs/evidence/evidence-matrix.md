# Matriz requisito–implementação–prova

| Competência | Implementação | Prova verificável |
|---|---|---|
| Administração RHEL | baseline, serviços nativos, SELinux e firewall | [baseline RHEL](../../roles/rhel_baseline/) e [Cockpit](../../roles/cockpit/) |
| Infraestrutura como código | imagem base, VMs e configuração idempotente | [Packer](../../automation/packer/), [Vagrant](../../automation/vagrant/) e [Ansible](../../playbooks/) |
| Containers | projetos Compose isolados e redes por responsabilidade | [roles da plataforma](../../roles/) e [dependências](../architecture/service-dependencies.md) |
| Inventário e IPAM | NetBox como fonte de verdade | [role NetBox](../../roles/netbox/) e [ADR de limites](../decisions/ADR-001-platform-boundary.md) |
| Monitoramento | Zabbix para eventos, triggers e mapas | [role Zabbix](../../roles/zabbix/) e [observabilidade](../observability.md) |
| Métricas e alertas | Prometheus, exporters, Grafana e Alertmanager | [role de observabilidade](../../roles/observability/) |
| Segurança de acesso | Traefik, TLS, middlewares e Zero Trust | [role Traefik](../../roles/traefik/) e [ADR de entrada](../decisions/ADR-002-ingress-and-security.md) |
| Gestão de segredos | Vault, arquivos protegidos e catálogo sem valores | [segredos e inventários](../secrets-and-inventories.md) e [catálogo](../../config/credential-catalog.json) |
| Continuidade | backups monitorados, réplica externa e recuperação isolada | [backup e restauração](../runbooks/backup-restore.md) e [RPO/RTO](../reliability-objectives.md) |
| CI e segurança de supply chain | validações, inventário de imagens e Trivy | [GitHub Actions](../../.github/workflows/) |
| Governança | ADRs, runbooks, criticidade e mudança | [documentação](../) e [ADRs](../decisions/) |

## Uso em entrevista

Para cada linha, explique primeiro o problema operacional, depois a decisão e
o trade-off, mostre a implementação e finalize com a prova. Essa sequência
evita uma apresentação baseada apenas em nomes de ferramentas.
