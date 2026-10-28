# UniFi connection-bound OCSP: proposed design and implementation gates

Status: initial design retained for history. A candidate is now implemented and
tested in isolation; see [implementation evidence](../testing/unifi-ocsp-implementation-20261028.md)
and the [current runbook](../runbooks/unifi-connection-ocsp.md). Not approved for deployment.
Base: dcfb850c0ec94fecd32095a2f6a96ecfd10c3b9d. Work occurs in a separate
Git worktree; no OPS/LAB01 access, production parameters, CA or data used.
Only fictitious test certificates have been issued under subsequent explicit
authorization. No operational CA was installed/replaced and no controller was
contacted or changed.

## Source inventory and blocking inputs

The public project contains the UnPoller Compose service, pinned to
`ghcr.io/unpoller/unpoller:v3.4.1`. Its upstream go.mod requires
`github.com/unpoller/unifi/v5 v5.30.0`.
There was no `unifi-ap-counts` implementation in the baseline revision. Under
subsequent authorization to inspect local copies, a generic script was found
in two matching local source trees and copied without executing it or reading
operational configuration. Source SHA-256:
`9bbe870f6fb4d6bf2ad72f14c0edc50353715ee0dfa4bc5975e045b2eb57dffa`.
The original used standard-library HTTPSConnection, CookieJar and urllib, explicitly
connects to a configured address with a configured hostname/SNI, and disables
environment proxies. Credentials come from configuration/runtime, not source.
The original explicitly stated that CRL/OCSP was not enforced. The candidate
now adds connection enforcement and a dedicated coordinated Ansible path; no
operational deployment has occurred. Do not retrieve operational configuration.

The upstream Go library constructs independent HTTP transports in `newUnifi`
and `checkNewStyleAPI`, before `Login`. A post-login hook or replacement of only
the authenticated client is insufficient. The optional SSLCert path also
replaces the transport and uses pinning; reject that mode when OCSP is enabled.
Do not replace ordinary chain/name verification with this path.

Primary source references:
- https://github.com/unpoller/unpoller/blob/v3.4.1/go.mod
- https://github.com/unpoller/unifi/blob/v5.30.0/unifi.go
- https://www.rfc-editor.org/rfc/rfc6960

## Proposed enforcement

Patch/rebuild the collectors; a timer, sidecar precheck or a Compose environment
variable unsupported by the binaries is not enforcement. No TLS-intercepting
proxy, additional listening ports or controller modification is proposed.

For the Go implementation, use one reviewed transport factory for every client,
including discovery. Ordinary TLS chain/name verification stays enabled.
Only after that succeeds, evaluate OCSP in the TLS connection verification
path, before returning the connection to HTTP. Do not install enforcement after
NewUnifi, which already performs discovery and login.

An initial implementation should deliberately disable HTTP connection pooling,
HTTP/2 and TLS session resumption for protected controller clients, so every
request uses a fresh verified connection. Explicit tests must prove that these
features cannot be re-enabled silently. Supporting persistent connections later
requires rechecking freshness/revocation before each authenticated write on the
same socket, not merely on its original handshake. Performance impact requires
measurement; do not claim pooling support without that gate.

Python must implement the equivalent lifecycle in its actual HTTP stack, after
normal verified handshake but before authenticated application bytes. Its
implementation must preserve the reviewed standard-library transport. Reject cross-origin redirects and
unprotected HTTP fallbacks, including redirect paths during discovery/login.
Auth credentials, cookies and API tokens never enter OCSP requests.

## OCSP acceptance policy proposal

- Bind status to leaf DER, verified issuer DER, serial and OCSP CertID hashes.
  Hashes are cache identities, NOT certificate pinning or trust substitutes.
- Require successful OCSP envelope, unambiguous matching SingleResponse,
  supported signature algorithm, valid response signature and ResponderID.
- Permit the verified issuer itself, or a directly issuer-authorized delegated
  responder with OCSP-signing EKU, appropriate key usage and valid certificate.
  An embedded response certificate alone does not establish authorization.
- Strictly validate issuer name/key hashes against the actual verified issuer;
  do not compare formatted DN strings or trust response-supplied issuer identity.
- Require GOOD. REVOKED and UNKNOWN block collection. Malformed and
  unauthorized responses cannot populate a GOOD cache.
- Proposed bounds, all explicit and guarded: clock skew 120 seconds; response
  maximum age 1 hour; request timeout 5 seconds; response maximum 64 KiB;
  cache maximum 128 entries; no redirects. These are design candidates, not
  operational defaults already applied.
