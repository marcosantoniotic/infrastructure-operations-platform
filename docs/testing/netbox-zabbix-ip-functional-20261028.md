# NetBox → Zabbix: aceitação funcional controlada da troca de IP

## Escopo e estado do registro

Resultado da execução: **APROVADO no ambiente isolado**, usando o candidato que,
naquele momento, ainda não estava integrado ao Git. Execução conclusiva em
**28/10/2026, 23:50:36–23:50:52**,
`America/Sao_Paulo` (UTC−03:00), equivalente a 29/10/2026, 02:50:36–02:50:52 UTC.
Não é aprovação de deploy no LAB01/OPS. Naquela execução, nenhuma publicação
externa foi feita. A revisão posterior para publicação está registrada abaixo.

Código local de referência: `dcfb850c0ec94fecd32095a2f6a96ecfd10c3b9d`.
A referência remota consultada foi `a57c1a46043f03dcb7a3a96f2c4480cdb02a4b53`.
O arquivo-base do sincronizador era idêntico nas duas revisões (blob Git
`86d78c15d2632b1598c5d42121bb17c2dadc45f3`). Não foi feito checkout, merge,
commit ou push durante o teste; alterações locais preexistentes foram preservadas.
O candidato efetivamente testado contém o patch mínimo descrito abaixo,
com SHA-256 `7d15091e04daa83d3cd4380145175708c2999b8e259de6014fea6af17c2426f6`.
A revisão-base, sozinha, **não identifica esse candidato com alterações locais**.

## Revisão para publicação autorizada — 29/10/2026

Após autorização específica para publicar um PR, a branch de revisão foi
atualizada por fast-forward para a `main` `a57c1a46043f03dcb7a3a96f2c4480cdb02a4b53`,
preservando o trabalho local. O sincronizador mantém exatamente o SHA-256 do
candidato validado. O JSON histórico também permanece intacto; não houve nova
execução de APIs, provisionamento ou acesso ao LAB01/OPS nessa revisão.

- 19 testes de reconciliação executados novamente: aprovados.
- 7 [testes offline do registro público](../../scripts/tests/test_netbox_sync_evidence.py): aprovados.
  Conferem integridade do arquivo, identidade/IP/interface, preservação,
  idempotência, limpeza, endereços de documentação e ausência de chaves de
  credenciais. Não substituem nem simulam uma nova execução das APIs.
- Harness e extrator recusam Python otimizado (`-O`), antes de qualquer setup,
  para impedir que suas travas baseadas em `assert` sejam removidas.
- Compilação Python e validações de estrutura Ansible, publicação, credenciais,
  imagens fixadas, privilégios e referências imutáveis de Actions: aprovadas.
- A [validação CI](../../.github/workflows/validation.yml) passa a incluir os
  sete testes do registro. Renderização Ansible/Jinja e os demais jobs remotos
  são responsabilidade do CI; seu estado deve ser conferido no PR, sem inferir
  aprovação a partir das verificações locais.

As três imagens locais não relacionadas ficam fora da seleção de arquivos do
PR. Logs privados, dumps, certificados, chaves e backups não são publicados.
Publicar a branch/PR não autoriza merge, release, postagem no LinkedIn ou deploy.

## Segurança e desenho

- Duas aplicações novas na VM descartável de testes, sem inventário/dados do
  LAB01 ou OPS, sem redes/volumes externos, sem portas publicadas.
- Uma rede Docker interna exclusiva, serviços novos e identificação do projeto
  e de seus recursos por rótulo de propriedade da execução.
- NetBox 4.6.10 e Zabbix 7.4.13, com bancos novos. APIs acessadas por HTTPS com
  CA fictícia exclusiva e validação de cadeia/hostname ativa. O proxy termina
  TLS; os backends HTTP ficam somente na rede interna descartável.
- Nenhum controlador, equipamento, nome, IP ou credencial real é usado no teste.
  A: `198.51.100.10/32`; B: `203.0.113.20/32` (endereços de documentação).
