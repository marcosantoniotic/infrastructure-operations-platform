# Implantação reproduzível do ambiente operacional

## Objetivo

Este documento define o percurso suportado para transformar a arquitetura de
referência do Infrastructure Operations Platform em um ambiente operacional
novo, rastreável e reconstruível. Ele não autoriza alterações no ambiente
legado e não contém endereços, credenciais ou identificadores reais.

O resultado esperado é uma plataforma criada por código, validada antes do
cutover e capaz de receber somente os dados necessários do ambiente anterior.

Para uma primeira execução, comece pelo
[checklist de reprodução do zero](from-zero-checklist.md). Este documento é a
referência detalhada dos gates, decisões e critérios de aceite.

## Entradas exigidas do operador

| Entrada | Quando é usada | Regra |
|---|---|---|
| ISO RHEL 9.8 DVD e SHA-256 | Packer/Kickstart | arquivo local legítimo e checksum conferido |
| endereço do controlador | Vagrant e inventário | exclusivo no segmento escolhido |
| endereço da plataforma | Vagrant e inventário | exclusivo no segmento escolhido |
| endereços de recovery/standby | Vagrant e inventário | opcionais na primeira implantação |
| usuário administrativo | imagem, Vagrant e Ansible | conta dedicada; padrão `automation` |
| domínio base e e-mail administrativo | aplicações e alertas | valores privados do ambiente |
| segredos das aplicações | Ansible Vault | gerados no cofre, distintos por ambiente |
| método de registro RHEL | controlador e hosts | credencial legítima, nunca embutida no código |
| SMTP e backup externo | fases posteriores | necessários apenas quando esses recursos forem habilitados |

Os endereços, domínios, credenciais e identificadores reais não pertencem ao
repositório público.

## Princípios

1. Packer e Kickstart produzem a imagem base do RHEL.
2. Vagrant controla o ciclo de vida das VMs no VMware.
3. Ansible aplica baseline, Docker e módulos da plataforma.
4. Docker Compose controla o ciclo de vida das aplicações.
5. Segredos são injetados a partir de um cofre aprovado e nunca publicados.
6. Dados são restaurados por mecanismos nativos; volumes em execução não são
   copiados como estratégia de migração.
7. Notificações, sincronizações, timers e publicação externa permanecem
   desativados até o gate de cutover.

## Nomenclatura

O padrão de hostname é `iop-<ambiente>-<função>-<sequência>`.

| Ambiente | Função | Hostname |
|---|---|---|
| operacional | automação | `iop-ops-automation-01` |
| operacional | plataforma | `iop-ops-platform-01` |
| operacional | recuperação | `iop-ops-recovery-01` |
| operacional | contingência | `iop-ops-standby-01` |
| validação | automação | `iop-val-automation-01` |
| validação | plataforma | `iop-val-platform-01` |

Os nomes publicados das aplicações permanecem independentes do hostname:
NetBox, Zabbix, Grafana, Portainer, Traefik e Cockpit podem manter seus nomes
DNS durante o cutover.

## Separação dos artefatos

```text
repositório público
  código, exemplos sanitizados, testes e documentação

inventories/operational/                 (ignorado pelo Git)
  topologia real e variáveis não secretas do ambiente

cofre de credenciais
  senhas, tokens, chaves, configuração de backup e credenciais SMTP

repositório de backup
  dumps, mídia, manifestos e pontos de recuperação criptografados
```

O modelo público está em
`inventories/examples/operational/`. A cópia real deve ser criada em
`inventories/operational/` e permanecer fora do Git.

## Topologia mínima recomendada

Para a primeira implantação, apenas o controlador e o host da plataforma são
obrigatórios. Recuperação e contingência podem ser adicionados quando houver
recursos, sem alterar o contrato dos módulos.

| VM | Dimensionamento inicial | Responsabilidade |
|---|---:|---|
| `iop-ops-automation-01` | 2 vCPU, 4 GiB RAM, 80 GiB sparse | execução do Ansible e ferramentas de administração |
| `iop-ops-platform-01` | 4 vCPU, 8 GiB RAM, 80 GiB | aplicações, bancos e observabilidade |
| `iop-ops-recovery-01` | 4 vCPU, 8 GiB RAM, 80 GiB sparse | restauração isolada e exercícios de recuperação |
| `iop-ops-standby-01` | 2 vCPU, 4 GiB RAM, 80 GiB sparse | contingência de serviços essenciais |

As VMs derivam da mesma box com disco virtual de 80 GiB. O disco é sparse: a
capacidade lógica é uniforme, mas o consumo físico cresce conforme o uso.

O dimensionamento deve ser revisto após sete dias de métricas do novo ambiente.

## Pré-requisitos

- VMware Workstation;
- Vagrant e `vagrant-vmware-desktop`;
- Packer;
- PowerShell 7 ou Windows PowerShell compatível com os scripts;
- ISO RHEL suportada e checksum validado;
- acesso legítimo aos repositórios do RHEL;
- Ansible no controlador;
- cofre de credenciais preparado;
- capacidade de manter o ambiente anterior desligado, mas preservado, durante
  a janela de rollback.

