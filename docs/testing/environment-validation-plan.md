# Plano de validação do ambiente

## Objetivo

Comprovar que a plataforma pode ser reconstruída a partir de uma instalação limpa, que cada módulo funciona independentemente e que novas execuções são idempotentes.

## Matriz inicial

| ID | Cenário | Resultado esperado |
|---|---|---|
| VAL-001 | RHEL 9 limpo | acesso SSH administrativo funcional |
| VAL-002 | preflight | requisitos aprovados ou falha explicativa |
| VAL-003 | baseline RHEL | hostname, timezone, pacotes, SELinux e firewall |
| VAL-004 | baseline repetido | nenhuma mudança inesperada |
| VAL-005 | instalação Docker | Engine e Compose ativos |
| VAL-006 | Docker repetido | execução idempotente |
| VAL-007 | NetBox isolado | aplicação e dependências saudáveis |
| VAL-008 | NetBox repetido | dados preservados e ausência de recriação indevida |
| VAL-009 | reinicialização do host | serviços recuperados automaticamente |
| VAL-010 | falha do PostgreSQL | NetBox degrada e causa é detectável |
| VAL-011 | restauração PostgreSQL | dados e login recuperados |
| VAL-012 | modo `--check` | nenhuma alteração no alvo |
| VAL-013 | credencial placeholder | playbook bloqueia antes da implantação |
| VAL-014 | NetBox com Traefik | publicação por hostname e TLS |
| VAL-015 | rollback | versão anterior recuperada sem perda de volume |

## Preparação

1. instale RHEL 9 em VM descartável;
2. crie usuário administrativo com sudo;
3. configure autenticação SSH por chave;
4. copie `inventories/example` para `inventories/validation`;
5. renomeie `vault.example.yml` para `vault.yml`;
6. substitua todos os placeholders e criptografe `vault.yml`;
7. instale as collections.

```bash
cp -r inventories/example/* inventories/validation/
mkdir -p inventories/validation/group_vars/all
mv inventories/validation/group_vars/all/vault.example.yml \
  inventories/validation/group_vars/all/vault.yml
ansible-vault encrypt inventories/validation/group_vars/all/vault.yml
ansible-galaxy collection install -r requirements.yml
```

Na execução, informe a senha do Vault interativamente:

```bash
ansible-playbook \
  -i inventories/validation/hosts.yml \
  playbooks/netbox.yml \
  --ask-vault-pass
```

## Execução por etapa

```bash
ansible-playbook -i inventories/validation/hosts.yml playbooks/preflight.yml
ansible-playbook -i inventories/validation/hosts.yml playbooks/bootstrap-rhel.yml
ansible-playbook -i inventories/validation/hosts.yml playbooks/docker.yml
ansible-playbook -i inventories/validation/hosts.yml playbooks/netbox.yml
```

## Teste de idempotência

Execute cada playbook novamente. O resultado esperado é `changed=0`, exceto tarefas que consultam ou renovam estado por desenho explícito.

## Modo de simulação

```bash
ansible-playbook \
  -i inventories/validation/hosts.yml \
  playbooks/netbox.yml \
  --check \
  --diff
```

Arquivos marcados com `no_log` não devem revelar segredos no diff.

## Validação do NetBox

```bash
cd /opt/netbox
docker compose config --quiet
docker compose ps
docker compose logs --since 10m netbox
curl -I http://localhost:8000/login/
```

Critérios:

- PostgreSQL saudável;
- Valkey principal e cache saudáveis;
- NetBox saudável;
- worker e housekeeping em execução;
- endpoint responde 200 ou 302;
- login administrativo funciona;
- dados permanecem após recriação dos containers.

## Evidências

Registrar para cada caso:

- data;
- versão do commit;
- versão do sistema;
- comando;
- resultado;
- evidência sanitizada;
- incidente encontrado;
- correção aplicada.

Nunca versionar logs completos, inventários reais ou arquivos Vault.
