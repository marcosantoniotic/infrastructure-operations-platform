# Zabbix backup role

Configures consistent, scheduled backups for the Zabbix Compose project and
supports an isolated restore test without changing the active database.

## Backup contents

- transactional MySQL dump with routines, triggers, and events;
- alert scripts, external scripts, exports, and SNMP trap data;
- sanitized operational Compose definition;
- image and format metadata;
- SHA-256 manifest for every protected artifact.

Backups are written with root-only permissions under:

```text
/var/backups/infrastructure-platform/zabbix/<UTC_TIMESTAMP>/
```

## Restore verification

The `verify` operation:

1. validates all checksums;
2. validates the operational data archive;
3. starts an isolated and disposable MySQL container;
4. restores the SQL dump with error propagation;
5. confirms the Zabbix `dbversion` and `hosts` tables;
6. removes the disposable container.

The active Zabbix database is never stopped or modified.

## Execution

```bash
ansible-playbook \
  -i inventories/validation/hosts.yml \
  playbooks/zabbix-backup.yml

sudo /usr/local/sbin/zabbix-backup backup
sudo /usr/local/sbin/zabbix-backup verify
sudo systemctl status zabbix-backup.timer
```

## Recovery boundary

The module proves that the local backup can be restored into a compatible
MySQL image. External encrypted replication and full application recovery
remain separate controls.
