# GLPI backup role

Configures consistent, scheduled GLPI backups and verifies recovery with
disposable Docker resources. Active database and application volumes are never
overwritten by the verification operation.

## Protected state

- transactional MariaDB dump with routines, triggers and events;
- GLPI configuration, including `glpicrypt.key` and `config_db.php`;
- documents, attachments, inventories and other content under `files`;
- application logs used for incident analysis;
- marketplace plugins;
- Compose, PHP and image metadata without secret files;
- SHA-256 manifest for every artifact.

Backups are stored with root-only permissions under:

```text
/var/backups/infrastructure-platform/glpi/<UTC_TIMESTAMP>/
```

The backup temporarily enables GLPI maintenance mode while the database and
application files are captured. The error handler always attempts to disable
maintenance mode before reporting failure.

## Isolated verification

The `verify` operation validates checksums, imports the SQL dump into a
disposable MariaDB container, checks the required GLPI schema and restores the
application archive into a disposable Docker volume. It requires a non-empty
encryption key, database configuration and GLPI core tables before removing all
temporary resources.

```bash
sudo /usr/local/sbin/glpi-backup backup
sudo /usr/local/sbin/glpi-backup verify
sudo systemctl status glpi-backup.timer
```
