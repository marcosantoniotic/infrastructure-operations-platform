# Agent 2 e leitores Windows — resultados nativos isolados

**Revisão posterior:** a [revisão de publicação](windows-service-policy-review-2026-11-05.md)
reproduziu e corrigiu dois gaps de metadados não cobertos por este ensaio.
Os novos guards são testados separadamente; o recorte nativo abaixo não foi
reexecutado nem reclassificado como ensaio do código corrigido. PR em rascunho,
sem aprovação de implantação.

Data de operação: **05/11/2026, America/Sao_Paulo (UTC−03)**. Leituras e ensaios
funcionais ocorreram aproximadamente entre 21:51 e 22:12, correspondendo a
06/11/2026 00:51–01:12 UTC.

**Resultado funcional: APROVADO NO RECORTE EXECUTADO.** Foram aprovadas 20
checagens nativas automatizadas, além do ciclo real de corte, idempotência e
rollback da política. **Não é autorização de implantação no LAB01/OPS nem aceite
de estabilidade prolongada ou de todas as variantes Windows.** Os limites abaixo
continuam relevantes para a revisão de aplicação.

Base local: `a899d1b0c8ca9f052c8c575a0d5b61ae3556a465`, mais o candidato local
da política e alterações anteriores preservadas. Não houve commit, push, PR, CI
remoto ou implantação nesta etapa. A [etapa anterior](windows-service-policy-2026-11-05.md)
usou mensagens PSK sintéticas; **esta etapa utilizou o Agent 2 Windows real**,
sem sender, valores injetados ou descoberta fabricada.

Nenhuma implantação no LAB01/OPS. Nenhuma conexão aos serviços ou comando nas VMs
do LAB01, DC ou OPS. As VMs externas que estavam ligadas na linha de base continuam
ligadas. Não foi iniciado serviço no DC do laboratório.

## Versões, desenho e escopo

- Windows Server 2025 Standard Evaluation Desktop Experience, en-US, versão
  nativa `10.0.26100`, instalado em disco novo, fora do domínio.
- Agent 2 Win64 OpenSSL **7.4.13**, revisão `3c950006297`, executado como
  **LocalSystem**. Artefato obtido do CDN oficial e assinatura verificada na
  preparação; hashes da mídia e MSI constam no histórico abaixo.
- Zabbix server/web **7.4.13**, MySQL **8.4.10**, Traefik **3.7.13**, volumes e
  credenciais exclusivamente fictícios. API HTTPS com cadeia e hostname
  verificados; canal ativo Agent 2–Zabbix autenticado por PSK própria.
- Um único host descartável, referenciado publicamente como **NATIVE-1**.
  A identidade do host e dos itens foi mantida no corte/rollback. Os IDs reais
  desta fixture estão somente nos registros privados.
- Rede Windows exclusivamente em LAN segment, sem gateway/DNS, bridge ou NAT.
  Relay TCP opaco limitado à interface privada e à origem Windows de teste;
  sem terminação TLS e sem posse da PSK. APIs sem portas publicadas.
- Consultas reais de AppXSvc/InventorySvc somente de leitura. Crash, início,
  parada, configuração e remoção/recriação somente nos serviços próprios
  `IOPWspNativeAlpha` e `IOPWspNativeBeta`. A projeção de teste foi gerada pelas
  mesmas definições, substituindo nomes, ownership e timings; o escopo fixo do
  reconciliador não foi ampliado.

## Matriz de evidências

As referências são basenames na pasta privada da execução; não publicar os
arquivos integrais. `check-*.private.json` contém snapshots reais das APIs e
seus horários, não somente o resultado booleano.