- Require thisUpdate, producedAt and nextUpdate, timezone-aware. Reject future
  thisUpdate/producedAt beyond skew, nextUpdate <= thisUpdate, nextUpdate
  preceding producedAt beyond skew, missing times and stale responses.
  No grace period after nextUpdate. Never accept past leaf/issuer validity.
  A small ordering skew allowance between producedAt and thisUpdate must be
  specified and tested, not implicitly inferred from the local clock.
- Cache deadline is the minimum of nextUpdate, local receipt plus cache TTL,
  maximum status age and certificate validity. A clock rollback invalidates
  cache, rather than extending its life. Cache misses fail closed.
- A cryptographically confirmed REVOKED result evicts GOOD state and writes a
  persistent deny record keyed to leaf+issuer identity. Protect the journal from
  deletion/downgrade. Keep it across collector rollback and process restarts.
  Do not treat attacker-supplied unsigned REVOKED as confirmed revocation.

Whether intermediate certificates also require OCSP must be resolved explicitly:
do not claim whole-chain revocation checking from a leaf-only implementation.
The baseline requirement is status of the actual controller leaf and verified
issuer; no automatic CRL fetching or chain-wide AIA crawling.

## Network and resource limits

Use explicit inventory allowlists of OCSP endpoints and destination addresses,
with no wildcard hostnames or arbitrary certificate-driven AIA fetches. Treat
AIA as untrusted input. Resolve and validate all addresses, then connect to an
approved resolved address without a second uncontrolled DNS resolution. For
HTTPS responders retain original hostname/SNI and normal certificate checks.
Disable environment proxies and redirects on the OCSP client. Bound total
response bytes, header sizes, DNS/network timeouts and concurrent requests.
No credentials, URL userinfo, cookies or collector session headers are allowed.
OCSP HTTP can carry signed protocol responses without borrowing controller
credentials; responder transport does not replace signature validation.

## Automation, metrics and rollback gates

An eventual coordinated environment opt-in must require both verified collector
builds, image attestations, CA inputs and complete policy. Default-off legacy
render must remain identical. Installed policy marker and deny journal must
reject silent disable, missing journal, insecure verification modes or policy
weakening. Do not expose an enable flag before functional binaries exist.

Use bounded reason labels (tls, revoked, unknown, signature, responder,
identity, time, dns, timeout, http, malformed, cache_expired). Export counters
and last collection success; never label by serial, username, URL, token or
unbounded exception text. Logs contain fixed reason codes, not response bodies
or authentication material. Recovery must clear stale success indications.

Before OPS application: review exact images and changes; completed snapshots;
verified private configuration/journal backups; bounded scrape interruption;
coordinated collector-only replacement, no full provision. Preserve passwords,
networks, volumes, CA and other services. Validate read-only collection and
Prometheus after both replacements.

Rollback MUST NOT restart stock collectors against a confirmed-revoked
certificate. Keep the persistent deny journal and a previously validated
OCSP-capable image. If no safe prior build exists, leave both collectors stopped
and alert. Loss of telemetry is preferable to revocation bypass. Restoring an
old backup must not erase newer deny records. No automatic CA/CRL fallback.

## Required evidence (all pending)

Fixture integrity tests and collector loopback TLS/OCSP integrations have now run;
see [fixture evidence](../testing/unifi-ocsp-fixtures-20261028.md) and the separate
[implementation evidence](../testing/unifi-ocsp-implementation-20261028.md).
The remaining paragraphs are the original acceptance plan, not a current result.
Source inspection is not integration evidence.
Existing NetBox tests do not validate this feature.

Separate pure-parser/time/cache mocks from real cryptographic TLS integrations.
Fictitious test certificates/keys/responses have been generated under explicit
authorization, exclusively in the ignored isolated directory. Operational
certificate issuance remains prohibited. Fixtures support
GOOD, REVOKED, UNKNOWN, invalid signatures, unauthorized responders, wrong
serial/issuer, expired/future/incoherent times and certificate rotation.

For EACH actual collector binary, a disposable local controller emulator must
count authenticated bytes/requests and prove zero before acceptance; exercise
initial discovery, login, retry, reconnect, rotation and attempts at reuse and
resumption. Include bad CA/name, malformed/oversized responses, DNS/timeouts,
redirects, valid/expired caches, revocation persistence, scrape recovery and no
controller writes beyond the read-only authentication protocol. Test actual
metrics endpoints separately from status-validator unit tests.

Run Ansible syntax/render/positive-negative guards, Compose validation,
default-off equality, image/version attestation, idempotence and coordinated
rollback. Record exact commands, exit codes, image digests and limitations.
Do not publish private keys or raw credentials with the evidence.
