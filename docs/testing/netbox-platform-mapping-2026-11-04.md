# Validacao isolada — plataformas NetBox/Zabbix — 04/11/2026

Resultado: **APROVADO no escopo isolado**. Nao e autorizacao nem aceite de
implantacao no LAB01. OPS e LAB01 nao foram acessados como aplicacoes/hosts
convidados nesta tarefa. O ensaio original abaixo ocorreu antes da autorizacao
de publicacao do PR; nao representa status do CI remoto nem aceite de deploy.

Base local: `10876df` (#92), com candidato entao nao commitado. Fonte executada e
harness daquela execucao conferidos por SHA-256. Evidencia historica sanitizada,
preservada sem reescrita apos a revisao:
[netbox-platform-mapping-20261104.json](../evidence/netbox-platform-mapping-20261104.json).

## Ambiente e proveniencia

VM descartavel exclusiva no E:, com Rocky Linux 9 (Bento, versao de box
202510.26.0), clone completo, NAT e sem discos/dados de LAB01/OPS. O catalogo
publico desse box nao forneceu checksum no metadata consultado; origem HTTPS
e versao foram registradas, sem alegar verificacao de assinatura do box.
Pacotes instalados por repositorios assinados; nenhuma verificacao TLS/GPG
foi desativada. A chave insegura inicial do Vagrant foi substituida por chave
propria e os acessos seguintes usaram host key fixada. Password do usuario
de teste bloqueado. Credenciais e CA ficticias novas, nao reutilizadas.

NetBox 4.6.10-Docker-5.0.2; Topology Views 4.5.1; QR Code 0.0.21;
Zabbix 7.4.13; Docker 29.9.3; Compose 2.40.3; Ansible-core 2.19.7.
IDs das imagens efetivamente executadas e logs completos ficaram privados.
Tags de imagem podem ser reconstruidas pelo fornecedor: nao inferir igualdade
de digest com instancias existentes sem uma revisao propria.

Oito containers, bancos novos, rede Docker interna, nenhuma porta de aplicacao
publicada, nenhuma rede/volume externo. Seis objetos sinteticos elegiveis,
com enderecos RFC 5737, foram cadastrados por REST e reconciliados com os
modelos reais do NetBox e JSON-RPC real do Zabbix. Um guard de encaminhamento
restringiu as escritas do sincronizador aos IDs novos; nao simulou respostas.
Todos os hosts ficaram desabilitados e nao havia midias de notificacao.
Nao havia sincronizador agendado concorrendo com o ensaio nem ponte GLPI.

## Resultados

| Etapa | Esperado | Observado / resultado |
| --- | --- | --- |
| Legado offline | Preservar os contratos anteriores | 19 testes aprovados |
| Perfis offline | Tipos, aliases, recusas e preservacao | 21 testes aprovados |
| Ansible | Sintaxe, guards positivos/negativos | Aprovados, sem falhas |
| Repeticao da renderizacao | Nenhuma mudanca adicional | 40 tarefas, changed=0 |
| Default desabilitado | Mesmo Compose da base | Comparacao byte a byte aprovada |
| Compose | JSON correto, sem nova exposicao | 4 variantes aprovadas; mesmas redes/mounts |
| Dry-run real | Nenhuma escrita | Zero escritas |
| Matriz real | Linux/Windows/rede em Devices e VMs | 6 hosts, grupos/templates correspondentes |
| Repeticao real | Idempotencia | Zero escritas adicionais |
| Troca de IP | Mesmo host/interface e tag local | hostinterface.update no ID esperado; tag/descricao locais preservadas |
| Plataforma ausente | Recusar antes das escritas | Recusada, zero escritas |
| Troca incompatível de perfil | Nao reconfigurar host existente | Recusada, zero escritas |
| Remocao da protecao/reaplicacao | Recusar downgrade; convergir ao voltar | Recusa e reaplicacao sem novas escritas |
| Fora do escopo | Nao alterar hosts de baseline ou alertas | Configuracao preservada; contagem de alertas inalterada |
| Limpeza | Remover somente recursos da execucao | 8 containers removidos por projeto/IDs/labels; rede e volumes ausentes |

As oito etapas reais concluiram entre 16:26 e 16:27 BRT de 04/11/2026. A
verificacao posterior confirmou os hashes do codigo e do harness daquela
execucao, e que nao restaram containers/volumes de teste.
As duas VMs descartaveis foram desligadas de forma controlada, com evidencias
preservadas no E:. Todas as VMs ja ligadas no inicio continuaram em execucao;
uma VM adicional fora do escopo entrou em execucao durante a janela e nao
recebeu comandos desta tarefa. O inventario global, portanto, nao e identico
ao inicial; nao atribuir essa diferenca ao ensaio ou tentar revertê-la.

## Intercorrencias e limites

- A primeira VM RHEL, criada a partir da base do projeto, nao tinha
  registro/repositorios. O bootstrap parou sem contornar a restricao; o
  operador autorizou nova base publica Rocky. A VM RHEL foi desligada.
- O arquivo Windows preservava pastas somente leitura. Com autorizacao,
  normalizaram-se somente permissoes da copia de testes, sem alterar a origem.
- Um caminho de icone incorreto no runner foi corrigido antes de subir apps.
  Outra tentativa foi encerrada pelo proprio operador, com finally/limpeza
  por labels, antes da fase funcional, para congelar o candidato final e
  usar o hostname HTTPS autorizado na sonda. Nao houve perda de dados reais.
- Nomes sinteticos foram encurtados para o limite real de 64 caracteres do
  Device. A alteracao ocorreu antes de iniciar o harness funcional, com
  controle do proprio runner e registro de SHA; nenhum criterio de aceite
  foi removido. A tentativa final completa e a evidencia de aprovacao.
- Os testes nao instalaram agentes Linux/Windows, nao fizeram ping em um
  equipamento real e nao validaram metricas, notificacoes ou chamados.
- Guard/reaplicacao foram testados. Migracao e rollback de templates/itens
  reais nao ocorreram; continuam dependendo do plano por ID e de aprovacao.
- Na data do ensaio original, o job funcional fora acrescentado ao CI, mas
  ainda nao executado no GitHub. As verificacoes acima sao locais e da VM
  isolada, nao um status remoto de CI.

## Revisao para o PR

A revisao encontrou uma expansao antecipada de loop Ansible que podia ler
um Compose inexistente na primeira instalacao. A correcao torna o loop vazio
nesse caso, sem relaxar os guards de instalacoes existentes. Foi acrescentado
um cenario de regressao sem Compose anterior; a execucao real dos guards em
Ansible 2.19.7 terminou com `ok=199`, `failed=0`, `rescued=13` (recusas esperadas).
Os 19 testes legados e 21 de perfis passaram novamente, assim como sintaxe
Python dos runners, estrutura Ansible, referencias imutaveis das Actions e
`git diff --check`.

O harness funcional passou a consultar explicitamente as duas APIs apos a
troca de IP, conferir IP B na mesma interface principal e contar exatamente
um host com a identidade sintética. Seu hash mudou; o JSON historico acima
continua descrevendo somente o harness efetivamente executado naquele ensaio.
Repeticoes com o harness reforcado devem ser registradas separadamente, sem
fabricar ou atualizar retroativamente a evidencia anterior. O CI do PR devera
repetir esses testes na revisao publicada; seu resultado deve ser consultado no
GitHub. Referencias a objetos de credenciais gerados pelo proprio fixture foram
formatadas para evitar falsos positivos do scanner; nenhuma credencial real
integra o codigo ou a evidencia publica.

## Antes de qualquer aplicacao

Revisar o [plano e rollback](../deployment/netbox-zabbix-platform-mapping.md),
levantar somente em leitura os slugs e hosts elegiveis reais, conferir agentes
ativos/Hostname e permissoes do token, confirmar snapshot/backup/restauracao
e aprovar a migracao por ID. VMs hoje em Virtual machines/ICMP nao serao
reclassificadas automaticamente pela primeira aplicacao.
