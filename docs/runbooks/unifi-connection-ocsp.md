# Coordinated UniFi OCSP: candidate operation and safe rollback

Status: isolated implementation candidate. NOT approved for publication or
operational rollout. See [evidence and limitations](../testing/unifi-ocsp-implementation-20261028.md).

## Enforcement design

UnPoller is rebuilt from upstream v3.4.1 commit
`d9f4fcbe2c41841a0dd0d0591b98a4a4c4a71c70`, with unifi/v5 v5.30.0 commit
`ef31b28fd458d777066533990054b6d7fea95043`. A checksum/anchor-checked build
patch installs the same protected transport in authenticated and initial
discovery clients. Remote/cloud API requests are explicitly refused in OCSP
mode. Pinning mode and VerifySSL=false are rejected before any connection.

Normal Go TLS chain/name verification runs before VerifyConnection. That hook
sends ONLY the presented leaf DER via stdin to the Python verifier inside the
same immutable image. No shell, credential argument, listener or TLS-intercepting
proxy is used. Native certificate failures also produce a sanitized TLS reason.
Go requires verified chains, disables tickets/resumption, rejects DidResume,
disables keepalive and HTTP/2, and refuses redirects. Every application request
therefore obtains a fresh verified connection. No precheck substitutes for this.

AP counts uses verified standard-library HTTPSConnection. After wrap_socket
and before HTTP bytes, it calls the same policy directly. Protected mode uses
explicit URL/user/configuration and a read-only password file; no Docker socket
or inspect privilege is granted. urllib closes connections; redirects are
refused in protected mode. The image can run it at a bounded 60-second interval.

The common verifier authenticates the issuer binding, CertID serial and issuer
hashes, response signature and responder authorization. Delegates must be
directly issued, currently valid and valid at producedAt, with OCSP-signing EKU
and digital-signature KeyUsage. RSA PKCS#1 and ECDSA SHA-2 are supported; other
signature profiles fail closed. Only single-response OCSP is accepted.

producedAt/thisUpdate allow at most 120 seconds future clock skew; ordering is
checked with that tolerance. nextUpdate is mandatory and never receives an
expiry grace period. Maximum response age is one hour. Cache expiry is bounded
by signed times, certificate/signer validity and a configured local TTL (maximum
300 seconds). Responses are revalidated on cache reads, even across processes.
Clock rollback fails closed. Leaf+issuer DER bind each cache identity.

Persistent, privately mounted state stores signed cached responses and confirmed
revocation identities. Atomic replacement and a persistent lock inode serialize
checks. GOOD entries are limited to 128; confirmed revocations are never evicted
to make room. A full deny journal fails closed. Missing/invalid state blocks.
Installed state is never automatically reinitialized. Issuer replacement is
refused after installation because it requires separate deny-history migration.

The OCSP client uses one explicit endpoint and numeric address from reviewed
inventory. It does not follow AIA, redirects, environment proxies or DNS-driven
destination changes. It sends no Cookie, Authorization or controller credentials.
POST responses must be HTTP 200, OCSP content type, at most 64 KiB; header size,
timeouts and concurrency are bounded. Native HTTPS verification also applies
when the responder URL is HTTPS. No automatic CRL fallback is present.

## Inventory and change boundaries

Defaults keep the feature off. Do NOT set only the opt-in flag on a stock image.
Use `playbooks/unifi-ocsp.yml` with an already tested immutable image reference
(repository@sha256 or a locally attested sha256 image ID). The image must carry
the connection-v1 capability label; that label is not a substitute for provenance
or acceptance tests. The role never builds or pulls an image during application.

Required reviewed fields:

