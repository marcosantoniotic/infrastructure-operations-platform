# Managed DNS client

Configures a selected NetworkManager connection to use explicit DNS servers.
A negative DNS priority prevents resolvers learned by other connections from
leaking queries outside the managed path.

The role validates normal resolution and a known blocked domain after applying
the connection. It does not change routes, DHCP servers or other clients.

Rollback with NetworkManager:

```bash
nmcli connection modify "<connection>" ipv4.dns "" \
  ipv4.dns-priority 0 ipv4.ignore-auto-dns yes
nmcli device reapply <interface>
```
