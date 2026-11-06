# Revisão de publicação da política Windows — bloqueios de rascunho

Data: 05/11/2026, America/Sao_Paulo (UTC−03).

**NÃO PRONTO PARA MERGE OU IMPLANTAÇÃO.** A revisão preserva o reconciliador
ensaiado e registra dois gaps confirmados com a API **em memória** dos contratos
offline. Não houve acesso ao LAB01/OPS, execução de serviços Windows, envio de
alertas ou criação de chamados nesta revisão.

Os [20 testes funcionais nativos](windows-service-native-2026-11-05.md) continuam
válidos para o recorte que executaram. Eles não exercitaram as condições de
drift de tags abaixo e não constituem aprovação desses guards.

## Bloqueios confirmados

| Prioridade | Contrato esperado | Observado somente no fake | Antes de sair do rascunho |
| --- | --- | --- | --- |
| P1 | Trigger efetivamente elegível a chamado deve exigir revisão de notificações antes do corte | Adicionar `glpi=ticket` a uma trigger própria e uma action restrita a essa tag permite as 12 alterações de corte | Conferir elegibilidade efetiva também na trigger e recusar antes de qualquer escrita; revisar igualmente o caminho de rollback dos legados |
| P2 | Um ID de trigger registrado no ledger não pode ser recriado silenciosamente quando perde ownership | Remover a tag de ownership de uma trigger registrada permite uma criação adicional, preserva a antiga e resulta em duas descrições iguais | Validar todos os IDs/ownership registrados antes de criar; recusar drift sem adotar, retaggear ou excluir objetos automaticamente |

As observações não alegam que um chamado foi criado ou que houve duplicação em
um ambiente real. São reproduções determinísticas de lacunas do reconciliador,
com todas as escritas limitadas a listas Python em memória.

## Regressões bloqueantes

`scripts/tests/test_windows_service_policy_review.py` contém os dois contratos
que devem passar **depois** de uma correção revisada. No candidato atual ambos
falham com `ValueError not raised`. Não foram marcados como skip ou expected
failure; o CI deve evidenciar o bloqueio, não mascará-lo para publicar o PR.

```sh
python scripts/tests/test_windows_service_policy.py
python scripts/tests/test_windows_service_policy_review.py
```

O primeiro comando mantém os 25 contratos anteriores. O segundo reproduz os
dois bloqueios novos. Separar esses resultados dos ensaios reais do motor/API
Zabbix e do Windows: um não substitui nem reclassifica o outro.

## Escopo da publicação

- Role dedicada, desativada por padrão e fora de `site.yml`/sincronizador.
- Playbook, fixture fictícia, testes, integração de CI e documentação da política.
- Relatórios sanitizados dos ensaios anteriores e nativos; entradas, CA/chaves,
  tokens, dumps, ledger, EVTX e capturas privadas não são publicados.
- Alterações locais de transição de perfis, recuperação do diretório, DNS e
  outros trabalhos permanecem fora do PR.
- Sem atualização da main local, sem troca de branch do workspace e sem deploy.

## Gate antes do merge e aplicação

1. Corrigir os dois contratos sem afrouxar TLS, ownership ou rotas de notificação.
2. Reexecutar contratos, guards Ansible, testes reais de API/motor e os recortes
   nativos afetados. O hash do candidato publicado e o do ensaio nativo devem
   continuar distinguíveis se houver alteração funcional posterior.
3. Manter os limites de idioma, domínio, duração, retenção e relay do relatório
   nativo. Avaliar janelas completas e o comportamento específico do ambiente.
4. Revisão e aprovação separadas para aplicação: snapshots, backups, ledger,
   janela observe, notificações e rollback de status por IDs. Não restaurar banco
   ou excluir volumes como rollback da política.
