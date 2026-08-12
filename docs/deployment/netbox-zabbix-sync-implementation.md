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
