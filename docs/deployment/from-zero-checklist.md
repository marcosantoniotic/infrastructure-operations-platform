# Checklist de reprodução do zero

## Resultado esperado

Ao concluir este checklist, um novo operador terá criado a imagem RHEL, duas
VMs operacionais e a plataforma IOP a partir do repositório, sem depender do
ambiente legado ou desta conversa. Os gates de migração, publicação externa e
cutover continuam deliberadamente supervisionados.

## 1. Preparar a estação

- instalar VMware Workstation, Packer, Vagrant, Git e OpenSSH;
- instalar o plugin `vagrant-vmware-desktop` e seu utility service;
- obter legitimamente a ISO RHEL 9.8 x86_64 DVD;
- clonar este repositório e abrir PowerShell na raiz;
- escolher endereços exclusivos para controlador e plataforma;
- preparar um cofre exclusivo para os segredos do ambiente.

Consulte o [guia de implantação operacional](operational-environment.md) para
dimensionamento, entradas e critérios de cada gate.

## 2. Inicializar os arquivos privados

```powershell
Set-Location "<REPOSITORY_ROOT>"

.\automation\scripts\Initialize-Operational.ps1 `
  -ControllerAddress "<CONTROLLER_ADDRESS>" `
  -PlatformAddress "<PLATFORM_ADDRESS>" `
  -IsoPath "<RHEL_DVD_ISO_PATH>" `
  -IsoChecksum "<RHEL_DVD_ISO_SHA256>"
```

O comando cria somente arquivos ignorados pelo Git. Edite:

- `inventories/operational/hosts.yml`;
- `inventories/operational/group_vars/all/main.yml`;
- `inventories/operational/group_vars/all/vault.yml`.

Substitua os placeholders não secretos de `hosts.yml` e `group_vars/all/main.yml`. O Vault será
criptografado e preenchido no controlador, que terá `ansible-core`:

```powershell
rg -n '<[A-Z][A-Z0-9_]+>' `
  inventories/operational/hosts.yml `
  inventories/operational/group_vars/all/main.yml
git status --short
```

Aceite: `hosts.yml` e `group_vars/all/main.yml` não contêm placeholders e `git status` não
lista os arquivos privados. É esperado que o modelo `vault.yml` ainda contenha
placeholders nesta fase.

Ao preencher o Vault, use pelo menos 50 caracteres aleatórios para
`vault_netbox_secret_key` e `vault_netbox_api_token_pepper`, e pelo menos 16
caracteres para as senhas do NetBox. Valores menores interrompem a implantação
antes da criação dos containers.

## 3. Validar e construir a imagem

```powershell
.\automation\scripts\Test-OperationalConfiguration.ps1 -Phase Image

.\automation\scripts\Build-RhelBox.ps1 `
  -VarFile ".\.operational\operational.pkrvars.hcl" `
  -BoxFileName "rhel-9.8-operational-vmware.box"

.\automation\scripts\Register-RhelBox.ps1 `
  -BoxPath ".\automation\packer\rhel9\output\rhel-9.8-operational-vmware.box" `
  -BoxName "infrastructure-operations-platform/rhel9.8-operational"

.\automation\scripts\Test-OperationalConfiguration.ps1 -Phase Virtualization
```

Aceite: o teste termina com `Operational configuration approved` e a box
operacional aparece em `vagrant box list`.

## 4. Criar as VMs mínimas

```powershell
.\automation\scripts\Start-OperationalEnvironment.ps1 `
  -Machine iop-ops-automation-01, iop-ops-platform-01