- Dispositivo `planned`, host Zabbix desabilitado, sem destinatários de alertas.
  A interface secundária fictícia permite verificar a preservação do estado
  que não pertence à integração.
- Sem serviço/loop de sincronização nesta fixture. Execuções únicas explícitas;
  nenhum agendamento existente foi interrompido ou modificado.
- O arquivo candidato é copiado integralmente, sem substituir seu ORM ou sua
  lógica de reconciliação. Um invólucro no harness encaminha as chamadas reais
  e recusa escritas fora do único host/interface desta execução. Isso não
  substitui as APIs por mocks. O patch local trata somente a serialização de tags.
- Preflight exige inventário novo vazio, ausência de hosts previamente
  gerenciados, escopo exatamente unitário e ausência de VMs. Não é um
  `--apply` global sobre o laboratório.

## Procedimento reproduzível (somente host descartável aprovado)

1. Revisar [gerador da fixture](../../scripts/tests/fixtures/netbox_zabbix_ip_prepare.py)
   e [harness](../../scripts/tests/functional_netbox_zabbix_ip.py).
2. Gerar um diretório **novo**, fora do repositório e protegido, usando um
   `--run-id synthetic-ip-<identificador-unico>` e a revisão efetiva.
   O gerador recusa reutilizar o diretório. A imagem NetBox customizada deve
   existir localmente, construída e identificada previamente; não é uma imagem
   privada a ser buscada em um registry externo.
3. Copiar o sincronizador sem modificações para `netbox-zabbix-sync.py` e o
   harness para `functional.py` nesse diretório. Registrar hashes e versões.
4. Validar `docker compose config --quiet`, a ausência de portas e redes
   externas, e o estado dos demais containers. Subir **somente** esse projeto.
5. Aguardar migrations, criação do administrador e prontidão real das APIs
   HTTPS. Container em execução não significa aplicação pronta.
6. Executar o harness uma vez no container NetBox da fixture, como root apenas
   para ler/gravar os segredos e evidências privados montados. O código usa
   REST autenticada para preparar/consultar NetBox e JSON-RPC autenticada para
   Zabbix; a reconciliação usa o ORM original do sincronizador.
7. Conferir `result.json`, cada evento, snapshots de API, RPCs reais e a limpeza.
   Uma falha não deve ser substituída por uma aprovação manual.
8. Arquivar evidências privadas, produzir versão pública por allowlist e
   verificar os hashes. Encerrar/remover somente recursos da fixture depois de
   conferir seus IDs e rótulos. Nunca usar prune global.

## Evidências e resultado

A [evidência pública JSON](../evidence/netbox-zabbix-ip-functional-20261028.json)
foi extraída por [allowlist](../../scripts/tests/fixtures/netbox_zabbix_ip_public.py)
das respostas reais. Contém eventos com horários, snapshots antes/depois,
RPCs, versões e hashes dos arquivos privados de origem. Os IDs abaixo pertencem
somente à fixture descartável, não ao LAB01 ou OPS. Identidade sintética
consistente da execução final: `synthetic-ip-20261028`.