| Ensaio | Observado | Resultado | Referência |
| --- | --- | --- | --- |
| WMI nativo e consulta vazia | Dois serviços, códigos numéricos; consulta sem serviços retornou `[]` | PASS | `backend-raw-*.private.json`, antes da criação dos serviços sintéticos |
| Cadência padrão | 15 itens suportados, pelo menos 16 amostras por item a 60 s; itens antigos continuam com histórico | PASS | `native-core-history.private.json` no arquivo do backend |
| `skip` e 1077 | Evento SCM 7034 anterior não repetido; Beta nunca iniciado separado de crash | PASS após warmup | `check-projection-initial-attempt-2.private.json`, `action-0003.private.json` |
| Execução e parada normais | Códigos zero; parada não gera falha apenas por estar parado | PASS | `check-running.private.json`, `check-stopped.private.json` |
| Crash genuíno | Evento SCM, código 1067 e falha da trigger; filtro contém acentos, colchetes, parênteses e `+` | PASS | `check-crashed.private.json`, EVTX e eventos SCM exportados |
| Falha não some por silêncio/parada limpa | Permaneceu ativa depois da janela de falhas, com serviço parado e códigos limpos | PASS | `check-latched.private.json` |
| Recuperação | Recuperou após observações limpas em execução e janela sem falhas | PASS | `check-recovered.private.json`, `check-recovered-attempt-2.private.json` |
| Startup divergente e restaurado | Manual detectado; Auto restaurado com recuperação | PASS | `check-drift.private.json`, `check-drift-restored.private.json` |
| Ausência e recriação | Ausência detectada; recriação recupera presença e mantém 1077 distinto | PASS | `check-missing.private.json`, `check-reappeared.private.json` |
| Start Pending prolongado | WMI nativo e trigger de transição observados juntos | PASS | `check-pending.private.json` |
| Evento novo e cursor após reinício | Evento contado; reinício do agente não repetiu evento já contado | PASS | `check-custom-positive.private.json`, `check-custom-clean.private.json` |
| Rotação do canal próprio | EVTX prévio arquivado/hash conferido; leitura retomada após rotação | PASS | `action-0017.private.json`, `check-custom-rotated.private.json` |
| Permissão insuficiente | Item ficou não suportado com erro; não virou zero saudável | PASS | `check-custom-denied.private.json` |
| ACL restaurada | Item suportado e evento novo contado após restauração da ACL original | PASS | `check-custom-supported.private.json`, `check-custom-restored.private.json` |
| Conexão ativa indisponível e recuperada | Nodata disparou; coleta voltou e ambas as triggers de perda de observação recuperaram | PASS | `check-lost.private.json`, `check-recovered-attempt-3.private.json` |
| Observe e repetição | 25 criações; repetição sem novas escritas; triggers novas desabilitadas | PASS | `native-observe-result.private.json` |
| Corte real e rollback | 12 mudanças, repetição 0, rollback 12, volta a observe 0; IDs preservados | PASS | `native-core-cutover-cycle.private.json` |
| Escopo e notificações | Demais hosts da fixture iguais à baseline, um host próprio, zero alertas enviados | PASS | `native-outside-verification.private.json`, `cleanup-*.private.json` |

O primeiro `check-projection-initial.private.json` falhou porque foi iniciado
antes do primeiro valor de evento; Zabbix informou dados insuficientes no
`nodata`. A falha foi preservada. A repetição ocorreu depois do warmup, mantendo
as mesmas exigências e reforçando a checagem de 1077; não houve relaxamento do
reconciliador ou fabricação de dados. A primeira tentativa de observe também
expirou aguardando descoberta nativa, cujo intervalo oficial era uma hora.

Para antecipar **leituras reais**, foi validado o parâmetro de agente
`ForceActiveChecksOnStart=1`, preservada a configuração anterior e reiniciado
somente o Agent 2 descartável. O template e sua cadência de descoberta de uma
hora não foram alterados. A descoberta então criou as duas regras esperadas.

## Preservação, rollback e estado final

- Política real retornou a observe: dez triggers novas desabilitadas e duas
  antigas habilitadas. A projeção sintética também foi desabilitada por IDs e
  ownership confirmados. Nenhum item, evento, histórico ou volume excluído.
- Os serviços próprios e o agente foram parados; ACL original e regra de saída
  do Windows foram restauradas. AppXSvc/InventorySvc foram apenas consultados:
  no início estavam Running e ao final Stopped com códigos zero, por atividade
  natural do Windows; nenhum comando os iniciou/parou.
- Windows exportou três EVTX e os eventos SCM próprios. **O System não foi
  limpo.** São 42 arquivos no ZIP, conferidos individualmente por hash e CRC após
  transferência. Dump transacional e configurações da fixture foram arquivados.
- Containers e rede próprios removidos **sem apagar volumes**; relay e regras
  temporárias próprios removidos. Não havia outros containers em execução.
  Ambas as VMs descartáveis foram desligadas suavemente. A placa adicional de
  teste do Rocky foi retirada com a VM desligada, preservando a configuração NAT.
- Não foi usado restore de banco/VM como rollback da política. Não houve
  provisionamento completo, alteração de serviços reais, de OPS, DC ou MikroTiks.

Arquivos privados protegidos no E:, fora do repositório:

| Artefato | SHA-256 |
| --- | --- |
| `windows-native-evidence.private.zip` | `bbe43f6723c25a6242a53aace2562b28bdc5386e476e85cf2e55244740d34efe` |
| `pre-native-backend.private.tar.gz` | `96075a56e6e08d2456f730177d90fadb83ba506812187d9c0240e187663a919c` |
| `post-native-backend.private.tar.gz` | `08b1b1d99eafab23f8b16dae127f97b794898d16628573f3ec46375972b614a8` |

