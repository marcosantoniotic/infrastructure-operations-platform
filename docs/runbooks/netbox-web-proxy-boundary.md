# NetBox web: Secure cookies and exact transport-peer trust

Status: implementation candidate, **not approved for deployment**. See the
isolated [evidence report](../testing/netbox-web-proxy-boundary-20261028.md)
before publication/merge or operational rollout. No operational
environment, IP, key or CA is embedded in this feature.

## Diagnosis and proposed diff

The netbox-docker 5.0.2 `netbox.granian` module wraps Django with proxy-header
trust for broad private ranges. Changing Django alone does not replace that
upstream trust decision. The opt-in feature mounts a replacement WSGI entry
module on the web service only, before any proxy rewriting. It uses Granian's
transport `REMOTE_ADDR`, never XFF, to match explicitly configured IPs.

- `netbox_secure_cookies`: existing opt-in, sets only session/CSRF Secure flags.
- `netbox_proxy_boundary_enabled`: new opt-in, default false.
- `netbox_proxy_trusted_peers`: exact address list; no CIDRs, DNS, wildcard,
  scoped, unspecified or multicast addresses. IPv4-mapped IPv6 is normalized.
- The web entry module disables independent Django X-Forwarded interpretation
  after Django initializes. NetBox 4.6.10 hard-codes these settings; adding
  constants to configuration.py does not override them.
  The boundary sets `wsgi.url_scheme` after validation and removes forwarded
  fields before calling Django. Host must agree with forwarded Host; Django
  still applies ALLOWED_HOSTS. No change to CSRF_TRUSTED_ORIGINS.
- Cookie HttpOnly/SameSite, environment, shared MEDIA_ROOT/mounts, plugins,
  images, worker/housekeeping/sync and persistent volumes are not rewritten.
- Guards reject incomplete opt-in, unsafe peers/origins, installed protection
  removal, conflicting mounts and silent changes to installed peer sets.

Illustrative inventory, not deployment-ready addresses:

```yaml
netbox_secure_cookies: true
netbox_proxy_boundary_enabled: true
netbox_proxy_trusted_peers:
  - 192.0.2.10
netbox_allowed_hosts:
  - inventory.example.test
netbox_csrf_trusted_origins:
  - https://inventory.example.test
```

Determine the **actual source IP** that reaches web in each access path. Ensure
it is stable and isolated from untrusted workloads. An IP allowlist is not
cryptographic proxy authentication: another workload able to impersonate that
peer is inside the trust boundary. Do not broaden a CIDR to solve IP churn.

## Request policy and limitations

Untrusted peers: remove X-Forwarded-*, Forwarded, X-Real-IP, scheme, original
host/URL and rewrite fields. They cannot turn an HTTP request into HTTPS.
Host remains subject to Django validation. Direct HTTP healthchecks with an
allowed Host and no credentials remain available; no global redirect is added.

Trusted peers: forwarded context must have single-valued X-Forwarded-Proto
(http/https) and X-Forwarded-Host, with Host agreement. If supplied, forwarded
port must agree with authority/scheme and XFF must be a single valid IP.
Malformed/empty/control/whitespace/list values and RFC Forwarded combinations
are rejected with 400. Chained proxies and comma-delimited XFF are deliberately
unsupported. The proxy must replace/sanitize client forwarding fields rather
than append a client-controlled chain. Verify actual behavior in isolation.

**Audit IP:** REMOTE_ADDR is preserved. NetBox audit and plugins see the proxy's
transport address for proxied requests, not the original browser's claimed IP.
Plugins depending on XFF/client-IP headers must be reviewed. Original client
attribution belongs in trusted proxy logs, correlated without session secrets.

WSGI presents normalized headers, not original wire bytes. Repeated raw Host
and forwarding-header requests must be tested against the exact Granian binary:
do not claim wire-level duplicate rejection solely from unit tests. Static/media
files handled directly by Granian do not pass through the Django boundary;
the wrapper does not make otherwise public media private. Maintain appropriate
proxy/Django access controls and test uploaded files explicitly.
The isolated binary returned 200 for existing static/media files with an invalid
Host on the backend, while Django rejected login with 400 and the HTTPS proxy
returned 404. Do not expose the backend or assume ALLOWED_HOSTS filters files.

Secure cookies require HTTPS in browsers (direct and SSH tunnel). Raw HTTP is
for credential-free healthchecks, not a supported browser login fallback.
Certificate/name validation must stay enabled. No new ports are published.