| Etapa | Esperado | Observado | Resultado | Referência |
|---|---|---|---|---|
| Preflight | Inventário exclusivo, sem pendências reais ou corrida do scheduler | 0 dispositivos/VMs/IPs prévios; 0 hosts gerenciados; 0 mídias de notificação; nenhum loop de sync na fixture | aprovado | JSON `events: preflight`; baseline privado |
| A | Dispositivo elegível com primário A | Device ID `5`, status `planned`, tag exclusiva, `198.51.100.10/32` | aprovado | JSON `snapshots.C-initial` |
| B | Dry-run sem escrita e criação de exatamente um host | Dry-run: 1 criação prevista/0 escritas; apply: host `10784` desabilitado, IP A | aprovado | `B-preflight`, `B-C`; `B-create-rpc.json` privado |
| C | IDs rastreáveis e vínculo persistido | Device `5`, host `10784`, interface principal agente `88`; host ID salvo no NetBox | aprovado | `snapshots.C-initial` |
| D | Estado local fora da responsabilidade da integração | Tag `local-test-owner`, descrição local e interface secundária `89` estabelecidas | aprovado | `snapshots.D-local-state` |
| E | Alterar apenas a referência de IP primário do dispositivo | NetBox B (`203.0.113.20/32`), Zabbix ainda A; PATCH contém só `primary_ip4` | aprovado | `snapshots.E-before-apply`; harness |
| F–G | Atualizar a interface certa sem duplicação | Uma chamada `hostinterface.update`, interface `88`, IP B; mesmo host `10784`; exatamente 1 host com a identidade NetBox `5` | aprovado | `ip_change_rpc`; `events: F-G` |
| G — preservação | Manter estado fora da integração | Tag local, descrição, interface `89`, grupo/template vinculados e demais campos de configuração retornados preservados | aprovado | `snapshots.D-local-state`, `G-after`; comparação completa no harness |
| H | Idempotência após a troca | `changes=0`, 0 RPCs de escrita, configuração e `last_updated` do dispositivo inalterados | aprovado | `idempotence_rpc: []`; `events: H` |
| J — suplementar | Atualizar tag gerenciada preservando a tag local | `planned → offline`, ambos desabilitados; uma chamada `host.update` aceita, local preservada, repetição sem escrita | aprovado após correção | `J-supplemental`, `J-idempotence` |
| Fora do escopo | Nenhum objeto não pertencente ao teste modificado | Configuração dos hosts preexistentes da fixture igual; alertas 0 → 0; nenhum inventário real acessado | aprovado | `outside-scope`; fingerprints privados |
| I | Limpeza por ID/propriedade e baseline restabelecido | Todos os objetos do ledger removidos; contagens NetBox voltaram a 0; baseline Zabbix igual; credenciais efêmeras revogadas | aprovado | `events: I`, `cleanup`; ledger privado |
| Isolamento | Não afetar serviços existentes ou publicar portas | 24 containers preexistentes com mesmos IDs, estado e horário de início; 8 containers novos, rede interna, 0 portas publicadas | aprovado | `isolation`; metadados privados |
| Encerramento | Remover somente os recursos Docker desta execução | 8 containers, 5 volumes exclusivos e 1 rede removidos após conferir propriedade e ausência de compartilhamento | aprovado | `resource_cleanup`; ledger privado de recursos |
| Testes offline | Regressão e contrato determinístico sem rede | 19 testes passaram; antes do patch o novo caso de tags falhava | aprovado (unitário, não substitui APIs reais) | `test_netbox_vm_sync.py`; logs privados |

Versões observadas: NetBox `4.6.10-Docker-5.0.2`, Zabbix `7.4.13`, pacotes
Topology Views `4.5.1` e QR Code `0.0.21`. Imagens exatas constam do JSON;
IDs/digests locais estão nos metadados privados. A fixture Compose passou em
`config --quiet`; Python compilou, os testes passaram e a validação de
publicação foi executada localmente. Não houve execução do CI remoto.
Após o encerramento, uma nova conferência confirmou os mesmos 24 containers
preexistentes (IDs, estado e horário de início), ausência dos recursos removidos
e o mesmo hash do candidato. O registro privado é `post-teardown-check.json`.
Não foi executado provisionamento Ansible. Uma checagem auxiliar de renderização
Jinja não pôde rodar por ausência do módulo no Python auxiliar; não é declarada
como aprovada. O template alterado não contém interpolação Jinja e seu Python
foi compilado e executado efetivamente na reconciliação real.

## Falhas observadas, correção e repetição

Nenhuma tentativa anterior foi apagada ou reclassificada como aprovada:

1. **Prontidão/bootstrap:** o frontend ainda estava em migrations na primeira
   tentativa. Depois, Zabbix exigiu `current_passwd` ao trocar a senha inicial.
   Não houve reconciliação nessas falhas. Foram corrigidas as pré-condições do
   harness; a credencial NetBox já emitida foi revogada por ID inspecionado.
