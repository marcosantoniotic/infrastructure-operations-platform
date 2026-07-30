# HTTP contract validation

## Purpose

The HTTP contract validates externally observable application behavior after a
deployment or maintenance window. It complements Prometheus Blackbox monitoring
with deterministic assertions for:

- accepted HTTP status codes, including `200` and authentication redirects;
- redirect destination patterns;
- TLS validation policy;
- required security headers;
- sanitized evidence without URLs, headers or response bodies.

## Validation environment

The public example targets the local validation routes:

```powershell
.\scripts\Test-HttpContract.ps1 `
  -ContractPath .\config\examples\http-contract.json `
  -EvidencePath .\.validation\http-contract-evidence.json
```

Self-signed validation certificates use `tls_insecure: true`. Production
contracts should validate the certificate chain and therefore set it to
`false`.

## Production use

Create an ignored file such as
`.validation/http-contract.production.json`. Use logical endpoint names and
real URLs only in that ignored file. For a Cloudflare Access route, keep
redirect following disabled, accept `302`, and assert a stable location pattern
without storing account identifiers in the repository.

Run the contract:

```powershell
.\scripts\Test-HttpContract.ps1 `
  -ContractPath .\.validation\http-contract.production.json `
  -EvidencePath .\.validation\evidence\http-contract.json
```

The evidence contains only endpoint names, observed status codes and boolean
check results. It deliberately omits URLs, redirect destinations, response
bodies and header values.

## Failure handling

1. identify whether the failure is DNS, TLS, proxy, identity or application;
2. validate the same route from the expected network boundary;
3. inspect Traefik and application health without publishing raw logs;
4. restore the previous known-good configuration when the change caused the
   failure;
5. retain only sanitized evidence.
