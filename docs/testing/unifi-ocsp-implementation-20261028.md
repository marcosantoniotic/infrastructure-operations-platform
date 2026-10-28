# UniFi connection-bound OCSP candidate — 2026-10-28

Status: implemented and exercised in isolation; submitted for source review.
No operational deployment, OPS/LAB01 access, real certificate issuance or
controller/CA change. Original working tree changes remain untouched. The custom
runtime image remains local and unpublished; this PR is not rollout approval.

## PR #91 review follow-up (2026-10-28)

The first candidate's CI found root Dockerfile execution and an image inventory
parser consuming the next YAML key after an empty optional image. Both are
corrected: fixed non-root identity with private read-only credential copy and
explicit empty-vs-block-scalar parsing, with malformed-block rejection tests.
Confirmed-revocation journal writes now also fsync the Linux parent directory.
Fault-injection tests cover file sync, atomic replace and directory sync errors;
these simulate errors, not a physical power-cut experiment.

The new CI acceptance job builds the patched runtime plus a fixture-only image,
asserts non-root identity, compares packaged Python sources to the checkout and
runs both real collectors against local fictitious TLS/OCSP services. Runtime
acceptance has network=none, read-only root, dropped capabilities and bounded
resources. It neither publishes the image nor contacts operational controllers.
Previously recorded image/source hashes below describe the initial candidate,
not the revised non-root image. Final CI results must be checked at the PR head.
The PR remains draft; all release/rollout limitations below continue to apply.

Follow-up validation results:

- Windows unittest discovery: 59 tests, 58 passed and 1 explicitly skipped
  (the Linux directory-fsync test). No cryptographic fixture tests skipped.
- Linux CI: the four durability tests (including directory fsync ordering and
  failure injection), six guard tests and 54 actual collector cases passed.
  This CI builds and runs the non-root candidate; it is no longer only fixture
  generation or pure-function guards. The pre-existing GLPI HTTPS CI also passed
  on the first correction commit.
- Disposable Linux VM independently repeated the same 54 collector cases.
  Real Ansible/Compose checked both running UIDs=10001 and original secret
  owner=root/mode=0600. Final repeated apply: ok=41, changed=0, failed=0.
- Configuration-only rollback again recovered transient failure, retained both
  journals and refused subsequent GOOD for the confirmed-revoked leaf. A
  different pre-generated fictitious leaf recovered collection without clearing
  either deny history. Collectors/emulators were stopped after acceptance.
- Test harness issues (metrics-mode reset and root-owned responder control file)
  were fixed in the fixture, not by relaxing runtime security. The rollback
  fixture preserves journal ownership during its test-only GOOD-cache eviction.
- Independently built revised local runtime image:
  `sha256:26d272e98365351e9aee912ebd224b1bc68a6686b8cf3ed260d8492d7a477901`,
  user `10001:10001`; image is still unpublished. Revised Linux verifier SHA-256:
  `d7189f4fd0dee9319f4e5790bdd90cdc9ec1ca614ef16d4f8354b981ddc7af8e`.

CI status is commit-specific: consult the PR head before approval. Image scans
are reporting jobs, not a claim that no vulnerabilities exist. No operational
controller, OPS or LAB01 was accessed during these corrections.

## Version and implementation evidence

- Project base: dcfb850c0ec94fecd32095a2f6a96ecfd10c3b9d.
- UnPoller v3.4.1 source d9f4fcbe2c41841a0dd0d0591b98a4a4c4a71c70.
- unifi/v5 v5.30.0 source ef31b28fd458d777066533990054b6d7fea95043.
- Rebuild uses a normalized source checksum and exact discovery/auth anchors.
- Go 1.27.3; Python 3.13.12/cryptography 50.0.2 in the Linux image. Windows
  fixture/unit runtime: Python 3.12.14. asn1crypto 1.5.1 is TEST-ONLY.
- Final tested runtime image (local, not pushed):
  `sha256:089fc6bf23139f28467d591a97c3c83eb40d3b44f7023ca13342bc58b86dee11`.
- Packaged verifier SHA-256:
  `4063ed288ed01508d0f723630a9c0e44e64a3ba135b854b18c845315caca4cf0`.
- Packaged AP collector SHA-256:
  `55b69796e125296a151f38f0418d1f91b44833d3c48becd573d18719d5155125`.
- Linux UnPoller executable SHA-256:
  `3c8c5079eb38341520ab103b835220fd906972b8c0acf6d776d1eaa66b5cbaa7`.
- Earlier builds and failed fixture attempts are retained in private logs; the
  final successful results, not the earlier partial runs, are summarized below.

UnPoller performs normal TLS before the OCSP connection callback; both discovery
and authentication use it. It invokes a common local verifier using only leaf
DER, never credentials. AP counts invokes that verifier directly after verified
TLS and before HTTP. No timer substitutes for either enforcement path.

## Tests and evidence boundaries

### Real loopback integration

**54 cases passed** in the actual custom Linux image. The test image adds only
the fixture-generation dependency; UnPoller binary and runtime code are the same.
The container used network=none, read-only root, dropped capabilities, memory/CPU
limits and only private fictitious fixture mounts. Controller and responder are
local emulators with real TLS/HTTP, certificates, signatures and sockets.

