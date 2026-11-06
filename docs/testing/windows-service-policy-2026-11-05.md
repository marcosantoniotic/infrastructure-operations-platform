# Política AppXSvc/InventorySvc — validação isolada

Data: 2026-11-05. Fuso de operação: America/Sao_Paulo, UTC−03.

Nota histórica: este relatório descreve somente o ensaio inicial com produtor
PSK fictício. O [ensaio Windows nativo posterior](windows-service-native-2026-11-05.md)
tem resultados, falhas de preparação e limites próprios. Não reclassificar as
14 etapas deste relatório como execução de leitores Windows.

**Resultado geral: PARCIAL.** Implementação opt-in e ensaio de API/motor Zabbix
em isolamento; a coleta nativa num Windows descartável continua pendente.
Não autoriza implantação no LAB01. Nenhum acesso ou alteração no LAB01, no DC
ou no OPS; nenhum comando de início/parada de serviço Windows.

Base local: `a899d1b0c8ca9f052c8c575a0d5b61ae3556a465`, mais alterações locais
anteriores preservadas e o candidato desta tarefa. Sem commit, push, PR ou CI
remoto nesta etapa. Não afirmar que este candidato já está na main.

Execução final v8: **14 etapas aprovadas**, incluindo recuperação reforçada,
redescoberta efetivamente processada e rollback. Fixture iniciada às 21:10:15 UTC
(18:10:15 UTC−03); etapas funcionais registradas de 21:13:17 a 21:16:05 UTC
(18:13:17 a 18:16:05 UTC−03).
Identificador fictício: `synthetic-ip-platform-20261105211015-07f2c3df`.
SHA-256 do reconciliador efetivamente executado, com LF:
`8629898892d4e632bd237f25f621594c0dd0231d75ae4241842a7d599583005b`.

## O que foi implementado

- Role/playbook próprios, fora de `site.yml` e da sincronização NetBox–Zabbix;
  desativados por padrão e limitados a IDs explicitamente aprovados.
- Por host: 15 itens e dez triggers locais, sem desligar descoberta, desvincular
  template ou excluir dados existentes.
- Fase `observe`: coleta adicional; regras novas desabilitadas e antigas mantidas.
- Fase `enforce`: aprovação separada, dados atuais e histórico mínimo exigidos;
  habilita as dez novas regras e desabilita apenas as duas antigas confirmadas.
- Parada limpa não é crash. Falhas SCM/códigos de saída, ausência, divergência
  de configuração, transição prolongada e perda de observação são diferenciadas.
- Recuperação de falha exige três amostras consecutivas em execução e com
  códigos limpos, fontes atuais e janela sem falhas SCM; silêncio não recupera.
- Ledger privado, journal de status, guards de propriedade/escopo e rollback
  explícito que não apaga itens, eventos ou histórico.

Ver [desenho, limites e plano futuro](../deployment/windows-service-policy.md).

### Escopo do diff

13 arquivos novos e duas adições pontuais no workflow existente:

- `roles/windows_service_policy/`: reconciliador, defaults, tasks e README.
- `playbooks/windows-service-policy.yml`: runner único e explícito.
- `scripts/tests/test_windows_service_policy.py` e
  `scripts/tests/functional_windows_service_policy.py`: contratos e ensaio real.
- `scripts/ci/`: guard inerte, render/schema e wrapper da fixture isolada.
- `scripts/fixtures/windows-service-policy.yml`: configuração inteiramente fictícia.
- Dois documentos: desenho/ativação/rollback e este relatório.
- `.github/workflows/validation.yml`: execução offline e guard inerte Ansible.
  O ensaio de API real continua explícito/opt-in; não foi adicionado deploy.

O patch de revisão desta tarefa não incorpora as mudanças locais anteriores da
sincronização NetBox. Seus arquivos foram conferidos por hash contra a linha de
base inicial; o conteúdo anterior do workflow também foi preservado. A árvore
de trabalho não está limpa porque esses trabalhos locais foram mantidos.

## Ambiente e natureza das evidências

Somente VM Rocky Linux descartável, rede NAT sem bridge/pastas compartilhadas.
Dentro dela, rede Docker interna, volumes novos e zero portas publicadas.
Nenhum inventário, dado, token ou certificado dos ambientes ativos foi utilizado.

| Componente executado | Versão/imagem |
| --- | --- |
| Zabbix server | `zabbix/zabbix-server-mysql:alpine-7.4.13` |
| Zabbix frontend/API | `zabbix/zabbix-web-nginx-mysql:alpine-7.4.13` |
| Banco fictício | `mysql:8.4.10-oraclelinux9` |
| Proxy TLS fictício | `traefik:v3.7.13` |
| Runner Python ocioso | Build da imagem NetBox `v4.6.10-5.0.2`; sem iniciar Django |

Postgres/Valkey constam do manifesto da fixture reutilizada, mas foram retirados
do Compose executado; não foram serviços testados. IDs de imagem estão nas
evidências privadas, não apenas tags mutáveis.

