# Cockpit role

Installs the native RHEL web console, enables socket activation, and configures
its reverse-proxy trust boundary through explicit origins and forwarded headers.

Direct firewall exposure is disabled by default. When Traefik integration is
enabled, Cockpit remains a native host service and Traefik connects to its
local HTTPS endpoint through a dedicated backend transport.

An optional dedicated administrator can be provisioned with
`cockpit_admin_enabled`. Its password hash must come from Ansible Vault; the
role unlocks only this account, requires membership in `wheel`, and validates
that a usable system password is configured. The automation SSH identity
remains key-only and locked for password authentication.
