INVENTORY ?= inventories/example/hosts.yml
LIMIT ?=
CHECK ?=

ANSIBLE_PLAYBOOK = ansible-playbook -i $(INVENTORY)
EXTRA = $(if $(LIMIT),--limit $(LIMIT),) $(if $(CHECK),--check --diff,)

.PHONY: requirements preflight bootstrap docker netbox platform validate

requirements:
	ansible-galaxy collection install -r requirements.yml

preflight:
	$(ANSIBLE_PLAYBOOK) playbooks/preflight.yml $(EXTRA)

bootstrap:
	$(ANSIBLE_PLAYBOOK) playbooks/bootstrap-rhel.yml $(EXTRA)

docker:
	$(ANSIBLE_PLAYBOOK) playbooks/docker.yml $(EXTRA)

netbox:
	$(ANSIBLE_PLAYBOOK) playbooks/netbox.yml $(EXTRA)

platform:
	$(ANSIBLE_PLAYBOOK) playbooks/platform.yml $(EXTRA)

validate:
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/validate-publication.ps1
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/validate-ansible-layout.ps1
