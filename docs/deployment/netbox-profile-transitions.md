# Reconciliação aditiva de perfis existentes (opt-in)

O campo do NetBox é o estado desejado. Este opt-in permite mover o grupo
gerenciado e **adicionar** templates no mesmo host. Não é uma conversão irrestrita
de sistema operacional. Não instala agentes, altera TLS, remove templates,
exclui itens ou chama `templates_clear`.

## Política explícita

```yaml
netbox_zabbix_sync_profile_transitions:
  - from: network-icmp
    to: windows-active
netbox_zabbix_sync_profile_ready:
  virtualization.virtualmachine:42:
    profile: windows-active
    hostid: '12345'
```

IDs acima são fictícios. Atestar prontidão somente depois de validar o agente
ativo real, identidade técnica, credencial PSK/certificado e canal criptografado.
A atestação não é uma sonda de disponibilidade nem uma prova automática de coleta.
O host destino deve aceitar somente PSK/certificado (`tls_accept` 2, 4 ou 6).
Não se copia nem se define qualquer segredo nesse mapa. Novos hosts mantêm o
comportamento anterior; esta política controla apenas mudanças de perfil existente.

O perfil Windows deve incluir `Windows by Zabbix agent active` e `ICMP Ping`.
O perfil de origem deve estar intacto, o vínculo de volta no NetBox deve confirmar
o mesmo host e a origem por campo não pode mudar. O grupo antigo gerenciado é
substituído, mas outros grupos, templates extras, macros, tags locais, interfaces,
transporte e histórico não são substituídos. São conferidos conflitos de chaves
com os itens/LLD já existentes; não há adoção silenciosa de itens locais.

O conjunto de templates antigo precisa ser subconjunto do destino. ICMP → Windows
com ICMP satisfaz isso. Windows → ICMP, Linux → Windows, remoções de templates,
drift, colisões e transições não autorizadas ficam pendentes. Remover um template
sem apagar itens também pode remover mapas de valores, tags e dashboards herdados;
isso requer outro procedimento revisado, não este opt-in.

## Execução e pendências

Sem política, os guards anteriores permanecem. Com política, recusas de perfil
conhecidas são registradas como `PROFILE-PENDING object=<tipo>:<id> reason=...`;
o host é mantido intacto e **não** classificado como órfão. Os demais objetos
válidos continuam. Retorno 2 significa lote parcial, não sucesso completo.
Erros globais de esquema, identidade, propriedade, TLS/API e escopo continuam
bloqueando o lote. Não interpretar toda falha como pendência tolerável.

Antes da escrita de migração o host é relido para detectar edições concorrentes.
Não existe compare-and-swap na API: a janela entre a última leitura e escrita
ainda existe. Execute um só reconciliador e não edite os mesmos hosts na janela.
Não há transação distribuída entre NetBox e Zabbix nem entre vários hosts.
Repetição após sucesso não deve gerar escritas. Um marcador gerenciado
`netbox_profile_reconciliation=additive-v1` impede retirar a proteção silenciosamente;
o guard Ansible também preserva as arestas instaladas. Atestações podem ser
revogadas removendo sua entrada; isso bloqueia futuras migrações daquele agente,
sem desativar sua coleta já configurada. Uma nova entrada só funciona se o ID
corresponder ao vínculo real e o transporte continuar criptografado.

## Aplicação no laboratório e rollback

1. Conferir revisão, diff, agendamento, IDs, valores desejados e credenciais sem
   expô-las. Capturar estados completos e o escopo de qualquer escrita prevista.
2. Proteger bancos/configuração, PKI e artefatos do sincronizador e criar snapshot
   conforme janela aprovada. Não provisionar a plataforma inteira.
3. Validar os testes isolados, render/sintaxe/Compose e guards. Atestar somente
   agentes realmente preparados; sem prontidão o host permanece ICMP/pendente.
4. Fazer dry-run e revisar mudanças. Aplicar somente no sincronizador e nos hosts
   explicitamente aprovados. Não instalar agente no DC sem etapa autorizada.
5. Conferir mesmo host/interface/itens antigos, histórico, grupos/templates extras,
   macros/tags/TLS; repetir e exigir ausência de escritas adicionais. Separar
   prova de cadastro via API da prova de coleta Windows e descoberta de serviços.

Rollback: congelar apenas a reconciliação na janela aprovada, manter atestações,
marcador e estado pós-migração, reverter somente os artefatos por cópia protegida.
Código antigo não entende o marcador; **não** executá-lo em hosts migrados.
Reverter grupo/templates requer revisão por IDs, sem `templates_clear`, apagar
itens, restaurar bancos ou excluir volumes. Não retirar TLS para voltar a coletar.
Enquanto congelado, a coleta já configurada no Zabbix continua independente.

## Testes e limites

`scripts/tests/test_netbox_profile_transitions.py` cobre contratos offline com
mocks. A fixture real em `functional_netbox_platform_mapping.py` testa criação e
migração de Device/VM sintéticos, itens antigos e histórico real de item trapper
local, identidade, tags/macros, idempotência e isolamento de pendência. Não é
teste de agente Windows real, disponibilidade no endereço ou alerta funcional.
Resultado e evidências da execução devem ser registrados separadamente.

O [ensaio sintético dos grupos técnicos](../testing/grafana-technical-groups-2026-11-07.md)
registra a transição no mesmo host com preservação de histórico. Não constitui
validação de agente Windows real ou aceite de implantação.

Referências: [API host.update](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/host/update)
e [vínculo de templates](https://www.zabbix.com/documentation/7.4/en/manual/config/templates/linking).
