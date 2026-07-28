# Traefik role

Deploys Traefik as the platform ingress without mounting the Docker Socket in
the proxy container.

## Security model

- Docker discovery uses a dedicated Socket Proxy;
- the control network is internal and publishes no host port;
- Docker API mutations are denied;
- `exposedByDefault=false`;
- the dashboard uses the secure `api@internal` service;
- dashboard authentication and standard headers are applied as reusable file
  middlewares;
- Traefik and validation workloads run read-only with dropped capabilities;
- HTTP, HTTPS and metrics bindings are configurable independently.

## Standalone execution

```bash
ansible-playbook \
  -i inventories/validation/hosts.yml \
  playbooks/traefik.yml
```

Replace `traefik_dashboard_basic_auth` with an externally generated `htpasswd`
entry. Keep the plaintext credential in an approved password manager, never in
the repository.

The validation profile binds ports to loopback and uses an SSH tunnel. HTTPS,
certificate automation and Cloudflare integration are intentionally separate
promotion steps.