As chamadas à API usam HTTPS com CA fictícia e validação de cadeia/nome. Os dados
ativos são mensagens fictícias autenticadas por TLS 1.2 PSK, enviadas ao servidor
Zabbix real. Não são dados produzidos por `wmi.getall`/`eventlog.count` executados
por Agent 2 no Windows. Essa distinção impede alegar validação ponta a ponta.

## Matriz observada

Tabela da execução final isolada v8. Os testes offline usam mocks; as etapas de
API, LLD, pré-processamento e triggers abaixo usam o servidor Zabbix real.

| Etapa | Esperado | Observado | Resultado / evidência privada |
| --- | --- | --- | --- |
| Contratos offline | Defaults inertes, escopo e guards; idempotência e rollback | 25 testes da versão final passaram localmente | Aprovado; `runner/offline.private.log` na execução final |
| Regressão NetBox | Preservar comportamento existente | 95 testes passaram localmente e nas execuções isoladas | Aprovado; `runner/regression.private.log` |
| Ansible | Sintaxe válida, opt-out inerte, recusa de retirada instalada | Sintaxe/guards aprovados; render repetido `changed=0` | Aprovado; `runner/syntax.private.log`, `role-guards.private.log`, `render-repeat.private.log` |
| Compose/isolamento | Zero portas/recursos externos e somente objetos próprios | Cinco containers fictícios; rede interna/volumes próprios | Aprovado; `fixture/compose-config.private.log`, `images.private.json` |
| PSK, LLD e histórico reais | Descobrir dois serviços e aceitar valores ativos | Dois itens antigos, quatro amostras persistidas por item | Aprovado; `wsp-initial-ids.private.json`, `wsp-history-before.private.json` |
| Observe | 25 objetos novos, nenhuma alteração no host/template | 25 criações, regras novas desabilitadas; repetição zero escritas | Aprovado; estágio `observe-plan-apply-repeat` |
| Pré-processamento real | Não transformar entrada inválida em zero saudável | Nove casos no motor Zabbix, incluindo JSON inválido, duplicação, códigos e nome localizado inconsistentes | Aprovado; `wsp-preprocessing.private.json` |
| Corte | Mudar somente status dos IDs previstos | Dez regras novas habilitadas + duas antigas desabilitadas; repetição zero | Aprovado; `cutover-only-two-old-statuses` |
| Ociosidade/1077 | Não confundir parada limpa/nunca iniciado com crash | Parada com código zero sem falha; 1077 em métrica distinta | Aprovado; `clean-idle-no-failure`, `never-started-not-a-crash` |
| Falha/recuperação | Falha SCM ou código ruim dispara; silêncio não recupera | SCM e 1066/específico 5 independentes; uma única amostra limpa não recupera; recuperação posterior após três amostras limpas em execução | Aprovado; estágios de `failure`/`exit-code-failure` |
| Ausência/configuração/transição | Avisos distintos, sem excluir itens antigos | Ausência, StartMode divergente e transição prolongada detectados e recuperados | Aprovado; `missing-and-config-drift`, `sampled-transition-duration` |
| Perda de observação | Entrada malformada não libera saúde | Master unsupported e alerta de ausência; recuperação após dados válidos | Aprovado; `malformed-is-unknown-not-healthy` |
| Redescoberta/reaplicação | Não reativar regra antiga nem afetar serviço fora do escopo | Terceiro serviço fictício realmente descoberto, sua regra permaneceu habilitada e as duas antigas desabilitadas; zero escritas do reconciliador | Aprovado; `wsp-rediscovery-witness.private.json`, `rediscovery-and-reapply` |
| Rollback/histórico/fora do escopo | Restaurar status, reter IDs/dados, zero notificações | 12 escritas; repetição zero; itens, amostras e eventos antigos preservados, sem reconhecimento manual; demais hosts e lista de alertas iguais | Aprovado; `rollback-idempotence-history-and-outside`, snapshots antes/depois |
| Leitor Windows nativo | Executar consultas e filtros na versão real do Agent 2 | Não executado | Pendente; não inferir aprovação da API |

Os caminhos da tabela são relativos a cada arquivo privado de evidências.
Os contadores de escrita referem-se a mutações da API; leituras e gravação atômica
do ledger privado não são contabilizadas como alteração de objetos Zabbix.
Não publicar arquivos privados completos: podem incluir respostas de APIs e
identificadores, ainda que a fixture desta tarefa seja fictícia.

## Tentativas anteriores e ajustes do ensaio

Os registros anteriores não foram apagados nem reclassificados como aprovados:

1. v1 foi interrompida de modo controlado: inicializava serviços NetBox
   desnecessários. Seu `finally` removeu somente recursos próprios.
2. v2 encontrou a espera de cache dos itens descobertos: passou-se a exigir
   aceite do protocolo ativo e histórico efetivamente persistido, não só HTTP 200.
3. v3 tentou um método `item.test` inexistente na API. O ensaio foi corrigido para
   injetar dados autenticados nos itens reais e conferir o pré-processamento real.
