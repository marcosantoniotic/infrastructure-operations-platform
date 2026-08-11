# Inventários e gestão de segredos

## Modelo adotado

O repositório separa configuração pública de material sensível:

- `inventories/example` contém o modelo modular original;
- `inventories/examples/operational` contém a topologia operacional sanitizada;
- `inventories/validation`, `inventories/operational` e
  `inventories/production` são ignorados pelo Git;
- variáveis operacionais permanecem em `group_vars/all/main.yml`;
- credenciais ficam em `group_vars/all/vault.yml`, criptografado com Ansible
  Vault. O diretório `all/` faz o Ansible carregar os segredos para todos os
  hosts; `group_vars/vault.yml` seria interpretado como variáveis de um grupo
  chamado `vault`.

O arquivo `group_vars/all/main.yml` referencia variáveis com prefixo `vault_`.
Manter as variáveis comuns e o Vault no mesmo diretório `all/` evita a colisão
ambígua entre um arquivo `group_vars/all.yml` e um diretório `group_vars/all/`.
Assim, nenhuma
senha precisa ser escrita em playbooks, roles, templates ou parâmetros de linha
de comando.

## Preparação de um ambiente

Para o ambiente de validação:

```bash
cp -r inventories/example/* inventories/validation/
mkdir -p inventories/validation/group_vars/all
mv inventories/validation/group_vars/all/vault.example.yml \
  inventories/validation/group_vars/all/vault.yml
```

Edite `hosts.yml`, `group_vars/all/main.yml` e `group_vars/all/vault.yml`. Em seguida:

```bash
ansible-vault encrypt inventories/validation/group_vars/all/vault.yml
ansible-vault view inventories/validation/group_vars/all/vault.yml
ansible-vault edit inventories/validation/group_vars/all/vault.yml
```

Para o ambiente operacional, use o modelo dedicado e mantenha o destino fora
do Git:

```bash
cp -r inventories/examples/operational/* inventories/operational/
mkdir -p inventories/operational/group_vars/all
mv inventories/operational/group_vars/all/vault.example.yml \
  inventories/operational/group_vars/all/vault.yml
ansible-vault encrypt inventories/operational/group_vars/all/vault.yml
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
