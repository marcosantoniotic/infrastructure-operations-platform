# Inventários e gestão de segredos

## Modelo adotado

O repositório separa configuração pública de material sensível:

- `inventories/example` contém o modelo modular original;
- `inventories/examples/operational` contém a topologia operacional sanitizada;
- `inventories/validation`, `inventories/operational` e
  `inventories/production` são ignorados pelo Git;
- variáveis operacionais permanecem em `group_vars/all.yml`;
- credenciais ficam em `group_vars/vault.yml`, criptografado com Ansible Vault.

O arquivo `all.yml` referencia variáveis com prefixo `vault_`. Assim, nenhuma
senha precisa ser escrita em playbooks, roles, templates ou parâmetros de linha
de comando.

## Preparação de um ambiente

Para o ambiente de validação:

```bash
cp -r inventories/example/* inventories/validation/
mv inventories/validation/group_vars/vault.example.yml \
  inventories/validation/group_vars/vault.yml
```

Edite `hosts.yml`, `all.yml` e `vault.yml`. Em seguida:

```bash
ansible-vault encrypt inventories/validation/group_vars/vault.yml
ansible-vault view inventories/validation/group_vars/vault.yml
ansible-vault edit inventories/validation/group_vars/vault.yml
```

Para o ambiente operacional, use o modelo dedicado e mantenha o destino fora
do Git:

```bash
cp -r inventories/examples/operational/* inventories/operational/
mv inventories/operational/group_vars/vault.example.yml \
  inventories/operational/group_vars/vault.yml
ansible-vault encrypt inventories/operational/group_vars/vault.yml
git check-ignore -v inventories/operational/hosts.yml
```

O procedimento completo está em
[implantação reproduzível do ambiente operacional](deployment/operational-environment.md).

## Execução segura

Para uso interativo:

```bash
ansible-playbook \
  -i inventories/validation/hosts.yml \
  playbooks/netbox.yml \
  --ask-vault-pass
```

Em automação, o arquivo que fornece a senha do Vault deve existir fora do
repositório, possuir permissões restritas e ser injetado pelo mecanismo de
segredos da plataforma de CI. Ele nunca deve ser versionado.

## Regras operacionais

- utilizar um Vault distinto por ambiente;
- não reutilizar credenciais entre validação e ambiente operacional;
- rotacionar segredos após exposição ou mudança de responsável;
- nunca colocar tokens em issues, screenshots, logs ou commits;
- executar `scripts/validate-publication.ps1` antes de publicar;
- revisar o diff e o histórico do Git antes de cada push.

## Governança e rotação

O catálogo público `config/credential-catalog.json` mantém somente metadados
operacionais: finalidade, privilégio, papel responsável e política de revisão
ou rotação. A cobertura entre esse catálogo e `vault.example.yml` é verificada
por `scripts/validate-credential-governance.ps1`.

O procedimento completo, incluindo rotação planejada, revogação emergencial e
particularidades por classe de credencial, está em
`docs/runbooks/credential-rotation.md`.
