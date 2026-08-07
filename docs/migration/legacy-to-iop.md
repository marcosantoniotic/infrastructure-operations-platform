# Migração controlada para o Infrastructure Operations Platform

## Estratégia

A migração adotará reconstrução limpa com importação seletiva. O ambiente novo
é criado integralmente por código; o ambiente anterior fornece somente dados e
artefatos autorizados.

Não são estratégias suportadas:

- clonar a VM antiga como plataforma definitiva;
- copiar volumes Docker enquanto containers estão em execução;
- promover o ambiente novo com notificações e timers concorrentes;
- reutilizar segredos expostos em arquivos não controlados;
- substituir uma versão de banco ou aplicação sem teste de compatibilidade.

## Estados da mudança

```text
planejado
  → novo ambiente implantado
  → restauração de ensaio
  → validação funcional
  → congelamento do legado
  → restauração final
  → cutover
  → observação
  → legado preservado para rollback
  → encerramento
```

## Fase 1 — descoberta

1. inventariar versões e digests em execução;
2. identificar projetos Compose, volumes e redes;
3. identificar plugins, mídia e integrações;
4. registrar jobs, timers e retenções;
5. classificar cada dado pela matriz de migração;
6. confirmar espaço para dois ambientes e pontos de recuperação.

Saída: inventário sanitizado e plano de compatibilidade aprovado.

## Fase 2 — construção paralela

Crie `iop-ops-automation-01` e `iop-ops-platform-01` com endereços temporários.
Implante todas as aplicações sem publicação oficial e com os seguintes efeitos
desativados:

- Alertmanager e notificações do Zabbix;
- sincronização NetBox → Zabbix;
- timers de backup externo;
- rotas Cloudflare oficiais;
- tarefas de manutenção;
- qualquer descoberta que possa duplicar hosts no monitoramento.

## Fase 3 — restauração de ensaio

1. produza ou selecione um ponto de recuperação conhecido;
2. valide checksum e manifesto antes da restauração;
3. restaure banco e arquivos pelo procedimento nativo de cada aplicação;
4. execute migrações de esquema somente pela versão alvo;
5. valide login, objetos, plugins, mídia e integrações;
6. descarte dados de ensaio somente após preservar a evidência sanitizada.

Não altere DNS oficial nesta fase.

## Fase 4 — aceite técnico

O ambiente novo deve comprovar:

- healthchecks saudáveis;
- contratos HTTP esperados;
- NetBox com inventário e plugins consistentes;
- Zabbix com hosts, templates, itens e triggers esperados;
- Grafana com datasources e dashboards funcionais;
- Prometheus coletando todos os targets planejados;
- Portainer refletindo os projetos Compose;
- Traefik roteando somente pelos nomes temporários;
- backup e restauração isolada aprovados;
- consumo de CPU, memória e armazenamento dentro do dimensionamento.

## Fase 5 — congelamento e carga final

1. comunicar a janela;
2. impedir alterações no NetBox anterior;
3. suspender no ambiente anterior apenas os writers e jobs definidos no plano;
4. produzir os dumps finais;
5. registrar timestamps e checksums;
6. restaurar a carga final no ambiente novo;
7. executar o checklist de aceite novamente.

As ações de parada exigem autorização explícita da mudança.

## Fase 6 — cutover

1. apontar Cloudflare/DNS para o novo Traefik;
2. validar HTTP 200 e redirecionamentos esperados;
3. confirmar autenticação e Cloudflare Access;
4. habilitar uma única origem de alertas;
5. habilitar sincronizações;
6. habilitar timers de backup;
7. observar logs, métricas e filas.

## Rollback

O rollback permanece disponível enquanto o ambiente anterior estiver
preservado e seus dados finais forem compatíveis com o ponto de retorno.

Disparadores sugeridos:

- corrupção ou ausência de objetos críticos;
- falha persistente de autenticação;
- indisponibilidade de aplicação crítica acima do RTO;
- regressão de integração sem correção segura na janela;
- backup inicial ou restauração isolada não comprovados.

Sequência:

1. desabilitar writers, jobs e notificações do ambiente novo;
2. devolver o origin/DNS ao ambiente anterior;
3. iniciar os serviços anteriores na ordem documentada;
4. validar contratos e autenticação;
5. registrar a decisão e preservar evidências dos dois ambientes.

Não misture gravações nos dois ambientes depois do cutover. Caso o novo
ambiente já tenha recebido alterações válidas, a reversão exige plano de
reconciliação antes de retornar.

## Encerramento

Após o período de observação:

1. confirmar backups e restaurações do ambiente novo;
2. confirmar ausência de dependências apontando para o legado;
3. atualizar inventário, diagramas e runbooks;
4. encerrar formalmente o rollback;
5. arquivar os pontos de recuperação exigidos;
6. remover o ambiente anterior apenas em mudança separada e autorizada.
