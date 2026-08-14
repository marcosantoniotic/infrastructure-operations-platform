# Encrypted external backup role

Replicates the validated NetBox and Zabbix backup sets into an encrypted Restic
repository. The default transport is an rclone OneDrive remote named
`onedrive`.

The role installs checksum-pinned Restic and rclone binaries, protects the
repository password and OAuth configuration with mode `0600`, initializes the
repository, schedules a persistent systemd timer, applies retention and
publishes sanitized Prometheus textfile metrics.

Secrets must be supplied through Ansible Vault. Never commit `rclone.conf`, the
Restic password, repository contents or command output containing tokens.

The Restic repository password is part of the recovery chain and must remain
available for the lifetime of that repository. If an existing destination
rejects the configured password, preserve it unchanged and either recover the
original password from the authorized secret store or select a new, empty
repository path. Never delete or reinitialize an unknown repository merely to
make convergence pass.

Run the module independently:

```bash
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/external-backup.yml \
  --ask-vault-pass
```

For local validation, set `external_backup_require_rclone: false` and use a
disposable filesystem repository. This exercises encryption, retention,
metrics and restore behavior without cloud credentials.
