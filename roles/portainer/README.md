# Portainer role

Deploys Portainer Community Edition LTS as an independent Docker Compose
project for operational visibility and controlled administration of the local
Docker Engine.

## Operating model

Ansible and the versioned Compose files remain the configuration source of
truth. Portainer is used for inventory, logs, health inspection and controlled
operational actions. Permanent platform changes must be returned to code.

## Security model

- the HTTP fallback binds to loopback by default;
- Traefik publication is opt-in and uses the shared security middleware;
- no Edge tunnel port is exposed;
- the administrator password is supplied from Ansible Vault through a
  read-only file;
- Portainer data is stored in a named volume;
- SELinux labeling is disabled only for this container because access to the
  host Docker socket is required;
- access to Portainer is equivalent to administrative access to Docker and
  must be protected by strong authentication and the external identity layer.

Portainer requires write-capable access to the Docker API to manage containers.
A read-only socket proxy would reduce the product to inventory-only behavior
and is therefore not used for this local management endpoint.

## Execution

```bash
ansible-playbook \
  -i inventories/validation/hosts.yml \
  playbooks/portainer.yml
```
