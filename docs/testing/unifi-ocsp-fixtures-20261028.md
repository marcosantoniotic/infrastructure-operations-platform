# UniFi OCSP fixture preparation — 2026-10-28

Status: prerequisites located/generated; collector OCSP implementation and
end-to-end validation remain PENDING. No deployment or publication performed.

Historical prerequisite-stage report. Implementation has since advanced; see
the [current implementation evidence](unifi-ocsp-implementation-20261028.md).

## Source recovered locally

The auxiliary collector was found in local source copies, not retrieved from
an operational host. Two source copies matched SHA-256:
`9bbe870f6fb4d6bf2ad72f14c0edc50353715ee0dfa4bc5975e045b2eb57dffa`.
The isolated copy is `roles/observability/files/unifi-ap-counts.py` and retains
the original bytes. No runtime secret, controller address, CA or inventory was
copied. Do not run its main entrypoint: it invokes Docker inspection and reads
configured credentials; neither action was used for these tests.

The script has only standard-library imports. It uses an explicit destination,
verified hostname/SNI, a custom HTTPSConnection, cookie handler and constrained
redirect handler. It does not currently implement OCSP. Its external executables
and runtime configuration still need controlled substitutes in integration tests.

## Generated test-only material

Generator: `scripts/ci/create-unifi-ocsp-fixtures.py`.
Dependencies: `scripts/ci/requirements-unifi-ocsp-tests.txt`, installed into the
isolated `.validation/ocsp-python` virtual environment, not system Python.
Tested Python 3.12.14, cryptography 50.0.2 and asn1crypto 1.5.1.

The final fixture set is under `.validation/ocsp-private/run-20261028-profile2`.
The private parent has inheritance disabled and access for the creating user
and SYSTEM only. Keys/responses/manifests remain ignored by Git. The generator
refuses an existing destination or a directory outside that private parent.
The private manifest includes SHA-256 checksums; it is not a publication asset.

Six test certificates: test root, unrelated test root, controller leaf, rotated
leaf, authorized OCSP delegate, and an unauthorized responder. The CA profile
has critical CA BasicConstraints, certificate/CRL signing KeyUsage, SKI and AKI.
Certificates are valid for seven days and only use fictitious identities.
No CA was added to Windows or any operational trust store.

Seventeen DER response vectors: issuer-signed GOOD, delegated GOOD, REVOKED,
UNKNOWN, unauthorized responder, wrong serial, rotated leaf GOOD, wrong issuer
hashes, expired, future thisUpdate, future producedAt, old producedAt,
incoherent producedAt, missing nextUpdate, nextUpdate before thisUpdate,
corrupted signature, and malformed body.

For the producedAt cases, the fixture generator re-signs the modified response
using the test key. Independent signature verification confirms these controls
have valid signatures; they do not fake a parsed timestamp or accidentally
exercise only signature failure.

## Commands

From the isolated worktree (PowerShell):

```powershell
# Use a fresh destination; do not overwrite or regenerate an existing fixture set.
./.validation/ocsp-python/Scripts/python.exe scripts/ci/create-unifi-ocsp-fixtures.py --destination .validation/ocsp-private/run-20261028-profile2
$env:IOP_OCSP_FIXTURE_DIR=(Resolve-Path .validation/ocsp-private/run-20261028-profile2).Path
./.validation/ocsp-python/Scripts/python.exe scripts/tests/test_unifi_ocsp_fixtures.py -v
```

Result: **9 tests passed**. These check manifest integrity, certificate profiles
and signatures, status/identity vectors, authorized versus unauthorized EKU,
signature corruption/malformed bytes, and cryptographically signed time vectors.

Three of the tests exercise REAL TLS using ephemeral loopback sockets and
SSLContext with explicit test trust: initial/rotated leaf acceptance, wrong CA
rejection and wrong hostname rejection. Only an unauthenticated fictitious GET
is sent; no operational services or authenticated collector requests are used.

## Evidence boundaries and remaining work

These are fixture/self-checks plus real loopback TLS controls. They are NOT
tests of a deployed OCSP verifier, not successful UniFi collection, not tests
of UnPoller discovery or authentication, and not proof of blocking credentials.
No GOOD vector has enabled an operational collection.

Both collector connection implementations, constrained OCSP networking,
authorization/time/identity validation, bounded cache, persistent confirmed
revocation journal, sanitized metrics/logs, opt-in automation and preservation
guards remain pending. So do real collector integration, timeout/DNS/HTTP
controls, connection reuse/resumption, idempotence and coordinated rollback.
No image digest or complete integration result is claimed at this stage.

No OPS/LAB01 host was accessed, no controller was changed, and original local
source copies and unrelated project changes were preserved.
