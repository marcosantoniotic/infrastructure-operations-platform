# Validation infrastructure automation

This layer reconstructs the validation environment from code without changing
the existing production virtual machines.

```text
RHEL DVD ISO
    |
    v
Packer + Kickstart
    |
    v
Local VMware Vagrant box
    |
    v
Vagrant + VMware Workstation
    |
    +-- AUTOMATION-CONTROLLER
    |
    `-- SRV01-VALIDATION
             |
             v
           Ansible
```

## Boundaries

- Packer creates the reusable RHEL base image.
- Kickstart performs the unattended operating system installation.
- Vagrant creates and manages the two validation VMs.
- Ansible configures the operating system and platform services.
- RHEL images and generated boxes remain local and are never published.
- Production VMs are outside the scope of every command in this directory.

See [validation environment](../docs/testing/validation-environment.md) for the
supervised execution procedure.
