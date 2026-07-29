# Catálogo de módulos

| Módulo | Playbook | Estado | Dependências automáticas |
|---|---|---|---|
| Preflight | `playbooks/preflight.yml` | implementado | nenhuma |
| Baseline RHEL | `playbooks/bootstrap-rhel.yml` | implementado | RHEL 9+ |
| Docker Engine | `playbooks/docker.yml` | implementado | RHEL 9+ |
| NetBox | `playbooks/netbox.yml` | implementado, validado e integrado ao Traefik | Docker; Traefik opcional |
| Backup do NetBox | `playbooks/netbox-backup.yml` | implementado e validado | systemd + Docker |
| Traefik | `playbooks/traefik.yml` | implementado e validado | Docker |
| Zabbix | `playbooks/zabbix.yml` | implementado e validado | Docker; Traefik opcional |
| Observabilidade | `playbooks/observability.yml` | planejado | Docker |
| Portainer | `playbooks/portainer.yml` | planejado | Docker |
| Integrações | `playbooks/integrations.yml` | planejado | módulos correspondentes |
| GLPI | `playbooks/glpi.yml` | fase futura | Docker e proxy opcional |

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
