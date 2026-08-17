# GLPI role

Deploys GLPI 11 with a dedicated MariaDB database as an independent Docker
Compose project.

## Operating model

- the official GLPI and MariaDB images use fixed versions;
- MariaDB is reachable only on an internal Docker network;
- the application fallback listener binds to loopback;
- Traefik publication is optional and uses the shared security middleware;
- automatic first installation is enabled by default;
- automatic schema updates on container restart are always disabled;
- the built-in scheduler runs in the official GLPI container;
- configuration, files, logs, marketplace and database have separate volumes.

## Administrator bootstrap

The role creates `glpi_admin_user` with a Vault-managed password, grants the
configured profile and then disables the default `glpi`, `tech`, `normal` and
`post-only` accounts. The default profile ID `4` is the clean-install
Super-Admin profile. Change it only after validating the target database.

Password rotation is deliberately gated by `glpi_admin_rotate_password`. Set it
to `true` for one authorized convergence and return it to `false` immediately.

## Security notes

The `.env` file is mode `0600` because the official GLPI image requires its
database password as an environment variable. MariaDB receives both passwords
through read-only files. Secrets remain in Ansible Vault and must never be
committed in an inventory.

Secure session cookies are enabled by default. The direct HTTP listener is
intended for health validation, not routine authenticated access. Use the
Traefik HTTPS route locally or through an SSH tunnel to the Traefik HTTPS port.

## Execution

```bash
ansible-playbook \
  --vault-password-file ~/.ansible/vault-password \
  -i inventories/validation/hosts.yml \
  playbooks/glpi.yml
```

The role validates the runtime requirements, database schema, encryption key,
timezone support, managed administrator and HTTPS security headers.

## Upgrade rule

Do not change `glpi_image` and converge directly in production. Create and
verify a backup, test the target image and explicit `db:update` operation in an
isolated environment, then execute the approved upgrade runbook. Normal role
execution rejects `glpi_skip_auto_update: false`.