## Reviewed web-only application sequence (do not run yet)

1. Confirm exact immutable web image ID and versions (NetBox 4.6.10,
   netbox-docker 5.0.2, Topology Views 4.5.1, QR Code 0.0.21). Obtain an image
   digest attestation from the target owner; do not assume matching tags mean
   matching binaries. No access to an excluded environment is required.
2. Present semantic Compose diff and inspect current proxy peer, headers,
   cookies, origins, env/MEDIA_ROOT, web/worker/housekeeping/sync and media.
3. Confirm snapshot completion and verified private configuration/media backups
   **after the MEDIA_ROOT fix**. Record existing image IDs, mounts and container
   IDs. Backup Compose, env, cookie/proxy overrides, versions and permissions.
   Backups may contain secrets and must never enter Git.
4. Use `playbooks/netbox-web-security.yml` with reviewed inventory, explicit
   `netbox_web_security_change_approved: true`,
   `netbox_web_security_backup_confirmed: true`, and
   `netbox_web_security_expected_image_id: sha256:<verified-image-id>`.
   These acknowledgements do not create or verify backups themselves.
5. The targeted path reads current installed Compose, adds only web security
   mounts/environment, validates a candidate, saves a Compose backup and
   recreates **netbox only**, no dependencies/build/pull. It performs no
   migrations, DB restore or worker/housekeeping/sync restart. It requires the
   corrected shared MEDIA_ROOT in env and checks that the image tag still
   resolves to the approved ID. Preserve all existing worker-specific settings.
   It runs collectstatic for enabled plugins after web recreation, and also
   checks it on repeat runs (zero changes when assets already exist).
6. Validate the complete matrix. Repeat application: zero changes/no recreation
   expected. Then review results before any other environment's rollout.

Do not use the full `playbooks/netbox.yml` for a security-only change: its normal
role includes deployment/migrations and broader validations. The default-off
legacy rendering remains unchanged; the dedicated path avoids those actions.

## Acceptance matrix and current evidence

| Check | Current state |
|---|---|
| Exact peers, mapped IPv6, untrusted spoof stripping, malformed context | Unit tests passed |
| Unsafe/incomplete inventory, installed-policy preservation | Unit tests passed |
| Web-only patch, media/mounts, other services, deterministic repeat | Unit tests passed |
| YAML parsing and Jinja default-off byte equality against baseline HEAD | Passed locally; real execution checked separately below |
| Pinned image + plugin versions + Granian entry-module loading | Passed; target custom-image attestation still required |
| Ansible syntax, real Jinja/Compose, positive/negative guards, idempotence | Passed; repeat changed=0 |
| HTTPS login/navigation/session; valid CSRF; missing/wrong token/foreign origin | Passed |
| Raw spoofed/duplicate headers and invalid Host | Passed for WSGI; static/media limitation above |
| Session/token APIs, plugin pages/static assets, upload/media persistence | Passed, including a real SSH tunnel |
| Worker, native housekeeping, PR #89 sync with VM sync disabled | Passed; sync uses an in-memory Zabbix API substitute |
| Rollback + reapply without MEDIA_ROOT/data regression | Passed, configuration-only rollback |

Local unit evidence: `python -m unittest discover -s scripts/tests -p 'test_*.py'`
passed 37 tests (13 specific to this boundary), using fixtures only, no live
Zabbix/GLPI API and no ticket creation. Unit mocks must not be presented as
successful integration with the exact image. CI runs the new boundary tests.

## Rollback, preserving post-MEDIA_ROOT state

Use the saved **post-MEDIA_ROOT** Compose/configuration, not an old baseline,
database dump or full snapshot revert. Restore only web's prior cookie/proxy
files and Compose; keep the corrected env and media mounts unchanged. Before
recreation, compare all non-web services, volumes and MEDIA_ROOT to the approved
state; run Compose config validation. Recreate web only with no dependencies,
no build and no pull. Never run down -v, prune, schema rollback or DB restore.

Installed-policy guards intentionally refuse silently disabling this feature.
Rollback is an explicitly reviewed manual restoration of saved files. Archive
the boundary marker outside the project only as part of that authorized
rollback; do not simply set the feature false to bypass guards. Preserve older
Secure cookies if they were already installed before this change. Confirm
health, both HTTPS access paths, login/CSRF, APIs, worker/media persistence and
image/mount identities again. A later reapplication needs the same review and
acceptance checks. No production rollout or merge is authorized by test success
alone in this runbook.
