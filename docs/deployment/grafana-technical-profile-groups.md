# Grupos técnicos por perfil no Grafana

Esta opção permite filtrar os dashboards com o plugin oficial assinado sem depender do filtro `hostTags` da consulta de métricas. A opção permanece desabilitada por padrão e exige seleção explícita de perfil por campo personalizado do NetBox.

## Propriedade dos grupos

Crie antecipadamente três grupos dedicados no Zabbix. Não reutilize grupos locais nem grupos base dos templates. Exemplo sanitizado:

```yaml
netbox_zabbix_sync_technical_groups_enabled: true
netbox_zabbix_sync_technical_groups:
  linux-active: IOP - Linux
  windows-active: IOP - Windows
  network-icmp: IOP - ICMP
```

As chaves devem corresponder exatamente aos perfis do inventário. O sincronizador não cria grupos durante uma reconciliação. Ele registra a propriedade de cada associação em `netbox_technical_group`, no formato `v1:perfil:groupid`.

Na troca de perfil autorizada, somente a associação técnica anterior é substituída. Os demais grupos permanecem. A política de transição de templates continua independente, aditiva e condicionada à prontidão; o grupo técnico representa o último perfil aplicado com sucesso, não uma migração pendente.

Associações técnicas sem marcador, marcadores inconsistentes, remapeamento de IDs, mistura de perfis e remoção da proteção instalada são recusados. Não corrija esses casos apagando marcadores: investigue a origem e prepare uma recuperação explícita.

## Dashboards

Os quatro candidatos estão em `technical-dashboards`: visão geral, Linux, Windows e ICMP. O seletor de perfil escolhe o grupo técnico exato; não há seletor de grupo genérico que possa ampliar o escopo. As consultas não usam `hostTags`.

Os JSONs candidatos usam os três nomes do exemplo. Se outro inventário escolher nomes diferentes, ajuste o mapa do seletor e sua expressão de “Todos” nos quatro JSONs antes da importação e repita os testes de escopo. A role não provisiona dashboards implicitamente.

Use uma fonte Zabbix somente de leitura, com validação da cadeia e do nome TLS, CA pública confiável e sem acesso direto ao banco. O plugin oficial deve apresentar assinatura válida. Não habilite plugins não assinados.

## Sequência de aplicação proposta

1. Revisar o diff e o resultado do ensaio isolado. Fazer backup das configurações, associações de grupos, tags, dashboards e fonte de dados; proteger os bancos e snapshots conforme a janela aprovada.
2. Confirmar que os novos grupos não são usados por actions, alertas ou políticas de permissão não planejadas. Associação a grupos pode ampliar acesso no Zabbix.
3. Criar os grupos dedicados e conceder somente leitura à conta da fonte. Confirmar IDs únicos e distintos dos grupos existentes.
4. Renderizar a configuração e executar dry-run. Conferir todos os objetos alcançados e qualquer transição pendente antes de autorizar aplicação.
5. Aplicar somente a reconciliação aprovada. Conferir hostid, interfaceid, histórico, grupos e tags locais, além da repetição idempotente.
6. Importar os quatro dashboards com UIDs novos, preservando os existentes. Validar os seletores, a ausência de vazamento entre perfis e os estados sem coleta.

Nenhuma dessas etapas está autorizada implicitamente pelo ensaio isolado.

## Rollback

Não restaure bancos nem exclua volumes. Primeiro exporte o estado pós-aplicação. Remova somente os quatro dashboards novos, por UID e origem confirmados, e restaure apenas a fonte alterada se necessário.

Para reverter associações, pause somente a reconciliação durante uma janela autorizada e compare o estado atual com o backup por hostid. Restaure somente a associação técnica e seu marcador, preservando qualquer grupo local adicionado depois. Não execute uma substituição cega de toda a lista de grupos. A desativação do recurso instalado exige um procedimento explícito, pois os guards recusam downgrade silencioso. Não remova os grupos enquanto houver referências ou membros.

## Alcance do teste

O ensaio usa APIs e o mecanismo real do Grafana com métricas sintéticas em infraestrutura descartável. Ele não comprova disponibilidade de agentes ou serviços reais. O resultado final e as capturas devem acompanhar o relatório da execução; não use imagens de ensaios com plugin não assinado como evidência desta opção.

A base PostgreSQL nova da fixture usa `fsync=off`, `synchronous_commit=off` e `full_page_writes=off` para reduzir a latência de criação do schema no disco do host. Esses parâmetros pertencem somente ao runner descartável; não são variáveis da role nem uma proposta para LAB01 ou OPS. O ensaio não valida durabilidade após queda de energia nem backup dos bancos.

## Reproduzir em host descartável

Exige Linux com Docker Compose, Python, Ansible e as collections do projeto. Não execute o runner em hosts do laboratório ativo ou OPS. O destino deve ser novo, privado e permitido pelo guard do script.

```bash
IOP_DISPOSABLE_PLATFORM_TEST=1 python scripts/ci/test-technical-grafana.py \
  --workspace /tmp/iop-technical-grafana-example --revision "$(git rev-parse HEAD)"
```

O modo padrão não aguarda navegador. Para revisão assistida, adicione `IOP_TECHNICAL_VISUAL_TEST=1`. A fixture gera uma senha aleatória em `secrets/grafana-viewer` e sinaliza `visual-ready`. Acesso visual somente por encaminhamento SSH limitado ao loopback para o IP do container de propriedade comprovada; não publique portas Docker.

Após a revisão, crie `visual-complete` somente na pasta desta execução. O teste restaura os estados temporários e retoma a reconciliação. Há limite de dez minutos e limpeza dos recursos de propriedade comprovada em falha. O diretório privado inclui credenciais fictícias e não deve ser publicado; exporte somente a evidência sanitizada revisada.