4. v4 falhou na comparação final que incluía disponibilidade/erro voláteis e
   listas sem ordem contratual. O ensaio passou a comparar todos os campos de
   configuração selecionados, canonicalizar listas e salvar antes/depois. A
   v4 não possuía os dois snapshots para atribuir retrospectivamente a diferença
   a um campo específico; não alegar diagnóstico mais preciso do que foi registrado.
5. v5 concluiu 14 etapas; motivou o reforço final da recuperação e a exigência de
   evidência material de redescoberta, em vez de somente reenviar o mesmo JSON.
6. v6 passou os cenários de falha com a recuperação reforçada, mas o testemunho
   baseado em descrição expirou: leitura da API mostrou descrição vazia nesta
   versão do template. O ensaio foi corrigido para adicionar um terceiro serviço
   inteiramente fictício via LLD, observar o item/trigger realmente criados e
   exigir que sua regra genérica, fora do escopo da política, continue habilitada.
   Não foi alterada a política para satisfazer esse teste. Não usar a descrição
   do template da versão mais recente como prova do comportamento da 7.4.13.
7. v7 falhou ao aguardar a primeira detecção depois do corte. A API confirmou
   status habilitado e valores de falha persistidos, mas não houve evento no
   prazo do ensaio. O produtor tinha parado após quatro amostras, permitindo que
   as janelas aceleradas expirassem enquanto se aguardava a avaliação assíncrona.
   A causa exata do atraso não foi isolada. Na v8, o produtor fictício permanece
   ativo até detecção, com prazo de 150 s e confirmação de aceite de cada envio;
   o tempo dessa espera é registrado. Isso não comprova captura de um único evento
   curto durante o corte, nem um SLA de latência em produção.
8. v8 concluiu as 14 etapas, incluindo redescoberta com testemunho material e
   rollback. A espera adicional de detecção com produtor ativo foi 0,157 s após
   as quatro amostras iniciais; não é medida de latência ponta a ponta Windows.

## Limites e critérios antes do LAB01

O ensaio usa intervalo de 1 s, janela de falhas de 8 s, transição de 12 s e
`nodata` de 30 s. Não comprova estabilidade prolongada nas janelas padrão de
60/600/600/300 s, nem resultado funcional de AppX, inventário ou tarefa Appraiser.

Ainda necessário: Windows descartável com Agent 2 da versão pertinente, tipos
reais do JSON WMI, localização/permissões/filtros/cursor dos eventos, reconexão,
rotação de logs, intervalos padrão e custo da coleta. Não iniciar serviços no DC
para produzir evidência. Falhas forçadas somente em serviços sintéticos próprios.

Ansible foi testado quanto a staging/schema/guards e repetição; o reconciliador
foi testado contra a API real separadamente. Não foi executado um playbook
Ansible completo escrevendo pela API. O CI remoto não foi acionado.

Antes de qualquer implantação: revisar diff e IDs, rota de notificações e tags
herdadas, obter janela específica, conferir backups do Zabbix/configuração/ledger
e snapshot apropriado. Hosts elegíveis a chamados ou rotas desconhecidas são
recusados, não contornados. Não há alteração automática do agente, firewall ou DC.

Rollback restaura os status antigos e desabilita apenas as regras substitutas
registradas. Não restaura banco/VM, não exclui volumes, não remove histórico e não
declara uma falha antiga recuperada. Concorrência ou resposta perdida numa criação
podem exigir inspeção manual; não apagar o ledger ou adotar objetos pelo nome.

## Evidências, revisão e encerramento

O arquivo privado final `evidence-v8.private.tar.gz` contém 36 arquivos verificados
por leitura integral e SHA-256: logs, respostas da fixture, configuração fictícia,
ledger após rollback e manifesto. A configuração em arquivo corresponde ao
dry-run inicial `observe`; os cortes posteriores estão no harness, nos estágios
registrados e no ledger. Não apresentá-la como export da fase `enforce`.

Os oito arquivos de evidências, inclusive tentativas que falharam, foram
conferidos por hash. O validador de publicação original do repositório passou em
uma cópia privada contendo somente os 14 caminhos desta tarefa; isso não atesta
a publicabilidade das anotações ou alterações anteriores mantidas no workspace.

Às 21:17:03 UTC (18:17:03 UTC−03), a conferência final confirmou: fontes executáveis
idênticas à cópia testada; recursos Docker próprios das oito tentativas removidos
por propriedade/IDs; zero containers remanescentes dessas fixtures; VM descartável
desligada de forma normal. As VMs externas que estavam ligadas na linha de base
continuavam ligadas. Nenhuma restauração, limpeza ou comando em LAB01/DC/OPS.

O diff entregue é específico desta tarefa e inclui arquivos novos; não depende
de `git diff` sozinho para mostrá-los. Nenhuma implantação deve ser inferida do
resultado do ensaio. A próxima etapa é revisar o diff e concluir o aceite Windows
nativo em isolamento, antes de propor qualquer janela do LAB01.
