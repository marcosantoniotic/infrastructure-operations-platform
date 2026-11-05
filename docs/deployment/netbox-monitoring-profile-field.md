# Perfil de monitoramento no NetBox (opt-in)

Seleção explícita de **Linux**, **Windows** ou **ICMP** no campo personalizado
**Perfil de monitoramento**, em Dispositivos e Máquinas Virtuais. Nome da máquina,
texto da plataforma e tags livres não determinam o perfil. A tag de elegibilidade
e o filtro de site continuam delimitando o escopo. O modo por slug exato de
plataforma permanece como padrão.

## Inventário e esquema

Veja a [fixture sanitizada](../../scripts/fixtures/netbox-monitoring-field.yml).
Não a copie sobre um inventário instalado: preserve mapas, perfis, TLS, filtros
e segredos existentes.

```yaml
netbox_zabbix_sync_platform_mapping_enabled: true
netbox_zabbix_sync_profile_source: custom-field
netbox_zabbix_sync_profile_field: monitoring_profile
netbox_zabbix_sync_profile_field_label: Perfil de monitoramento
netbox_zabbix_sync_profile_choice_set: iop-monitoring-profiles
netbox_zabbix_sync_profile_values:
  linux: linux-active
  windows: windows-active
  icmp: network-icmp
netbox_zabbix_sync_profile_labels:
  linux: Linux
  windows: Windows
  icmp: ICMP
netbox_zabbix_sync_manage_profile_field: true
netbox_zabbix_sync_platform_profiles:
  linux-active:
    group: Linux servers
    template: Linux by Zabbix agent active
  windows-active:
    group: Windows servers
    templates:
      - Windows by Zabbix agent active
      - ICMP Ping
  network-icmp:
    group: Network devices
    template: ICMP Ping
```

`template` (único, compatível com inventários antigos) e `templates` (lista) são
alternativas exclusivas. Grupos/templates precisam existir sem ambiguidade;
não são criados automaticamente. Colisões de chaves de itens/LLD, identidades
duplicadas e transportes não suportados bloqueiam o lote antes de escritas.
Não há preparação de interfaces SNMP/JMX/IPMI ou suas credenciais.

O opt-in `manage_profile_field` executa uma operação separada, transacional e
idempotente (`--prepare-monitoring-field`) antes do preflight. Cria somente
Choice Set e campo de seleção única, visível/editável, sem padrão, em Device/VM.
Não consulta Zabbix, não precisa do token e não preenche objetos. Definição
incompatível existente não é sobrescrita. O `--apply` normal não cria/repara esquema.

No NetBox: Dispositivo/VM → **Editar** → **Campos Personalizados** →
**Perfil de monitoramento** → Linux, Windows ou ICMP → salvar.
O ORM fornece o valor escalar; não há fallback para nome/plataforma.
Campo vazio/desconhecido em objeto elegível bloqueia todo o lote. Objetos fora
do escopo podem permanecer sem valor.

Host novo recebe os templates do perfil. Em host existente, mudança de perfil,
grupo ou templates exige migração explícita revisada. Mudar o campo não autoriza
desvincular templates ou trocar transporte. Tags locais, macros, templates extras
e histórico são preservados. Esta extensão não instala agentes.

## Windows: somente serviços nesta etapa

O perfil proposto combina **Windows by Zabbix agent active** e **ICMP Ping**.
O template oficial base já inclui descoberta de serviços, além das métricas do
sistema; não vincule outro template que duplique `service.discovery`.
Não são adicionados complementos AD DS/DNS, IIS ou SQL nesta etapa.

Após preparar e validar agente ativo/canal seguro em etapa autorizada, revise
as macros herdadas `{$SERVICE.NAME.MATCHES}` e `{$SERVICE.NAME.NOT_MATCHES}`.
Use nomes internos dos serviços, não nomes de exibição. Exemplo **fictício**:

```text
{$SERVICE.NAME.MATCHES} = ^(ExampleSvcA|ExampleSvcB)$
```

Confira também `{$SERVICE.STARTUPNAME.MATCHES}` /
`{$SERVICE.STARTUPNAME.NOT_MATCHES}` e exclusões na versão instalada. Não
substitua listas existentes sem revisão. O sincronizador preserva macros locais,
mas não as administra. Serviço “Running” não comprova saúde funcional da aplicação.
Testes de API/templates em Linux não comprovam coleta/LLD/alertas em Windows.