Use a preparação já certificada em
[ambiente de validação como código](../testing/validation-environment.md) como
referência para Packer, Vagrant e requisitos da estação.

## Inicialização local e inventário privado

O inicializador cria uma identidade SSH exclusiva, variáveis locais do Packer,
configuração do Vagrant e o inventário privado. Ele não cria nem inicia VMs:

```powershell
Set-Location "<REPOSITORY_ROOT>"
.\automation\scripts\Initialize-Operational.ps1 `
  -ControllerAddress "<CONTROLLER_ADDRESS>" `
  -PlatformAddress "<PLATFORM_ADDRESS>" `
  -IsoPath "<RHEL_DVD_ISO_PATH>"
```

Os parâmetros `-RecoveryAddress` e `-StandbyAddress` são opcionais. Depois:

1. substitua somente na cópia privada os endereços e o domínio;
2. obtenha os segredos no cofre aprovado;
3. confirme que os arquivos privados continuam ignorados pelo Git;
4. valide a fase de imagem antes de construir a box;
5. preencha e criptografe o Vault no controlador antes do primeiro playbook.

```powershell
git check-ignore -v inventories/operational/hosts.yml
git status --short

.\automation\scripts\Test-OperationalConfiguration.ps1 -Phase Image
```

O teste operacional falha se detectar ISO ausente, arquivos privados
rastreáveis pelo Git ou configuração inválida. Placeholders e criptografia são
validados no gate `Deployment`, depois que o controlador possuir Ansible.

Consulte [inventários e gestão de segredos](../secrets-and-inventories.md).

## Ordem de implantação

### Gate 0 — estação e imagem base

1. validar os pré-requisitos;
2. validar ISO e checksum;
3. gerar a imagem base pelo Packer/Kickstart;
4. registrar a box operacional local no Vagrant;
5. registrar a evidência de versão das ferramentas.

```powershell
.\automation\scripts\Build-RhelBox.ps1 `
  -VarFile ".\.operational\operational.pkrvars.hcl" `
  -BoxFileName "rhel-9.8-operational-vmware.box"

.\automation\scripts\Register-RhelBox.ps1 `
  -BoxPath ".\automation\packer\rhel9\output\rhel-9.8-operational-vmware.box" `
  -BoxName "infrastructure-operations-platform/rhel9.8-operational"

.\automation\scripts\Test-OperationalConfiguration.ps1 -Phase Virtualization
```

Critério: imagem construída sem segredo no artefato público e acesso SSH por
chave comprovado.

### Gate 1 — ciclo de vida das VMs

1. criar inicialmente controlador e plataforma;
2. confirmar os hostnames `iop-ops-*`;
3. confirmar recursos, discos e interfaces;
4. adicionar as VMs à biblioteca do VMware;
5. usar `vagrant status`, `vagrant up` e `vagrant halt` como comandos normais.

`vagrant destroy` não faz parte da operação diária e exige mudança autorizada.

```powershell
.\automation\scripts\Start-OperationalEnvironment.ps1 `
  -Machine iop-ops-automation-01, iop-ops-platform-01
```

O Vagrantfile dedicado está em `automation/vagrant/operational/`. Recuperação e
contingência só são definidas quando seus endereços foram informados na
inicialização.

Critério: as VMs iniciam novamente a partir do código, sem configuração manual
de sistema operacional.

### Gate 1.1 — controlador de automação

1. valide no console VMware a impressão digital SSH do controlador;
2. registre os hosts RHEL pelo método legítimo aprovado para a organização;
3. instale `ansible-core`, Git e as coleções declaradas em `requirements.yml`;
4. clone o repositório público no controlador;
5. transfira por SSH somente o inventário operacional ignorado e a chave de
   automação para a conta administrativa do controlador;
6. aplique modo `0600` à chave e não a mostre no terminal;
7. use `--ask-vault-pass` ou integração com o cofre, sem versionar arquivo de
   senha do Ansible Vault.

Os passos de registro e transferência são supervisionados porque envolvem
identidade, confiança SSH e material sensível. Eles não devem ser substituídos
por credenciais embutidas no Packer ou no Vagrantfile.

No controlador:

```bash
cd "<REPOSITORY_ROOT>"
ansible-galaxy collection install -r requirements.yml
ansible-vault encrypt inventories/operational/group_vars/vault.yml
ansible-vault edit inventories/operational/group_vars/vault.yml
rg -n '<[A-Z][A-Z0-9_]+>' \
  inventories/operational/hosts.yml \
  inventories/operational/group_vars/all.yml
ansible-inventory \
  -i inventories/operational/hosts.yml \
  --graph \
  --ask-vault-pass
ansible \
  -i inventories/operational/hosts.yml \
  platform \
  -m ping \
  --ask-vault-pass
```

