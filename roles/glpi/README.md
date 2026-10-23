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
- Ansible creates those volumes explicitly and assigns the application volumes
  to the validated GLPI container UID/GID before Compose starts the service.

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

PHP security patches should use a tested, immutable image reference, without
implicitly changing GLPI's application version or database schema. The optional
`glpi_php_security_hardening: true` mounts a separate readable ini with session
upload-progress/backtrace restrictions, without changing existing cookie,
upload, memory, or proxy settings. Defaults preserve previous deployment
behavior; this is not a substitute for a patched PHP binary.

`glpi_https_cookie_hardening: true` additionally enables Secure/HttpOnly,
SameSite and strict session IDs in that separate ini. It requires an explicit
`glpi_trusted_proxy_subnet` CIDR, HTTPS ingress and `glpi_tls_ca_file` for verified
validation. Migrate integration clients to verified HTTPS before enabling it;
GLPI rejects HTTP requests, including OAuth, when Secure cookies are required.
The trusted proxy network is a security boundary, not end-to-end backend TLS.
Do not make the entire legacy ini readable just to enable cookies: that also
changes memory/upload settings. These options default off and must be scoped
to the approved inventory, with snapshots/backups and isolated API tests.

Do not change `glpi_image` and converge directly in production. Create and
verify a backup, test the target image and explicit `db:update` operation in an
isolated environment, then execute the approved upgrade runbook. Normal role
execution rejects `glpi_skip_auto_update: false`.
