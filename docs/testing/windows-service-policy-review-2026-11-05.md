# Revisão da política Windows — correção dos dois guards

Data de operação: 05/11/2026, America/Sao_Paulo (UTC−03).

**PR #96 permanece em rascunho, sem merge nem implantação autorizados.**
Os dois bloqueios reproduzidos na revisão inicial foram corrigidos. Os contratos
offline passam; o CI da revisão corrigida deve concluir antes de novo aceite.
Não houve acesso ao LAB01, DC ou OPS, execução de serviços Windows ou criação
de chamados nesta correção.

## Diagnóstico original e correção

Reprodução original: `bb7d41e53ab9502ba07f564bb276f18e05ba64e5`.
As escritas abaixo ocorreram apenas em listas Python, não em ambientes reais.

| Bloqueio | Observado antes, em memória | Correção |
| --- | --- | --- |
| P1: elegibilidade de chamado na trigger | `glpi=ticket` na trigger própria permitia 12 escritas de corte | Recusa tag de chamado em triggers próprias, registradas e legadas, além de host/templates, antes de escrita na API ou ledger, inclusive no rollback |
| P2: perda de ownership | Retirar a tag de uma trigger registrada permitia uma criação adicional e duas descrições iguais | Valida todos os IDs registrados, nome e ownership exato; objeto ausente ou alterado exige inspeção, nunca recriação/adoção automática |

Também são recusados ownership duplicado/ambíguo, colisão de nome com trigger
manual e objetos próprios sem ID registrado. Itens registrados recebem a mesma
verificação de identidade. A criação parcial **com IDs persistidos** continua
retomável; resposta perdida antes de registrar um ID exige inspeção manual.
Tags locais sem elegibilidade de chamado são preservadas.

Todos os alvos passam pelo preflight e por uma última barreira de leitura antes
da primeira mutação do ledger. Essa barreira não é CAS: permanece obrigatório
um escritor único em janela controlada. Não retirar tags nem apagar o ledger
para liberar um guard, inclusive durante rollback.

## Evidências separadas por camada

| Camada | Verificação | Resultado/limite |
| --- | --- | --- |
| Contratos anteriores, APIs em memória | 25 testes de política, estado, notificações, freshness, journal, idempotência e rollback | PASS local |
| Novas regressões, APIs em memória | 10 testes, múltiplos subcasos: trigger própria/legada, host/template, dry-run/observe/enforce/rollback, ID/nome/tag alterados, itens, colisão manual, retomada parcial, tag local e drift na barreira final | PASS local; zero escritas na API/ledger nas recusas |
| API/motor Zabbix 7.4.13 real, fixture Linux própria | Adicionados 12 cenários negativos: tag de chamado, ownership ausente/incorreto × quatro modos; metadados injetados somente em trigger sintética desabilitada, restaurados em `finally` | Executado no job isolado do CI; consultar o resultado da revisão, não inferir aprovação de testes anteriores |
| Mesmo motor, caminho positivo | Criação 25, repetição 0, corte 12, rollback 12, histórico/IDs/hosts externos preservados; nova tag local deve sobreviver | Job isolado; produtor PSK fictício, não leitor Windows |
| Windows nativo histórico | 20 checagens com Agent 2 7.4.13, WMI/SCM e corte/rollback | Não reexecutado nesta correção; ver hash e limites no relatório nativo |

Os testes contra API real comparam snapshots das triggers, bytes do ledger e
tentativas de escrita do reconciliador. Injeção/restauração de metadados pertence
à fixture, não é uma escrita autorizada da política. Não se cria action, mídia ou
destinatário real. Casos de tag na trigger legada ficam nos contratos em memória:
o ensaio real não altera protótipos compartilhados nem regras descobertas.

```sh
python scripts/tests/test_windows_service_policy.py
python scripts/tests/test_windows_service_policy_review.py
```

O CI também executa guards Ansible, renderização/Compose/promtool, validações de
publicação/segurança e o motor real descartável. Não há skip/expectedFailure para
os dois contratos originais. WMI, normalizador e definições de itens/triggers
devem ser idênticos ao candidato nativo; mudanças limitadas ao preflight.

## Preservação e aplicação futura

- Atualização apenas do PR em rascunho, com índice alternativo; branch, HEAD,
  índice real e trabalhos locais não relacionados preservados.
- Sem dados privados, CA/chaves, tokens/PSK, dumps, EVTX ou ledger no PR.
- Mantidos os limites nativos: en-US fora de domínio, falhas aceleradas, sem
  ensaio de falha de 600 s, carga prolongada ou retenção longa; relay afeta peer.
- Antes de aplicar: revisão/aprovação separadas, escopo e rotas reais conferidos,
  snapshots, backups e ledger protegidos, janela observe e escritor único.
- Rollback atua somente nos status por IDs registrados; não restaura banco/VM,
  apaga histórico ou exclui volumes. Drift de segurança deve ser revisado antes.
- CI verde não remove o rascunho nem autoriza LAB01/OPS automaticamente.
