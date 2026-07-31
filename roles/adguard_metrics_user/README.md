# AdGuard metrics identity

Adds a dedicated, rotatable API identity to an initialized AdGuard Home
configuration. AdGuard Home has no read-only user role, so the identity has
administrative API capability even though the collector only performs GET
requests.

The role preserves `AdGuardHome.yaml.pre-metrics` before its first change. The
plaintext password and deterministic bcrypt salt must remain in Ansible Vault.
