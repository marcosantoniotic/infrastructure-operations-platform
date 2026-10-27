# Implementação da integração NetBox-Zabbix

## Resultado

A integração NetBox → Zabbix passou a ser um componente implantável da
Infrastructure Operations Platform. A role `netbox_zabbix_sync` reconcilia a
cada 60 segundos os dispositivos NetBox marcados com a tag `zabbix`.

## Comportamento

- cria hosts no Zabbix usando nome e IP primário do dispositivo;
- resolve grupo e template por nome, sem IDs específicos do ambiente;
- atualiza nome, estado, IP e tags gerenciadas;
- preserva tags criadas diretamente no Zabbix;
- grava o ID do host no campo NetBox `zabbix_hostid`;
- desabilita hosts quando a tag é removida ou quando não há IP primário;
- interrompe com segurança diante de colisão com host não gerenciado;
- nunca apaga automaticamente hosts reais.

## Segurança e operação

### VMs opt-in e escopo por site

O padrão continua restrito a dispositivos. Para habilitar VMs, configure no
inventário privado (não reutilize endereços ou segredos de outro ambiente):

```yaml
netbox_zabbix_sync_include_vms: true
netbox_zabbix_sync_vm_group: Virtual machines
netbox_zabbix_sync_vm_template: ICMP Ping
netbox_zabbix_sync_site_slugs: [example-lab]
```

A tag configurada seleciona tanto dispositivos quanto VMs; aplique-a somente a
objetos com IP primário, alcance confirmado e monitoração aprovada. VMs desligadas
ou já gerenciadas por outra automação devem ser revisadas antes da inclusão.
O template de VM é obrigatório e único para esse conjunto: ICMP mede somente
disponibilidade, não substitui agente Linux/Windows nem SNMP de equipamentos.
Não selecione um template Linux para todas as plataformas indiscriminadamente.

VMs usam nome técnico estável `netbox-vm-<id>` e nome visível do inventário.
A identidade inclui `netbox_object_type` e `netbox_id`; hosts legados sem tipo
continuam sendo dispositivos. O campo `zabbix_hostid` passa a aceitar VMs sem
remover suas associações anteriores. Colisões globais de nomes, IDs conflitantes,
posse duplicada e divergências de grupo/template bloqueiam a execução antes das
escritas. Hosts existentes não são adotados automaticamente. Tags, histórico,
grupos e templates externos são preservados; objetos fora do site não são
desabilitados por ausência no conjunto selecionado.

Antes de aplicar: faça snapshot confirmado, backup dos bancos/configurações e
cópia externa com hash; teste uma restauração isolada; confira a elegibilidade e
execute dry-run com a rotina periódica parada. Aplique apenas a role/serviço de
sincronização, sem provisionamento completo, e exija uma segunda execução sem
mudanças. A rede/CA TLS existente e seus mounts somente leitura devem permanecer.
Os guards recusam desligamento silencioso das VMs ou mudança do escopo/template
previamente instalado; migrações intencionais exigem revisão explícita.

Para não abrir chamados, não aplique a tag de encaminhamento ao GLPI e confira
os filtros das ações e tags herdadas dos templates. Não injete eventos de teste
nem execute o fluxo de criação de tickets para validar o inventário.
Esta inclusão não habilita chamados para VMs: a referência canônica de inventário
da ponte existente ainda assume dispositivos. Antes de habilitar notificações
de VMs, revise separadamente o suporte ao tipo de objeto nessa ponte e seu webhook.

Rollback: pare somente a sincronização, restaure script/Compose e overrides
privados anteriores, remova somente as tags adicionadas nesta mudança e
desabilite os hosts novos identificados na evidência. Preserve IDs, histórico,
volumes e cadastros existentes. Não restaure o banco inteiro sobre dados novos
como rollback rotineiro; reserve a restauração integral para recuperação aprovada.
Não remova associações de campos personalizados que já eram usadas antes.

O token Zabbix fica em Ansible Vault e é materializado como arquivo
`root:root 0640`. O contêiner executa como `netbox:root` e recebe o segredo
por bind mount somente leitura. Mudanças no token, script ou Compose forçam a
recriação do contêiner, evitando que mounts continuem presos ao inode anterior.

Tokens não são portáveis entre bancos Zabbix. Em reconstruções ou migrações,
use um token emitido pela instância que permanecerá ativa.

## Artefatos adicionados

- `roles/netbox_zabbix_sync`;
- `playbooks/netbox-zabbix-sync.yml`;
- inclusão da role em `playbooks/platform.yml`, depois do Zabbix;
- variáveis públicas e exemplo de segredo Vault;
- renderização e validação do Compose no CI;
- referência operacional em `docs/configuration-reference.md`.

## Validação

O pipeline valida a sintaxe Python/YAML, o playbook Ansible e o Compose
renderizado. Na implantação, a role exige autenticação nas APIs, cria o campo
personalizado de forma idempotente e executa uma reconciliação em dry-run.

Para um teste funcional controlado, use um dispositivo descartável com a tag
configurada e um endereço reservado para documentação. Confirme a criação do
host no grupo esperado, remova os objetos de teste e exija uma segunda
convergência sem mudanças.