```yaml
observability_unifi_ocsp_enabled: true
observability_unifi_ocsp_image: <TESTED_IMMUTABLE_IMAGE>
observability_unifi_ocsp_previous_image: <CURRENT_IMAGE_IF_UPGRADING_PROTECTION>
observability_unifi_ocsp_ca_certificate: <PUBLIC_TRUST_BUNDLE_ONLY>
observability_unifi_ocsp_issuer_certificate: <ACTUAL_PUBLIC_ISSUER_CERTIFICATE>
observability_unifi_ocsp_policy:
  controller_address: 192.0.2.10
  responder_url: http://ocsp.example.test/status
  responder_address: 192.0.2.20
  timeout_seconds: 5
  response_limit: 65536
  cache_entries: 128
  clock_skew_seconds: 120
  max_age_seconds: 3600
  cache_ttl_seconds: 300
observability_unifi_ocsp_change_approved: false
observability_unifi_ocsp_backup_confirmed: false
```

These are documentation-only identities, not operational parameters. Existing
URL, username and verified TLS must match the reviewed inventory. A pre-existing
auxiliary service with incompatible settings must be reconciled separately;
the role refuses replacing it silently. No controller account is created.

The playbook semantically patches only the two collector services. Image,
environment and read-only configuration/state mounts are coordinated; unrelated
services, network definitions and data volumes are retained. The AP collector
writes existing node-exporter textfile storage without publishing a port.
Policy/trust changes recreate both collectors together. A full observability
provision is refused after OCSP installation; it cannot erase the protection.

## Proposed operational sequence — approval still required

1. Obtain current runtime/image/configuration evidence in a separately authorized
   operational review. Do not import private parameters into the public project.
2. Reconcile local changes and reproduce tests with the exact proposed immutable
   image. Pin release base-image digests and review third-party license notices
   before any image publication. Do not assume a tag or capability label suffices.
3. Plan capacity: fresh connections plus a bounded local Python invocation per
   UnPoller connection add CPU and handshake work. A missed OCSP result is a
   failed scrape, not permission to use HTTP or disable verification.
4. Complete VM snapshots and protected off-host configuration/journal backups;
   verify copies and hashes. Approval flags neither create nor verify backups.
   Preserve journal updates made AFTER a snapshot or initial backup.
5. Review the collector-only Compose diff and apply only after explicit approval.
   No full provision, controller write, new port, CA replacement or CRL enablement.
6. Validate both data collectors, actual Prometheus/textfile metrics, TLS failures,
   cache behaviour and recovery. Repeat: configuration changes must be zero.

## Metrics and limits

`iop_unifi_ocsp_last_check_success`, bounded `...last_check_reason` gauges and
timestamp are emitted for unpoller/ap_counts. They report the LAST CHECK, not an
assertion that a newer scrape happened: monitor timestamp freshness as well.
Reasons distinguish TLS, revoked, unknown, identity/signature/responder/time,
timeout/unavailable/http/malformed, cache expiry and state/clock problems.
AP success=0 replaces previous data on failure. Error text is sanitized; no
response DER, usernames, credentials or arbitrary exception labels are logged.

The initial implementation deliberately does not support pooling, HTTP/2,
TLS resumption, cloud/remote mode or pinning. DNS is removed from OCSP routing;
hostnames without an explicit approved numeric destination cannot be enabled.
POST-only responders and supported signature profiles are required. This checks
the controller leaf's revocation, not recursive OCSP for intermediate/responder
certificates. Only RSA issuer/delegate fixtures were integration-tested here;
ECDSA support still requires its own release acceptance fixtures.

## Rollback — must retain revocation enforcement

Never roll back to stock UnPoller, the old unprotected Python script, disabled
OCSP flags, empty state, stale state backups, HTTP or relaxed TLS. If there is no
previous verified OCSP-capable image, STOP both collectors and alert instead.

For a configuration fault, restore only approved protected Compose/policy files,
keep the same issuer identity, preserve CURRENT journals/locks, validate Compose
and recreate only the collectors without build/pull/dependencies. No database
or volume restore/removal is involved. Do not overwrite newer confirmed denies
with snapshot-era files. Snapshot revert is not this tested rollback procedure;
disaster recovery needs external deny-history reconciliation before resuming.

A confirmed revoked certificate remains blocked even if a subsequent response
says GOOD. Recovery requires a separately authorized valid replacement leaf,
whose new identity is checked normally; never delete old denies to recover.
Test snapshots/backups remain private, outside Git. No operational rollout has
been performed or authorized by the isolated results.
