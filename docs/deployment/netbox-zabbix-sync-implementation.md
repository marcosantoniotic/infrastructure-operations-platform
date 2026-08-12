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

O token Zabbix fica em Ansible Vault e é materializado como arquivo
`root:root 0640`. O contêiner executa como `netbox:root` e recebe o segredo
por bind mount somente leitura. Mudanças no token, script ou Compose forçam a
recriação do contêiner, evitando que mounts continuem presos ao inode anterior.

Tokens não são portáveis entre bancos Zabbix. O ambiente operacional recebeu
um token emitido pela instância de destino; o token legado foi rejeitado como
esperado e não foi reutilizado.

## Artefatos adicionados

- `roles/netbox_zabbix_sync`;
- `playbooks/netbox-zabbix-sync.yml`;
- inclusão da role em `playbooks/platform.yml`, depois do Zabbix;
- variáveis públicas e exemplo de segredo Vault;
- renderização e validação do Compose no CI;
- referência operacional em `docs/configuration-reference.md`.

## Evidências de validação — 2026-08-11

- Python, YAML e `git diff --check`: aprovados;
- `ansible-playbook --syntax-check`: aprovado no controller;
- Compose operacional: válido;
- criação idempotente do campo `zabbix_hostid`: aprovada;
- API NetBox/PostgreSQL e API Zabbix: autorizadas;
- dispositivo temporário `codex-sync-validation` criado no NetBox;
- host correspondente criado no Zabbix com IP `192.0.2.254`;
- host e objetos temporários removidos após o teste;
- convergência final da role: `ok=7 changed=0 failed=0`;
- contêiner `netbox-zabbix-sync-netbox-zabbix-sync-1`: ativo.

## Migração dos dados reais

Os bancos reais foram restaurados em 2026-08-12. A integração reconciliou os
dois dispositivos marcados com `zabbix` com dois hosts gerenciados e terminou
com dry-run limpo. O token usado pertence ao banco Zabbix restaurado.

No ambiente migrado em 2026-08-11, o token restaurado possui acesso ao grupo
`NetBox - Managed` e a integração usa o template `ICMP Ping`. Esses nomes ficam
no inventário privado operacional; a role permanece reutilizável e resolve os
objetos por nome em cada ambiente.
