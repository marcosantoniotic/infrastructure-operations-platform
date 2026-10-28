# NetBox exact-peer boundary: isolated evidence, 2026-10-28

Status: implementation candidate for PR review, not deployed or approved for rollout.
Base revision: `b1920769b14f1ef1648893d151b244bb2993fa4a` (PR #89).
No LAB01 or OPS connection, configuration, data, credentials or CA was used.
Unrelated local PNG files are excluded from this change and preserved locally.
Publication for review does not authorize merge or operational deployment.

## Test environment and image

Disposable RHEL 9.8 VM, 4 CPUs/8 GiB, NAT only, separate synthetic database,
credentials, CA, certificates and Docker volumes. SSH bootstrap uses its own
key and a loopback-only Vagrant forward. The accidentally passphrase-protected
test key was corrected without changing global SSH or operational credentials.

NetBox `4.6.10-Docker-5.0.2`, Topology Views `4.5.1`, QR Code `0.0.21`.
Base `netboxcommunity/netbox:v4.6.10-5.0.2` image identity:
`sha256:91b823a05cb51004f07acc2228ccc2993f38b0f0bf711b403b0fdf85e51277e8`.
Locally built plugin image identity:
`sha256:030f777115f93a66016714418556a84cad64d66fe7fb997acd8f219020f52c49`.
These attest to the disposable images, not binary equality with an excluded
environment's custom image. Obtain that attestation from its owner before rollout.

The unregistered base had no RPM repositories. Official static Docker 29.0.0,
Compose 2.40.3 and buildx 0.30.1 were used for testing; published asset checksums
were checked. SELinux remained enforcing. This does not validate the RPM engine
installation role or an operational SELinux/container-selinux policy.
See [Docker's static binary guidance](https://docs.docker.com/engine/install/binaries/).

## Proposed changes and findings

- Opt-in exact-peer web entry wrapper, read-only mount, strict header context
  validation, mapped-IPv6 comparison and forwarding-header removal for outsiders.
- NetBox 4.6.10 hard-codes proxy settings. The wrapper overrides those effective
  values after Django initialization, only in the web process. An earlier
  configuration-file-only approach was detected by a runtime assertion and removed.
- Existing Secure-cookie override preserves HttpOnly, SameSite and CSRF origins.
- Installed-policy guards and a dedicated web-only playbook retain images,
  environment, corrected MEDIA_ROOT, ports, networks and non-web services.
- collectstatic repairs plugin assets after recreation; subsequent runs copy zero.

## Executed results

| Test | Result |
|---|---|
| Python suite | 37 passed, including 13 boundary tests |
| Default-off template | Byte-identical legacy render against baseline |
| Ansible syntax, rendered Compose, real apply | Passed |
| Unsafe CIDR, missing cookies, absent backup approval, wrong image | Refused |
| Installed-policy disable and peer change | Refused |
| Effective web settings after initialization | Secure cookies true; independent Django forwarded-header trust disabled |
| Real HTTPS login, navigation, existing session | Passed |
| CSRF correct / missing / wrong / foreign origin | Accepted / rejected / rejected / rejected |
| Session and v2-token API | Passed |
| Exact transport peer and mapped IPv6 | Passed; raw peer retained |
| Raw duplicate/malformed trusted context | Nine rejection cases passed |
| Outsider spoof and invalid Django Host | Cannot establish trusted HTTPS context; invalid Host rejected |
| HTTP health without credentials | Passed, no global redirect |
| Bad CA / wrong certificate hostname | Both TLS failures as required |
| Topology page/static and QR rendered image | Passed |
| Real API media upload, HTTPS fetch and persistence | Passed, hash unchanged across rollback/recreation |
| Actual SSH tunnel, alternate public port, strict TLS/SNI | Login, CSRF and session API passed; only own temporary forward closed |
| Worker IDs/mounts/images, MEDIA_ROOT, environment | Preserved; worker not restarted; env byte-identical |
| Native SystemHousekeepingJob through worker | Completed |
| PR #89 sync with VMs disabled | Real ORM/source, synthetic device+VM; in-memory Zabbix API, no tickets or live Zabbix/GLPI calls |
| Configuration rollback and reapply | Passed, existing session/token, rows and volume identities preserved |
| Repeat targeted playbook | changed=0, unreachable=0, failed=0 |
| Additional application host ports | Zero; existing loopback backend publication unchanged |

The final boundary revision was reapplied and tested again after correcting the
hard-coded Django settings issue. Non-web preservation and native housekeeping
were rechecked afterward. Wire-parser tests and the synchronizer test used the
same boundary-class logic and unchanged synchronizer source, respectively.

## Limits and review gates

1. Existing static/media files served directly by Granian returned 200 for an
   invalid backend Host. Django login returned 400; the HTTPS proxy returned 404.
   This wrapper is not a global static-file Host filter. Restrict backend access;
   do not assume public media becomes private.
2. Audit/plugins see the real socket peer (often `::ffff:<proxy-ip>`), not a
   claimed browser IP. Review IP-dependent plugins and correlate proxy logs.
3. The trusted proxy must overwrite, not append, caller-supplied context. No
   comma-separated proxy chains; IP impersonation inside the trusted network
   remains outside this protection's guarantees.
4. No live integration or operational-image equality is claimed. Operator image
   attestation and environment-specific peer/header review remain required.
5. No snapshot of operational VMs was needed or taken: tests used a disposable
   fixture. Before any real deployment require completed snapshots and verified
   post-MEDIA_ROOT configuration/media backups, not only acknowledgement booleans.

## Application impact and rollback proposal (not executed operationally)

Follow the [runbook](../runbooks/netbox-web-proxy-boundary.md). Review inventory
and semantic diff, attest the image, confirm snapshots/backups, then recreate
only web without dependencies/build/pull. Expect a brief web interruption; do
not run full provisioning, migrations, DB restoration or volume deletion.

Rollback restores the approved post-MEDIA_ROOT Compose and prior web override
files, validates Compose and recreates only web, collecting plugin static assets.
Keep the corrected environment/media mounts and all database state. Archive
boundary marker files explicitly; disabling inventory alone must fail the guard.
Repeat both HTTPS access paths, CSRF/API, worker/media and image/mount checks.

Private evidence was archived outside Git on the protected test destination;
source and copied archive SHA-256 matched:
`ebf6ff9a7f7f61f1077334e77a9be74a68edfff76f68455a6580e1b0b8c94613`.
Logs, test sessions, private keys and configuration backups are not publication assets.