2. **Preparação de tag:** `selectTags=extend` devolve `automatic`, campo somente
   de leitura. Reenviar a resposta inteira em `host.update` falhou. O setup
   passou a enviar somente os campos de entrada `tag` e `value`; a comparação
   da presença de tag também passou a conferir esses campos sem exigir que o
   servidor omita metadados de saída. Limpeza por IDs validada em cada tentativa.
3. **Defeito real no sincronizador:** a troca A → B e a idempotência já passavam
   na versão-base (device `3`, host `10782`, interface `84`). Porém, um teste
   adicional de tag gerenciada reproduziu a rejeição `unexpected parameter
   "automatic"` em uma chamada real do próprio sincronizador. O caso offline
   correspondente falhou antes da correção. O patch mínimo troca a cópia do
   dicionário completo pela preservação de `tag`/`value` das tags locais. Não
   modifica seleção, templates, IPs, permissões, TLS ou agenda.
4. **Comparação de conjuntos:** a API aceitou o patch, mas a primeira comparação
   suplementar apontou diferença. A exportação privada inicialmente recebeu
   `Permission denied`; o trabalho protegido foi interrompido, o usuário
   autorizou exportação via sudo, e os arquivos originais não tiveram permissões
   ampliadas. A análise dos snapshots confirmou a mudança planejada de
   `netbox_status` e reordenação das tags, sem outra diferença de configuração.
   A comparação passou a ordenar coleções sem ordem semântica. Autotestes
   comprovam que ainda detecta IP/porta/tag alterados, interface perdida e outra
   identidade. A execução completa foi então repetida: **12 eventos PASS**.

Arquivos privados das tentativas: `attempts/01-setup-tag-input`,
`02-readonly-metadata-comparison`, `03-production-tag-regression` e
`04-tag-order-comparator`. A execução conclusiva está em `evidence/` no arquivo
protegido final. Não houve restauração de dados reais para produzir aprovação.

## Integridade e publicação

Logs, respostas completas, ledgers e resultados intermediários permanecem no
destino privado autorizado, fora do Git. Cópias verificadas por SHA-256:

| Arquivo privado | SHA-256 |
|---|---|
| `protected-evidence-before-comparison.tar.gz` | `5bfa47f6a6311cf7888b19112c62447af849baa2358fa49285d6e9ead54047fb` |
| `protected-evidence-final-before-teardown.tar.gz` | `3a427339dcf811d6f2f8656a4a6a2146f73279d70ed42fac1560571fa162b8e6` |
| `protected-resource-cleanup.tar.gz` | `b1520d30751d31e7c9a67923c056f8b72186c9371ade32e3ee2645608b117c61` |
| `protected-final-result.tar.gz` | `c649ed948a685c0d86775bbcc3589d19d54f045218d80dfe55f3d934dc8d8e3a` |

JSON sanitizado: SHA-256
`02bcfa3910e0dfe75deb086c7ec5b4900c0315298741dec1a7f437fc746091cf`.
As extrações no E: mantêm a ACL restrita ao usuário autorizado e SYSTEM.
Nenhum token, senha, cookie, chave privada, inventário ou topologia real foi
incluído no extrato público. Não foram produzidas capturas de UI: são evidências
de APIs reais, não telas simuladas. Imagens preexistentes não relacionadas
foram preservadas sem alteração.

## Limpeza e rollback

O ledger é persistido a cada criação NetBox e a cada resposta `host.create`.
O harness remove somente IDs constantes desse ledger, conferindo marcadores de
origem e tags de propriedade. Remove referências de IP do dispositivo próprio,
exclui os objetos em ordem inversa de dependência e verifica a ausência por ID.
Os snapshots de configuração dos hosts não pertencentes ao teste devem
coincidir antes/depois, desconsiderando campos operacionais voláteis da
interface (disponibilidade/erro/temporização) e a ordem semântica irrelevante das
coleções de tags/interfaces/grupos/templates. Nenhum valor de configuração é
descartado para aprovar o resultado.