Set-Location ".\automation\vagrant\operational"
vagrant status
```

Aceite: ambas as VMs estão `running`, com hostnames `iop-ops-*` e acesso SSH
por chave. Recovery e standby são opcionais e não devem ser criados até seus
endereços serem definidos.

## 5. Preparar o controlador

No controlador, registre o RHEL pelo método aprovado, instale `ansible-core` e
Git, clone o repositório e transfira por canal seguro:

- o inventário privado ignorado;
- a chave SSH operacional com modo `0600`.

Depois:

```bash
ansible-galaxy collection install -r requirements.yml
ansible-vault encrypt inventories/operational/group_vars/all/vault.yml
ansible-vault edit inventories/operational/group_vars/all/vault.yml
ansible-inventory -i inventories/operational/hosts.yml --graph --ask-vault-pass
ansible -i inventories/operational/hosts.yml platform -m ping --ask-vault-pass
```

O primeiro comando do Vault criptografa o modelo ainda sem valores reais. Use
`ansible-vault edit` para inserir os segredos diretamente no editor protegido.
Sincronize de volta à estação somente a cópia criptografada e execute:

```powershell
.\automation\scripts\Test-OperationalConfiguration.ps1 -Phase Deployment
```

Aceite: o gate `Deployment` é aprovado, somente os hosts esperados aparecem e
o ping Ansible é bem-sucedido.

## 6. Aplicar infraestrutura e plataforma

Execute na ordem, sempre com o inventário operacional:

```bash
ansible-playbook -i inventories/operational/hosts.yml playbooks/preflight.yml --limit iop-ops-platform-01 --ask-vault-pass
ansible-playbook -i inventories/operational/hosts.yml playbooks/bootstrap-rhel.yml --limit iop-ops-platform-01 --ask-vault-pass
ansible-playbook -i inventories/operational/hosts.yml playbooks/docker.yml --limit iop-ops-platform-01 --ask-vault-pass
ansible-playbook -i inventories/operational/hosts.yml playbooks/traefik.yml --limit iop-ops-platform-01 --ask-vault-pass
ansible-playbook -i inventories/operational/hosts.yml playbooks/netbox.yml --limit iop-ops-platform-01 --ask-vault-pass
ansible-playbook -i inventories/operational/hosts.yml playbooks/zabbix.yml --limit iop-ops-platform-01 --ask-vault-pass
ansible-playbook -i inventories/operational/hosts.yml playbooks/portainer.yml --limit iop-ops-platform-01 --ask-vault-pass
ansible-playbook -i inventories/operational/hosts.yml playbooks/observability.yml --limit iop-ops-platform-01 --ask-vault-pass
ansible-playbook -i inventories/operational/hosts.yml playbooks/cockpit.yml --limit iop-ops-platform-01 --ask-vault-pass
```

Mantenha rotas públicas, Alertmanager, sincronizações e backups externos
desativados até seus respectivos gates. Execute os playbooks uma segunda vez;
mudanças inesperadas na segunda execução impedem o avanço.

## 7. Validar antes de migrar dados

Com as rotas públicas ainda desativadas, abra um túnel a partir da estação e
mantenha o terminal aberto durante os testes:

```powershell
Set-Location ".\automation\vagrant\operational"
vagrant ssh iop-ops-platform-01 -- -N `
  -L 8000:127.0.0.1:8000 `
  -L 8081:127.0.0.1:8081 `
  -L 9000:127.0.0.1:9000 `
  -L 3000:127.0.0.1:3000 `
  -L 9090:127.0.0.1:9090 `
  -L 9091:127.0.0.1:9091
```

Valide `http://127.0.0.1:8000` (NetBox), `:8081` (Zabbix), `:9000`
(Portainer), `:3000` (Grafana), `:9090` (Prometheus) e
`https://127.0.0.1:9091` (Cockpit). A porta `8000` do NetBox é HTTP; não
permita que o navegador a converta para HTTPS.

- todos os containers esperados estão saudáveis;
- reinício controlado preserva os dados;
- dashboards e targets internos estão íntegros;
- backup inicial gera manifesto e checksum;
- restauração ocorre em ambiente isolado;
- nenhum segredo ou endereço real aparece em logs, Git ou evidências.

Somente depois siga a
[migração controlada do ambiente legado](../migration/legacy-to-iop.md). Para
instalar apenas um componente, use o [catálogo de módulos](../modules.md).
