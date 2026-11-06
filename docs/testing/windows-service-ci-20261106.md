# Política Windows: corrida de observação no CI — 2026-11-06

Base: `ebc826ba9b70ca69eb91207f4b72b96df18aa782` (PR #97 integrado).
Data de operação: 06/11/2026, America/Sao_Paulo (UTC−03).
Somente código de teste/CI, fixtures fictícias e VM Linux descartável. Sem
acesso ou implantação em OPS/LAB01, agente Windows real ou início de serviços.

## Evidência e limite do diagnóstico

O [CI pós-merge](https://github.com/marcosantoniotic/infrastructure-operations-platform/actions/runs/42164331996/job/127717143016)
falhou na etapa `functional` após cerca de 34 s. O wrapper publicou apenas
`Isolated stage failed: functional; private log retained`. O run tinha zero
artefatos publicados; o log interno não pôde ser recuperado do runner encerrado.
Não se afirma conhecer a linha/causa exata daquele run nem se atribui a falha
ao OCSP. A repetição completa local do commit original passou nos 16 estágios.

Foi reproduzida uma corrida concreta, independente da repetição integral:
o predicado original `processed()` aceita `lastclock >= sent`, ambos em segundos.
Se a nova entrada `[]` (serviço ausente) é enviada no mesmo segundo da entrada
anterior válida, a API pode ainda mostrar `present=1` anterior com timestamp
igual ao do envio. O predicado declara esse resultado antigo como novo; a
asserção seguinte então falha. A reprodução executa o AST da função original,
sem copiar/reescrever o comparador e sem redes/APIs. O teste de recusa do valor
antigo falha no código sem fence, como esperado.

Evidência privada: `baseline-clock-regression.private.log` (vermelho intencional)
e `baseline-clock-reproduction.sanitized.json`. Isso comprova a lacuna do teste,
não reconstrói um log que não existe mais. A causa histórica permanece limitada
por essa ausência de evidência.

## Correção delimitada

- Registrar o clock exato de cada lote enviado, com segundos/nanos coerentes.
- Antes de cada controle de preprocessing, aguardar que o relógio real avance
  para um segundo estritamente posterior ao **último envio**, incluindo amostras
  aceitas mas ainda não visíveis na API. Não usar somente o último item visível.
- Manter as exigências originais de estado, erro, valor/presença e freshness.
  Não esperar por um valor esperado para forçar aprovação, injetar timestamps
  futuros, ampliar a janela de processamento ou alterar os tempos da política.
- Relógio parado/regressivo falha boundedly, em até 3 s de espera da fence.
- Em falha, produzir metadata sanitizada: classe de exceção, arquivo/linha
  permitidos e identificadores fixos de check. Sem mensagens arbitrárias,
  argumentos OpenSSL, tokens, PSK, cookies, URLs ou payloads de API.
- O wrapper publica essa metadata **após** o teardown validado por IDs/labels;
  logs completos permanecem privados. Diagnóstico auxiliar não substitui nem
  suprime a falha original.

Produção inalterada: role, reconciliador, definições WMI/SCM, triggers,
limiares, notificações, ledger e rollback. A fixture continua usando API/motor
Zabbix 7.4.13 reais com produtor PSK sintético, não leitor nativo Windows.

## Validação

```sh
python scripts/tests/test_wsp_ci_observation.py
python scripts/tests/test_windows_service_policy.py
python scripts/tests/test_windows_service_policy_review.py

# Exclusivamente no host descartável, com workspace novo por tentativa:
IOP_DISPOSABLE_PLATFORM_TEST=1 python scripts/ci/test-windows-service-policy.py \
  --workspace /home/vagrant/<WORKSPACE_NOVO> --revision <BASE_MAIS_DIFF_IDENTIFICADO>
```

| Validação | Resultado observado |
| --- | --- |
| Predicado antigo, falha determinística reproduzida | Uma regressão vermelha esperada: amostra anterior aceita indevidamente |
| Base original, execução completa local | 16 estágios PASS; não reproduziu a falha histórica integral |
| Novas regressões offline | 11 PASS, zero falhas/skips: resolução de segundo, amostra enfileirada, relógio parado/regressivo, entradas inválidas e privacidade |
| Contratos anteriores | 25 de política + 10 de ownership/chamados PASS, zero falhas/skips |
| Execuções completas corrigidas A / B / C | 16 / 16 / 16 estágios PASS, em projetos/bancos novos independentes |
| Identidade, histórico, corte e rollback | Preservados em cada execução; corte 12, repetição 0 e rollback 12 |
| Limpeza por ownership | Recursos fictícios removidos; containers externos iguais à baseline em cada tentativa |
| Diagnóstico no Linux por arquivo/CLI reais | PASS, sem mocks do parser/serializador e sem publicar sentinelas sensíveis |
| Validações estáticas | Layout, publicação, credenciais, imagens, privilégios, Actions, Python/YAML e whitespace PASS |

Total offline: 46 testes. Os 48 estágios integrais são três repetições da mesma
matriz, não 48 testes de negócio distintos. Não há novo ensaio nativo Windows.
A política real ficou byte a byte idêntica à base em todas as fixtures.

`evidence.sanitized.json` registra horários UTC, hashes de fontes e resultados.
Arquivo bruto privado das quatro fixtures e logs, conferido na origem e no E:
por hash e leitura integral do tar/gzip:
`fb1383686192317771d29fb7dc36adfb5717d9f659ac5eef531a7c823abd460a`.
São 462 entradas; contém credenciais e chaves **fictícias**, não publicar.
Reprodução determinística e logs completos ficam privados, fora do Git.

## Rollback e publicação

Reverter somente estes arquivos de CI/teste, se necessário. Não restaurar
bancos, volumes, VMs ou ledger operacional para reverter um teste. Não ocultar
falhas com retries até passar, skip/expectedFailure ou continue-on-error.
Cada execução conserva evidência privada e remove somente seus recursos
fictícios após conferência de IDs/labels e igualdade dos containers externos.

Alterações locais de NetBox e outros trabalhos ficam preservadas e fora do
diff. CI remoto da correção exige publicação autorizada em branch/PR separado;
o run histórico não se torna verde por causa de um teste local posterior.
Coletores/serviços da fixture foram encerrados; a VM descartável que foi ligada
para este ensaio é devolvida desligada. Nenhum backup/VM/serviço operacional ou
alteração local não relacionada foi removido ou alterado.
