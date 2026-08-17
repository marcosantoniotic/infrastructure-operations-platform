# GLPI laboratory validation evidence

## Scope

This record certifies the reproducible GLPI service module in the isolated
project laboratory. It contains no credentials, private addresses or data from
an operational environment.

Validation date: 2026-08-17.

Validated components:

- `AUTOMATION-CONTROLLER` as the Ansible control node;
- `SRV01-VALIDATION` as the platform target;
- `glpi/glpi:11.0.8`;
- `mariadb:11.8.8`;
- Traefik HTTPS route `glpi.localhost`.

## Result

| Control | Result |
|---|---|
| RHEL compatibility and subscription preflight | Passed |
| Docker Compose rendering and deployment | Passed |
| MariaDB health without a published host port | Passed |
| GLPI HTTP health listener bound to loopback | Passed |
| GLPI runtime requirements | Passed |
| Database schema integrity | Passed |
| `glpicrypt.key` presence | Passed |
| Timezone database support | Passed |
| Dedicated `glpi-admin` account and Super-Admin profile | Passed |
| Default GLPI accounts disabled | Passed |
| Official GLPI scheduler enabled | Passed |
| HTTPS certificate hostname and security headers | Passed |
| Authenticated web login and `/Helpdesk` redirect | Passed |
| Persistence after platform VM reload | Passed |
| Final Ansible convergence | `changed=0`, `unreachable=0`, `failed=0` |

## Corrections incorporated during certification

The laboratory exposed and verified three reusable corrections:

1. the GLPI runner reconstructs its local paths after nested validation
   runners return, avoiding PowerShell dynamic-scope collisions;
2. Ansible creates the named volumes and applies the official container
   UID/GID before Compose starts GLPI, preventing cache creation failures;
3. the isolated validation certificate includes `glpi.localhost`, allowing
   strict SNI validation through Traefik.

## Remaining phase gates

This evidence does not approve external publication, production data, backup
and isolated restore, Zabbix ticket creation, NetBox references or GLPI
dashboards. Those gates remain independent items in the project roadmap.
