# Grafana profile delivery validation

Date: 2026-11-07, America/Sao_Paulo. Scope: LAB01 only. No OPS access,
publication, release or full platform provisioning.

## Applied result

Five existing hosts received their configured technical group and ownership
marker: two Linux, one Windows and two ICMP. The same host IDs, interfaces,
templates, TLS settings, local groups and other tags were preserved. No host was
created or disabled. The other two hosts remained unchanged. The immediate
reconciliation after application reported zero changes and zero pending objects.

The signed Zabbix plugin source remains HTTPS with certificate and hostname
validation, a dedicated read-only account and an existing isolated TLS network.
The four dashboards were installed in the separate `IOP Perfis` folder using
`roles/grafana_profiles` and `playbooks/grafana-profiles.yml`. All six prior
dashboards were compared as complete API objects and remained unchanged.

## Checks

| Check | Observed result |
| --- | --- |
| Source signature and health | Official plugin 6.10.2, valid signature, source OK |
| Combined Compose | Other services and published ports unchanged |
| Host reconciliation | Five owned additions, then zero changes and no pending objects |
| Numeric series | Every data panel in all four dashboards returned populated numeric series |
| Reader visibility | Exactly the five eligible hosts |
| Real browser inspection | Overview, Linux, Windows and ICMP displayed real samples |
| Profile selector | Windows selection excluded Linux and ICMP hosts |
| Equipment selector | Linux list contained two hosts; selecting one reduced the displayed scope |
| Windows services | 65 services, readable state table, 10 rows per page; second page verified |
| Reapplication | Final Ansible execution completed with zero changes after the visual adjustment |
| Offline regression | 11 tests passed, including five tests for the new delivery filters and contract |
| Removal guards | Disabling installed Grafana or technical-group protection failed with zero changes; valid technical contract passed |
| Runtime | 23 containers running; configured healthchecks healthy; recovered MySQL mount preserved |
| Calls and notifications | Ticket count unchanged; zero alerts from the protected action during the window; action and bridge restored |

The first real Windows rendering exposed overlapping labels in the 65-series
timeline. The delivery filter now renders that panel as a paginated table of the
last collected state. Queries, item identities and server-side history are
unchanged. Stopped services retain neutral styling rather than being presented
as failures. The query and mapping regression test covers this adjustment.

## Automation and protection

The generic feature is opt-in and requires temporary approval and backup flags.
The controller inventory stores the environment-specific image, network and
credentials in Vault. Controller updates used targeted patches to preserve its
existing adjustments. Its filter path was explicitly declared, and deployment
used the configured automation user's existing known-host file with strict SSH
checking. No new host-key trust or certificate bypass was introduced.

Fresh application/configuration backups were copied to the protected private
backup destination and verified before application. The previous cold snapshot
and earlier backups were retained. Private API baselines and ownership records
support a scoped rollback; they are not included in this repository.

Rollback of visualization should preserve the technical associations and
synchronizer protection, restore only the previous Grafana delivery and operate
only on proven owned dashboard UIDs. Reverting memberships or decommissioning
the installed contract requires separate review. Do not restore application
databases or remove volumes to undo a dashboard change. Production rollback and
full VM restoration were not exercised by this validation.

The test proves reconciliation and dashboard queries, not the correctness of
every Windows service alert, SNMP collection or monitoring of future hosts.
ICMP remains availability/latency/loss only. No additional Windows services,
templates or triggers were started, replaced or suppressed.

## Publication review without environment access

The subsequent publication review ran 84 offline tests covering technical
groups, profile transitions/mapping, custom fields, dashboard contracts and
delivery policy. Eight YAML files parsed and eight copy artifacts rendered with
synthetic inputs. This is not a new Ansible or Docker Compose runtime test.
The original base Compose template is unchanged, and CI now explicitly runs the
new delivery test suite.

Follow-up guards restrict administrative HTTP to loopback and reject incompatible
source adoption, unowned providers/directories/folders, and incorrect ownership
markers. They were not applied to LAB01 or OPS during publication preparation.
Keep the PR in draft until CI and an isolated Ansible adoption/failure matrix
have been reviewed. See the [sanitized evidence record](../evidence/grafana-profile-delivery-20261107.sanitized.json).
