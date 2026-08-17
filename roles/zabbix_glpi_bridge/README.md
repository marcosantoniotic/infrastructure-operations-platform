# Zabbix-GLPI bridge role

Deploys an internal-only, idempotent bridge from eligible Zabbix trigger events
to GLPI 11 tickets. The role manages a dedicated GLPI technical account and
OAuth client, plus a dedicated Zabbix notification user, webhook media type and
action.

## Contract

- only events at or above `zabbix_glpi_bridge_min_severity` and carrying the
  configured tag, by default `glpi=ticket`, reach the bridge;
- the original Zabbix problem `eventid` is the immutable correlation key;
- repeated problem deliveries do not create another ticket;
- recovery creates one GLPI timeline followup and moves the ticket to the
  configured solved or closed status;
- repeated recovery deliveries do not create another followup;
- `netbox_id`, when inherited by the event from a NetBox-managed Zabbix host,
  becomes a canonical `type=device; id=<id>; URL` reference in the ticket;
- NetBox remains authoritative for technical inventory data.

The bridge has no published host port. Its SQLite correlation database is
stored in `/var/lib/zabbix-glpi-bridge`; `/healthz` and `/metrics` are available
only on the GLPI and Zabbix Docker networks. The container runs as UID/GID
`65532`, read-only, without Linux capabilities and with `no-new-privileges`.

## Prerequisites

Deploy NetBox, Zabbix and GLPI first. The Zabbix API token is deliberately not
created from an administrator password by this role. Provision a dedicated API
user and token once, then store only the token in Vault. Its API role allow-list
must contain:

- `action.get`, `action.create`, `action.update`;
- `mediatype.get`, `mediatype.create`, `mediatype.update`;
- `role.get`;
- `user.get`, `user.create`, `user.update`;
- `usergroup.get`, `usergroup.create`.

The public `apiinfo.version` call needs no token and must not be included in the
allow-list. The GLPI account defaults to the Technician profile in entity 0;
use a narrower approved profile when the local service-desk model provides one.

## Configuration

All four credentials must come from Ansible Vault:

```yaml
zabbix_glpi_bridge_enabled: true
zabbix_glpi_bridge_zabbix_api_token: "{{ vault_zabbix_glpi_bridge_zabbix_api_token }}"
zabbix_glpi_bridge_glpi_user_password: "{{ vault_zabbix_glpi_bridge_glpi_user_password }}"
zabbix_glpi_bridge_glpi_oauth_secret: "{{ vault_zabbix_glpi_bridge_glpi_oauth_secret }}"
zabbix_glpi_bridge_webhook_token: "{{ vault_zabbix_glpi_bridge_webhook_token }}"

zabbix_glpi_bridge_zabbix_web_url: "https://zabbix.example.net"
zabbix_glpi_bridge_glpi_web_url: "https://glpi.example.net"
zabbix_glpi_bridge_netbox_url: "https://netbox.example.net"
```

Generate the GLPI password with at least 16 characters and both shared secrets
with at least 32 random characters. Copy the variable names from
`inventories/example/group_vars/all/vault.example.yml`, replace the
placeholders and encrypt `vault.yml` before deployment.

## Deployment and validation

```bash
ansible-playbook \
  --vault-password-file /secure/path/vault-password \
  -i inventories/validation/hosts.yml \
  playbooks/zabbix-glpi-bridge.yml
```

Apply the `glpi=ticket` tag only to approved triggers or hosts. NetBox-managed
hosts already receive the `netbox_id` tag from `netbox_zabbix_sync`; the bridge
does not copy names, serials, addresses, racks or interfaces into GLPI.

The laboratory acceptance command is intentionally explicit because it creates
one synthetic GLPI ticket:

```bash
sudo docker compose \
  --project-directory /opt/zabbix-glpi-bridge \
  run --rm zabbix-glpi-bridge \
  python /usr/local/libexec/zabbix-glpi-bridge.py validate-event-flow
```

Acceptance requires one ticket, one recovery followup, final status solved or
closed, one recovered SQLite correlation and a second Ansible convergence with
`changed=0`.

## Rotation, rollback and removal

Rotate one credential at a time in Vault. Set
`zabbix_glpi_bridge_glpi_rotate_password: true` for exactly one convergence
when changing the GLPI account password, then return it to `false`. Revoke the
old Zabbix token only after `self-test` succeeds with the replacement.

For rollback, disable the managed Zabbix action first, retain the SQLite state
directory, restore the previous reviewed templates and converge again. For
removal, set `zabbix_glpi_bridge_enabled: false`, disable/delete the managed
Zabbix action and media type, revoke both technical credentials, and archive
the correlation database according to the ticket-retention policy. The role
does not delete tickets or NetBox data.