## Migração coordenada de ambiente instalado

1. Registre revisão, escopo e IDs, perfis, grupos, templates, tags e macros.
   Faça backup protegido dos bancos/configurações e snapshot das VMs envolvidas;
   preserve PKI, volumes e credenciais.
2. Confira interferência do agendamento e da ponte de chamados. Pausas/alterações
   exigem autorização específica. Não execute provisionamento completo.
3. Preserve nomes internos de perfis e mapas antigos. Aponte valores do campo
   para os **mesmos** perfis instalados. Prepare grupos/templates faltantes
   somente com aprovação; revise diff renderizado.
4. Prepare o esquema explicitamente e registre IDs/estado inicial. Preencha
   somente objetos elegíveis pelos IDs aprovados, nunca por inferência do nome.
5. Preflight e dry-run: adoção equivalente deve gerar somente a tag gerenciada
   `netbox_monitoring_source=custom-field:<campo>` nos mesmos hosts. Grupo,
   templates, interface, IP e identidade não devem mudar.
6. Aplique somente o escopo revisado, consulte ambas as APIs e repita sem
   alterações (zero escritas adicionais). Valide continuidade da coleta.
7. Prepare Windows separadamente; não migre o DC sem agente/canal validados.

Guards preservam origem/campo/Choice Set e entradas instaladas dos mapas de
valores/rótulos. A tag de origem também bloqueia downgrade silencioso para
plataforma. Não remova proteções para fazer o playbook passar.

## Plano original para LAB01 — posteriormente aplicado

O plano abaixo foi posteriormente autorizado e executado no LAB01.
Consulte o [registro separado da aplicação](../testing/netbox-monitoring-field-lab01-2026-11-04.md)
para resultados e limites; o ensaio isolado original continua histórico.

- Confirmar novamente estado, escopo e agendamento na janela autorizada; este
  ensaio não acessa o laboratório e não revalida seu estado atual.
- Proteger plataforma/controller com snapshot e backup em destino privado antes
  de alterar inventário, artefatos ou cadastros. Não tocar OPS, roteadores ou DC.
- Preservar os perfis internos instalados `linux-active` e `legacy-icmp`.
  Mapear `linux` para o primeiro e `icmp` para o segundo; não substituir a
  configuração instalada pela fixture de instalação nova.
- Preparar o grupo Windows e o perfil `windows-active` somente após aprovação.
  O campo pode oferecer Windows, mas isso não migra o DC automaticamente.
- Preencher Linux somente em controller/standby; manter os demais objetos
  atualmente ICMP nesse perfil, usando ledger de IDs revisado na janela.
- Adotar a origem por campo nos mesmos hosts com alteração apenas de tag,
  validar APIs/coleta e repetir. Preservar templates extras, PSK, CA e ajustes
  locais do controller. Sem provisionamento completo.
- Manter descoberta/coleta real de serviços Windows como etapa separada,
  dependente do agente ativo, canal seguro e aprovação sobre o servidor alvo.

## Rollback

Se o preflight falhar, não aplique; a coleta existente independe da reconciliação.
Após adoção, congele somente a reconciliação pelo procedimento aprovado e preserve
campo, valores e tags. Não volte apenas `profile_source` para `platform`: o guard
deve recusar. Código antigo não tem esse guard; não o execute sobre hosts adotados
sem plano explícito.

Restaure somente artefatos/configuração do sincronizador quando seguro, mantendo
execução congelada. Reverter dados gerenciados exige ledger de IDs, comparação de
estado e aprovação. Não restaure bancos, exclua volumes, desvincule templates ou
remova tags locais como atalho. Prefira corrigir/reaplicar com as mesmas identidades.
Esquema aditivo vazio pode permanecer sem afetar a coleta.

## Referências

- [Campos personalizados NetBox](https://netboxlabs.com/docs/netbox/customization/custom-fields/)
- [Modelo NetBox 4.6.10](https://github.com/netbox-community/netbox/blob/v4.6.10/netbox/extras/models/customfields.py)
- [Templates Windows oficiais](https://www.zabbix.com/integrations/windows)
- [Agente Windows 7.4](https://www.zabbix.com/documentation/7.4/en/manual/guides/monitor_windows)
