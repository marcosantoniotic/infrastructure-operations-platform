# Standby DNS bootstrap — local validation, 2026-11-28

The standby resolver was listening on UDP/TCP 53, but its HTTPS upstream could
not bootstrap: the original public bootstrap resolvers timed out and IPv6 was
unreachable. A successful exporter scrape did not mean a successful DNS probe.

The operator supplied read-only output from both directory DNS servers: public
forwarders, root hints enabled, and no conditional forwarders listed. There was
no forwarding path back to the standby in that evidence. Both internal resolvers
resolved the HTTPS upstream hostname from the standby before the change.

Only AdGuard bootstrap resolvers were changed, followed by a controlled restart
of AdGuard. HTTPS upstream, certificate validation, container image, credentials,
volumes, and filtering policy were preserved. Existing backup sets and OPS were
not changed. The original configuration was held in memory for immediate rollback;
no new backup generation was created.

Results: UDP and TCP queries from the platform returned NOERROR; the direct
blackbox DNS probe returned success; a later Prometheus sample showed all eight
probe_success series at 1 (seven HTTP, one DNS). This is functional validation,
not a sustained-availability or DNSSEC audit.

## Automation protection

The existing dns_standby role does not render or overwrite initialized
AdGuardHome.yaml. The new opt-in bootstrap guard checks its actual bootstrap list,
requires HTTPS upstreams, and rejects an explicit DNS TLS-verification bypass
before Compose deployment. On drift it fails closed rather than rewriting a live
AdGuard file, which AdGuard can overwrite while running.

The LAB01 wrapper reads the ignored private file
`.validation/dns-bootstrap-policy.json` (enabled=true, resolvers=array of IPv4
addresses), then emits the guard variables with its generated inventory. Actual
LAB01 addresses remain private. Keep this file: removing it disables the wrapper
opt-in. A direct Ansible invocation must explicitly supply
`dns_standby_bootstrap_guard: true` and
`dns_standby_expected_bootstrap_dns`; generic defaults remain unchanged.

This is protection for the corrected initialized deployment, not automatic
first-run initialization or automatic drift repair. Do not bypass a failed guard:
review the resolver chain, stop AdGuard, reconcile only the bootstrap list, and
restart with rollback available. Existing remote automation bundles are not
silently updated; the wrapper stages the current role and generated variables
when explicitly invoked. No deployment was run as part of this code change.

Tests: role/default YAML parsed; PowerShell parser reported zero errors; five
offline Ansible 2.14.18 expression cases passed (matching policy, mismatched
bootstrap, HTTP upstream, empty upstream, TLS bypass). No full role deployment,
Compose recreation, or deployment-idempotence claim is made. No push or PR.
