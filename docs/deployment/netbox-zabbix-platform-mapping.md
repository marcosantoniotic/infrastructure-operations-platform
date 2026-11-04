# Mapeamento de plataformas NetBox → Zabbix

## Escopo e estado

Implementacao opt-in, validada em isolamento; ver [resultados e limites](../testing/netbox-platform-mapping-2026-11-04.md).
Nenhuma implantacao autorizada por
este documento. LAB01 e OPS nao sao alvos dos testes. Equipamentos de rede
usam **ICMP primeiro**, conforme decisao do operador; SNMPv3 fica para outra
mudanca, com interface, credenciais e testes proprios.

O sincronizador le o campo **Platform** do NetBox; nao descobre o sistema
operacional pela rede e nao classifica pelo nome da maquina. A chave e o slug
exato da plataforma. Devices e VMs usam a mesma tabela de classificacao; a
inclusao de VMs continua dependendo de `netbox_zabbix_sync_include_vms`.
O fabricante nao participa da chave: se diferentes cadastros de Platform
usarem o mesmo slug, eles receberao o mesmo perfil. Padronizar slugs distintos
quando precisarem de politicas diferentes, antes de habilitar a opcao.

| Perfil de exemplo | Grupo | Template |
| --- | --- | --- |
| linux-active | Linux servers | Linux by Zabbix agent active |
| windows-active | Windows servers | Windows by Zabbix agent active |
| network-icmp | Network devices | ICMP Ping |

Exemplo sanitizado: [netbox-platform-profiles.yml](../../scripts/fixtures/netbox-platform-profiles.yml).
Os slugs sao exemplos, nao um inventario real. Grupos e templates devem existir
e ser visiveis ao token Zabbix; a rotina nao os cria silenciosamente.

## Variaveis e compatibilidade

- `netbox_zabbix_sync_platform_mapping_enabled: false`: padrao legado preservado.
- `netbox_zabbix_sync_platform_map: {}`: slug exato → identificador de perfil.
- `netbox_zabbix_sync_platform_profiles: {}`: perfil → `group` e `template`.

Com a opcao desabilitada, nenhum novo ambiente/mount/rede/porta e acrescentado
ao Compose. Devices continuam no grupo/template legado, VMs no par legado de
VMs; site, tag, TLS, CA e mecanismos de identidade anteriores permanecem.
Os grupos/templates legados continuam sendo resolvidos para proteger hosts
antigos ainda sem a nova tag; manter essas variaveis e seus cadastros existentes.

Com a opcao habilitada, qualquer objeto elegivel sem Platform ou sem regra
exata bloqueia o lote no preflight, sem fallback para Linux. Fora do site/tag
selecionado nao se tenta classificar novos objetos. JSON duplicado, schema
invalido, perfil inexistente e nomes vazios/com controles ou `$` sao recusados.
Nao colocar credenciais em perfis: somente nomes de grupo/template.

Todos os perfis sao resolvidos e seus itens, regras LLD e prototipos consultados antes de escrever.
Templates vazios ou que exijam SNMP, IPMI ou JMX sao recusados: esta etapa nao
converte transportes. O token precisa de `hostgroup.get`, `template.get` e
`item.get` e `discoveryrule.get`, alem das permissoes da sincronizacao ja existente.

A interface de endereco criada continua sendo tipo Agent, IP principal,
porta 10050. Para ICMP ela fornece o endereco padrao ao template de simple
checks; nao instala agente, nao publica portas e nao configura SNMP. Para
Linux/Windows ativos, o agente precisa existir, ter ServerActive correto e
**Hostname exatamente igual ao nome tecnico do host Zabbix**. Para VMs esse
nome e `netbox-vm-<id>`, nao necessariamente o nome amigavel do NetBox.
O sincronizador nao instala ou altera agentes nem controles de firewall.

## Protecoes e migracao de hosts existentes

A tag gerenciada `netbox_monitoring_profile` identifica o perfil. Um host
existente so e adotado se ja tiver o grupo/template esperado e uma unica
interface principal compativel. Grupos/templates adicionais, tags locais,
macros, descricoes, interfaces secundarias e IDs sao preservados.

Mudanca de plataforma que implique outro perfil, divergencia de grupo/template, interface ausente,
DNS em vez de IP ou porta diferente bloqueiam a aplicacao. A rotina nao faz
unlink, `templates_clear`, substituicao de grupos/macros/interfaces ou exclusao
de hosts. Hosts legados compativeis podem apenas receber a nova tag.

O guard Ansible recusa desligar um mapeamento instalado ou alterar/remover
suas regras e perfis. Adicoes sao permitidas somente preservando integralmente
as entradas anteriores; remapeamentos precisam de migracao explicitamente
revisada, nao de remover a protecao.
O runtime tambem recusa desligamento quando encontra a tag instalada. A role
valida o JSON sem Django/APIs e executa dry-run antes de substituir o servico
agendado quando a opcao esta ativa. Campo personalizado deve estar previamente
preparado; o dry-run nao cria esse campo nem suas associacoes.

