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
| Consistent local backup and SHA-256 manifest | Passed |
| Isolated MariaDB and persistent-data restore | Passed |
| `glpicrypt.key` recovered and non-empty | Passed |
| Backup timer and metrics persisted after VM reload | Passed |
| Encrypted OneDrive snapshot and verified restore | Passed |
| Final Ansible convergence | `changed=0`, `unreachable=0`, `failed=0` |

## Corrections incorporated during certification

The laboratory exposed and verified five reusable corrections:

1. the GLPI runner reconstructs its local paths after nested validation
   runners return, avoiding PowerShell dynamic-scope collisions;
2. Ansible creates the named volumes and applies the official container
   UID/GID before Compose starts GLPI, preventing cache creation failures;
3. the isolated validation certificate includes `glpi.localhost`, allowing
   strict SNI validation through Traefik;
4. MariaDB backup and restore clients use the supported `MYSQL_PWD` or explicit
   password mechanisms while secrets remain inside protected containers;
5. the OneDrive validation runner escapes Linux command substitution before
   sending it through PowerShell and requires all four service manifests.

## Gate G4 evidence

On 2026-08-17, the validation environment created a real GLPI recovery point,
verified its manifest, imported the database into a disposable MariaDB 11.8.8
container and restored all four persistent paths into a disposable volume. The
timer remained `enabled` and `active` after VM reload, the latest point passed a
second isolated restore, and configuration-only convergence finished with
`changed=0`.

The encrypted external workflow then created Restic snapshot `96cbb672` with
NetBox, Zabbix, observability and GLPI. A clean `restic restore --verify`
recovered 4.503 GiB and verified 224 files before every available service
manifest passed SHA-256 validation. Identifiers are retained only as sanitized
laboratory evidence; no credentials, tokens or operational records are stored
here.

## Remaining phase gates

This evidence approves G4 protection in the isolated laboratory. Zabbix ticket
creation and canonical NetBox references were subsequently approved in the
[Gate G5 evidence](glpi-integrations-validation-evidence.md). Production data
and the final GLPI operational dashboards remain independent concerns.