Critério: o controlador alcança somente os hosts esperados e o inventário não
aparece em `git status`.

O `rg` deve terminar sem ocorrências. A primeira operação do Vault criptografa
o modelo antes da inserção dos valores; a segunda abre o conteúdo somente no
editor controlado. Depois de devolver a cópia já criptografada à estação, rode:

```powershell
.\automation\scripts\Test-OperationalConfiguration.ps1 -Phase Deployment
```

### Gate 2 — preflight e baseline

```bash
ansible-playbook \
  -i inventories/operational/hosts.yml \
  playbooks/preflight.yml \
  --limit iop-ops-platform-01

ansible-playbook \
  -i inventories/operational/hosts.yml \
  playbooks/bootstrap-rhel.yml \
  --limit iop-ops-platform-01

ansible-playbook \
  -i inventories/operational/hosts.yml \
  playbooks/docker.yml \
  --limit iop-ops-platform-01
```

Critério: execução idempotente, firewall e SELinux preservados, Docker saudável
e nenhuma aplicação publicada externamente.

### Gate 3 — plataforma sem efeitos externos

Mantenha no inventário:

- Alertmanager desativado;
- backup externo desativado;
- execução imediata de backups desativada;
- rotas Traefik das aplicações desativadas;
- manutenção não autorizada.

Implante por módulo para isolar falhas:

```bash
ansible-playbook -i inventories/operational/hosts.yml playbooks/traefik.yml
ansible-playbook -i inventories/operational/hosts.yml playbooks/netbox.yml
ansible-playbook -i inventories/operational/hosts.yml playbooks/zabbix.yml
ansible-playbook -i inventories/operational/hosts.yml playbooks/portainer.yml
ansible-playbook -i inventories/operational/hosts.yml playbooks/observability.yml
ansible-playbook -i inventories/operational/hosts.yml playbooks/cockpit.yml
```

Critério: containers saudáveis, persistência comprovada após reinício
controlado e acessos disponíveis apenas pelos caminhos temporários autorizados.

### Gate 4 — restauração seletiva

Siga [migração do ambiente anterior](../migration/legacy-to-iop.md) e a
[matriz de dados](../migration/data-migration-matrix.md). Não ative automações
que possam gerar alertas duplicados ou sincronizações bidirecionais.

Critério: integridade dos bancos, mídia, plugins e objetos confirmada; dados
sensíveis ausentes das evidências.

### Gate 5 — observabilidade e recuperação

1. habilitar coleta interna;
2. validar dashboards e targets;
3. executar um backup inicial controlado;
4. verificar checksums e manifestos;
5. restaurar em ambiente isolado;
6. registrar RPO e RTO observados.

Critério: restauração comprovada sem tocar no ambiente ativo.

### Gate 6 — cutover

1. congelar alterações no ambiente anterior;
2. produzir os últimos dumps autorizados;
3. repetir a restauração final;
4. validar contratos HTTP e autenticação;
5. alterar os origins do Cloudflare/DNS;
6. habilitar uma única instância de notificações, sincronizações e timers;
7. observar o ambiente durante a janela definida.

Critério: aplicações acessíveis pelos nomes oficiais, sem alertas duplicados,
sem jobs concorrentes e com rollback ainda disponível.

### Gate 7 — estabilização

Mantenha o ambiente anterior desligado e preservado por pelo menos 14 dias ou
pelo período aprovado na mudança. Não reutilize seus endereços ou volumes antes
do encerramento formal do rollback.

## Execução modular

Quem precisa somente de um componente pode executar seu playbook e suas
dependências:

| Objetivo | Sequência mínima |
|---|---|
| NetBox | preflight → baseline → Docker → Traefik → NetBox |
| Zabbix | preflight → baseline → Docker → Traefik → Zabbix |
| Grafana/Prometheus | preflight → baseline → Docker → Traefik → observabilidade |
| Portainer | preflight → baseline → Docker → Traefik → Portainer |
| host RHEL | preflight → baseline → Docker → Cockpit |

Os módulos são descritos em [catálogo de módulos](../modules.md).

## Critérios de aceite da reprodutibilidade

- um novo operador consegue seguir o documento sem consultar esta conversa;
- o ambiente nasce de Packer, Vagrant, Ansible e Compose;
- o inventário público não contém informações reais;
- o inventário privado é ignorado pelo Git;
- todos os playbooks aplicáveis passam duas vezes sem mudança inesperada;
- cada aplicação possui healthcheck ou contrato verificável;
- backups possuem manifesto, checksum e restauração isolada comprovada;
- o cutover e o rollback possuem responsáveis e critérios objetivos;
- nenhuma etapa depende da cópia bruta de um volume em execução.

## Estado da implementação

O repositório contém imagem Packer/Kickstart, inicializador operacional,
Vagrantfile dedicado, inventário sanitizado, playbooks modulares e critérios de
migração. A implantação continua intencionalmente supervisionada nos gates de
segredos, restauração, publicação externa e cutover.
