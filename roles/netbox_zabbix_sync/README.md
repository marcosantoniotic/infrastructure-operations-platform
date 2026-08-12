# NetBox-Zabbix synchronization role

Reconciles NetBox devices tagged `zabbix` with Zabbix hosts every 60 seconds.
It creates and updates managed hosts, preserves unmanaged Zabbix tags, disables
hosts whose NetBox tag was removed, and records the Zabbix host ID in NetBox.

The integration uses product APIs and a restricted Zabbix API token stored in
Ansible Vault. Group and template names are resolved at runtime; database access
and environment-specific numeric IDs are not used.

```yaml
netbox_zabbix_sync_enabled: true
netbox_zabbix_sync_api_token: "{{ vault_netbox_zabbix_sync_api_token }}"
netbox_zabbix_sync_group: Linux servers
netbox_zabbix_sync_template: Linux by Zabbix agent active
```

Only devices with the configured tag and a primary IP are synchronized. A
name collision with an unmanaged Zabbix host fails safely instead of taking
ownership of that host.
