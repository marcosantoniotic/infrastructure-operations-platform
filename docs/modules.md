# Catálogo de módulos

| Módulo | Playbook | Estado | Dependências automáticas |
|---|---|---|---|
| Preflight | `playbooks/preflight.yml` | implementado | nenhuma |
| Baseline RHEL | `playbooks/bootstrap-rhel.yml` | implementado | RHEL 9+ |
| Docker Engine | `playbooks/docker.yml` | implementado | RHEL 9+ |
| Métricas operacionais do AdGuard | `playbooks/adguard-metrics.yml` | implementado e validado | AdGuard inicializado; Node Exporter |
| NetBox | `playbooks/netbox.yml` | implementado, validado e integrado ao Traefik | Docker; Traefik opcional |
| Backup do NetBox | `playbooks/netbox-backup.yml` | implementado e validado | systemd + Docker |
| Traefik | `playbooks/traefik.yml` | implementado e validado | Docker |
| Cloudflare Tunnel | `playbooks/cloudflare-tunnel.yml` | implementado; ativação externa opcional | Docker; Traefik; Cloudflare Access |
| Zabbix | `playbooks/zabbix.yml` | implementado e validado | Docker; Traefik opcional |
| Backup do Zabbix | `playbooks/zabbix-backup.yml` | implementado e validado | systemd + Docker + Zabbix |
| Observabilidade | `playbooks/observability.yml` | implementado com host e containers | Docker; Traefik opcional |
| Backup da observabilidade | `playbooks/observability-backup.yml` | implementado para Grafana e Prometheus | systemd + Docker + Observabilidade |
| Janela de manutenção | `playbooks/maintenance-window.yml` | implementada com backup obrigatório e evidência | RHEL 9 + módulos da plataforma |
| Cockpit | `playbooks/cockpit.yml` | implementado e validado | RHEL 9; Traefik opcional |
| Portainer | `playbooks/portainer.yml` | implementado e integrado ao Traefik | Docker; Traefik opcional |
| Sincronização NetBox-Zabbix | `playbooks/netbox-zabbix-sync.yml` | implementada e validada | NetBox; Zabbix; token API restrito |
| Integração Zabbix-GLPI | `playbooks/zabbix-glpi-bridge.yml` | implementada, idempotente e validada | NetBox; Zabbix; GLPI; tokens dedicados |
| GLPI | `playbooks/glpi.yml` | implementado e validado no laboratório e no ambiente operacional | Docker; MariaDB dedicado; Traefik opcional |
| Backup do GLPI | `playbooks/glpi-backup.yml` | implementado para banco, chave, arquivos e marketplace | systemd + Docker + GLPI |

## Contrato dos módulos

Todo módulo deverá:

1. funcionar isoladamente;
2. declarar dependências;
3. falhar cedo em variáveis inválidas;
4. preservar dados persistentes;
5. suportar reexecução;
6. evitar segredos no output;
7. validar o serviço após implantação;
8. documentar atualização, rollback e remoção;
9. permitir integração opcional com Traefik;
10. possuir casos formais de validação técnica.