## Plano proposto para LAB01 — aguarda revisao/autorizacao

1. Conferir diff, evidencias isoladas e revisao exata do candidato. Validar
   versoes de NetBox, plugins, Zabbix e disponibilidade dos templates no LAB01.
2. Fazer inventario somente leitura dos objetos elegiveis, Platforms, IPs,
   hostids, interfaces e tags; listar as divergencias. Nao adivinhar slugs e
   nao executar `--apply` global para descobrir o que acontecera.
3. Confirmar backup atualizado dos bancos/configuracoes, manifestos e copia
   externa protegida, com restauracao isolada; confirmar snapshot consistente
   da VM plataforma. Manter o MySQL recuperado, midia e raiz da PKI protegidos.
4. Preparar plano por ID para os hosts existentes, com antes/depois e aprovacao
   explicita. VMs hoje em Virtual machines/ICMP nao serao trocadas automaticamente.
   Conferir agentes ativos, nomes tecnicos e direito do token nos novos grupos.
5. Durante a janela aprovada, pausar somente o sincronizador e aplicar a
   protecao de manutencao/notificacoes dos hosts selecionados. Revisar a ponte
   para que a migracao nao gere chamados; nao criar eventos ou tickets de teste.
6. Criar apenas grupos faltantes aprovados e preparar plataformas/associacoes
   por IDs. Preferir adicoes revisadas preservando os grupos/templates antigos;
   nao remover cadastros ou limpar historico. Qualquer conflito de itens exige
   revisao especifica, nunca unlink-and-clear para forcar a passagem do teste.
7. Renderizar e validar Ansible/Compose; executar candidato uma vez com
   `--verbose`, sem `--apply`. Exigir
   que o plano corresponda aos IDs aprovados, sem efeitos em outros objetos.
8. Somente apos autorizacao de aplicacao, atualizar exclusivamente o servico
   de sincronizacao, nao o provisionamento completo. Validar mesmo hostid,
   interfaceid, tags locais, templates/grupos adicionais, IP e campo NetBox.
   Repetir sem mudancas e exigir zero escritas adicionais.
9. Confirmar continuidade de coleta e integracoes antes de retomar agendamento
   e notificacoes. Coleta real de agentes/ICMP e aceite separado: cadastrar um
   host corretamente nao comprova que seu agente ou ping respondeu.

## Rollback coordenado

Antes da aplicacao, guardar script, Compose, overrides/CA/mounts e inventario
dos IDs/associacoes. Em falha, pausar apenas a sincronizacao e manter os hosts
afetados protegidos contra notificacoes. Restaurar os artefatos anteriores
revisados; nao apenas mudar a flag atual para false, o que o guard recusa.

Preservar IDs, tags locais, bancos, volumes e o MySQL recuperado. Hosts novos
devem ser desabilitados por IDs comprovados, nao apagados. Se nao pertencem
aos grupos legados, retirar temporariamente somente sua tag de selecao
adicionada nesta mudanca, por IDs do ledger, para nao bloquear o preflight do
reconciliador antigo; preservar hostid/campo personalizado e tag de perfil.
A volta exata de
templates/grupos e uma operacao separada por host: manter adicoes ate revisao,
sem `templates_clear` ou exclusao de itens/historico. Nao remover tags de
protecao para esconder o estado instalado. Esse rollback interrompe o novo
reconciliador; nao promete desfazer automaticamente toda migracao de itens.
Reaplicar o candidato somente apos corrigir a causa e repetir o dry-run.

APIs diferentes nao formam uma transacao distribuida. O preflight evita
erros deterministas conhecidos antes das escritas; falhas de transporte no
meio de uma aplicacao podem deixa-la parcial e precisam de reconciliacao
controlada, nao restauracao indiscriminada dos bancos.

## Testes reproduziveis e limites

Offline: `python scripts/tests/test_netbox_vm_sync.py` e
`python scripts/tests/test_netbox_platform_mapping.py`. Modelos/APIs simulados;
nao constituem prova de integracao real.

O runner `scripts/ci/test-netbox-platform-mapping.py` exige
`IOP_DISPOSABLE_PLATFORM_TEST=1`, um workspace novo e Docker descartavel. Ele
cria oito containers, bancos vazios, CA ficticia e rede interna sem portas
publicadas; executa `functional_netbox_platform_mapping.py` com ORM/REST NetBox
e JSON-RPC Zabbix reais. O guard de escrita encaminha as requisicoes reais,
mas restringe-as aos IDs ficticios da execucao; nao simula respostas.
Os seis hosts ficam desabilitados, sem midias de notificacao. Dados e imagens
de LAB01/OPS nao sao usados. A limpeza confere rotulos/IDs do projeto antes
de remover somente seus containers/volumes; evidencias privadas permanecem.

O resultado desta execucao esta registrado no relatorio vinculado acima.
Nenhum ensaio de API desta etapa comprova
metricas de agente Linux/Windows ou resposta de um equipamento real a ICMP.

Referencias: [interface Zabbix 7.4](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/hostinterface/object),
[semantica de host.update e templates_clear](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/host/update).
