# Gestão de mudanças

## Antes da mudança

1. defina objetivo e escopo;
2. identifique serviços e dependências;
3. classifique o risco;
4. prepare rollback;
5. tire snapshot ou backup proporcional ao risco;
6. valide espaço, memória e saúde atuais;
7. abra manutenção no Zabbix quando houver impacto.

## Preparação

Nunca edite primeiro o arquivo ativo. Trabalhe em cópia, execute a validação e promova somente depois:

```bash
docker compose -f /tmp/compose.candidate.yaml config --quiet
```

Para configurações montadas por bind, considere que substituir o arquivo pode mudar o inode. Alguns processos precisam de reload ou recriação controlada do container.

## Aplicação

- recrie somente o serviço necessário;
- preserve volumes;
- acompanhe logs;
- evite atualizar componentes não relacionados;
- registre a versão anterior e a nova.

## Validação

- estado dos containers;
- healthchecks;
- targets Prometheus;
- mapa e triggers Zabbix;
- acesso local;
- acesso externo e desafio de identidade;
- consumo de recursos;
- integridade dos dados.

## Rollback

O rollback deve:

- restaurar o arquivo anterior;
- recriar somente serviços afetados;
- manter dados persistentes;
- ser executável sem depender de memória informal;
- terminar com nova validação.

## Evidência

Registre:

- data e responsável;
- motivação;
- arquivos alterados;
- versões;
- validações;
- resultado;
- ação de rollback, mesmo quando não utilizada.