Both collectors exercised:

- GOOD and authorized delegated GOOD allow authentication and data reads.
- REVOKED, UNKNOWN, bad signature, unauthorized responder, wrong serial/issuer,
  expired/future/incoherent timestamps and missing nextUpdate block before ANY
  controller application request (including discovery) is observed.
- Malformed/oversized response, HTTP error, redirect and timeout block.
- Wrong CA/name retain native TLS rejection; TLS failure metrics are checked.
- Valid cache survives responder failure; expired cache blocks application bytes.
- Actual leaf rotation rejects the prior leaf's cached/returned status; matching
  new status recovers collection. Repeated calls keep cached bytes/deny state.
- Server supports persistent HTTP: observed successful requests use distinct
  connections with no resumed TLS sessions. Protected pooling/resumption is not
  a supported mode, rather than an untested feature assumed safe.
- Confirmed revocation survives process restarts and subsequent GOOD responses.

UnPoller cloud/remote mode is explicitly rejected before its network request.
A real Prometheus scrape exposes the fictitious site's topology metrics.
Python returns AP users/guests counts from the fictitious controller.
OCSP request capture confirms absence of Authorization and Cookie credentials.
No controller writes other than authentication are permitted by the emulator.

These are REAL collector/transport integrations against EMULATED services, not
validation against a real UniFi firmware. The Python harness supplies explicit
synthetic configuration; its Docker-inspect fallback is stubbed but not used by
protected mode. No TLS socket, OCSP signature/parser or Go transport is mocked.

### Unit/fixture tests

51 Python tests passed with the explicit fixture environment: 37 pre-existing,
9 cryptographic-fixture/TLS controls and 5 inventory/Compose guard tests. Without
that environment the 9 fixture tests intentionally skip; do not count skips as
passed cryptographic tests. Inventory/Compose tests are pure functions, not
live integration evidence.

Upstream Go suite was also attempted. Two tests assert the English phrase
"connection refused" and fail on localized Windows socket error text. The same
two failures were reproduced in an UNPATCHED v5.30.0 worktree. They were not
silently marked passed or corrected in third-party source. Other packages ran;
the full upstream suite is therefore not claimed green on Windows.

### Real Ansible/Compose fixture

The targeted playbook ran only on the disposable Linux test VM and fictitious
collector Compose project. Real Compose validation, image enforcement label,
immutable image selection, issuer/account guards, private trust/configuration,
persistent journal mounts and both services were exercised. A repeated apply
reported changed=0; no configuration/state reinitialization was performed.
Default-off legacy Compose template itself is unchanged from project HEAD.
The real full-provisioning preservation guard was also exercised with opt-in
set false: expected refusal, changed=0, failed=0, rescued=1. It did not run the
remaining provisioning tasks or restart a collector.

Protected configuration rollback recovered collection after responder outage.
Confirmed revocation was then recorded independently in both journals; protected
Compose restoration and subsequent GOOD did not unblock the same certificate.
No database restore, volume deletion, stock-image rollback or deny reset was used.
Both revoked fixture collectors were stopped, preserving state/backups.

During fixture development a missing environment-only startup config and test
file ownership/wait timing were corrected. Those attempts are not successful
acceptance evidence; private logs retain them. No operational permissions or
services were changed to work around test failures.

## Review gates and limitations

Read the [runbook](../runbooks/unifi-connection-ocsp.md) for variables, bounds,
metrics, snapshot/backup planning and safe rollback. Before image publication/rollout:

1. Review the custom dependency patch and local verifier execution boundary.
2. Pin release base-image digests, finish redistribution notices and attest the
   immutable operational image. Build tags/labels are not provenance guarantees.
3. Measure load from fresh TLS and Python startup on expected controller scale.
4. Confirm the issuer/responder profile. Leaf OCSP does not recursively check
   issuer or delegated-responder revocation; non-RSA fixture coverage is pending.
5. Reconcile any existing auxiliary service, timer and private overrides without
   overwriting them. The dedicated role refuses incompatible AP service settings,
   unknown image swaps and issuer changes; full provisioning refuses installed OCSP.
6. Review off-host deny-history persistence and disaster recovery. The tested
   rollback is CONFIGURATION-ONLY; it is not permission to revert an entire VM
   snapshot and thereby erase newer revocation knowledge.
7. Monitor last-check timestamps and actual scrape health, not only a historical
   OCSP success gauge. No DNS/AIA auto-discovery or automatic CRL fallback exists.

No claim of compatibility with real controller firmware, network scale, operational
images, controller accounts or existing OPS-specific automation is made here.
Those require a separately authorized review; none was accessed in this task.

Final private evidence archive was copied to the protected isolated destination
and source/copy SHA-256 matched:
`b7b3b0db897a6bbc1141945ed6ddf661afe54916b87dc010fca88a3388ede7ed`.
Fictitious private keys, generated configuration/state and raw logs remain
outside Git. All OCSP acceptance collectors/emulators were left stopped; journals
and protected rollback copies were preserved.