Rollback da mudança de IP, se fosse necessário antes da limpeza: atribuir A
novamente **somente** ao dispositivo próprio e reconciliar sob a mesma trava;
não restaurar bancos, snapshots ou volumes compartilhados. A limpeza final
elimina os objetos sintéticos. Nunca excluir por nome isoladamente. Se a
identidade/propriedade não puder ser comprovada, interromper e conservar o
ledger para revisão. Credenciais efêmeras devem ser revogadas.

Rollback do código proposto: reverter o commit em uma revisão específica, sem
restaurar bancos, snapshots ou volumes. Isso reintroduz a limitação de
serialização de tags da versão anterior; não é uma correção alternativa.
Qualquer aplicação ou rollback operacional precisará de autorização própria.

## Limitações da conclusão

Este exercício valida o **plano de controle** da sincronização de IP. O host
permanece desabilitado, sem agente nos IPs de documentação. Não comprova coleta,
resposta do agente em B, recuperação do monitoramento, triggers, entrega de
alertas, GLPI, carga/concorrência, aplicação em produção ou mudanças em VMs.
Não é teste de menor privilégio do token: a fixture usa administrador sintético
para setup e execução; a autorização restrita de produção não é reproduzida.
Não é teste de login/cookies/plugins; versões instaladas não equivalem à
cobertura funcional desses componentes. Não houve acesso ao LAB01 ou OPS.
Tags de descoberta automática (`automatic=1`) e hosts criados por LLD não foram
testados; a regressão coberta usa uma tag local manual (`automatic=0`).

Capturas de interface são opcionais: se não forem produzidas, a evidência será
descrita como resposta real de API, nunca como captura visual ou ilustração.

## Rascunho factual para LinkedIn — não publicado

> Validei em ambiente isolado a sincronização de IP primário do NetBox para o
> Zabbix. Um dispositivo sintético passou de 198.51.100.10 para 203.0.113.20,
> atualizando a mesma interface do mesmo host, sem duplicação. Tag local,
> descrição e interface secundária foram preservadas, e uma nova reconciliação
> não gerou alterações. Um teste adicional revelou e permitiu corrigir o reenvio
> de metadados somente de leitura nas tags. As evidências vêm das APIs reais;
> os objetos de teste foram removidos. O teste comprova a sincronização do
> cadastro, não resposta de agente, retomada de coleta ou funcionamento em
> produção. A correção é proposta para revisão, sem implantação em produção.

Antes de publicar, revisar o patch e o conteúdo sanitizado. Não afirmar que a
correção já está na main, no LAB01 ou no OPS. O teste não envolveu push, release
ou postagem; a publicação posterior do PR depende da autorização registrada acima.

## Arquivos da alteração

- [Sincronizador](../../roles/netbox_zabbix_sync/templates/netbox-zabbix-sync.py.j2): patch mínimo de tags.
- [README da role](../../roles/netbox_zabbix_sync/README.md): comportamento, escopo e referência da prova.
- [Testes offline](../../scripts/tests/test_netbox_vm_sync.py): interface/IP, dry-run e tags com metadados de leitura.
- [Contrato das evidências](../../scripts/tests/test_netbox_sync_evidence.py) e [CI](../../.github/workflows/validation.yml): consistência offline e recusa de otimização insegura dos utilitários.
- [Harness funcional](../../scripts/tests/functional_netbox_zabbix_ip.py): APIs reais, trava por identidade, provas e limpeza.
- [Gerador isolado](../../scripts/tests/fixtures/netbox_zabbix_ip_prepare.py): aplicações novas, CA fictícia e nenhuma porta publicada.
- [Extrator público](../../scripts/tests/fixtures/netbox_zabbix_ip_public.py): allowlist e hashes, sem baselines/credenciais.
- Este relatório, o [JSON de evidências](../evidence/netbox-zabbix-ip-functional-20261028.json) e a [matriz de evidências](../evidence/evidence-matrix.md).

Nenhuma alteração foi implantada no LAB01/OPS. Backups, certificados, dumps e
logs privados não fazem parte desses arquivos versionáveis.
