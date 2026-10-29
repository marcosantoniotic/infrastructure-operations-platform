# NetBox-Zabbix synchronization role

Reconciles NetBox devices tagged `zabbix` with Zabbix hosts every 60 seconds.
It creates and updates managed hosts, preserves unmanaged Zabbix tags, disables
hosts whose NetBox tag was removed, and records the Zabbix host ID in NetBox.

The reconciler runs in the NetBox application context and reads/writes NetBox
through its Django ORM; Zabbix operations use JSON-RPC and an API token stored in
Ansible Vault. Group and template names are resolved at runtime; manually
maintained database queries and environment-specific numeric IDs are not used.

```yaml
netbox_zabbix_sync_enabled: true
netbox_zabbix_sync_api_token: "{{ vault_netbox_zabbix_sync_api_token }}"
netbox_zabbix_sync_group: Linux servers
netbox_zabbix_sync_template: Linux by Zabbix agent active
```

Only devices with the configured tag and a primary IP are synchronized. A
name collision with an unmanaged Zabbix host fails safely instead of taking
ownership of that host.

## Primary IP changes and controlled acceptance

For an existing owned host, a changed primary IP updates the existing main
agent interface (`type=1`, `main=1`) with `hostinterface.update`. The host ID is
not replaced. IPv4 takes precedence over IPv6. The reconciler owns the primary
agent interface's IP, `useip=1`, empty DNS and port `10050`; changing the IP also
reasserts those settings. Unmanaged tags are merged, not deleted. Host
description and secondary interfaces are not managed by this code.
Zabbix response-only tag metadata (such as `automatic`) is not sent back in
updates: local tag/value pairs are preserved without invalid API parameters.

There is **no per-device-ID CLI filter**: tag/site selection and preflight checks
are not an authorization boundary against all other managed hosts. In
particular, do not run a global `--apply` as a functional test in a populated
environment. The regular Compose service repeats `--apply`; executing an
additional process there does not suspend that loop.

The [controlled IP-change acceptance record](../../docs/testing/netbox-zabbix-ip-functional-20261028.md)
separates real API evidence from offline tests and states the tested scope,
cleanup and limitations. The isolated harness is **not** a production launcher.
