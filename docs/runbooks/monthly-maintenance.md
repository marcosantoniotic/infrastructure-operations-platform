# Monthly maintenance window

## Purpose

Apply controlled operating-system and pinned-container maintenance while
preserving a verified recovery point and producing sanitized operational
evidence. The workflow is operator initiated and is intentionally not scheduled
as an unattended timer.

## Recommended cadence

Reserve the second Saturday of each month at 02:00 in the platform's local
timezone. Keep the execution operator initiated so that incident status,
capacity, backups and the approved change reference are reviewed immediately
before authorization. Use `CHG-YYYY-NNNN` for an approved maintenance window
and `SIM-YYYYMMDD-NNN` for a rehearsal.

An operational rehearsal exercises recovery points, Compose reconciliation,
health checks, evidence and metrics without applying packages, refreshing
images, rebooting or replicating externally:

```bash
ansible-playbook \
  -i inventories/operational/hosts.yml \
  playbooks/maintenance-window.yml \
  --ask-vault-pass \
  -e maintenance_authorized=true \
  -e maintenance_change_reference=SIM-YYYYMMDD-NNN \
  -e maintenance_apply_os_updates=false \
  -e maintenance_refresh_container_images=false \
  -e maintenance_reboot_if_required=false \
  -e maintenance_run_external_backup=false
```

Authorization is supplied only on the command line for that execution. Keep
`maintenance_authorized: false` in every persistent inventory.

## Before authorization

1. confirm the approved change reference and maintenance window;
2. verify that no incident or recovery operation is active;
3. review available RHEL updates and repository health;
4. confirm local and external backup capacity;
5. announce expected impact;
6. preserve a hypervisor snapshot when the risk classification requires it.

## Validation environment

From the repository root on the Windows workstation:

```powershell
.\automation\scripts\Run-ValidationMaintenanceWindow.ps1
```

This executes the complete backup and post-maintenance validation path without
changing packages. To exercise RHEL updates and conditional reboot:

```powershell
.\automation\scripts\Run-ValidationMaintenanceWindow.ps1 -ApplyUpdates
```

Container images remain unchanged unless the separately controlled
`-RefreshContainerImages` switch is supplied. External replication is selected
with `-RunExternalBackup`.

## Production execution

Use an approved, descriptive change reference:

```bash
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/maintenance-window.yml \
  --ask-vault-pass \
  -e maintenance_authorized=true \
  -e maintenance_change_reference=CHG-YYYY-NNNN
```

Do not place credentials or customer information in the change reference.

## Workflow

The role:

1. validates authorization, filesystem capacity and backup utilities;
2. creates fresh NetBox, Zabbix, Grafana and Prometheus recovery points;
3. optionally replicates those points through the encrypted external backup;
4. optionally refreshes only the image references already pinned in Compose;
5. applies RHEL package updates;
6. reboots only when `dnf needs-restarting -r` requires it;
7. validates NetBox, Zabbix, Portainer, Prometheus and Grafana;
8. rejects unhealthy, exited or dead platform containers;
9. publishes Prometheus metrics and a sanitized JSON evidence record.

The validated Docker Compose plugin is excluded from generic package updates.
Its version is controlled by the `docker_engine` role and is upgraded only
after service publication and recovery tests pass in the validation
environment.

## Evidence

Evidence is written to:

```text
/var/log/infrastructure-platform/maintenance/
```

Node Exporter reads the status from:

```text
/var/lib/node_exporter/textfile_collector/maintenance.prom
```

The evidence contains component names, timestamps, HTTP results and maintenance
options. It excludes credentials, backup content, private application data and
tokens.

## Rollback

If validation fails:

1. stop further changes;
2. preserve logs and the failed state;
3. revert the VM snapshot when required by the change plan, or restore the
   affected component from the mandatory pre-maintenance recovery point;
4. reapply the last known-good Git revision;
5. rerun application health checks;
6. record the deviation and corrective action.

Package downgrades are not the primary rollback mechanism because dependency
transactions can be incomplete. Recovery points, reproducible configuration and
the hypervisor snapshot provide the controlled rollback path.