Arquivos do backend incluem credenciais fictícias: **não publicar**. Os discos
das VMs e os volumes de dados também foram preservados. Backups do LAB01/OPS
não foram acessados ou alterados.

## Limites e gate antes do LAB01

1. Windows en-US fora de domínio. Nomes sintéticos com acentos/metacaracteres
   foram testados; isso não prova todos os idiomas nem o comportamento de um DC.
2. Falhas/estados sintéticos usaram intervalo 3 s, janelas 12 s e nodata 30 s.
   A política real coletou a 60 s, mas não foi provocado um Start Pending de
   600 s nem um ensaio de falha/recuperação de dez minutos. Não é teste de carga,
   longevidade ou retenção prolongada do System.
3. Permissões e rotação negativas foram testadas no canal próprio, não mudando
   ACL/limpeza do System nem permissões WMI globais. Outros códigos Win32/SCM,
   além dos observados, continuam cobertos por contratos offline, não por falhas
   físicas nativas reproduzidas para cada código.
4. O peer visto pelo Zabbix é o relay/gateway Docker; não se validou auditoria de
   IP de origem nem o caminho/firewall real do LAB01. Não é ensaio ponta a ponta
   NetBox–Zabbix–GLPI, de tarefas de inventário ou de implantação AppX.
5. Antes de qualquer aplicação: revisão do diff, escopo/IDs/templates/rotas de
   notificação reais, aprovação específica, snapshots/backups/ledger protegidos
   e janela de observe. Nenhum serviço do DC deve ser iniciado para tornar
   observações verdes. Rollback deve atuar somente nos status registrados,
   preservando dados e eventos, sem restaurar banco ou excluir volumes.

## Diff desta etapa

Nesta etapa histórica, o reconciliador e seus guards permaneceram inalterados.
SHA-256 LF do core efetivamente ensaiado:
`8629898892d4e632bd237f25f621594c0dd0231d75ae4241842a7d599583005b`.
A correção posterior dos guards de chamado/ownership modifica o hash do core,
mas preserva as definições WMI, normalização e triggers. Não se alegam novos
testes Windows dessa revisão: regressões offline e CI de API real são evidências
separadas. A execução nativa usou as mesmas definições do candidato anterior.
Fixtures de serviço Windows estão
em `scripts/tests/windows/NativeServiceFixture.cs` e
`scripts/tests/windows/Invoke-NativeServiceFixture.ps1`; orquestração e entradas
privadas ficam fora do repositório. Documentação recebe resultados e referências
cruzadas. Alterações locais de outros trabalhos não fazem parte deste diff.

Na conferência final, passaram novamente os 25 testes unitários da política e
os 14 testes de regressão offline de transição de perfil NetBox. Estes últimos
usam APIs falsas, não são novas escritas no laboratório. O diff de revisão foi
analisado pelo Git sem aplicá-lo; o HEAD permaneceu na revisão indicada.

## Preparação e integridade dos artefatos

Instalação limpa a partir do Evaluation Center da Microsoft, sem clonagem de
máquinas ou dados do domínio. A ausência inicial da mídia do VMware Tools
interrompeu o bootstrap; a instalação local do Tools e um reinício controlado
somente da VM descartável permitiram retomar a preparação protegida.

A declaração de porta no Compose não criou um listener na rede interna; isso
foi diagnosticado por inspeção e tentativa de conexão. A instrumentação
descartável passou a usar o relay privado descrito acima e uma regra temporária
restrita a origem/destino/porta de teste, removida ao final. Não desativar
firewall ou TLS para reproduzir o ensaio.

SHA-256 medido da ISO efetivamente baixada:
`7b052573ba7894c9924e3e87ba732ccd354d18cb75a883efa9b900ea125bfd51`.
Esse valor comprova identidade do artefato desta execução, não é apresentado
como checksum publicado pela Microsoft.

SHA-256 do MSI do Agent 2:
`afa7bda5ed73cb99d1f81ca82bf7d8669c0f3332ee10bdaee328963e45b48569`.
Assinatura Authenticode verificada, signatário Zabbix SIA.

Fontes: [Microsoft Evaluation Center](https://www.microsoft.com/en-us/evalcenter/download-windows-server-2025)
e [MSI oficial do Agent 2 7.4.13](https://cdn.zabbix.com/zabbix/binaries/stable/7.4/7.4.13/zabbix_agent2-7.4.13-windows-amd64-openssl.msi).

O diário detalhado de preparação, falhas de acesso à console e artefatos privados
foi preservado localmente. Eles não fazem parte da documentação pública nem
substituem as evidências de coleta nativa da matriz acima.
